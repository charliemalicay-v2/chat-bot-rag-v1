/** Minimal server-sent-events parser. Feed it decoded text chunks as they arrive. */

export interface SseEvent {
  event: string;
  data: string;
}

export interface SseParser {
  push(chunk: string): void;
  /** Call when the stream ends; emits a final event that lacked its blank-line terminator. */
  flush(): void;
}

function parseBlock(block: string): SseEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) continue; // blank or comment
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length > 0 ? { event, data: data.join("\n") } : null;
}

export function createSseParser(onEvent: (event: SseEvent) => void): SseParser {
  let buffer = "";

  const drain = (final: boolean) => {
    // Normalise CRLF / CR to LF. A CR at the very end of the buffer may be the first half of a
    // CRLF whose LF arrives in the next chunk, so hold it back instead of treating it as a
    // complete line break (that would split the event with a phantom blank line).
    const heldCr = !final && buffer.endsWith("\r");
    if (heldCr) buffer = buffer.slice(0, -1);
    buffer = buffer.replace(/\r\n?/g, "\n") + (heldCr ? "\r" : "");
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const parsed = parseBlock(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (parsed) onEvent(parsed);
    }
    if (final && buffer.trim() !== "") {
      const parsed = parseBlock(buffer);
      buffer = "";
      if (parsed) onEvent(parsed);
    }
  };

  return {
    push(chunk) {
      buffer += chunk;
      drain(false);
    },
    flush() {
      drain(true);
    },
  };
}
