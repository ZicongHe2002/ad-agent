"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge, Button, EmptyState, PageHeader, Panel, Progress, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/format";

type LatencyBucket = { count: number; p50: number | null; p90: number | null; p95: number | null; p99: number | null };
type Overview = {
  jobs_by_state: Record<string, number>;
  published_comments: number;
  pending_reviews: number;
  process_counters: Record<string, number>;
  activity_counts: Record<string, number>;
};
type Latency = {
  unit: "milliseconds";
  detection: LatencyBucket;
  generation: LatencyBucket;
  quality_and_risk: LatencyBucket;
  publish: LatencyBucket;
  end_to_end: LatencyBucket;
};
type Quality = {
  samples: number;
  quality_allow_rate: number;
  quality_review_rate: number;
  quality_block_rate: number;
  human_acceptance_rate: number;
  human_edit_rate: number;
};

type Ranking = { first_comment_success_rate: number; top5_success_rate: number; chronological_rank_measurement_coverage: number; samples: number };
const terminalStates = new Set(["PUBLISHED", "BLOCKED", "FAILED", "SKIPPED"]);
const latencyTargets: Array<[keyof Pick<Latency, "detection" | "generation" | "quality_and_risk" | "publish" | "end_to_end">, string, number]> = [
  ["detection", "Detection", 10_000],
  ["generation", "Generation", 1_800],
  ["quality_and_risk", "Quality + risk", 1_500],
  ["publish", "Official publish", 3_000],
  ["end_to_end", "End-to-end", 15_000],
];

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function duration(value: number | null): string {
  if (value === null) return "No samples";
  return value < 1_000 ? `${Math.round(value)}ms` : `${(value / 1_000).toFixed(1)}s`;
}

function stateTone(state: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (state === "PUBLISHED") return "success";
  if (["FAILED", "SKIPPED"].includes(state)) return "danger";
  if (["WAITING_REVIEW", "PUBLISH_UNCERTAIN", "READY_FOR_RETRY", "MANUAL"].includes(state)) return "warning";
  return "info";
}

export default function DashboardPage() {
  const [overview, setOverview] = useState<Overview>();
  const [latency, setLatency] = useState<Latency>();
  const [quality, setQuality] = useState<Quality>();
  const [ranking, setRanking] = useState<Ranking>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  const applyData = useCallback((result: [Overview, Latency, Quality, Ranking]) => {
    setOverview(result[0]);
    setLatency(result[1]);
    setQuality(result[2]);
    setRanking(result[3]);
  }, []);

  const loadMetrics = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      applyData(await Promise.all([
        api.get<Overview>("/metrics/overview"),
        api.get<Latency>("/metrics/latency"),
        api.get<Quality>("/metrics/quality"),
        api.get<Ranking>("/metrics/ranking"),
      ]));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, [applyData]);

  useEffect(() => {
    let active = true;
    void Promise.all([
      api.get<Overview>("/metrics/overview"),
      api.get<Latency>("/metrics/latency"),
      api.get<Quality>("/metrics/quality"),
      api.get<Ranking>("/metrics/ranking"),
    ])
      .then((result) => {
        if (active) applyData(result);
      })
      .catch((requestError: unknown) => {
        if (active) setError(errorMessage(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [applyData]);

  const states = useMemo(
    () => Object.entries(overview?.jobs_by_state ?? {}).sort((left, right) => right[1] - left[1]),
    [overview],
  );
  const totalJobs = states.reduce((total, [, count]) => total + count, 0);
  const activeJobs = states.reduce((total, [state, count]) => total + (terminalStates.has(state) ? 0 : count), 0);

  return (
    <>
      <PageHeader
        eyebrow="OPERATIONS OVERVIEW"
        title="Operations dashboard"
        description="Live tenant metrics for pipeline volume, review pressure, quality decisions, and latency budgets."
        actions={<Button onClick={() => void loadMetrics()} disabled={loading}>{loading ? "Refreshing…" : "Refresh metrics"}</Button>}
      />
      <div className="stats-grid">
        <StatCard label="Pipeline jobs" value={String(totalJobs)} detail={`${activeJobs} currently non-terminal`} tone="info" />
        <StatCard label="Published comments" value={String(overview?.published_comments ?? 0)} detail="Confirmed in the publication ledger" tone="success" />
        <StatCard label="Human acceptance" value={quality ? percent(quality.human_acceptance_rate) : "—"} detail={quality ? `${percent(quality.human_edit_rate)} edited before approval` : "No quality response yet"} tone="success" />
        <StatCard label="Waiting review" value={String(overview?.pending_reviews ?? 0)} detail="Pending human decisions" tone={(overview?.pending_reviews ?? 0) > 0 ? "warning" : "neutral"} />
      </div>
      <div className="stats-grid">
        <StatCard label="First comment" value={ranking && ranking.chronological_rank_measurement_coverage > 0 ? percent(ranking.first_comment_success_rate) : "—"} detail="Only measured chronological ranks" />
        <StatCard label="Top 5" value={ranking && ranking.chronological_rank_measurement_coverage > 0 ? percent(ranking.top5_success_rate) : "—"} detail="Unknown ranks are excluded" />
        <StatCard label="Rank coverage" value={ranking ? percent(ranking.chronological_rank_measurement_coverage) : "—"} detail={ranking ? `${ranking.samples} published comments` : "Loading measurements"} />
      </div>
      {error ? <div className="callout callout-danger" role="alert" style={{ marginBottom: 18 }}>{error}</div> : null}
      {loading && !overview ? (
        <Panel><EmptyState title="Loading operational metrics" detail="Reading overview, latency, and quality aggregates from the API…" /></Panel>
      ) : !overview || !latency || !quality ? (
        <Panel><EmptyState title="Metrics unavailable" detail="Refresh after the API and database are ready." /></Panel>
      ) : (
        <div className="content-grid">
          <div className="stack">
            <Panel title="Pipeline state ledger" description="Persisted comment jobs grouped by current state" actions={<Badge tone={activeJobs > 0 ? "info" : "success"}>{activeJobs > 0 ? `${activeJobs} IN FLIGHT` : "IDLE"}</Badge>}>
              {states.length === 0 ? (
                <EmptyState title="No pipeline jobs" detail="Run the demo workflow or poll an active creator to populate this view." />
              ) : (
                <div className="data-table-wrap">
                  <table className="data-table">
                    <thead><tr><th>State</th><th>Jobs</th><th>Share</th><th>Lifecycle</th></tr></thead>
                    <tbody>
                      {states.map(([state, count]) => (
                        <tr key={state}>
                          <td><Badge tone={stateTone(state)}>{state}</Badge></td>
                          <td>{count}</td>
                          <td>{totalJobs ? percent(count / totalJobs) : "0%"}</td>
                          <td>{terminalStates.has(state) ? "Terminal" : "In progress"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
            <Panel title="Latency envelope" description="Observed P95 values against engineering targets">
              {latencyTargets.every(([key]) => latency[key].count === 0) ? (
                <EmptyState title="No latency samples" detail="Stage timing appears after persisted jobs progress through the pipeline." />
              ) : (
                <div className="metric-list">
                  {latencyTargets.map(([key, label, target]) => {
                    const value = latency[key].p95;
                    const budget = value === null ? 0 : Math.round((value / target) * 100);
                    return <Progress key={key} label={`${label} · P95 ${duration(value)} / ${duration(target)}`} value={budget} />;
                  })}
                </div>
              )}
            </Panel>
          </div>
          <div className="stack">
            <Panel title="Quality posture" description={`${quality.samples} evaluated candidates`}>
              {quality.samples === 0 ? (
                <EmptyState title="No quality evaluations" detail="Quality outcomes appear after a comment candidate is generated." />
              ) : (
                <dl className="detail-list">
                  <div><dt>Allowed</dt><dd><Badge tone="success">{percent(quality.quality_allow_rate)}</Badge></dd></div>
                  <div><dt>Sent to review</dt><dd><Badge tone="warning">{percent(quality.quality_review_rate)}</Badge></dd></div>
                  <div><dt>Blocked</dt><dd><Badge tone="danger">{percent(quality.quality_block_rate)}</Badge></dd></div>
                  <div><dt>Human acceptance</dt><dd>{percent(quality.human_acceptance_rate)}</dd></div>
                </dl>
              )}
            </Panel>
            <Panel title="Persisted activity" description="Committed events across API and worker processes">
              {Object.keys(overview.activity_counts).length === 0 ? (
                <EmptyState title="No activity yet" detail="Worker events appear here after their transactions commit." />
              ) : (
                <ul className="activity-list">
                  {Object.entries(overview.activity_counts).map(([name, count]) => (
                    <li key={name}><strong>{name}</strong><span>Observed transition count</span><time>{count}</time></li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}
