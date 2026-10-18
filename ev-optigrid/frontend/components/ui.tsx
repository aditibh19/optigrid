import type { ReactNode } from "react";
import type { DataSource } from "@/services/api";

export const CURRENCY = "₹";

export function Card({ title, aside, children, className = "" }: {
  title?: string; aside?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && (
        <div className="card-head">
          <h2>{title}</h2>
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="page-head">
      <h1>{title}</h1>
      {children && <p>{children}</p>}
    </header>
  );
}

let fieldCounter = 0;
const nextId = () => `f${++fieldCounter}`;

/** Number input that lets the user clear the box while typing (value becomes NaN). */
export function NumberField({ label, value, onChange, min, max, step, suffix, hint }: {
  label: string; value: number; onChange: (v: number) => void;
  min?: number; max?: number; step?: number; suffix?: string; hint?: string;
}) {
  const id = nextId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="input-wrap">
        <input id={id} type="number" inputMode="decimal" value={Number.isFinite(value) ? value : ""}
          min={min} max={max} step={step ?? "any"}
          onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))} />
        {suffix && <span className="suffix">{suffix}</span>}
      </div>
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function TextField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const id = nextId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="input-wrap"><input id={id} type="text" value={value} onChange={(e) => onChange(e.target.value)} /></div>
    </div>
  );
}

export function SelectField<T extends string>({ label, value, onChange, options, hint }: {
  label: string; value: T; onChange: (v: T) => void;
  options: { value: T; label: string }[]; hint?: string;
}) {
  const id = nextId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="input-wrap">
        <select id={id} value={value} onChange={(e) => onChange(e.target.value as T)}>
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "error" | "warn" | "good"; children: ReactNode }) {
  return <div className={`notice ${tone === "info" ? "" : tone}`} role={tone === "error" ? "alert" : undefined}>{children}</div>;
}

const SOURCE_LABEL: Record<DataSource, string> = {
  real: "Live data", predicted: "Model forecast", simulated: "Simulated", demo: "Demo data",
};
/** Spec §29: simulated / demo data must never look like live data. */
export function SourceBadge({ source }: { source: DataSource }) {
  return <span className={`badge ${source}`}>{SOURCE_LABEL[source] ?? source}</span>;
}

export function Stat({ label, value, unit, tone }: {
  label: string; value: ReactNode; unit?: string; tone?: "signal" | "good" | "bad" | "warn";
}) {
  return (
    <div className={`stat ${tone ?? ""}`}>
      <span className="label">{label}</span>
      <span className="value">{value}{unit && <small>{unit}</small>}</span>
    </div>
  );
}

export const allFinite = (o: object) => Object.values(o).every((v) => typeof v !== "number" || Number.isFinite(v));
export const errorMessage = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");
