"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, FileText, Scale, Sparkles, BookOpen, MessageSquare, Network, BarChart3, CalendarDays, Settings, X } from "lucide-react";
import { listCases, CaseRecord } from "@/lib/api";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const router = useRouter();

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    if (open && cases.length === 0) {
      listCases().then(setCases).catch(() => {});
    }
  }, [open, cases.length]);

  if (!open) return null;

  const filteredCases = cases.filter(
    (c) =>
      c.title.toLowerCase().includes(query.toLowerCase()) ||
      (c.client_reference && c.client_reference.toLowerCase().includes(query.toLowerCase())) ||
      (c.court && c.court.toLowerCase().includes(query.toLowerCase()))
  );

  function navigateTo(path: string) {
    setOpen(false);
    setQuery("");
    router.push(path);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[15vh] backdrop-blur-sm animate-in fade-in duration-150">
      <div className="w-full max-w-xl overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-elevated)]">
        {/* Search Input Bar */}
        <div className="flex items-center border-b border-[var(--border)] px-4 py-3">
          <Search className="size-4 shrink-0 text-[var(--accent-strong)]" />
          <input
            autoFocus
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search cases, modules, or tools (Ctrl+K)..."
            className="w-full bg-transparent px-3 text-sm text-[var(--text)] outline-none placeholder:text-[var(--text-muted)]"
          />
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded p-1 text-[var(--text-muted)] hover:bg-[var(--surface-2)]"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Results Body */}
        <div className="max-h-80 overflow-y-auto p-2 text-xs">
          {/* Global Tools & Short Links */}
          <div className="px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-[var(--accent-strong)]">
            Quick Navigation
          </div>
          <div className="space-y-1">
            <button
              type="button"
              onClick={() => navigateTo("/cases")}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left hover:bg-[var(--surface-2)]"
            >
              <Scale className="size-4 text-[var(--primary)]" />
              <div>
                <div className="font-semibold text-[var(--text)]">All Cases</div>
                <div className="text-[11px] text-[var(--text-muted)]">View master docket of active matters</div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => navigateTo("/dates")}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left hover:bg-[var(--surface-2)]"
            >
              <CalendarDays className="size-4 text-[var(--accent-strong)]" />
              <div>
                <div className="font-semibold text-[var(--text)]">Dates Agenda</div>
                <div className="text-[11px] text-[var(--text-muted)]">Manual calendar and hearing list</div>
              </div>
            </button>
            <button
              type="button"
              onClick={() => navigateTo("/settings")}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left hover:bg-[var(--surface-2)]"
            >
              <Settings className="size-4 text-[var(--text-muted)]" />
              <div>
                <div className="font-semibold text-[var(--text)]">Chambers Settings</div>
                <div className="text-[11px] text-[var(--text-muted)]">Appearance, privacy, and integrations</div>
              </div>
            </button>
          </div>

          {/* Cases List */}
          {filteredCases.length > 0 && (
            <div className="mt-3">
              <div className="px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-[var(--accent-strong)]">
                Cases ({filteredCases.length})
              </div>
              <div className="space-y-1">
                {filteredCases.slice(0, 5).map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => navigateTo(`/cases/${c.id}`)}
                    className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left hover:bg-[var(--surface-2)]"
                  >
                    <div className="min-w-0 pr-2">
                      <div className="truncate font-semibold text-[var(--text)]">{c.title}</div>
                      <div className="font-mono text-[10px] text-[var(--text-muted)]">
                        {[c.client_reference, c.court, c.case_type].filter(Boolean).join(" · ")}
                      </div>
                    </div>
                    <span className="shrink-0 text-[10px] text-[var(--accent-strong)] font-semibold">Open →</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-[var(--border)] bg-[var(--surface-2)] px-4 py-2 text-[10px] text-[var(--text-muted)]">
          <span>Use arrows to navigate, Enter to select</span>
          <kbd className="rounded border border-[var(--border)] bg-[var(--surface)] px-1.5 py-0.5 font-mono">Esc to close</kbd>
        </div>
      </div>
    </div>
  );
}
