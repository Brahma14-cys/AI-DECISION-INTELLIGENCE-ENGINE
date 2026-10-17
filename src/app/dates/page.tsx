"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CalendarDays, Scale, Calendar as CalendarIcon } from "lucide-react";
import { listCases, CaseRecord } from "@/lib/api";
import { WorkspaceShell } from "@/app/workspace-shell";
import { PageShell, PageHeader, PageBody, PageFootnote } from "@/components/domain/page-shell";
import { EmptyState } from "@/components/domain/empty-state";
import { formatDate } from "@/lib/formatters";

export default function DatesAgendaPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listCases()
      .then(setCases)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const casesWithDates = cases.filter((c) => c.next_hearing_date);

  return (
    <WorkspaceShell active="dates">
      <PageShell>
        <PageHeader
          title="Dates agenda"
          description="Aggregated hearing dates across all active chambers matters."
        />

        <PageBody>
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((n) => (
                <div key={n} className="h-14 w-full animate-pulse rounded bg-[var(--surface)] border border-[var(--border)]" />
              ))}
            </div>
          ) : casesWithDates.length === 0 ? (
            <EmptyState
              icon={CalendarDays}
              title="No hearing dates scheduled"
              description="Assign hearing dates within individual case workspaces to view them aggregated here."
            />
          ) : (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
              {casesWithDates.map((c) => {
                const hearingDate = new Date(c.next_hearing_date!);
                const dayNum = isNaN(hearingDate.getTime()) ? "—" : hearingDate.getDate();
                const monthShort = isNaN(hearingDate.getTime()) ? "" : hearingDate.toLocaleDateString("en-IN", { month: "short" });

                return (
                  <div
                    key={c.id}
                    className="flex items-center justify-between p-4 text-xs hover:bg-[var(--surface-2)]/40 transition"
                  >
                    <div className="flex items-center gap-3.5 min-w-0">
                      <div className="grid size-11 place-items-center rounded-md border border-[var(--border)] bg-[var(--surface-2)] shrink-0 text-center leading-none">
                        <span className="font-semibold text-lg text-[var(--text)]">{dayNum}</span>
                        <span className="text-[10px] text-[var(--text-muted)] uppercase">{monthShort}</span>
                      </div>
                      <div className="min-w-0">
                        <Link
                          href={`/cases/${c.id}?tab=dates`}
                          className="font-medium text-sm text-[var(--text)] hover:text-[var(--primary)] truncate block"
                        >
                          {c.title}
                        </Link>
                        <div className="mt-0.5 flex items-center gap-2 text-xs text-[var(--text-muted)]">
                          {c.court && <span>{c.court}</span>}
                          {c.client_reference && <span>· {c.client_reference}</span>}
                        </div>
                      </div>
                    </div>

                    <Link
                      href={`/cases/${c.id}?tab=dates`}
                      className="btn-ghost text-xs text-[var(--primary)] shrink-0"
                    >
                      Open matter →
                    </Link>
                  </div>
                );
              })}
            </div>
          )}
        </PageBody>

        <PageFootnote>
          <span>Dates are entered manually. No deadlines are calculated automatically.</span>
        </PageFootnote>
      </PageShell>
    </WorkspaceShell>
  );
}
