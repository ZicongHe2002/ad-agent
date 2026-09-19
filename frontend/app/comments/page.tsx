"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Button, EmptyState, PageHeader, Panel, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { ManualPublishingPanel } from "@/components/manual-publishing";
import { errorMessage, formatDateTime, shortId, statusTone } from "@/lib/format";
import type {
  CandidateStatus,
  CommentCandidate,
  ContentProvenance,
  Creator,
  PageResult,
  Post,
  PublishedComment,
  RankConfidence,
} from "@/lib/types";

type LedgerView = "published" | "candidates";

function rankLabel(rank: number | null, confidence: RankConfidence): string {
  return rank === null ? "Unknown" : `#${rank} ${confidence.toLocaleLowerCase()}`;
}

function csvCell(value: unknown): string {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

export default function CommentsPage() {
  const [published, setPublished] = useState<PublishedComment[]>([]);
  const [candidates, setCandidates] = useState<CommentCandidate[]>([]);
  const [creators, setCreators] = useState<Creator[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [view, setView] = useState<LedgerView>("published");
  const [provenance, setProvenance] = useState<ContentProvenance | "ALL">("ALL");
  const [candidateStatus, setCandidateStatus] = useState<CandidateStatus | "ALL">("ALL");
  const [search, setSearch] = useState("");

  const loadLedger = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const [publishedPage, candidatePage, creatorPage, postPage] = await Promise.all([
        api.get<PageResult<PublishedComment>>("/comments/published?limit=500"),
        api.get<PageResult<CommentCandidate>>("/comments/candidates?limit=500"),
        api.get<PageResult<Creator>>("/creators?limit=500"),
        api.get<PageResult<Post>>("/posts?limit=500"),
      ]);
      setPublished(publishedPage.items);
      setCandidates(candidatePage.items);
      setCreators(creatorPage.items);
      setPosts(postPage.items);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.all([
      api.get<PageResult<PublishedComment>>("/comments/published?limit=500"),
      api.get<PageResult<CommentCandidate>>("/comments/candidates?limit=500"),
      api.get<PageResult<Creator>>("/creators?limit=500"),
      api.get<PageResult<Post>>("/posts?limit=500"),
    ])
      .then(([publishedPage, candidatePage, creatorPage, postPage]) => {
        if (!active) return;
        setPublished(publishedPage.items);
        setCandidates(candidatePage.items);
        setCreators(creatorPage.items);
        setPosts(postPage.items);
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

  const creatorNames = useMemo(
    () => new Map(creators.map((creator) => [creator.id, creator.name])),
    [creators],
  );
  const postCreators = useMemo(
    () => new Map(posts.map((post) => [post.id, post.creator_id])),
    [posts],
  );

  const filteredPublished = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return published.filter((comment) => {
      const creatorName = comment.creator_id ? creatorNames.get(comment.creator_id) ?? "" : "";
      return (
        (provenance === "ALL" || comment.content_provenance === provenance) &&
        (!query ||
          comment.final_text.toLocaleLowerCase().includes(query) ||
          creatorName.toLocaleLowerCase().includes(query) ||
          comment.external_comment_id?.toLocaleLowerCase().includes(query))
      );
    });
  }, [creatorNames, provenance, published, search]);

  const filteredCandidates = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return candidates.filter((candidate) => {
      const creatorId = postCreators.get(candidate.post_id);
      const creatorName = creatorId ? creatorNames.get(creatorId) ?? "" : "";
      return (
        (provenance === "ALL" || candidate.content_provenance === provenance) &&
        (candidateStatus === "ALL" || candidate.status === candidateStatus) &&
        (!query ||
          candidate.text.toLocaleLowerCase().includes(query) ||
          creatorName.toLocaleLowerCase().includes(query))
      );
    });
  }, [candidateStatus, candidates, creatorNames, postCreators, provenance, search]);

  const exportCsv = () => {
    const rows = view === "published"
      ? [
          ["id", "text", "creator", "platform", "provenance", "disclosure", "chronological_rank", "visible_rank", "published_at"],
          ...filteredPublished.map((comment) => [
            comment.id,
            comment.final_text,
            comment.creator_id ? creatorNames.get(comment.creator_id) ?? comment.creator_id : "",
            comment.platform,
            comment.content_provenance,
            comment.disclosure_status,
            comment.chronological_rank ?? "",
            comment.visible_rank ?? "",
            comment.published_at,
          ]),
        ]
      : [
          ["id", "text", "creator", "strategy", "status", "provenance", "disclosure", "created_at"],
          ...filteredCandidates.map((candidate) => {
            const creatorId = postCreators.get(candidate.post_id);
            return [
              candidate.id,
              candidate.text,
              creatorId ? creatorNames.get(creatorId) ?? creatorId : "",
              candidate.strategy,
              candidate.status,
              candidate.content_provenance,
              candidate.disclosure_status,
              candidate.created_at,
            ];
          }),
        ];
    const blob = new Blob([rows.map((row) => row.map(csvCell).join(",")).join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `firstcomment-${view}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const exactRanks = published.filter(
    (comment) => comment.chronological_rank_confidence === "EXACT",
  ).length;
  const removedCount = published.filter((comment) => comment.removed_at !== null).length;
  const pendingDisclosure = [...published, ...candidates].filter(
    (comment) => comment.disclosure_status === "REQUIRED_PENDING",
  ).length;

  return (
    <>
      <PageHeader
        eyebrow="CONTENT LEDGER"
        title="Comments"
        description="Review persisted candidates and published comments with provenance, disclosure, and measured rank."
        actions={
          <div className="button-row">
            <Button onClick={() => void loadLedger()} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</Button>
            <Button onClick={exportCsv} disabled={view === "published" ? filteredPublished.length === 0 : filteredCandidates.length === 0}>Download current CSV</Button>
          </div>
        }
      />
      <div className="stats-grid">
        <StatCard label="Published loaded" value={String(published.length)} detail={`${exactRanks} with exact chronological rank`} tone="success" />
        <StatCard label="Candidates loaded" value={String(candidates.length)} detail="All candidate states" />
        <StatCard label="Disclosure pending" value={String(pendingDisclosure)} detail="Requires resolution before publishing" tone="warning" />
        <StatCard label="Removed" value={String(removedCount)} detail="Recorded platform removals" tone={removedCount ? "danger" : "neutral"} />
      </div>
      {error ? <div className="callout callout-danger" role="alert" style={{ marginBottom: 18 }}>{error}</div> : null}
      <div style={{ marginBottom: 18 }}><ManualPublishingPanel onCompleted={() => void loadLedger()} /></div>
      <Panel title="Comment ledger" description="Unknown platform rank is reported as unknown, never as a failure.">
        <div className="filter-bar">
          <select className="select" aria-label="Comment view" value={view} onChange={(event) => setView(event.target.value as LedgerView)}>
            <option value="published">Published comments</option>
            <option value="candidates">Generated candidates</option>
          </select>
          <input className="input" aria-label="Search comments" placeholder="Search text or creator…" value={search} onChange={(event) => setSearch(event.target.value)} />
          <select className="select" aria-label="Provenance" value={provenance} onChange={(event) => setProvenance(event.target.value as ContentProvenance | "ALL")}>
            <option value="ALL">All provenance</option>
            <option value="HUMAN_AUTHORED">Human authored</option>
            <option value="AI_GENERATED_PENDING_REVIEW">AI generated, pending review</option>
            <option value="AI_ASSISTED_HUMAN_EDITED">AI assisted, human edited</option>
            <option value="AI_GENERATED_HUMAN_APPROVED">AI generated, human approved</option>
            <option value="AI_GENERATED_AUTO_APPROVED">AI generated, auto approved</option>
          </select>
          {view === "candidates" ? (
            <select className="select" aria-label="Candidate status" value={candidateStatus} onChange={(event) => setCandidateStatus(event.target.value as CandidateStatus | "ALL")}>
              <option value="ALL">All candidate statuses</option>
              <option value="GENERATED">Generated</option>
              <option value="SELECTED">Selected</option>
              <option value="REJECTED">Rejected</option>
              <option value="BLOCKED">Blocked</option>
            </select>
          ) : null}
        </div>
        {loading && published.length === 0 && candidates.length === 0 ? (
          <EmptyState title="Loading comment ledger" detail="Reading published comments and generated candidates…" />
        ) : view === "published" ? (
          filteredPublished.length === 0 ? (
            <EmptyState title="No published comments" detail={published.length === 0 ? "No successful or manually confirmed publishes are recorded yet." : "No published comments match these filters."} />
          ) : (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead><tr><th>Comment</th><th>Creator</th><th>Platform</th><th>Provenance</th><th>Disclosure</th><th>Chronological</th><th>Visible</th><th>Published</th></tr></thead>
                <tbody>
                  {filteredPublished.map((comment) => (
                    <tr key={comment.id}>
                      <td><span className="cell-primary">{comment.final_text}</span><span className="cell-secondary">External {shortId(comment.external_comment_id)}</span></td>
                      <td>{comment.creator_id ? creatorNames.get(comment.creator_id) ?? shortId(comment.creator_id) : "Unknown"}</td>
                      <td>{comment.platform}</td>
                      <td><Badge tone={statusTone(comment.content_provenance)}>{comment.content_provenance}</Badge></td>
                      <td><Badge tone={statusTone(comment.disclosure_status)}>{comment.disclosure_status}</Badge></td>
                      <td>{rankLabel(comment.chronological_rank, comment.chronological_rank_confidence)}</td>
                      <td>{rankLabel(comment.visible_rank, comment.visible_rank_confidence)}</td>
                      <td>{formatDateTime(comment.published_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : filteredCandidates.length === 0 ? (
          <EmptyState title="No generated candidates" detail={candidates.length === 0 ? "No candidate records have been generated yet." : "No candidates match these filters."} />
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>Candidate</th><th>Creator</th><th>Strategy</th><th>Status</th><th>Provenance</th><th>Disclosure</th><th>Created</th></tr></thead>
              <tbody>
                {filteredCandidates.map((candidate) => {
                  const creatorId = postCreators.get(candidate.post_id);
                  return (
                    <tr key={candidate.id}>
                      <td><span className="cell-primary">{candidate.text}</span><span className="cell-secondary">Post {shortId(candidate.post_id)} · confidence {Math.round(Number(candidate.confidence) * 100)}%</span></td>
                      <td>{creatorId ? creatorNames.get(creatorId) ?? shortId(creatorId) : "Unknown"}</td>
                      <td>{candidate.strategy}</td>
                      <td><Badge tone={statusTone(candidate.status)}>{candidate.status}</Badge></td>
                      <td><Badge tone={statusTone(candidate.content_provenance)}>{candidate.content_provenance}</Badge></td>
                      <td><Badge tone={statusTone(candidate.disclosure_status)}>{candidate.disclosure_status}</Badge></td>
                      <td>{formatDateTime(candidate.created_at)}</td>
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
