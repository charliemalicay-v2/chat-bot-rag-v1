"use client";

import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

/** Keep in step with MAX_QUESTION_CHARS in backend/chat/serializers.py. */
export const MAX_MESSAGE_CHARS = 2000;
const MAX_HEIGHT_PX = 200;

interface Props {
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function Composer({ streaming, onSend, onStop }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Grow with the content, up to a cap.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
    // Only show a scrollbar once the cap is reached (it otherwise flashes arrows on one line).
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT_PX ? "auto" : "hidden";
  }, [value]);

  const trimmed = value.trim();
  const canSend = trimmed.length > 0 && !streaming;

  const submit = () => {
    if (!canSend) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <div className="border-t bg-background px-4 py-3">
      <form
        className="mx-auto flex w-full max-w-3xl items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="relative flex-1">
          <Textarea
            ref={ref}
            value={value}
            rows={1}
            maxLength={MAX_MESSAGE_CHARS}
            placeholder="Ask about shipping, returns, gear care, or products…"
            aria-label="Message"
            className="min-h-10 resize-none py-2.5"
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends, Shift+Enter adds a line. Ignore Enter while an IME is composing.
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
          />
          {value.length > MAX_MESSAGE_CHARS - 200 && (
            <span className="pointer-events-none absolute right-2 bottom-1 text-[10px] text-muted-foreground">
              {value.length}/{MAX_MESSAGE_CHARS}
            </span>
          )}
        </div>
        {streaming ? (
          <Button type="button" size="icon-lg" variant="outline" onClick={onStop} aria-label="Stop generating">
            <Square className="fill-current" />
          </Button>
        ) : (
          <Button type="submit" size="icon-lg" disabled={!canSend} aria-label="Send message">
            <ArrowUp />
          </Button>
        )}
      </form>
      <p className="mx-auto mt-1.5 w-full max-w-3xl text-center text-[11px] text-muted-foreground">
        Answers are generated from the store’s documents and can be wrong. Check the sources.
      </p>
    </div>
  );
}
