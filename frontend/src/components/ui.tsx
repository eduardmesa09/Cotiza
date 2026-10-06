// Piezas de interfaz compartidas: tarjetas, botones, etiquetas, campos y estados vacíos.

import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import type { Evaluation, QuoteState } from "../lib/types";

const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

// --- Tarjeta y encabezados ------------------------------------------------------------

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cx("rounded-2xl bg-surface p-5 shadow-card", className)}>{children}</section>;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="text-base font-semibold text-ink">{children}</h2>
      {aside}
    </div>
  );
}

// --- Botones --------------------------------------------------------------------------

type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-white shadow-sm hover:bg-brand-mid",
  secondary: "border border-line bg-surface text-ink hover:bg-canvas",
  ghost: "text-muted hover:bg-canvas hover:text-ink",
  danger: "bg-bad text-white hover:bg-red-700",
  success: "bg-ok text-white hover:bg-green-700",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  busy?: boolean;
  icon?: ReactNode;
  size?: "sm" | "md";
}

export function Button({ variant = "secondary", busy, icon, size = "md", children, className, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full font-medium transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
        "disabled:cursor-not-allowed disabled:opacity-45",
        size === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm",
        VARIANTS[variant],
        className,
      )}
    >
      {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

// --- Etiquetas ------------------------------------------------------------------------

type Tone = "neutral" | "brand" | "ok" | "warn" | "bad" | "info";

const TONES: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-700",
  brand: "bg-sky-100 text-brand-dark",
  ok: "bg-green-100 text-green-800",
  warn: "bg-amber-100 text-amber-900",
  bad: "bg-red-100 text-red-800",
  info: "bg-cyan-100 text-cyan-900",
};

export function Badge({ tone = "neutral", children, icon }: { tone?: Tone; children: ReactNode; icon?: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium", TONES[tone])}>
      {icon}
      {children}
    </span>
  );
}

const STATE: Record<QuoteState, { label: string; tone: Tone }> = {
  BORRADOR: { label: "Borrador", tone: "neutral" },
  CALCULADA: { label: "Calculada", tone: "brand" },
  PENDIENTE_APROBACION: { label: "Pendiente de aprobación", tone: "warn" },
  EMITIDA: { label: "Emitida", tone: "info" },
  EN_SEGUIMIENTO: { label: "En seguimiento", tone: "info" },
  GANADA: { label: "Ganada", tone: "ok" },
  PERDIDA: { label: "Perdida", tone: "bad" },
  VENCIDA: { label: "Vencida", tone: "neutral" },
};

export const STATE_LABEL = Object.fromEntries(Object.entries(STATE).map(([k, v]) => [k, v.label])) as Record<QuoteState, string>;

export function StateBadge({ state, replaced }: { state: QuoteState; replaced?: boolean }) {
  if (replaced) return <Badge tone="neutral">Reemplazada</Badge>;
  return <Badge tone={STATE[state].tone}>{STATE[state].label}</Badge>;
}

const EVALUATION: Record<Evaluation, { label: string; tone: Tone }> = {
  LISTA_PARA_EMITIR: { label: "Lista para emitir", tone: "ok" },
  REQUIERE_APROBACION: { label: "Requiere aprobación", tone: "warn" },
  NO_EMITIBLE: { label: "No emitible", tone: "bad" },
};

export function EvaluationBadge({ evaluation }: { evaluation: Evaluation }) {
  return <Badge tone={EVALUATION[evaluation].tone}>{EVALUATION[evaluation].label}</Badge>;
}

// --- Avisos ---------------------------------------------------------------------------

const NOTICE: Record<"ok" | "warn" | "bad" | "info", { box: string; icon: ReactNode }> = {
  ok: { box: "border-green-200 bg-green-50 text-green-900", icon: <CheckCircle2 className="size-5 shrink-0 text-ok" aria-hidden /> },
  warn: { box: "border-amber-200 bg-amber-50 text-amber-950", icon: <AlertTriangle className="size-5 shrink-0 text-amber-600" aria-hidden /> },
  bad: { box: "border-red-200 bg-red-50 text-red-900", icon: <XCircle className="size-5 shrink-0 text-bad" aria-hidden /> },
  info: { box: "border-sky-200 bg-sky-50 text-brand-dark", icon: <Info className="size-5 shrink-0 text-brand" aria-hidden /> },
};

export function Notice({ tone, title, children, action }: { tone: "ok" | "warn" | "bad" | "info"; title?: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div role={tone === "bad" ? "alert" : "status"} className={cx("flex items-start gap-3 rounded-xl border px-4 py-3 text-sm", NOTICE[tone].box)}>
      {NOTICE[tone].icon}
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={title ? "mt-0.5" : ""}>{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function ErrorNotice({ message, onClose }: { message: string | null; onClose?: () => void }) {
  if (!message) return null;
  return (
    <Notice
      tone="bad"
      action={
        onClose && (
          <button type="button" onClick={onClose} aria-label="Cerrar aviso" className="rounded p-0.5 hover:bg-red-100">
            <X className="size-4" />
          </button>
        )
      }
    >
      {message}
    </Notice>
  );
}

export function Loading({ label = "Cargando…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted" role="status">
      <Loader2 className="size-5 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 py-14 text-center">
      {icon && <div className="rounded-full bg-canvas p-3 text-muted">{icon}</div>}
      <p className="font-medium text-ink">{title}</p>
      {children && <p className="max-w-md text-sm text-muted">{children}</p>}
    </div>
  );
}

// --- Campos de formulario -------------------------------------------------------------

const FIELD = "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-slate-400 focus:border-brand focus:outline-2 focus:outline-brand/25 disabled:bg-canvas disabled:text-muted";

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={cx(FIELD, className)} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={cx(FIELD, className)}>
      {children}
    </select>
  );
}

// --- Tabla y ventana modal ------------------------------------------------------------

export function Table({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">{head}</thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
    </div>
  );
}

export const TH = "px-3 py-2.5 font-medium";
export const TD = "px-3 py-3 align-top";

export function Modal({ title, onClose, children, footer }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy/50 p-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="w-full max-w-lg rounded-2xl bg-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Cerrar" className="rounded-full p-1.5 text-muted hover:bg-canvas">
            <X className="size-5" />
          </button>
        </div>
        <div className="space-y-4 px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-4">{footer}</div>}
      </div>
    </div>
  );
}
