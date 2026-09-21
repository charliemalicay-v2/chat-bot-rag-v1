import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import { ChatStreamError, streamChat } from "./chat-stream";
import type { Source } from "./types";

const enc = new TextEncoder();

/** A fetch Response whose body delivers the given byte chunks one at a time. */
function sseResponse(chunks: (string | Uint8Array)[], init: ResponseInit = { status: 200 }): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(typeof c === "string" ? enc.encode(c) : c);
      controller.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" }, ...init });
}

const ev = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

function setup(response: Response | (() => Response)) {
  const fetchMock = vi.fn(async () => (typeof response === "function" ? response() : response));
  vi.stubGlobal("fetch", fetchMock);
  const calls = { tokens: [] as string[], sources: [] as Source[][], done: [] as unknown[] };
  const opts = {
    message: "hello",
    conversationId: null as number | null,
    onToken: (t: string) => calls.tokens.push(t),
    onSources: (s: Source[]) => calls.sources.push(s),
    onDone: (d: unknown) => calls.done.push(d),
  };
  return { fetchMock, calls, opts };
}

afterEach(() => vi.unstubAllGlobals());

describe("streamChat", () => {
  it("delivers tokens, then sources, then done", async () => {
    const source = { type: "document", title: "T", path: "p.md", chunk_index: 0, distance: 0.2, snippet: "s" };
    const { calls, opts } = setup(
      sseResponse([
        ev("token", { text: "Hel" }),
        ev("token", { text: "lo" }),
        ev("sources", { sources: [source] }),
        ev("done", { conversation_id: 7, message_id: 9 }),
      ]),
    );
    await streamChat(opts);
    expect(calls.tokens).toEqual(["Hel", "lo"]);
    expect(calls.sources).toEqual([[source]]);
    expect(calls.done).toEqual([{ conversation_id: 7, message_id: 9 }]);
  });

  it("sends the message, and conversation_id only when there is one", async () => {
    const first = setup(sseResponse([ev("done", { conversation_id: 1, message_id: 2 })]));
    await streamChat(first.opts);
    const [url, init] = first.fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ message: "hello" });

    const second = setup(sseResponse([ev("done", { conversation_id: 5, message_id: 2 })]));
    await streamChat({ ...second.opts, conversationId: 5 });
    const init2 = (second.fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(init2.body as string)).toEqual({ message: "hello", conversation_id: 5 });
  });

  it("handles events and multi-byte characters split across network chunks", async () => {
    const bytes = enc.encode(ev("token", { text: "café ☕" }) + ev("done", { conversation_id: 1, message_id: 2 }));
    // one-byte chunks split every UTF-8 sequence
    const { calls, opts } = setup(sseResponse(Array.from(bytes, (b) => new Uint8Array([b]))));
    await streamChat(opts);
    expect(calls.tokens).toEqual(["café ☕"]);
    expect(calls.done).toHaveLength(1);
  });

  it("throws ApiError with the server's detail for an HTTP failure (nothing streamed)", async () => {
    const { calls, opts } = setup(
      new Response(JSON.stringify({ detail: "The language model is unavailable: down" }), {
        status: 502,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(streamChat(opts)).rejects.toMatchObject({
      name: "ApiError",
      status: 502,
      message: "The language model is unavailable: down",
    });
    expect(calls.tokens).toEqual([]);
  });

  it("formats DRF validation errors", async () => {
    const { opts } = setup(new Response(JSON.stringify({ message: ["This field may not be blank."] }), { status: 400 }));
    await expect(streamChat(opts)).rejects.toThrow("message: This field may not be blank.");
  });

  it("surfaces a mid-stream error event as ChatStreamError, keeping the tokens already delivered", async () => {
    const { calls, opts } = setup(
      sseResponse([ev("token", { text: "partial" }), ev("error", { detail: "The language model failed: oom" })]),
    );
    const promise = streamChat(opts);
    await expect(promise).rejects.toBeInstanceOf(ChatStreamError);
    await expect(promise).rejects.toThrow("The language model failed: oom");
    expect(calls.tokens).toEqual(["partial"]);
    expect(calls.done).toEqual([]);
  });

  it("fails when the connection closes before `done`", async () => {
    const { opts } = setup(sseResponse([ev("token", { text: "cut off" })]));
    await expect(streamChat(opts)).rejects.toThrow("closed before the answer finished");
  });

  it("flags a malformed event payload instead of silently ignoring it", async () => {
    const { opts } = setup(sseResponse(["event: token\ndata: {not json\n\n"]));
    await expect(streamChat(opts)).rejects.toThrow("malformed event");
  });

  it("propagates an abort so the caller can tell a user stop from a failure", async () => {
    const controller = new AbortController();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        return new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        });
      }),
    );
    const promise = streamChat({
      message: "x",
      conversationId: null,
      signal: controller.signal,
      onToken: () => {},
      onSources: () => {},
      onDone: () => {},
    });
    controller.abort();
    await expect(promise).rejects.toMatchObject({ name: "AbortError" });
    await expect(promise).rejects.not.toBeInstanceOf(ApiError);
  });
});
