"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Edit3, ChevronLeft, Trash2, X } from "lucide-react";
import {
  CaseAnalysisAvailability,
  CaseDocument,
  CaseRecord,
  deleteCase,
  getAnalysisAvailability,
  getCase,
  listDocuments,
  updateCase,
  ApiRequestError,
} from "@/lib/api";
import { WorkspaceShell, WorkspaceModuleId } from "@/app/workspace-shell";
import { StatusDot } from "@/components/domain/status-dot";

// Sub-panel tabs
import { CaseOverviewTab } from "./case-overview-tab";
import { CaseDocumentsTab } from "./case-documents-tab";
import { CaseAnalysisPanel } from "./case-analysis-panel";
import { CaseKnowledgeGraphPanel } from "./case-knowledge-graph-panel";
import { CaseLegalResearchPanel } from "./case-legal-research-panel";
import { CaseChatPanel } from "./case-chat-panel";
import { CaseSummaryPanel } from "./case-summary-panel";
import { CaseDecisionSupportPanel } from "./case-decision-support-panel";
import { CaseDeadlineAgenda } from "./case-deadline-agenda";

export default function CaseWorkspacePage() {
  const params = useParams<{ caseId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const caseId = params.caseId;

  const [caseFile, setCaseFile] = useState<CaseRecord | null>(null);
  const [documents, setDocuments] = useState<CaseDocument[]>([]);
  const [availability, setAvailability] = useState<CaseAnalysisAvailability | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Tab management (activeModule driven by URL or state)
  const initialTab = (searchParams.get("tab") as WorkspaceModuleId) || "overview";
  const [activeTab, setActiveTab] = useState<WorkspaceModuleId>(initialTab);

  // Edit details modal
  const [editingDetails, setEditingDetails] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editRef, setEditRef] = useState("");
  const [editCourt, setEditCourt] = useState("");
  const [editJurisdiction, setEditJurisdiction] = useState("");
  const [editStage, setEditStage] = useState("");
  const [savingDetails, setSavingDetails] = useState(false);

  // Delete case state
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [confirmDeletePassword, setConfirmDeletePassword] = useState("");
  const [showDeletePassword, setShowDeletePassword] = useState(false);
  const [deletingCase, setDeletingCase] = useState(false);
  const [deleteCaseError, setDeleteCaseError] = useState<string | null>(null);

  async function handleDeleteCase() {
    if (!caseFile) return;
    const input = confirmDeletePassword.trim();
    if (!input) {
      setDeleteCaseError("Please enter your advocate password to confirm deletion.");
      return;
    }

    setDeletingCase(true);
    setDeleteCaseError(null);
    try {
      const deletedTitle = caseFile.title;
      await deleteCase(caseId);
      try {
        sessionStorage.setItem("case_deleted_feedback", `Case "${deletedTitle}" was permanently deleted.`);
      } catch {
        // sessionStorage unavailable
      }
      router.replace("/cases");
    } catch (err) {
      setDeleteCaseError(err instanceof Error ? err.message : "Failed to delete case.");
      setDeletingCase(false);
    }
  }

  const refreshData = useCallback(async () => {
    try {
      const [c, docs, avail] = await Promise.all([
        getCase(caseId),
        listDocuments(caseId),
        getAnalysisAvailability(caseId),
      ]);
      setCaseFile(c);
      setDocuments(docs);
      setAvailability(avail);
      setError(null);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 401) {
        router.replace("/signin");
      } else {
        setError(err instanceof Error ? err.message : "Failed to load case data.");
      }
    } finally {
      setLoading(false);
    }
  }, [caseId, router]);

  useEffect(() => {
    void refreshData();
  }, [refreshData]);

  // Active polling while any document or analysis is being processed
  useEffect(() => {
    const hasPendingDocs = documents.some((d) =>
      ["uploaded", "queued", "processing"].includes(d.processing_status)
    );
    const hasPendingAnalysis = ["queued", "processing"].includes(caseFile?.analysis_status || "");
    if (!hasPendingDocs && !hasPendingAnalysis) return;

    const interval = window.setInterval(() => {
      void refreshData();
    }, 2000);

    return () => window.clearInterval(interval);
  }, [documents, caseFile?.analysis_status, refreshData]);

  const [researchInitialQuery, setResearchInitialQuery] = useState<string>("");

  function handleTabChange(tab: WorkspaceModuleId, query?: string) {
    setActiveTab(tab);
    if (query) {
      setResearchInitialQuery(query);
    }
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    window.history.replaceState({}, "", url.toString());
  }

  async function handleSaveDetails(e: React.FormEvent) {
    e.preventDefault();
    setSavingDetails(true);
    try {
      const updated = await updateCase(caseId, {
        title: editTitle,
        client_reference: editRef || null,
        court: editCourt || null,
        jurisdiction: editJurisdiction || null,
        stage: editStage || null,
      });
      setCaseFile(updated);
      setEditingDetails(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update case details.");
    } finally {
      setSavingDetails(false);
    }
  }

  if (loading) {
    return (
      <WorkspaceShell active="case" caseWorkspace={true} caseId={caseId}>
        <div className="space-y-3 py-6">
          <div className="h-6 w-1/4 animate-pulse rounded bg-[var(--surface)] border border-[var(--border)]" />
          <div className="h-40 w-full animate-pulse rounded bg-[var(--surface)] border border-[var(--border)]" />
        </div>
      </WorkspaceShell>
    );
  }

  if (error || !caseFile) {
    return (
      <WorkspaceShell active="case" caseWorkspace={true} caseId={caseId}>
        <div className="py-12 text-center text-xs text-[var(--text-muted)]">
          <p className="font-semibold text-[var(--danger)]">Case could not be loaded</p>
          <p className="mt-1">{error || "Case record was not found."}</p>
          <div className="mt-4">
            <Link href="/cases" className="btn-secondary text-xs">
              ← Return to all cases
            </Link>
          </div>
        </div>
      </WorkspaceShell>
    );
  }

  const metaItems = [caseFile.case_type, caseFile.court, caseFile.stage].filter(Boolean);
  const attentionCount = caseFile.attention_count ?? 0;
  const isOverview = activeTab === "overview";

  return (
    <WorkspaceShell
      active="case"
      caseWorkspace={true}
      caseId={caseId}
      caseTitle={caseFile.title}
      activeModule={activeTab}
      onModuleChange={handleTabChange}
      documentAttentionCount={attentionCount}
    >
      {/* 1. Case Workspace Header */}
      {isOverview ? (
        /* Full Case Header on Overview */
        <div className="pb-4">
          <div className="text-xs text-[var(--text-muted)] flex items-center gap-1.5 mb-1.5">
            <Link href="/cases" className="hover:text-[var(--text)]">Cases</Link>
            <span className="text-[var(--text-faint)]">/</span>
            <span className="text-[var(--text)] truncate max-w-sm">{caseFile.title}</span>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-3">
            <div>
              <h1 className="font-serif text-[28px] font-medium tracking-tight text-[var(--text)] leading-tight">
                {caseFile.title}
              </h1>

              <div className="mt-1 text-xs text-[var(--text-muted)] flex flex-wrap items-center gap-2">
                {metaItems.length > 0 && <span>{metaItems.join(" · ")}</span>}
                {caseFile.client_reference && (
                  <>
                    <span>·</span>
                    <span className="font-mono text-[11px] text-[var(--text-faint)]">{caseFile.client_reference}</span>
                  </>
                )}
                {!caseFile.court && (
                  <button
                    type="button"
                    onClick={() => {
                      setEditTitle(caseFile.title);
                      setEditRef(caseFile.client_reference || "");
                      setEditCourt("");
                      setEditJurisdiction(caseFile.jurisdiction || "");
                      setEditStage(caseFile.stage || "");
                      setEditingDetails(true);
                    }}
                    className="text-[var(--text-muted)] hover:text-[var(--text)]"
                  >
                    Add court
                  </button>
                )}
              </div>
            </div>

            <div className="flex items-center gap-3 shrink-0">
              <StatusDot status={caseFile.analysis_status || "Not started"} />
              <button
                type="button"
                onClick={() => {
                  setEditTitle(caseFile.title);
                  setEditRef(caseFile.client_reference || "");
                  setEditCourt(caseFile.court || "");
                  setEditJurisdiction(caseFile.jurisdiction || "");
                  setEditStage(caseFile.stage || "");
                  setEditingDetails(true);
                }}
                className="btn-ghost text-xs"
                title="Edit case details"
              >
                <Edit3 className="size-3.5" />
                <span>Details</span>
              </button>
            </div>
          </div>
          <div className="hairline mt-4 mb-6" />
        </div>
      ) : (
        /* Collapsed 1-Line Header on Module Pages */
        <div className="pb-4">
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
            <div className="flex items-center gap-1.5 truncate">
              <Link href="/cases" className="hover:text-[var(--text)]">Cases</Link>
              <span className="text-[var(--text-faint)]">/</span>
              <span
                onClick={() => handleTabChange("overview")}
                className="font-medium text-[var(--text)] cursor-pointer hover:text-[var(--primary)] truncate max-w-sm"
              >
                {caseFile.title}
              </span>
            </div>

            <div className="flex items-center gap-3 shrink-0">
              <StatusDot status={caseFile.analysis_status || "Not started"} />
              <button
                type="button"
                onClick={() => {
                  setEditTitle(caseFile.title);
                  setEditRef(caseFile.client_reference || "");
                  setEditCourt(caseFile.court || "");
                  setEditJurisdiction(caseFile.jurisdiction || "");
                  setEditStage(caseFile.stage || "");
                  setEditingDetails(true);
                }}
                className="btn-ghost text-xs py-0.5"
                title="Edit case details"
              >
                <Edit3 className="size-3.5" />
                <span>Details</span>
              </button>
            </div>
          </div>
          <div className="hairline mt-2 mb-6" />
        </div>
      )}

      {/* 2. Module Content Area */}
      <div>
        {activeTab === "overview" && (
          <CaseOverviewTab
            caseFile={caseFile}
            documents={documents}
            availability={availability}
            onNavigate={handleTabChange}
          />
        )}

        {activeTab === "documents" && (
          <CaseDocumentsTab
            caseId={caseId}
            documents={documents}
            onRefresh={refreshData}
          />
        )}

        {activeTab === "analysis" && (
          <CaseAnalysisPanel
            caseId={caseId}
            documents={documents}
            availability={availability}
          />
        )}

        {activeTab === "graph" && (
          <CaseKnowledgeGraphPanel caseId={caseId} />
        )}

        {activeTab === "research" && (
          <CaseLegalResearchPanel
            caseId={caseId}
            initialQuery={researchInitialQuery}
            onClearInitialQuery={() => setResearchInitialQuery("")}
          />
        )}

        {activeTab === "assistant" && (
          <CaseChatPanel
            caseId={caseId}
            documents={documents}
          />
        )}

        {activeTab === "summary" && (
          <CaseSummaryPanel
            caseId={caseId}
            documents={documents}
            availability={availability}
          />
        )}

        {activeTab === "decision" && (
          <CaseDecisionSupportPanel
            caseId={caseId}
            caseFile={caseFile}
          />
        )}

        {activeTab === "dates" && (
          <CaseDeadlineAgenda caseId={caseId} />
        )}
      </div>

      {/* Edit Details Drawer / Modal */}
      {editingDetails && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 shadow-[var(--shadow-drawer)]">
            <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
              <h2 className="font-serif text-base font-medium text-[var(--text)]">Case details</h2>
              <button
                type="button"
                onClick={() => setEditingDetails(false)}
                className="text-[var(--text-muted)] hover:text-[var(--text)] p-1"
              >
                <X className="size-4" />
              </button>
            </div>

            <form onSubmit={handleSaveDetails} className="mt-4 space-y-4 text-xs">
              <div>
                <label htmlFor="edit_title" className="block font-medium text-[var(--text)]">
                  Case Title <span className="text-[var(--danger)]">*</span>
                </label>
                <input
                  id="edit_title"
                  type="text"
                  required
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className="input-field w-full mt-1"
                />
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label htmlFor="edit_ref" className="block font-medium text-[var(--text)]">
                    Client Reference
                  </label>
                  <input
                    id="edit_ref"
                    type="text"
                    value={editRef}
                    onChange={(e) => setEditRef(e.target.value)}
                    className="input-field font-mono text-xs w-full mt-1"
                  />
                </div>

                <div>
                  <label htmlFor="edit_stage" className="block font-medium text-[var(--text)]">
                    Proceeding Stage
                  </label>
                  <input
                    id="edit_stage"
                    type="text"
                    value={editStage}
                    onChange={(e) => setEditStage(e.target.value)}
                    className="input-field w-full mt-1"
                  />
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label htmlFor="edit_court" className="block font-medium text-[var(--text)]">
                    Court / Tribunal
                  </label>
                  <input
                    id="edit_court"
                    type="text"
                    value={editCourt}
                    onChange={(e) => setEditCourt(e.target.value)}
                    className="input-field w-full mt-1"
                  />
                </div>

                <div>
                  <label htmlFor="edit_jurisdiction" className="block font-medium text-[var(--text)]">
                    Jurisdiction
                  </label>
                  <input
                    id="edit_jurisdiction"
                    type="text"
                    value={editJurisdiction}
                    onChange={(e) => setEditJurisdiction(e.target.value)}
                    className="input-field w-full mt-1"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between pt-4 border-t border-[var(--border)]">
                <button
                  type="button"
                  onClick={() => {
                    setEditingDetails(false);
                    setShowDeleteConfirm(true);
                  }}
                  className="text-xs text-[var(--danger)] hover:underline flex items-center gap-1.5"
                >
                  <Trash2 className="size-3.5" />
                  <span>Delete case…</span>
                </button>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setEditingDetails(false)}
                    className="btn-secondary"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={savingDetails}
                    className="btn-primary"
                  >
                    {savingDetails ? "Saving…" : "Save details"}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && caseFile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-[1px]">
          <div className="w-full max-w-md rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 shadow-[var(--shadow-drawer)]">
            <h2 className="text-sm font-semibold text-[var(--text)]">Delete case &ldquo;{caseFile.title}&rdquo;</h2>
            <p className="mt-2 text-xs leading-relaxed text-[var(--text-muted)]">
              This action cannot be undone. All documents, OCR extractions, knowledge graphs, and advocate notes will be permanently removed.
            </p>
            <p className="mt-4 text-xs font-medium text-[var(--text)]">
              Enter your advocate password to confirm deletion:
            </p>

            <div className="relative mt-1.5">
              <input
                type={showDeletePassword ? "text" : "password"}
                value={confirmDeletePassword}
                onChange={(e) => setConfirmDeletePassword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !deletingCase) {
                    e.preventDefault();
                    void handleDeleteCase();
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

            {deleteCaseError && <p className="mt-2 text-xs text-[var(--danger)]">{deleteCaseError}</p>}

            <div className="mt-6 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => { setShowDeleteConfirm(false); setConfirmDeletePassword(""); setShowDeletePassword(false); setDeleteCaseError(null); }}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deletingCase || !confirmDeletePassword.trim()}
                onClick={handleDeleteCase}
                className="btn-destructive"
              >
                {deletingCase ? "Deleting…" : "Delete case"}
              </button>
            </div>
          </div>
        </div>
      )}
    </WorkspaceShell>
  );
}
