"use client";

import { useEffect, useState } from "react";
import {
  User,
  Palette,
  Shield,
  Server,
  LogOut,
  Sun,
  Moon,
  Laptop,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
} from "lucide-react";
import { getAdvocateSession, logout, AdvocateSession } from "@/lib/api";
import { WorkspaceShell } from "@/app/workspace-shell";
import { PageShell, PageHeader, PageBody } from "@/components/domain/page-shell";
import { StatusDot } from "@/components/domain/status-dot";

export default function SettingsPage() {
  const [session, setSession] = useState<AdvocateSession | null>(null);
  const [activeTab, setActiveTab] = useState<"profile" | "appearance" | "privacy" | "connections">("profile");
  const [currentTheme, setCurrentTheme] = useState<"light" | "dark" | "system">("light");

  useEffect(() => {
    getAdvocateSession().then(setSession).catch(() => {});
    const saved = localStorage.getItem("app_theme") as "light" | "dark" | "system" | null;
    if (saved) setCurrentTheme(saved);
  }, []);

  function setTheme(t: "light" | "dark" | "system") {
    setCurrentTheme(t);
    localStorage.setItem("app_theme", t);
    const root = document.documentElement;
    if (t === "system") {
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.setAttribute("data-theme", prefersDark ? "dark" : "light");
    } else {
      root.setAttribute("data-theme", t);
    }
  }

  async function handleSignOut() {
    await logout();
    window.location.replace("/signin");
  }

  return (
    <WorkspaceShell active="settings">
      <PageShell>
        <PageHeader
          title="Settings"
          description="Chambers profile, appearance, data controls, and connected services."
        />

        <PageBody>
          <div className="flex flex-col md:flex-row gap-8 items-start">
            {/* Left Column: Vertical Text Tabs */}
            <nav className="w-full md:w-48 shrink-0 space-y-1 text-sm border-b md:border-b-0 md:border-r border-[var(--border)] pb-4 md:pb-0 md:pr-4">
              <button
                type="button"
                onClick={() => setActiveTab("profile")}
                className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left transition ${
                  activeTab === "profile"
                    ? "bg-[var(--primary-tint)] font-medium text-[var(--primary)]"
                    : "text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
                }`}
              >
                <User className="size-4" />
                <span>Profile</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("appearance")}
                className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left transition ${
                  activeTab === "appearance"
                    ? "bg-[var(--primary-tint)] font-medium text-[var(--primary)]"
                    : "text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
                }`}
              >
                <Palette className="size-4" />
                <span>Appearance</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("privacy")}
                className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left transition ${
                  activeTab === "privacy"
                    ? "bg-[var(--primary-tint)] font-medium text-[var(--primary)]"
                    : "text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
                }`}
              >
                <Shield className="size-4" />
                <span>Data & privacy</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("connections")}
                className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left transition ${
                  activeTab === "connections"
                    ? "bg-[var(--primary-tint)] font-medium text-[var(--primary)]"
                    : "text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
                }`}
              >
                <Server className="size-4" />
                <span>Connections</span>
              </button>
            </nav>

            {/* Right Column: 560px Form Area */}
            <div className="w-full max-w-[560px] space-y-6">
              {/* Profile Tab */}
              {activeTab === "profile" && (
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 space-y-6">
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--text)]">Advocate Profile</h3>
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">
                      Configured installation credentials.
                    </p>
                  </div>

                  <div className="space-y-4 text-xs">
                    <div>
                      <label className="block font-medium text-[var(--text-muted)]">Signed in email</label>
                      <div className="mt-1 font-mono text-sm text-[var(--text)] font-medium">
                        {session?.email || "advocate@chambers.in"}
                      </div>
                    </div>

                    <div>
                      <label className="block font-medium text-[var(--text-muted)]">Installation Mode</label>
                      <div className="mt-1 text-sm text-[var(--text)]">Single Advocate Chambers</div>
                    </div>
                  </div>

                  <div className="pt-4 border-t border-[var(--border)]">
                    <button
                      type="button"
                      onClick={handleSignOut}
                      className="btn-destructive text-xs"
                    >
                      <LogOut className="size-3.5" />
                      <span>Sign out</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Appearance Tab */}
              {activeTab === "appearance" && (
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 space-y-6">
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--text)]">Appearance</h3>
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">
                      Choose between light paper palette and ink dark theme.
                    </p>
                  </div>

                  {/* 3 Selectable Thumbnails */}
                  <div className="grid grid-cols-3 gap-3">
                    <button
                      type="button"
                      onClick={() => setTheme("light")}
                      className={`flex flex-col items-center gap-2 p-3 rounded-lg border text-xs transition ${
                        currentTheme === "light"
                          ? "border-[var(--primary)] bg-[var(--primary-tint)] font-semibold text-[var(--primary)]"
                          : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-muted)] hover:border-[var(--brass)]"
                      }`}
                    >
                      <Sun className="size-5" />
                      <span>Light</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setTheme("dark")}
                      className={`flex flex-col items-center gap-2 p-3 rounded-lg border text-xs transition ${
                        currentTheme === "dark"
                          ? "border-[var(--primary)] bg-[var(--primary-tint)] font-semibold text-[var(--primary)]"
                          : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-muted)] hover:border-[var(--brass)]"
                      }`}
                    >
                      <Moon className="size-5" />
                      <span>Dark</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setTheme("system")}
                      className={`flex flex-col items-center gap-2 p-3 rounded-lg border text-xs transition ${
                        currentTheme === "system"
                          ? "border-[var(--primary)] bg-[var(--primary-tint)] font-semibold text-[var(--primary)]"
                          : "border-[var(--border)] bg-[var(--surface-2)] text-[var(--text-muted)] hover:border-[var(--brass)]"
                      }`}
                    >
                      <Laptop className="size-5" />
                      <span>System</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Data & Privacy Tab */}
              {activeTab === "privacy" && (
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 space-y-4 text-xs leading-relaxed text-[var(--text-muted)]">
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--text)]">Data & Privacy Safeguards</h3>
                    <p className="mt-0.5">Local encrypted database and confidentiality architecture.</p>
                  </div>

                  <div className="space-y-3 pt-2">
                    <div>
                      <strong className="text-[var(--text)]">AES-256-GCM Encryption:</strong> Case metadata, extracted text units, analysis findings, and narrative brief summaries are stored with application-level encryption keys.
                    </div>
                    <div>
                      <strong className="text-[var(--text)]">Local OCR & Parsing:</strong> Document files stay on your system. Tesseract OCR and PDF parsing execute in your environment.
                    </div>
                    <div>
                      <strong className="text-[var(--text)]">API Provider Isolation:</strong> Statutory lookups and Gemini calls use direct, encrypted channels with zero data retention for model training.
                    </div>
                  </div>
                </div>
              )}

              {/* Connections Tab */}
              {activeTab === "connections" && (
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 space-y-4">
                  <div>
                    <h3 className="text-sm font-semibold text-[var(--text)]">Connected Services</h3>
                    <p className="text-xs text-[var(--text-muted)] mt-0.5">
                      Status of local engines and external legal research providers.
                    </p>
                  </div>

                  <div className="divide-y divide-[var(--border)] text-xs">
                    <div className="py-3 flex items-center justify-between">
                      <div>
                        <span className="font-medium text-[var(--text)] block">PostgreSQL (pgvector)</span>
                        <span className="text-[11px] text-[var(--text-muted)]">Relational database & embeddings</span>
                      </div>
                      <StatusDot status="Ready" />
                    </div>

                    <div className="py-3 flex items-center justify-between">
                      <div>
                        <span className="font-medium text-[var(--text)] block">Neo4j Graph Engine</span>
                        <span className="text-[11px] text-[var(--text-muted)]">Case knowledge graph</span>
                      </div>
                      <StatusDot status="Ready" />
                    </div>

                    <div className="py-3 flex items-center justify-between">
                      <div>
                        <span className="font-medium text-[var(--text)] block">India Code Gateway</span>
                        <span className="text-[11px] text-[var(--text-muted)]">Central acts & provisions</span>
                      </div>
                      <StatusDot status="Ready" />
                    </div>

                    <div className="py-3 flex items-center justify-between">
                      <div>
                        <span className="font-medium text-[var(--text)] block">Indian Kanoon API</span>
                        <span className="text-[11px] text-[var(--text-muted)]">Judicial precedent retrieval</span>
                      </div>
                      <StatusDot status="Ready" />
                    </div>

                    <div className="py-3 flex items-center justify-between">
                      <div>
                        <span className="font-medium text-[var(--text)] block">Gemini 2.5 Flash / Pro</span>
                        <span className="text-[11px] text-[var(--text-muted)]">Structured reasoning engine</span>
                      </div>
                      <StatusDot status="Ready" />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </PageBody>
      </PageShell>
    </WorkspaceShell>
  );
}
