"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminMessages, CheckboxField } from "@/components/admin-form";
import { Badge, Button, EmptyState, PageHeader, Panel } from "@/components/ui";
import { api } from "@/lib/api";
import { errorMessage, formatDateTime } from "@/lib/format";

export type PublishingSettings = {
  mode: "REVIEW" | "AUTO";
  can_edit: boolean;
  tenant_id: string | null;
  auto_disclosure_enabled: boolean;
  updated_at: string | null;
  platform_readiness: Array<{ platform: string; top_level_comment: string; automatic_publish_available: boolean; reason: string }>;
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<PublishingSettings>();
  const [mode, setMode] = useState<"REVIEW" | "AUTO">("REVIEW");
  const [disclosure, setDisclosure] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const apply = useCallback((value: PublishingSettings) => {
    setSettings(value); setMode(value.mode); setDisclosure(value.auto_disclosure_enabled);
  }, []);
  useEffect(() => {
    let active = true;
    void api.get<PublishingSettings>("/system/publishing-settings").then((value) => { if (active) apply(value); })
      .catch((reason: unknown) => { if (active) setError(errorMessage(reason)); });
    return () => { active = false; };
  }, [apply]);
  const save = async () => {
    setSaving(true); setError(undefined); setNotice(undefined);
    try {
      apply(await api.patch<PublishingSettings>("/system/publishing-settings", { mode, auto_disclosure_enabled: disclosure }));
      setNotice("Publishing policy saved. Existing pending reviews still require an explicit decision.");
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setSaving(false); }
  };
  return <>
    <PageHeader eyebrow="PUBLISHING POLICY" title="Settings" description="Use human review while testing. Enable automatic publishing for promotion once each account and platform is ready." />
    <AdminMessages error={error} notice={notice} />
    {!settings ? <Panel><EmptyState title={error ? "Settings unavailable" : "Loading publishing policy"} detail="No saved configuration is shown until the API responds." /></Panel> : <div className="stack">
      <Panel title="Publishing mode" description={`Last saved: ${formatDateTime(settings.updated_at)}`}>
        <div className="panel-body stack">
          <div className="field"><label htmlFor="publishing-mode">Mode for new opportunities</label><select id="publishing-mode" className="select" value={mode} disabled={!settings.can_edit || saving} onChange={(event) => setMode(event.target.value as "REVIEW" | "AUTO")}><option value="REVIEW">Testing · human review for every comment</option><option value="AUTO">Promotion · automatic publishing when all checks pass</option></select></div>
          <div className="callout">In automatic mode, the account must enable automatic publishing and the campaign must allow it. Quality, risk, authorization, disclosure, limits, and kill switches remain enforced. Failed checks skip the opportunity; existing pending reviews are not automatically approved.</div>
          <CheckboxField id="automatic-disclosure" label="Include identity and AI disclosure automatically" detail="Add the account’s real public identity and “AI辅助生成” to generated comments and record the disclosure method. This does not grant platform permission." checked={disclosure} disabled={!settings.can_edit || saving} onChange={(event) => setDisclosure(event.target.checked)} />
          {!settings.can_edit ? <div className="callout">An administrator or brand manager can update this policy.</div> : null}
          <Button variant="primary" onClick={() => void save()} disabled={!settings.can_edit || saving || (mode === settings.mode && disclosure === settings.auto_disclosure_enabled)}>{saving ? "Saving…" : "Save publishing policy"}</Button>
        </div>
      </Panel>
      <Panel title="Platform readiness" description="Account registration and automatic mode do not configure a sending channel. API or authorized browser channels require separate integration and verification.">
        <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Platform</th><th>Comment capability</th><th>Automatic publishing</th><th>Reason</th></tr></thead><tbody>{settings.platform_readiness.map((platform) => <tr key={platform.platform}><td>{platform.platform}</td><td>{platform.top_level_comment}</td><td><Badge tone={platform.automatic_publish_available ? "success" : "warning"}>{platform.automatic_publish_available ? "AVAILABLE" : "UNAVAILABLE"}</Badge></td><td style={{ whiteSpace: "normal" }}>{platform.reason}</td></tr>)}</tbody></table></div>
      </Panel>
    </div>}
  </>;
}
