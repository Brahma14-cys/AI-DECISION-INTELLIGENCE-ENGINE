"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import {
  Search,
  ExternalLink,
  Bookmark,
  BookmarkCheck,
  CheckCircle2,
  Filter,
  ChevronDown,
  ChevronUp,
  X,
  Scale,
  Sparkles,
  ArrowLeft,
  Copy,
  Check,
  BookOpen,
  Trash2,
  FileText,
  Clock,
  ShieldCheck,
  AlertCircle,
  HelpCircle,
  Edit3,
} from "lucide-react";
import {
  LegalResearchResponse,
  LegalResearchResult,
  LegalResearchSuggestion,
  LegalAuthorityReview,
  GroundedResearchAnswer,
  LegalResearchDocument,
  searchLegalAuthorities,
  getLegalResearchSuggestions,
  listAuthorityReviews,
  saveAuthorityReview,
  getIndianKanoonDocument,
  createGroundedResearchAnswer,
} from "@/lib/api";
import {
  PageShell,
  PageHeader,
  PageBody,
  PageFootnote,
} from "@/components/domain/page-shell";
import { InlineAlert } from "@/components/domain/inline-alert";
import { canonicalizeAuthority, isValidLegalReference, formatDate } from "@/lib/formatters";

// Helper to format unstructured / clumped legal text into cleanly readable sections and paragraphs
function formatLegalText(rawText: string): { type: "heading" | "clause" | "proviso" | "paragraph"; text: string; label?: string }[] {
  if (!rawText) return [];

  // Strip raw HTML tags if present
  let clean = rawText
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "")
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, "")
    .replace(/<br\s*[\/]?>/gi, "\n")
    .replace(/<\/p>/gi, "\n\n")
    .replace(/<\/div>/gi, "\n\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");

  // If text is already multi-paragraph, preserve it; otherwise break on clause boundaries
  let rawBlocks = clean.split(/\n{2,}/);
  if (rawBlocks.length <= 2 && clean.length > 300) {
    // Break on numbered sections like "4. Consequence...", "(1)", "(2)", "(a)", "Provided that", etc.
    const splitRegex = /(?=(?:^\d+\.\s+[A-Z]|\.\s+(?:\d+\.\s+[A-Z]|\(\d+\)|\([a-z]\)|(?:Provided\s+that|Provided\s+further\s+that|Explanation(?:\s+\d+)?:))))/g;
    rawBlocks = clean.split(splitRegex).map((b) => b.replace(/^\.\s+/, "").trim()).filter(Boolean);
  }

  const formatted: { type: "heading" | "clause" | "proviso" | "paragraph"; text: string; label?: string }[] = [];

  for (const block of rawBlocks) {
    const trimmed = block.trim();
    if (!trimmed) continue;

    // Check if it's a section heading (e.g. "4. Consequence of breach of provisions of section 3.")
    const headingMatch = trimmed.match(/^(\d+\.\s+[^.\n]{3,80}\.?)(?:\s+([\s\S]+))?$/);
    if (headingMatch && headingMatch[1].length < 100 && !headingMatch[1].includes("(") && !headingMatch[1].includes(",")) {
      formatted.push({
        type: "heading",
        text: headingMatch[1],
      });
      if (headingMatch[2]?.trim()) {
        formatted.push({
          type: "paragraph",
          text: headingMatch[2].trim(),
        });
      }
      continue;
    }

    // Check if it starts with a clause identifier like (1), (2), (a), (b), (i), (iv)
    const clauseMatch = trimmed.match(/^(\((?:\d+|[a-z]{1,2}|[ivx]{1,4})\))\s*([\s\S]+)$/i);
    if (clauseMatch) {
      formatted.push({
        type: "clause",
        label: clauseMatch[1],
        text: clauseMatch[2].trim(),
      });
      continue;
    }

    // Check if it's a Proviso or Explanation
    if (/^(?:Provided\s+that|Provided\s+further\s+that|Explanation)/i.test(trimmed)) {
      formatted.push({
        type: "proviso",
        text: trimmed,
      });
      continue;
    }

    // Default paragraph
    formatted.push({
      type: "paragraph",
      text: trimmed,
    });
  }

  return formatted;
}

export function CaseLegalResearchPanel({
  caseId,
  initialQuery,
  onClearInitialQuery,
}: {
  caseId: string;
  initialQuery?: string;
  onClearInitialQuery?: () => void;
}) {
  const [activeView, setActiveView] = useState<"search" | "saved">("search");
  const [query, setQuery] = useState(initialQuery || "");
  const [sourceFilter, setSourceFilter] = useState<"all" | "india_code" | "indian_kanoon">("all");
  const [court, setCourt] = useState("");
  const [act, setAct] = useState("");
  const [section, setSection] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<LegalResearchResponse | null>(null);

  // Suggestions & saved authorities
  const [suggestions, setSuggestions] = useState<LegalResearchSuggestion[]>([]);
  const [authorityReviews, setAuthorityReviews] = useState<LegalAuthorityReview[]>([]);
  const [showAllSuggestions, setShowAllSuggestions] = useState(false);
  const [savedStatusFilter, setSavedStatusFilter] = useState<"all" | "verified" | "needs_review" | "not_relevant">("all");
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState("");

  // Document preview reader & Gemini note
  const [openedDoc, setOpenedDoc] = useState<LegalResearchDocument | null>(null);
  const [docLoading, setDocLoading] = useState(false);
  const [docSearchQuery, setDocSearchQuery] = useState("");
  const [copiedDoc, setCopiedDoc] = useState(false);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [researchNote, setResearchNote] = useState<GroundedResearchAnswer | null>(null);
  const [noteLoading, setNoteLoading] = useState(false);

  // Load suggestions and saved authorities
  const refreshReviews = useCallback(() => {
    void listAuthorityReviews(caseId)
      .then((res) => {
        setAuthorityReviews(res || []);
      })
      .catch(() => undefined);
  }, [caseId]);

  useEffect(() => {
    let active = true;
    void getLegalResearchSuggestions(caseId)
      .then((res) => {
        if (active) setSuggestions(res.suggestions || []);
      })
      .catch(() => undefined);

    refreshReviews();

    return () => {
      active = false;
    };
  }, [caseId, refreshReviews]);

  // Clean canonical suggestions (filter noise and merge duplicates)
  const suggestedAuthorities = useMemo(() => {
    const valid = suggestions.filter((s) => isValidLegalReference(s.query));
    const seen = new Set<string>();
    const unique: LegalResearchSuggestion[] = [];

    for (const s of valid) {
      const canonical = canonicalizeAuthority(s.query);
      if (!seen.has(canonical.toLowerCase())) {
        seen.add(canonical.toLowerCase());
        unique.push({ ...s, query: canonical });
      }
    }
    return unique;
  }, [suggestions]);

  const visibleSuggestions = showAllSuggestions
    ? suggestedAuthorities
    : suggestedAuthorities.slice(0, 6);

  const executeSearch = useCallback(
    async (targetQuery: string) => {
      const q = targetQuery.trim();
      if (!q) return;

      setActiveView("search");
      setQuery(q);
      setLoading(true);
      setError(null);
      setResponse(null);
      try {
        const res = await searchLegalAuthorities(caseId, q, {
          limit: 10,
          ...(court ? { court } : {}),
          ...(fromDate ? { from_date: fromDate } : {}),
          ...(toDate ? { to_date: toDate } : {}),
          ...(act.trim() && section.trim() ? { act: act.trim(), section: section.trim() } : {}),
        });
        setResponse(res);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Legal research search failed.");
      } finally {
        setLoading(false);
      }
    },
    [caseId, court, fromDate, toDate, act, section]
  );

  // Auto-search if initialQuery provided
  useEffect(() => {
    if (initialQuery && initialQuery.trim()) {
      void executeSearch(initialQuery);
      if (onClearInitialQuery) {
        onClearInitialQuery();
      }
    }
  }, [initialQuery, executeSearch, onClearInitialQuery]);

  async function handleSearchSubmit(e?: React.FormEvent, directQuery?: string) {
    if (e) e.preventDefault();
    const targetQuery = (directQuery ?? query).trim();
    if (!targetQuery) return;
    await executeSearch(targetQuery);
  }

  async function openDocumentDetail(sourceId: string, title?: string, fallbackDoc?: unknown) {
    setDocLoading(true);
    setDocSearchQuery("");
    try {
      if (/^\d+$/.test(sourceId)) {
        const doc = await getIndianKanoonDocument(caseId, sourceId);
        setOpenedDoc(doc);
      } else {
        // India Code or custom statute object
        setOpenedDoc({
          provider: "india_code",
          source_id: sourceId,
          document: typeof fallbackDoc === "object" && fallbackDoc !== null ? (fallbackDoc as Record<string, unknown>) : { title: title || sourceId, doc: String(fallbackDoc || "") },
          metadata: {},
          url: `https://www.indiacode.nic.in`,
          notice: "Statutory provision text. Verify official gazette publications for recent amendments.",
        });
      }
    } catch {
      // If Kanoon API fails, fallback to preview
      if (fallbackDoc) {
        setOpenedDoc({
          provider: "indian_kanoon",
          source_id: sourceId,
          document: typeof fallbackDoc === "object" && fallbackDoc !== null ? (fallbackDoc as Record<string, unknown>) : { title: title || sourceId, doc: String(fallbackDoc) },
          metadata: {},
          url: `https://indiankanoon.org/doc/${sourceId}/`,
          notice: "Cached passage preview.",
        });
      } else {
        alert("Could not load authority text from provider.");
      }
    } finally {
      setDocLoading(false);
    }
  }

  async function toggleSaveReview(
    provider: string,
    sourceId: string,
    title: string,
    url?: string,
    forcedStatus?: "verified" | "needs_review" | "not_relevant"
  ) {
    const existing = authorityReviews.find((r) => r.source_id === sourceId);
    const newStatus = forcedStatus
      ? forcedStatus
      : existing?.status === "verified"
      ? "needs_review"
      : "verified";

    // Normalize URL to allowed legal domains if empty
    let validUrl = url || "";
    if (!validUrl || !validUrl.startsWith("http")) {
      if (provider === "india_code") {
        validUrl = "https://www.indiacode.nic.in";
      } else {
        validUrl = `https://indiankanoon.org/doc/${sourceId}/`;
      }
    }

    try {
      const updated = await saveAuthorityReview(caseId, {
        provider: provider === "india_code" ? "india_code" : "indian_kanoon",
        source_id: sourceId,
        title: title || sourceId,
        url: validUrl,
        status: newStatus,
        note: existing?.note || null,
      });
      setAuthorityReviews((prev) => [
        ...prev.filter((r) => r.source_id !== sourceId),
        updated,
      ]);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update authority review.");
    }
  }

  async function handleSaveNote(review: LegalAuthorityReview, noteText: string) {
    try {
      const updated = await saveAuthorityReview(caseId, {
        provider: review.provider,
        source_id: review.source_id,
        title: review.title,
        url: review.url,
        status: review.status,
        note: noteText.trim() || null,
      });
      setAuthorityReviews((prev) => [
        ...prev.filter((r) => r.source_id !== review.source_id),
        updated,
      ]);
      setEditingNoteId(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to save note.");
    }
  }

  async function generateResearchNote() {
    if (!query.trim() || selectedDocIds.length === 0) return;
    setNoteLoading(true);
    try {
      const answer = await createGroundedResearchAnswer(caseId, query.trim(), selectedDocIds);
      setResearchNote(answer);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Could not generate research note.");
    } finally {
      setNoteLoading(false);
    }
  }

  // Split results into statutes vs judgments
  const statutes = useMemo(
    () => (response?.results || []).filter((r) => r.provider === "india_code"),
    [response]
  );
  const judgments = useMemo(
    () => (response?.results || []).filter((r) => r.provider === "indian_kanoon" || r.provider !== "india_code"),
    [response]
  );

  const savedVerifiedCount = authorityReviews.filter((r) => r.status === "verified").length;
  const filteredSavedReviews = authorityReviews.filter((r) => {
    if (savedStatusFilter === "all") return true;
    return r.status === savedStatusFilter;
  });

  // Extract document text for reader modal
  const openedDocText = useMemo(() => {
    if (!openedDoc) return "";
    const doc = openedDoc.document;
    if (typeof doc === "string") return doc;
    if (doc && typeof doc === "object") {
      if ("doc" in doc && typeof doc.doc === "string") return doc.doc;
      if ("text" in doc && typeof doc.text === "string") return doc.text;
      if ("content" in doc) {
        return typeof doc.content === "string" ? doc.content : JSON.stringify(doc.content, null, 2);
      }
      return JSON.stringify(doc, null, 2);
    }
    return "";
  }, [openedDoc]);

  const openedDocFormatted = useMemo(() => {
    return formatLegalText(openedDocText);
  }, [openedDocText]);

  const openedDocMeta = useMemo(() => {
    if (!openedDoc || typeof openedDoc.document !== "object" || !openedDoc.document) return null;
    const doc = openedDoc.document as Record<string, unknown>;
    return {
      title: String(doc.title || openedDoc.source_id),
      court: String(doc.court || doc.docsource || openedDoc.metadata?.court || ""),
      date: String(doc.date || openedDoc.metadata?.date || ""),
      bench: String(doc.bench || doc.author || ""),
      citation: String(doc.citation || ""),
    };
  }, [openedDoc]);

  const isCurrentOpenedDocSaved = useMemo(() => {
    if (!openedDoc) return false;
    return authorityReviews.some(
      (r) => r.source_id === openedDoc.source_id && r.status === "verified"
    );
  }, [openedDoc, authorityReviews]);

  return (
    <PageShell>
      {/* 1. Page Header with Tab Switcher */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h1 className="font-serif text-2xl font-medium tracking-tight text-[var(--text)]">
              Legal research & authorities
            </h1>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              Search India Code statutes, Kanoon judicial precedents, and manage saved case authorities.
            </p>
          </div>

          {/* View Switcher Tabs */}
          <div className="flex items-center rounded-lg border border-[var(--border)] p-1 bg-[var(--surface)] self-start sm:self-auto shadow-sm">
            <button
              type="button"
              onClick={() => setActiveView("search")}
              className={`flex items-center gap-1.5 rounded-md px-3.5 py-1.5 text-xs font-medium transition ${
                activeView === "search"
                  ? "bg-[var(--primary)] text-white shadow-sm"
                  : "text-[var(--text-muted)] hover:text-[var(--text)]"
              }`}
            >
              <Search className="size-3.5" />
              <span>Search & Precedents</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveView("saved")}
              className={`flex items-center gap-1.5 rounded-md px-3.5 py-1.5 text-xs font-medium transition ${
                activeView === "saved"
                  ? "bg-[var(--primary)] text-white shadow-sm"
                  : "text-[var(--text-muted)] hover:text-[var(--text)]"
              }`}
            >
              <Bookmark className="size-3.5" />
              <span>Saved Authorities</span>
              {authorityReviews.length > 0 && (
                <span
                  className={`ml-1 rounded-full px-1.5 py-0.2 font-mono text-[10px] font-bold ${
                    activeView === "saved"
                      ? "bg-white/20 text-white"
                      : "bg-[var(--brass)] text-white"
                  }`}
                >
                  {authorityReviews.length}
                </span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* VIEW A: SAVED AUTHORITIES SECTION */}
      {activeView === "saved" && (
        <div className="space-y-4 pt-2">
          {/* Controls / Filter Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[var(--border)]">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-muted)] font-medium">Filter status:</span>
              <div className="flex items-center rounded-md border border-[var(--border)] p-0.5 bg-[var(--surface)] text-xs">
                {(["all", "verified", "needs_review", "not_relevant"] as const).map((st) => (
                  <button
                    key={st}
                    type="button"
                    onClick={() => setSavedStatusFilter(st)}
                    className={`rounded px-2.5 py-1 capitalize transition ${
                      savedStatusFilter === st
                        ? "bg-[var(--surface-2)] text-[var(--text)] font-semibold"
                        : "text-[var(--text-muted)]"
                    }`}
                  >
                    {st === "verified" ? "Verified Supporting" : st.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={() => setActiveView("search")}
              className="btn-primary text-xs flex items-center gap-1.5 self-start sm:self-auto"
            >
              <Search className="size-3.5" />
              <span>Search new authorities</span>
            </button>
          </div>

          {filteredSavedReviews.length === 0 ? (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-12 text-center text-xs text-[var(--text-muted)] space-y-3">
              <Bookmark className="mx-auto size-9 text-[var(--text-faint)]" />
              <p className="font-semibold text-sm text-[var(--text)]">No saved authorities found</p>
              <p className="max-w-md mx-auto leading-relaxed text-[11px]">
                Advocates can save statutes from India Code and precedents from Indian Kanoon directly into this section to reference offline without searching again.
              </p>
              <button
                type="button"
                onClick={() => setActiveView("search")}
                className="btn-secondary text-xs inline-flex items-center gap-1.5 mx-auto mt-2"
              >
                <Search className="size-3.5" />
                <span>Search precedents & statutes</span>
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredSavedReviews.map((item) => {
                const isEditingNote = editingNoteId === item.source_id;

                return (
                  <div
                    key={`${item.provider}-${item.source_id}`}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 space-y-3 shadow-sm hover:border-[var(--brass)]/60 transition"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                              item.provider === "india_code"
                                ? "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20"
                                : "bg-blue-500/10 text-blue-600 border border-blue-500/20"
                            }`}
                          >
                            {item.provider === "india_code" ? "Statute · India Code" : "Precedent · Kanoon"}
                          </span>

                          <span
                            className={`rounded px-2 py-0.5 text-[10px] font-semibold ${
                              item.status === "verified"
                                ? "bg-[var(--brass)]/15 text-[var(--brass)]"
                                : item.status === "not_relevant"
                                ? "bg-[var(--danger)]/10 text-[var(--danger)]"
                                : "bg-[var(--warning)]/15 text-[var(--warning)]"
                            }`}
                          >
                            {item.status === "verified"
                              ? "Supporting Authority"
                              : item.status === "not_relevant"
                              ? "Distinguished / Opposing"
                              : "Under Review"}
                          </span>

                          {item.reviewed_at && (
                            <span className="text-[11px] text-[var(--text-faint)] flex items-center gap-1">
                              <Clock className="size-3" />
                              <span>Saved {formatDate(item.reviewed_at)}</span>
                            </span>
                          )}
                        </div>

                        <h3 className="font-serif text-base font-semibold text-[var(--text)] leading-snug">
                          {item.title}
                        </h3>
                      </div>

                      {/* Right Action Buttons */}
                      <div className="flex items-center gap-2 shrink-0 self-end sm:self-start">
                        <button
                          type="button"
                          onClick={() => openDocumentDetail(item.source_id, item.title)}
                          className="btn-secondary h-8 px-3 text-xs flex items-center gap-1.5 font-medium"
                        >
                          <BookOpen className="size-3.5 text-[var(--brass)]" />
                          <span>Read full text</span>
                        </button>

                        {item.url && (
                          <a
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)] transition"
                            title="Open original website source"
                          >
                            <ExternalLink className="size-4" />
                          </a>
                        )}

                        <button
                          type="button"
                          onClick={() =>
                            toggleSaveReview(item.provider, item.source_id, item.title, item.url, "not_relevant")
                          }
                          className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--danger)] hover:bg-[var(--danger)]/10 transition"
                          title="Remove from saved authorities"
                        >
                          <Trash2 className="size-4" />
                        </button>
                      </div>
                    </div>

                    {/* Advocate Notes & Strategy Section */}
                    <div className="rounded-md bg-[var(--surface-2)] p-3 text-xs space-y-2 border border-[var(--border)]">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-[var(--text)] flex items-center gap-1.5 text-[11px]">
                          <Edit3 className="size-3 text-[var(--brass)]" />
                          <span>Advocate Strategy & Applicability Note:</span>
                        </span>

                        {!isEditingNote && (
                          <button
                            type="button"
                            onClick={() => {
                              setEditingNoteId(item.source_id);
                              setNoteDraft(item.note || "");
                            }}
                            className="text-[11px] text-[var(--primary)] font-medium hover:underline"
                          >
                            {item.note ? "Edit note" : "+ Add note"}
                          </button>
                        )}
                      </div>

                      {isEditingNote ? (
                        <div className="space-y-2 mt-1">
                          <textarea
                            value={noteDraft}
                            onChange={(e) => setNoteDraft(e.target.value)}
                            placeholder="e.g. Citing this Supreme Court ruling for paragraph 4 defense regarding mandatory show-cause notice..."
                            rows={3}
                            className="input-field w-full text-xs font-serif leading-relaxed"
                            autoFocus
                          />
                          <div className="flex items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => setEditingNoteId(null)}
                              className="btn-secondary h-7 px-2.5 text-xs"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              onClick={() => handleSaveNote(item, noteDraft)}
                              className="btn-primary h-7 px-3 text-xs"
                            >
                              Save note
                            </button>
                          </div>
                        </div>
                      ) : (
                        <p className="font-serif text-[13px] leading-relaxed text-[var(--text)] italic">
                          {item.note || "No specific advocate notes recorded yet. Click '+ Add note' to record case application points."}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* VIEW B: SEARCH & SUGGESTIONS SECTION */}
      {activeView === "search" && (
        <div className="space-y-4 pt-2">
          {/* Search Row: 40px Input + Source Control + Search Button */}
          <div className="space-y-2">
            <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row items-stretch gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[var(--text-faint)] pointer-events-none" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search sections, acts, doctrines, or case citations (e.g. Evidence Act Sec 113, mandatory notice)..."
                  className="input-field h-10 w-full pl-10 text-sm"
                />
              </div>

              <div className="flex items-center gap-2">
                {/* Source Segmented Control */}
                <div className="flex items-center rounded-md border border-[var(--border)] p-0.5 h-10 bg-[var(--surface)]">
                  <button
                    type="button"
                    onClick={() => setSourceFilter("all")}
                    className={`rounded px-3 py-1.5 text-xs transition ${
                      sourceFilter === "all"
                        ? "bg-[var(--surface-2)] text-[var(--text)] font-semibold"
                        : "text-[var(--text-muted)]"
                    }`}
                  >
                    All
                  </button>
                  <button
                    type="button"
                    onClick={() => setSourceFilter("india_code")}
                    className={`rounded px-3 py-1.5 text-xs transition ${
                      sourceFilter === "india_code"
                        ? "bg-[var(--surface-2)] text-[var(--text)] font-semibold"
                        : "text-[var(--text-muted)]"
                    }`}
                  >
                    India Code
                  </button>
                  <button
                    type="button"
                    onClick={() => setSourceFilter("indian_kanoon")}
                    className={`rounded px-3 py-1.5 text-xs transition ${
                      sourceFilter === "indian_kanoon"
                        ? "bg-[var(--surface-2)] text-[var(--text)] font-semibold"
                        : "text-[var(--text-muted)]"
                    }`}
                  >
                    Indian Kanoon
                  </button>
                </div>

                <button
                  type="submit"
                  disabled={loading || !query.trim()}
                  className="btn-primary h-10 px-5 text-sm font-medium shrink-0"
                >
                  {loading ? "Searching…" : "Search"}
                </button>
              </div>
            </form>

            {/* Filters Toggle Button */}
            <div>
              <button
                type="button"
                onClick={() => setFiltersOpen(!filtersOpen)}
                className="text-xs text-[var(--text-muted)] hover:text-[var(--text)] flex items-center gap-1 font-medium"
              >
                <span>Advanced search filters</span>
                {filtersOpen ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
              </button>

              {/* Expanded Filters Grid */}
              {filtersOpen && (
                <div className="mt-2 grid grid-cols-2 sm:grid-cols-5 gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
                  <div>
                    <label className="block text-[11px] font-medium text-[var(--text-muted)]">Court</label>
                    <input
                      type="text"
                      value={court}
                      onChange={(e) => setCourt(e.target.value)}
                      placeholder="e.g. Supreme Court"
                      className="input-field mt-1 h-9 w-full text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-[var(--text-muted)]">Act / Statute</label>
                    <input
                      type="text"
                      value={act}
                      onChange={(e) => setAct(e.target.value)}
                      placeholder="e.g. Evidence Act"
                      className="input-field mt-1 h-9 w-full text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-[var(--text-muted)]">Section</label>
                    <input
                      type="text"
                      value={section}
                      onChange={(e) => setSection(e.target.value)}
                      placeholder="e.g. 113"
                      className="input-field mt-1 h-9 w-full text-xs font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-[var(--text-muted)]">From Date</label>
                    <input
                      type="date"
                      value={fromDate}
                      onChange={(e) => setFromDate(e.target.value)}
                      className="input-field mt-1 h-9 w-full text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-[var(--text-muted)]">To Date</label>
                    <input
                      type="date"
                      value={toDate}
                      onChange={(e) => setToDate(e.target.value)}
                      className="input-field mt-1 h-9 w-full text-xs"
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {error && <InlineAlert type="error" message={error} />}

          {/* Suggested Searches From Case File */}
          {suggestedAuthorities.length > 0 && !response && (
            <div className="space-y-2 pt-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-[var(--text)]">
                  Extracted citations & suggested searches from this case file:
                </span>
                <span className="text-[11px] text-[var(--text-muted)] font-mono">
                  {suggestedAuthorities.length} candidate(s)
                </span>
              </div>

              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
                {visibleSuggestions.map((item, idx) => (
                  <div
                    key={idx}
                    onClick={() => {
                      void executeSearch(item.query);
                    }}
                    className="flex items-center justify-between p-3.5 text-xs hover:bg-[var(--surface-2)] transition cursor-pointer group"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Scale className="size-4 text-[var(--brass)] shrink-0 group-hover:scale-110 transition" />
                      <div>
                        <span className="font-medium text-[13px] text-[var(--text)] group-hover:text-[var(--primary)] transition block">
                          {item.query}
                        </span>
                        <span className="text-[11px] text-[var(--text-muted)]">
                          from {item.document} · {item.locator}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        void executeSearch(item.query);
                      }}
                      className="btn-primary h-7 px-3 text-xs shrink-0 flex items-center gap-1 font-medium"
                    >
                      <Search className="size-3" />
                      <span>Search</span>
                    </button>
                  </div>
                ))}
                {suggestedAuthorities.length > 6 && (
                  <div className="p-2.5 text-center">
                    <button
                      type="button"
                      onClick={() => setShowAllSuggestions(!showAllSuggestions)}
                      className="text-xs text-[var(--primary)] font-medium hover:underline"
                    >
                      {showAllSuggestions ? "Show fewer" : `Show all (${suggestedAuthorities.length})`}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Results Display */}
          {response && (
            <PageBody className="space-y-6">
              <div className="flex items-center justify-between pb-2 border-b border-[var(--border)]">
                <button
                  type="button"
                  onClick={() => {
                    setResponse(null);
                    setQuery("");
                  }}
                  className="btn-secondary text-xs flex items-center gap-1.5"
                >
                  <ArrowLeft className="size-3.5" />
                  <span>← Back to suggested case laws</span>
                </button>
                <span className="text-xs text-[var(--text-muted)]">
                  Found {response.results?.length || 0} authorit{response.results?.length === 1 ? "y" : "ies"} for &ldquo;{response.query}&rdquo;
                </span>
              </div>

              {/* Statutes (India Code) */}
              {(sourceFilter === "all" || sourceFilter === "india_code") && statutes.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-[var(--text)] flex items-center gap-2">
                      <span>Statutes & Provisions (India Code)</span>
                      <span className="rounded bg-emerald-500/10 text-emerald-600 px-2 py-0.5 text-[10px] font-bold">
                        {statutes.length}
                      </span>
                    </h3>
                  </div>

                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
                    {statutes.map((res, idx) => {
                      const sourceId = res.source_id || res.url || res.title;
                      const isSaved = authorityReviews.some(
                        (r) => r.source_id === sourceId && r.status === "verified"
                      );

                      return (
                        <div key={idx} className="p-4 space-y-2 text-xs hover:bg-[var(--surface-2)]/30 transition">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <span className="font-semibold text-sm text-[var(--text)] block">
                                {res.title}
                              </span>
                              {res.court && (
                                <span className="text-[11px] text-[var(--text-muted)] mt-0.5 block">
                                  {res.court}
                                </span>
                              )}
                            </div>

                            <div className="flex items-center gap-2 shrink-0">
                              <button
                                type="button"
                                onClick={() => openDocumentDetail(sourceId, res.title, res.snippet)}
                                className="btn-secondary h-7 px-2.5 text-xs flex items-center gap-1 font-medium"
                              >
                                <BookOpen className="size-3" />
                                <span>Read text</span>
                              </button>

                              <button
                                type="button"
                                onClick={() => toggleSaveReview("india_code", sourceId, res.title, res.url)}
                                className={`h-7 px-2.5 rounded-md text-xs font-medium flex items-center gap-1 transition ${
                                  isSaved
                                    ? "bg-[var(--brass)] text-white"
                                    : "border border-[var(--border-strong)] text-[var(--text)] hover:bg-[var(--surface-2)]"
                                }`}
                                title={isSaved ? "Saved to Case Authorities" : "Save to Case Authorities"}
                              >
                                <Bookmark className="size-3.5" />
                                <span>{isSaved ? "Saved ✓" : "Save to Case"}</span>
                              </button>
                            </div>
                          </div>

                          {res.snippet && (
                            <p className="text-[var(--text-muted)] leading-relaxed font-serif text-[13px] line-clamp-3 pl-1 border-l-2 border-[var(--brass)]/50">
                              {res.snippet}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Judgments (Indian Kanoon) */}
              {(sourceFilter === "all" || sourceFilter === "indian_kanoon") && judgments.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-[var(--text)] flex items-center gap-2">
                      <span>Precedents & Judgments (Indian Kanoon)</span>
                      <span className="rounded bg-blue-500/10 text-blue-600 px-2 py-0.5 text-[10px] font-bold">
                        {judgments.length}
                      </span>
                    </h3>

                    {selectedDocIds.length > 0 && (
                      <button
                        type="button"
                        disabled={noteLoading}
                        onClick={generateResearchNote}
                        className="btn-primary text-xs h-8 flex items-center gap-1.5"
                      >
                        <Sparkles className="size-3.5" />
                        <span>{noteLoading ? "Synthesizing with Gemini…" : `Synthesize Note (${selectedDocIds.length})`}</span>
                      </button>
                    )}
                  </div>

                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
                    {judgments.map((res, idx) => {
                      const docId = res.source_id || res.url;
                      const isSelected = docId ? selectedDocIds.includes(docId) : false;
                      const isSaved = docId
                        ? authorityReviews.some((r) => r.source_id === docId && r.status === "verified")
                        : false;

                      return (
                        <div key={idx} className="p-4 space-y-2.5 text-xs hover:bg-[var(--surface-2)]/40 transition">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start gap-2.5 min-w-0">
                              {docId && (
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={(e) => {
                                    if (e.target.checked) setSelectedDocIds((prev) => [...prev, docId]);
                                    else setSelectedDocIds((prev) => prev.filter((id) => id !== docId));
                                  }}
                                  className="mt-1 rounded border-[var(--border-strong)] text-[var(--primary)] size-4 cursor-pointer"
                                  title="Select to synthesize Gemini research note"
                                />
                              )}
                              <div>
                                <span className="font-semibold text-sm text-[var(--text)] block leading-snug">
                                  {res.title}
                                </span>
                                <span className="text-[11px] text-[var(--text-muted)] mt-0.5 block">
                                  {res.court || "High Court / Supreme Court"} · {res.date || "Reported judgment"}
                                </span>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 shrink-0">
                              {res.source_id && (
                                <button
                                  type="button"
                                  onClick={() => openDocumentDetail(res.source_id!, res.title, res.snippet)}
                                  className="btn-secondary h-7 px-2.5 text-xs flex items-center gap-1 font-medium"
                                >
                                  <BookOpen className="size-3" />
                                  <span>Read full judgment</span>
                                </button>
                              )}

                              <button
                                type="button"
                                onClick={() =>
                                  toggleSaveReview("indian_kanoon", docId || res.title, res.title, res.url)
                                }
                                className={`h-7 px-2.5 rounded-md text-xs font-medium flex items-center gap-1 transition ${
                                  isSaved
                                    ? "bg-[var(--brass)] text-white"
                                    : "border border-[var(--border-strong)] text-[var(--text)] hover:bg-[var(--surface-2)]"
                                }`}
                                title={isSaved ? "Saved to Case Authorities" : "Save to Case Authorities"}
                              >
                                <Bookmark className="size-3.5" />
                                <span>{isSaved ? "Saved ✓" : "Save to Case"}</span>
                              </button>
                            </div>
                          </div>

                          {res.snippet && (
                            <p className="text-[var(--text-muted)] leading-relaxed font-serif text-[13px] line-clamp-3 pl-6">
                              “{res.snippet}”
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Research Note Output */}
              {researchNote && (
                <div className="rounded-lg border border-[var(--brass)] bg-[var(--surface)] p-6 space-y-3 shadow-md">
                  <div className="flex items-center justify-between">
                    <h3 className="font-serif text-base font-medium text-[var(--text)] flex items-center gap-2">
                      <Sparkles className="size-4 text-[var(--brass)]" />
                      <span>Gemini Grounded Research Note</span>
                    </h3>
                    <span className="text-[11px] text-[var(--text-muted)] font-mono">
                      Grounded in {researchNote.sources_used?.length || 0} authority/authorities
                    </span>
                  </div>
                  <div className="font-serif text-sm leading-relaxed text-[var(--text)] whitespace-pre-wrap pl-2 border-l-2 border-[var(--brass)]">
                    {researchNote.answer}
                  </div>
                </div>
              )}
            </PageBody>
          )}
        </div>
      )}

      {/* Footnote */}
      <PageFootnote>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-emerald-500" />
            <span>India Code (Statutes)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-blue-500" />
            <span>Indian Kanoon (Judgments)</span>
          </div>
        </div>
        <span className="text-[11px] text-[var(--text-faint)]">
          Candidate legal references. Verify current precedent and statutory amendments before citing.
        </span>
      </PageFootnote>

      {/* RICH LEGAL DOCUMENT READER MODAL (760px Typography-optimized reader) */}
      {openedDoc && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-[1px]">
          <div className="flex h-full w-full max-w-[760px] flex-col border-l border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-drawer)]">
            {/* Header */}
            <div className="border-b border-[var(--border)] px-6 py-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                        openedDoc.provider === "india_code"
                          ? "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20"
                          : "bg-blue-500/10 text-blue-600 border border-blue-500/20"
                      }`}
                    >
                      {openedDoc.provider === "india_code" ? "India Code Statute" : "Indian Kanoon Judgment"}
                    </span>
                    <span className="text-[11px] font-mono text-[var(--text-muted)]">
                      ID: {openedDoc.source_id}
                    </span>
                  </div>

                  <h2 className="font-serif text-lg font-bold text-[var(--text)] leading-snug">
                    {openedDocMeta?.title || openedDoc.source_id}
                  </h2>
                </div>

                <button
                  type="button"
                  onClick={() => setOpenedDoc(null)}
                  className="p-1 rounded-md text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)]"
                >
                  <X className="size-5" />
                </button>
              </div>

              {/* Metadata Sub-row */}
              {openedDocMeta && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--text-muted)] font-sans">
                  {openedDocMeta.court && (
                    <span>
                      <strong className="text-[var(--text)]">Court:</strong> {openedDocMeta.court}
                    </span>
                  )}
                  {openedDocMeta.date && (
                    <span>
                      <strong className="text-[var(--text)]">Date:</strong> {openedDocMeta.date}
                    </span>
                  )}
                  {openedDocMeta.bench && (
                    <span>
                      <strong className="text-[var(--text)]">Bench:</strong> {openedDocMeta.bench}
                    </span>
                  )}
                </div>
              )}

              {/* Reader Action Bar: Search In Document + Save to Case + Copy Text */}
              <div className="flex items-center justify-between gap-2 pt-1">
                <div className="relative flex-1 max-w-xs">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-[var(--text-faint)]" />
                  <input
                    type="text"
                    value={docSearchQuery}
                    onChange={(e) => setDocSearchQuery(e.target.value)}
                    placeholder="Find in document…"
                    className="input-field h-8 w-full pl-8 text-xs"
                  />
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(openedDocText);
                        setCopiedDoc(true);
                        setTimeout(() => setCopiedDoc(false), 2000);
                      } catch {
                        // ignore clipboard error
                      }
                    }}
                    className="btn-secondary h-8 px-2.5 text-xs flex items-center gap-1"
                    title="Copy full text to clipboard"
                  >
                    {copiedDoc ? <Check className="size-3 text-[var(--success)]" /> : <Copy className="size-3" />}
                    <span>{copiedDoc ? "Copied" : "Copy"}</span>
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      toggleSaveReview(
                        openedDoc.provider,
                        openedDoc.source_id,
                        openedDocMeta?.title || openedDoc.source_id,
                        openedDoc.url
                      )
                    }
                    className={`btn-primary h-8 px-3 text-xs flex items-center gap-1.5 font-medium ${
                      isCurrentOpenedDocSaved ? "bg-[var(--brass)] border-[var(--brass)] text-white" : ""
                    }`}
                  >
                    <Bookmark className="size-3.5" />
                    <span>{isCurrentOpenedDocSaved ? "Saved in Case ✓" : "Save to Case"}</span>
                  </button>

                  {openedDoc.url && (
                    <a
                      href={openedDoc.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text)]"
                      title="Open in provider site"
                    >
                      <ExternalLink className="size-4" />
                    </a>
                  )}
                </div>
              </div>
            </div>

            {/* Document Body (Formatted Paragraphs, Section Breaks, Clause Indentations) */}
            <div className="flex-1 overflow-y-auto p-8 font-serif text-[15px] leading-[1.8] text-[var(--text)] space-y-4">
              {docLoading ? (
                <div className="py-20 text-center text-xs text-[var(--text-muted)] space-y-2">
                  <Scale className="size-6 animate-pulse mx-auto text-[var(--brass)]" />
                  <p>Loading document text from provider…</p>
                </div>
              ) : openedDocFormatted.length === 0 ? (
                <div className="py-20 text-center text-xs text-[var(--text-muted)]">
                  No readable body text available for this authority.
                </div>
              ) : (
                openedDocFormatted.map((item, idx) => {
                  const queryLower = docSearchQuery.trim().toLowerCase();
                  const matchesSearch = queryLower && item.text.toLowerCase().includes(queryLower);

                  if (item.type === "heading") {
                    return (
                      <h3
                        key={idx}
                        className={`font-serif text-base font-bold text-[var(--text)] pt-4 pb-1 border-b border-[var(--border)] ${
                          matchesSearch ? "bg-yellow-200/30 dark:bg-yellow-500/20 px-1 rounded" : ""
                        }`}
                      >
                        {item.text}
                      </h3>
                    );
                  }

                  if (item.type === "clause") {
                    return (
                      <div
                        key={idx}
                        className={`flex items-start gap-3 pl-4 py-1.5 ${
                          matchesSearch ? "bg-yellow-200/30 dark:bg-yellow-500/20 px-2 rounded" : ""
                        }`}
                      >
                        <span className="font-mono font-bold text-xs text-[var(--brass)] bg-[var(--surface-2)] px-2 py-0.5 rounded border border-[var(--border)] shrink-0 mt-0.5">
                          {item.label}
                        </span>
                        <div className="flex-1 text-[var(--text)] leading-relaxed">
                          {item.text}
                        </div>
                      </div>
                    );
                  }

                  if (item.type === "proviso") {
                    return (
                      <blockquote
                        key={idx}
                        className={`border-l-4 border-[var(--brass)] bg-[var(--surface-2)]/60 p-3.5 rounded-r-md italic text-[14px] text-[var(--text)] leading-relaxed my-2 ${
                          matchesSearch ? "ring-2 ring-yellow-400/50" : ""
                        }`}
                      >
                        {item.text}
                      </blockquote>
                    );
                  }

                  return (
                    <p
                      key={idx}
                      className={`text-[var(--text)] leading-relaxed ${
                        matchesSearch ? "bg-yellow-200/30 dark:bg-yellow-500/20 px-1 rounded" : ""
                      }`}
                    >
                      {item.text}
                    </p>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </PageShell>
  );
}
