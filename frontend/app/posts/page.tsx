"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button, EmptyState, PageHeader, Panel, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { errorMessage, formatDateTime, formatPercent, shortId, statusTone } from "@/lib/format";
import type { Creator, PageResult, Platform, Post, PostDetail, PostTimeline } from "@/lib/types";

function detectionLatency(post: Post): string {
  const published = new Date(post.published_at).getTime();
  const detected = new Date(post.detected_at).getTime();
  if (Number.isNaN(published) || Number.isNaN(detected)) return "—";
  const seconds = Math.max(0, (detected - published) / 1000);
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${(seconds / 60).toFixed(1)}m`;
}

export default function PostsPage() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [creators, setCreators] = useState<Creator[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [search, setSearch] = useState("");
  const [platform, setPlatform] = useState<Platform | "ALL">("ALL");
  const [postStatus, setPostStatus] = useState<Post["status"] | "ALL">("ALL");
  const [selectedPostId, setSelectedPostId] = useState<string>();
  const [detail, setDetail] = useState<PostDetail>();
  const [timeline, setTimeline] = useState<PostTimeline>();
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string>();
  const detailRequest = useRef<string | undefined>(undefined);

  const loadPosts = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const [postPage, creatorPage] = await Promise.all([
        api.get<PageResult<Post>>("/posts?limit=500"),
        api.get<PageResult<Creator>>("/creators?limit=500"),
      ]);
      setPosts(postPage.items);
      setCreators(creatorPage.items);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.all([
      api.get<PageResult<Post>>("/posts?limit=500"),
      api.get<PageResult<Creator>>("/creators?limit=500"),
    ])
      .then(([postPage, creatorPage]) => {
        if (!active) return;
        setPosts(postPage.items);
        setCreators(creatorPage.items);
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

  const filteredPosts = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return posts.filter((post) => {
      const creatorName = creatorNames.get(post.creator_id) ?? "";
      const matchesSearch =
        !query ||
        post.external_post_id.toLocaleLowerCase().includes(query) ||
        creatorName.toLocaleLowerCase().includes(query);
      const matchesPlatform = platform === "ALL" || post.platform === platform;
      const matchesStatus = postStatus === "ALL" || post.status === postStatus;
      return matchesSearch && matchesPlatform && matchesStatus;
    });
  }, [creatorNames, platform, postStatus, posts, search]);

  const inspectPost = async (post: Post) => {
    detailRequest.current = post.id;
    setSelectedPostId(post.id);
    setDetailLoading(true);
    setDetailError(undefined);
    try {
      const [postDetail, postTimeline] = await Promise.all([
        api.get<PostDetail>(`/posts/${post.id}`),
        api.get<PostTimeline>(`/posts/${post.id}/timeline`),
      ]);
      if (detailRequest.current !== post.id) return;
      setDetail(postDetail);
      setTimeline(postTimeline);
    } catch (requestError) {
      if (detailRequest.current !== post.id) return;
      setDetail(undefined);
      setTimeline(undefined);
      setDetailError(errorMessage(requestError));
    } finally {
      if (detailRequest.current === post.id) setDetailLoading(false);
    }
  };

  const activeCount = posts.filter((post) => post.status === "ACTIVE").length;
  const platforms = new Set(posts.map((post) => post.platform)).size;
  const creatorCoverage = new Set(posts.map((post) => post.creator_id)).size;

  return (
    <>
      <PageHeader
        eyebrow="CONTENT PIPELINE"
        title="Posts"
        description="Inspect normalized content, extracted anchors, and the persisted processing timeline."
        actions={<Button onClick={() => void loadPosts()} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</Button>}
      />
      <div className="stats-grid">
        <StatCard label="Loaded posts" value={String(posts.length)} detail="Current tenant scope" tone="info" />
        <StatCard label="Creator coverage" value={String(creatorCoverage)} detail="Creators represented in this result" tone="success" />
        <StatCard label="Active posts" value={String(activeCount)} detail="Not deleted or unknown" />
        <StatCard label="Platforms" value={String(platforms)} detail="Represented in this result" />
      </div>
      {error ? <div className="callout callout-danger" role="alert" style={{ marginBottom: 18 }}>{error}</div> : null}
      <div className="stack">
        <Panel title="Recent posts" description="List data comes from the normalized post ledger.">
          <div className="filter-bar">
            <input
              className="input"
              placeholder="Search external ID or creator…"
              aria-label="Search posts"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <select
              className="select"
              aria-label="Filter platform"
              value={platform}
              onChange={(event) => setPlatform(event.target.value as Platform | "ALL")}
            >
              <option value="ALL">All platforms</option>
              <option value="MOCK">Mock</option>
              <option value="DOUYIN">Douyin</option>
              <option value="XIAOHONGSHU">Xiaohongshu</option>
              <option value="WECHAT_CHANNELS">WeChat Channels</option>
            </select>
            <select
              className="select"
              aria-label="Filter post status"
              value={postStatus}
              onChange={(event) => setPostStatus(event.target.value as Post["status"] | "ALL")}
            >
              <option value="ALL">All statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="DELETED">Deleted</option>
              <option value="UNKNOWN">Unknown</option>
            </select>
          </div>
          {loading && posts.length === 0 ? (
            <EmptyState title="Loading posts" detail="Reading normalized posts from the API…" />
          ) : filteredPosts.length === 0 ? (
            <EmptyState
              title={posts.length === 0 ? "No posts detected" : "No posts match these filters"}
              detail={posts.length === 0 ? "Poll an active creator or run the demo workflow to ingest a post." : "Change the search, platform, or status filter."}
            />
          ) : (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead><tr><th>Post</th><th>Creator</th><th>Platform</th><th>Status</th><th>Detected</th><th>Latency</th><th /></tr></thead>
                <tbody>
                  {filteredPosts.map((post) => (
                    <tr key={post.id}>
                      <td><span className="cell-primary">{post.external_post_id}</span><span className="cell-secondary">Internal {shortId(post.id)}</span></td>
                      <td>{creatorNames.get(post.creator_id) ?? shortId(post.creator_id)}</td>
                      <td>{post.platform}</td>
                      <td><Badge tone={statusTone(post.status)}>{post.status}</Badge></td>
                      <td>{formatDateTime(post.detected_at)}</td>
                      <td className="mono">{detectionLatency(post)}</td>
                      <td><Button variant="ghost" onClick={() => void inspectPost(post)} disabled={detailLoading && selectedPostId === post.id}>{detailLoading && selectedPostId === post.id ? "Loading…" : "Inspect"}</Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        {selectedPostId ? (
          <Panel
            title={detail?.content?.title ?? `Post ${shortId(selectedPostId)}`}
            description="Normalized context, anchors, candidates, and durable events."
            actions={<Button variant="ghost" onClick={() => { detailRequest.current = undefined; setSelectedPostId(undefined); setDetail(undefined); setTimeline(undefined); setDetailLoading(false); }}>Close</Button>}
          >
            {detailError ? <div className="panel-body"><div className="callout callout-danger" role="alert">{detailError}</div></div> : null}
            {detailLoading ? <EmptyState title="Loading post detail" detail="Reading content and timeline events…" /> : detail ? (
              <div className="panel-body stack">
                <div className="callout">
                  {detail.content?.caption ?? detail.content?.visual_summary ?? "No caption or visual summary is available for this post."}
                </div>
                <dl className="detail-list">
                  <div><dt>Published</dt><dd>{formatDateTime(detail.published_at)}</dd></div>
                  <div><dt>Data completeness</dt><dd>{detail.content ? `${formatPercent(detail.content.data_completeness)}%` : "Unknown"}</dd></div>
                  <div><dt>Anchors</dt><dd>{detail.anchors.length}</dd></div>
                  <div><dt>Candidates</dt><dd>{detail.candidates.length}</dd></div>
                  <div><dt>Capability snapshot</dt><dd className="mono">{shortId(detail.source_capability_snapshot_id)}</dd></div>
                </dl>
                {detail.anchors.length > 0 ? (
                  <div className="anchor-list" style={{ padding: 0 }}>
                    {detail.anchors.map((anchor) => <span className="anchor" key={anchor.id}>{anchor.anchor_type} · {anchor.anchor_text}</span>)}
                  </div>
                ) : <div className="callout">No anchors have been persisted for this post.</div>}
                <div className="data-table-wrap">
                  <table className="data-table">
                    <thead><tr><th>Timeline event</th><th>Occurred</th><th>Aggregate</th><th>Trace</th></tr></thead>
                    <tbody>
                      {timeline?.events.map((event) => (
                        <tr key={event.id}><td>{event.event_type}</td><td>{formatDateTime(event.occurred_at)}</td><td>{event.aggregate_type} · {shortId(event.aggregate_id)}</td><td className="mono">{shortId(event.trace_id)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                  {timeline?.events.length === 0 ? <EmptyState title="No timeline events" detail="This post has no persisted processing events yet." /> : null}
                </div>
              </div>
            ) : null}
          </Panel>
        ) : null}
      </div>
    </>
  );
}
