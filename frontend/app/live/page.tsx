"use client";

import { useEffect, useState } from "react";
import { Badge, Button, EmptyState, PageHeader, Panel, StatCard } from "@/components/ui";
import { useEventStream } from "@/lib/sse";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/format";

type LiveOverview = { active_jobs: number; critical_active_jobs: number; oldest_critical_seconds: number | null };

function summarize(payload: Record<string, unknown> | undefined): string {
  if (!payload) return "No event payload";
  return Object.entries(payload).map(([key, value]) => `${key}: ${String(value)}`).join(" · ");
}

export default function LivePage() {
  const [creatorId, setCreatorId] = useState("");
  const [postId, setPostId] = useState("");
  const { events, state, retryCount, clear } = useEventStream({ creator_id: creatorId || undefined, post_id: postId || undefined });
  const [overview, setOverview] = useState<LiveOverview>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const result = await api.get<LiveOverview>("/metrics/overview");
        if (active) { setOverview(result); setError(undefined); }
      } catch (reason) { if (active) setError(errorMessage(reason)); }
    };
    void load();
    const timer = setInterval(() => void load(), 10_000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  const rows = events;

  return (
    <>
      <PageHeader
        eyebrow="REAL-TIME EVENT STREAM"
        title="Live operations"
        description="Follow detection, analysis, review, and publish decisions as they happen. The authenticated stream reconnects automatically without bypassing authorization."
        actions={<div className={`stream-status ${state}`}><span />{state === "open" ? "Connected" : state === "retrying" ? `Reconnecting · attempt ${retryCount}` : state}</div>}
      />
      <div className="stats-grid">
        <StatCard label="Stream status" value={state === "open" ? "Live" : "Standby"} detail={state === "retrying" ? `Retry attempt ${retryCount}` : "Heartbeat expected every 15s"} tone={state === "open" ? "success" : "warning"} />
        <StatCard label="Events buffered" value={String(events.length)} detail="Newest 100 retained in browser" />
        <StatCard label="Pipeline active" value={overview ? String(overview.active_jobs) : "—"} detail={overview ? `${overview.critical_active_jobs} FAST jobs · tenant scope` : "Loading committed job states"} tone="info" />
        <StatCard label="Oldest FAST job" value={overview?.oldest_critical_seconds == null ? "—" : `${Math.round(overview.oldest_critical_seconds)}s`} detail="Age includes human review waits" />
      </div>
      {error ? <div className="callout callout-danger" role="alert">{error}</div> : null}
      {state === "error" ? <div className="callout callout-danger" role="alert">Stream authorization failed. Sign in again to reconnect.</div> : null}
      <Panel title="Event timeline" description="Authenticated events from the durable timeline" actions={<Button variant="ghost" onClick={clear}>Clear buffer</Button>}>
        <div className="filter-bar">
          <input className="input" aria-label="Creator ID filter" placeholder="Filter creator ID" value={creatorId} onChange={(event) => setCreatorId(event.target.value)} />
          <input className="input" aria-label="Post ID filter" placeholder="Filter post ID" value={postId} onChange={(event) => setPostId(event.target.value)} />
          <Badge tone={state === "open" ? "success" : "warning"}>{state === "open" ? "CONNECTED" : "NOT CONNECTED"}</Badge>
        </div>
        {rows.length ? (
          <ul className="timeline">
            {rows.map((event) => (
              <li key={event.event_id}>
                <time>{new Date(event.occurred_at).toLocaleTimeString()}</time>
                <div><strong>{event.event_type}</strong><p>{summarize(event.payload)}</p></div>
                <code>{event.post_id ?? "—"}</code>
              </li>
            ))}
          </ul>
        ) : <EmptyState title="Waiting for events" detail="The connection is open. New events will appear here without refreshing the page." />}
      </Panel>
    </>
  );
}
