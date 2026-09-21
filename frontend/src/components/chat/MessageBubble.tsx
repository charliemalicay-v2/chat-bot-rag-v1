import { RotateCw, TriangleAlert } from "lucide-react";
import ReactMarkdown from "react-markdown";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { SourcesList } from "./SourcesList";
import type { UiMessage } from "./types";

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1" role="status" aria-label="Assistant is typing">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

export function MessageBubble({ message, onRetry }: { message: UiMessage; onRetry?: () => void }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm whitespace-pre-wrap text-primary-foreground">
          {message.content}
        </div>
      </div>
    );
  }

  const waiting = message.status === "streaming" && message.content === "";
  return (
    <div className="flex justify-start">
      <div
        className={cn(
          "max-w-[92%] rounded-2xl rounded-bl-md border bg-card px-4 py-2.5 text-sm text-card-foreground",
          message.status === "error" && "border-destructive/40",
        )}
      >
        {waiting ? (
          <TypingDots />
        ) : message.content ? (
          <div className="md">
            <ReactMarkdown
              components={{
                a: ({ href, children }) => (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        ) : null}

        {message.status === "streaming" && message.content !== "" && (
          <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-foreground/60 align-middle" aria-hidden />
        )}

        {message.status === "stopped" && (
          <p className="mt-2 text-xs text-muted-foreground">Stopped. This reply was not saved.</p>
        )}

        {message.status === "error" && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-destructive" role="alert">
            <TriangleAlert className="size-3.5 shrink-0" aria-hidden />
            <span>{message.error ?? "Something went wrong."} Nothing was saved.</span>
            {onRetry && (
              <Button size="xs" variant="outline" onClick={onRetry}>
                <RotateCw data-icon="inline-start" />
                Retry
              </Button>
            )}
          </div>
        )}

        {message.status === "done" && <SourcesList sources={message.sources} />}
      </div>
    </div>
  );
}
