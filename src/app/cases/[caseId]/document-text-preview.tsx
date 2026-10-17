"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Search, RefreshCw, FileText, AlertTriangle, CheckCircle, Copy, Check } from "lucide-react";
import { DocumentTextUnit, getDocumentText } from "@/lib/api";

export function DocumentTextPreview({
  caseId,
  documentId,
  processingStatus,
}: {
  caseId: string;
  documentId: string;
  processingStatus: string;
}) {
  const [units, setUnits] = useState<DocumentTextUnit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedUnitId, setCopiedUnitId] = useState<string | null>(null);

  const [target, setTarget] = useState<{ unitId: string; start: number | null; end: number | null } | null>(null);
  const targetRef = useRef<HTMLLIElement>(null);

  const isPending = ["uploaded", "queued", "processing"].includes(processingStatus);

  const fetchText = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getDocumentText(caseId, documentId);
      setUnits(data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load extracted text.");
    } finally {
      setLoading(false);
    }
  }, [caseId, documentId]);

  // Auto-fetch on mount
  useEffect(() => {
    void fetchText();
  }, [fetchText]);

  // Poll while extraction is running or until units are loaded
  useEffect(() => {
    if (!isPending && units !== null && units.length > 0) return;
    const interval = window.setInterval(() => {
      void fetchText();
    }, 2000);
    return () => window.clearInterval(interval);
  }, [isPending, units, fetchText]);

  useEffect(() => {
    function handleSourceJump(event: Event) {
      const detail = (event as CustomEvent<{ documentId: string; unitId: string; start: number | null; end: number | null }>).detail;
      if (detail.documentId !== documentId) return;
      setTarget({ unitId: detail.unitId, start: detail.start, end: detail.end });
      void fetchText();
    }
    window.addEventListener("legal-source-jump", handleSourceJump);
    return () => window.removeEventListener("legal-source-jump", handleSourceJump);
  }, [documentId, fetchText]);

  useEffect(() => {
    if (!target || !units) return;
    targetRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [target, units]);

  async function handleCopy(unitId: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedUnitId(unitId);
      setTimeout(() => setCopiedUnitId(null), 2000);
    } catch {
      // Ignore clipboard error
    }
  }

  const filteredUnits = (units || []).filter((u) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return u.text.toLowerCase().includes(q) || u.locator_label.toLowerCase().includes(q);
  });

  return (
    <div className="space-y-4">
      {/* Search within document bar */}
      <div className="flex items-center justify-between gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[var(--text-faint)] pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search text in this document…"
            className="input-field h-9 w-full pl-10 text-xs"
          />
        </div>

        <button
          type="button"
          disabled={loading}
          onClick={fetchText}
          className="btn-secondary h-9 px-3 text-xs"
          title="Refresh extracted text"
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      {/* Loading or extraction in progress */}
      {(loading && units === null) || (isPending && (!units || units.length === 0)) ? (
        <div className="flex flex-col items-center justify-center p-10 text-xs text-[var(--text-muted)] space-y-2.5 border border-[var(--border)] rounded-lg bg-[var(--surface)] text-center">
          <RefreshCw className="size-5 animate-spin text-[var(--brass)]" />
          <p className="font-semibold text-[var(--text)]">
            {isPending ? "Extraction in progress…" : "Loading extracted text units…"}
          </p>
          <p className="text-[11px] leading-relaxed max-w-sm text-[var(--text-muted)]">
            The local OCR and document parser is reading pages and extracting text passages. This view will update automatically.
          </p>
        </div>
      ) : null}

      {/* Error state */}
      {error && (
        <div className="rounded-lg border border-[var(--danger)]/30 bg-[var(--surface)] p-4 text-xs text-[var(--danger)]">
          <p className="font-semibold">Failed to load text</p>
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">{error}</p>
        </div>
      )}

      {/* Empty / 0 units when fully processed */}
      {!loading && !isPending && units !== null && units.length === 0 && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-8 text-center text-xs text-[var(--text-muted)] space-y-3">
          <FileText className="mx-auto size-7 text-[var(--text-faint)]" />
          <p className="font-semibold text-[var(--text)]">No text extracted from this document</p>
          <p className="text-[11px] leading-relaxed max-w-sm mx-auto">
            The scanner detected 0 readable text lines. You can retry the scan or replace this file with a clearer scan.
          </p>
          <button
            type="button"
            onClick={() => void fetchText()}
            className="btn-secondary text-xs inline-flex items-center gap-1.5 mx-auto"
          >
            <RefreshCw className="size-3.5" />
            <span>Retry scan / reload text</span>
          </button>
        </div>
      )}

      {/* Text Units List */}
      {units !== null && units.length > 0 && (
        <div className="space-y-3">
          <div className="text-xs text-[var(--text-muted)] flex items-center justify-between">
            <span>
              Showing {filteredUnits.length} of {units.length} page segment(s)
            </span>
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="text-[var(--primary)] underline hover:opacity-80"
              >
                Clear filter
              </button>
            )}
          </div>

          <ol className="space-y-3">
            {filteredUnits.map((unit) => {
              const isTargeted = target?.unitId === unit.id;
              const hasText = Boolean(unit.text && unit.text.trim());

              return (
                <li
                  key={unit.id}
                  ref={isTargeted ? targetRef : undefined}
                  className={`rounded-lg border p-4 text-xs transition space-y-2.5 bg-[var(--surface)] ${
                    isTargeted
                      ? "border-[var(--brass)] ring-2 ring-[var(--brass)]/20"
                      : "border-[var(--border)]"
                  }`}
                >
                  {/* Page / Locator Header */}
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-2 text-[11px]">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-[var(--text)] bg-[var(--surface-2)] px-2 py-0.5 rounded border border-[var(--border)]">
                        {unit.locator_label || `Page ${unit.unit_number}`}
                      </span>
                      <span className="text-[var(--text-muted)] capitalize">
                        {unit.extraction_method?.replace(/[_-]+/g, " ") || "OCR"}
                      </span>
                    </div>

                    <div className="flex items-center gap-3">
                      {unit.ocr_confidence !== null && (
                        <span
                          className={`font-mono font-medium ${
                            unit.ocr_needs_review || unit.ocr_confidence < 70
                              ? "text-[var(--warning)]"
                              : "text-[var(--success)]"
                          }`}
                        >
                          {Math.round(unit.ocr_confidence)}% OCR confidence
                        </span>
                      )}

                      {hasText && (
                        <button
                          type="button"
                          onClick={() => handleCopy(unit.id, unit.text)}
                          className="flex items-center gap-1 text-[11px] text-[var(--text-muted)] hover:text-[var(--text)]"
                          title="Copy page text"
                        >
                          {copiedUnitId === unit.id ? (
                            <>
                              <Check className="size-3 text-[var(--success)]" />
                              <span className="text-[var(--success)]">Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy className="size-3" />
                              <span>Copy</span>
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* OCR Warning */}
                  {unit.ocr_needs_review && (
                    <div className="flex items-center gap-2 rounded bg-[var(--warning)]/10 px-2.5 py-1.5 text-[11px] text-[var(--warning)]">
                      <AlertTriangle className="size-3.5 shrink-0" />
                      <span>Low OCR confidence on this page. Verify text against the original filing.</span>
                    </div>
                  )}

                  {/* Extracted Text Content */}
                  <div className="font-serif text-[13px] leading-relaxed text-[var(--text)] whitespace-pre-wrap selection:bg-[var(--primary-tint)]">
                    {hasText ? (
                      isTargeted && target.start !== null && target.end !== null && target.start >= 0 && target.end <= unit.text.length && target.end > target.start ? (
                        <>
                          {unit.text.slice(0, target.start)}
                          <mark className="bg-[var(--brass)]/30 text-[var(--text)] rounded px-0.5 font-medium">
                            {unit.text.slice(target.start, target.end)}
                          </mark>
                          {unit.text.slice(target.end)}
                        </>
                      ) : (
                        unit.text
                      )
                    ) : (
                      <span className="italic text-[var(--text-faint)]">[No readable text detected on this page]</span>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}
