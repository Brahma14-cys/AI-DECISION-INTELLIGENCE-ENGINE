"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useRef, useEffect, type ReactNode } from "react";
import {
  Scale,
  Calendar,
  Settings,
  Search,
  ChevronLeft,
  LogOut,
  User,
  LayoutDashboard,
  FileText,
  Sparkles,
  Network,
  BookOpen,
  MessageSquare,
  FileCheck,
  Menu,
  X,
  ShieldCheck,
} from "lucide-react";
import { logout } from "@/lib/api";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { StatusDot } from "@/components/domain/status-dot";

export type WorkspaceModuleId =
  | "overview"
  | "documents"
  | "analysis"
  | "graph"
  | "research"
  | "assistant"
  | "summary"
  | "decision"
  | "dates";

export function WorkspaceShell({
  children,
  active = "cases",
  caseWorkspace = false,
  caseId,
  caseTitle,
  activeModule = "overview",
  onModuleChange,
  documentAttentionCount = 0,
}: {
  children: ReactNode;
  active?: "cases" | "new" | "dates" | "settings" | "case";
  caseWorkspace?: boolean;
  caseId?: string;
  caseTitle?: string;
  activeModule?: WorkspaceModuleId;
  onModuleChange?: (module: WorkspaceModuleId) => void;
  documentAttentionCount?: number;
}) {
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [avatarMenuOpen, setAvatarMenuOpen] = useState(false);
  const avatarMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (avatarMenuRef.current && !avatarMenuRef.current.contains(e.target as Node)) {
        setAvatarMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function handleSignOut() {
    try {
      await logout();
    } finally {
      window.location.replace("/signin");
    }
  }

  function openCommandPalette() {
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, bubbles: true }));
  }

  const caseNavItems: {
    id: WorkspaceModuleId;
    label: string;
    icon: React.ReactNode;
    hasAlert?: boolean;
  }[] = [
    { id: "overview", label: "Overview", icon: <LayoutDashboard className="size-4" strokeWidth={1.5} /> },
    { id: "documents", label: "Documents", icon: <FileText className="size-4" strokeWidth={1.5} />, hasAlert: documentAttentionCount > 0 },
    { id: "analysis", label: "Analysis", icon: <Sparkles className="size-4" strokeWidth={1.5} /> },
    { id: "graph", label: "Knowledge graph", icon: <Network className="size-4" strokeWidth={1.5} /> },
    { id: "research", label: "Legal research", icon: <BookOpen className="size-4" strokeWidth={1.5} /> },
    { id: "assistant", label: "Case assistant", icon: <MessageSquare className="size-4" strokeWidth={1.5} /> },
  ];

  const toolsNavItems: {
    id: WorkspaceModuleId;
    label: string;
    icon: React.ReactNode;
  }[] = [
    { id: "summary", label: "Summary", icon: <FileCheck className="size-4" strokeWidth={1.5} /> },
    { id: "decision", label: "Decision support", icon: <Scale className="size-4" strokeWidth={1.5} /> },
    { id: "dates", label: "Dates agenda", icon: <Calendar className="size-4" strokeWidth={1.5} /> },
  ];

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--bg)] text-[var(--text)] flex-col">
      {/* 56px Fixed Top Bar */}
      <header className="flex h-14 shrink-0 w-full items-center justify-between border-b border-[var(--border)] bg-[var(--bg)] px-4 sm:px-6 z-40">
        {/* Left Brand: Scale mark 22px + 'Legal Decision Intelligence' 14px/600 */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-1 text-[var(--text-muted)] hover:text-[var(--text)]"
            aria-label="Toggle navigation"
          >
            {mobileMenuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>

          <Link href="/cases" className="flex items-center gap-2.5 text-decoration-none">
            <Scale className="size-[22px] text-[var(--brass)]" strokeWidth={1.75} />
            <span className="text-sm font-semibold tracking-tight text-[var(--text)]">
              Legal Decision Intelligence
            </span>
          </Link>
        </div>

        {/* Center Search / Command Palette trigger */}
        <div className="hidden sm:flex flex-1 max-w-[400px] mx-4">
          <button
            type="button"
            onClick={openCommandPalette}
            className="flex h-9 w-full items-center justify-between rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-xs text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text)] transition"
          >
            <span className="flex items-center gap-2 min-w-0">
              <Search className="size-3.5 text-[var(--text-faint)] shrink-0" />
              <span className="truncate">Search or jump to…</span>
            </span>
            <kbd className="font-mono text-[11px] text-[var(--text-faint)] bg-[var(--surface-2)] px-1.5 py-0.5 rounded border border-[var(--border)]">
              Ctrl K
            </kbd>
          </button>
        </div>

        {/* Right Actions & Avatar */}
        <div className="flex items-center gap-3">
          <ThemeToggle />

          {/* Avatar Menu */}
          <div className="relative" ref={avatarMenuRef}>
            <button
              type="button"
              onClick={() => setAvatarMenuOpen(!avatarMenuOpen)}
              className="grid size-8 place-items-center rounded-full bg-[var(--surface-2)] border border-[var(--border)] text-[var(--text)] text-xs font-semibold hover:bg-[var(--border)] transition"
              aria-label="Advocate account menu"
            >
              A
            </button>

            {avatarMenuOpen && (
              <div className="absolute right-0 mt-2 w-48 rounded-md border border-[var(--border)] bg-[var(--surface)] p-1.5 shadow-[var(--shadow-drawer)] z-50 text-xs">
                <Link
                  href="/settings"
                  onClick={() => setAvatarMenuOpen(false)}
                  className="flex items-center gap-2 rounded px-2.5 py-1.5 text-[var(--text)] hover:bg-[var(--surface-2)]"
                >
                  <User className="size-3.5 text-[var(--text-muted)]" />
                  <span>Profile & Settings</span>
                </Link>
                <div className="my-1 border-t border-[var(--border)]" />
                <button
                  type="button"
                  onClick={handleSignOut}
                  className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-[var(--danger)] hover:bg-[var(--surface-2)] text-left"
                >
                  <LogOut className="size-3.5" />
                  <span>Sign out</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Container: Fixed Height, Left Rail + Scrollable Content */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left Rail (Desktop: 232px, Sticky with own scroll if needed) */}
        <aside
          className={`
            fixed inset-y-14 left-0 z-30 w-[232px] flex-col justify-between border-r border-[var(--border)] bg-[var(--sidebar)] p-3 md:static md:flex md:h-full
            ${mobileMenuOpen ? "flex" : "hidden md:flex"}
          `}
        >
          <div className="flex flex-col flex-1 overflow-y-auto space-y-4">
            {!caseWorkspace ? (
              /* Global Rail (Case List Level) */
              <nav className="space-y-1">
                <Link
                  href="/cases"
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex h-9 items-center gap-2.5 rounded-md px-3 text-sm font-medium transition ${
                    active === "cases"
                      ? "bg-[var(--primary-tint)] text-[var(--primary)] font-semibold border-l-2 border-l-[var(--primary)]"
                      : "text-[var(--text)] hover:bg-[var(--surface-2)]"
                  }`}
                >
                  <Scale className="size-4 text-[var(--text-muted)]" strokeWidth={1.5} />
                  <span>All cases</span>
                </Link>
                <Link
                  href="/dates"
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex h-9 items-center gap-2.5 rounded-md px-3 text-sm font-medium transition ${
                    active === "dates"
                      ? "bg-[var(--primary-tint)] text-[var(--primary)] font-semibold border-l-2 border-l-[var(--primary)]"
                      : "text-[var(--text)] hover:bg-[var(--surface-2)]"
                  }`}
                >
                  <Calendar className="size-4 text-[var(--text-muted)]" strokeWidth={1.5} />
                  <span>Dates agenda</span>
                </Link>
                <Link
                  href="/settings"
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex h-9 items-center gap-2.5 rounded-md px-3 text-sm font-medium transition ${
                    active === "settings"
                      ? "bg-[var(--primary-tint)] text-[var(--primary)] font-semibold border-l-2 border-l-[var(--primary)]"
                      : "text-[var(--text)] hover:bg-[var(--surface-2)]"
                  }`}
                >
                  <Settings className="size-4 text-[var(--text-muted)]" strokeWidth={1.5} />
                  <span>Settings</span>
                </Link>
              </nav>
            ) : (
              /* Case Rail (Case Workspace Level) */
              <div className="flex flex-col flex-1">
                {/* Back to all cases */}
                <Link
                  href="/cases"
                  onClick={() => setMobileMenuOpen(false)}
                  className="mb-4 inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text)]"
                >
                  <ChevronLeft className="size-3.5" /> All cases
                </Link>

                {/* Case Group */}
                <div className="space-y-0.5">
                  <div className="px-3 pb-1 text-xs font-medium text-[var(--text-muted)]">
                    Case
                  </div>
                  {caseNavItems.map((item) => {
                    const isCurrent = activeModule === item.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          onModuleChange?.(item.id);
                          setMobileMenuOpen(false);
                        }}
                        className={`flex h-9 w-full items-center justify-between rounded-md px-3 text-left text-sm font-medium transition ${
                          isCurrent
                            ? "bg-[var(--primary-tint)] text-[var(--primary)] font-semibold border-l-2 border-l-[var(--primary)]"
                            : "text-[var(--text)] hover:bg-[var(--surface-2)]"
                        }`}
                      >
                        <span className="flex items-center gap-2.5 min-w-0">
                          <span className={isCurrent ? "text-[var(--primary)]" : "text-[var(--text-muted)]"}>
                            {item.icon}
                          </span>
                          <span className="truncate">{item.label}</span>
                        </span>
                        {item.hasAlert && (
                          <span className="size-1.5 rounded-full bg-[var(--warning)] shrink-0" />
                        )}
                      </button>
                    );
                  })}
                </div>

                {/* Tools Group */}
                <div className="mt-6 space-y-0.5">
                  <div className="px-3 pb-1 text-xs font-medium text-[var(--text-muted)]">
                    Tools
                  </div>
                  {toolsNavItems.map((item) => {
                    const isCurrent = activeModule === item.id;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          onModuleChange?.(item.id);
                          setMobileMenuOpen(false);
                        }}
                        className={`flex h-9 w-full items-center gap-2.5 rounded-md px-3 text-left text-sm font-medium transition ${
                          isCurrent
                            ? "bg-[var(--primary-tint)] text-[var(--primary)] font-semibold border-l-2 border-l-[var(--primary)]"
                            : "text-[var(--text)] hover:bg-[var(--surface-2)]"
                        }`}
                      >
                        <span className={isCurrent ? "text-[var(--primary)]" : "text-[var(--text-muted)]"}>
                          {item.icon}
                        </span>
                        <span className="truncate">{item.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Rail Footer: Connection status dot & version */}
          <div className="pt-3 border-t border-[var(--border)] text-[11px] text-[var(--text-faint)] flex items-center justify-between">
            <span>v0.1.0</span>
            <div className="flex items-center gap-1.5 text-[var(--text-muted)]">
              <span className="size-1.5 rounded-full bg-[var(--success)]" />
              <span>Chambers connected</span>
            </div>
          </div>
        </aside>

        {/* Center Main Scroll Container (Only this region scrolls) */}
        <main className="flex-1 min-w-0 overflow-y-auto px-5 sm:px-8 py-6 scroll-smooth">
          <div className="mx-auto w-full max-w-[1080px]">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
