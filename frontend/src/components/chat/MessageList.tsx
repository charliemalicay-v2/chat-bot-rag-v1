"use client";

import { useEffect, useRef } from "react";

import { EmptyState } from "./EmptyState";
import { MessageBubble } from "./MessageBubble";
import type { UiMessage } from "./types";

const NEAR_BOTTOM_PX = 96;

interface Props {
  messages: UiMessage[];
  disabled: boolean;
  onSuggestion: (text: string) => void;
  onRetry: (key: string) => void;
}

export function MessageList({ messages, disabled, onSuggestion, onRetry }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const previousCount = useRef(0);

  // Follow the answer as it streams, unless the reader has scrolled up to re-read.
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (messages.length > previousCount.current) stickToBottom.current = true; // a new message was added
    previousCount.current = messages.length;
    if (stickToBottom.current) el.scrollTo({ top: el.scrollHeight });
  }, [messages]);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
  };

  return (
    <div ref={scroller} onScroll={onScroll} className="flex-1 overflow-y-auto" data-testid="message-scroller">
      {messages.length === 0 ? (
        <EmptyState onSuggestion={onSuggestion} disabled={disabled} />
      ) : (
        <div
          className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-6"
          role="log"
          aria-live="polite"
          aria-label="Conversation"
        >
          {messages.map((m) => (
            <MessageBubble
              key={m.key}
              message={m}
              onRetry={m.status === "error" ? () => onRetry(m.key) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}
