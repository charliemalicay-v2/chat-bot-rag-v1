"use client";

import { Menu } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster } from "@/components/ui/sonner";
import {
  ApiError,
  deleteConversation,
  getConversation,
  getHealth,
  listConversations,
} from "@/lib/api";
import { ChatStreamError, streamChat } from "@/lib/chat-stream";
import type { Conversation, Health, Message } from "@/lib/types";

import { Composer } from "./Composer";
import { HealthBanner } from "./HealthBanner";
import { MessageList } from "./MessageList";
import { Sidebar } from "./Sidebar";
import type { UiMessage } from "./types";

const ACTIVE_KEY = "chat.activeConversation";
const HEALTH_POLL_MS = 5000;

let keyCounter = 0;
const newKey = () => `m${Date.now().toString(36)}-${keyCounter++}`;

const toUi = (m: Message): UiMessage => ({
  key: `s${m.id}`,
  role: m.role,
  content: m.content,
  sources: m.sources ?? [],
  status: "done",
});

function readStoredId(): number | null {
  try {
    const n = Number(localStorage.getItem(ACTIVE_KEY));
    return Number.isInteger(n) && n > 0 ? n : null;
  } catch {
    return null; // storage blocked (private mode etc.)
  }
}

function describe(err: unknown): string {
  if (err instanceof ApiError || err instanceof ChatStreamError) return err.message;
  return "Could not reach the server.";
}

export function ChatApp() {
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [activeId, setActiveIdState] = useState<number | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [health, setHealth] = useState<Health | null | undefined>(undefined); // undefined = not checked yet
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Bumped to make the health poller start again (it stops once everything is ready).
  const [healthNonce, setHealthNonce] = useState(0);

  // Refs mirror state that async callbacks must read fresh (avoids stale closures).
  const activeIdRef = useRef<number | null>(null);
  const streamingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  const setActive = useCallback((id: number | null) => {
    activeIdRef.current = id;
    setActiveIdState(id);
    try {
      if (id === null) localStorage.removeItem(ACTIVE_KEY);
      else localStorage.setItem(ACTIVE_KEY, String(id));
    } catch {
      /* storage unavailable: the conversation just is not remembered across reloads */
    }
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await listConversations());
    } catch {
      setConversations((prev) => prev ?? []);
    }
  }, []);

  const patch = useCallback((key: string, fn: (m: UiMessage) => UiMessage) => {
    setMessages((ms) => ms.map((m) => (m.key === key ? fn(m) : m)));
  }, []);

  const openConversation = useCallback(
    async (id: number) => {
      abortRef.current?.abort();
      setSidebarOpen(false);
      setLoadingConversation(true);
      try {
        const detail = await getConversation(id);
        setActive(id);
        setMessages(detail.messages.map(toUi));
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          setActive(null); // it was deleted elsewhere
          setMessages([]);
          void refreshConversations();
        } else {
          toast.error(`Could not open the conversation. ${describe(err)}`);
        }
      } finally {
        setLoadingConversation(false);
      }
    },
    [refreshConversations, setActive],
  );

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    setActive(null);
    setMessages([]);
    setSidebarOpen(false);
  }, [setActive]);

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || streamingRef.current) return;

      const controller = new AbortController();
      abortRef.current = controller;
      streamingRef.current = true;
      setStreaming(true);

      const botKey = newKey();
      setMessages((ms) => [
        ...ms,
        { key: newKey(), role: "user", content: text, sources: [], status: "done" },
        { key: botKey, role: "assistant", content: "", sources: [], status: "streaming" },
      ]);

      try {
        await streamChat({
          message: text,
          conversationId: activeIdRef.current,
          signal: controller.signal,
          onToken: (t) => patch(botKey, (m) => ({ ...m, content: m.content + t })),
          onSources: (sources) => patch(botKey, (m) => ({ ...m, sources })),
          onDone: (done) => setActive(done.conversation_id),
        });
        patch(botKey, (m) => ({ ...m, status: "done" }));
        void refreshConversations();
      } catch (err) {
        if (controller.signal.aborted) {
          patch(botKey, (m) => ({ ...m, status: "stopped" }));
        } else {
          const message = describe(err);
          patch(botKey, (m) => ({ ...m, status: "error", error: message }));
          toast.error(message);
          setHealthNonce((n) => n + 1); // show the banner if the backend is down, and clear it when back
        }
      } finally {
        streamingRef.current = false;
        abortRef.current = null;
        setStreaming(false);
      }
    },
    [patch, refreshConversations, setActive],
  );

  const retry = useCallback(
    (botKey: string) => {
      if (streamingRef.current) return;
      const idx = messages.findIndex((m) => m.key === botKey);
      const question = idx > 0 ? messages[idx - 1] : undefined;
      if (!question || question.role !== "user") return;
      // A failed answer saved nothing on the server, so drop the pair and ask again.
      setMessages((ms) => ms.filter((_, i) => i !== idx && i !== idx - 1));
      void send(question.content);
    },
    [messages, send],
  );

  const remove = useCallback(
    async (id: number) => {
      try {
        await deleteConversation(id);
        setConversations((cs) => cs?.filter((c) => c.id !== id) ?? cs);
        if (activeIdRef.current === id) newChat();
        toast.success("Conversation deleted");
      } catch (err) {
        toast.error(`Could not delete the conversation. ${describe(err)}`);
      }
    },
    [newChat],
  );

  // First load: conversation list, then reopen the one that was active before a reload.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let list: Conversation[] = [];
      try {
        list = await listConversations();
      } catch {
        /* the health banner explains an unreachable backend */
      }
      if (cancelled) return;
      setConversations(list);
      const stored = readStoredId();
      if (stored !== null && list.some((c) => c.id === stored)) void openConversation(stored);
    })();
    return () => {
      cancelled = true;
    };
  }, [openConversation]);

  // Poll health until everything is ready (first run downloads the models).
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const h = await getHealth();
      if (stopped) return;
      setHealth(h);
      if (h?.status !== "ok") timer = setTimeout(tick, HEALTH_POLL_MS);
    };
    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [healthNonce]);

  const sidebar = (
    <Sidebar
      conversations={conversations}
      activeId={activeId}
      onSelect={(id) => void openConversation(id)}
      onNew={newChat}
      onDelete={(id) => void remove(id)}
    />
  );

  return (
    <>
      <div className="flex h-dvh overflow-hidden bg-background">
        <aside className="hidden w-72 shrink-0 border-r bg-sidebar text-sidebar-foreground md:block">{sidebar}</aside>

        <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
          <SheetContent side="left" showCloseButton={false} className="w-72 max-w-[85vw] p-0 md:hidden">
            <SheetTitle className="sr-only">Conversations</SheetTitle>
            {sidebar}
          </SheetContent>
        </Sheet>

        <main className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center gap-2 border-b px-3 py-2 md:hidden">
            <Button variant="ghost" size="icon" onClick={() => setSidebarOpen(true)} aria-label="Open conversations">
              <Menu />
            </Button>
            <span className="truncate text-sm font-medium">Northwind assistant</span>
          </header>

          {health !== undefined && <HealthBanner health={health} />}

          {loadingConversation ? (
            <div className="mx-auto w-full max-w-3xl flex-1 space-y-4 px-4 py-6" aria-busy="true">
              <Skeleton className="ml-auto h-10 w-1/2" />
              <Skeleton className="h-24 w-4/5" />
            </div>
          ) : (
            <MessageList
              messages={messages}
              disabled={streaming}
              onSuggestion={(t) => void send(t)}
              onRetry={retry}
            />
          )}

          <Composer streaming={streaming} onSend={(t) => void send(t)} onStop={() => abortRef.current?.abort()} />
        </main>
      </div>
      <Toaster position="top-center" />
    </>
  );
}
