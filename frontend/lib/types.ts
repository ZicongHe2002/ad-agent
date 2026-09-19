export type RiskDecision = "ALLOW" | "REVIEW" | "BLOCK";
export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";
export type Platform = "MOCK" | "XIAOHONGSHU" | "DOUYIN" | "WECHAT_CHANNELS";
export type MonitorState = "ACTIVE" | "PAUSED" | "ERROR";
export type ReviewStatus = "PENDING" | "APPROVED" | "EDITED_APPROVED" | "REJECTED" | "EXPIRED";
export type CandidateStatus = "GENERATED" | "SELECTED" | "REJECTED" | "BLOCKED";
export type QualityDecision = "ALLOW" | "REVIEW" | "BLOCK" | "REGENERATE";
export type RankConfidence = "EXACT" | "ESTIMATED" | "PARTIAL" | "UNKNOWN";
export type ContentProvenance =
  | "HUMAN_AUTHORED"
  | "AI_GENERATED_PENDING_REVIEW"
  | "AI_ASSISTED_HUMAN_EDITED"
  | "AI_GENERATED_HUMAN_APPROVED"
  | "AI_GENERATED_AUTO_APPROVED";
export type DisclosureStatus =
  | "NOT_REQUIRED"
  | "REQUIRED_PENDING"
  | "DECLARED"
  | "PLATFORM_APPLIED"
  | "UNKNOWN";
export type CapabilityStatus =
  | "SUPPORTED"
  | "CONDITIONAL"
  | "AUTH_REQUIRED"
  | "MANUAL"
  | "UNSUPPORTED"
  | "UNKNOWN"
  | "RATE_LIMITED"
  | "DISABLED";

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    trace_id?: string;
    details?: Record<string, unknown>;
  };
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: "ADMIN" | "BRAND_MANAGER" | "REVIEWER" | "VIEWER";
}

export interface LoginResponse {
  access_token: string;
  refresh_token?: string;
  user: User;
}

export interface TimelineEvent {
  event_id: string;
  event_type: string;
  occurred_at: string;
  trace_id?: string;
  creator_id?: string;
  post_id?: string;
  campaign_id?: string;
  payload?: Record<string, unknown>;
}

export interface PageResult<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface TimestampedRecord {
  id: string;
  created_at: string;
  updated_at: string;
}

export interface Creator extends TimestampedRecord {
  tenant_id: string | null;
  name: string;
  category: string;
  relationship_type:
    | "OWN_ACCOUNT"
    | "PARTNER_CREATOR"
    | "OFFICIAL_CAMPAIGN_CREATOR"
    | "GENERAL_CREATOR"
    | "BRAND_ACCOUNT"
    | "COMPETITOR"
    | "BLOCKED_CREATOR";
  priority: number;
  normal_poll_interval_sec: number;
  warm_poll_interval_sec: number;
  hot_poll_interval_sec: number;
  expected_publish_windows: Array<Record<string, unknown>>;
  last_checked_at: string | null;
  last_post_at: string | null;
  monitor_state: MonitorState;
}

export interface CreatorMonitorResult {
  creator_id: string;
  monitor_state: MonitorState;
}

export interface TaskResult {
  task_id: string;
  creator_id?: string;
  post_id?: string;
}

export interface Post extends TimestampedRecord {
  platform: Platform;
  external_post_id: string;
  creator_id: string;
  published_at: string;
  detected_at: string;
  content_updated_at: string | null;
  status: "ACTIVE" | "DELETED" | "UNKNOWN";
  raw_payload_hash: string;
  source_capability_snapshot_id: string | null;
}

export interface PostContent {
  post_id: string;
  title: string | null;
  caption: string | null;
  hashtags: string[];
  mentions: string[];
  ocr_text: string | null;
  transcript: string | null;
  visual_summary: string | null;
  content_language: string;
  content_hash: string;
  data_completeness: number;
  model_derived_fields: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PostAnchor extends TimestampedRecord {
  post_id: string;
  anchor_type: "OBJECT" | "COLOR" | "STYLE" | "TOPIC" | "QUOTE" | "ACTION" | "CLAIM";
  anchor_text: string;
  source_field: string;
  confidence: number;
}

export interface CommentCandidate extends TimestampedRecord {
  comment_job_id: string | null;
  post_id: string;
  campaign_id: string;
  brand_account_id: string;
  strategy:
    | "NORMAL_INTERACTION"
    | "EXPERT_COMMENT"
    | "LIGHT_BRAND_MENTION"
    | "PARTNER_BRAND_COMMENT"
    | "PRODUCT_RELATED"
    | "CAMPAIGN_DISCLOSURE"
    | "SKIP";
  text: string;
  normalized_text: string;
  content_provenance: ContentProvenance;
  disclosure_status: DisclosureStatus;
  prompt_version: string;
  prompt_hash: string | null;
  model_provider: string;
  model_name: string;
  model_request_id: string | null;
  relevance_score: number;
  commercial_score: number;
  confidence: number;
  referenced_anchor_ids: string[];
  referenced_claim_ids: string[];
  generation_reason: string;
  uses_first_person_experience: boolean;
  implies_consumer_identity: boolean;
  status: CandidateStatus;
}

export interface CommentQualityEvaluation extends TimestampedRecord {
  candidate_id: string;
  anchor_coverage: number;
  specificity: number;
  fluency: number;
  voice_match: number;
  novelty: number;
  truthfulness: number;
  identity_consistency: number;
  duplicate_similarity_max: number;
  generic_praise_detected: boolean;
  fake_experience_detected: boolean;
  fake_identity_detected: boolean;
  unsupported_claim_detected: boolean;
  random_typo_pattern_detected: boolean;
  quality_score: number;
  decision: QualityDecision;
  reasons: string[];
}

export interface RiskEvent extends TimestampedRecord {
  candidate_id: string;
  rule_decision: RiskDecision;
  llm_decision: RiskDecision | null;
  final_decision: RiskDecision;
  risk_score: number;
  matched_rules: string[];
  reasons: string[];
  policy_versions: Record<string, string>;
}

export interface ReviewJob extends TimestampedRecord {
  candidate_id: string;
  status: ReviewStatus;
  assigned_to: string | null;
  submitted_at: string;
  expires_at: string | null;
  resolved_at: string | null;
  original_candidate_text: string;
  final_text: string | null;
  review_notes: string | null;
  edit_reason: string | null;
  edit_distance: number | null;
}

export interface ReviewJobDetail extends ReviewJob {
  candidate: CommentCandidate | null;
  quality: CommentQualityEvaluation | null;
  risk_events: RiskEvent[];
  anchors: PostAnchor[];
}

export interface PostDetail extends Post {
  content: PostContent | null;
  anchors: PostAnchor[];
  candidates: CommentCandidate[];
}

export interface PostTimelineEvent extends TimestampedRecord {
  event_type: string;
  aggregate_type: string;
  aggregate_id: string;
  comment_job_id: string | null;
  trace_id: string;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface PostTimeline {
  post_id: string;
  events: PostTimelineEvent[];
}

export interface PublishedComment extends TimestampedRecord {
  publish_job_id: string;
  post_id: string;
  campaign_id: string | null;
  creator_id: string | null;
  brand_account_id: string;
  platform: Platform;
  external_comment_id: string | null;
  final_text: string;
  content_provenance: ContentProvenance;
  disclosure_status: DisclosureStatus;
  published_at: string;
  chronological_rank: number | null;
  chronological_rank_confidence: RankConfidence;
  visible_rank: number | null;
  visible_rank_confidence: RankConfidence;
  removed_at: string | null;
  rank_observed_at: string | null;
}
