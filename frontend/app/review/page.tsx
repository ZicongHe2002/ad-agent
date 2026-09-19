"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button, ConfirmDialog, EmptyState, PageHeader, Panel, Progress, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { DisclosureFields, disclosurePayload, type ResolvedDisclosure } from "@/components/disclosure-fields";
import { useAuth } from "@/lib/auth";
import { errorMessage, formatDateTime, formatPercent, shortId, statusTone } from "@/lib/format";
import type { PageResult, PostDetail, ReviewJob, ReviewJobDetail } from "@/lib/types";

type PendingAction = "approve" | "reject" | null;

export default function ReviewPage() {
  const { user } = useAuth();
  const [jobs, setJobs] = useState<ReviewJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string>();
  const [detail, setDetail] = useState<ReviewJobDetail>();
  const [post, setPost] = useState<PostDetail>();
  const [queueLoading, setQueueLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [editReason, setEditReason] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [activeAction, setActiveAction] = useState<string>();
  const [disclosureStatus, setDisclosureStatus] = useState<ResolvedDisclosure | "">("");
  const [disclosureEvidence, setDisclosureEvidence] = useState("");
  const requestedDetail = useRef<string | undefined>(undefined);

  const canReview = user?.role === "ADMIN" || user?.role === "REVIEWER";
  const claimedByMe = Boolean(detail && user && detail.assigned_to === user.id);
  const claimedByAnother = Boolean(detail?.assigned_to && !claimedByMe);
  const candidate = detail?.candidate;
  const changed = Boolean(candidate && draft.trim() !== candidate.text.trim());
  const latestRisk = detail?.risk_events.at(-1);

  const loadDetail = useCallback(async (jobId: string) => {
    requestedDetail.current = jobId;
    setDetailLoading(true);
    setError(undefined);
    try {
      const reviewDetail = await api.get<ReviewJobDetail>(`/review/jobs/${jobId}`);
      let postDetail: PostDetail | undefined;
      if (reviewDetail.candidate) {
        try {
          postDetail = await api.get<PostDetail>(`/posts/${reviewDetail.candidate.post_id}`);
        } catch {
          postDetail = undefined;
        }
      }
      if (requestedDetail.current !== jobId) return;
      setDetail(reviewDetail);
      setPost(postDetail);
      setDraft(reviewDetail.candidate?.text ?? reviewDetail.original_candidate_text);
      setEditing(false);
      setEditReason("");
      setReviewNotes("");
      setDisclosureStatus("");
      setDisclosureEvidence("");
    } catch (requestError) {
      if (requestedDetail.current !== jobId) return;
      setDetail(undefined);
      setPost(undefined);
      setError(errorMessage(requestError));
    } finally {
      if (requestedDetail.current === jobId) setDetailLoading(false);
    }
  }, []);

  const loadQueue = useCallback(async () => {
    setQueueLoading(true);
    setError(undefined);
    try {
      const response = await api.get<PageResult<ReviewJob>>("/review/jobs?status=PENDING&limit=500");
      setJobs(response.items);
      const first = response.items[0];
      setSelectedJobId(first?.id);
      if (first) {
        await loadDetail(first.id);
      } else {
        requestedDetail.current = undefined;
        setDetail(undefined);
        setPost(undefined);
        setDetailLoading(false);
      }
    } catch (requestError) {
      setJobs([]);
      setDetail(undefined);
      setPost(undefined);
      setError(errorMessage(requestError));
    } finally {
      setQueueLoading(false);
    }
  }, [loadDetail]);

  useEffect(() => {
    let active = true;
    void api.get<PageResult<ReviewJob>>("/review/jobs?status=PENDING&limit=500")
      .then(async (response) => {
        if (!active) return;
        setJobs(response.items);
        const first = response.items[0];
        setSelectedJobId(first?.id);
        if (!first) {
          setQueueLoading(false);
          return;
        }
        requestedDetail.current = first.id;
        const reviewDetail = await api.get<ReviewJobDetail>(`/review/jobs/${first.id}`);
        let postDetail: PostDetail | undefined;
        if (reviewDetail.candidate) {
          try {
            postDetail = await api.get<PostDetail>(`/posts/${reviewDetail.candidate.post_id}`);
          } catch {
            postDetail = undefined;
          }
        }
        if (!active || requestedDetail.current !== first.id) return;
        setDetail(reviewDetail);
        setPost(postDetail);
        setDraft(reviewDetail.candidate?.text ?? reviewDetail.original_candidate_text);
      })
      .catch((requestError: unknown) => {
        if (active) setError(errorMessage(requestError));
      })
      .finally(() => {
        if (active) {
          setQueueLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const selectJob = (jobId: string) => {
    setSelectedJobId(jobId);
    setNotice(undefined);
    void loadDetail(jobId);
  };

  const claimJob = async () => {
    if (!detail) return;
    setActiveAction("claim");
    setError(undefined);
    setNotice(undefined);
    try {
      const claimed = await api.post<ReviewJob>(`/review/jobs/${detail.id}/claim`);
      setDetail((current) => current?.id === claimed.id ? { ...current, assigned_to: claimed.assigned_to } : current);
      setJobs((items) => items.map((item) => item.id === claimed.id ? { ...item, assigned_to: claimed.assigned_to } : item));
      setNotice("Review claimed. You can now approve, edit and approve, or reject it.");
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setActiveAction(undefined);
    }
  };

  const submitDecision = async () => {
    if (!detail || !candidate || !pendingAction) return;
    const action = pendingAction;
    setPendingAction(null);
    setError(undefined);
    setNotice(undefined);
    if (action === "approve" && changed && editReason.trim().length < 3) {
      setError("Enter an edit reason of at least 3 characters before submitting edited text.");
      return;
    }
    setActiveAction(action);
    try {
      if (action === "reject") {
        await api.post<ReviewJob>(`/review/jobs/${detail.id}/reject`, {
          notes: reviewNotes.trim() || null,
        });
        setNotice("Review rejected and the decision was written to the audit trail.");
      } else if (changed) {
        await api.post<ReviewJob>(`/review/jobs/${detail.id}/edit-and-approve`, {
          final_text: draft.trim(),
          edit_reason: editReason.trim(),
          ...disclosurePayload(disclosureStatus, disclosureEvidence),
        });
        setNotice("Edited text passed through the backend re-check workflow. No direct publish request was made by this page.");
      } else {
        await api.post<ReviewJob>(`/review/jobs/${detail.id}/approve`, {
          notes: reviewNotes.trim() || null,
          ...disclosurePayload(disclosureStatus, disclosureEvidence),
        });
        setNotice("Candidate approved for the backend capability and safety workflow. This page never publishes directly.");
      }
      await loadQueue();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setActiveAction(undefined);
    }
  };

  const confirmation = useMemo(() => {
    if (pendingAction === "approve") {
      return {
        title: changed ? "Approve the edited comment?" : "Approve this candidate?",
        description: changed
          ? "The edited text will be submitted to mandatory identity, claim, quality, duplicate, disclosure, and risk checks."
          : "Approval enters the backend safety and capability workflow; it is not a direct publish command.",
        label: changed ? "Submit edit for checks" : "Confirm approval",
      };
    }
    return {
      title: "Reject this candidate?",
      description: "The candidate will be rejected and the pipeline opportunity will be skipped with an audit record.",
      label: "Confirm rejection",
    };
  }, [changed, pendingAction]);

  const unclaimed = jobs.filter((job) => job.assigned_to === null).length;
  const mine = jobs.filter((job) => job.assigned_to === user?.id).length;
  const withDeadline = jobs.filter((job) => job.expires_at !== null).length;

  return (
    <>
      <PageHeader
        eyebrow="HUMAN DECISION GATE"
        title="Review queue"
        description="Claim a pending review, inspect persisted evidence, then approve, edit and approve, or reject it."
        actions={<Button onClick={() => void loadQueue()} disabled={queueLoading}>{queueLoading ? "Refreshing…" : "Refresh queue"}</Button>}
      />
      <div className="stats-grid">
        <StatCard label="Pending loaded" value={String(jobs.length)} detail="Current tenant queue" tone="warning" />
        <StatCard label="Unclaimed" value={String(unclaimed)} detail="Available to reviewers" />
        <StatCard label="Claimed by you" value={String(mine)} detail="Ready for your decision" tone="info" />
        <StatCard label="With deadline" value={String(withDeadline)} detail="Review before the recorded expiry" tone={withDeadline ? "warning" : "neutral"} />
      </div>
      {error ? <div className="callout callout-danger" role="alert" style={{ marginBottom: 18 }}>{error}</div> : null}
      {notice ? <div className="callout" role="status" style={{ marginBottom: 18 }}>{notice}</div> : null}

      <div className="review-layout">
        <div className="stack">
          <Panel title="Pending reviews" description="Select an item to request its complete review detail.">
            {queueLoading && jobs.length === 0 ? (
              <EmptyState title="Loading review queue" detail="Reading pending review jobs…" />
            ) : jobs.length === 0 ? (
              <EmptyState title="Review queue is clear" detail="There are no pending review jobs in your tenant scope." />
            ) : (
              <div className="candidate-list">
                {jobs.map((job, index) => (
                  <button
                    key={job.id}
                    className={`candidate-card ${selectedJobId === job.id ? "selected" : ""}`}
                    onClick={() => selectJob(job.id)}
                  >
                    <div className="candidate-meta">
                      <span className="candidate-index">{index + 1}</span>
                      <span><Badge tone={job.assigned_to ? "info" : "warning"}>{job.assigned_to ? "CLAIMED" : "UNCLAIMED"}</Badge></span>
                    </div>
                    <p>{job.original_candidate_text}</p>
                    <span className="cell-secondary">Submitted {formatDateTime(job.submitted_at)} · {shortId(job.id)}</span>
                  </button>
                ))}
              </div>
            )}
          </Panel>

          {selectedJobId && detailLoading ? (
            <Panel><EmptyState title="Loading review detail" detail="Reading candidate, quality, risk, anchors, and post context…" /></Panel>
          ) : detail && candidate ? (
            <>
              <Panel
                title="Post context"
                description={`${post?.platform ?? "Platform unknown"} · post ${shortId(candidate.post_id)}`}
              >
                <div className="panel-body stack">
                  <p style={{ lineHeight: 1.75, margin: 0 }}>
                    {post?.content?.caption ?? post?.content?.visual_summary ?? "Normalized post content is not available for this review."}
                  </p>
                  <div className="callout">
                    Content completeness: {post?.content ? `${formatPercent(post.content.data_completeness)}%` : "unknown"} · Published {formatDateTime(post?.published_at)}
                  </div>
                </div>
              </Panel>
              <Panel title="Concrete anchors" description="The approved text must remain grounded in these persisted anchors.">
                {detail.anchors.length > 0 ? (
                  <div className="anchor-list">
                    {detail.anchors.map((anchor) => <span className="anchor" key={anchor.id}>{anchor.anchor_type} · {anchor.anchor_text}</span>)}
                  </div>
                ) : <EmptyState title="No anchors available" detail="Approval may fail the backend hard gates until concrete context is available." />}
              </Panel>
              <Panel title="Candidate comment" description="Edited text is always sent back through mandatory backend checks.">
                <div className="candidate-list">
                  <div className="candidate-card selected">
                    <div className="candidate-meta">
                      <span className="candidate-index">1</span>
                      <span>
                        <Badge tone={statusTone(detail.quality?.decision ?? "UNKNOWN")}>{detail.quality?.decision ?? "NOT SCORED"}</Badge>{" "}
                        <Badge>SIM {formatPercent(detail.quality?.duplicate_similarity_max)}%</Badge>
                      </span>
                    </div>
                    <p>{candidate.text}</p>
                  </div>
                </div>
                {editing ? (
                  <div className="panel-body stack" style={{ paddingTop: 0 }}>
                    <div className="field">
                      <label htmlFor="review-edit">Edit selected candidate</label>
                      <textarea id="review-edit" className="textarea" value={draft} onChange={(event) => setDraft(event.target.value)} />
                      <span className="cell-secondary">The browser submits this text to edit-and-approve; it never calls a publish endpoint.</span>
                    </div>
                    {changed ? (
                      <div className="field">
                        <label htmlFor="edit-reason">Edit reason</label>
                        <input id="edit-reason" className="input" value={editReason} onChange={(event) => setEditReason(event.target.value)} placeholder="Required (at least 3 characters)" />
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <div className="panel-body stack" style={{ borderTop: "1px solid var(--line)" }}>
                  <DisclosureFields status={disclosureStatus} evidence={disclosureEvidence} onStatus={setDisclosureStatus} onEvidence={setDisclosureEvidence} disabled={!claimedByMe || Boolean(activeAction)} />
                  <div className="field">
                    <label htmlFor="review-notes">Review notes</label>
                    <textarea id="review-notes" className="textarea" value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} placeholder="Optional decision context for the audit trail" />
                  </div>
                  <div className="button-row">
                    <Button
                      variant="primary"
                      onClick={() => setPendingAction("approve")}
                      disabled={!claimedByMe || Boolean(activeAction) || draft.trim().length === 0}
                    >
                      {changed ? "Submit edit & approve" : "Approve candidate"}
                    </Button>
                    <Button onClick={() => setEditing(true)} disabled={!claimedByMe || Boolean(activeAction)}>Edit</Button>
                    <Button variant="danger" onClick={() => setPendingAction("reject")} disabled={!claimedByMe || Boolean(activeAction)}>Reject</Button>
                  </div>
                </div>
              </Panel>
            </>
          ) : null}
        </div>

        <div className="stack">
          <Panel
            title="Assignment"
            description="A reviewer must claim the job before making a decision."
          >
            <div className="panel-body stack">
              <div>
                <Badge tone={claimedByMe ? "success" : claimedByAnother ? "warning" : "neutral"}>
                  {claimedByMe ? "CLAIMED BY YOU" : claimedByAnother ? "CLAIMED BY ANOTHER REVIEWER" : "UNCLAIMED"}
                </Badge>
              </div>
              <Button
                variant="primary"
                onClick={() => void claimJob()}
                disabled={!detail || detailLoading || !canReview || claimedByMe || claimedByAnother || Boolean(activeAction)}
              >
                {activeAction === "claim" ? "Claiming…" : claimedByMe ? "Claimed" : "Claim review"}
              </Button>
              {!canReview && user ? <div className="callout callout-warning">Your {user.role} role can inspect this queue but cannot make review decisions.</div> : null}
            </div>
          </Panel>
          {detail && candidate ? (
            <>
              <Panel title="Decision context">
                <dl className="detail-list">
                  <div><dt>Review</dt><dd className="mono">{shortId(detail.id)}</dd></div>
                  <div><dt>Candidate</dt><dd className="mono">{shortId(candidate.id)}</dd></div>
                  <div><dt>Strategy</dt><dd>{candidate.strategy}</dd></div>
                  <div><dt>Status</dt><dd><Badge tone={statusTone(candidate.status)}>{candidate.status}</Badge></dd></div>
                  <div><dt>Disclosure</dt><dd><Badge tone={statusTone(candidate.disclosure_status)}>{candidate.disclosure_status}</Badge></dd></div>
                  <div><dt>Approved claim refs</dt><dd>{candidate.referenced_claim_ids.length}</dd></div>
                  <div><dt>Provenance</dt><dd>{candidate.content_provenance}</dd></div>
                  <div><dt>Expires</dt><dd>{formatDateTime(detail.expires_at)}</dd></div>
                </dl>
              </Panel>
              <Panel title="Quality breakdown" description={detail.quality ? `Decision: ${detail.quality.decision}` : "No quality evaluation is available."}>
                {detail.quality ? (
                  <div className="metric-list">
                    <Progress label="Overall quality" value={formatPercent(detail.quality.quality_score)} />
                    <Progress label="Anchor coverage" value={formatPercent(detail.quality.anchor_coverage)} />
                    <Progress label="Specificity" value={formatPercent(detail.quality.specificity)} />
                    <Progress label="Fluency" value={formatPercent(detail.quality.fluency)} />
                    <Progress label="Voice match" value={formatPercent(detail.quality.voice_match)} />
                    <Progress label="Novelty" value={formatPercent(detail.quality.novelty)} />
                    <Progress label="Truthfulness" value={formatPercent(detail.quality.truthfulness)} />
                  </div>
                ) : <EmptyState title="Not scored" detail="The pipeline has not persisted a quality evaluation for this candidate." />}
              </Panel>
              <Panel title="Risk decision" description="Rule and semantic decisions are persisted before review.">
                <div className="panel-body stack">
                  {latestRisk ? (
                    <>
                      <div><Badge tone={statusTone(latestRisk.final_decision)}>{latestRisk.final_decision} · {formatPercent(latestRisk.risk_score)}%</Badge></div>
                      {latestRisk.reasons.length > 0 ? <div className="callout callout-warning">{latestRisk.reasons.join(" · ")}</div> : null}
                      <div className="callout">Matched rules: {latestRisk.matched_rules.length > 0 ? latestRisk.matched_rules.join(", ") : "none"}</div>
                    </>
                  ) : <div className="callout">No risk event has been persisted for this candidate.</div>}
                </div>
              </Panel>
            </>
          ) : null}
        </div>
      </div>
      <ConfirmDialog
        open={pendingAction !== null}
        title={confirmation.title}
        description={confirmation.description}
        confirmLabel={confirmation.label}
        danger={pendingAction === "reject"}
        onCancel={() => setPendingAction(null)}
        onConfirm={() => void submitDecision()}
      />
    </>
  );
}
