export type Role = "user" | "assistant";

export interface DocumentSource {
  type: "document";
  title: string;
  path: string;
  chunk_index: number;
  /** Cosine distance: lower means closer to the question. */
  distance: number;
  snippet: string;
}

export interface ProductSource {
  type: "product";
  sku: string;
  name: string;
  category: string;
  price: string;
  stock: number;
}

export type Source = DocumentSource | ProductSource;

export interface Message {
  id: number;
  role: Role;
  content: string;
  sources: Source[];
  created_at: string;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface HealthCheck {
  ok: boolean;
  detail: string;
}

export interface Health {
  status: "ok" | "degraded";
  checks: Record<string, HealthCheck>;
}
