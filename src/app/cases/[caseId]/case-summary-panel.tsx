"use client";

import { useEffect, useState } from "react";
import {
  FileCheck,
  RefreshCw,
  Printer,
  FileText,
  Clock,
  Scale,
} from "lucide-react";
import {
  CaseAnalysisAvailability,
  CaseDocument,
  CaseSummaryPoint,
  CaseSummaryResult,
  CaseSummaryRun,
  CaseSummarySection,
  getLatestCaseSummary,
  startCaseSummary,
} from "@/lib/api";
import { PageShell, PageHeader, PageBody } from "@/components/domain/page-shell";
import { EmptyState } from "@/components/domain/empty-state";
import { InlineAlert } from "@/components/domain/inline-alert";
import { CitationChip } from "@/components/domain/citation-chip";
import { formatDate } from "@/lib/formatters";

export function CaseSummaryPanel({
  caseId,
  documents,
  availability,
}: {
  caseId: string;
  documents: CaseDocument[];
  availability: CaseAnalysisAvailability | null;
}) {
  const [summary, setSummary] = useState<CaseSummaryResult | null>(null);
  const [queuedRun, setQueuedRun] = useState<CaseSummaryRun | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acknowledgeIncomplete, setAcknowledgeIncomplete] = useState(false);

  const incompleteDocuments = documents.filter((d) => ["failed", "needs_review"].includes(d.processing_status));
  const run = summary?.run ?? queuedRun;
  const pending = run !== null && ["queued", "processing"].includes(run.status);
  const documentsReady =
    documents.length > 0 &&
    documents.every((d) => ["processed", "needs_review", "failed"].includes(d.processing_status)) &&
    documents.some((d) => d.text_unit_count > 0);

  useEffect(() => {
    let active = true;
    void getLatestCaseSummary(caseId)
      .then((res) => { if (active) setSummary(res); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [caseId]);

  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => {
      void getLatestCaseSummary(caseId)
        .then((res) => {
          setSummary(res);
          if (res && ["completed", "failed"].includes(res.run.status)) {
            setQueuedRun(null);
          }
        })
        .catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [caseId, pending]);

  async function generateSummary() {
    setStarting(true);
    setError(null);
    try {
      const res = await startCaseSummary(caseId, acknowledgeIncomplete);
      setQueuedRun(res);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Could not generate case summary.";
      if (msg.includes("already queued or running")) {
        void getLatestCaseSummary(caseId)
          .then((res) => { if (res) setSummary(res); })
          .catch(() => undefined);
      } else {
        setError(msg);
      }
    } finally {
      setStarting(false);
    }
  }

  function handlePrint() {
    window.print();
  }

  const narrative = summary?.narrative_summary ?? [];
  const sections = summary?.structured_summary ?? [];

  return (
    <PageShell>
      {/* 1. Header */}
      <PageHeader
        title="Summary"
        description="Chronology, core claims, and procedural brief."
        actions={
          <div className="flex items-center gap-2">
            {summary && (
              <button
                type="button"
                onClick={handlePrint}
                className="btn-ghost text-xs flex items-center gap-1.5"
                title="Print or export PDF"
              >
                <Printer className="size-3.5" />
                <span>Export PDF</span>
              </button>
            )}

            <button
              type="button"
              disabled={starting || pending || !documentsReady}
              onClick={generateSummary}
              className="btn-primary text-xs"
            >
              <FileCheck className="size-3.5" />
              <span>
                {pending
                  ? "Generating…"
                  : summary
                  ? "Regenerate"
                  : "Generate summary"}
              </span>
            </button>
          </div>
        }
      />

      {error && (
        <InlineAlert type="error" message={error} />
      )}

      {/* Incomplete source notice if applicable */}
      {incompleteDocuments.length > 0 && !summary && (
        <InlineAlert
          type="warning"
          message={`${incompleteDocuments.length} document${incompleteDocuments.length > 1 ? "s" : ""} pending OCR or review.`}
          action={
            <label className="flex items-center gap-1.5 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={acknowledgeIncomplete}
                onChange={(e) => setAcknowledgeIncomplete(e.target.checked)}
                className="rounded border-[var(--border-strong)] text-[var(--primary)] focus:ring-[var(--brass)]"
              />
              <span className="text-[var(--text-muted)]">Proceed with available text</span>
            </label>
          }
        />
      )}

      {/* Empty State */}
      {!summary && !pending && (
        <EmptyState
          icon={FileCheck}
          title="No summary generated yet"
          description="Synthesize all readable case pleadings, evidence, and orders into an integrated advocate brief with verified source citations."
          action={
            <button
              type="button"
              disabled={starting || !documentsReady}
              onClick={generateSummary}
              className="btn-primary"
            >
              <FileCheck className="size-4" />
              <span>{starting ? "Generating…" : "Generate summary"}</span>
            </button>
          }
        />
      )}

      {/* Generating State */}
      {pending && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-8 text-center space-y-3">
          <div className="flex items-center justify-center gap-2 text-xs font-medium text-[var(--primary)]">
            <RefreshCw className="size-4 animate-spin" />
            <span>Drafting case summary & timeline brief…</span>
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            Integrating source facts across all filings and validating citation links.
          </p>
        </div>
      )}

      {/* 2. Document Reading Layout (720px Centered Column with Sticky Outline on Left) */}
      {summary && (
        <PageBody>
          <div className="flex flex-col lg:flex-row gap-8 items-start justify-center">
            {/* Sticky Outline Navigation (Desktop: 200px) */}
            <aside className="hidden lg:block w-[200px] shrink-0 sticky top-20 text-xs space-y-2 text-[var(--text-muted)] border-r border-[var(--border)] pr-4">
              <div className="font-semibold text-[var(--text)] text-[12px] mb-2">
                Outline
              </div>
              {narrative.length > 0 && (
                <a href="#narrative" className="block hover:text-[var(--primary)] py-1">
                  Overview narrative
                </a>
              )}
              {sections.map((sec, sidx) => (
                <a
                  key={sec.section_key || sidx}
                  href={`#sec-${sec.section_key || sidx}`}
                  className="block hover:text-[var(--primary)] py-1 truncate"
                >
                  {sec.title}
                </a>
              ))}
            </aside>

            {/* Reading Column: Max 720px, Serif Section Headings, 15/25 Body */}
            <article className="w-full max-w-[720px] rounded-lg border border-[var(--border)] bg-[var(--surface)] p-8 sm:p-12 space-y-8">
              {/* Narrative Summary */}
              {narrative.length > 0 && (
                <section id="narrative" className="space-y-4">
                  <h2 className="text-xl font-medium tracking-tight text-[var(--text)] pb-2 border-b border-[var(--border)] font-serif">
                    Overview Narrative
                  </h2>
                  <div className="space-y-3 text-[15px] leading-[1.65] text-[var(--text)]">
                    {narrative.map((pt, pidx) => (
                      <div key={pidx} className="space-y-1.5">
                        <p>{pt.text}</p>
                        {pt.citations?.length > 0 && (
                          <div className="flex flex-wrap gap-1 pt-1">
                            {pt.citations.map((c, ci) => (
                              <CitationChip
                                key={ci}
                                caseId={caseId}
                                documentId={c.source_document_id}
                                filename={c.source_filename}
                                locator={c.source_locator}
                                quote={c.evidence_quote}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Structured Sections */}
              {sections.map((sec, sidx) => (
                <section key={sec.section_key || sidx} id={`sec-${sec.section_key || sidx}`} className="space-y-4 pt-4">
                  <h2 className="text-xl font-medium tracking-tight text-[var(--text)] pb-2 border-b border-[var(--border)] font-serif">
                    {sec.title}
                  </h2>
                  <div className="space-y-3">
                    {sec.points?.map((pt, pidx) => (
                      <div key={pidx} className="text-xs font-sans space-y-1.5 p-3 rounded-md bg-[var(--surface-2)]">
                        <p className="text-[14px] leading-relaxed text-[var(--text)]">
                          {pt.text}
                        </p>
                        {pt.citations?.length > 0 && (
                          <div className="flex flex-wrap gap-1 pt-1">
                            {pt.citations.map((c, ci) => (
                              <CitationChip
                                key={ci}
                                caseId={caseId}
                                documentId={c.source_document_id}
                                filename={c.source_filename}
                                locator={c.source_locator}
                                quote={c.evidence_quote}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </article>
          </div>
        </PageBody>
      )}
    </PageShell>
  );
}
