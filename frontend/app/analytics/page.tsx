"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge, Button, EmptyState, PageHeader, Panel, Progress, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/format";

type LatencyBucket = { count: number; p50: number | null; p90: number | null; p95: number | null; p99: number | null };
type Overview = { jobs_by_state: Record<string, number>; published_comments: number; pending_reviews: number };
type Latency = {
  unit: string;
  detection: LatencyBucket;
  generation: LatencyBucket;
  quality_and_risk: LatencyBucket;
  publish: LatencyBucket;
  end_to_end: LatencyBucket;
};
type Quality = {
  samples: number;
  anchor_coverage_rate: number;
  quality_allow_rate: number;
  quality_review_rate: number;
  quality_block_rate: number;
  generic_comment_rate: number;
  duplicate_block_rate: number;
  human_acceptance_rate: number;
  human_edit_rate: number;
};
type Ranking = {
  samples: number;
  first_comment_success_rate: number;
  top5_success_rate: number;
  chronological_rank_measurement_coverage: number;
  visible_rank_measurement_coverage: number;
};
type Metrics = { overview: Overview; latency: Latency; quality: Quality; ranking: Ranking };

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function p95(bucket: LatencyBucket): string {
  if (bucket.p95 === null) return "No samples";
  return bucket.p95 < 1_000 ? `${Math.round(bucket.p95)}ms` : `${(bucket.p95 / 1_000).toFixed(1)}s`;
}

const latencyRows: Array<[keyof Pick<Latency, "detection" | "generation" | "quality_and_risk" | "publish" | "end_to_end">, string, number]> = [
  ["detection", "Detection", 10_000],
  ["generation", "Generation", 1_800],
  ["quality_and_risk", "Quality + rule risk", 1_500],
  ["publish", "Official publish", 3_000],
  ["end_to_end", "End-to-end", 15_000],
];

export default function AnalyticsPage() {
  const [metrics, setMetrics] = useState<Metrics>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  const requestMetrics = useCallback(async (): Promise<Metrics> => {
    const [overview, latency, quality, ranking] = await Promise.all([
      api.get<Overview>("/metrics/overview"),
      api.get<Latency>("/metrics/latency"),
      api.get<Quality>("/metrics/quality"),
      api.get<Ranking>("/metrics/ranking"),
    ]);
    return { overview, latency, quality, ranking };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      setMetrics(await requestMetrics());
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, [requestMetrics]);

  useEffect(() => {
    let active = true;
    void requestMetrics()
      .then((result) => {
        if (active) setMetrics(result);
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
  }, [requestMetrics]);

  return (
    <>
      <PageHeader
        eyebrow="MEASUREMENT WITH COVERAGE"
        title="Analytics"
        description="Latency, quality, review, and chronological rank computed from persisted tenant records. Unknown rank remains visible through coverage."
        actions={<Button onClick={() => void refresh()} disabled={loading}>{loading ? "Refreshing…" : "Refresh metrics"}</Button>}
      />
      <div className="stats-grid">
        <StatCard label="Chronological first" value={metrics ? percent(metrics.ranking.first_comment_success_rate) : "—"} detail={metrics ? `${percent(metrics.ranking.chronological_rank_measurement_coverage)} measurement coverage` : "Waiting for metrics"} tone="success" />
        <StatCard label="Chronological top 5" value={metrics ? percent(metrics.ranking.top5_success_rate) : "—"} detail={metrics ? `${metrics.ranking.samples} published samples` : "Waiting for metrics"} tone="success" />
        <StatCard label="AI-ready P95" value={metrics ? p95(metrics.latency.end_to_end) : "—"} detail="Engineering target ≤ 15 seconds" tone="info" />
        <StatCard label="Human acceptance" value={metrics ? percent(metrics.quality.human_acceptance_rate) : "—"} detail={metrics ? `${percent(metrics.quality.human_edit_rate)} edited before approval` : "Waiting for metrics"} />
      </div>
      {error ? <div className="callout callout-danger" role="alert" style={{ marginBottom: 18 }}>{error}</div> : null}
      {loading && !metrics ? (
        <Panel><EmptyState title="Loading analytics" detail="Aggregating persisted pipeline, quality, and rank records…" /></Panel>
      ) : !metrics ? (
        <Panel><EmptyState title="Analytics unavailable" detail="Refresh once the API is reachable." /></Panel>
      ) : (
        <div className="content-grid">
          <div className="stack">
            <Panel title="Outcome funnel" description="Current persisted counts, without synthetic period comparisons">
              <div className="metric-list">
                <Progress label={`Quality allow · ${percent(metrics.quality.quality_allow_rate)}`} value={metrics.quality.quality_allow_rate * 100} />
                <Progress label={`Human acceptance · ${percent(metrics.quality.human_acceptance_rate)}`} value={metrics.quality.human_acceptance_rate * 100} />
                <Progress label={`Chronological top five · ${percent(metrics.ranking.top5_success_rate)}`} value={metrics.ranking.top5_success_rate * 100} />
                <Progress label={`Chronological first · ${percent(metrics.ranking.first_comment_success_rate)}`} value={metrics.ranking.first_comment_success_rate * 100} />
              </div>
            </Panel>
            <Panel title="Latency by stage" description="P95 against the documented path budget">
              {latencyRows.every(([key]) => metrics.latency[key].count === 0) ? (
                <EmptyState title="No stage timing samples" detail="Timing appears when jobs progress through persisted timeline stages." />
              ) : (
                <div className="metric-list">
                  {latencyRows.map(([key, label, target]) => {
                    const bucket = metrics.latency[key];
                    const used = bucket.p95 === null ? 0 : (bucket.p95 / target) * 100;
                    return <Progress key={key} label={`${label} · ${p95(bucket)} / ${target / 1_000}s · n=${bucket.count}`} value={used} />;
                  })}
                </div>
              )}
            </Panel>
          </div>
          <div className="stack">
            <Panel title="Quality outcomes" description={`${metrics.quality.samples} evaluated candidates`}>
              {metrics.quality.samples === 0 ? (
                <EmptyState title="No quality data" detail="Generate candidates to populate quality measurements." />
              ) : (
                <dl className="detail-list">
                  <div><dt>Anchor coverage</dt><dd>{percent(metrics.quality.anchor_coverage_rate)}</dd></div>
                  <div><dt>Quality allow</dt><dd>{percent(metrics.quality.quality_allow_rate)}</dd></div>
                  <div><dt>Sent to review</dt><dd>{percent(metrics.quality.quality_review_rate)}</dd></div>
                  <div><dt>Blocked</dt><dd>{percent(metrics.quality.quality_block_rate)}</dd></div>
                  <div><dt>Generic detected</dt><dd>{percent(metrics.quality.generic_comment_rate)}</dd></div>
                  <div><dt>Duplicate blocked</dt><dd>{percent(metrics.quality.duplicate_block_rate)}</dd></div>
                </dl>
              )}
            </Panel>
            <Panel title="Rank coverage" actions={<Badge>{metrics.ranking.samples} SAMPLES</Badge>}>
              <div className="metric-list">
                <Progress label="Chronological rank" value={metrics.ranking.chronological_rank_measurement_coverage * 100} />
                <Progress label="Visible rank" value={metrics.ranking.visible_rank_measurement_coverage * 100} />
                <div className="callout">Unmeasured ranks are excluded from success-rate denominators and reported through coverage.</div>
              </div>
            </Panel>
            <Panel title="Pipeline totals">
              <dl className="detail-list">
                <div><dt>Published</dt><dd><Badge tone="success">{metrics.overview.published_comments}</Badge></dd></div>
                <div><dt>Pending review</dt><dd><Badge tone={metrics.overview.pending_reviews ? "warning" : "success"}>{metrics.overview.pending_reviews}</Badge></dd></div>
                <div><dt>Job states represented</dt><dd>{Object.keys(metrics.overview.jobs_by_state).length}</dd></div>
              </dl>
            </Panel>
            <Panel title="Metric guardrails"><div className="panel-body"><div className="callout callout-warning">No detector-evasion, human-probability, stealth, or review-evasion metric is collected.</div></div></Panel>
          </div>
        </div>
      )}
    </>
  );
}
