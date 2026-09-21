import { LoaderCircle, TriangleAlert } from "lucide-react";

import type { Health } from "@/lib/types";

const LABELS: Record<string, string> = {
  mysql: "Database",
  vector_db: "Vector store",
  llm: "Language model",
  embedder: "Embedding model",
  index: "Document index",
};

/** Shown while the backend is starting up (first run downloads the models) or unreachable. */
export function HealthBanner({ health }: { health: Health | null }) {
  if (health?.status === "ok") return null;

  if (health === null) {
    return (
      <div role="alert" className="flex items-center gap-2 border-b bg-destructive/10 px-4 py-2 text-xs text-destructive">
        <TriangleAlert className="size-3.5 shrink-0" aria-hidden />
        Can’t reach the server. Retrying…
      </div>
    );
  }

  const failing = Object.entries(health.checks).filter(([, c]) => !c.ok);
  return (
    <div role="status" className="flex items-start gap-2 border-b bg-muted px-4 py-2 text-xs text-muted-foreground">
      <LoaderCircle className="mt-0.5 size-3.5 shrink-0 animate-spin" aria-hidden />
      <div>
        <p className="font-medium text-foreground">The assistant is still starting up.</p>
        <ul className="mt-0.5 space-y-0.5">
          {failing.map(([name, c]) => (
            <li key={name}>
              <span className="font-medium">{LABELS[name] ?? name}:</span> {c.detail}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
