import type { Metadata } from "next";
import "./globals.css";
import { AuthRedirector } from "@/app/auth-redirector";
import { SourcePeekDrawer } from "@/components/domain/source-peek-drawer";
import { CommandPalette } from "@/components/ui/command-palette";

export const metadata: Metadata = {
  title: "AI Legal Decision Intelligence Engine",
  description:
    "A privacy-first case-analysis workspace for Indian advocates, supporting connected, source-grounded document analysis.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full antialiased" data-theme="light">
      <head>
        <link rel="preconnect" href="https://api.fontshare.com" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://api.fontshare.com/v2/css?f[]=satoshi@400,500,600,700,800,900&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&family=Poppins:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-full font-sans antialiased bg-[var(--bg)] text-[var(--text)] selection:bg-[var(--primary-tint)] selection:text-[var(--primary)]">
        <AuthRedirector />
        {children}
        <SourcePeekDrawer />
        <CommandPalette />
      </body>
    </html>
  );
}
