"use client";

import { useEffect, useState, useCallback } from "react";
import { X, ExternalLink, Copy, Check, FileText, ChevronLeft, ChevronRight, AlertCircle } from "lucide-react";
import { getDocumentText, DocumentTextUnit } from "@/lib/api";

export type SourcePeekTarget = {
  caseId: string;
  documentId?: string;
  filename?: string;
  documentName?: string;
  unitId?: string;
  locator?: string;
  start?: number | null;
  end?: number | null;
  quote?: string;
};

export function SourcePeekDrawer() {
  const [target, setTarget] = useState<SourcePeekTarget | null>(null);
  const [units, setUnits] = useState<DocumentTextUnit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const close = useCallback(() => {
    setTarget(null);
    setUnits(null);
    setError(null);
  }, []);

  useEffect(() => {
    function handleOpen(event: Event) {
      const detail = (event as CustomEvent<SourcePeekTarget>).detail;
      if (!detail || !detail.caseId || !detail.documentId) return;
      setTarget(detail);
      setLoading(true);
      setError(null);

      getDocumentText(detail.caseId, detail.documentId)
        .then((data) => {
          setUnits(data);
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Failed to load document text.");
        })
        .finally(() => {
          setLoading(false);
        });
    }

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        close();
      }
    }

    window.addEventListener("legal-source-jump", handleOpen);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("legal-source-jump", handleOpen);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [close]);

  if (!target) return null;

  const currentUnit = units?.find((u) => u.id === target.unitId) || units?.[0];
  const unitIndex = units && currentUnit ? units.indexOf(currentUnit) : -1;

  function copyCitation() {
    const citation = `${target?.filename || "Document"} (${currentUnit?.locator_label || target?.locator || "Page"}): "${target?.quote || currentUnit?.text || ""}"`;
    navigator.clipboard.writeText(citation);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function goToUnit(index: number) {
    if (!units || index < 0 || index >= units.length) return;
    const nextUnit = units[index];
    setTarget((prev) => (prev ? { ...prev, unitId: nextUnit.id, locator: nextUnit.locator_label } : null));
  }

  return (
    <aside
      className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[480px] flex-col border-l border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-drawer)] transition-transform duration-200 ease-out"
      aria-labelledby="source-peek-heading"
      role="complementary"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border)] bg-[var(--surface-2)] px-5 py-3.5">
        <div className="flex items-center gap-2.5 min-w-0">
          <FileText className="size-4 shrink-0 text-[var(--accent-strong)]" />
          <div className="min-w-0">
            <h2 id="source-peek-heading" className="truncate text-xs font-bold text-[var(--text)]">
              {target.filename || "Source Inspection"}
            </h2>
            <p className="font-mono text-[10px] text-[var(--text-muted)]">
              {currentUnit?.locator_label || target.locator || "Location Reference"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={copyCitation}
            className="inline-flex size-7 items-center justify-center rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--text-muted)] hover:text-[var(--text)]"
            title="Copy formal citation"
          >
            {copied ? <Check className="size-3.5 text-[var(--status-success)]" /> : <Copy className="size-3.5" />}
          </button>
          <button
            type="button"
            onClick={close}
            className="inline-flex size-7 items-center justify-center rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--text-muted)] hover:text-[var(--text)]"
            title="Close drawer (Esc)"
          >
            <X className="size-4" />
          </button>
        </div>
      </div>

      {/* Traversal Controls */}
      {units && units.length > 1 && (
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-2 text-[11px] text-[var(--text-muted)]">
          <span>Unit {unitIndex + 1} of {units.length}</span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={unitIndex <= 0}
              onClick={() => goToUnit(unitIndex - 1)}
              className="inline-flex items-center gap-0.5 rounded px-2 py-0.5 text-xs font-medium hover:bg-[var(--surface-2)] disabled:opacity-30"
            >
              <ChevronLeft className="size-3" /> Prev
            </button>
            <button
              type="button"
              disabled={unitIndex >= units.length - 1}
              onClick={() => goToUnit(unitIndex + 1)}
              className="inline-flex items-center gap-0.5 rounded px-2 py-0.5 text-xs font-medium hover:bg-[var(--surface-2)] disabled:opacity-30"
            >
              Next <ChevronRight className="size-3" />
            </button>
          </div>
        </div>
      )}

      {/* Body Content */}
      <div className="flex-1 overflow-y-auto p-5 text-sm">
        {loading && (
          <div className="space-y-3">
            <div className="h-4 w-3/4 animate-pulse rounded bg-[var(--surface-2)]" />
            <div className="h-24 w-full animate-pulse rounded bg-[var(--surface-2)]" />
            <div className="h-32 w-full animate-pulse rounded bg-[var(--surface-2)]" />
          </div>
        )}

        {error && (
          <div className="rounded-md border border-[var(--status-danger)]/30 bg-[var(--status-danger-bg)] p-3 text-xs text-[var(--status-danger)]">
            <div className="flex items-center gap-1.5 font-semibold">
              <AlertCircle className="size-4" /> Could not load extracted text
            </div>
            <p className="mt-1">{error}</p>
          </div>
        )}

        {!loading && !error && currentUnit && (
          <div>
            {currentUnit.ocr_needs_review && (
              <div className="mb-4 rounded-md border border-[var(--status-warning)]/40 bg-[var(--status-warning-bg)] p-3 text-xs text-[var(--status-warning)]">
                <p className="font-semibold">Low or unavailable OCR confidence</p>
                <p className="mt-0.5 text-[11px] leading-relaxed">Check this page against the original before relying on its extracted text.</p>
              </div>
            )}

            <div className="mb-3 flex items-center justify-between text-[11px] font-mono text-[var(--text-faint)]">
              <span>Method: {currentUnit.extraction_method.replaceAll("_", " ")}</span>
              {currentUnit.ocr_confidence !== null && (
                <span>OCR: {Math.round(currentUnit.ocr_confidence)}%</span>
              )}
            </div>

            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-4 leading-relaxed text-[var(--text)]">
              {currentUnit.text ? (
                <p className="whitespace-pre-wrap font-serif text-[13px] leading-6">
                  {target.start !== null &&
                  target.end !== null &&
                  target.start !== undefined &&
                  target.end !== undefined &&
                  target.start >= 0 &&
                  target.end <= currentUnit.text.length &&
                  target.end > target.start ? (
                    <>
                      {currentUnit.text.slice(0, target.start)}
                      <mark className="rounded bg-[#FFE8A3] px-1 py-0.5 font-medium text-[#422B00] dark:bg-[#684C10] dark:text-[#FFF2D1]">
                        {currentUnit.text.slice(target.start, target.end)}
                      </mark>
                      {currentUnit.text.slice(target.end)}
                    </>
                  ) : (
                    currentUnit.text
                  )}
                </p>
              ) : (
                <p className="text-xs italic text-[var(--text-muted)]">[No text detected on this page/location.]</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer Strip */}
      <div className="border-t border-[var(--border)] bg-[var(--surface)] px-5 py-3 text-[11px] text-[var(--text-faint)]">
        Source document verification · Exact match highlighted
      </div>
    </aside>
  );
}
