import { ApiError, errorDetail } from "./api";
import { createSseParser } from "./sse";
import type { Source } from "./types";

export interface ChatDone {
  conversation_id: number;
  message_id: number;
}

export interface StreamChatOptions {
  message: string;
  conversationId: number | null;
  signal?: AbortSignal;
  onToken: (text: string) => void;
  onSources: (sources: Source[]) => void;
  onDone: (done: ChatDone) => void;
}

/** The stream started but the answer did not complete (model error, dropped connection). */
export class ChatStreamError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChatStreamError";
  }
}

/**
 * POST /api/chat and consume the server-sent events.
 * Resolves after the `done` event. Throws ApiError for HTTP failures (nothing was streamed),
 * ChatStreamError if the stream fails or ends early, and lets AbortError through on cancel.
 */
export async function streamChat(opts: StreamChatOptions): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({
      message: opts.message,
      ...(opts.conversationId !== null ? { conversation_id: opts.conversationId } : {}),
    }),
    signal: opts.signal,
    cache: "no-store",
  });
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
  if (!res.body) throw new ChatStreamError("The server sent an empty response.");

  let finished = false;
  let failure: ChatStreamError | null = null;

  const parser = createSseParser(({ event, data }) => {
    let payload: unknown;
    try {
      payload = JSON.parse(data);
    } catch {
      failure ??= new ChatStreamError("Received a malformed event from the server.");
      return;
    }
    const body = payload as Record<string, unknown>;
    switch (event) {
      case "token":
        opts.onToken(String(body.text ?? ""));
        break;
      case "sources":
        opts.onSources((body.sources as Source[]) ?? []);
        break;
      case "done":
        finished = true;
        opts.onDone(body as unknown as ChatDone);
        break;
      case "error":
        failure ??= new ChatStreamError(String(body.detail ?? "The answer failed."));
        break;
    }
  });

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
      if (failure) break;
    }
    parser.push(decoder.decode());
    parser.flush();
  } finally {
    reader.cancel().catch(() => undefined);
  }

  if (failure) throw failure;
  if (!finished) throw new ChatStreamError("The connection closed before the answer finished.");
}
