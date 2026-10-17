import { AlertTriangle, CheckCircle2 } from "lucide-react";

export function ConfidenceMeter({
  confidence,
  threshold = 70,
  needsReview = false,
}: {
  confidence: number | null;
  threshold?: number;
  needsReview?: boolean;
}) {
  if (confidence === null || confidence === undefined) {
    return <span className="text-[11px] text-[var(--text-faint)] italic">Direct PDF stream</span>;
  }

  const rounded = Math.round(confidence);
  const isLow = rounded < threshold || needsReview;

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--surface-3)]">
        <div
          style={{ width: `${Math.min(100, Math.max(0, rounded))}%` }}
          className={`h-full rounded-full transition-all duration-300 ${
            isLow ? "bg-[var(--status-warning)]" : "bg-[var(--status-success)]"
          }`}
        />
      </div>
      <span className="font-mono text-[11px] text-[var(--text-muted)]">{rounded}%</span>
      {isLow && (
        <span className="inline-flex items-center gap-1 rounded bg-[var(--status-warning-bg)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--status-warning)]">
          <AlertTriangle className="size-2.5" /> Needs review
        </span>
      )}
    </div>
  );
}
