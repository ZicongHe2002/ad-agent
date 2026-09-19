"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, EmptyState, PageHeader, Panel, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/format";

type RiskMetrics = { samples: number; decisions: Record<string, number>; rule_matches: Record<string, number>; policy_versions: Array<Record<string, string>> };

export default function RiskPage() {
  const [metrics, setMetrics] = useState<RiskMetrics>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    try { const result = await api.get<RiskMetrics>("/metrics/risk"); setMetrics(result); setError(undefined); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    let active = true;
    void api.get<RiskMetrics>("/metrics/risk").then((result) => { if (active) setMetrics(result); })
      .catch((reason: unknown) => { if (active) setError(errorMessage(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const rate = (decision: string) => metrics?.samples ? `${Math.round((metrics.decisions[decision] ?? 0) / metrics.samples * 100)}%` : "—";
  return <>
    <PageHeader eyebrow="POLICY ENFORCEMENT" title="Risk control" description="Persisted tenant risk decisions and rule matches. These measurements do not imply that a platform is authorized or a dependency is healthy." actions={<Button disabled={loading} onClick={() => { setLoading(true); void load(); }}>{loading ? "Loading…" : "Refresh"}</Button>} />
    {error ? <div className="callout callout-danger" role="alert">{error}</div> : null}
    <div className="stats-grid"><StatCard label="Allowed" value={rate("ALLOW")} detail="Persisted decisions" tone="success" /><StatCard label="Sent to review" value={rate("REVIEW")} detail="Persisted decisions" tone="warning" /><StatCard label="Blocked" value={rate("BLOCK")} detail="Persisted decisions" tone="danger" /><StatCard label="Samples" value={metrics ? String(metrics.samples) : "—"} detail="All recorded tenant risk events" /></div>
    <Panel title="Rule matches" description="Counts reflect recorded events, not an assumed 24-hour period.">{!metrics || metrics.samples === 0 ? <EmptyState title={loading ? "Loading risk data" : error ? "Risk data unavailable" : "No risk decisions recorded"} detail="Generate and evaluate a candidate to populate this report." /> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Rule</th><th>Matches</th></tr></thead><tbody>{Object.entries(metrics.rule_matches).map(([rule, count]) => <tr key={rule}><td className="mono">{rule}</td><td><Badge>{count}</Badge></td></tr>)}</tbody></table>{Object.keys(metrics.rule_matches).length === 0 ? <div className="panel-body">No rules matched the recorded events.</div> : null}</div>}</Panel>
  </>;
}
