"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AdminMessages, CheckboxField } from "@/components/admin-form";
import { Badge, Button, ConfirmDialog, EmptyState, PageHeader, Panel, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage, formatDateTime } from "@/lib/format";
import type { PageResult, Platform } from "@/lib/types";

type Brand = { id: string; name: string; tenant_id: string | null };
type Identity = { id: string; tenant_id: string | null; account_kind: string; public_identity_text: string; legal_or_operating_entity: string; active: boolean };
type Voice = { id: string; brand_id: string; name: string; version: number; active: boolean };
type Account = { id: string; brand_id: string; platform: Platform; external_account_id: string; display_name: string; account_kind: string; identity_profile_id: string; voice_profile_id: string; auto_publish_enabled: boolean; publisher_kill_switch: boolean; max_comments_per_day: number; auth_status: string; last_auth_verified_at: string | null };
type AccountDraft = Omit<Account, "id" | "publisher_kill_switch" | "auth_status" | "last_auth_verified_at"> & { id?: string };
type CapabilityMatrix = { platforms: Array<{ platform: Platform; capabilities: Array<{ capability: string; status: string }> }> };

export default function AccountsPage() {
  const { user } = useAuth();
  const canManage = user?.role === "ADMIN" || user?.role === "BRAND_MANAGER";
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [brands, setBrands] = useState<Brand[]>([]);
  const [identities, setIdentities] = useState<Identity[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [capabilities, setCapabilities] = useState<CapabilityMatrix>();
  const [draft, setDraft] = useState<AccountDraft>();
  const [showIdentity, setShowIdentity] = useState(false);
  const [identityEntity, setIdentityEntity] = useState("");
  const [identityText, setIdentityText] = useState("");
  const [identityKind, setIdentityKind] = useState("BRAND_OFFICIAL");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [killTarget, setKillTarget] = useState<Account>();
  const fetchData = useCallback(() => Promise.all([
    api.get<PageResult<Account>>("/platform-accounts?limit=500"),
    api.get<PageResult<Brand>>("/brands?limit=500"),
    api.get<PageResult<Identity>>("/platform-accounts/identity-profiles?limit=500"),
    api.get<PageResult<Voice>>("/platform-accounts/voice-profiles?limit=500"),
    api.get<CapabilityMatrix>("/system/capabilities"),
  ]), []);
  const apply = useCallback((values: Awaited<ReturnType<typeof fetchData>>) => {
    setAccounts(values[0].items); setBrands(values[1].items); setIdentities(values[2].items); setVoices(values[3].items); setCapabilities(values[4]);
  }, []);
  useEffect(() => {
    let active = true;
    void fetchData().then((values) => { if (active) apply(values); })
      .catch((reason: unknown) => { if (active) setError(errorMessage(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [apply, fetchData]);
  const refresh = async () => {
    setLoading(true); setError(undefined);
    try { apply(await fetchData()); } catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!draft) return;
    const identity = identities.find((item) => item.id === draft.identity_profile_id);
    if (!identity) return;
    setBusy(true); setError(undefined); setNotice(undefined);
    try {
      const fields = { display_name: draft.display_name.trim(), identity_profile_id: draft.identity_profile_id, voice_profile_id: draft.voice_profile_id, auto_publish_enabled: draft.auto_publish_enabled, max_comments_per_day: draft.max_comments_per_day };
      const saved = draft.id ? await api.patch<Account>(`/platform-accounts/${draft.id}`, fields)
        : await api.post<Account>("/platform-accounts", { ...fields, brand_id: draft.brand_id, platform: draft.platform, external_account_id: draft.external_account_id.trim(), account_kind: identity.account_kind });
      setAccounts((items) => draft.id ? items.map((item) => item.id === saved.id ? saved : item) : [saved, ...items]);
      setDraft(undefined); setNotice("Account configuration saved. Login authorization and sending-channel readiness are unchanged.");
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };
  const createIdentity = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(undefined); setNotice(undefined);
    try {
      const identity = await api.post<Identity>("/platform-accounts/identity-profiles", { legal_or_operating_entity: identityEntity.trim(), account_kind: identityKind, public_identity_text: identityText.trim(), may_speak_as_consumer: false, may_use_first_person_experience: false, requires_brand_disclosure: true, requires_ai_disclosure_policy_check: true });
      setIdentities((items) => [identity, ...items]); setShowIdentity(false); setIdentityEntity(""); setIdentityText("");
      setNotice("Operating identity created. Select it when registering the account.");
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };
  const toggleKill = async () => {
    if (!killTarget) return;
    const target = killTarget; setKillTarget(undefined); setBusy(true); setError(undefined); setNotice(undefined);
    try {
      const updated = await api.post<Account>(`/platform-accounts/${target.id}/kill-switch`, { enabled: !target.publisher_kill_switch });
      setAccounts((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNotice(`${updated.display_name}: publisher ${updated.publisher_kill_switch ? "stopped" : "kill switch cleared"}.`);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };
  const verifyMock = async (account: Account) => {
    setBusy(true); setError(undefined); setNotice(undefined);
    try { await api.post(`/platform-accounts/${account.id}/verify-auth`); await refresh(); setNotice("Mock authorization verified. This does not authorize a real platform."); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };
  const selectedBrand = brands.find((brand) => brand.id === draft?.brand_id);
  const availableIdentities = identities.filter((identity) => identity.active && identity.tenant_id === selectedBrand?.tenant_id && (!draft?.id || identity.account_kind === draft.account_kind));
  const availableVoices = voices.filter((voice) => voice.active && voice.brand_id === draft?.brand_id);
  return <>
    <PageHeader eyebrow="DECLARED IDENTITY" title="Publishing accounts" description="Register your real operating identity and account configuration. Login authorization and sending-channel availability are tracked separately." actions={<div className="button-row"><Button disabled={loading || busy} onClick={() => void refresh()}>Refresh</Button><Button disabled={!canManage || busy || loading} onClick={() => setShowIdentity((value) => !value)}>New identity</Button><Button variant="primary" disabled={!canManage || busy || loading} onClick={() => setDraft({ brand_id: brands[0]?.id ?? "", platform: "XIAOHONGSHU", external_account_id: "", display_name: "", account_kind: "BRAND_OFFICIAL", identity_profile_id: "", voice_profile_id: "", auto_publish_enabled: false, max_comments_per_day: 20 })}>Add account</Button></div>} />
    <AdminMessages error={error} notice={notice} />
    <div className="callout callout-warning" style={{ marginBottom: 18 }}>Xiaohongshu and Douyin sending channels are not configured. Account registration and automatic mode do not connect a channel. An API integration or an authorized browser session can provide a future sending channel; use manual publishing until one is implemented and verified.</div>
    <div className="stats-grid"><StatCard label="Registered accounts" value={loading ? "—" : String(accounts.length)} detail="Persisted account configurations" /><StatCard label="Automatic mode enabled" value={loading ? "—" : String(accounts.filter((item) => item.auto_publish_enabled).length)} detail="Still subject to platform and campaign checks" /><StatCard label="Authorization unconfigured" value={loading ? "—" : String(accounts.filter((item) => item.auth_status !== "VALID").length)} detail="Not verified for automatic publishing" tone="warning" /><StatCard label="Kill switches enabled" value={loading ? "—" : String(accounts.filter((item) => item.publisher_kill_switch).length)} detail="Publishing blocked for these accounts" tone="danger" /></div>
    <div className="stack">
      {showIdentity ? <Panel title="Real operating identity"><form className="panel-body stack" onSubmit={(event) => void createIdentity(event)}><div className="field"><label htmlFor="identity-entity">Legal or operating entity</label><input id="identity-entity" className="input" required maxLength={255} value={identityEntity} onChange={(event) => setIdentityEntity(event.target.value)} /></div><div className="field"><label htmlFor="identity-kind">Account kind</label><select id="identity-kind" className="select" value={identityKind} onChange={(event) => setIdentityKind(event.target.value)}><option value="BRAND_OFFICIAL">Brand official</option><option value="EMPLOYEE_DISCLOSED">Disclosed employee</option><option value="PARTNER_CREATOR">Partner creator</option><option value="HUMAN_OPERATOR">Human operator</option></select></div><div className="field"><label htmlFor="identity-public">Truthful public identity for disclosure</label><input id="identity-public" className="input" required maxLength={2000} value={identityText} onChange={(event) => setIdentityText(event.target.value)} placeholder="Example: 品牌官方运营团队" /></div><Button type="submit" variant="primary" disabled={busy}>Save identity</Button></form></Panel> : null}
      {draft ? <Panel title={draft.id ? "Edit account configuration" : "Register account"}><form className="panel-body stack" onSubmit={(event) => void save(event)}>
        {brands.length === 0 ? <div className="callout"><Link href="/brand">Create a brand and voice profile first.</Link></div> : null}
        <div className="equal-grid">
          <div className="field"><label htmlFor="account-brand">Brand</label><select id="account-brand" className="select" required disabled={Boolean(draft.id)} value={draft.brand_id} onChange={(event) => setDraft({ ...draft, brand_id: event.target.value, identity_profile_id: "", voice_profile_id: "" })}><option value="">Select brand</option>{brands.map((brand) => <option key={brand.id} value={brand.id}>{brand.name}</option>)}</select></div>
          <div className="field"><label htmlFor="account-platform">Platform</label><select id="account-platform" className="select" disabled={Boolean(draft.id)} value={draft.platform} onChange={(event) => setDraft({ ...draft, platform: event.target.value as Platform })}><option value="XIAOHONGSHU">Xiaohongshu · not connected</option><option value="DOUYIN">Douyin · not connected</option><option value="MOCK">Mock · local testing</option><option value="WECHAT_CHANNELS">WeChat Channels · not connected</option></select></div>
          <div className="field"><label htmlFor="account-name">Display name</label><input id="account-name" className="input" required maxLength={160} value={draft.display_name} onChange={(event) => setDraft({ ...draft, display_name: event.target.value })} /></div>
          <div className="field"><label htmlFor="account-external">Platform account ID</label><input id="account-external" className="input" required maxLength={255} disabled={Boolean(draft.id)} value={draft.external_account_id} onChange={(event) => setDraft({ ...draft, external_account_id: event.target.value })} /></div>
          <div className="field"><label htmlFor="account-identity">Operating identity</label><select id="account-identity" className="select" required value={draft.identity_profile_id} onChange={(event) => setDraft({ ...draft, identity_profile_id: event.target.value })}><option value="">Select an active identity</option>{availableIdentities.map((identity) => <option key={identity.id} value={identity.id}>{identity.public_identity_text} · {identity.account_kind}</option>)}</select></div>
          <div className="field"><label htmlFor="account-voice">Voice version</label><select id="account-voice" className="select" required value={draft.voice_profile_id} onChange={(event) => setDraft({ ...draft, voice_profile_id: event.target.value })}><option value="">Select an active brand voice</option>{availableVoices.map((voice) => <option key={voice.id} value={voice.id}>{voice.name} · v{voice.version}</option>)}</select></div>
          <div className="field"><label htmlFor="account-limit">Daily comment limit</label><input id="account-limit" className="input" type="number" min={1} required value={draft.max_comments_per_day} onChange={(event) => setDraft({ ...draft, max_comments_per_day: Number(event.target.value) })} /></div>
        </div>
        <CheckboxField id="account-auto" label="Allow this account to participate in automatic publishing" detail="Requires promotion mode, a campaign without mandatory review, valid authorization, supported platform capability, and all quality/disclosure checks." checked={draft.auto_publish_enabled} onChange={(event) => setDraft({ ...draft, auto_publish_enabled: event.target.checked })} />
        <div className="button-row"><Button type="submit" variant="primary" disabled={busy}>Save account</Button><Button type="button" disabled={busy} onClick={() => setDraft(undefined)}>Cancel</Button></div>
      </form></Panel> : null}
      <Panel title="Account registry" description="Stored authorization status is shown independently from integration availability.">{loading && accounts.length === 0 ? <EmptyState title="Loading accounts" detail="Reading account, identity, voice, and capability records…" /> : accounts.length === 0 ? <EmptyState title={error ? "Accounts unavailable" : "No accounts registered"} detail="Create a brand and voice, add an identity, then register an account." /> : <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Account</th><th>Identity</th><th>Authorization</th><th>Comment capability</th><th>Automatic setting</th><th>Kill switch</th><th>Actions</th></tr></thead><tbody>{accounts.map((account) => {
        const capability = capabilities?.platforms.find((item) => item.platform === account.platform)?.capabilities.find((item) => item.capability === "TOP_LEVEL_COMMENT")?.status ?? "UNKNOWN";
        return <tr key={account.id}><td><span className="cell-primary">{account.display_name}</span><span className="cell-secondary">{account.platform} · {account.external_account_id}</span></td><td>{identities.find((item) => item.id === account.identity_profile_id)?.public_identity_text ?? "Unavailable"}</td><td><Badge tone={account.platform === "MOCK" && account.auth_status === "VALID" ? "success" : "warning"}>{account.auth_status}</Badge><span className="cell-secondary">Verified {formatDateTime(account.last_auth_verified_at)}</span>{account.platform !== "MOCK" ? <span className="cell-secondary">Sending channel not configured</span> : null}</td><td>{capability}</td><td>{account.auto_publish_enabled ? "Enabled · checks required" : "Disabled"}</td><td><Badge tone={account.publisher_kill_switch ? "danger" : "neutral"}>{account.publisher_kill_switch ? "ON" : "OFF"}</Badge></td><td><div className="button-row"><Button disabled={!canManage || busy} onClick={() => setDraft({ ...account })}>Edit</Button>{account.platform === "MOCK" ? <Button disabled={user?.role !== "ADMIN" || busy} onClick={() => void verifyMock(account)}>Verify mock auth</Button> : null}<Button variant={account.publisher_kill_switch ? "secondary" : "danger"} disabled={user?.role !== "ADMIN" || busy} onClick={() => setKillTarget(account)}>{account.publisher_kill_switch ? "Clear kill switch" : "Stop publishing"}</Button></div></td></tr>;
      })}</tbody></table></div>}</Panel>
    </div>
    <ConfirmDialog open={Boolean(killTarget)} title={killTarget?.publisher_kill_switch ? "Clear this account’s kill switch?" : "Stop publishing for this account?"} description={`${killTarget?.display_name ?? ""}. The saved control applies to future publish attempts. Existing history is retained.`} confirmLabel={killTarget?.publisher_kill_switch ? "Clear kill switch" : "Stop publishing"} danger={!killTarget?.publisher_kill_switch} onCancel={() => setKillTarget(undefined)} onConfirm={() => void toggleKill()} />
  </>;
}
