"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Calendar as CalendarIcon,
  Plus,
  CheckCircle2,
  Circle,
  MoreHorizontal,
  Trash2,
  Clock,
  X,
} from "lucide-react";
import {
  CaseDeadline,
  createCaseDeadline,
  deleteCaseDeadline,
  listCaseDeadlines,
  updateCaseDeadline,
} from "@/lib/api";
import { PageShell, PageHeader, PageToolbar, PageBody, PageFootnote } from "@/components/domain/page-shell";
import { StatusDot } from "@/components/domain/status-dot";
import { EmptyState } from "@/components/domain/empty-state";
import { InlineAlert } from "@/components/domain/inline-alert";

export function CaseDeadlineAgenda({ caseId }: { caseId: string }) {
  const [items, setItems] = useState<CaseDeadline[]>([]);
  const [title, setTitle] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addDrawerOpen, setAddDrawerOpen] = useState(false);

  const refresh = useCallback(async () => {
    setItems(await listCaseDeadlines(caseId));
  }, [caseId]);

  useEffect(() => {
    let active = true;
    void listCaseDeadlines(caseId)
      .then((result) => {
        if (active) setItems(result);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Could not load dates.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [caseId]);

  async function handleAddDate(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() || !dueDate) return;

    setSaving(true);
    setError(null);
    try {
      await createCaseDeadline(caseId, {
        title: title.trim(),
        due_date: dueDate,
        note: note.trim() || undefined,
      });
      setTitle("");
      setDueDate("");
      setNote("");
      setAddDrawerOpen(false);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save date.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleStatus(item: CaseDeadline) {
    try {
      await updateCaseDeadline(caseId, item.id, {
        status: item.status === "open" ? "complete" : "open",
      });
      await refresh();
    } catch {
      alert("Could not update date status.");
    }
  }

  async function removeItem(id: string) {
    if (!confirm("Permanently remove this date from the agenda?")) return;
    try {
      await deleteCaseDeadline(caseId, id);
      await refresh();
    } catch {
      alert("Could not delete date.");
    }
  }

  // Group dates by Month (e.g. October 2026, November 2026)
  const groupedDates = useMemo(() => {
    const groups: Record<string, CaseDeadline[]> = {};
    const sorted = [...items].sort((a, b) => new Date(a.due_date).getTime() - new Date(b.due_date).getTime());

    sorted.forEach((item) => {
      const d = new Date(item.due_date);
      const monthKey = isNaN(d.getTime())
        ? "Other"
        : d.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
      if (!groups[monthKey]) groups[monthKey] = [];
      groups[monthKey].push(item);
    });

    return groups;
  }, [items]);

  return (
    <PageShell>
      {/* 1. Header */}
      <PageHeader
        title="Dates agenda"
        description="Track upcoming hearings, filing dates, and proceedings."
        actions={
          <button
            type="button"
            onClick={() => setAddDrawerOpen(true)}
            className="btn-primary"
          >
            <Plus className="size-4" />
            <span>Add date</span>
          </button>
        }
      />

      {error && (
        <InlineAlert type="error" message={error} />
      )}

      {/* 2. Body */}
      <PageBody>
        {items.length === 0 ? (
          <EmptyState
            icon={CalendarIcon}
            title="No dates scheduled"
            description="Add important hearing dates, written submission deadlines, and case milestones."
            action={
              <button
                type="button"
                onClick={() => setAddDrawerOpen(true)}
                className="btn-primary"
              >
                <Plus className="size-4" />
                <span>Add date</span>
              </button>
            }
          />
        ) : (
          <div className="space-y-6">
            {Object.entries(groupedDates).map(([monthYear, monthItems]) => (
              <div key={monthYear} className="space-y-2">
                <h3 className="font-semibold text-xs text-[var(--text-muted)] uppercase tracking-wider pl-1">
                  {monthYear}
                </h3>

                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] divide-y divide-[var(--border)]">
                  {monthItems.map((item) => {
                    const d = new Date(item.due_date);
                    const dayNum = isNaN(d.getTime()) ? "—" : d.getDate();
                    const monthShort = isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-IN", { month: "short" });
                    const isComplete = item.status === "complete";

                    return (
                      <div
                        key={item.id}
                        className="flex items-center justify-between p-3.5 text-xs hover:bg-[var(--surface-2)]/40 transition"
                      >
                        <div className="flex items-center gap-3.5 min-w-0">
                          {/* Date Block: Day number 20px, month 12px muted */}
                          <div className="grid size-11 place-items-center rounded-md border border-[var(--border)] bg-[var(--surface-2)] shrink-0 text-center leading-none">
                            <span className="font-semibold text-lg text-[var(--text)]">{dayNum}</span>
                            <span className="text-[10px] text-[var(--text-muted)] uppercase">{monthShort}</span>
                          </div>

                          <div className="space-y-0.5 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className={`font-medium text-sm text-[var(--text)] ${isComplete ? "line-through opacity-60" : ""}`}>
                                {item.title}
                              </span>
                            </div>
                            {item.note && (
                              <p className="text-[11px] text-[var(--text-muted)] truncate">{item.note}</p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            type="button"
                            onClick={() => toggleStatus(item)}
                            className="btn-ghost h-7 px-2 text-xs flex items-center gap-1 text-[var(--text-muted)]"
                          >
                            {isComplete ? (
                              <>
                                <CheckCircle2 className="size-3.5 text-[var(--success)]" />
                                <span>Complete</span>
                              </>
                            ) : (
                              <>
                                <Circle className="size-3.5" />
                                <span>Mark done</span>
                              </>
                            )}
                          </button>

                          <button
                            type="button"
                            onClick={() => removeItem(item.id)}
                            className="p-1 text-[var(--text-faint)] hover:text-[var(--danger)]"
                            title="Delete date"
                          >
                            <Trash2 className="size-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </PageBody>

      {/* 3. Footnote */}
      <PageFootnote>
        <span>Dates are entered manually. No deadlines or limitation periods are calculated automatically.</span>
      </PageFootnote>

      {/* Add Date Drawer / Modal */}
      {addDrawerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 shadow-[var(--shadow-drawer)]">
            <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
              <h2 className="font-serif text-base font-medium text-[var(--text)]">Add case date</h2>
              <button
                type="button"
                onClick={() => setAddDrawerOpen(false)}
                className="text-[var(--text-muted)] hover:text-[var(--text)] p-1"
              >
                <X className="size-4" />
              </button>
            </div>

            <form onSubmit={handleAddDate} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-[var(--text)]">
                  Event / Deadline Title <span className="text-[var(--danger)]">*</span>
                </label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Next hearing for final arguments"
                  className="input-field mt-1 w-full"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[var(--text)]">
                  Date <span className="text-[var(--danger)]">*</span>
                </label>
                <input
                  type="date"
                  required
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="input-field mt-1 w-full"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[var(--text)]">
                  Notes / Location <span className="text-[var(--text-faint)] font-normal">(optional)</span>
                </label>
                <textarea
                  rows={2}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="Court hall number or advocate preparation notes…"
                  className="input-field h-auto mt-1 w-full p-2 text-xs"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[var(--border)]">
                <button
                  type="button"
                  onClick={() => setAddDrawerOpen(false)}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !title.trim() || !dueDate}
                  className="btn-primary"
                >
                  {saving ? "Saving…" : "Add date"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </PageShell>
  );
}
