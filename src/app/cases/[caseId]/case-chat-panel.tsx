"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import {
  MessageSquare,
  Plus,
  History,
  Send,
  Scale,
  Copy,
  Check,
  RefreshCw,
  X,
  Edit2,
  Trash2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import {
  CaseChatConversation,
  CaseDocument,
  createCaseChatConversation,
  deleteCaseChatConversation,
  getCaseChatConversation,
  listCaseChatConversations,
  renameCaseChatConversation,
  sendCaseChatMessage,
} from "@/lib/api";
import { PageShell, PageHeader, PageBody } from "@/components/domain/page-shell";
import { CitationChip } from "@/components/domain/citation-chip";
import { formatDate } from "@/lib/formatters";

export function CaseChatPanel({
  caseId,
  documents,
}: {
  caseId: string;
  documents: CaseDocument[];
}) {
  const [conversations, setConversations] = useState<CaseChatConversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [active, setActive] = useState<CaseChatConversation | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // History slide-over drawer state
  const [historyOpen, setHistoryOpen] = useState(false);
  const [editingTitle, setEditingTitle] = useState(false);
  const [tempTitle, setTempTitle] = useState("");
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let live = true;
    listCaseChatConversations(caseId)
      .then((rows) => {
        if (!live) return;
        setConversations(rows);
        if (rows[0]) setActiveId((curr) => curr ?? rows[0].id);
      })
      .catch((err) => {
        if (live) setError(err instanceof Error ? err.message : "Could not load chat.");
      });
    return () => {
      live = false;
    };
  }, [caseId]);

  useEffect(() => {
    if (!activeId) return;
    let live = true;
    getCaseChatConversation(caseId, activeId)
      .then((conversation) => {
        if (live) {
          setActive(conversation);
          setTempTitle(conversation.title);
        }
      })
      .catch((err) => {
        if (live) setError(err instanceof Error ? err.message : "Could not load conversation.");
      });
    return () => {
      live = false;
    };
  }, [caseId, activeId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [active?.messages, busy]);

  async function handleNewChat() {
    setBusy(true);
    setError(null);
    try {
      const created = await createCaseChatConversation(caseId);
      setConversations((prev) => [created, ...prev]);
      setActiveId(created.id);
      setActive({ ...created, messages: [] });
      setHistoryOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create new chat.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveTitle() {
    if (!activeId || !tempTitle.trim()) return;
    try {
      const updated = await renameCaseChatConversation(caseId, activeId, tempTitle.trim());
      setConversations((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      setActive((prev) => (prev ? { ...prev, title: updated.title } : null));
      setEditingTitle(false);
    } catch {
      alert("Failed to rename conversation.");
    }
  }

  async function handleDeleteChat(id: string) {
    if (!confirm("Permanently delete this chat conversation?")) return;
    try {
      await deleteCaseChatConversation(caseId, id);
      const remaining = conversations.filter((c) => c.id !== id);
      setConversations(remaining);
      if (activeId === id) {
        setActiveId(remaining[0]?.id ?? null);
        setActive(null);
      }
    } catch {
      alert("Failed to delete chat.");
    }
  }

  async function handleSendMessage(customPrompt?: string) {
    const textToSend = customPrompt || draft.trim();
    if (!textToSend || busy) return;

    setBusy(true);
    setError(null);
    if (!customPrompt) setDraft("");

    try {
      let targetConvId = activeId;
      if (!targetConvId) {
        const created = await createCaseChatConversation(caseId);
        setConversations((prev) => [created, ...prev]);
        setActiveId(created.id);
        targetConvId = created.id;
      }

      const updated = await sendCaseChatMessage(caseId, targetConvId, {
        content: textToSend,
        include_india_code: true,
        acknowledge_incomplete_sources: false,
      });

      setActive(updated);
      setConversations((prev) =>
        prev.map((c) => (c.id === updated.id ? { ...c, title: updated.title, updated_at: updated.updated_at } : c))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSendMessage();
    }
  }

  function copyText(text: string, index: number) {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  }

  const starterPrompts = [
    "What are the primary claims asserted in this case?",
    "Summarize the key chronological events from the pleadings.",
    "Are there any conflicting assertions between the parties?",
    "Which statutory provisions and precedents are cited?",
  ];

  return (
    <PageShell className="flex flex-col flex-1 h-[calc(100vh-140px)]">
      {/* 1. Header */}
      <PageHeader
        title="Case assistant"
        description={
          editingTitle ? (
            <span className="flex items-center gap-2 mt-1">
              <input
                type="text"
                value={tempTitle}
                onChange={(e) => setTempTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSaveTitle()}
                className="input-field h-7 text-xs font-medium"
                autoFocus
              />
              <button type="button" onClick={handleSaveTitle} className="btn-secondary h-7 px-2 text-xs">
                Save
              </button>
            </span>
          ) : (
            <span
              onClick={() => setEditingTitle(true)}
              className="cursor-pointer hover:underline text-[var(--text-muted)] flex items-center gap-1.5 mt-0.5 text-xs"
              title="Click to rename"
            >
              <span>{active?.title || "New conversation"}</span>
              <Edit2 className="size-3 opacity-50" />
            </span>
          )
        }
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleNewChat}
              className="btn-ghost text-xs flex items-center gap-1"
              title="Start a new chat"
            >
              <Plus className="size-3.5" />
              <span>New chat</span>
            </button>
            <button
              type="button"
              onClick={() => setHistoryOpen(true)}
              className="btn-ghost text-xs flex items-center gap-1"
              title="View chat history"
            >
              <History className="size-3.5" />
              <span>History</span>
            </button>
          </div>
        }
      />

      {/* 2. Chat Body: Centered 720px Column */}
      <div className="flex-1 flex flex-col min-h-0 mx-auto w-full max-w-[720px]">
        {/* Messages List Area (Only this scrolls) */}
        <div className="flex-1 overflow-y-auto pr-2 space-y-6 pb-4">
          {!active?.messages || active.messages.length === 0 ? (
            /* Empty State */
            <div className="flex flex-col items-center justify-center h-full text-center py-12 space-y-6">
              <div>
                <Scale className="mx-auto size-9 text-[var(--brass)] mb-3" strokeWidth={1.5} />
                <h2 className="font-serif text-2xl font-medium text-[var(--text)]">
                  Ask about this case
                </h2>
                <p className="mt-1 text-xs text-[var(--text-muted)] max-w-sm">
                  Grounded decision support across your pleadings, affidavits, and case evidence.
                </p>
              </div>

              {/* 2x2 Starter Prompts Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-lg">
                {starterPrompts.map((p, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleSendMessage(p)}
                    className="p-3 text-left text-xs rounded-lg border border-[var(--border)] bg-[var(--surface)] text-[var(--text)] hover:border-[var(--brass)] hover:bg-[var(--surface-2)] transition leading-relaxed"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            (active.messages || []).map((msg, idx) => {
              const isUser = msg.role === "user";
              const isLatestAssistant = !isUser && idx === (active.messages || []).length - 1;

              return (
                <div
                  key={msg.id || idx}
                  className={`flex flex-col ${isUser ? "items-end" : "items-start"} space-y-2 group`}
                >
                  {isUser ? (
                    /* User Message: Right-aligned, surface-2 fill, 8px radius, max 75% */
                    <div className="rounded-lg bg-[var(--surface-2)] border border-[var(--border)] px-4 py-3 text-sm text-[var(--text)] max-w-[75%] leading-relaxed">
                      {msg.content}
                    </div>
                  ) : (
                    /* Assistant Message: No card, plain text at 15/25, brass scale icon */
                    <div className="w-full space-y-3">
                      <div className="flex items-start gap-3">
                        <div className="grid size-5 place-items-center rounded bg-[var(--surface-2)] text-[var(--brass)] shrink-0 mt-1">
                          <Scale className="size-3.5" />
                        </div>
                        <div className="flex-1 space-y-3 font-serif text-[15px] leading-[1.65] text-[var(--text)]">
                          <div className="whitespace-pre-wrap">{msg.content}</div>

                          {msg.retrieval_mode === "bm25_semantic_unavailable" && (
                            <div className="rounded-md border border-[var(--warning)]/30 bg-[var(--surface-2)] px-3 py-2 font-sans text-xs leading-relaxed text-[var(--text-muted)]">
                              Semantic retrieval was unavailable for this reply. It used keyword-ranked passages; check the cited sources and case coverage.
                            </div>
                          )}
                          {msg.retrieval_mode === "document_coverage_sampled" && (
                            <div className="rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 font-sans text-xs leading-relaxed text-[var(--text-muted)]">
                              This reply used representative passages across the case file, not every page. The coverage note below identifies documents or locations that were not fully covered.
                            </div>
                          )}
                          {msg.retrieval_mode === "bm25_plus_local_semantic" && (
                            <div className="font-sans text-[10px] text-[var(--text-faint)]">
                              Retrieval: keyword and local semantic passage ranking
                            </div>
                          )}

                          {/* Collapsed Sources Row */}
                          {msg.citations && msg.citations.length > 0 && (
                            <div className="pt-2 border-t border-[var(--border)] font-sans not-italic text-xs">
                              <div className="text-[11px] font-medium text-[var(--text-muted)] mb-1.5">
                                Sources ({msg.citations.length}):
                              </div>
                              <div className="flex flex-wrap gap-1.5">
                                {msg.citations.map((c, ci) => (
                                  <CitationChip
                                    key={ci}
                                    caseId={caseId}
                                    documentId={c.document_id || ""}
                                    unitId={c.source_unit_id || ""}
                                    filename={c.filename || c.title || "Document"}
                                    locator={c.locator || (c.page_number ? `p.${c.page_number}` : "")}
                                    quote={c.quote || c.statement || ""}
                                    start={c.source_start_char}
                                    end={c.source_end_char}
                                  />
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Message Actions on Hover */}
                      <div className="flex items-center gap-2 pl-8 opacity-0 group-hover:opacity-100 transition text-xs">
                        <button
                          type="button"
                          onClick={() => copyText(msg.content, idx)}
                          className="btn-ghost h-7 px-2 text-[11px] flex items-center gap-1"
                        >
                          {copiedIndex === idx ? <Check className="size-3 text-[var(--success)]" /> : <Copy className="size-3" />}
                          <span>{copiedIndex === idx ? "Copied" : "Copy"}</span>
                        </button>
                      </div>

                      {/* Follow-up suggestions under latest assistant message only */}
                      {isLatestAssistant && (
                        <div className="flex flex-wrap gap-2 pl-8 pt-1 font-sans">
                          {["What are the next procedural steps?", "Identify potential weak points in defendant's claims."].map((s, si) => (
                            <button
                              key={si}
                              type="button"
                              onClick={() => handleSendMessage(s)}
                              className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 text-xs text-[var(--text-muted)] hover:text-[var(--text)] hover:border-[var(--brass)] transition"
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}

          {/* Busy Streaming / Thinking Indicator */}
          {busy && (
            <div className="flex items-center gap-3 pl-2 text-xs text-[var(--text-muted)]">
              <Scale className="size-4 text-[var(--brass)] animate-pulse" />
              <span>Analyzing case documents and composing grounded answer…</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {error && (
          <div className="mb-2 rounded-md border border-[var(--danger)]/30 bg-[var(--surface)] p-3 text-xs text-[var(--danger)]">
            {error}
          </div>
        )}

        {/* 3. Pinned Auto-Growing Composer: 720px */}
        <div className="pt-2 border-t border-[var(--border)]">
          <div className="relative rounded-lg border border-[var(--border-strong)] bg-[var(--surface)] focus-within:border-[var(--brass)] transition p-2">
            <textarea
              ref={textareaRef}
              rows={2}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about this case, facts, or legal positions…"
              className="w-full resize-none bg-transparent text-sm text-[var(--text)] outline-none placeholder:text-[var(--text-faint)] pr-10"
            />

            <button
              type="button"
              disabled={busy || !draft.trim()}
              onClick={() => handleSendMessage()}
              className="absolute right-2.5 bottom-2.5 grid size-7 place-items-center rounded-full bg-[var(--primary)] text-white hover:bg-[var(--primary-hover)] disabled:opacity-40 transition"
            >
              <Send className="size-3.5" />
            </button>
          </div>

          <div className="mt-1.5 flex items-center justify-between text-[11px] text-[var(--text-faint)] px-1">
            <span>Enter to send · Shift+Enter for a new line</span>
            <span>Answers draw on this case file. Not legal advice.</span>
          </div>
        </div>
      </div>

      {/* 4. History Slide-Over Drawer (Left, 280px) */}
      {historyOpen && (
        <div className="fixed inset-0 z-50 flex bg-black/40">
          <div className="flex h-full w-[280px] flex-col border-r border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-drawer)]">
            <div className="flex items-center justify-between border-b border-[var(--border)] p-4">
              <h3 className="font-serif text-sm font-medium text-[var(--text)]">Chat history</h3>
              <button
                type="button"
                onClick={() => setHistoryOpen(false)}
                className="text-[var(--text-muted)] hover:text-[var(--text)] p-1"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1 divide-y divide-[var(--border)]">
              {conversations.length === 0 ? (
                <p className="p-4 text-center text-xs text-[var(--text-muted)]">No previous chats.</p>
              ) : (
                conversations.map((c) => (
                  <div
                    key={c.id}
                    onClick={() => {
                      setActiveId(c.id);
                      setHistoryOpen(false);
                    }}
                    className={`flex items-center justify-between p-2.5 rounded-md cursor-pointer transition text-xs ${
                      activeId === c.id ? "bg-[var(--primary-tint)] font-semibold text-[var(--primary)]" : "hover:bg-[var(--surface-2)] text-[var(--text)]"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <span className="block truncate">{c.title}</span>
                      <span className="text-[10px] text-[var(--text-muted)] font-normal">{formatDate(c.updated_at, true)}</span>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDeleteChat(c.id);
                      }}
                      className="p-1 text-[var(--text-muted)] hover:text-[var(--danger)]"
                      title="Delete chat"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </PageShell>
  );
}
