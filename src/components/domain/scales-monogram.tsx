import React from "react";
import { Scale } from "lucide-react";

export function ScalesMonogram({ size = 32 }: { size?: number }) {
  return (
    <div
      style={{ width: size, height: size }}
      className="grid shrink-0 place-items-center rounded-lg border border-[var(--accent)] bg-[var(--accent-faint)] text-[var(--accent-strong)] shadow-sm"
      aria-hidden="true"
    >
      <Scale style={{ width: size * 0.55, height: size * 0.55 }} strokeWidth={1.8} />
    </div>
  );
}
