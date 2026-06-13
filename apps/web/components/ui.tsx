import Link from "next/link";
import type { LucideIcon } from "lucide-react";

export function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  detail?: string;
  icon?: LucideIcon;
}) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-line/80 bg-white p-6 shadow-panel">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white via-white to-field/80" />
      {Icon ? (
        <span className="absolute right-6 top-6 grid size-14 place-items-center rounded-full bg-field text-indigo">
          <Icon size={26} strokeWidth={1.8} />
        </span>
      ) : null}
      <div className="relative">
        <p className="text-sm font-semibold text-ink/80">{label}</p>
        <p className="electric-text mt-3 text-5xl font-semibold tracking-normal">{value}</p>
        {detail ? <p className="mt-4 max-w-[16rem] text-sm leading-6 text-muted">{detail}</p> : null}
      </div>
    </div>
  );
}

export function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-line/80 bg-white p-5 shadow-panel">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function IconLink({ href, icon: Icon, children }: { href: string; icon: LucideIcon; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="focus-ring inline-flex items-center gap-3 rounded-lg bg-gradient-to-br from-indigo to-violet px-6 py-4 text-sm font-semibold text-white shadow-glow transition duration-300 hover:-translate-y-0.5 hover:shadow-[0_22px_52px_rgba(91,92,246,0.38)]"
    >
      <Icon size={16} />
      {children}
    </Link>
  );
}

export function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-ink/75">{label}</span>
        <span className="font-medium text-ink">{value}</span>
      </div>
      <div className="h-2 rounded-full bg-ink/10">
        <div
          className="h-2 rounded-full bg-gradient-to-r from-indigo to-violet"
          style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-white/70 p-8 text-center">
      <p className="text-lg font-semibold text-ink">{title}</p>
      <p className="mt-2 text-sm text-muted">{description}</p>
    </div>
  );
}
