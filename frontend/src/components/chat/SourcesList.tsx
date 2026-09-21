import { ChevronDown, FileText, Package } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { DocumentSource, ProductSource, Source } from "@/lib/types";

/** Snippets are raw Markdown; drop heading markers so they read as plain text. */
export function cleanSnippet(snippet: string): string {
  return snippet.replace(/(^|\s)#{1,6}\s+/g, "$1").trim();
}

/** Cosine distance (0 = same direction) to an easy-to-read match percentage. */
export function relevance(distance: number): number {
  return Math.max(0, Math.min(100, Math.round((1 - distance) * 100)));
}

function DocumentItem({ s }: { s: DocumentSource }) {
  return (
    <li className="rounded-lg border bg-background p-3">
      <div className="flex flex-wrap items-center gap-2">
        <FileText className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <span className="text-sm font-medium">{s.title}</span>
        <Badge variant="secondary">{relevance(s.distance)}% match</Badge>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {s.path} · section {s.chunk_index + 1}
      </p>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">“{cleanSnippet(s.snippet)}…”</p>
    </li>
  );
}

function ProductItem({ s }: { s: ProductSource }) {
  const inStock = s.stock > 0;
  return (
    <li className="rounded-lg border bg-background p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Package className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <span className="text-sm font-medium">{s.name}</span>
        <Badge variant={inStock ? "secondary" : "destructive"}>
          {inStock ? `${s.stock} in stock` : "Out of stock"}
        </Badge>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {s.category} · SKU {s.sku} · ${s.price}
      </p>
    </li>
  );
}

export function SourcesList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;
  return (
    <details className="group mt-3 text-sm">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-md px-1 py-0.5 text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none [&::-webkit-details-marker]:hidden">
        <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" aria-hidden />
        {sources.length} {sources.length === 1 ? "source" : "sources"}
      </summary>
      <ul className="mt-2 space-y-2">
        {sources.map((s, i) =>
          s.type === "document" ? (
            <DocumentItem key={`d-${s.path}-${s.chunk_index}-${i}`} s={s} />
          ) : (
            <ProductItem key={`p-${s.sku}`} s={s} />
          ),
        )}
      </ul>
    </details>
  );
}
