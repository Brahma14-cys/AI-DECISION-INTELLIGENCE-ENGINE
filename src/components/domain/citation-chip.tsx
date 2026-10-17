"use client";

import { FileText } from "lucide-react";
import { SourcePeekTarget } from "./source-peek-drawer";

export function CitationChip({
  caseId,
  documentId,
  filename,
  documentName,
  unitId,
  locator,
  start,
  end,
  quote,
}: SourcePeekTarget) {
  const resolvedFilename = filename || documentName;

  function handleClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    window.dispatchEvent(
      new CustomEvent<SourcePeekTarget>("legal-source-jump", {
        detail: { caseId, documentId: documentId || "", filename: resolvedFilename, unitId, locator, start, end, quote },
      })
    );
  }

  const label = [resolvedFilename, locator].filter(Boolean).join(" · ") || "Source";

  return (
    <button
      type="button"
      onClick={handleClick}
      title={quote ? `"${quote.slice(0, 100)}..."` : "Click to view source in context"}
      className="citation-chip inline-flex items-center gap-1.5 transition hover:scale-102"
    >
      <FileText className="size-3 shrink-0 text-[var(--accent)]" />
      <span className="truncate max-w-[200px]">{label}</span>
    </button>
  );
}
