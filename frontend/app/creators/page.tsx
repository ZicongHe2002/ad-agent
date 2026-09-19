"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Button, EmptyState, PageHeader, Panel, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage, formatDateTime, statusTone } from "@/lib/format";
import type { Creator, CreatorMonitorResult, MonitorState, PageResult, TaskResult } from "@/lib/types";

type MonitorAction = "monitor" | "pause" | "poll-now";

export default function CreatorsPage() {
  const { user } = useAuth();
  const [creators, setCreators] = useState<Creator[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [search, setSearch] = useState("");
  const [relationship, setRelationship] = useState("ALL");
  const [monitorState, setMonitorState] = useState<MonitorState | "ALL">("ALL");
  const [activeAction, setActiveAction] = useState<string>();

  const canManage = user?.role === "ADMIN" || user?.role === "BRAND_MANAGER";

  const loadCreators = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const response = await api.get<PageResult<Creator>>("/creators?limit=500");
      setCreators(response.items);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void api.get<PageResult<Creator>>("/creators?limit=500")
      .then((response) => {
        if (active) setCreators(response.items);
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
  }, []);

  const filteredCreators = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return creators.filter((creator) => {
      const matchesSearch =
        !query ||
        creator.name.toLocaleLowerCase().includes(query) ||
        creator.category.toLocaleLowerCase().includes(query);
      const matchesRelationship = relationship === "ALL" || creator.relationship_type === relationship;
      const matchesState = monitorState === "ALL" || creator.monitor_state === monitorState;
      return matchesSearch && matchesRelationship && matchesState;
    });
  }, [creators, monitorState, relationship, search]);

  const runAction = async (creator: Creator, action: MonitorAction) => {
    setActiveAction(`${creator.id}:${action}`);
    setError(undefined);
    setNotice(undefined);
    try {
      if (action === "poll-now") {
        const result = await api.post<TaskResult>(`/creators/${creator.id}/poll-now`);
        setNotice(`Poll queued for ${creator.name} (task ${result.task_id.slice(0, 8)}…).`);
      } else {
        const result = await api.post<CreatorMonitorResult>(`/creators/${creator.id}/${action}`);
        setCreators((items) =>
          items.map((item) =>
            item.id === result.creator_id ? { ...item, monitor_state: result.monitor_state } : item,
          ),
        );
        setNotice(`${creator.name} monitor is now ${result.monitor_state.toLowerCase()}.`);
      }
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setActiveAction(undefined);
    }
  };

  const activeCount = creators.filter((creator) => creator.monitor_state === "ACTIVE").length;
  const pausedCount = creators.filter((creator) => creator.monitor_state === "PAUSED").length;
  const errorCount = creators.filter((creator) => creator.monitor_state === "ERROR").length;

  return (
    <>
      <PageHeader
        eyebrow="MONITORING"
        title="Creators"
        description="Prioritize authorized creator accounts and control capability-aware monitoring."
        actions={
          <Button onClick={() => void loadCreators()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </Button>
        }
      />
      <div className="stats-grid">
        <StatCard label="Loaded creators" value={String(creators.length)} detail="Current tenant scope" />
        <StatCard label="Active monitors" value={String(activeCount)} detail="Eligible for scheduled polling" tone="success" />
        <StatCard label="Paused monitors" value={String(pausedCount)} detail="No scheduled polling" tone="warning" />
        <StatCard label="Monitor errors" value={String(errorCount)} detail="Requires operator review" tone={errorCount ? "danger" : "neutral"} />
      </div>
      {error ? <div className="callout callout-danger" role="alert" style={{ marginBottom: 18 }}>{error}</div> : null}
      {notice ? <div className="callout" role="status" style={{ marginBottom: 18 }}>{notice}</div> : null}
      <Panel title="Creator registry" description="Polling controls call the live monitor endpoints and respect role permissions.">
        <div className="filter-bar">
          <input
            className="input"
            aria-label="Search creators"
            placeholder="Search name or category…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <select
            className="select"
            aria-label="Filter relationship"
            value={relationship}
            onChange={(event) => setRelationship(event.target.value)}
          >
            <option value="ALL">All relationships</option>
            <option value="OWN_ACCOUNT">Own account</option>
            <option value="PARTNER_CREATOR">Partner creator</option>
            <option value="OFFICIAL_CAMPAIGN_CREATOR">Official campaign creator</option>
            <option value="GENERAL_CREATOR">General creator</option>
            <option value="BRAND_ACCOUNT">Brand account</option>
            <option value="COMPETITOR">Competitor</option>
            <option value="BLOCKED_CREATOR">Blocked creator</option>
          </select>
          <select
            className="select"
            aria-label="Filter monitor state"
            value={monitorState}
            onChange={(event) => setMonitorState(event.target.value as MonitorState | "ALL")}
          >
            <option value="ALL">All monitor states</option>
            <option value="ACTIVE">Active</option>
            <option value="PAUSED">Paused</option>
            <option value="ERROR">Error</option>
          </select>
        </div>
        {loading && creators.length === 0 ? (
          <EmptyState title="Loading creators" detail="Reading the creator registry from the API…" />
        ) : filteredCreators.length === 0 ? (
          <EmptyState
            title={creators.length === 0 ? "No creators yet" : "No creators match these filters"}
            detail={creators.length === 0 ? "Create or seed a creator to start monitoring posts." : "Change the search or monitor filters."}
          />
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr><th>Creator</th><th>Relationship</th><th>Priority</th><th>Poll intervals</th><th>Last checked</th><th>Monitor</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {filteredCreators.map((creator) => {
                  const stateAction = creator.monitor_state === "ACTIVE" ? "pause" : "monitor";
                  const changingState = activeAction === `${creator.id}:${stateAction}`;
                  const polling = activeAction === `${creator.id}:poll-now`;
                  return (
                    <tr key={creator.id}>
                      <td><span className="cell-primary">{creator.name}</span><span className="cell-secondary">{creator.category} · {creator.id.slice(0, 8)}</span></td>
                      <td>{creator.relationship_type}</td>
                      <td>{creator.priority}</td>
                      <td className="mono">{creator.normal_poll_interval_sec}s / {creator.warm_poll_interval_sec}s / {creator.hot_poll_interval_sec}s</td>
                      <td>{formatDateTime(creator.last_checked_at)}</td>
                      <td><Badge tone={statusTone(creator.monitor_state)}>{creator.monitor_state}</Badge></td>
                      <td>
                        <div className="button-row">
                          <Button
                            variant="ghost"
                            disabled={!canManage || polling || creator.monitor_state !== "ACTIVE"}
                            onClick={() => void runAction(creator, "poll-now")}
                          >
                            {polling ? "Queueing…" : "Poll now"}
                          </Button>
                          <Button
                            variant={creator.monitor_state === "ACTIVE" ? "danger" : "secondary"}
                            disabled={!canManage || changingState}
                            onClick={() => void runAction(creator, stateAction)}
                          >
                            {changingState ? "Saving…" : creator.monitor_state === "ACTIVE" ? "Pause" : "Monitor"}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
