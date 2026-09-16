/**
 * @typedef {Object} TaskPlanVariant
 * @property {string} category_a
 * @property {string} category_b
 * @property {number} record_count
 *
 * @typedef {Object} TaskPlanScope
 * @property {string} [store]
 * @property {string} [listing]
 *
 * @typedef {Object} TaskPlanSegment
 * @property {string} segment_key
 * @property {string} agent_family
 * @property {string} [standard_name]
 * @property {number} [standard_version]
 * @property {string} [logic_version]
 * @property {string} taxonomy_version
 * @property {"ready" | "blocked" | string} status
 * @property {TaskPlanScope} [scope]
 * @property {number} record_count
 * @property {number} unique_comments
 * @property {TaskPlanVariant[]} variants
 *
 * @typedef {Object} TaskExecutionPlan
 * @property {string} plan_hash
 * @property {string} [primary_store]
 * @property {TaskPlanScope[]} [detected_scopes]
 * @property {number} record_count
 * @property {number} valid_comment_count
 * @property {number} unique_comment_count
 * @property {number} executable_count
 * @property {number} [excluded_count]
 * @property {number} blocked_count
 * @property {number} [unmatched_product_count]
 * @property {number} [missing_category_count]
 * @property {number} [missing_category_product_count]
 * @property {number} [missing_category_comment_count]
 * @property {number} [unknown_category_count]
 * @property {number} [unresolved_scope_count]
 * @property {number} [unresolved_product_count]
 * @property {boolean} [category_completion_required]
 * @property {TaskPlanVariant[]} unknown_categories
 * @property {TaskPlanSegment[]} segments
 * @property {{scope?: TaskPlanScope}} [inputs]
 * @property {TaskUnresolvedProduct[]} [unresolved_products]
 * @property {TaskCategoryOption[]} [category_options]
 * @property {number} [unresolved_product_comment_count]
 *
 * @typedef {Object} TaskUnresolvedProduct
 * @property {string} product_key
 * @property {string} [store]
 * @property {string} msku
 * @property {string} [suggested_listing]
 * @property {number} [record_count]
 * @property {number} [comment_count]
 * @property {boolean} [editable]
 * @property {string} [match_status]
 * @property {Record<string, unknown>} [match_candidate]
 * @property {string} [current_category_a]
 * @property {string} [current_category_b]
 * @property {string} [product_name]
 *
 * @typedef {Object} TaskCategoryOption
 * @property {string} category_a
 * @property {string} category_b
 * @property {string} [agent_family]
 * @property {string} [standard_id]
 * @property {string} [standard_version_id]
 * @property {string} [standard_name]
 * @property {number} [standard_version]
 *
 * @typedef {Object} TaskDataQuality
 * @property {Record<string, number>} [counts]
 *
 * @typedef {Object} TaskPlanCounts
 * @property {number} unique
 * @property {number} executable
 * @property {number} notAnalyzed
 * @property {boolean} reconciled
 * @property {string} coverageLabel
 */

export {};
