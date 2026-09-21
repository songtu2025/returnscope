// 此文件由 OpenAPI 自动生成，请勿手动修改。

export type ClientOptions = {
  baseUrl: `${string}://${string}` | (string & {});
};

/**
 * CategoryDefinition
 */
export type CategoryDefinition = {
  /**
   * Code
   */
  code: string;
  /**
   * Name
   */
  name: string;
  /**
   * Parent Code
   */
  parent_code?: string | null;
};

/**
 * ClaimEvidenceRequirement
 */
export type ClaimEvidenceRequirement = {
  /**
   * Claim Id
   */
  claim_id: string;
  /**
   * Cues
   */
  cues: Array<string>;
  /**
   * Label Code
   */
  label_code: string;
  /**
   * Semantic Requirement
   */
  semantic_requirement?: string;
};

/**
 * ClassificationPayloadResponse
 */
export type ClassificationPayloadResponse = {
  /**
   * Classification Key
   */
  classification_key?: string | null;
  /**
   * Comment Summary
   */
  comment_summary?: {
    [key: string]: unknown;
  } | null;
  /**
   * Dimension Decisions
   */
  dimension_decisions?: Array<{
    [key: string]: unknown;
  }>;
  /**
   * Extracted Facts
   */
  extracted_facts?: Array<{
    [key: string]: unknown;
  }>;
  /**
   * Fact Mappings
   */
  fact_mappings?: Array<{
    [key: string]: unknown;
  }>;
  /**
   * Model Name
   */
  model_name?: string | null;
  /**
   * Needs Review
   */
  needs_review?: boolean | null;
  /**
   * Positive Label Codes
   */
  positive_label_codes?: Array<string>;
  /**
   * Primary Label Codes
   */
  primary_label_codes?: Array<string>;
  /**
   * Problem Label Codes
   */
  problem_label_codes?: Array<string>;
  /**
   * Prompt Version
   */
  prompt_version?: string | null;
  /**
   * Review Reasons
   */
  review_reasons?: Array<string>;
  /**
   * Semantic Relations
   */
  semantic_relations?: Array<{
    [key: string]: unknown;
  }>;
  semantic_review?: SemanticReviewResponse | null;
  /**
   * Semantic Units
   */
  semantic_units?: Array<ClassificationSemanticFactResponse>;
  /**
   * Status
   */
  status?: string | null;
  /**
   * Taxonomy Version
   */
  taxonomy_version?: string | null;
  /**
   * Unknown Semantics
   */
  unknown_semantics?: Array<ClassificationUnknownSemanticResponse>;
  [key: string]: unknown;
};

/**
 * ClassificationResultBlockingReasonResponse
 */
export type ClassificationResultBlockingReasonResponse = {
  /**
   * Code
   */
  code: string;
  /**
   * Message
   */
  message: string;
  [key: string]: unknown;
};

/**
 * ClassificationResultCommentStatusCountResponse
 */
export type ClassificationResultCommentStatusCountResponse = {
  /**
   * Comment Count
   */
  comment_count: number;
  /**
   * Status
   */
  status: "POSITIVE" | "NEGATIVE" | "MIXED" | "CONFLICT" | "NO_CONFIRMED";
  [key: string]: unknown;
};

/**
 * ClassificationResultDispositionCountResponse
 */
export type ClassificationResultDispositionCountResponse = {
  /**
   * Comment Count
   */
  comment_count: number;
  /**
   * Record Count
   */
  record_count: number;
  /**
   * Semantic Disposition
   */
  semantic_disposition: string;
  [key: string]: unknown;
};

/**
 * ClassificationResultDrilldownItemResponse
 */
export type ClassificationResultDrilldownItemResponse = {
  /**
   * Label Code
   */
  label_code?: string | null;
  /**
   * Label Group
   */
  label_group?: string | null;
  /**
   * Label Name
   */
  label_name?: string | null;
  /**
   * Label Path
   */
  label_path?: Array<string> | null;
  /**
   * Parent Code
   */
  parent_code?: string | null;
  /**
   * Record Count
   */
  record_count: number;
  /**
   * Unit Count
   */
  unit_count: number;
  /**
   * Value
   */
  value: string | null;
  [key: string]: unknown;
};

/**
 * ClassificationResultDrilldownResponse
 */
export type ClassificationResultDrilldownResponse = {
  /**
   * Group By
   */
  group_by: "category" | "problem" | "product_name" | "product_sku";
  /**
   * Items
   */
  items: Array<ClassificationResultDrilldownItemResponse>;
  /**
   * Page
   */
  page: number;
  /**
   * Page Size
   */
  page_size: number;
  /**
   * Total
   */
  total: number;
  [key: string]: unknown;
};

/**
 * ClassificationResultGroupMemberResponse
 */
export type ClassificationResultGroupMemberResponse = {
  /**
   * Comment
   */
  comment?: string | null;
  /**
   * Reason
   */
  reason?: string | null;
  /**
   * Return Date
   */
  return_date?: string | null;
  /**
   * Source Origin Id
   */
  source_origin_id?: string | null;
  /**
   * Source Record Id
   */
  source_record_id: string;
  /**
   * Source Row
   */
  source_row: number;
  [key: string]: unknown;
};

/**
 * ClassificationResultGroupResponse
 */
export type ClassificationResultGroupResponse = {
  /**
   * Member Count
   */
  member_count: number;
  /**
   * Members
   */
  members: Array<ClassificationResultGroupMemberResponse>;
  record: ClassificationResultRecordResponse;
  [key: string]: unknown;
};

/**
 * ClassificationResultGroupsResponse
 */
export type ClassificationResultGroupsResponse = {
  /**
   * Items
   */
  items: Array<ClassificationResultGroupResponse>;
  /**
   * Page
   */
  page: number;
  /**
   * Page Size
   */
  page_size: number;
  /**
   * Source Total
   */
  source_total: number;
  /**
   * Total
   */
  total: number;
  [key: string]: unknown;
};

/**
 * ClassificationResultListResponse
 */
export type ClassificationResultListResponse = {
  /**
   * Items
   */
  items: Array<ClassificationResultVersionResponse>;
  /**
   * Page
   */
  page: number;
  /**
   * Page Size
   */
  page_size: number;
  /**
   * Total
   */
  total: number;
  [key: string]: unknown;
};

/**
 * ClassificationResultMetricsResponse
 */
export type ClassificationResultMetricsResponse = {
  /**
   * Comment Count
   */
  comment_count: number;
  /**
   * Event Count
   */
  event_count: number;
  /**
   * Fact Count
   */
  fact_count: number;
  /**
   * Primary Unit
   */
  primary_unit: "comment";
  /**
   * Source Record Count
   */
  source_record_count: number;
  [key: string]: unknown;
};

/**
 * ClassificationResultProblemCountResponse
 */
export type ClassificationResultProblemCountResponse = {
  /**
   * Comment Count
   */
  comment_count: number;
  /**
   * Label Code
   */
  label_code: string;
  /**
   * Label Group
   */
  label_group: string | null;
  /**
   * Label Name
   */
  label_name: string | null;
  /**
   * Label Path
   */
  label_path: Array<string>;
  /**
   * Record Count
   */
  record_count: number;
  /**
   * Unit Count
   */
  unit_count: number;
  [key: string]: unknown;
};

/**
 * ClassificationResultProcessingCountResponse
 */
export type ClassificationResultProcessingCountResponse = {
  /**
   * Comment Count
   */
  comment_count: number;
  /**
   * Processing Status
   */
  processing_status: string;
  /**
   * Record Count
   */
  record_count: number;
  /**
   * Unit Count
   */
  unit_count: number;
  [key: string]: unknown;
};

/**
 * ClassificationResultQualityCountResponse
 */
export type ClassificationResultQualityCountResponse = {
  /**
   * Comment Count
   */
  comment_count: number;
  /**
   * Quality Status
   */
  quality_status: string;
  /**
   * Record Count
   */
  record_count: number;
  /**
   * Unit Count
   */
  unit_count: number;
  [key: string]: unknown;
};

/**
 * ClassificationResultRecordResponse
 */
export type ClassificationResultRecordResponse = {
  /**
   * Asin
   */
  asin?: string | null;
  /**
   * Atomic Facts
   */
  atomic_facts?: Array<ClassificationSemanticFactResponse>;
  /**
   * Category A
   */
  category_a?: string | null;
  /**
   * Category B
   */
  category_b?: string | null;
  classification: ClassificationPayloadResponse;
  /**
   * Classification Key
   */
  classification_key: string;
  /**
   * Comment
   */
  comment?: string | null;
  /**
   * Comment Conclusions
   */
  comment_conclusions?: Array<ClassificationTopicSummaryResponse>;
  /**
   * Comment Summary Status
   */
  comment_summary_status: string;
  /**
   * Event Count
   */
  event_count: number;
  /**
   * Fact Count
   */
  fact_count: number;
  /**
   * Fnsku
   */
  fnsku?: string | null;
  /**
   * Id
   */
  id: string;
  /**
   * Ignored Semantics
   */
  ignored_semantics?: Array<ClassificationUnknownSemanticResponse>;
  /**
   * Listing
   */
  listing?: string | null;
  /**
   * Matched Msku
   */
  matched_msku?: string | null;
  /**
   * Order Id
   */
  order_id?: string | null;
  /**
   * Problem Labels
   */
  problem_labels?: Array<string>;
  /**
   * Processing Status
   */
  processing_status: string;
  /**
   * Product Match Status
   */
  product_match_status: string;
  /**
   * Product Name
   */
  product_name?: string | null;
  /**
   * Product Sku
   */
  product_sku?: string | null;
  /**
   * Quality Status
   */
  quality_status: string;
  /**
   * Reason
   */
  reason?: string | null;
  /**
   * Result Version Id
   */
  result_version_id: string;
  /**
   * Return Date
   */
  return_date?: string | null;
  /**
   * Semantic Disposition
   */
  semantic_disposition: string;
  /**
   * Source Origin Id
   */
  source_origin_id?: string | null;
  /**
   * Source Record Id
   */
  source_record_id: string;
  /**
   * Source Row
   */
  source_row: number;
  /**
   * Source Sku
   */
  source_sku?: string | null;
  /**
   * Store Site
   */
  store_site?: string | null;
  /**
   * Unknown Semantics
   */
  unknown_semantics?: Array<ClassificationUnknownSemanticResponse>;
  [key: string]: unknown;
};

/**
 * ClassificationResultRecordsResponse
 */
export type ClassificationResultRecordsResponse = {
  /**
   * Items
   */
  items: Array<ClassificationResultRecordResponse>;
  /**
   * Page
   */
  page: number;
  /**
   * Page Size
   */
  page_size: number;
  taxonomy?: TaxonomyConfig | null;
  /**
   * Total
   */
  total: number;
  [key: string]: unknown;
};

/**
 * ClassificationResultSummaryResponse
 */
export type ClassificationResultSummaryResponse = {
  /**
   * Comment Count
   */
  comment_count: number;
  /**
   * Comment Statuses
   */
  comment_statuses: Array<ClassificationResultCommentStatusCountResponse>;
  /**
   * Hierarchy Problems
   */
  hierarchy_problems: Array<ClassificationResultDrilldownItemResponse>;
  metrics: ClassificationResultMetricsResponse;
  /**
   * Processing Statuses
   */
  processing_statuses: Array<ClassificationResultProcessingCountResponse>;
  /**
   * Quality
   */
  quality: Array<ClassificationResultQualityCountResponse>;
  /**
   * Semantic Dispositions
   */
  semantic_dispositions: Array<ClassificationResultDispositionCountResponse>;
  /**
   * Top Problems
   */
  top_problems: Array<ClassificationResultProblemCountResponse>;
  /**
   * Topic Summaries
   */
  topic_summaries: Array<ClassificationResultTopicAggregateResponse>;
  /**
   * Total Comment Count
   */
  total_comment_count: number;
  /**
   * Version Id
   */
  version_id: string;
  [key: string]: unknown;
};

/**
 * ClassificationResultTaxonomyLabelResponse
 */
export type ClassificationResultTaxonomyLabelResponse = {
  /**
   * Allowed Claim Ids
   */
  allowed_claim_ids?: Array<string>;
  /**
   * Allowed Sentiments
   */
  allowed_sentiments: Array<SentimentCode>;
  /**
   * Code
   */
  code: string;
  /**
   * Description
   */
  description?: string;
  /**
   * Examples
   */
  examples?: Array<LabelExample>;
  /**
   * Exclusions
   */
  exclusions?: Array<string>;
  /**
   * Group
   */
  group?: string;
  /**
   * Keywords
   */
  keywords?: Array<string>;
  /**
   * Label Path
   */
  label_path: Array<string>;
  /**
   * Name
   */
  name: string;
  /**
   * Parent Code
   */
  parent_code?: string | null;
  [key: string]: unknown;
};

/**
 * ClassificationResultTaxonomyResponse
 */
export type ClassificationResultTaxonomyResponse = {
  /**
   * Agent Family
   */
  agent_family: string;
  /**
   * Allowed Parts
   */
  allowed_parts?: Array<string>;
  /**
   * Categories
   */
  categories?: Array<CategoryDefinition>;
  /**
   * Instructions
   */
  instructions?: Array<string>;
  /**
   * Labels
   */
  labels: Array<ClassificationResultTaxonomyLabelResponse>;
  /**
   * Product Context
   */
  product_context: string;
  /**
   * Recognition Profile
   */
  recognition_profile?: "legacy_v3" | "keyword_free_v1" | "semantic_v1" | "fact_v2";
  /**
   * Standard Id
   */
  standard_id: string;
  /**
   * Standard Name
   */
  standard_name: string;
  /**
   * Standard Version
   */
  standard_version: number;
  /**
   * Standard Version Id
   */
  standard_version_id: string;
  /**
   * Structure Version
   */
  structure_version?: 1 | 2;
  validation_rules?: TaxonomyValidationRules;
  /**
   * Version
   */
  version: string;
  [key: string]: unknown;
};

/**
 * ClassificationResultTopicAggregateResponse
 */
export type ClassificationResultTopicAggregateResponse = {
  /**
   * Comment Count
   */
  comment_count: number;
  /**
   * Event Count
   */
  event_count: number;
  /**
   * Fact Count
   */
  fact_count: number;
  /**
   * Status Counts
   */
  status_counts: {
    [key: string]: number;
  };
  /**
   * Topic Code
   */
  topic_code: string;
  /**
   * Topic Code Path
   */
  topic_code_path: Array<string>;
  /**
   * Topic Name
   */
  topic_name: string;
  /**
   * Topic Path
   */
  topic_path: Array<string>;
  [key: string]: unknown;
};

/**
 * ClassificationResultVersionResponse
 */
export type ClassificationResultVersionResponse = {
  /**
   * Agent Family
   */
  agent_family: string;
  /**
   * Agent Key
   */
  agent_key: string;
  /**
   * Analysis Context
   */
  analysis_context: "returns" | "review" | "user_feedback";
  /**
   * Blocking Reasons
   */
  blocking_reasons: Array<ClassificationResultBlockingReasonResponse>;
  /**
   * Changed Unit Count
   */
  changed_unit_count: number;
  /**
   * Claims Version
   */
  claims_version: string | null;
  /**
   * Content Hash
   */
  content_hash: string;
  /**
   * Created At
   */
  created_at: string;
  /**
   * Created By
   */
  created_by: string | null;
  /**
   * Created By Name
   */
  created_by_name: string | null;
  /**
   * Dashboard Eligibility
   */
  dashboard_eligibility: boolean;
  /**
   * Dataset Name
   */
  dataset_name: string;
  /**
   * Dataset Version
   */
  dataset_version: number;
  /**
   * Dataset Version Id
   */
  dataset_version_id: string;
  /**
   * Delivery Status
   */
  delivery_status: "ready" | "needs_review" | "review-derived" | "unusable";
  /**
   * Inherited Unit Count
   */
  inherited_unit_count: number;
  /**
   * Listing
   */
  listing: string | null;
  /**
   * Logic Version
   */
  logic_version: string | null;
  /**
   * Model Policy Version
   */
  model_policy_version: string | null;
  /**
   * Parent Version Id
   */
  parent_version_id: string | null;
  /**
   * Parent Version No
   */
  parent_version_no: number | null;
  /**
   * Product Dataset Name
   */
  product_dataset_name: string;
  /**
   * Product Names
   */
  product_names: Array<string>;
  /**
   * Product Version
   */
  product_version: number;
  /**
   * Product Version Id
   */
  product_version_id: string;
  /**
   * Publish Origin
   */
  publish_origin: "original-classification" | "review-derived";
  /**
   * Publish Status
   */
  publish_status: "publishing" | "published" | "failed";
  /**
   * Published At
   */
  published_at: string | null;
  /**
   * Quality Status
   */
  quality_status: "ready" | "review_required" | "unusable";
  /**
   * Record Count
   */
  record_count: number;
  /**
   * Result Id
   */
  result_id: string;
  /**
   * Source Review Batch Id
   */
  source_review_batch_id: string | null;
  /**
   * Source Segment Id
   */
  source_segment_id: string;
  /**
   * Source Task Id
   */
  source_task_id: string;
  /**
   * Standard Id
   */
  standard_id: string | null;
  /**
   * Standard Name
   */
  standard_name: string | null;
  /**
   * Standard Version
   */
  standard_version: number | null;
  /**
   * Standard Version Id
   */
  standard_version_id: string | null;
  /**
   * Store Site
   */
  store_site: string | null;
  /**
   * Taxonomy Version
   */
  taxonomy_version: string;
  /**
   * Unit Count
   */
  unit_count: number;
  /**
   * Version
   */
  version: number;
  /**
   * Version Id
   */
  version_id: string;
  /**
   * Version Reason
   */
  version_reason: string;
  [key: string]: unknown;
};

/**
 * ClassificationSemanticFactResponse
 */
export type ClassificationSemanticFactResponse = {
  /**
   * Actor Ref
   */
  actor_ref?: string | null;
  /**
   * Assertion
   */
  assertion?: string;
  /**
   * Certainty
   */
  certainty?: string;
  /**
   * Condition
   */
  condition?:
    | string
    | {
        [key: string]: unknown;
      };
  /**
   * Event Ref
   */
  event_ref?: string | null;
  /**
   * Evidence
   */
  evidence?: string;
  /**
   * Evidence Source
   */
  evidence_source?: string;
  /**
   * Fact Id
   */
  fact_id?: string | null;
  /**
   * Fact Text Zh
   */
  fact_text_zh?: string;
  /**
   * Implicit
   */
  implicit?: boolean;
  /**
   * Label Code
   */
  label_code: string;
  /**
   * Label Code Path
   */
  label_code_path?: Array<string>;
  /**
   * Label Path
   */
  label_path?: Array<string>;
  /**
   * Object Ref
   */
  object_ref?: string;
  /**
   * Opinion
   */
  opinion?: string;
  /**
   * Original Evidence
   */
  original_evidence?: string;
  /**
   * Part
   */
  part?: string;
  /**
   * Product Ref
   */
  product_ref?: string | null;
  /**
   * Scenario
   */
  scenario?: string;
  /**
   * Sentiment
   */
  sentiment?: string;
  /**
   * Statement Type
   */
  statement_type?: string | null;
  /**
   * Usage Task
   */
  usage_task?: string;
  [key: string]: unknown;
};

/**
 * ClassificationTopicSummaryResponse
 */
export type ClassificationTopicSummaryResponse = {
  /**
   * Event Count
   */
  event_count?: number;
  /**
   * Fact Count
   */
  fact_count?: number;
  /**
   * Label Codes
   */
  label_codes?: Array<string>;
  /**
   * Status
   */
  status: "POSITIVE" | "NEGATIVE" | "MIXED" | "CONFLICT" | "NO_CONFIRMED";
  /**
   * Supporting Fact Ids
   */
  supporting_fact_ids?: Array<string>;
  /**
   * Topic Code
   */
  topic_code: string;
  /**
   * Topic Code Path
   */
  topic_code_path?: Array<string>;
  /**
   * Topic Name
   */
  topic_name: string;
  /**
   * Topic Path
   */
  topic_path?: Array<string>;
  [key: string]: unknown;
};

/**
 * ClassificationUnknownSemanticResponse
 */
export type ClassificationUnknownSemanticResponse = {
  /**
   * Disposition
   */
  disposition: string;
  /**
   * Evidence
   */
  evidence?: string;
  /**
   * Opinion
   */
  opinion?: string;
  /**
   * Reason
   */
  reason?: string;
  [key: string]: unknown;
};

/**
 * DimensionContract
 */
export type DimensionContract = {
  /**
   * Parent Code
   */
  parent_code: string;
  /**
   * Scope Fields
   */
  scope_fields: Array<
    | "source_ref"
    | "experiencer_ref"
    | "product_ref"
    | "variant_ref"
    | "event_ref"
    | "reference_basis"
    | "part"
    | "operation"
    | "condition"
  >;
  /**
   * Verdict Label Codes
   */
  verdict_label_codes: Array<string>;
};

/**
 * EvidenceRequirement
 */
export type EvidenceRequirement = {
  /**
   * Cues
   */
  cues: Array<string>;
  /**
   * Label Code
   */
  label_code: string;
  /**
   * Semantic Requirement
   */
  semantic_requirement?: string;
  /**
   * Unknown Opinion
   */
  unknown_opinion: string;
  /**
   * Unknown Reason
   */
  unknown_reason: string;
};

/**
 * HTTPValidationError
 */
export type HttpValidationError = {
  /**
   * Detail
   */
  detail?: Array<ValidationError>;
};

/**
 * ImplicitEvidenceRule
 */
export type ImplicitEvidenceRule = {
  /**
   * Cues
   */
  cues: Array<string>;
  /**
   * Label Code
   */
  label_code: string;
  /**
   * Semantic Requirement
   */
  semantic_requirement?: string;
};

/**
 * LabelDefinition
 */
export type LabelDefinition = {
  /**
   * Allowed Claim Ids
   */
  allowed_claim_ids?: Array<string>;
  /**
   * Allowed Sentiments
   */
  allowed_sentiments: Array<SentimentCode>;
  /**
   * Code
   */
  code: string;
  /**
   * Description
   */
  description?: string;
  /**
   * Examples
   */
  examples?: Array<LabelExample>;
  /**
   * Exclusions
   */
  exclusions?: Array<string>;
  /**
   * Group
   */
  group?: string;
  /**
   * Keywords
   */
  keywords?: Array<string>;
  /**
   * Name
   */
  name: string;
  /**
   * Parent Code
   */
  parent_code?: string | null;
};

/**
 * LabelExample
 */
export type LabelExample = {
  /**
   * Applies
   */
  applies: boolean;
  /**
   * Explanation
   */
  explanation: string;
  sentiment?: SentimentCode | null;
  /**
   * Text
   */
  text: string;
};

/**
 * SemanticReviewCoverageResponse
 */
export type SemanticReviewCoverageResponse = {
  /**
   * Analysis Failure
   */
  analysis_failure?: number;
  /**
   * Complete
   */
  complete?: boolean;
  /**
   * Mapped
   */
  mapped?: number;
  /**
   * No Tag Needed
   */
  no_tag_needed?: number;
  /**
   * Taxonomy Gap
   */
  taxonomy_gap?: number;
  /**
   * Total
   */
  total?: number;
  /**
   * True Ambiguity
   */
  true_ambiguity?: number;
  /**
   * Unexplained Fragment Count
   */
  unexplained_fragment_count?: number;
  [key: string]: unknown;
};

/**
 * SemanticReviewItemResponse
 */
export type SemanticReviewItemResponse = {
  /**
   * Action
   */
  action?: string | null;
  /**
   * Business Review Required
   */
  business_review_required?: boolean | null;
  /**
   * Detail
   */
  detail?: string | null;
  /**
   * Detail Status
   */
  detail_status?: string | null;
  /**
   * Diagnostic Code
   */
  diagnostic_code?: string | null;
  /**
   * Diagnostic Domain
   */
  diagnostic_domain?: string | null;
  /**
   * Diagnostic Title
   */
  diagnostic_title?: string | null;
  /**
   * Disposition
   */
  disposition: string;
  /**
   * Evidence Source
   */
  evidence_source?: string;
  /**
   * Evidence Text
   */
  evidence_text?: string;
  /**
   * Fact Id
   */
  fact_id?: string;
  /**
   * Item Id
   */
  item_id: string;
  /**
   * Label Code
   */
  label_code?: string;
  /**
   * Label Path
   */
  label_path?: Array<string>;
  /**
   * Opinion
   */
  opinion?: string;
  /**
   * Primary Result
   */
  primary_result?: string | null;
  /**
   * Reason
   */
  reason?: string;
  /**
   * Secondary Result
   */
  secondary_result?: string | null;
  [key: string]: unknown;
};

/**
 * SemanticReviewResponse
 */
export type SemanticReviewResponse = {
  coverage_summary: SemanticReviewCoverageResponse;
  /**
   * Semantic Items
   */
  semantic_items?: Array<SemanticReviewItemResponse>;
  /**
   * Unexplained Fragments
   */
  unexplained_fragments?: Array<string>;
  [key: string]: unknown;
};

/**
 * SentimentCode
 */
export type SentimentCode = "NEGATIVE" | "POSITIVE" | "NEUTRAL";

/**
 * TaxonomyConfig
 */
export type TaxonomyConfig = {
  /**
   * Agent Family
   */
  agent_family: string;
  /**
   * Allowed Parts
   */
  allowed_parts?: Array<string>;
  /**
   * Categories
   */
  categories?: Array<CategoryDefinition>;
  /**
   * Instructions
   */
  instructions?: Array<string>;
  /**
   * Labels
   */
  labels: Array<LabelDefinition>;
  /**
   * Product Context
   */
  product_context: string;
  /**
   * Recognition Profile
   */
  recognition_profile?: "legacy_v3" | "keyword_free_v1" | "semantic_v1" | "fact_v2";
  /**
   * Structure Version
   */
  structure_version?: 1 | 2;
  validation_rules?: TaxonomyValidationRules;
  /**
   * Version
   */
  version: string;
};

/**
 * TaxonomyValidationRules
 */
export type TaxonomyValidationRules = {
  /**
   * Allowed Groups
   */
  allowed_groups?: Array<string>;
  /**
   * Boundary Required Labels
   */
  boundary_required_labels?: Array<string>;
  /**
   * Claim Evidence Requirements
   */
  claim_evidence_requirements?: Array<ClaimEvidenceRequirement>;
  /**
   * Conflict Scope
   */
  conflict_scope?: "comment" | "evidence";
  /**
   * Conflicting Label Sets
   */
  conflicting_label_sets?: Array<Array<string>>;
  /**
   * Dimension Contracts
   */
  dimension_contracts?: Array<DimensionContract>;
  /**
   * Evidence Requirements
   */
  evidence_requirements?: Array<EvidenceRequirement>;
  /**
   * Fallback Label Codes
   */
  fallback_label_codes?: Array<string>;
  /**
   * Implicit Evidence Rules
   */
  implicit_evidence_rules?: Array<ImplicitEvidenceRule>;
  /**
   * Neutral Reason Labels
   */
  neutral_reason_labels?: Array<string> | null;
  /**
   * Opposite Reason Labels
   */
  opposite_reason_labels?: {
    [key: string]: Array<string>;
  };
  /**
   * Required Review Labels
   */
  required_review_labels?: Array<string>;
};

/**
 * ValidationError
 */
export type ValidationError = {
  /**
   * Context
   */
  ctx?: {
    [key: string]: unknown;
  };
  /**
   * Input
   */
  input?: unknown;
  /**
   * Location
   */
  loc: Array<string | number>;
  /**
   * Message
   */
  msg: string;
  /**
   * Error Type
   */
  type: string;
};

export type ListResultsApiClassificationResultsGetData = {
  body?: never;
  path?: never;
  query?: {
    /**
     * Page
     */
    page?: number;
    /**
     * Page Size
     */
    page_size?: number;
    /**
     * Q
     */
    q?: string | null;
    /**
     * Store Site
     */
    store_site?: string | null;
    /**
     * Listing
     */
    listing?: string | null;
    /**
     * Quality Status
     */
    quality_status?: string | null;
  };
  url: "/api/classification-results";
};

export type ListResultsApiClassificationResultsGetErrors = {
  /**
   * Validation Error
   */
  422: HttpValidationError;
};

export type ListResultsApiClassificationResultsGetError =
  ListResultsApiClassificationResultsGetErrors[keyof ListResultsApiClassificationResultsGetErrors];

export type ListResultsApiClassificationResultsGetResponses = {
  /**
   * Successful Response
   */
  200: ClassificationResultListResponse;
};

export type ListResultsApiClassificationResultsGetResponse =
  ListResultsApiClassificationResultsGetResponses[keyof ListResultsApiClassificationResultsGetResponses];

export type GetResultApiClassificationResultsVersionIdGetData = {
  body?: never;
  path: {
    /**
     * Version Id
     */
    version_id: string;
  };
  query?: never;
  url: "/api/classification-results/{version_id}";
};

export type GetResultApiClassificationResultsVersionIdGetErrors = {
  /**
   * Validation Error
   */
  422: HttpValidationError;
};

export type GetResultApiClassificationResultsVersionIdGetError =
  GetResultApiClassificationResultsVersionIdGetErrors[keyof GetResultApiClassificationResultsVersionIdGetErrors];

export type GetResultApiClassificationResultsVersionIdGetResponses = {
  /**
   * Successful Response
   */
  200: ClassificationResultVersionResponse;
};

export type GetResultApiClassificationResultsVersionIdGetResponse =
  GetResultApiClassificationResultsVersionIdGetResponses[keyof GetResultApiClassificationResultsVersionIdGetResponses];

export type DownloadResultApiClassificationResultsVersionIdDownloadGetData = {
  body?: never;
  path: {
    /**
     * Version Id
     */
    version_id: string;
  };
  query?: never;
  url: "/api/classification-results/{version_id}/download";
};

export type DownloadResultApiClassificationResultsVersionIdDownloadGetErrors = {
  /**
   * Validation Error
   */
  422: HttpValidationError;
};

export type DownloadResultApiClassificationResultsVersionIdDownloadGetError =
  DownloadResultApiClassificationResultsVersionIdDownloadGetErrors[keyof DownloadResultApiClassificationResultsVersionIdDownloadGetErrors];

export type DownloadResultApiClassificationResultsVersionIdDownloadGetResponses = {
  /**
   * Successful Response
   */
  200: unknown;
};

export type GetDrilldownApiClassificationResultsVersionIdDrilldownGetData = {
  body?: never;
  path: {
    /**
     * Version Id
     */
    version_id: string;
  };
  query: {
    /**
     * Group By
     */
    group_by: string;
    /**
     * Page
     */
    page?: number;
    /**
     * Page Size
     */
    page_size?: number;
    /**
     * Problem
     */
    problem?: string | null;
    /**
     * Product Name
     */
    product_name?: string | null;
    /**
     * Product Sku
     */
    product_sku?: string | null;
    /**
     * Order Id
     */
    order_id?: string | null;
  };
  url: "/api/classification-results/{version_id}/drilldown";
};

export type GetDrilldownApiClassificationResultsVersionIdDrilldownGetErrors = {
  /**
   * Validation Error
   */
  422: HttpValidationError;
};

export type GetDrilldownApiClassificationResultsVersionIdDrilldownGetError =
  GetDrilldownApiClassificationResultsVersionIdDrilldownGetErrors[keyof GetDrilldownApiClassificationResultsVersionIdDrilldownGetErrors];

export type GetDrilldownApiClassificationResultsVersionIdDrilldownGetResponses = {
  /**
   * Successful Response
   */
  200: ClassificationResultDrilldownResponse;
};

export type GetDrilldownApiClassificationResultsVersionIdDrilldownGetResponse =
  GetDrilldownApiClassificationResultsVersionIdDrilldownGetResponses[keyof GetDrilldownApiClassificationResultsVersionIdDrilldownGetResponses];

export type ListRecordGroupsApiClassificationResultsVersionIdRecordGroupsGetData = {
  body?: never;
  path: {
    /**
     * Version Id
     */
    version_id: string;
  };
  query?: {
    /**
     * Page
     */
    page?: number;
    /**
     * Page Size
     */
    page_size?: number;
    /**
     * Order Id
     */
    order_id?: string | null;
    /**
     * Listing
     */
    listing?: string | null;
    /**
     * Product Name
     */
    product_name?: string | null;
    /**
     * Source Sku
     */
    source_sku?: string | null;
    /**
     * Matched Msku
     */
    matched_msku?: string | null;
    /**
     * Product Sku
     */
    product_sku?: string | null;
    /**
     * Asin
     */
    asin?: string | null;
    /**
     * Problem
     */
    problem?: string | null;
    /**
     * Quality Status
     */
    quality_status?: string | null;
  };
  url: "/api/classification-results/{version_id}/record-groups";
};

export type ListRecordGroupsApiClassificationResultsVersionIdRecordGroupsGetErrors = {
  /**
   * Validation Error
   */
  422: HttpValidationError;
};

export type ListRecordGroupsApiClassificationResultsVersionIdRecordGroupsGetError =
  ListRecordGroupsApiClassificationResultsVersionIdRecordGroupsGetErrors[keyof ListRecordGroupsApiClassificationResultsVersionIdRecordGroupsGetErrors];

export type ListRecordGroupsApiClassificationResultsVersionIdRecordGroupsGetResponses =
  {
    /**
     * Successful Response
     */
    200: ClassificationResultGroupsResponse;
  };

export type ListRecordGroupsApiClassificationResultsVersionIdRecordGroupsGetResponse =
  ListRecordGroupsApiClassificationResultsVersionIdRecordGroupsGetResponses[keyof ListRecordGroupsApiClassificationResultsVersionIdRecordGroupsGetResponses];

export type ListRecordsApiClassificationResultsVersionIdRecordsGetData = {
  body?: never;
  path: {
    /**
     * Version Id
     */
    version_id: string;
  };
  query?: {
    /**
     * Page
     */
    page?: number;
    /**
     * Page Size
     */
    page_size?: number;
    /**
     * Order Id
     */
    order_id?: string | null;
    /**
     * Listing
     */
    listing?: string | null;
    /**
     * Product Name
     */
    product_name?: string | null;
    /**
     * Source Sku
     */
    source_sku?: string | null;
    /**
     * Matched Msku
     */
    matched_msku?: string | null;
    /**
     * Product Sku
     */
    product_sku?: string | null;
    /**
     * Asin
     */
    asin?: string | null;
    /**
     * Problem
     */
    problem?: string | null;
    /**
     * Quality Status
     */
    quality_status?: string | null;
  };
  url: "/api/classification-results/{version_id}/records";
};

export type ListRecordsApiClassificationResultsVersionIdRecordsGetErrors = {
  /**
   * Validation Error
   */
  422: HttpValidationError;
};

export type ListRecordsApiClassificationResultsVersionIdRecordsGetError =
  ListRecordsApiClassificationResultsVersionIdRecordsGetErrors[keyof ListRecordsApiClassificationResultsVersionIdRecordsGetErrors];

export type ListRecordsApiClassificationResultsVersionIdRecordsGetResponses = {
  /**
   * Successful Response
   */
  200: ClassificationResultRecordsResponse;
};

export type ListRecordsApiClassificationResultsVersionIdRecordsGetResponse =
  ListRecordsApiClassificationResultsVersionIdRecordsGetResponses[keyof ListRecordsApiClassificationResultsVersionIdRecordsGetResponses];

export type GetSummaryApiClassificationResultsVersionIdSummaryGetData = {
  body?: never;
  path: {
    /**
     * Version Id
     */
    version_id: string;
  };
  query?: never;
  url: "/api/classification-results/{version_id}/summary";
};

export type GetSummaryApiClassificationResultsVersionIdSummaryGetErrors = {
  /**
   * Validation Error
   */
  422: HttpValidationError;
};

export type GetSummaryApiClassificationResultsVersionIdSummaryGetError =
  GetSummaryApiClassificationResultsVersionIdSummaryGetErrors[keyof GetSummaryApiClassificationResultsVersionIdSummaryGetErrors];

export type GetSummaryApiClassificationResultsVersionIdSummaryGetResponses = {
  /**
   * Successful Response
   */
  200: ClassificationResultSummaryResponse;
};

export type GetSummaryApiClassificationResultsVersionIdSummaryGetResponse =
  GetSummaryApiClassificationResultsVersionIdSummaryGetResponses[keyof GetSummaryApiClassificationResultsVersionIdSummaryGetResponses];

export type GetResultTaxonomyApiClassificationResultsVersionIdTaxonomyGetData = {
  body?: never;
  path: {
    /**
     * Version Id
     */
    version_id: string;
  };
  query?: never;
  url: "/api/classification-results/{version_id}/taxonomy";
};

export type GetResultTaxonomyApiClassificationResultsVersionIdTaxonomyGetErrors = {
  /**
   * Validation Error
   */
  422: HttpValidationError;
};

export type GetResultTaxonomyApiClassificationResultsVersionIdTaxonomyGetError =
  GetResultTaxonomyApiClassificationResultsVersionIdTaxonomyGetErrors[keyof GetResultTaxonomyApiClassificationResultsVersionIdTaxonomyGetErrors];

export type GetResultTaxonomyApiClassificationResultsVersionIdTaxonomyGetResponses = {
  /**
   * Successful Response
   */
  200: ClassificationResultTaxonomyResponse;
};

export type GetResultTaxonomyApiClassificationResultsVersionIdTaxonomyGetResponse =
  GetResultTaxonomyApiClassificationResultsVersionIdTaxonomyGetResponses[keyof GetResultTaxonomyApiClassificationResultsVersionIdTaxonomyGetResponses];

export type GetResultVersionsApiClassificationResultsVersionIdVersionsGetData = {
  body?: never;
  path: {
    /**
     * Version Id
     */
    version_id: string;
  };
  query?: never;
  url: "/api/classification-results/{version_id}/versions";
};

export type GetResultVersionsApiClassificationResultsVersionIdVersionsGetErrors = {
  /**
   * Validation Error
   */
  422: HttpValidationError;
};

export type GetResultVersionsApiClassificationResultsVersionIdVersionsGetError =
  GetResultVersionsApiClassificationResultsVersionIdVersionsGetErrors[keyof GetResultVersionsApiClassificationResultsVersionIdVersionsGetErrors];

export type GetResultVersionsApiClassificationResultsVersionIdVersionsGetResponses = {
  /**
   * Response Get Result Versions Api Classification Results  Version Id  Versions Get
   *
   * Successful Response
   */
  200: Array<ClassificationResultVersionResponse>;
};

export type GetResultVersionsApiClassificationResultsVersionIdVersionsGetResponse =
  GetResultVersionsApiClassificationResultsVersionIdVersionsGetResponses[keyof GetResultVersionsApiClassificationResultsVersionIdVersionsGetResponses];
