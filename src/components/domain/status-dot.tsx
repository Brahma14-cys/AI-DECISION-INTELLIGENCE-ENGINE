export function StatusDot({
  status,
  className = "",
}: {
  status: string;
  className?: string;
}) {
  const s = status.toLowerCase();

  let dotColor = "bg-[var(--status-neutral)]";
  let text = "Not run";

  if (s === "completed" || s === "ready" || s === "processed") {
    dotColor = "bg-[var(--status-success)]";
    text = "Completed";
  } else if (s === "running" || s === "processing" || s === "queued" || s === "uploaded") {
    dotColor = "bg-[var(--status-warning)] animate-pulse";
    text = "Running";
  } else if (s === "needs_review" || s === "needs attention" || s === "partially_read") {
    dotColor = "bg-[var(--status-warning)]";
    text = "Needs attention";
  } else if (s === "failed" || s === "unreadable") {
    dotColor = "bg-[var(--status-danger)]";
    text = "Failed";
  } else if (s === "stale") {
    dotColor = "bg-[var(--status-warning)]";
    text = "Stale";
  } else {
    text = status.replaceAll("_", " ");
  }

  return (
    <span className={`inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)] ${className}`}>
      <span className={`size-2 rounded-full shrink-0 ${dotColor}`} />
      <span className="capitalize">{text}</span>
    </span>
  );
}
