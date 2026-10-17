"use client";

import React from "react";

export function PageShell({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`space-y-6 ${className}`}>
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  badge,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  badge?: React.ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2.5">
          <h1 className="font-serif text-[28px] font-medium tracking-tight text-[var(--text)] leading-tight">
            {title}
          </h1>
          {badge}
        </div>
        {description && (
          <p className="mt-1 text-sm text-[var(--text-muted)] max-w-2xl leading-relaxed">
            {description}
          </p>
        )}
      </div>

      {actions && (
        <div className="flex items-center gap-2.5 shrink-0 sm:pt-1">
          {actions}
        </div>
      )}
    </header>
  );
}

export function PageToolbar({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-wrap items-center justify-between gap-3 ${className}`}>
      {children}
    </div>
  );
}

export function PageBody({
  children,
  variant = "default",
  className = "",
}: {
  children: React.ReactNode;
  variant?: "default" | "fill";
  className?: string;
}) {
  if (variant === "fill") {
    return (
      <div className={`flex flex-col flex-1 min-h-[calc(100vh-240px)] ${className}`}>
        {children}
      </div>
    );
  }

  return (
    <div className={`space-y-6 ${className}`}>
      {children}
    </div>
  );
}

export function PageFootnote({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <footer className="hairline pt-4 text-xs text-[var(--text-muted)] flex items-center justify-between">
      <div className={`flex items-center gap-2 ${className}`}>
        {children}
      </div>
    </footer>
  );
}
