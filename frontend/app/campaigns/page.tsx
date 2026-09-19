"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { Badge, Button, EmptyState, PageHeader, Panel, Progress, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/format";

type PageResult<T> = { items: T[]; total: number; offset: number; limit: number };
type Brand = { id: string; name: string; status: string };
type Campaign = {
  id: string;
  brand_id: string;
  name: string;
  run_mode: "FAST" | "FIRST_COMMENT" | "TOP5_COMMENT" | "NORMAL";
  start_at: string | null;
  end_at: string | null;
  allowed_strategies: string[];
  creator_relationship_allowlist: string[];
  max_comments_per_day: number;
  max_comments_per_creator_per_day: number;
  human_review_required: boolean;
  publisher_kill_switch: boolean;
  status: "DRAFT" | "ACTIVE" | "PAUSED" | "COMPLETED";
};

function statusTone(status: Campaign["status"]): "neutral" | "success" | "warning" {
  if (status === "ACTIVE") return "success";
  if (status === "DRAFT" || status === "PAUSED") return "warning";
  return "neutral";
}

export default function CampaignsPage() {
  const { user } = useAuth();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [brands, setBrands] = useState<Brand[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [activeAction, setActiveAction] = useState<string>();
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [brandId, setBrandId] = useState("");
  const [runMode, setRunMode] = useState<Campaign["run_mode"]>("NORMAL");
  const [dailyLimit, setDailyLimit] = useState(20);
  const [creatorLimit, setCreatorLimit] = useState(1);
  const [reviewRequired, setReviewRequired] = useState(true);

  const canManage = user?.role === "ADMIN" || user?.role === "BRAND_MANAGER";

  const applyData = useCallback((result: [PageResult<Campaign>, PageResult<Brand>]) => {
    setCampaigns(result[0].items);
    setBrands(result[1].items);
    setBrandId((current) => current || result[1].items[0]?.id || "");
  }, []);

  const fetchData = useCallback(() => Promise.all([
    api.get<PageResult<Campaign>>("/campaigns?limit=500"),
    api.get<PageResult<Brand>>("/brands?limit=500"),
  ]), []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      applyData(await fetchData());
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, [applyData, fetchData]);

  useEffect(() => {
    let active = true;
    void fetchData()
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
  }, [applyData, fetchData]);

  const createCampaign = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!brandId || !name.trim()) return;
    setActiveAction("create");
    setError(undefined);
    setNotice(undefined);
    try {
      const created = await api.post<Campaign>("/campaigns", {
        brand_id: brandId,
        name: name.trim(),
        run_mode: runMode,
        allowed_strategies: [],
        creator_relationship_allowlist: [],
        max_comments_per_day: dailyLimit,
        max_comments_per_creator_per_day: creatorLimit,
        human_review_required: reviewRequired,
      });
      setCampaigns((items) => [created, ...items]);
      setName("");
      setShowCreate(false);
      setNotice(`Campaign “${created.name}” was created as a draft.`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setActiveAction(undefined);
    }
  };

  const transitionCampaign = async (campaign: Campaign) => {
    const action = campaign.status === "ACTIVE" ? "pause" : "activate";
    setActiveAction(`${campaign.id}:${action}`);
    setError(undefined);
    setNotice(undefined);
    try {
      const updated = await api.post<Campaign>(`/campaigns/${campaign.id}/${action}`);
      setCampaigns((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNotice(`${updated.name} is now ${updated.status.toLowerCase()}.`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setActiveAction(undefined);
    }
  };

  const toggleKillSwitch = async (campaign: Campaign) => {
    const enabled = !campaign.publisher_kill_switch;
    setActiveAction(`${campaign.id}:kill`);
    setError(undefined);
    setNotice(undefined);
    try {
      const updated = await api.patch<Campaign>(`/campaigns/${campaign.id}`, { publisher_kill_switch: enabled });
      setCampaigns((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNotice(`${updated.name} publisher kill switch is ${enabled ? "enabled" : "disabled"}.`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setActiveAction(undefined);
    }
  };

  const toggleReview = async (campaign: Campaign) => {
    setActiveAction(`${campaign.id}:review`);
    setError(undefined); setNotice(undefined);
    try {
      const updated = await api.patch<Campaign>(`/campaigns/${campaign.id}`, { human_review_required: !campaign.human_review_required });
      setCampaigns((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNotice(updated.human_review_required ? "Campaign requires human review." : "Campaign allows automatic publishing in promotion mode when account and platform checks pass.");
    } catch (requestError) { setError(errorMessage(requestError)); }
    finally { setActiveAction(undefined); }
  };

  const activeCount = campaigns.filter((campaign) => campaign.status === "ACTIVE").length;
  const reviewCount = campaigns.filter((campaign) => campaign.human_review_required).length;
  const killSwitchCount = campaigns.filter((campaign) => campaign.publisher_kill_switch).length;
  const dailyCapacity = campaigns.reduce((total, campaign) => total + campaign.max_comments_per_day, 0);
  const brandNames = new Map(brands.map((brand) => [brand.id, brand.name]));

  return (
    <>
      <PageHeader
        eyebrow="ORCHESTRATION"
        title="Campaigns"
        description="Control campaign modes, daily limits, review gates, lifecycle state, and the publisher kill switch through audited API operations."
        actions={<div className="button-row"><Button onClick={() => void refresh()} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</Button><Button variant="primary" onClick={() => setShowCreate((value) => !value)} disabled={!canManage}>{showCreate ? "Cancel" : "New campaign"}</Button></div>}
      />
      <div className="stats-grid">
        <StatCard label="Campaigns loaded" value={String(campaigns.length)} detail={`${activeCount} active`} tone="info" />
        <StatCard label="Daily capacity" value={String(dailyCapacity)} detail="Combined configured maximum" />
        <StatCard label="Review required" value={String(reviewCount)} detail="Campaign-level human gate" tone="warning" />
        <StatCard label="Kill switches" value={String(killSwitchCount)} detail={killSwitchCount ? "Publishing blocked for affected campaigns" : "All campaign publishers clear"} tone={killSwitchCount ? "danger" : "success"} />
      </div>
      {error ? <div className="callout callout-danger" role="alert" style={{ marginBottom: 18 }}>{error}</div> : null}
      {notice ? <div className="callout" role="status" style={{ marginBottom: 18 }}>{notice}</div> : null}
      <div className="stack">
        {showCreate ? (
          <Panel title="Create campaign" description="New campaigns start as DRAFT and cannot publish until explicitly activated.">
            {brands.length === 0 ? (
              <EmptyState title="Create a brand first" detail="A campaign must belong to an existing brand." />
            ) : (
              <form className="panel-body stack" onSubmit={(event) => void createCampaign(event)}>
                <div className="equal-grid">
                  <div className="field"><label htmlFor="campaign-brand">Brand</label><select id="campaign-brand" className="select" value={brandId} onChange={(event) => setBrandId(event.target.value)} required>{brands.map((brand) => <option value={brand.id} key={brand.id}>{brand.name}</option>)}</select></div>
                  <div className="field"><label htmlFor="campaign-name">Name</label><input id="campaign-name" className="input" value={name} onChange={(event) => setName(event.target.value)} maxLength={160} required /></div>
                  <div className="field"><label htmlFor="campaign-mode">Run mode</label><select id="campaign-mode" className="select" value={runMode} onChange={(event) => setRunMode(event.target.value as Campaign["run_mode"])}><option value="NORMAL">NORMAL</option><option value="FAST">FAST</option><option value="FIRST_COMMENT">FIRST_COMMENT</option><option value="TOP5_COMMENT">TOP5_COMMENT</option></select></div>
                  <div className="field"><label htmlFor="campaign-daily">Daily limit</label><input id="campaign-daily" className="input" type="number" min={1} value={dailyLimit} onChange={(event) => setDailyLimit(Number(event.target.value))} required /></div>
                  <div className="field"><label htmlFor="campaign-creator-limit">Per-creator daily limit</label><input id="campaign-creator-limit" className="input" type="number" min={1} max={dailyLimit} value={creatorLimit} onChange={(event) => setCreatorLimit(Number(event.target.value))} required /></div>
                  <div className="field"><label htmlFor="campaign-review">Human review gate</label><select id="campaign-review" className="select" value={reviewRequired ? "required" : "policy"} onChange={(event) => setReviewRequired(event.target.value === "required")}><option value="required">Always required</option><option value="policy">Use relationship policy</option></select></div>
                </div>
                <div className="button-row"><Button variant="primary" type="submit" disabled={activeAction === "create" || creatorLimit > dailyLimit}>{activeAction === "create" ? "Creating…" : "Create draft"}</Button></div>
              </form>
            )}
          </Panel>
        ) : null}
        {loading && campaigns.length === 0 ? (
          <Panel><EmptyState title="Loading campaigns" detail="Reading the campaign registry from the API…" /></Panel>
        ) : campaigns.length === 0 ? (
          <Panel><EmptyState title="No campaigns" detail="Create a draft campaign after adding a brand." /></Panel>
        ) : (
          <div className="three-grid">
            {campaigns.map((campaign) => {
              const transitioning = activeAction === `${campaign.id}:${campaign.status === "ACTIVE" ? "pause" : "activate"}`;
              const changingKillSwitch = activeAction === `${campaign.id}:kill`;
              return (
                <Panel key={campaign.id} title={campaign.name} description={`${campaign.run_mode} · ${brandNames.get(campaign.brand_id) ?? campaign.brand_id.slice(0, 8)}`}>
                  <div className="panel-body stack">
                    <div className="button-row"><Badge tone={statusTone(campaign.status)}>{campaign.status}</Badge>{campaign.publisher_kill_switch ? <Badge tone="danger">PUBLISHER DISABLED</Badge> : null}</div>
                    <p className="page-description">{campaign.human_review_required ? "Every candidate requires human review." : "Review follows relationship and content policy."}</p>
                    <Progress label={`Daily limit · ${campaign.max_comments_per_day}`} value={(campaign.max_comments_per_creator_per_day / campaign.max_comments_per_day) * 100} />
                    <dl className="detail-list">
                      <div><dt>Per creator</dt><dd>{campaign.max_comments_per_creator_per_day} / day</dd></div>
                      <div><dt>Strategies</dt><dd>{campaign.allowed_strategies.length ? campaign.allowed_strategies.join(", ") : "Policy default"}</dd></div>
                      <div><dt>Relationships</dt><dd>{campaign.creator_relationship_allowlist.length ? campaign.creator_relationship_allowlist.join(", ") : "Policy default"}</dd></div>
                    </dl>
                    <div className="button-row">
                      <Button disabled={!canManage || Boolean(activeAction)} onClick={() => void toggleReview(campaign)}>{campaign.human_review_required ? "Allow automatic mode" : "Require human review"}</Button>
                      <Button disabled={!canManage || transitioning || campaign.publisher_kill_switch} onClick={() => void transitionCampaign(campaign)}>{transitioning ? "Saving…" : campaign.status === "ACTIVE" ? "Pause" : "Activate"}</Button>
                      <Button variant={campaign.publisher_kill_switch ? "secondary" : "danger"} disabled={!canManage || changingKillSwitch} onClick={() => void toggleKillSwitch(campaign)}>{changingKillSwitch ? "Saving…" : campaign.publisher_kill_switch ? "Clear kill switch" : "Enable kill switch"}</Button>
                    </div>
                  </div>
                </Panel>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
