import type { Conversation, ConversationDetail, Health } from "./types";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Best-effort human message from a DRF/Django error response. */
export async function errorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    const first = Object.entries(body ?? {})[0];
    if (first) return `${first[0]}: ${Array.isArray(first[1]) ? first[1].join(" ") : String(first[1])}`;
  } catch {
    /* not JSON */
  }
  return `Request failed (${res.status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { cache: "no-store", ...init });
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const listConversations = () => request<Conversation[]>("/api/conversations");

export const getConversation = (id: number) => request<ConversationDetail>(`/api/conversations/${id}`);

export const deleteConversation = (id: number) =>
  request<void>(`/api/conversations/${id}`, { method: "DELETE" });

/**
 * Service health. The backend answers 503 with a JSON body while something is still
 * starting (e.g. the model download), so a non-2xx response is still useful.
 * Returns null when the backend cannot be reached at all.
 */
export async function getHealth(): Promise<Health | null> {
  try {
    const res = await fetch("/api/health", { cache: "no-store" });
    const body = await res.json();
    return body?.checks ? (body as Health) : null;
  } catch {
    return null;
  }
}
