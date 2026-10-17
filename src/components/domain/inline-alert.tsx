"use client";

import { useState } from "react";
import { AlertCircle, AlertTriangle, Info, ChevronDown, ChevronUp } from "lucide-react";

export function InlineAlert({
  type = "error",
  message,
  technicalDetails,
  action,
}: {
  type?: "error" | "warning" | "info";
  message: string;
  technicalDetails?: string | null;
  action?: React.ReactNode;
}) {
  const [showDetails, setShowDetails] = useState(false);

  const isError = type === "error";
  const isWarning = type === "warning";

  const borderColor = isError
    ? "border-l-[var(--status-danger)]"
    : isWarning
    ? "border-l-[var(--status-warning)]"
    : "border-l-[var(--accent)]";

  const Icon = isError ? AlertCircle : isWarning ? AlertTriangle : Info;
  const iconColor = isError
    ? "text-[var(--status-danger)]"
    : isWarning
    ? "text-[var(--status-warning)]"
    : "text-[var(--accent)]";

  return (
    <div className={`rounded-md border border-[var(--border)] bg-[var(--surface)] p-3 text-xs border-l-4 ${borderColor}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          <Icon className={`size-4 shrink-0 mt-0.5 ${iconColor}`} />
          <div className="min-w-0">
            <p className="text-[var(--text)] font-medium leading-relaxed">{message}</p>
            {technicalDetails && (
              <button
                type="button"
                onClick={() => setShowDetails(!showDetails)}
                className="mt-1 inline-flex items-center gap-1 text-[11px] text-[var(--text-muted)] hover:text-[var(--text)] underline"
              >
                <span>{showDetails ? "Hide details" : "Show details"}</span>
                {showDetails ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
              </button>
            )}
          </div>
        </div>

        {action && <div className="shrink-0">{action}</div>}
      </div>

      {showDetails && technicalDetails && (
        <div className="mt-2.5 rounded bg-[var(--sidebar)] p-2.5 font-mono text-[11px] text-[var(--text-muted)] break-all border border-[var(--border)]">
          {technicalDetails}
        </div>
      )}
    </div>
  );
}
