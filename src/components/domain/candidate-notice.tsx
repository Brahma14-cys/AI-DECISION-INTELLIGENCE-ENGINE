import { ShieldAlert } from "lucide-react";

export function CandidateNotice() {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-[var(--accent)]/30 bg-[var(--accent-soft)]/20 p-3.5 text-xs text-[var(--text)]">
      <ShieldAlert className="size-4 shrink-0 text-[var(--accent-strong)] mt-0.5" />
      <div className="leading-relaxed">
        <strong className="font-semibold text-[var(--text)]">Candidate Authorities Notice: </strong>
        <span className="text-[var(--text-muted)]">
          Search results and suggested statutory provisions are candidate authorities for your review. Always independently verify current statutory amendments, jurisdictional applicability, and precedential status before citing.
        </span>
      </div>
    </div>
  );
}
