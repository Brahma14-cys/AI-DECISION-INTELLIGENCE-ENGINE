"use client";

import { ChangeEvent, useRef, useState } from "react";
import {
  Upload,
  FileText,
  Trash2,
  RefreshCw,
  MoreHorizontal,
  Download,
  AlertCircle,
  AlertTriangle,
  Eye,
  Plus,
  X,
  FileX,
  ShieldAlert,
  CheckCircle2,
} from "lucide-react";
import {
  CaseDocument,
  formatFileSize,
  uploadDocuments,
  replaceDocumentFile,
  deleteDocument,
  retryDocumentExtraction,
} from "@/lib/api";
import { StatusDot } from "@/components/domain/status-dot";
import { DocumentTextPreview } from "./document-text-preview";
import { PageShell, PageHeader, PageBody } from "@/components/domain/page-shell";
import { InlineAlert } from "@/components/domain/inline-alert";
import { formatDate } from "@/lib/formatters";

const ACCEPTED_FILE_TYPES = ".pdf,.docx,.jpg,.jpeg,.png,.tif,.tiff";
const MAX_FILE_BYTES = 50 * 1024 * 1024;

export function CaseDocumentsTab({
  caseId,
  documents,
  onRefresh,
}: {
  caseId: string;
  documents: CaseDocument[];
  onRefresh: () => Promise<void>;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const replaceInputRef = useRef<HTMLInputElement>(null);
  const replaceTargetRef = useRef<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deleteFeedback, setDeleteFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  // Text preview drawer state
  const [previewDocId, setPreviewDocId] = useState<string | null>(null);
  const previewDoc = documents.find((d) => d.id === previewDocId) || null;

  // Identify unreadable or low-OCR documents
  const unreadableDocs = documents.filter((doc) => {
    if (doc.processing_status === "failed") return true;
    if (["processed", "needs_review"].includes(doc.processing_status) && doc.text_unit_count === 0) return true;
    if (doc.unreadable_location_count > 0 && doc.readable_location_count === 0) return true;
    if (doc.pages_without_text_count > 0 && doc.pages_with_text_count === 0) return true;
    return false;
  });

  const needsReviewDocs = documents.filter(
    (doc) => doc.processing_status === "needs_review" && !unreadableDocs.some((u) => u.id === doc.id)
  );

  async function handleFilesSelected(filesList: FileList | File[] | null) {
    const files = Array.from(filesList ?? []);
    if (!files.length) return;

    setUploading(true);
    setUploadError(null);

    const invalidSize = files.find((f) => f.size > MAX_FILE_BYTES);
    if (invalidSize) {
      setUploadError(`File "${invalidSize.name}" exceeds the 50 MB limit.`);
      setUploading(false);
      return;
    }

    try {
      const res = await uploadDocuments(caseId, files);
      if (res.rejected.length > 0) {
        setUploadError(res.rejected.map((r) => `${r.filename}: ${r.reason}`).join("\n"));
      }
      await onRefresh();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  function triggerReplace(docId: string) {
    replaceTargetRef.current = docId;
    replaceInputRef.current?.click();
  }

  async function handleReplace(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    const docId = replaceTargetRef.current;
    if (!file || !docId) return;

    setUploading(true);
    setUploadError(null);
    try {
      await replaceDocumentFile(caseId, docId, file);
      await onRefresh();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Could not replace document file.");
    } finally {
      setUploading(false);
      replaceTargetRef.current = null;
      if (replaceInputRef.current) replaceInputRef.current.value = "";
    }
  }

  async function handleDelete(doc: CaseDocument) {
    if (!confirm(`Permanently delete "${doc.original_filename}"?`)) return;
    setDeletingId(doc.id);
    setDeleteFeedback(null);
    try {
      await deleteDocument(caseId, doc.id);
      setDeleteFeedback({
        type: "success",
        message: `Document "${doc.original_filename}" was permanently deleted.`,
      });
      await onRefresh();
    } catch (err) {
      setDeleteFeedback({
        type: "error",
        message: err instanceof Error ? err.message : "Failed to delete document.",
      });
    } finally {
      setDeletingId(null);
    }
  }

  async function handleRetry(docId: string) {
    setRetryingId(docId);
    try {
      await retryDocumentExtraction(caseId, docId);
      await onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Extraction retry failed.");
    } finally {
      setRetryingId(null);
    }
  }

  return (
    <PageShell>
      {/* Hidden File Inputs */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ACCEPTED_FILE_TYPES}
        onChange={(e) => handleFilesSelected(e.target.files)}
        className="hidden"
      />
      <input
        ref={replaceInputRef}
        type="file"
        accept={ACCEPTED_FILE_TYPES}
        onChange={handleReplace}
        className="hidden"
      />

      {/* Page Header */}
      <PageHeader
        title="Documents"
        description="Filings, affidavits, orders and evidence."
        actions={
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
            className="btn-primary"
          >
            <Upload className="size-4" />
            <span>{uploading ? "Uploading…" : "Upload"}</span>
          </button>
        }
      />

      {deleteFeedback && (
        <div
          className={`rounded-lg border p-3.5 text-xs flex items-center justify-between gap-2 shadow-sm ${
            deleteFeedback.type === "success"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
              : "border-[var(--danger)]/30 bg-[var(--danger)]/10 text-[var(--danger)]"
          }`}
        >
          <div className="flex items-center gap-2">
            {deleteFeedback.type === "success" ? (
              <CheckCircle2 className="size-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle className="size-4 text-[var(--danger)] shrink-0" />
            )}
            <span className="font-medium">{deleteFeedback.message}</span>
          </div>
          <button
            type="button"
            onClick={() => setDeleteFeedback(null)}
            className="p-1 hover:opacity-75"
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}

      {/* Prominent Lock / Warning Banner if Unreadable or Low OCR files exist */}
      {unreadableDocs.length > 0 && (
        <div className="rounded-lg border border-[var(--danger)]/30 bg-[var(--surface)] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs border-l-4 border-l-[var(--danger)] shadow-sm">
          <div className="flex items-start gap-3 min-w-0">
            <ShieldAlert className="size-5 text-[var(--danger)] shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <span className="font-semibold text-[var(--text)] text-sm block">
                {unreadableDocs.length} unreadable / low-OCR document(s) detected — Analysis locked
              </span>
              <p className="text-[var(--text-muted)] leading-relaxed">
                Clean text could not be extracted from scanned pages. Further AI analysis and knowledge graph generation are locked until you retry extraction or replace with clearer scans.
              </p>
            </div>
          </div>
          <span className="shrink-0 px-2.5 py-1 rounded bg-[var(--danger)]/10 text-[var(--danger)] font-medium text-[11px] self-start sm:self-auto">
            Analysis Blocked
          </span>
        </div>
      )}

      {/* Single-line 56px Dashed Dropzone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragOver(false);
          handleFilesSelected(e.dataTransfer.files);
        }}
        onClick={() => fileInputRef.current?.click()}
        className={`flex h-14 w-full cursor-pointer items-center justify-between rounded-lg border border-dashed px-5 text-xs transition ${
          isDragOver
            ? "border-[var(--primary)] bg-[var(--primary-tint)]"
            : "border-[var(--border-strong)] bg-[var(--surface)] hover:border-[var(--brass)]"
        }`}
      >
        <div className="flex items-center gap-3">
          <Upload className="size-4 text-[var(--text-muted)]" />
          <span className="font-medium text-[var(--text)]">
            Drop files here or browse
          </span>
        </div>
        <span className="text-[var(--text-muted)] text-[11px]">
          50 MB max · PDF, DOCX, images
        </span>
      </div>

      {uploadError && (
        <div className="rounded-md border border-[var(--danger)]/30 bg-[var(--surface)] p-3 text-xs text-[var(--danger)] whitespace-pre-wrap">
          {uploadError}
        </div>
      )}

      {/* Documents Table */}
      <PageBody>
        {documents.length === 0 ? (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-8 text-center text-xs text-[var(--text-muted)]">
            <FileText className="mx-auto size-8 text-[var(--text-faint)] mb-2" />
            <p className="font-medium text-sm text-[var(--text)]">No documents in this case</p>
            <p className="mt-1">Upload petitions, plaints, written statements, or orders to start analysis.</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--surface)]">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-[var(--border)] text-xs text-[var(--text-muted)] font-medium bg-[var(--surface-2)]">
                <tr>
                  <th className="py-2.5 px-4 font-medium">Name</th>
                  <th className="py-2.5 px-4 font-medium">Type</th>
                  <th className="py-2.5 px-4 font-medium text-right">Pages</th>
                  <th className="py-2.5 px-4 font-medium">Reading status</th>
                  <th className="py-2.5 px-4 font-medium">Added</th>
                  <th className="py-2.5 px-4 text-right font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {documents.map((doc) => {
                  const isUnreadable = unreadableDocs.some((u) => u.id === doc.id);
                  const isNeedsReview = needsReviewDocs.some((n) => n.id === doc.id);
                  const pageCount = doc.page_count ?? doc.text_unit_count ?? 1;

                  return (
                    <tr
                      key={doc.id}
                      onClick={() => setPreviewDocId(doc.id)}
                      className={`group cursor-pointer transition ${
                        isUnreadable
                          ? "bg-[var(--danger)]/5 hover:bg-[var(--danger)]/10"
                          : "hover:bg-[var(--surface-2)]"
                      }`}
                    >
                      {/* Name Column */}
                      <td className="py-3 px-4">
                        <div className="font-medium text-[var(--text)] group-hover:text-[var(--primary)] flex items-center gap-2">
                          <FileText
                            className={`size-4 shrink-0 ${
                              isUnreadable
                                ? "text-[var(--danger)]"
                                : isNeedsReview
                                ? "text-[var(--warning)]"
                                : "text-[var(--brass)]"
                            }`}
                          />
                          <span className="truncate max-w-xs sm:max-w-md">{doc.original_filename}</span>
                        </div>
                        <div className="text-[11px] text-[var(--text-muted)] mt-0.5">
                          {formatFileSize(doc.size_bytes)}
                        </div>

                        {/* Unreadable / Low OCR inline warning bar */}
                        {isUnreadable && (
                          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-[var(--danger)] bg-[var(--danger)]/10 px-2 py-1 rounded">
                            <span className="font-medium">
                              Unreadable / Low OCR (0 readable lines) — Blocks analysis
                            </span>
                            <div className="flex items-center gap-2 ml-auto">
                              <button
                                type="button"
                                disabled={retryingId === doc.id}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleRetry(doc.id);
                                }}
                                className="font-medium underline hover:opacity-80"
                              >
                                {retryingId === doc.id ? "Retrying…" : "Retry scan"}
                              </button>
                              <span>·</span>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  triggerReplace(doc.id);
                                }}
                                className="font-medium underline hover:opacity-80"
                              >
                                Replace file
                              </button>
                            </div>
                          </div>
                        )}

                        {isNeedsReview && !isUnreadable && (
                          <div className="mt-1 flex items-center gap-2 text-[11px] text-[var(--warning)]">
                            <span>Low OCR confidence on select pages.</span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setPreviewDocId(doc.id);
                              }}
                              className="font-medium underline hover:opacity-80"
                            >
                              Review extracted text
                            </button>
                          </div>
                        )}
                      </td>

                      {/* Type */}
                      <td className="py-3 px-4 text-xs text-[var(--text-muted)]">
                        {doc.document_type || "Pleading / Affidavit"}
                      </td>

                      {/* Pages (Number only, no 'loc') */}
                      <td className="py-3 px-4 text-xs font-mono text-right text-[var(--text)]">
                        {pageCount}
                      </td>

                      {/* Reading status (StatusDot only) */}
                      <td className="py-3 px-4">
                        <StatusDot
                          status={
                            isUnreadable
                              ? "Failed"
                              : isNeedsReview
                              ? "Needs review"
                              : doc.processing_status === "processed"
                              ? "Ready"
                              : "Processing"
                          }
                        />
                      </td>

                      {/* Added date */}
                      <td className="py-3 px-4 text-xs text-[var(--text-muted)]">
                        {formatDate(doc.uploaded_at)}
                      </td>

                      {/* Actions Column: Direct, visible, unclipped toolbar */}
                      <td className="py-2.5 px-4 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1">
                          {/* 1. Open Text Preview */}
                          <button
                            type="button"
                            onClick={() => setPreviewDocId(doc.id)}
                            className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)] transition"
                            title="Open extracted text preview"
                          >
                            <Eye className="size-4" />
                          </button>

                          {/* 2. Download Original */}
                          <a
                            href={`/api/v1/cases/${caseId}/documents/${doc.id}/file`}
                            download
                            className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)] transition"
                            title="Download original file"
                          >
                            <Download className="size-4" />
                          </a>

                          {/* 3. Replace File */}
                          <button
                            type="button"
                            onClick={() => triggerReplace(doc.id)}
                            className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)] transition"
                            title="Replace document with clearer scan"
                          >
                            <Upload className="size-4" />
                          </button>

                          {/* 4. Retry Scan (if failed or review) */}
                          <button
                            type="button"
                            disabled={retryingId === doc.id}
                            onClick={() => handleRetry(doc.id)}
                            className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-2)] transition"
                            title="Retry OCR text extraction"
                          >
                            <RefreshCw className={`size-4 ${retryingId === doc.id ? "animate-spin" : ""}`} />
                          </button>

                          {/* 5. Delete Document */}
                          <button
                            type="button"
                            disabled={deletingId === doc.id}
                            onClick={() => handleDelete(doc)}
                            className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--danger)] hover:bg-[var(--danger)]/10 transition"
                            title="Permanently remove document"
                          >
                            <Trash2 className="size-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </PageBody>

      {/* Document Text Preview Modal / Drawer */}
      {previewDoc && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/40">
          <div className="flex h-full w-full max-w-[720px] flex-col border-l border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-drawer)]">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
              <div>
                <h2 className="font-serif text-base font-medium text-[var(--text)] truncate">
                  {previewDoc.original_filename}
                </h2>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">
                  {previewDoc.document_type || "Pleading"} · {previewDoc.page_count} pages
                </p>
              </div>
              <button
                type="button"
                onClick={() => setPreviewDocId(null)}
                className="text-[var(--text-muted)] hover:text-[var(--text)] p-1"
              >
                <X className="size-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              <DocumentTextPreview
                caseId={caseId}
                documentId={previewDoc.id}
                processingStatus={previewDoc.processing_status}
              />
            </div>
          </div>
        </div>
      )}
    </PageShell>
  );
}
