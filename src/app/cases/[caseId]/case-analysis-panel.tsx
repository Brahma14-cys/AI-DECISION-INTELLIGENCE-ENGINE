"use client";

import { useEffect, useState } from "react";
import {
  Sparkles,
  RefreshCw,
  FileText,
  CheckCircle,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Info,
  Scale,
  ShieldCheck,
  Eye,
  ShieldAlert,
  ArrowRight,
} from "lucide-react";
import {
  CaseAnalysisAvailability,
  CaseAnalysisFact,
  CaseAnalysisFinding,
  CaseAnalysisExtractionItem,
  CaseClaimReview,
  CaseAnalysisResult,
  CaseAnalysisRun,
  CaseDocument,
  getLatestCaseAnalysis,
  startCaseAnalysis,
} from "@/lib/api";
import { PageShell, PageHeader, PageBody } from "@/components/domain/page-shell";
import { EmptyState } from "@/components/domain/empty-state";
import { InlineAlert } from "@/components/domain/inline-alert";
import { StatusDot } from "@/components/domain/status-dot";
import { CitationChip } from "@/components/domain/citation-chip";
import { formatLabel } from "@/lib/formatters";

export function CaseAnalysisPanel({
  caseId,
  documents,
  availability,
}: {
  caseId: string;
  documents: CaseDocument[];
  availability: CaseAnalysisAvailability | null;
}) {
  const [analysis, setAnalysis] = useState<CaseAnalysisResult | null>(null);
  const [queuedRun, setQueuedRun] = useState<CaseAnalysisRun | null>(null);
  const [starting, setStarting] = useState(false);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter & tab controls
  const [activeTab, setActiveTab] = useState<"facts" | "issues" | "parties" | "contradictions" | "claims">("facts");
  const [claimsExpanded, setClaimsExpanded] = useState(false);
  const [claimDraft, setClaimDraft] = useState("");
  const [showPrivacyPopover, setShowPrivacyPopover] = useState(false);

  // Detect unreadable or critically low OCR documents
  const unreadableDocuments = documents.filter((doc) => {
    if (doc.processing_status === "failed") return true;
    if (["processed", "needs_review"].includes(doc.processing_status) && doc.text_unit_count === 0) return true;
    if (doc.unreadable_location_count > 0 && doc.readable_location_count === 0) return true;
    if (doc.pages_without_text_count > 0 && doc.pages_with_text_count === 0) return true;
    return false;
  });

  const isAnalysisBlocked = unreadableDocuments.length > 0;

  const run = analysis?.run ?? queuedRun;
  const isPending = run !== null && ["queued", "processing"].includes(run.status);
  const hasAnalysisRun = Boolean(analysis?.run && analysis.run.status === "completed");
  const hasFailedRun = Boolean(analysis?.run && analysis.run.status === "failed");
  const documentsReady =
    documents.length > 0 &&
    documents.every((doc) => ["processed", "needs_review"].includes(doc.processing_status)) &&
    documents.some((doc) => doc.text_unit_count > 0);

  const fetchAnalysis = async () => {
    try {
      const result = await getLatestCaseAnalysis(caseId);
      setAnalysis(result);
      if (result && ["completed", "failed"].includes(result.run.status)) {
        setQueuedRun(null);
      }
    } catch {
      // 404 means no analysis run yet
      setAnalysis(null);
    } finally {
      setLoadingInitial(false);
    }
  };

  useEffect(() => {
    void fetchAnalysis();
  }, [caseId]);

  useEffect(() => {
    if (!isPending) return;
    const timer = window.setInterval(() => {
      void fetchAnalysis();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [caseId, isPending]);

  async function executeAnalysis(acknowledgeIncomplete = false) {
    setStarting(true);
    setError(null);
    try {
      const claims = claimDraft
        .split("\n")
        .map((claim) => claim.trim())
        .filter(Boolean);
      if (claims.length > 20) throw new Error("Add up to 20 advocate-entered claims per analysis run.");

      const runData = await startCaseAnalysis(caseId, claims, acknowledgeIncomplete || isAnalysisBlocked);
      setQueuedRun(runData);
      setAnalysis((prev) => (prev ? { ...prev, run: runData } : null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start case analysis.");
    } finally {
      setStarting(false);
    }
  }

  function handleRunClick() {
    void executeAnalysis(isAnalysisBlocked);
  }

  const facts: CaseAnalysisFact[] = analysis?.facts ?? [];
  const items: CaseAnalysisExtractionItem[] = analysis?.extraction_items ?? [];
  const issues = items.filter((it) => it.item_kind === "sentence_role" || it.category.toLowerCase().includes("issue"));
  const entities = items.filter((it) => it.item_kind === "entity" || it.item_kind === "date" || it.item_kind === "amount");
  const contradictions: CaseAnalysisFinding[] = analysis?.findings ?? [];
  const claimEvaluations: CaseClaimReview[] = analysis?.claim_reviews ?? [];

  return (
    <PageShell>
      {/* 1. Header */}
      <PageHeader
        title="Analysis"
        description="Extract facts and compare documents."
        actions={
          <button
            type="button"
            disabled={isAnalysisBlocked || starting || isPending || !documentsReady}
            onClick={handleRunClick}
            className={`btn-primary ${isAnalysisBlocked ? "opacity-50 cursor-not-allowed" : ""}`}
            title={
              isAnalysisBlocked
                ? "Analysis is locked because unreadable / low-OCR files exist in Documents"
                : undefined
            }
          >
            <Sparkles className="size-4" />
            <span>
              {isAnalysisBlocked
                ? "Analysis locked (unreadable files)"
                : isPending
                ? "Analyzing…"
                : hasFailedRun
                ? "Retry analysis"
                : hasAnalysisRun
                ? "Run again"
                : "Run analysis"}
            </span>
          </button>
        }
      />

      {/* 2. Subheader compact row: Document coverage & Privacy info */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-xs">
        <div className="flex items-center gap-2">
          <FileText className="size-3.5 text-[var(--brass)]" />
          <span className="font-medium text-[var(--text)]">
            {documents.filter((d) => d.processing_status === "processed" && d.text_unit_count > 0).length} of {documents.length} documents ready for analysis
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-[var(--text-muted)]">
          <span>Readable text is sent to Gemini in batches. Files stay local.</span>
          <button
            type="button"
            onClick={() => setShowPrivacyPopover(!showPrivacyPopover)}
            className="text-[var(--text-muted)] hover:text-[var(--text)] p-0.5"
            title="Privacy and batching details"
          >
            <Info className="size-3.5" />
          </button>
        </div>
      </div>

      {/* Privacy Popover */}
      {showPrivacyPopover && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-4 text-xs leading-relaxed text-[var(--text-muted)] space-y-2">
          <div className="font-medium text-[var(--text)] flex items-center gap-1.5">
            <ShieldCheck className="size-4 text-[var(--brass)]" />
            <span>Privacy and Local Verification Safeguards</span>
          </div>
          <p>
            Files and OCR raw images remain on local storage. Only extracted text segments are transmitted in encrypted batches to the Gemini model for fact extraction. Findings are grounded against exact file coordinates.
          </p>
        </div>
      )}

      {/* Strict Lock Alert if Unreadable / Low-OCR files exist */}
      {isAnalysisBlocked && (
        <div className="rounded-lg border border-[var(--danger)]/30 bg-[var(--surface)] p-4 flex items-start gap-3 text-xs border-l-4 border-l-[var(--danger)] shadow-sm">
          <ShieldAlert className="size-5 text-[var(--danger)] shrink-0 mt-0.5" />
          <div className="space-y-1">
            <div className="font-semibold text-[var(--text)] text-sm">
              Analysis is locked: {unreadableDocuments.length} document(s) are unreadable or have critically low OCR confidence
            </div>
            <p className="text-[var(--text-muted)] leading-relaxed">
              The following file(s) failed clean text extraction:{" "}
              <strong className="text-[var(--text)] font-mono">
                {unreadableDocuments.map((d) => d.original_filename).join(", ")}
              </strong>
              . To prevent erroneous fact extraction or hallucinated legal conclusions, please replace these files with clearer scans or retry OCR extraction in the Documents module before starting analysis.
            </p>
          </div>
        </div>
      )}

      {error && (
        <InlineAlert type="error" message={error} />
      )}

      {/* 3. Collapsible 'Add claims to check' */}
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)]">
        <button
          type="button"
          onClick={() => setClaimsExpanded(!claimsExpanded)}
          className="flex w-full items-center justify-between p-3 text-left text-xs font-medium text-[var(--text)] hover:bg-[var(--surface-2)] transition"
        >
          <span>Add claims to check (optional)</span>
          {claimsExpanded ? <ChevronUp className="size-4 text-[var(--text-muted)]" /> : <ChevronDown className="size-4 text-[var(--text-muted)]" />}
        </button>

        {claimsExpanded && (
          <div className="border-t border-[var(--border)] p-4 space-y-2">
            <textarea
              rows={3}
              value={claimDraft}
              onChange={(e) => setClaimDraft(e.target.value)}
              placeholder="Enter advocate claims to verify against the evidence (one claim per line, up to 20)…"
              className="input-field h-auto w-full p-2.5 text-xs font-normal"
            />
            <p className="text-[11px] text-[var(--text-muted)]">
              One claim per line, up to 20. Claims are tested against extracted text passages.
            </p>
          </div>
        )}
      </div>

      {/* 4. Running State Stepper */}
      {isPending && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5 text-center space-y-3">
          <div className="flex items-center justify-center gap-2 text-xs font-medium text-[var(--primary)]">
            <RefreshCw className="size-4 animate-spin" />
            <span>Analyzing case documents… Stage: {run?.status || "Processing"}</span>
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            Screening candidate facts, cross-document relations, and legal entities. This may take 30-60 seconds for multi-page filings.
          </p>
        </div>
      )}

      {/* 5. Results Area */}
      <PageBody>
        {loadingInitial ? (
          <div className="space-y-3 py-4">
            <div className="h-8 w-1/3 animate-pulse rounded bg-[var(--surface)] border border-[var(--border)]" />
            <div className="h-32 w-full animate-pulse rounded bg-[var(--surface)] border border-[var(--border)]" />
            <div className="h-32 w-full animate-pulse rounded bg-[var(--surface)] border border-[var(--border)]" />
          </div>
        ) : hasFailedRun ? (
          <div className="rounded-lg border border-[var(--danger)]/30 bg-[var(--surface)] p-6 space-y-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="size-5 text-[var(--danger)] shrink-0 mt-0.5" />
              <div className="space-y-1.5 flex-1">
                <h3 className="text-sm font-semibold text-[var(--text)]">Analysis Run Encountered an Error</h3>
                <p className="text-xs text-[var(--text-muted)] leading-relaxed">
                  {analysis?.run.error_message || "The AI model encountered an issue during fact extraction or relationship analysis."}
                </p>
              </div>
            </div>
            <div className="pt-2 flex items-center justify-end gap-2 border-t border-[var(--border)]">
              <button
                type="button"
                disabled={starting || isAnalysisBlocked || !documentsReady}
                onClick={handleRunClick}
                className="btn-primary text-xs flex items-center gap-1.5"
              >
                <RefreshCw className={`size-3.5 ${starting ? "animate-spin" : ""}`} />
                <span>Retry Analysis</span>
              </button>
            </div>
          </div>
        ) : analysis?.run.status === "completed" ? (
          <div className="space-y-4">
            {/* Tabs Row */}
            <div className="flex items-center gap-1 border-b border-[var(--border)] pb-2 overflow-x-auto text-xs">
              <button
                type="button"
                onClick={() => setActiveTab("facts")}
                className={`px-3 py-1.5 rounded-md font-medium transition ${
                  activeTab === "facts"
                    ? "bg-[var(--primary-tint)] text-[var(--primary)]"
                    : "text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)]"
                }`}
              >
                Facts ({facts.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("issues")}
                className={`px-3 py-1.5 rounded-md font-medium transition ${
                  activeTab === "issues"
                    ? "bg-[var(--primary-tint)] text-[var(--primary)]"
                    : "text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)]"
                }`}
              >
                Issues ({issues.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("parties")}
                className={`px-3 py-1.5 rounded-md font-medium transition ${
                  activeTab === "parties"
                    ? "bg-[var(--primary-tint)] text-[var(--primary)]"
                    : "text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)]"
                }`}
              >
                Parties & dates ({entities.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("contradictions")}
                className={`px-3 py-1.5 rounded-md font-medium transition ${
                  activeTab === "contradictions"
                    ? "bg-[var(--primary-tint)] text-[var(--primary)]"
                    : "text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)]"
                }`}
              >
                Review leads ({contradictions.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("claims")}
                className={`px-3 py-1.5 rounded-md font-medium transition ${
                  activeTab === "claims"
                    ? "bg-[var(--primary-tint)] text-[var(--primary)]"
                    : "text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)]"
                }`}
              >
                Claim check ({claimEvaluations.length})
              </button>
            </div>

            {/* Facts Tab */}
            {activeTab === "facts" && (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
                {facts.length === 0 ? (
                  <div className="p-6 text-center text-xs text-[var(--text-muted)]">No facts extracted.</div>
                ) : (
                  facts.map((fact, idx) => (
                    <div key={idx} className="p-3.5 text-xs flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                      <div className="space-y-1 flex-1">
                        <div className="font-medium text-[var(--text)] leading-relaxed">{fact.statement}</div>
                      </div>
                      <div className="shrink-0">
                        <CitationChip
                          caseId={caseId}
                          documentId={fact.source_document_id}
                          unitId={fact.source_text_unit_id}
                          filename={fact.source_filename}
                          locator={fact.source_locator}
                          quote={fact.statement}
                          start={fact.source_start_char}
                          end={fact.source_end_char}
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Issues Tab */}
            {activeTab === "issues" && (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
                {issues.length === 0 ? (
                  <div className="p-6 text-center text-xs text-[var(--text-muted)]">No issues extracted.</div>
                ) : (
                  issues.map((issue, idx) => (
                    <div key={idx} className="p-3.5 text-xs flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                      <div className="font-medium text-[var(--text)] leading-relaxed">{issue.text}</div>
                      <div className="shrink-0">
                        <CitationChip
                          caseId={caseId}
                          documentId={issue.source_document_id}
                          unitId={issue.source_text_unit_id}
                          filename={issue.source_filename}
                          locator={issue.source_locator}
                          quote={issue.evidence_quote || issue.text}
                          start={issue.source_start_char}
                          end={issue.source_end_char}
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Parties & Dates Tab */}
            {activeTab === "parties" && (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
                {entities.length === 0 ? (
                  <div className="p-6 text-center text-xs text-[var(--text-muted)]">No parties or entities extracted.</div>
                ) : (
                  entities.map((ent, idx) => (
                    <div key={idx} className="p-3.5 text-xs flex items-center justify-between gap-3">
                      <div>
                        <span className="font-medium text-[var(--text)]">{ent.text}</span>
                        <span className="ml-2 text-[11px] text-[var(--text-muted)]">({formatLabel(ent.category)})</span>
                      </div>
                      <div className="shrink-0">
                        <CitationChip
                          caseId={caseId}
                          documentId={ent.source_document_id}
                          unitId={ent.source_text_unit_id}
                          filename={ent.source_filename}
                          locator={ent.source_locator}
                          quote={ent.evidence_quote || ent.text}
                          start={ent.source_start_char}
                          end={ent.source_end_char}
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Review Leads (Contradictions) Tab */}
            {activeTab === "contradictions" && (
              <div className="space-y-3">
                <p className="text-xs text-[var(--text-muted)]">
                  A review lead is not a finding that anyone lied. Compare passages across filings to inspect variance.
                </p>

                <div className="space-y-3">
                  {contradictions.length === 0 ? (
                    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 text-center text-xs text-[var(--text-muted)]">
                      No direct cross-document contradictions detected.
                    </div>
                  ) : (
                    contradictions.map((lead, idx) => (
                      <div key={idx} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 space-y-3">
                        <div className="font-medium text-xs text-[var(--text)]">
                          {lead.explanation || "Variance between document statements"}
                        </div>

                        <div className="grid gap-3 sm:grid-cols-2">
                          <div className="rounded bg-[var(--surface-2)] p-3 space-y-2 text-xs">
                            <div className="text-[11px] font-medium text-[var(--text-muted)]">Statement A:</div>
                            <blockquote className="italic text-[var(--text)] leading-relaxed">
                              “{lead.left_fact?.statement}”
                            </blockquote>
                            <div className="pt-1">
                              <CitationChip
                                caseId={caseId}
                                documentId={lead.left_fact?.source_document_id || ""}
                                unitId={lead.left_fact?.source_text_unit_id || ""}
                                filename={lead.left_fact?.source_filename || "Doc A"}
                                locator={lead.left_fact?.source_locator || ""}
                                quote={lead.left_fact?.statement || ""}
                              />
                            </div>
                          </div>

                          <div className="rounded bg-[var(--surface-2)] p-3 space-y-2 text-xs">
                            <div className="text-[11px] font-medium text-[var(--text-muted)]">Statement B:</div>
                            <blockquote className="italic text-[var(--text)] leading-relaxed">
                              “{lead.right_fact?.statement}”
                            </blockquote>
                            <div className="pt-1">
                              <CitationChip
                                caseId={caseId}
                                documentId={lead.right_fact?.source_document_id || ""}
                                unitId={lead.right_fact?.source_text_unit_id || ""}
                                filename={lead.right_fact?.source_filename || "Doc B"}
                                locator={lead.right_fact?.source_locator || ""}
                                quote={lead.right_fact?.statement || ""}
                              />
                            </div>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* Claim Check Tab */}
            {activeTab === "claims" && (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
                {claimEvaluations.length === 0 ? (
                  <div className="p-6 text-center text-xs text-[var(--text-muted)]">
                    No advocate claims were submitted for this analysis run.
                  </div>
                ) : (
                  claimEvaluations.map((evalItem, idx) => (
                    <div key={idx} className="p-4 space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm text-[var(--text)]">{evalItem.claim_text}</span>
                        <StatusDot
                          status={
                            evalItem.support_status === "supported"
                              ? "Ready"
                              : evalItem.support_status === "unsupported"
                              ? "Failed"
                              : "Needs review"
                          }
                        />
                      </div>
                      <p className="text-[var(--text-muted)] leading-relaxed">{evalItem.explanation}</p>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        ) : !isPending ? (
          <EmptyState
            icon={Sparkles}
            title={isAnalysisBlocked ? "Analysis locked due to unreadable files" : "No analysis results yet"}
            description={
              isAnalysisBlocked
                ? `Extraction failed on ${unreadableDocuments.length} document(s). Replace unreadable files or retry scan in Documents to unlock analysis.`
                : "Run cross-document extraction to detect facts, issues, contradictions, and verify case claims."
            }
            action={
              <button
                type="button"
                disabled={isAnalysisBlocked || starting || !documentsReady}
                onClick={handleRunClick}
                className={`btn-primary ${isAnalysisBlocked ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                <Sparkles className="size-4" />
                <span>{isAnalysisBlocked ? "Locked" : "Run analysis"}</span>
              </button>
            }
          />
        ) : null}
      </PageBody>
    </PageShell>
  );
}

