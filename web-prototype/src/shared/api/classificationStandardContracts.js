/** @typedef {"legacy_v3" | "semantic_v1" | "fact_v2" | "keyword_free_v1"} ReadableRecognitionProfile */
/** @typedef {"legacy_v3" | "semantic_v1" | "fact_v2"} WritableRecognitionProfile */
/** @typedef {"standard_version" | "keyword_ab" | "semantic_ab"} ValidationComparisonType */
/** @typedef {20 | 50 | 100} ValidationSampleSize */
/** @typedef {"NEGATIVE" | "POSITIVE" | "NEUTRAL"} ClassificationStandardSentiment */
/** @typedef {{code: string, name: string, parent_code: string | null}} ClassificationStandardCategory */
/** @typedef {{category_a: string, category_b: string, attributes: Record<string, string>}} ClassificationStandardVariant */
/** @typedef {{text: string, applies: true, sentiment: ClassificationStandardSentiment, explanation: string} | {text: string, applies: false, sentiment: null, explanation: string}} ClassificationStandardLabelExample */
/** @typedef {{text: string, applies: boolean, sentiment?: ClassificationStandardSentiment | null, explanation: string}} ClassificationStandardEditableLabelExample */
/**
 * @typedef {object} ClassificationStandardLabel
 * @property {string} code
 * @property {string} name
 * @property {string} group
 * @property {string | null} parent_code
 * @property {string} description
 * @property {string[]} keywords
 * @property {string[]} exclusions
 * @property {ClassificationStandardLabelExample[]} examples
 * @property {ClassificationStandardSentiment[]} allowed_sentiments
 * @property {string[]} allowed_claim_ids
 */
/** @typedef {Omit<ClassificationStandardLabel, "examples"> & {examples: ClassificationStandardEditableLabelExample[]}} ClassificationStandardEditableLabel */
/** @typedef {Pick<ClassificationStandardEditableLabel, "code" | "name" | "allowed_sentiments"> & Partial<Omit<ClassificationStandardEditableLabel, "code" | "name" | "allowed_sentiments">>} ClassificationStandardSnapshotLabel */
/** @typedef {{sheet?: string, row?: number, path?: string[], label_code?: string, source_label?: string, source_sentiment?: string}} ClassificationStandardImportSource */
/** @typedef {{label_code: string, semantic_requirement?: string, cues: string[], unknown_opinion: string, unknown_reason: string}} ClassificationStandardEvidenceRequirement */
/** @typedef {{label_code: string, semantic_requirement?: string, cues: string[]}} ClassificationStandardImplicitEvidenceRule */
/** @typedef {{label_code: string, claim_id: string, semantic_requirement?: string, cues: string[]}} ClassificationStandardClaimEvidenceRequirement */
/** @typedef {"source_ref" | "experiencer_ref" | "product_ref" | "variant_ref" | "event_ref" | "reference_basis" | "part" | "operation" | "condition"} ClassificationStandardDimensionScopeField */
/** @typedef {{parent_code: string, verdict_label_codes: string[], scope_fields: ClassificationStandardDimensionScopeField[]}} ClassificationStandardDimensionContract */
/**
 * @typedef {Record<string, unknown> & {
 *   allowed_groups?: string[],
 *   neutral_reason_labels?: string[] | null,
 *   required_review_labels?: string[],
 *   boundary_required_labels?: string[],
 *   fallback_label_codes?: string[],
 *   conflict_scope?: "comment" | "evidence",
 *   opposite_reason_labels?: Record<string, string[]>,
 *   conflicting_label_sets?: string[][],
 *   evidence_requirements?: ClassificationStandardEvidenceRequirement[],
 *   implicit_evidence_rules?: ClassificationStandardImplicitEvidenceRule[],
 *   claim_evidence_requirements?: ClassificationStandardClaimEvidenceRequirement[],
 *   dimension_contracts?: ClassificationStandardDimensionContract[],
 * }} ClassificationStandardValidationRules
 */
/**
 * @typedef {object} ClassificationStandardContentFields
 * @property {ReadableRecognitionProfile} recognition_profile
 * @property {string} name
 * @property {string} product_context
 * @property {string[]} instructions
 * @property {string[]} allowed_parts
 * @property {ClassificationStandardValidationRules} validation_rules
 * @property {ClassificationStandardVariant[]} variants
 */
/** @typedef {ClassificationStandardContentFields & {structure_version?: 1 | 2, categories?: ClassificationStandardCategory[], import_sources?: ClassificationStandardImportSource[], labels: ClassificationStandardEditableLabel[]}} ClassificationStandardEditableContent */
/** @typedef {ClassificationStandardContentFields & {structure_version: 1 | 2, categories: ClassificationStandardCategory[], import_sources: ClassificationStandardImportSource[], labels: ClassificationStandardEditableLabel[]}} ClassificationStandardDraftContent */
/** @typedef {Omit<ClassificationStandardEditableLabel, "allowed_claim_ids"> & {allowed_claim_ids: string[] | null}} ClassificationStandardLabelRequest */
/** @typedef {Omit<ClassificationStandardEditableContent, "recognition_profile" | "labels"> & {recognition_profile: WritableRecognitionProfile, labels: ClassificationStandardLabelRequest[]}} ClassificationStandardDraftContentRequest */
/**
 * @typedef {object} ClassificationStandardSnapshot
 * @property {string} name
 * @property {ClassificationStandardVariant[]} [variants]
 * @property {ClassificationStandardImportSource[]} [import_sources]
 * @property {{product_context: string, recognition_profile?: ReadableRecognitionProfile, instructions?: string[], allowed_parts?: string[], validation_rules?: ClassificationStandardValidationRules, structure_version?: 1 | 2, categories?: ClassificationStandardCategory[], labels?: ClassificationStandardSnapshotLabel[]}} taxonomy
 */
/** @typedef {{kind: string, message: string, field: string | null, label_code?: string, label_index?: number}} ClassificationStandardValidationIssue */
/** @typedef {{blocking: string[], warnings: string[], issues?: ClassificationStandardValidationIssue[]}} ClassificationStandardValidation */
/** @typedef {{id: string, name: string, status: "active" | "inactive", version_no: number, agent_family: string, product_context: string, category_count: number, label_count: number, label_group_count: number, delete_mode: "delete" | "deactivate", draft_id: string | null, updated_at: string}} ClassificationStandardSummary */
/** @typedef {ClassificationStandardSummary & {standard_version_id: string, snapshot: ClassificationStandardSnapshot}} ClassificationStandardDetail */
/** @typedef {{id: string, version_no: number, version_reason: string, published_at: string}} ClassificationStandardVersion */
/**
 * @typedef {object} ClassificationStandardDraft
 * @property {string} id
 * @property {string} standard_id
 * @property {number} base_version_no
 * @property {number} revision
 * @property {boolean} is_new
 * @property {string} change_reason
 * @property {ClassificationStandardDraftContent} content
 * @property {ClassificationStandardSnapshot} snapshot
 * @property {ClassificationStandardSnapshot} base_snapshot
 * @property {ClassificationStandardValidation} validation
 */

/** @typedef {{name: string, product_context: string, category_a: string, category_b: string}} ClassificationStandardCreatePayload */
/** @typedef {{expected_revision: number, content: ClassificationStandardDraftContentRequest, change_reason?: string}} ClassificationStandardUpdatePayload */
/** @typedef {{expected_revision: number, document: unknown, change_reason: string}} ClassificationStandardImportPayload */
/** @typedef {{expected_revision: number, reason: string}} ClassificationStandardActionPayload */
/** @typedef {{id: string, mode: "deleted" | "deactivated", status: "deleted" | "inactive"}} ClassificationStandardDeleteResult */
/** @typedef {{id: string, standard_id: string}} ClassificationStandardDiscardResult */
/** @typedef {{hierarchy_columns?: string[], source_label_column?: string, sentiment_column?: string}} ClassificationStandardExcelColumns */
/** @typedef {{severity: "blocking" | "warning", row: number | null, message: string}} ClassificationStandardExcelIssue */
/**
 * @typedef {object} ClassificationStandardExcelPreview
 * @property {string[]} sheets
 * @property {string[]} headers
 * @property {ClassificationStandardDraftContent | null} content
 * @property {ClassificationStandardExcelIssue[]} issues
 * @property {{rows?: number, categories?: number, labels?: number}} stats
 * @property {ClassificationStandardValidation} [validation]
 */

/**
 * @typedef {object} ClassificationStandardValidationSourceBase
 * @property {string} result_version_id
 * @property {number} version_no
 * @property {string} quality_status
 * @property {number} unit_count
 * @property {number} record_count
 * @property {string} published_at
 * @property {string | null} store_site
 * @property {string | null} listing
 */
/** @typedef {ClassificationStandardValidationSourceBase & {source_kind: "raw_dataset", available_sample_count: null, return_dataset_name: string, return_version_id: string, product_dataset_name: string, product_version_id: string}} ClassificationStandardRawValidationSource */
/** @typedef {ClassificationStandardValidationSourceBase & {available_sample_count: number}} ClassificationStandardPublishedValidationSource */
/** @typedef {ClassificationStandardRawValidationSource | ClassificationStandardPublishedValidationSource} ClassificationStandardValidationSource */
/**
 * @typedef {object} ClassificationStandardValidationRunSummary
 * @property {string} id
 * @property {"queued" | "running" | "completed" | "failed"} status
 * @property {number} draft_revision
 * @property {number} processed_count
 * @property {number} sample_size
 * @property {boolean} is_current
 */
/**
 * @typedef {object} ClassificationStandardValidationRunSource
 * @property {string | null} [listing]
 * @property {string} [filename]
 * @property {string} [analysis_context]
 * @property {"standard_version" | "keyword_ab" | "semantic_ab"} [comparison_type]
 * @property {{baseline: {profile: ReadableRecognitionProfile}, candidate: {profile: ReadableRecognitionProfile}}} [recognition_contract]
 * @property {number} [skipped_category_count]
 */
/** @typedef {{passed: boolean, blocking: string[], warnings: string[]}} ClassificationStandardQualityGate */
/**
 * @typedef {ClassificationStandardValidationRunSummary & {
 *   stage: string,
 *   error: string | null,
 *   summary: Record<string, unknown>,
 *   source: ClassificationStandardValidationRunSource,
 *   model_names: string[],
 *   error_count: number,
 *   quality_gate: ClassificationStandardQualityGate,
 *   publication_ready: boolean,
 *   items: Record<string, unknown>[],
 * }} ClassificationStandardValidationRunDetail
 */
/** @typedef {{expected_revision: number, source_result_version_id: string, sample_size: ValidationSampleSize, comparison_type?: ValidationComparisonType}} ClassificationStandardValidationRunPayload */
/** @typedef {{expected_revision: number, note: string}} ClassificationStandardValidationApprovalPayload */
/**
 * @typedef {object} ClassificationResultTaxonomy
 * @property {string} version
 * @property {string} agent_family
 * @property {string} product_context
 * @property {1 | 2} structure_version
 * @property {ClassificationStandardCategory[]} categories
 * @property {ReadableRecognitionProfile} recognition_profile
 * @property {string[]} allowed_parts
 * @property {string[]} instructions
 * @property {Record<string, unknown>} validation_rules
 * @property {(ClassificationStandardLabel & {label_path: string[]})[]} labels
 * @property {string} standard_id
 * @property {string} standard_version_id
 * @property {string} standard_name
 * @property {number} standard_version
 */

export {};
