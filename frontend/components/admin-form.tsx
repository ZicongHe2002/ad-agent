import type { ChangeEventHandler, ReactNode } from "react";

export function AdminMessages({ error, notice }: { error?: string; notice?: string }) {
  if (!error && !notice) return null;
  return (
    <div className="stack" style={{ marginBottom: 18 }}>
      {error ? <div className="callout callout-danger" role="alert">{error}</div> : null}
      {notice ? <div className="callout" role="status">{notice}</div> : null}
    </div>
  );
}

export function CheckboxField({
  id,
  label,
  detail,
  checked,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  detail?: ReactNode;
  checked: boolean;
  disabled?: boolean;
  onChange: ChangeEventHandler<HTMLInputElement>;
}) {
  return (
    <label
      htmlFor={id}
      className="callout"
      style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 10, alignItems: "start" }}
    >
      <input id={id} type="checkbox" checked={checked} disabled={disabled} onChange={onChange} />
      <span>
        <strong style={{ display: "block", color: "var(--text)" }}>{label}</strong>
        {detail ? <span style={{ display: "block", marginTop: 4, color: "var(--muted)" }}>{detail}</span> : null}
      </span>
    </label>
  );
}

export function TextListField({
  id,
  label,
  value,
  onChange,
  placeholder,
  detail = "One value per line.",
}: {
  id: string;
  label: string;
  value: string;
  onChange: ChangeEventHandler<HTMLTextAreaElement>;
  placeholder?: string;
  detail?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea id={id} className="textarea" value={value} onChange={onChange} placeholder={placeholder} />
      <small style={{ color: "var(--muted)" }}>{detail}</small>
    </div>
  );
}

export function JsonObjectField({
  id,
  label,
  value,
  onChange,
  detail = "Enter a JSON object. It is validated before submission.",
}: {
  id: string;
  label: string;
  value: string;
  onChange: ChangeEventHandler<HTMLTextAreaElement>;
  detail?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea id={id} className="textarea mono" value={value} onChange={onChange} spellCheck={false} />
      <small style={{ color: "var(--muted)" }}>{detail}</small>
    </div>
  );
}

export function splitLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseJsonObject(value: string, label: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value || "{}");
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${label} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}

export function parseJsonArray(value: string, label: string): Array<Record<string, unknown>> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value || "[]");
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
  if (!Array.isArray(parsed) || parsed.some((item) => !item || Array.isArray(item) || typeof item !== "object")) {
    throw new Error(`${label} must be a JSON array of objects.`);
  }
  return parsed as Array<Record<string, unknown>>;
}

export function toDateTimeInput(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export function toIsoDateTime(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error("Date and time values must be valid.");
  return date.toISOString();
}
