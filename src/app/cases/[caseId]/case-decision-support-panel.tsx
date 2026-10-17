"use client";

import { useEffect, useState } from "react";
import {
  Scale,
  ChevronDown,
  ChevronUp,
  Download,
  Bookmark,
  Pin,
  CheckCircle,
  MoreHorizontal,
  X,
  FileText,
} from "lucide-react";
import {
  CaseAnalysisResult,
  CaseRecord,
  CaseSummaryResult,
  LegalAuthorityReview,
  LegalResearchSuggestion,
  getLatestCaseAnalysis,
  getLatestCaseSummary,
  getLegalResearchSuggestions,
  listAuthorityReviews,
} from "@/lib/api";
import { PageShell, PageHeader, PageBody } from "@/components/domain/page-shell";
import { StatusDot } from "@/components/domain/status-dot";
import { CitationChip } from "@/components/domain/citation-chip";
import { EmptyState } from "@/components/domain/empty-state";
import { canonicalizeAuthority, isValidLegalReference } from "@/lib/formatters";

type SectionItem = {
  id: string;
  statement: string;
  status: string;
  documentName?: string;
  locator?: string;
  quote?: string;
  type?: string;
};

export function CaseDecisionSupportPanel({
  caseId,
  caseFile,
}: {
  caseId: string;
  caseFile: CaseRecord;
}) {
  const [analysis, setAnalysis] = useState<CaseAnalysisResult | null>(null);
  const [summary, setSummary] = useState<CaseSummaryResult | null>(null);
  const [leads, setLeads] = useState<LegalResearchSuggestion[]>([]);
  const [authorities, setAuthorities] = useState<LegalAuthorityReview[]>([]);
  const [loading, setLoading] = useState(true);

  // Focus / Pinned List state & Drawer
  const [pinnedItems, setPinnedItems] = useState<SectionItem[]>([]);
  const [focusDrawerOpen, setFocusDrawerOpen] = useState(false);

  // Section collapse states
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    evidence: true,
    issues: true,
    contradictions: true,
    claims: true,
    leads: true,
    questions: false,
  });

  const [showAllMap, setShowAllMap] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let active = true;
    void Promise.allSettled([
      getLatestCaseAnalysis(caseId),
      getLatestCaseSummary(caseId),
      getLegalResearchSuggestions(caseId),
      listAuthorityReviews(caseId),
    ]).then((results) => {
      if (!active) return;
      if (results[0].status === "fulfilled") setAnalysis(results[0].value);
      if (results[1].status === "fulfilled") setSummary(results[1].value);
      if (results[2].status === "fulfilled") setLeads(results[2].value.suggestions || []);
      if (results[3].status === "fulfilled") setAuthorities(results[3].value);
      setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [caseId]);

  function toggleSection(key: string) {
    setExpandedSections((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function togglePin(item: SectionItem) {
    setPinnedItems((prev) => {
      const exists = prev.some((p) => p.id === item.id);
      if (exists) return prev.filter((p) => p.id !== item.id);
      return [...prev, item];
    });
  }

  // 1. Evidence items
  const evidenceItems: SectionItem[] = (analysis?.facts || []).map((f, i) => ({
    id: `ev-${i}`,
    statement: f.statement,
    status: "Needs advocate review",
    documentName: f.source_filename,
    locator: f.source_locator,
    quote: f.statement,
  }));

  // 2. Issue items
  const issues = (analysis?.extraction_items || []).filter((item) => {
    const classification = `${item.category} ${item.legal_role || ""}`.toLowerCase();
    return /\b(issue|issues|question for determination|point for determination)\b/.test(classification);
  });
  const issueItems: SectionItem[] = issues.map((iss, i) => ({
    id: `iss-${i}`,
    statement: iss.text,
    status: "Needs review",
    documentName: iss.source_filename,
    locator: iss.source_locator,
    quote: iss.evidence_quote || iss.text,
  }));

  // 3. Contradictions
  const contradictionItems: SectionItem[] = (analysis?.findings || []).map((c, i) => ({
    id: `contra-${i}`,
    statement: c.explanation || `Variance between ${c.left_fact?.source_filename} and ${c.right_fact?.source_filename}`,
    status: "Needs review",
    documentName: c.left_fact?.source_filename,
    locator: c.left_fact?.source_locator,
    quote: c.left_fact?.statement,
  }));

  // 4. Claims to review
  const claimItems: SectionItem[] = (analysis?.claim_reviews || []).map((cl, i) => ({
    id: `claim-${i}`,
    statement: `${cl.claim_text}: ${cl.explanation}`,
    status: "AI assessment · review required",
  }));

  // 5. Research leads
  const leadItems: SectionItem[] = leads
    .filter((l) => isValidLegalReference(l.query))
    .map((l, i) => ({
      id: `lead-${i}`,
      statement: canonicalizeAuthority(l.query),
      status: "Not started",
      documentName: l.document,
      locator: l.locator,
      quote: l.evidence_quote,
    }));

  // 6. Open questions / next steps
  const questionItems: SectionItem[] = [];

  const sections = [
    { key: "evidence", title: "Extracted candidate facts", items: evidenceItems },
    { key: "issues", title: "Issues for determination", items: issueItems },
    { key: "contradictions", title: "Possible contradictions", items: contradictionItems },
    { key: "claims", title: "Advocate claims to review", items: claimItems },
    { key: "leads", title: "Research leads & legal authorities", items: leadItems },
    { key: "questions", title: "Open questions & investigation points", items: questionItems },
  ];

  function handleExportReport() {
    window.print();
  }

  return (
    <PageShell>
      {/* 1. Page Header */}
      <PageHeader
        title="Decision support"
        description="Structured overview of evidence, issues, and pending verification."
        actions={
          <div className="flex items-center gap-2">
            {pinnedItems.length > 0 && (
              <button
                type="button"
                onClick={() => setFocusDrawerOpen(true)}
                className="btn-secondary text-xs flex items-center gap-1.5"
              >
                <Pin className="size-3.5" />
                <span>Focus list ({pinnedItems.length})</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleExportReport}
              className="btn-ghost text-xs flex items-center gap-1.5"
            >
              <Download className="size-3.5" />
              <span>Export report</span>
            </button>
          </div>
        }
      />

      {/* 2. Six Collapsible Sections */}
      <PageBody className="space-y-4">
        {sections.map(({ key, title, items }) => {
          const isExpanded = expandedSections[key];
          const isShowAll = showAllMap[key];
          const visibleItems = isShowAll ? items : items.slice(0, 3);

          return (
            <div key={key} className="rounded-lg border border-[var(--border)] bg-[var(--surface)]">
              {/* Section Header */}
              <button
                type="button"
                onClick={() => toggleSection(key)}
                className="flex w-full items-center justify-between p-4 text-left hover:bg-[var(--surface-2)] transition"
              >
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-[var(--text)]">{title}</h3>
                  <span className="rounded bg-[var(--surface-2)] px-2 py-0.5 font-mono text-[11px] text-[var(--text-muted)]">
                    {items.length}
                  </span>
                </div>
                {isExpanded ? <ChevronUp className="size-4 text-[var(--text-muted)]" /> : <ChevronDown className="size-4 text-[var(--text-muted)]" />}
              </button>

              {/* Section Body */}
              {isExpanded && (
                <div className="border-t border-[var(--border)] divide-y divide-[var(--border)]">
                  {items.length === 0 ? (
                    <div className="p-4 text-center text-xs text-[var(--text-muted)]">
                      No items recorded in this section.
                    </div>
                  ) : (
                    visibleItems.map((item) => {
                      const isPinned = pinnedItems.some((p) => p.id === item.id);

                      return (
                        <div key={item.id} className="flex items-start justify-between gap-3 p-3.5 text-xs hover:bg-[var(--surface-2)]/40 transition">
                          <div className="flex items-start gap-2.5 min-w-0">
                            <StatusDot status={item.status} />
                            <div className="space-y-1">
                              <p className="font-medium text-[var(--text)] leading-relaxed">{item.statement}</p>
                              {item.documentName && (
                                <CitationChip
                                  caseId={caseId}
                                  filename={item.documentName}
                                  locator={item.locator || ""}
                                  quote={item.quote || item.statement}
                                />
                              )}
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={() => togglePin(item)}
                            className={`p-1 transition rounded ${
                              isPinned ? "text-[var(--primary)] bg-[var(--primary-tint)]" : "text-[var(--text-faint)] hover:text-[var(--text)]"
                            }`}
                            title={isPinned ? "Remove from focus list" : "Pin to focus list"}
                          >
                            <Pin className="size-3.5" />
                          </button>
                        </div>
                      );
                    })
                  )}

                  {items.length > 3 && (
                    <div className="p-2 text-center bg-[var(--surface-2)]/30">
                      <button
                        type="button"
                        onClick={() => setShowAllMap((prev) => ({ ...prev, [key]: !prev[key] }))}
                        className="text-xs font-medium text-[var(--primary)] hover:underline"
                      >
                        {isShowAll ? "Show fewer" : `Show all (${items.length})`}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </PageBody>

      {/* Focus List Drawer (Right Side) */}
      {focusDrawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/40">
          <div className="flex h-full w-full max-w-[420px] flex-col border-l border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-drawer)]">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
              <h2 className="font-serif text-base font-medium text-[var(--text)]">
                Focus List ({pinnedItems.length})
              </h2>
              <button
                type="button"
                onClick={() => setFocusDrawerOpen(false)}
                className="text-[var(--text-muted)] hover:text-[var(--text)] p-1"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4 divide-y divide-[var(--border)]">
              {pinnedItems.map((p) => (
                <div key={p.id} className="py-3 text-xs space-y-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-medium text-[var(--text)]">{p.statement}</p>
                    <button
                      type="button"
                      onClick={() => togglePin(p)}
                      className="text-[var(--text-faint)] hover:text-[var(--danger)]"
                      title="Unpin"
                    >
                      <X className="size-3.5" />
                    </button>
                  </div>
                  {p.documentName && (
                    <CitationChip
                      caseId={caseId}
                      filename={p.documentName}
                      locator={p.locator || ""}
                      quote={p.quote || ""}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </PageShell>
  );
}
