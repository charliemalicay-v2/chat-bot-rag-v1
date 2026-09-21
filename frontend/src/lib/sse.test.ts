import { describe, expect, it } from "vitest";

import { createSseParser, type SseEvent } from "./sse";

function collect(chunks: string[], flush = true): SseEvent[] {
  const events: SseEvent[] = [];
  const parser = createSseParser((e) => events.push(e));
  chunks.forEach((c) => parser.push(c));
  if (flush) parser.flush();
  return events;
}

describe("createSseParser", () => {
  it("parses event and data fields", () => {
    expect(collect(['event: token\ndata: {"text":"Hi"}\n\n'])).toEqual([{ event: "token", data: '{"text":"Hi"}' }]);
  });

  it("parses several events in one chunk", () => {
    const events = collect(["event: a\ndata: 1\n\nevent: b\ndata: 2\n\n"]);
    expect(events.map((e) => e.event)).toEqual(["a", "b"]);
  });

  it("reassembles an event split across arbitrary chunk boundaries", () => {
    const raw = 'event: token\ndata: {"text":"split me"}\n\n';
    for (let cut = 1; cut < raw.length; cut++) {
      expect(collect([raw.slice(0, cut), raw.slice(cut)])).toEqual([{ event: "token", data: '{"text":"split me"}' }]);
    }
  });

  it("does not emit an event until its terminating blank line arrives", () => {
    expect(collect(["event: a\ndata: 1\n"], false)).toEqual([]);
  });

  it("flush emits a final event that lacks the trailing blank line", () => {
    expect(collect(["event: done\ndata: {}"])).toEqual([{ event: "done", data: "{}" }]);
  });

  it("handles CRLF and lone CR line endings", () => {
    expect(collect(["event: a\r\ndata: 1\r\n\r\n"])).toEqual([{ event: "a", data: "1" }]);
    expect(collect(["event: a\rdata: 1\r\r"])).toEqual([{ event: "a", data: "1" }]);
  });

  it("a CRLF pair split between chunks is still one line break", () => {
    expect(collect(["event: a\r", "\ndata: 1\r", "\n\r", "\n"])).toEqual([{ event: "a", data: "1" }]);
  });

  it("joins multi-line data with newlines", () => {
    expect(collect(["data: line1\ndata: line2\n\n"])).toEqual([{ event: "message", data: "line1\nline2" }]);
  });

  it("defaults the event name to 'message'", () => {
    expect(collect(["data: x\n\n"])[0].event).toBe("message");
  });

  it("ignores comments, unknown fields and events without data", () => {
    expect(collect([": keep-alive\n\nid: 7\nretry: 100\n\nevent: only-name\n\n"])).toEqual([]);
  });

  it("keeps everything after the first colon and strips one leading space", () => {
    expect(collect(["data:  two spaces: and a colon\n\n"])[0].data).toBe(" two spaces: and a colon");
  });

  it("preserves unicode across events", () => {
    expect(collect(['event: token\ndata: {"text":"café ☕ 日本語"}\n\n'])[0].data).toContain("café ☕ 日本語");
  });
});
