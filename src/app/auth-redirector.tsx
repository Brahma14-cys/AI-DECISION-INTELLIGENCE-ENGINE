"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { ApiRequestError, getAdvocateSession, getAuthSetupStatus } from "@/lib/api";

export function AuthRedirector() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (pathname === "/login" || pathname === "/signup") return;

    let active = true;
    function redirectToLogin() {
      if (pathname !== "/login") router.replace("/login");
    }

    // Register before checking the session so a page request that receives
    // 401 cannot dispatch an auth event before this listener is installed.
    window.addEventListener("legal-engine:auth-required", redirectToLogin);

    void getAdvocateSession().catch(async (reason: unknown) => {
      if (active && reason instanceof ApiRequestError && reason.status === 401) {
        redirectToLogin();
        return;
      }
      if (active && reason instanceof ApiRequestError && reason.status === 503) {
        const setup = await getAuthSetupStatus().catch(() => null);
        if (active && setup && !setup.configured) router.replace("/signup");
      }
    });

    return () => {
      active = false;
      window.removeEventListener("legal-engine:auth-required", redirectToLogin);
    };
  }, [pathname, router]);

  return null;
}
