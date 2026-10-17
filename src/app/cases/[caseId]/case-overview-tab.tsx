"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Scale,
  ChevronDown,
  ChevronUp,
  Search,
  CheckCircle2,
  AlertTriangle,
  Info,
  RefreshCw,
  ArrowRight,
  FileText,
} from "lucide-react";
import {
  CaseDocument,
  CaseRecord,
  CaseAnalysisAvailability,
  getLegalResearchSuggestions,
  searchLegalAuthorities,
  LegalResearchSuggestion,
} from "@/lib/api";
import { WorkspaceModuleId } from "@/app/workspace-shell";
import { PageShell, PageHeader, PageBody } from "@/components/domain/page-shell";
import { StatusDot } from "@/components/domain/status-dot";
import { canonicalizeAuthority, isValidLegalReference, formatDate } from "@/lib/formatters";

export function CaseOverviewTab({
  caseFile,
  documents,
  availability,
  onNavigate,
}: {
  caseFile: CaseRecord;
  documents: CaseDocument[];
  availability: CaseAnalysisAvailability | null;
  onNavigate: (module: WorkspaceModuleId, query?: string) => void;
}) {
  // Detect unreadable or critically low OCR documents
  const unreadableDocs = documents.filter((doc) => {
    if (doc.processing_status === "failed") return true;
    if (["processed", "needs_review"].includes(doc.processing_status) && doc.text_unit_count === 0) return true;
    if (doc.unreadable_location_count > 0 && doc.readable_location_count === 0) return true;
    if (doc.pages_without_text_count > 0 && doc.pages_with_text_count === 0) return true;
    return false;
  });

  const isAnalysisBlocked = unreadableDocs.length > 0;
  const totalDocs = documents.length;
  const reviewDocs = documents.filter(
    (d) => d.processing_status === "needs_review" && !unreadableDocs.some((u) => u.id === d.id)
  ).length;
  const failedDocs = unreadableDocs.length;
  const totalUnits = documents.reduce((acc, d) => acc + (d.text_unit_count || 0), 0);

  const hasDocs = totalDocs > 0;
  const hasExtracted = documents.length > 0 && !isAnalysisBlocked && documents.some((d) => d.text_unit_count > 0);
  const isAnalysisRunning = ["processing", "queued"].includes(caseFile.analysis_status || "");
  const hasAnalysis = caseFile.analysis_status === "completed" || (caseFile.analysis_status || "").includes("re-analysis");

  const progressSteps: { label: string; id: WorkspaceModuleId; status: "done" | "current" | "pending" }[] = [
    { label: "Upload", id: "documents", status: hasDocs ? "done" : "current" },
    { label: "Extract", id: "documents", status: hasExtracted ? "done" : hasDocs ? "current" : "pending" },
    { label: "Analyse", id: "analysis", status: hasAnalysis ? "done" : (hasExtracted || isAnalysisRunning) ? "current" : "pending" },
    { label: "Graph", id: "graph", status: hasAnalysis ? "done" : "pending" },
    { label: "Research", id: "research", status: hasAnalysis ? "done" : "pending" },
  ];

  // Laws and Judgments state
  const [rawSuggestions, setRawSuggestions] = useState<LegalResearchSuggestion[]>([]);
  const [loadingLaws, setLoadingLaws] = useState(false);
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [indiaCodeTexts, setIndiaCodeTexts] = useState<Record<number, { loading: boolean; text?: string; error?: string }>>({});
  const [showAllAuthorities, setShowAllAuthorities] = useState(false);

  useEffect(() => {
    let active = true;
    setLoadingLaws(true);
    getLegalResearchSuggestions(caseFile.id)
      .then((res) => {
        if (active) setRawSuggestions(res.suggestions || []);
      })
      .catch(() => {
        if (active) setRawSuggestions([]);
      })
      .finally(() => {
        if (active) setLoadingLaws(false);
      });
    return () => {
      active = false;
    };
  }, [caseFile.id]);

  // Clean, canonicalise and deduplicate genuine legal authorities
  const legalAuthorities = useMemo(() => {
    const seen = new Set<string>();
    const results: LegalResearchSuggestion[] = [];

    for (const item of rawSuggestions) {
      if (!isValidLegalReference(item.query)) continue;
      const canonical = canonicalizeAuthority(item.query);
      const key = canonical.toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        results.push({
          ...item,
          query: canonical,
        });
      }
    }
    return results;
  }, [rawSuggestions]);

  const visibleAuthorities = showAllAuthorities ? legalAuthorities : legalAuthorities.slice(0, 6);

  async function toggleLawDetails(index: number, law: LegalResearchSuggestion) {
    if (expandedIndex === index) {
      setExpandedIndex(null);
      return;
    }

    setExpandedIndex(index);

    if (!indiaCodeTexts[index]) {
      setIndiaCodeTexts((prev) => ({ ...prev, [index]: { loading: true } }));
      try {
        const searchRes = await searchLegalAuthorities(caseFile.id, law.query, { limit: 3 });
        const indiaCodeMatch = searchRes.results.find((r) => r.provider === "india_code");
        if (indiaCodeMatch) {
          const matchMeta = (indiaCodeMatch as { metadata?: { section_text?: string } }).metadata;
          setIndiaCodeTexts((prev) => ({
            ...prev,
            [index]: {
              loading: false,
              text: indiaCodeMatch.snippet || matchMeta?.section_text || "Statutory provision text found in India Code.",
            },
          }));
        } else {
          setIndiaCodeTexts((prev) => ({
            ...prev,
            [index]: {
              loading: false,
              text: "No direct statutory match was found in India Code. Broader research is available in Legal Research.",
            },
          }));
        }
      } catch {
        setIndiaCodeTexts((prev) => ({
          ...prev,
          [index]: {
            loading: false,
            error: "Could not fetch statutory text.",
          },
        }));
      }
    }
  }

  return (
    <PageShell>
      {/* 1. Header */}
      <PageHeader
        title="Overview"
        description="Where this case stands."
      />

      {/* 2. Stats: Row of 4 plain numbers (Inter 24px) separated by hairlines */}
      <div className="grid grid-cols-2 sm:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-[var(--border)] rounded-lg border border-[var(--border)] bg-[var(--surface)] py-4">
        <div className="px-5 py-2">
          <div className="text-2xl font-semibold tracking-tight text-[var(--text)]">{totalDocs}</div>
          <div className="text-xs text-[var(--text-muted)] mt-0.5">Documents</div>
        </div>
        <div className="px-5 py-2">
          <div className="text-2xl font-semibold tracking-tight text-[var(--text)]">{totalUnits}</div>
          <div className="text-xs text-[var(--text-muted)] mt-0.5">Pages read</div>
        </div>
        <div className="px-5 py-2">
          <div className="text-2xl font-semibold tracking-tight text-[var(--text)]">{reviewDocs + failedDocs}</div>
          <div className="text-xs text-[var(--text-muted)] mt-0.5">Items to review</div>
        </div>
        <div className="px-5 py-2">
          <div className="text-2xl font-semibold tracking-tight text-[var(--text)]">
            {caseFile.next_hearing_date ? formatDate(caseFile.next_hearing_date, true) : "None"}
          </div>
          <div className="text-xs text-[var(--text-muted)] mt-0.5">Next hearing</div>
        </div>
      </div>

      {/* 3. Progress: Horizontal 5-Step Indicator */}
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
        <div className="text-xs font-medium text-[var(--text-muted)] mb-3">Workflow progress</div>
        <div className="flex items-center justify-between gap-2 overflow-x-auto">
          {progressSteps.map((step, idx) => {
            const isDone = step.status === "done";
            const isCurrent = step.status === "current";

            return (
              <div key={step.label} className="flex items-center gap-2 flex-1 min-w-[100px]">
                <button
                  type="button"
                  onClick={() => onNavigate(step.id)}
                  className="flex items-center gap-2 text-left group"
                >
                  <div
                    className={`grid size-6 place-items-center rounded-full text-xs font-medium transition ${
                      isDone
                        ? "bg-[var(--brass)] text-white"
                        : isCurrent
                        ? "border-2 border-[var(--primary)] text-[var(--primary)] font-semibold bg-[var(--primary-tint)]"
                        : "border border-[var(--border-strong)] text-[var(--text-faint)]"
                    }`}
                  >
                    {isDone ? "✓" : idx + 1}
                  </div>
                  <span
                    className={`text-xs ${
                      isDone
                        ? "font-medium text-[var(--text)] group-hover:text-[var(--primary)]"
                        : isCurrent
                        ? "font-semibold text-[var(--primary)]"
                        : "text-[var(--text-faint)]"
                    }`}
                  >
                    {step.label}
                  </span>
                </button>
                {idx < progressSteps.length - 1 && (
                  <div className="flex-1 hairline" />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 4. Needs Attention: At most 3 rows inside single bordered surface */}
      <div className="space-y-2">
        <div className="text-xs font-medium text-[var(--text-muted)]">Needs attention</div>

        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
          {totalDocs === 0 ? (
            <div className="p-4 text-xs text-[var(--text-muted)] flex items-center justify-between">
              <span>No documents added yet. Upload pleadings or affidavits to start.</span>
              <button
                type="button"
                onClick={() => onNavigate("documents")}
                className="btn-primary text-xs"
              >
                Upload documents
              </button>
            </div>
          ) : reviewDocs === 0 && failedDocs === 0 ? (
            <div className="p-4 text-xs text-[var(--success)] flex items-center gap-2">
              <CheckCircle2 className="size-4 shrink-0" />
              <span>All uploaded documents have readable extracted text. Ready for analysis.</span>
            </div>
          ) : (
            <>
              {reviewDocs > 0 && (
                <div className="p-3 text-xs flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <StatusDot status="Needs review" />
                    <div>
                      <span className="font-medium text-[var(--text)]">{reviewDocs} document(s) need OCR review</span>
                      <p className="text-[11px] text-[var(--text-muted)]">Low confidence detected on scanned pages.</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onNavigate("documents")}
                    className="btn-ghost text-xs text-[var(--primary)]"
                  >
                    Review text
                  </button>
                </div>
              )}
              {failedDocs > 0 && (
                <div className="p-3 text-xs flex items-center justify-between bg-[var(--danger)]/5">
                  <div className="flex items-center gap-2.5">
                    <StatusDot status="Failed" />
                    <div>
                      <span className="font-semibold text-[var(--danger)]">{failedDocs} document(s) unreadable — Analysis locked</span>
                      <p className="text-[11px] text-[var(--text-muted)]">Clean text could not be extracted. Replace or rescan file to enable analysis.</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onNavigate("documents")}
                    className="btn-ghost text-xs text-[var(--danger)] font-semibold underline"
                  >
                    Fix in Documents
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* 5. Legal Authorities in the Case File */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-[var(--text)]">
              Legal authorities in the case file
            </h3>
            {legalAuthorities.length > 0 && (
              <span className="rounded bg-[var(--surface-2)] px-1.5 py-0.5 font-mono text-[11px] font-semibold text-[var(--text)]">
                {legalAuthorities.length}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={() => onNavigate("research")}
            className="text-xs text-[var(--primary)] font-medium hover:underline flex items-center gap-1"
          >
            <span>Search India Code</span>
            <ArrowRight className="size-3" />
          </button>
        </div>

        <p className="text-xs text-[var(--text-muted)] flex items-center gap-1.5">
          <span>Explicit statute, provision, and case citations extracted from case documents.</span>
          <span title="Extracted references are candidates and do not confirm current binding applicability." className="cursor-help">
            <Info className="size-3.5 text-[var(--text-faint)]" />
          </span>
        </p>

        {loadingLaws ? (
          <div className="space-y-2">
            <div className="h-10 w-full animate-pulse rounded bg-[var(--surface)] border border-[var(--border)]" />
            <div className="h-10 w-full animate-pulse rounded bg-[var(--surface)] border border-[var(--border)]" />
          </div>
        ) : legalAuthorities.length === 0 ? (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 text-xs text-[var(--text-muted)] text-center">
            {hasAnalysis ? (
              <span>No explicit statutory sections or case citations were detected in the current analysis run.</span>
            ) : (
              <span>Run Case Analysis to extract statutory provisions, sections, and case citations.</span>
            )}
          </div>
        ) : (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
            {visibleAuthorities.map((law, idx) => {
              const isExpanded = expandedIndex === idx;
              const liveData = indiaCodeTexts[idx];

              return (
                <div key={`${law.query}-${idx}`}>
                  {/* Header / Toggle Row */}
                  <div className="flex w-full items-center justify-between p-3.5 text-left text-xs hover:bg-[var(--surface-2)] transition">
                    <button
                      type="button"
                      onClick={() => toggleLawDetails(idx, law)}
                      className="flex items-center gap-2.5 min-w-0 flex-1 text-left"
                    >
                      <Scale className="size-3.5 shrink-0 text-[var(--brass)]" />
                      <div className="min-w-0">
                        <span className="font-medium text-sm text-[var(--text)] hover:text-[var(--primary)] transition">
                          {law.query}
                        </span>
                        <span className="text-xs text-[var(--text-muted)] ml-2">
                          {law.document} · {law.locator}
                        </span>
                      </div>
                    </button>

                    <div className="flex items-center gap-2.5 shrink-0">
                      <span className="text-xs text-[var(--text-muted)] capitalize hidden sm:inline">
                        {law.kind.replace(/[_-]+/g, " ")}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onNavigate("research", law.query);
                        }}
                        className="btn-ghost text-xs text-[var(--primary)] h-7 px-2 flex items-center gap-1 font-medium hover:bg-[var(--primary)]/10"
                        title="Search this authority directly in Legal Research"
                      >
                        <Search className="size-3" />
                        <span>Research</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleLawDetails(idx, law)}
                        className="p-1 text-[var(--text-muted)] hover:text-[var(--text)]"
                      >
                        {isExpanded ? (
                          <ChevronUp className="size-4" />
                        ) : (
                          <ChevronDown className="size-4" />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Expanded Body Content */}
                  {isExpanded && (
                    <div className="border-t border-[var(--border)] bg-[var(--surface-2)] p-4 text-xs space-y-3">
                      {law.evidence_quote && (
                        <div>
                          <div className="text-[11px] font-medium text-[var(--text-muted)] mb-1">
                            Cited in case file ({law.document} · {law.locator}):
                          </div>
                          <blockquote className="border-l-2 border-[var(--brass)] pl-2.5 italic text-[var(--text)] leading-relaxed font-serif">
                            “{law.evidence_quote}”
                          </blockquote>
                        </div>
                      )}

                      {/* Live India Code Statutory Text */}
                      <div>
                        <div className="text-[11px] font-medium text-[var(--text-muted)] mb-1 flex items-center justify-between">
                          <span>Statutory Text & Mapping (India Code):</span>
                          {liveData?.loading && (
                            <span className="flex items-center gap-1 text-[10px] text-[var(--text-muted)] font-mono">
                              <RefreshCw className="size-2.5 animate-spin" /> Fetching India Code…
                            </span>
                          )}
                        </div>

                        {liveData?.text && (
                          <div className="rounded-md bg-[var(--surface)] p-3 font-serif text-[13px] text-[var(--text)] leading-relaxed border border-[var(--border)] whitespace-pre-wrap">
                            {liveData.text}
                          </div>
                        )}

                        {liveData?.error && (
                          <div className="text-xs text-[var(--danger)]">
                            {liveData.error}
                          </div>
                        )}
                      </div>

                      {/* Action */}
                      <div className="flex justify-end pt-1">
                        <button
                          type="button"
                          onClick={() => onNavigate("research", law.query)}
                          className="btn-primary h-8 px-3 text-xs flex items-center gap-1.5"
                        >
                          <Search className="size-3.5" />
                          <span>Search Full India Code / Kanoon</span>
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            {legalAuthorities.length > 6 && (
              <div className="p-2.5 text-center">
                <button
                  type="button"
                  onClick={() => setShowAllAuthorities(!showAllAuthorities)}
                  className="text-xs font-medium text-[var(--primary)] hover:underline"
                >
                  {showAllAuthorities ? "Show fewer" : `Show all (${legalAuthorities.length})`}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </PageShell>
  );
}
