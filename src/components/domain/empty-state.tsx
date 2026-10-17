import { LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="py-16 text-center">
      <div className="mx-auto grid size-10 place-items-center text-[var(--text-faint)]">
        <Icon className="size-8 stroke-[1.5]" />
      </div>
      <h2 className="mt-3 text-base font-semibold text-[var(--text)]">{title}</h2>
      <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-[var(--text-muted)]">
        {description}
      </p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
