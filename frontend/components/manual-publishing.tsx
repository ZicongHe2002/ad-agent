"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { AdminMessages, CheckboxField } from "@/components/admin-form";
import { DisclosureFields, disclosurePayload, type ResolvedDisclosure } from "@/components/disclosure-fields";
import { Badge, Button, EmptyState, Panel } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage, formatDateTime, shortId } from "@/lib/format";
import type { CommentCandidate, PageResult, Platform } from "@/lib/types";

type ManualJob = { id: string; candidate_id: string; platform: Platform; state: string; state_reason: string | null; created_at: string };
type ManualDetail = ManualJob & {
  candidate: CommentCandidate | null;
  post: { id: string; source_url: string | null; external_post_id: string; content: { title: string | null; caption: string | null } | null } | null;
  account: { display_name: string; external_account_id: string } | null;
  identity: { public_identity_text: string } | null;
};

function safeLink(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : undefined; }
  catch { return undefined; }
}

export function ManualPublishingPanel({ onCompleted }: { onCompleted(): void }) {
  const { user } = useAuth();
  const canConfirm = user?.role === "ADMIN" || user?.role === "BRAND_MANAGER" || user?.role === "REVIEWER";
  const [jobs, setJobs] = useState<ManualJob[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [detail, setDetail] = useState<ManualDetail>();
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [result, setResult] = useState<"published" | "skipped" | "failed">("published");
  const [confirmed, setConfirmed] = useState(false);
  const [externalId, setExternalId] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [disclosureStatus, setDisclosureStatus] = useState<ResolvedDisclosure | "">("");
  const [disclosureEvidence, setDisclosureEvidence] = useState("");
  const latestDetail = useRef<string | undefined>(undefined);
  const requestJobs = useCallback((pageOffset: number) => api.get<PageResult<ManualJob>>(`/comments/publish-jobs?state=WAITING_MANUAL_PUBLISH&limit=50&offset=${pageOffset}`), []);
  const applyJobs = useCallback((page: PageResult<ManualJob>) => { setJobs(page.items); setTotal(page.total); setOffset(page.offset); }, []);
  useEffect(() => {
    let active = true;
    void requestJobs(0).then((page) => { if (active) applyJobs(page); })
      .catch((reason: unknown) => { if (active) setError(errorMessage(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; latestDetail.current = undefined; };
  }, [applyJobs, requestJobs]);
  const refresh = async (pageOffset = offset) => {
    setLoading(true); setError(undefined);
    try { applyJobs(await requestJobs(pageOffset)); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setLoading(false); }
  };
  const inspect = async (id: string) => {
    latestDetail.current = id; setDetail(undefined); setDetailLoading(true); setError(undefined); setNotice(undefined);
    setConfirmed(false); setExternalId(""); setResult("published"); setDisclosureStatus(""); setDisclosureEvidence("");
    try {
      const value = await api.get<ManualDetail>(`/comments/publish-jobs/${id}`);
      if (latestDetail.current !== id) return;
      setDetail(value); setSourceUrl(value.post?.source_url ?? "");
    } catch (reason) { if (latestDetail.current === id) setError(errorMessage(reason)); }
    finally { if (latestDetail.current === id) setDetailLoading(false); }
  };
  const saveUrl = async () => {
    if (!detail?.post || !safeLink(sourceUrl)) { setError("Enter a valid HTTP or HTTPS source URL without credentials."); return; }
    const postId = detail.post.id;
    setBusy(true); setError(undefined);
    try {
      const saved = await api.patch<{ source_url: string }>(`/posts/${postId}/source-url`, { source_url: sourceUrl });
      setDetail((current) => current?.post?.id === postId ? { ...current, post: { ...current.post, source_url: saved.source_url } } : current);
      setNotice("Post link saved.");
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!detail || (result === "published" && !confirmed)) return;
    setBusy(true); setError(undefined); setNotice(undefined);
    try {
      await api.post(`/comments/publish-jobs/${detail.id}/manual-result`, { result, operator_confirmed: confirmed, external_comment_id: externalId.trim() || null, ...(result === "published" ? disclosurePayload(disclosureStatus, disclosureEvidence) : {}) });
      latestDetail.current = undefined; setDetail(undefined); setNotice(`Manual result recorded: ${result}.`);
      await refresh(0); onCompleted();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  };
  const copy = async () => {
    if (!detail?.candidate) return;
    try { await navigator.clipboard.writeText(detail.candidate.text); setNotice("Approved comment copied. Check the destination account and post before sending."); }
    catch { setError("Clipboard unavailable. Select and copy the approved text below."); }
  };
  const postLink = safeLink(detail?.post?.source_url);
  return <Panel title="Manual publishing queue" description="Open the post in your logged-in platform, send the approved comment, then record the actual result." actions={<Button disabled={loading || busy} onClick={() => void refresh()}>{loading ? "Loading…" : "Refresh queue"}</Button>}>
    <div className="panel-body stack"><AdminMessages error={error} notice={notice} />
      {!jobs.length ? <EmptyState title={loading ? "Loading manual tasks" : error ? "Manual queue unavailable" : "No manual tasks pending"} detail="Approved comments requiring a manual sending step appear here." /> : <>
        <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Task</th><th>Platform</th><th>Reason</th><th>Created</th><th /></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td className="mono">{shortId(job.id)}</td><td>{job.platform}</td><td style={{ whiteSpace: "normal" }}>{job.state_reason ?? job.state}</td><td>{formatDateTime(job.created_at)}</td><td><Button disabled={busy} onClick={() => void inspect(job.id)}>Open task</Button></td></tr>)}</tbody></table></div>
        <div className="button-row"><Button disabled={loading || busy || offset === 0} onClick={() => void refresh(Math.max(0, offset - 50))}>Previous</Button><span>{offset + 1}–{offset + jobs.length} of {total}</span><Button disabled={loading || busy || offset + jobs.length >= total} onClick={() => void refresh(offset + 50)}>Next</Button></div>
      </>}
      {detailLoading ? <EmptyState title="Loading task context" detail="Reading the approved comment, source post, and account…" /> : detail?.candidate ? <form className="stack" onSubmit={(event) => void submit(event)}>
        <div className="callout"><strong>{detail.account?.display_name ?? "Account unavailable"}</strong> · {detail.platform}<br />{detail.identity?.public_identity_text ?? "Identity unavailable"}<br />Platform account: {detail.account?.external_account_id ?? "Unknown"}</div>
        <div className="callout">{detail.post?.content?.title ?? detail.post?.external_post_id ?? "Post unavailable"}<br />{detail.post?.content?.caption}</div>
        <div className="field"><label htmlFor="manual-source-url">Source post URL</label><input id="manual-source-url" className="input" type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} disabled={!canConfirm || busy} /></div>
        <div className="button-row"><Button type="button" disabled={!canConfirm || busy || !detail.post || !sourceUrl.trim()} onClick={() => void saveUrl()}>Save post link</Button>{postLink ? <a className="button" style={{ display: "inline-flex", alignItems: "center" }} href={postLink} target="_blank" rel="noopener noreferrer">Open source post</a> : null}</div>
        <div className="field"><label htmlFor="manual-comment">Approved comment</label><textarea id="manual-comment" className="textarea" value={detail.candidate.text} readOnly /></div>
        <div className="button-row"><Button type="button" onClick={() => void copy()}>Copy approved comment</Button><Badge>{detail.candidate.disclosure_status}</Badge></div>
        <div className="field"><label htmlFor="manual-result">Actual outcome</label><select id="manual-result" className="select" value={result} disabled={!canConfirm || busy} onChange={(event) => { setResult(event.target.value as typeof result); setConfirmed(false); }}><option value="published">Published by me</option><option value="skipped">Skipped</option><option value="failed">Failed</option></select></div>
        {result === "published" ? <>
          <div className="field"><label htmlFor="manual-external-id">Platform comment ID (if available)</label><input id="manual-external-id" className="input" value={externalId} disabled={!canConfirm || busy} onChange={(event) => setExternalId(event.target.value)} /></div>
          <DisclosureFields status={disclosureStatus} evidence={disclosureEvidence} onStatus={setDisclosureStatus} onEvidence={setDisclosureEvidence} disabled={!canConfirm || busy} />
          <CheckboxField id="manual-confirmed" label="I sent this exact approved comment on this post using the displayed account" detail="Confirm only after checking the actual platform result. Copying the text or opening the post does not publish it." checked={confirmed} disabled={!canConfirm || busy} onChange={(event) => setConfirmed(event.target.checked)} />
        </> : null}
        <div className="button-row"><Button type="submit" variant="primary" disabled={!canConfirm || busy || detail.state !== "WAITING_MANUAL_PUBLISH" || (result === "published" && !confirmed)}>{busy ? "Recording…" : "Record actual result"}</Button><Button type="button" disabled={busy} onClick={() => { latestDetail.current = undefined; setDetail(undefined); }}>Close task</Button></div>
      </form> : null}
    </div>
  </Panel>;
}
