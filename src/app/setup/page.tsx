"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Scale, Lock, Eye, EyeOff, Check } from "lucide-react";
import { getAuthSetupStatus, registerAdvocate } from "@/lib/api";
import { ThemeToggle } from "@/components/ui/theme-toggle";

export default function SetupPage() {
  const router = useRouter();
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [disclaimerAccepted, setDisclaimerAccepted] = useState(false);

  useEffect(() => {
    getAuthSetupStatus()
      .then((status) => {
        setConfigured(status.configured);
      })
      .catch(() => {
        setConfigured(true);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  const hasMinLength = password.length >= 12;
  const hasUppercase = /[A-Z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);
  const passwordsMatch = password.length > 0 && password === confirmPassword;

  // Strength score: 0 to 4
  const strengthScore = [hasMinLength, hasUppercase, hasNumber, hasSpecial].filter(Boolean).length;
  const isFormValid = hasMinLength && disclaimerAccepted && passwordsMatch;

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!isFormValid) return;

    setSubmitting(true);
    setError(null);
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email") ?? "").trim();

    try {
      await registerAdvocate(email, password);
      window.location.replace("/cases");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-[var(--bg)] p-4">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--brass)] border-t-transparent" />
      </main>
    );
  }

  // If already configured, show lock state
  if (configured) {
    return (
      <main className="grid min-h-screen place-items-center bg-[var(--bg)] p-4">
        <div className="w-full max-w-sm rounded-lg border border-[var(--border)] bg-[var(--surface)] p-8 text-center shadow-[var(--shadow-drawer)]">
          <div className="mx-auto grid size-12 place-items-center rounded-full bg-[var(--surface-2)] text-[var(--brass)]">
            <Lock className="size-6" strokeWidth={1.5} />
          </div>
          <h1 className="mt-4 font-serif text-xl font-medium text-[var(--text)]">
            This installation is already set up
          </h1>
          <p className="mt-2 text-xs leading-relaxed text-[var(--text-muted)]">
            The engine supports a single advocate account. Please sign in with your configured credentials.
          </p>
          <div className="mt-6">
            <Link href="/signin" className="btn-primary w-full text-xs font-medium">
              Go to sign in
            </Link>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="grid min-h-screen grid-cols-1 lg:grid-cols-2 bg-[var(--bg)]">
      {/* Left 50%: Setup Form */}
      <section className="flex flex-col justify-between p-6 sm:p-12 overflow-y-auto">
        <div className="flex items-center justify-between">
          <Scale className="size-7 text-[var(--brass)]" strokeWidth={1.75} />
          <ThemeToggle />
        </div>

        <div className="mx-auto my-auto w-full max-w-[420px] py-8">
          <div className="mb-7">
            <h1 className="font-serif text-[32px] font-medium tracking-tight text-[var(--text)] leading-tight">
              Create the advocate account
            </h1>
            <p className="mt-2 text-sm text-[var(--text-muted)]">
              This installation supports a single advocate account.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="rounded-md border border-[var(--danger)]/30 bg-[var(--surface)] p-3 text-xs text-[var(--danger)]">
                {error}
              </div>
            )}

            <div>
              <label htmlFor="full_name" className="block text-[13px] font-medium text-[var(--text)]">
                Full name
              </label>
              <input
                id="full_name"
                name="full_name"
                type="text"
                required
                placeholder="Senior Advocate / Counsel"
                className="input-field mt-1 h-9 w-full"
              />
            </div>

            <div>
              <label htmlFor="enrolment" className="block text-[13px] font-medium text-[var(--text)]">
                Enrolment number <span className="text-[var(--text-faint)] font-normal">(optional)</span>
              </label>
              <input
                id="enrolment"
                name="enrolment"
                type="text"
                placeholder="e.g. D/1234/2012"
                className="input-field mt-1 h-9 w-full"
              />
              <p className="mt-1 text-[11px] text-[var(--text-muted)]">Bar Council enrolment number.</p>
            </div>

            <div>
              <label htmlFor="email" className="block text-[13px] font-medium text-[var(--text)]">
                Email address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                required
                placeholder="advocate@chambers.in"
                className="input-field mt-1 h-9 w-full"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-[13px] font-medium text-[var(--text)]">
                Password
              </label>
              <div className="relative mt-1">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 12 characters"
                  className="input-field h-9 w-full pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-2 text-[var(--text-muted)] hover:text-[var(--text)]"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>

              {/* 4-Segment Strength Bar */}
              {password.length > 0 && (
                <div className="mt-2 space-y-1">
                  <div className="grid grid-cols-4 gap-1.5 h-1">
                    {[1, 2, 3, 4].map((step) => (
                      <div
                        key={step}
                        className={`h-full rounded-full transition ${
                          strengthScore >= step
                            ? strengthScore <= 2
                              ? "bg-[var(--warning)]"
                              : "bg-[var(--success)]"
                            : "bg-[var(--border)]"
                        }`}
                      />
                    ))}
                  </div>
                  <p className="text-[11px] text-[var(--text-muted)]">
                    {hasMinLength ? "✓ 12+ characters" : "Must be at least 12 characters"}
                  </p>
                </div>
              )}
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-[13px] font-medium text-[var(--text)]">
                Confirm password
              </label>
              <input
                id="confirmPassword"
                name="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Repeat password"
                className="input-field mt-1 h-9 w-full"
              />
              {confirmPassword.length > 0 && !passwordsMatch && (
                <p className="mt-1 text-[11px] text-[var(--danger)]">Passwords do not match</p>
              )}
            </div>

            <div className="pt-2">
              <label className="flex items-start gap-2.5 cursor-pointer text-xs leading-relaxed text-[var(--text)]">
                <input
                  type="checkbox"
                  checked={disclaimerAccepted}
                  onChange={(e) => setDisclaimerAccepted(e.target.checked)}
                  className="mt-0.5 rounded border-[var(--border-strong)] text-[var(--primary)] focus:ring-[var(--brass)]"
                />
                <span>
                  I understand this tool supports my analysis and does not make legal decisions.
                </span>
              </label>
            </div>

            <button
              type="submit"
              disabled={submitting || !isFormValid}
              className="btn-primary h-10 w-full text-sm font-medium mt-4"
            >
              {submitting ? "Creating account…" : "Create account"}
            </button>
          </form>
        </div>

        <div className="mx-auto w-full max-w-[420px] pt-4 text-center text-xs text-[var(--text-muted)]">
          Already configured?{" "}
          <Link href="/signin" className="font-medium text-[var(--primary)] hover:underline">
            Sign in instead
          </Link>
        </div>
      </section>

      {/* Right 50%: Solid Deep Oxblood Panel */}
      <section className="relative hidden lg:flex flex-col justify-end p-12 bg-[#3F1220] dark:bg-[#2A0E16] text-[#FAF9F6] overflow-hidden">
        <div className="pointer-events-none absolute -right-16 -top-16 select-none opacity-[0.06] text-[#D3CCBD]">
          <Scale className="size-[560px]" strokeWidth={1} />
        </div>

        <div className="relative z-10 max-w-md">
          <p className="font-serif text-2xl font-medium tracking-tight text-[#FAF9F6] leading-relaxed">
            “Evidence, organised. Decisions, yours.”
          </p>
          <div className="brass-hairline mt-4 w-12 opacity-60" />
        </div>
      </section>
    </main>
  );
}
