import { CheckCircle2, AlertTriangle, AlertCircle, Clock } from "lucide-react";

export function StatusPill({ status }: { status: string }) {
  const normalized = status.toLowerCase();

  let icon = <Clock className="size-3" />;
  let className = "status-pill status-pill-neutral";

  if (["processed", "ready", "complete"].includes(normalized)) {
    icon = <CheckCircle2 className="size-3" />;
    className = "status-pill status-pill-ready";
  } else if (["needs_review", "partially_read", "warning", "stale"].includes(normalized)) {
    icon = <AlertTriangle className="size-3" />;
    className = "status-pill status-pill-warning";
  } else if (["failed", "unreadable", "danger"].includes(normalized)) {
    icon = <AlertCircle className="size-3" />;
    className = "status-pill status-pill-danger";
  }

  const label = status.replaceAll("_", " ");

  return (
    <span className={className}>
      {icon}
      <span>{label}</span>
    </span>
  );
}
