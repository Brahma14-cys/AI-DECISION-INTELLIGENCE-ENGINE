"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Scale, Eye, EyeOff, Info, X } from "lucide-react";
import { getAdvocateSession, getAuthSetupStatus, login } from "@/lib/api";
import { ThemeToggle } from "@/components/ui/theme-toggle";

export default function SignInPage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [setupConfigured, setSetupConfigured] = useState<boolean | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [capsLockActive, setCapsLockActive] = useState(false);
  const [showPrivacyModal, setShowPrivacyModal] = useState(false);

  useEffect(() => {
    let active = true;
    getAuthSetupStatus()
      .then((status) => {
        if (active) setSetupConfigured(status.configured);
      })
      .catch(() => {
        if (active) setSetupConfigured(true);
      });

    getAdvocateSession()
      .then(() => {
        if (active) router.replace("/cases");
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, [router]);

  function handleKeyUp(e: React.KeyboardEvent) {
    setCapsLockActive(e.getModifierState("CapsLock"));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");

    try {
      await login(email, password);
      window.location.replace("/cases");
    } catch (reason) {
      const msg = reason instanceof Error ? reason.message : "Email or password is incorrect.";
      setError(
        msg.includes("401") || msg.includes("Unauthorized")
          ? "Email or password is incorrect."
          : msg
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen grid-cols-1 lg:grid-cols-2 bg-[var(--bg)]">
      {/* Left 50%: Form Centred in 380px Column */}
      <section className="flex flex-col justify-between p-6 sm:p-12">
        {/* Top bar in left column */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Scale className="size-7 text-[var(--brass)]" strokeWidth={1.75} />
          </div>
          <ThemeToggle />
        </div>

        {/* Centred Form Area: 380px max-width */}
        <div className="mx-auto my-auto w-full max-w-[380px] py-8">
          <div className="mb-7">
            <h1 className="font-serif text-[32px] font-medium tracking-tight text-[var(--text)] leading-tight">
              Sign in
            </h1>
            <p className="mt-2 text-sm text-[var(--text-muted)]">
              Welcome back to your chambers.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5" onKeyUp={handleKeyUp}>
            {error && (
              <div className="rounded-md border border-[var(--danger)]/30 bg-[var(--surface)] p-3 text-xs text-[var(--danger)]">
                {error}
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-[13px] font-medium text-[var(--text)]">
                Email address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                required
                autoFocus
                placeholder="advocate@chambers.in"
                className="input-field mt-1.5 h-10 w-full"
              />
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label htmlFor="password" className="block text-[13px] font-medium text-[var(--text)]">
                  Password
                </label>
                {capsLockActive && (
                  <span className="text-[11px] font-medium text-[var(--warning)]">
                    Caps Lock is ON
                  </span>
                )}
              </div>
              <div className="relative mt-1.5">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  required
                  placeholder="••••••••••••"
                  className="input-field h-10 w-full pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-2.5 text-[var(--text-muted)] hover:text-[var(--text)]"
                  tabIndex={-1}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="btn-primary h-10 w-full text-sm font-medium"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>

            {setupConfigured === false && (
              <div className="pt-2 text-center text-xs text-[var(--text-muted)]">
                <span>First time on this installation? </span>
                <Link href="/setup" className="font-medium text-[var(--primary)] hover:underline">
                  Set up the account
                </Link>
              </div>
            )}
          </form>
        </div>

        {/* Footer */}
        <div className="mx-auto w-full max-w-[380px] pt-4 text-center">
          <button
            type="button"
            onClick={() => setShowPrivacyModal(true)}
            className="text-[13px] text-[var(--text-muted)] hover:text-[var(--text)] transition"
          >
            Privacy and data handling
          </button>
        </div>
      </section>

      {/* Right 50%: Solid Deep Oxblood Panel with Faint Brass Watermark */}
      <section className="relative hidden lg:flex flex-col justify-end p-12 bg-[#3F1220] dark:bg-[#2A0E16] text-[#FAF9F6] overflow-hidden">
        {/* Faint Brass Watermark Line Art */}
        <div className="pointer-events-none absolute -right-16 -top-16 select-none opacity-[0.06] text-[#D3CCBD]">
          <Scale className="size-[560px]" strokeWidth={1} />
        </div>

        {/* Ivory Quote at bottom-left */}
        <div className="relative z-10 max-w-md">
          <p className="font-serif text-2xl font-medium tracking-tight text-[#FAF9F6] leading-relaxed">
            “Evidence, organised. Decisions, yours.”
          </p>
          <div className="brass-hairline mt-4 w-12 opacity-60" />
        </div>
      </section>

      {/* Privacy and Data Handling Modal / Popover */}
      {showPrivacyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 shadow-[var(--shadow-drawer)]">
            <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
              <div className="flex items-center gap-2">
                <Info className="size-4 text-[var(--brass)]" />
                <h2 className="text-sm font-semibold text-[var(--text)]">Privacy and Data Handling</h2>
              </div>
              <button
                type="button"
                onClick={() => setShowPrivacyModal(false)}
                className="text-[var(--text-muted)] hover:text-[var(--text)] p-1"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="mt-4 space-y-3 text-xs leading-relaxed text-[var(--text-muted)]">
              <p>
                <strong className="text-[var(--text)]">Single Advocate Architecture:</strong> This instance is provisioned exclusively for one advocate. Credentials and sessions are governed by AES-256-GCM database encryption and HttpOnly cookies.
              </p>
              <p>
                <strong className="text-[var(--text)]">Local File Processing:</strong> Uploaded documents (pleadings, affidavits, orders) are stored locally. Text extraction, OCR, and document indexing execute on this system.
              </p>
              <p>
                <strong className="text-[var(--text)]">LLM Intelligence:</strong> Batch analysis and research summaries utilize Gemini models via secure API channels with no data retention for training.
              </p>
            </div>

            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={() => setShowPrivacyModal(false)}
                className="btn-secondary text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
