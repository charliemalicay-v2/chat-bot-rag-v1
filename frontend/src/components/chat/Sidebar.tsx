import { MessageSquare, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/lib/types";

interface Props {
  conversations: Conversation[] | null; // null = still loading
  activeId: number | null;
  onSelect: (id: number) => void;
  onNew: () => void;
  onDelete: (id: number) => void;
}

export function Sidebar({ conversations, activeId, onSelect, onNew, onDelete }: Props) {
  return (
    <div className="flex h-full flex-col">
      <div className="p-3">
        <Button onClick={onNew} variant="outline" className="w-full justify-start">
          <Plus data-icon="inline-start" />
          New chat
        </Button>
      </div>
      <nav aria-label="Conversations" className="flex-1 overflow-y-auto px-2 pb-3">
        {conversations === null ? (
          <div className="space-y-2 px-1" aria-busy="true">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-2/3" />
          </div>
        ) : conversations.length === 0 ? (
          <p className="px-3 py-2 text-xs text-muted-foreground">Your conversations will appear here.</p>
        ) : (
          <ul className="space-y-0.5">
            {conversations.map((c) => (
              <li key={c.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onSelect(c.id)}
                  aria-current={c.id === activeId ? "true" : undefined}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-lg px-3 py-2 pr-9 text-left text-sm transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50",
                    c.id === activeId && "bg-muted font-medium",
                  )}
                >
                  <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="truncate">{c.title || `Conversation ${c.id}`}</span>
                </button>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Delete conversation: ${c.title || c.id}`}
                  onClick={() => onDelete(c.id)}
                  className="absolute top-1/2 right-1.5 -translate-y-1/2 opacity-0 focus-visible:opacity-100 group-focus-within:opacity-100 group-hover:opacity-100 max-md:opacity-100"
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </nav>
    </div>
  );
}
