import type { Role, Source } from "@/lib/types";

/**
 * A message as shown in the UI. `status` covers what the server never stores:
 *  - streaming: answer still arriving
 *  - stopped:   the user pressed Stop; the partial answer was NOT saved
 *  - error:     the answer failed; nothing was saved, so it is safe to retry
 */
export interface UiMessage {
  key: string;
  role: Role;
  content: string;
  sources: Source[];
  status: "done" | "streaming" | "stopped" | "error";
  error?: string;
}
