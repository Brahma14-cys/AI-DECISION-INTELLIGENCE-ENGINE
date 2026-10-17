"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ChevronLeft, Scale, Plus, AlertCircle, RefreshCw } from "lucide-react";
import { createCase } from "@/lib/api";
import { WorkspaceShell } from "@/app/workspace-shell";

const CASE_TYPES = [
  "Civil Suit",
  "Criminal Appeal / Revision",
  "Writ Petition",
  "Commercial Dispute",
  "Arbitration",
  "Company / Insolvency (NCLT)",
  "Family / Matrimonial",
  "Property / Land Dispute",
  "Labour & Employment",
  "Taxation (Direct / Indirect)",
  "Other Matter"
];

const STAGES = [
  "Pre-filing / Consultation",
  "Filed",
  "Notice & Summons",
  "Pleadings & Written Statement",
  "Framing of Issues",
  "Evidence & Cross-examination",
  "Final Arguments",
  "Judgment Reserved",
  "Appeal / Revision",
  "Execution Proceedings",
  "Closed / Disposed"
];

const COMMON_COURTS = [
  "Supreme Court of India",
  "Delhi High Court",
  "Bombay High Court",
  "Madras High Court",
  "Calcutta High Court",
  "Karnataka High Court",
  "Telangana High Court",
  "Principal District & Sessions Court",
  "National Company Law Tribunal (NCLT)",
  "Debt Recovery Tribunal (DRT)"
];

export default function NewCasePage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [description, setDescription] = useState("");

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(e.currentTarget);

    const title = String(form.get("title") ?? "").trim();
    const clientRef = String(form.get("client_reference") ?? "").trim();
    const caseType = String(form.get("case_type") ?? "").trim();
    const court = String(form.get("court") ?? "").trim();
    const jurisdiction = String(form.get("jurisdiction") ?? "").trim();
    const stage = String(form.get("stage") ?? "").trim();
    const caseNumber = String(form.get("case_number") ?? "").trim();

    try {
      const created = await createCase({
        title,
        client_reference: clientRef || undefined,
        case_type: caseType || undefined,
        court: court || undefined,
        jurisdiction: jurisdiction || undefined,
        stage: stage || undefined,
        case_number: caseNumber || undefined,
      });
      router.push(`/cases/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create case.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <WorkspaceShell active="new">
      <div className="mx-auto max-w-2xl">
        <Link
          href="/cases"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--accent-strong)] hover:underline"
        >
          <ChevronLeft className="size-3.5" /> Back to all cases
        </Link>

        <div className="mt-4">
          <h1 className="text-2xl font-bold tracking-tight text-[var(--text)]">Create a new case</h1>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            Register a matter in your chambers workspace to organise documents, run extraction, and track hearings.
          </p>
        </div>

        <div className="brass-rule mt-3 mb-6" />

        <form onSubmit={handleSubmit} className="chambers-card space-y-6">
          {/* Section 1: Identification */}
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold uppercase tracking-wider text-[var(--accent-strong)]">
                Section 1
              </span>
              <span className="text-xs font-semibold text-[var(--text)]">· Matter Identification</span>
            </div>

            <div className="mt-4 space-y-4">
              <div>
                <label htmlFor="title" className="block text-xs font-semibold text-[var(--text)]">
                  Case Title <span className="text-[var(--status-danger)]">*</span>
                </label>
                <input
                  id="title"
                  name="title"
                  type="text"
                  required
                  placeholder="e.g. Anand Sharma v. Union of India & Ors."
                  className="mt-1.5 w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-2 text-xs text-[var(--text)] outline-none focus:border-[var(--accent)]"
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="client_reference" className="block text-xs font-semibold text-[var(--text)]">
                    Internal Reference Code <span className="text-[var(--status-danger)]">*</span>
                  </label>
                  <input
                    id="client_reference"
                    name="client_reference"
                    type="text"
                    required
                    placeholder="e.g. DL-HC-2026-084"
                    className="mt-1.5 w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-2 font-mono text-xs text-[var(--text)] outline-none focus:border-[var(--accent)]"
                  />
                  <span className="mt-1 block text-[10px] text-[var(--text-faint)]">Unique docket ID for your records</span>
                </div>

                <div>
                  <label htmlFor="case_type" className="block text-xs font-semibold text-[var(--text)]">
                    Case Type
                  </label>
                  <select
                    id="case_type"
                    name="case_type"
                    className="mt-1.5 w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--text)] outline-none focus:border-[var(--accent)]"
                  >
                    {CASE_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </div>

          <div className="border-t border-[var(--border-subtle)]" />

          {/* Section 2: Forum */}
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold uppercase tracking-wider text-[var(--accent-strong)]">
                Section 2
              </span>
              <span className="text-xs font-semibold text-[var(--text)]">· Forum & Jurisdiction</span>
            </div>

            <div className="mt-4 space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="court" className="block text-xs font-semibold text-[var(--text)]">
                    Court / Tribunal
                  </label>
                  <input
                    id="court"
                    name="court"
                    type="text"
                    list="court_options"
                    placeholder="e.g. Delhi High Court"
                    className="mt-1.5 w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-2 text-xs text-[var(--text)] outline-none focus:border-[var(--accent)]"
                  />
                  <datalist id="court_options">
                    {COMMON_COURTS.map((c) => (
                      <option key={c} value={c} />
                    ))}
                  </datalist>
                </div>

                <div>
                  <label htmlFor="jurisdiction" className="block text-xs font-semibold text-[var(--text)]">
                    Jurisdiction / State
                  </label>
                  <input
                    id="jurisdiction"
                    name="jurisdiction"
                    type="text"
                    placeholder="e.g. New Delhi, Delhi"
                    className="mt-1.5 w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-2 text-xs text-[var(--text)] outline-none focus:border-[var(--accent)]"
                  />
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="stage" className="block text-xs font-semibold text-[var(--text)]">
                    Current Proceeding Stage
                  </label>
                  <select
                    id="stage"
                    name="stage"
                    className="mt-1.5 w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--text)] outline-none focus:border-[var(--accent)]"
                  >
                    {STAGES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="case_number" className="block text-xs font-semibold text-[var(--text)]">
                    Court Case / Filing No. <span className="text-[10px] font-normal text-[var(--text-faint)]">(Optional)</span>
                  </label>
                  <input
                    id="case_number"
                    name="case_number"
                    type="text"
                    placeholder="e.g. CS (OS) 402/2026"
                    className="mt-1.5 w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] px-3.5 py-2 text-xs text-[var(--text)] outline-none focus:border-[var(--accent)]"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="description" className="block text-xs font-semibold text-[var(--text)]">
                  Case Brief & Notes <span className="text-[10px] font-normal text-[var(--text-faint)]">(Max 500 characters)</span>
                </label>
                <textarea
                  id="description"
                  name="description"
                  rows={3}
                  maxLength={500}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Summary of claims, reliefs sought, or urgent hearing notes…"
                  className="mt-1.5 w-full rounded-md border border-[var(--border)] bg-[var(--surface-2)] p-3 text-xs text-[var(--text)] outline-none focus:border-[var(--accent)]"
                />
                <div className="mt-1 text-right text-[10px] text-[var(--text-faint)]">
                  {description.length} / 500 chars
                </div>
              </div>
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-md border border-[var(--status-danger)]/30 bg-[var(--status-danger-bg)] p-3 text-xs text-[var(--status-danger)]">
              <AlertCircle className="size-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <Link href="/cases" className="btn-secondary text-xs">
              Cancel
            </Link>
            <button
              type="submit"
              disabled={submitting}
              className="btn-primary text-xs font-semibold"
            >
              {submitting ? (
                <>
                  <RefreshCw className="size-3.5 animate-spin" />
                  <span>Creating workspace…</span>
                </>
              ) : (
                <span>Create case</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </WorkspaceShell>
  );
}
