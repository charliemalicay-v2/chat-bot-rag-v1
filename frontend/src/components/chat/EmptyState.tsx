import { Tent } from "lucide-react";

import { Button } from "@/components/ui/button";

const SUGGESTIONS = [
  "How long do I have to return an item?",
  "Can I put my tent in the washing machine?",
  "Is the Summit insulated sleeping pad in stock?",
  "What are your Sunday opening hours?",
];

export function EmptyState({ onSuggestion, disabled }: { onSuggestion: (text: string) => void; disabled: boolean }) {
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center gap-6 px-4 py-10 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-primary text-primary-foreground">
        <Tent className="size-6" aria-hidden />
      </div>
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Northwind Outfitters assistant</h1>
        <p className="text-sm text-muted-foreground">
          Ask about shipping and returns, the warranty, gear care, or products and stock. Answers come from our
          documents and catalog, with sources shown under each reply.
        </p>
      </div>
      <div className="grid w-full gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <Button
            key={s}
            variant="outline"
            disabled={disabled}
            onClick={() => onSuggestion(s)}
            className="h-auto justify-start px-3 py-2.5 text-left whitespace-normal"
          >
            {s}
          </Button>
        ))}
      </div>
    </div>
  );
}
