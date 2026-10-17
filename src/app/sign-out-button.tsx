"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { logout } from "@/lib/api";

export function SignOutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function signOut() {
    setBusy(true);
    setError(null);
    try {
      await logout();
      router.replace("/login");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not sign out. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" onClick={signOut} disabled={busy} className="rounded-lg border border-[#d9d8d0] bg-white/70 px-3 py-2 text-xs font-semibold text-[#52615b] hover:bg-white disabled:opacity-60">
        {busy ? "Signing out…" : "Sign out"}
      </button>
      {error && <span role="alert" className="max-w-40 text-xs text-[#863e31]">{error}</span>}
    </>
  );
}
