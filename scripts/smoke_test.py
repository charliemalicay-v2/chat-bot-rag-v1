#!/usr/bin/env python3
"""End-to-end smoke test for a running stack. Standard library only.

    python scripts/smoke_test.py                       # through the frontend proxy (http://127.0.0.1:3000)
    python scripts/smoke_test.py --direct --base http://127.0.0.1:8000   # straight at Django
    python scripts/smoke_test.py --wait 900            # first start: wait for the model downloads

Uses the real LLM and embedding model, so it takes a while on CPU. Checks are chosen to
be deterministic where the LLM's wording is not: what matters is retrieval, streaming,
persistence, and the refusal path, not the exact sentence.
Exits 0 when every check passes, 1 otherwise. Conversations it creates are deleted.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

FAILURES: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        FAILURES.append(label)
    return ok


def warn(ok: bool, label: str) -> None:
    if not ok:
        print(f"  [WARN] {label}  (LLM wording varies; not a failure)")
    else:
        print(f"  [ ok ] {label}")


class Client:
    def __init__(self, base: str, direct: bool):
        self.base = base.rstrip("/")
        self.slash = "/" if direct else ""  # Django wants trailing slashes; the Next proxy redirects them away

    def url(self, path: str) -> str:
        return f"{self.base}/api/{path.strip('/')}{self.slash}"

    def request(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url(path), data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as exc:
            return exc

    def json(self, method: str, path: str, body: dict | None = None):
        resp = self.request(method, path, body)
        raw = resp.read()
        return resp.status if hasattr(resp, "status") else resp.code, (json.loads(raw) if raw else None)

    def chat(self, message: str, conversation_id: int | None = None) -> dict:
        body = {"message": message, **({"conversation_id": conversation_id} if conversation_id else {})}
        t0 = time.time()
        resp = self.request("POST", "chat", body)
        status = getattr(resp, "status", None) or resp.code
        out = {"status": status, "events": [], "tokens": [], "first_token_s": None, "sources": [], "done": None}
        if status != 200:
            out["error"] = resp.read().decode(errors="replace")
            return out
        event = None
        for raw in resp:
            line = raw.decode().rstrip("\n")
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                out["events"].append(event)
                if event == "token":
                    if out["first_token_s"] is None:
                        out["first_token_s"] = time.time() - t0
                    out["tokens"].append(data["text"])
                elif event == "sources":
                    out["sources"] = data["sources"]
                elif event == "done":
                    out["done"] = data
                elif event == "error":
                    out["error"] = data
        out["answer"] = "".join(out["tokens"]).strip()
        out["total_s"] = time.time() - t0
        return out


def wait_until_healthy(client: Client, timeout: int) -> bool:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            status, body = client.json("GET", "health")
            if status == 200 and body and body.get("status") == "ok":
                return True
            failing = {k: v["detail"][:70] for k, v in (body or {}).get("checks", {}).items() if not v["ok"]}
            note = f"waiting: {failing}"
        except Exception as exc:  # noqa: BLE001 - backend still starting
            note = f"waiting: {exc}"
        if note != last:
            print(f"    {note}")
            last = note
        time.sleep(5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="http://127.0.0.1:3000")
    parser.add_argument("--direct", action="store_true", help="talk to Django directly (trailing slashes)")
    parser.add_argument("--wait", type=int, default=120, help="seconds to wait for a healthy stack")
    args = parser.parse_args()
    client = Client(args.base, args.direct)
    created: list[int] = []

    print(f"Smoke test against {args.base}")

    print("\n1. Health")
    healthy = wait_until_healthy(client, args.wait)
    check(healthy, "all backend checks report ok")
    if not healthy:
        _, body = client.json("GET", "health")
        print(json.dumps(body, indent=2)[:1500])
        return 1
    _, health = client.json("GET", "health")
    chunks = health["checks"]["index"]["detail"]
    check(chunks.endswith("chunks indexed"), "documents are ingested", chunks)

    print("\n2. In-scope question (documents)")
    r = client.chat("How long do I have to return an item, and is shipping free for returns?")
    check(r["status"] == 200, "HTTP 200 event stream", str(r.get("error", "")))
    check(r["events"][-2:] == ["sources", "done"] and set(r["events"][:-2]) == {"token"},
          "events arrive as token* -> sources -> done")
    check(len(r["tokens"]) > 3, "answer streams as several tokens", f"{len(r['tokens'])} tokens")
    check(any(s["type"] == "document" and s["path"] == "shipping-and-returns.md" for s in r["sources"]),
          "sources include the returns policy")
    warn("60" in r["answer"], "answer mentions 60 days")
    print(f"     first token {r['first_token_s']:.1f}s, total {r['total_s']:.1f}s")
    if r["done"]:
        created.append(r["done"]["conversation_id"])
    cid = r["done"]["conversation_id"] if r["done"] else None

    print("\n3. Structured data (MySQL product table)")
    r2 = client.chat("Is the Summit insulated sleeping pad in stock?")
    pad = next((s for s in r2["sources"] if s["type"] == "product" and s["sku"] == "NW-PAD-INS"), None)
    check(pad is not None and pad["stock"] == 0, "product source carries the sold-out stock level")
    warn(any(w in r2["answer"].lower() for w in ("out of stock", "not in stock", "unavailable")),
         "answer says it is out of stock")
    if r2["done"]:
        created.append(r2["done"]["conversation_id"])

    print("\n4. Follow-up keeps the conversation")
    r3 = client.chat("what about for Canadian customers?", cid)
    check(r3["done"] is not None and r3["done"]["conversation_id"] == cid, "reply is added to the same conversation")
    check(any(s["path"] == "shipping-and-returns.md" for s in r3["sources"] if s["type"] == "document"),
          "short follow-up retrieves the right document (previous question used as context)")

    print("\n5. Out-of-scope question is refused, not answered")
    r4 = client.chat("What is the capital of France?")
    check(r4["sources"] == [] and "don't want to guess" in r4["answer"], "fixed 'I don't know' reply, no sources")
    # Timing is only a hint (retrieval still embeds the question, and the CPU may be busy).
    warn((r4["first_token_s"] or 99) < 5, f"replied without waiting on the LLM ({r4['first_token_s']:.2f}s)")
    if r4["done"]:
        created.append(r4["done"]["conversation_id"])

    print("\n6. Persistence")
    if cid:
        status, conv = client.json("GET", f"conversations/{cid}")
        check(status == 200 and [m["role"] for m in conv["messages"]] == ["user", "assistant", "user", "assistant"],
              "conversation has 4 messages in order")
        check(bool(conv["messages"][1]["sources"]), "sources are stored with the assistant message")
    status, listing = client.json("GET", "conversations")
    check(status == 200 and all(c in [x["id"] for x in listing] for c in created), "conversations are listed")

    print("\n7. Input validation")
    status, _ = client.json("POST", "chat", {"message": "   "})
    check(status == 400, "blank message -> 400", str(status))
    status, _ = client.json("POST", "chat", {"message": "hi there", "conversation_id": 99999999})
    check(status == 404, "unknown conversation -> 404", str(status))

    print("\n8. Cleanup")
    for c in dict.fromkeys(created):
        status, _ = client.json("DELETE", f"conversations/{c}")
        check(status == 204, f"deleted conversation {c}", str(status))

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s): " + "; ".join(FAILURES))
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
