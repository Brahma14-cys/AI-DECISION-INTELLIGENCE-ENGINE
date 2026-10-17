"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Plus,
  Search,
  LayoutGrid,
  List,
  Scale,
  MoreHorizontal,
  Trash2,
  ExternalLink,
  X,
  CheckCircle2,
} from "lucide-react";
import { CaseRecord, createCase, deleteCase, getAdvocateSession, listCases, ApiRequestError } from "@/lib/api";
import { WorkspaceShell } from "@/app/workspace-shell";
import { StatusDot } from "@/components/domain/status-dot";
import { EmptyState } from "@/components/domain/empty-state";
import { PageShell, PageHeader, PageToolbar, PageBody } from "@/components/domain/page-shell";
import { formatDate } from "@/lib/formatters";

export default function CasesPage() {
  const router = useRouter();
  const [cases, setCases] = useState<CaseRecord[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const [query, setQuery] = useState("");
  const [stageFilter, setStageFilter] = useState("all");
  const [sortMode, setSortMode] = useState<"updated" | "name" | "created">("updated");
  const [viewMode, setViewMode] = useState<"table" | "cards">("table");

  // Row menu state
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);

  // New Case Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newRef, setNewRef] = useState("");
  const [newType, setNewType] = useState("Civil suit");
  const [newCourt, setNewCourt] = useState("");
  const [newJurisdiction, setNewJurisdiction] = useState("");
  const [newStage, setNewStage] = useState("Intake");

  // Delete modal state
  const [caseToDelete, setCaseToDelete] = useState<CaseRecord | null>(null);
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showDeletePassword, setShowDeletePassword] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const storedFeedback = sessionStorage.getItem("case_deleted_feedback");
      if (storedFeedback) {
        setFeedbackMessage({ type: "success", text: storedFeedback });
        sessionStorage.removeItem("case_deleted_feedback");
      }
    } catch {
      // sessionStorage unavailable
    }
  }, []);

  useEffect(() => {
    let active = true;
    getAdvocateSession()
      .then(() => listCases())
      .then((data) => {
        if (active) setCases(data);
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiRequestError && err.status === 401) {
          router.replace("/signin");
        } else {
          setError(err instanceof Error ? err.message : "Failed to load cases.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [router]);

  async function handleCreateCase(e: React.FormEvent) {
    e.preventDefault();
    if (!newTitle.trim()) return;

    setCreating(true);
    setCreateError(null);
    try {
      const created = await createCase({
        title: newTitle.trim(),
        client_reference: newRef.trim() || undefined,
        case_type: newType || undefined,
        court: newCourt.trim() || undefined,
        jurisdiction: newJurisdiction.trim() || undefined,
        stage: newStage || undefined,
      });
      setCases((prev) => (prev ? [created, ...prev] : [created]));
      setDrawerOpen(false);
      // Reset form
      setNewTitle("");
      setNewRef("");
      setNewCourt("");
      setNewJurisdiction("");
      setNewStage("Intake");
      router.push(`/cases/${created.id}`);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create case.");
    } finally {
      setCreating(false);
    }
  }

  async function handleDeleteConfirm() {
    if (!caseToDelete) return;
    const input = confirmPassword.trim();
    if (!input) {
      setDeleteError("Please enter your advocate password to confirm deletion.");
      return;
    }

    setDeleting(true);
    setDeleteError(null);
    const deletedTitle = caseToDelete.title;
    try {
      await deleteCase(caseToDelete.id);
      setCases((prev) => prev?.filter((c) => c.id !== caseToDelete.id) ?? null);
      setCaseToDelete(null);
      setConfirmPassword("");
      setShowDeletePassword(false);
      setFeedbackMessage({
        type: "success",
        text: `Case "${deletedTitle}" was permanently deleted.`,
      });
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete case.");
    } finally {
      setDeleting(false);
    }
  }

  const filteredCases = useMemo(() => {
    if (!cases) return [];
    return cases
      .filter((c) => {
        const q = query.trim().toLowerCase();
        const matchesQuery =
          !q ||
          c.title.toLowerCase().includes(q) ||
          (c.client_reference && c.client_reference.toLowerCase().includes(q)) ||
          (c.court && c.court.toLowerCase().includes(q)) ||
          (c.case_type && c.case_type.toLowerCase().includes(q));

        const matchesStage = stageFilter === "all" || (c.stage && c.stage.toLowerCase() === stageFilter.toLowerCase());
        return matchesQuery && matchesStage;
      })
      .sort((a, b) => {
        if (sortMode === "name") return a.title.localeCompare(b.title);
        if (sortMode === "created") return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        return new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime();
      });
  }, [cases, query, stageFilter, sortMode]);

  return (
    <WorkspaceShell active="cases">
      <PageShell>
        {/* Page Header */}
        <PageHeader
          title="Cases"
          badge={
            cases ? (
              <span className="text-xs text-[var(--text-muted)] font-mono ml-1">
                {cases.length}
              </span>
            ) : null
          }
          actions={
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="btn-primary"
            >
              <Plus className="size-4" />
              <span>New case</span>
            </button>
          }
        />

        {feedbackMessage && (
          <div
            role="alert"
            className={`mb-4 flex items-center justify-between gap-3 rounded-lg border px-4 py-3 text-xs animate-in fade-in slide-in-from-top-1 duration-200 ${
              feedbackMessage.type === "success"
                ? "border-[var(--emerald)]/30 bg-[var(--emerald)]/10 text-[var(--emerald)]"
                : "border-[var(--danger)]/30 bg-[var(--danger)]/10 text-[var(--danger)]"
            }`}
          >
            <div className="flex items-center gap-2 font-medium">
              <CheckCircle2 className="size-4 shrink-0" />
              <span>{feedbackMessage.text}</span>
            </div>
            <button
              type="button"
              onClick={() => setFeedbackMessage(null)}
              className="text-current opacity-70 hover:opacity-100 p-0.5 rounded transition"
              aria-label="Dismiss message"
            >
              <X className="size-3.5" />
            </button>
          </div>
        )}

        {/* Page Toolbar: Search, Filters & View Switcher (All 36px, 14px text) */}
        <PageToolbar>
          <div className="relative flex-1 min-w-[260px] max-w-md">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[var(--text-faint)] pointer-events-none" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search cases…"
              className="input-field w-full pl-10"
            />
          </div>

          <div className="flex items-center gap-2">
            <select
              value={stageFilter}
              onChange={(e) => setStageFilter(e.target.value)}
              className="input-field text-xs text-[var(--text-muted)] cursor-pointer"
            >
              <option value="all">All stages</option>
              <option value="Intake">Intake</option>
              <option value="Filed">Filed</option>
              <option value="Pleadings">Pleadings</option>
              <option value="Evidence">Evidence</option>
              <option value="Arguments">Arguments</option>
              <option value="Judgment reserved">Judgment reserved</option>
              <option value="Appeal">Appeal</option>
            </select>

            <select
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value as any)}
              className="input-field text-xs text-[var(--text-muted)] cursor-pointer"
            >
              <option value="updated">Recently updated</option>
              <option value="name">Name (A-Z)</option>
              <option value="created">Created date</option>
            </select>

            {/* Segmented list/grid control */}
            <div className="flex items-center rounded-md border border-[var(--border)] p-0.5 h-9">
              <button
                type="button"
                onClick={() => setViewMode("table")}
                className={`rounded px-2.5 py-1 text-xs transition ${
                  viewMode === "table"
                    ? "bg-[var(--surface-2)] text-[var(--text)] font-medium"
                    : "text-[var(--text-muted)]"
                }`}
                title="List view"
              >
                <List className="size-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setViewMode("cards")}
                className={`rounded px-2.5 py-1 text-xs transition ${
                  viewMode === "cards"
                    ? "bg-[var(--surface-2)] text-[var(--text)] font-medium"
                    : "text-[var(--text-muted)]"
                }`}
                title="Grid view"
              >
                <LayoutGrid className="size-3.5" />
              </button>
            </div>
          </div>
        </PageToolbar>

        {/* Page Body */}
        <PageBody>
          {loading && (
            <div className="space-y-2">
              {[1, 2, 3, 4].map((n) => (
                <div key={n} className="h-14 w-full animate-pulse rounded bg-[var(--surface)] border border-[var(--border)]" />
              ))}
            </div>
          )}

          {error && (
            <div className="rounded-md border border-[var(--danger)]/30 bg-[var(--surface)] p-4 text-xs text-[var(--danger)]">
              <p className="font-semibold">Could not load cases</p>
              <p className="mt-1">{error}</p>
            </div>
          )}

          {!loading && !error && filteredCases.length === 0 && cases?.length === 0 && (
            <EmptyState
              icon={Scale}
              title="No cases yet"
              description="Create your first case to start organising documents, extracting facts, and running structured legal analysis."
              action={
                <button
                  type="button"
                  onClick={() => setDrawerOpen(true)}
                  className="btn-primary"
                >
                  <Plus className="size-4" />
                  <span>New case</span>
                </button>
              }
            />
          )}

          {!loading && !error && filteredCases.length === 0 && (cases?.length ?? 0) > 0 && (
            <div className="py-12 text-center text-xs text-[var(--text-muted)]">
              No matching cases.{" "}
              <button
                type="button"
                onClick={() => { setQuery(""); setStageFilter("all"); }}
                className="text-[var(--primary)] font-medium hover:underline"
              >
                Clear filters
              </button>
            </div>
          )}

          {/* Table View (List) */}
          {!loading && !error && viewMode === "table" && filteredCases.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--surface)]">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-[var(--border)] text-xs text-[var(--text-muted)] font-medium bg-[var(--surface-2)]">
                  <tr>
                    <th className="py-2.5 px-4 font-medium">Case</th>
                    <th className="py-2.5 px-4 font-medium">Stage</th>
                    <th className="py-2.5 px-4 font-medium">Analysis</th>
                    <th className="py-2.5 px-4 font-medium">Next hearing</th>
                    <th className="py-2.5 px-4 text-right font-medium"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {filteredCases.map((c) => {
                    const metaParts = [c.case_type, c.court].filter(Boolean);
                    const isIntake = !c.stage || c.stage.toLowerCase() === "intake";

                    return (
                      <tr
                        key={c.id}
                        onClick={() => router.push(`/cases/${c.id}`)}
                        className="group h-[52px] cursor-pointer transition hover:bg-[var(--surface-2)]"
                      >
                        {/* Case column: Name + Meta line */}
                        <td className="py-2 px-4">
                          <div className="font-medium text-[var(--text)] group-hover:text-[var(--primary)]">
                            {c.title}
                          </div>
                          <div className="text-xs text-[var(--text-muted)] flex items-center gap-1.5 mt-0.5">
                            {metaParts.length > 0 && <span>{metaParts.join(" · ")}</span>}
                            {c.client_reference && (
                              <>
                                {metaParts.length > 0 && <span>·</span>}
                                <span className="font-mono text-[11px] text-[var(--text-faint)]">{c.client_reference}</span>
                              </>
                            )}
                          </div>
                        </td>

                        {/* Stage column */}
                        <td className="py-2 px-4 text-xs">
                          {isIntake ? (
                            <span className="text-[var(--text-faint)]">Intake</span>
                          ) : (
                            <span className="text-[var(--text)] flex items-center gap-1.5">
                              <span className="size-1.5 rounded-full bg-[var(--text-muted)]" />
                              <span>{c.stage}</span>
                            </span>
                          )}
                        </td>

                        {/* Analysis column */}
                        <td className="py-2 px-4">
                          <StatusDot status={c.analysis_status || "Not started"} />
                        </td>

                        {/* Next hearing date */}
                        <td className="py-2 px-4 font-mono text-xs text-[var(--text-muted)]">
                          {c.next_hearing_date ? formatDate(c.next_hearing_date) : ""}
                        </td>

                        {/* Row Menu */}
                        <td className="py-2 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                          <div className="relative inline-block text-left">
                            <button
                              type="button"
                              onClick={() => setActiveMenuId(activeMenuId === c.id ? null : c.id)}
                              className="p-1 rounded text-[var(--text-faint)] hover:text-[var(--text)] opacity-0 group-hover:opacity-100 transition"
                              title="Case actions"
                            >
                              <MoreHorizontal className="size-4" />
                            </button>

                            {activeMenuId === c.id && (
                              <div className="absolute right-0 mt-1 w-32 rounded-md border border-[var(--border)] bg-[var(--surface)] p-1 shadow-[var(--shadow-drawer)] z-30 text-xs">
                                <Link
                                  href={`/cases/${c.id}`}
                                  className="flex items-center gap-2 rounded px-2 py-1.5 text-[var(--text)] hover:bg-[var(--surface-2)]"
                                >
                                  <span>Open</span>
                                </Link>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setActiveMenuId(null);
                                    setCaseToDelete(c);
                                  }}
                                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-[var(--danger)] hover:bg-[var(--surface-2)] text-left"
                                >
                                  <span>Delete</span>
                                </button>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Grid View (Cards) */}
          {!loading && !error && viewMode === "cards" && filteredCases.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filteredCases.map((c) => {
                const metaParts = [c.case_type, c.court].filter(Boolean);
                return (
                  <div
                    key={c.id}
                    onClick={() => router.push(`/cases/${c.id}`)}
                    className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 cursor-pointer transition hover:border-[var(--brass)] hover:bg-[var(--surface-2)]"
                  >
                    <div className="font-medium text-sm text-[var(--text)] line-clamp-1">
                      {c.title}
                    </div>
                    <div className="mt-1 text-xs text-[var(--text-muted)] line-clamp-1">
                      {metaParts.join(" · ") || c.client_reference || "Matter"}
                    </div>

                    <div className="mt-4 flex items-center justify-between border-t border-[var(--border)] pt-3 text-xs">
                      <StatusDot status={c.analysis_status || "Not started"} />
                      <span className="font-mono text-[11px] text-[var(--text-muted)]">
                        {c.next_hearing_date ? formatDate(c.next_hearing_date, true) : ""}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </PageBody>
      </PageShell>

      {/* New Case Drawer (Right Side, 440px) */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/40">
          <div className="flex h-full w-full max-w-[440px] flex-col border-l border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-drawer)]">
            {/* Drawer Header */}
            <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
              <h2 className="font-serif text-lg font-medium text-[var(--text)]">New case</h2>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                className="text-[var(--text-muted)] hover:text-[var(--text)] p-1"
              >
                <X className="size-4" />
              </button>
            </div>

            {/* Drawer Form Body */}
            <form onSubmit={handleCreateCase} className="flex flex-1 flex-col justify-between overflow-y-auto p-6">
              <div className="space-y-6">
                {createError && (
                  <div className="rounded-md border border-[var(--danger)]/30 bg-[var(--surface-2)] p-3 text-xs text-[var(--danger)]">
                    {createError}
                  </div>
                )}

                {/* Group 1: Case Details */}
                <div className="space-y-4">
                  <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                    Case Details
                  </h3>

                  <div>
                    <label htmlFor="drawer_title" className="block text-xs font-medium text-[var(--text)]">
                      Case title / Parties <span className="text-[var(--danger)]">*</span>
                    </label>
                    <input
                      id="drawer_title"
                      type="text"
                      required
                      autoFocus
                      value={newTitle}
                      onChange={(e) => setNewTitle(e.target.value)}
                      placeholder="e.g. Vijaya Reddy v. State of AP & Ors."
                      className="input-field mt-1 w-full"
                    />
                  </div>

                  <div>
                    <label htmlFor="drawer_ref" className="block text-xs font-medium text-[var(--text)]">
                      Client reference <span className="text-[var(--text-faint)] font-normal">(optional)</span>
                    </label>
                    <input
                      id="drawer_ref"
                      type="text"
                      value={newRef}
                      onChange={(e) => setNewRef(e.target.value)}
                      placeholder="e.g. CHAMBERS-2026-VR"
                      className="input-field font-mono text-xs mt-1 w-full"
                    />
                  </div>
                </div>

                {/* Group 2: Forum & Stage */}
                <div className="space-y-4 pt-2 border-t border-[var(--border)]">
                  <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                    Forum & Stage
                  </h3>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label htmlFor="drawer_type" className="block text-xs font-medium text-[var(--text)]">
                        Matter type
                      </label>
                      <select
                        id="drawer_type"
                        value={newType}
                        onChange={(e) => setNewType(e.target.value)}
                        className="input-field mt-1 w-full text-xs"
                      >
                        <option value="Civil suit">Civil suit</option>
                        <option value="Writ petition">Writ petition</option>
                        <option value="Commercial suit">Commercial suit</option>
                        <option value="Arbitration">Arbitration</option>
                        <option value="Criminal appeal">Criminal appeal</option>
                        <option value="Special leave petition">SLP</option>
                      </select>
                    </div>

                    <div>
                      <label htmlFor="drawer_stage" className="block text-xs font-medium text-[var(--text)]">
                        Proceeding stage
                      </label>
                      <select
                        id="drawer_stage"
                        value={newStage}
                        onChange={(e) => setNewStage(e.target.value)}
                        className="input-field mt-1 w-full text-xs"
                      >
                        <option value="Intake">Intake</option>
                        <option value="Filed">Filed</option>
                        <option value="Pleadings">Pleadings</option>
                        <option value="Evidence">Evidence</option>
                        <option value="Arguments">Arguments</option>
                        <option value="Judgment reserved">Judgment reserved</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label htmlFor="drawer_court" className="block text-xs font-medium text-[var(--text)]">
                      Court / Tribunal <span className="text-[var(--text-faint)] font-normal">(optional)</span>
                    </label>
                    <input
                      id="drawer_court"
                      type="text"
                      value={newCourt}
                      onChange={(e) => setNewCourt(e.target.value)}
                      placeholder="e.g. High Court of Judicature at Hyderabad"
                      className="input-field mt-1 w-full"
                    />
                  </div>

                  <div>
                    <label htmlFor="drawer_jurisdiction" className="block text-xs font-medium text-[var(--text)]">
                      Jurisdiction <span className="text-[var(--text-faint)] font-normal">(optional)</span>
                    </label>
                    <input
                      id="drawer_jurisdiction"
                      type="text"
                      value={newJurisdiction}
                      onChange={(e) => setNewJurisdiction(e.target.value)}
                      placeholder="e.g. Original Jurisdiction"
                      className="input-field mt-1 w-full"
                    />
                  </div>
                </div>
              </div>

              {/* Drawer Footer Actions */}
              <div className="flex items-center justify-end gap-2.5 pt-6 border-t border-[var(--border)]">
                <button
                  type="button"
                  onClick={() => setDrawerOpen(false)}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating || !newTitle.trim()}
                  className="btn-primary"
                >
                  {creating ? "Creating…" : "Create case"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {caseToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-[1px]">
          <div className="w-full max-w-md rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 shadow-[var(--shadow-drawer)]">
            <h2 className="text-sm font-semibold text-[var(--text)]">Delete case &ldquo;{caseToDelete.title}&rdquo;</h2>
            <p className="mt-2 text-xs leading-relaxed text-[var(--text-muted)]">
              This action cannot be undone. All documents, OCR extractions, knowledge graphs, and advocate notes will be permanently removed.
            </p>
            <p className="mt-4 text-xs font-medium text-[var(--text)]">
              Enter your advocate password to confirm deletion:
            </p>

            <div className="relative mt-1.5">
              <input
                type={showDeletePassword ? "text" : "password"}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !deleting) {
                    e.preventDefault();
                    void handleDeleteConfirm();
                  }
                }}
                placeholder="Enter password (e.g. 12345678)"
                className="input-field text-xs w-full pr-14"
                autoFocus
              />
              <button
                type="button"
                onClick={() => setShowDeletePassword((v) => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[11px] font-medium text-[var(--text-faint)] hover:text-[var(--text)]"
              >
                {showDeletePassword ? "Hide" : "Show"}
              </button>
            </div>

            {deleteError && <p className="mt-2 text-xs text-[var(--danger)]">{deleteError}</p>}

            <div className="mt-6 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => { setCaseToDelete(null); setConfirmPassword(""); setShowDeletePassword(false); setDeleteError(null); }}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleting || !confirmPassword.trim()}
                onClick={handleDeleteConfirm}
                className="btn-destructive"
              >
                {deleting ? "Deleting…" : "Delete case"}
              </button>
            </div>
          </div>
        </div>
      )}
    </WorkspaceShell>
  );
}
