import { ApiError } from "./api";
import type { BadgeTone } from "./types";

const dateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "medium",
});

const relativeFormatter = new Intl.RelativeTimeFormat("en-US", { numeric: "auto" });

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : dateTimeFormatter.format(date);
}

export function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const differenceSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const intervals: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, seconds] of intervals) {
    if (Math.abs(differenceSeconds) >= seconds) {
      return relativeFormatter.format(Math.round(differenceSeconds / seconds), unit);
    }
  }
  return relativeFormatter.format(differenceSeconds, "second");
}

export function formatPercent(value: number | string | null | undefined): number {
  const numeric = Number(value ?? 0);
  return Math.round(Math.max(0, Math.min(1, numeric)) * 100);
}

export function shortId(value: string | null | undefined, length = 8): string {
  if (!value) return "—";
  return value.length <= length ? value : `${value.slice(0, length)}…`;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const suffix = error.traceId ? ` (trace ${shortId(error.traceId)})` : "";
    return `${error.message}${suffix}`;
  }
  return error instanceof Error ? error.message : "The request could not be completed.";
}

export function statusTone(status: string): BadgeTone {
  if (
    [
      "ACTIVE",
      "ALLOW",
      "APPROVED",
      "EDITED_APPROVED",
      "PUBLISHED",
      "SELECTED",
      "DECLARED",
      "PLATFORM_APPLIED",
      "EXACT",
    ].includes(status)
  ) {
    return "success";
  }
  if (
    [
      "PENDING",
      "PAUSED",
      "REVIEW",
      "REQUIRED_PENDING",
      "UNKNOWN",
      "ESTIMATED",
      "PARTIAL",
    ].includes(status)
  ) {
    return "warning";
  }
  if (["ERROR", "BLOCK", "BLOCKED", "REJECTED", "DELETED", "EXPIRED"].includes(status)) {
    return "danger";
  }
  if (["GENERATED", "AI_ASSISTED_HUMAN_EDITED"].includes(status)) return "info";
  return "neutral";
}
