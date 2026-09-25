/**
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultRecordResponse} GeneratedRecord
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationSemanticFactResponse} GeneratedFact
 * @typedef {Record<string, unknown>} SemanticObject
 * @typedef {GeneratedRecord | SemanticObject} SemanticRecord
 * @typedef {GeneratedFact | SemanticObject} RawFact
 * @typedef {{
 *   factId: string,
 *   labelCode: string,
 *   labelPath: string[],
 *   opinion: string,
 *   subject: string,
 *   direction: string,
 *   assertion: string,
 *   sourceRef: string,
 *   experiencerRef: string,
 *   productRef: string,
 *   variantRef: string,
 *   eventRef: string,
 *   referenceBasis: string,
 *   condition: string,
 *   operation: string,
 *   part: string,
 *   evidence: string,
 *   evidenceSource: string,
 *   decisionReason: string,
 *   mappingReason: string,
 *   relationType: string,
 *   relatedFactIds: string[],
 *   causalAttribution: string,
 *   position: number
 * }} NormalizedFactFields
 * @typedef {SemanticObject & NormalizedFactFields} NormalizedFact
 */

/** @param {unknown} value @returns {value is SemanticObject} */
function isSemanticObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** @param {unknown} value @returns {SemanticObject} */
function object(value) {
  return isSemanticObject(value) ? value : {};
}

/** @param {unknown} value @returns {unknown[]} */
function array(value) {
  return Array.isArray(value) ? value : [];
}

/** @param {unknown} value @returns {string[]} */
function stringArray(value) {
  return array(value)
    .filter((item) => item !== undefined && item !== null && item !== "")
    .map(String);
}

/** @param {unknown} value @returns {string} */
function stringValue(value) {
  return value === undefined || value === null ? "" : String(value);
}

/** @param {SemanticRecord} record @returns {SemanticObject} */
function classificationOf(record) {
  const source = object(record);
  return isSemanticObject(source.classification) ? source.classification : source;
}

/** @param {RawFact | NormalizedFact} fact @returns {string} */
function directionOf(fact) {
  const source = object(fact);
  return String(
    source.evaluation_direction ?? source.sentiment ?? source.direction ?? "NEUTRAL",
  ).toUpperCase();
}

/** @param {RawFact | NormalizedFact} fact @returns {string} */
function assertionOf(fact) {
  const source = object(fact);
  return String(
    source.statement_type ??
      source.assertion_status ??
      source.assertion ??
      source.fact_type ??
      "AFFIRMED",
  ).toUpperCase();
}

/** @param {RawFact | NormalizedFact} fact @returns {boolean} */
function isConfirmed(fact) {
  return ![
    "PREDICTION",
    "HYPOTHESIS",
    "NOT_TESTED",
    "INTENT",
    "ADVICE",
    "RECOMMENDATION",
  ].includes(assertionOf(fact));
}

/** @param {RawFact | NormalizedFact} fact @returns {string[]} */
function pathOf(fact) {
  const source = object(fact);
  const path =
    source.full_label_path ??
    source.label_path ??
    source.taxonomy_path ??
    source.labelPath ??
    [];
  if (Array.isArray(path)) return path.filter(Boolean).map(String);
  if (typeof path === "string") {
    return path
      .split(/\s*(?:→|>|\/|-)\s*/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

/** @param {unknown} value @returns {string} */
function conditionText(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.filter(Boolean).join("、");
  if (typeof value === "object") {
    return Object.values(value).map(conditionText).filter(Boolean).join("；");
  }
  return String(value);
}

/** @param {...unknown} values @returns {unknown} */
function firstValue(...values) {
  return values.find(
    (value) => value !== undefined && value !== null && String(value).trim(),
  );
}

/** @param {...unknown} values @returns {string} */
function firstText(...values) {
  return stringValue(firstValue(...values));
}

/** @param {...unknown} values @returns {string} */
function coalescedText(...values) {
  return stringValue(values.find((value) => value !== undefined && value !== null));
}

/**
 * @param {RawFact | SemanticObject} fact
 * @param {number} index
 * @param {unknown} [scope]
 * @returns {NormalizedFact}
 */
function normalizedFact(fact, index, scope = {}) {
  const source = object(fact);
  const factScope = object(source.scope);
  const scopeSource = object(scope);
  const evidenceSpans = array(source.evidence_spans).map(object);
  return {
    ...source,
    factId: coalescedText(
      source.fact_id,
      array(source.fact_ids)[0],
      source.source_fact_id,
      source.id,
    ),
    labelCode: coalescedText(
      source.label_code,
      source.verdict_label_code,
      source.labelCode,
    ),
    labelPath: pathOf(source),
    opinion: firstText(
      source.opinion,
      source.fact_text_zh,
      source.fact_summary,
      source.summary,
    ),
    subject: firstText(source.subject, source.object_type, factScope.subject),
    direction: directionOf(fact),
    assertion: assertionOf(fact),
    sourceRef: firstText(
      scopeSource.source_ref,
      source.source_ref,
      factScope.source_ref,
      source.sourceRef,
    ),
    experiencerRef: firstText(
      scopeSource.experiencer_ref,
      scopeSource.actor_ref,
      source.experiencer_ref,
      source.actor_ref,
      source.actor,
      factScope.experiencer_ref,
      factScope.actor,
      source.experiencerRef,
    ),
    productRef: firstText(
      scopeSource.product_ref,
      source.product_ref,
      factScope.product_ref,
      source.productRef,
    ),
    variantRef: firstText(
      scopeSource.variant_ref,
      source.variant_ref,
      factScope.variant_ref,
      source.variantRef,
    ),
    eventRef: firstText(
      scopeSource.event_ref,
      source.event_ref,
      source.event_id,
      factScope.event_ref,
      source.eventRef,
    ),
    referenceBasis: firstText(
      scopeSource.reference_basis,
      source.reference_basis,
      factScope.reference_basis,
      source.referenceBasis,
    ),
    condition: conditionText(
      firstValue(
        scopeSource.condition,
        source.condition,
        source.conditions,
        factScope.condition,
      ),
    ),
    operation: firstText(scopeSource.operation, source.operation, factScope.operation),
    part: firstText(scopeSource.part, source.part, factScope.part),
    evidence: coalescedText(
      source.evidence,
      source.evidence_text,
      source.text,
      evidenceSpans
        .map((span) => span.text)
        .filter(Boolean)
        .join(" … "),
    ),
    evidenceSource: coalescedText(
      source.evidence_source,
      source.source,
      source.evidenceSource,
      evidenceSpans
        .map((span) => span.source)
        .filter(Boolean)
        .join("+"),
    ),
    decisionReason: firstText(
      source.decision_reason,
      source.verdict_reason,
      source.decisionReason,
    ),
    mappingReason: firstText(
      source.mapping_reason,
      source.mappingReason,
      source.reason,
    ),
    relationType: String(
      firstValue(
        source.relation_type,
        source.fact_relation_type,
        source.relationType,
      ) || "",
    ).toUpperCase(),
    relatedFactIds: stringArray(
      source.related_fact_ids ?? source.cause_fact_ids ?? source.relatedFactIds,
    ),
    causalAttribution: firstText(
      source.causal_attribution,
      source.cause_attribution,
      source.cause_actor,
      source.cause_ref,
      source.cause,
      source.causalAttribution,
    ),
    position: index,
  };
}

/**
 * @param {SemanticObject} classification
 * @param {SemanticObject} record
 * @returns {unknown[][]}
 */
function factSources(classification, record) {
  const candidates = [
    record.atomic_facts,
    record.semantic_units,
    classification.atomic_facts,
    classification.semantic_units,
    record.semantic_facts,
    classification.semantic_facts,
    record.extracted_facts,
    classification.extracted_facts,
    record.facts,
    classification.facts,
    record.evidence,
  ];
  /** @type {unknown[][]} */
  const sources = [];
  candidates.forEach((candidate) => {
    if (Array.isArray(candidate)) sources.push(candidate);
  });
  return sources;
}

/**
 * @param {SemanticObject} classification
 * @param {SemanticObject} record
 * @returns {SemanticObject[]}
 */
function mappingSources(classification, record) {
  return array(record.fact_mappings ?? classification.fact_mappings).filter(
    isSemanticObject,
  );
}

/** @param {unknown} value @returns {boolean} */
function meaningful(value) {
  return value !== undefined && value !== null && value !== "";
}

/**
 * @param {NormalizedFact} primary
 * @param {SemanticObject} secondary
 * @returns {NormalizedFact}
 */
function mergeFacts(primary, secondary) {
  const merged = { ...primary };
  Object.entries(secondary).forEach(([key, value]) => {
    if (
      !meaningful(merged[key]) ||
      (Array.isArray(merged[key]) && !merged[key].length)
    ) {
      merged[key] = value;
    }
  });
  return merged;
}

/**
 * @param {SemanticObject} classification
 * @param {SemanticObject} record
 * @returns {NormalizedFact[]}
 */
function sourceFacts(classification, record) {
  /** @type {Map<string, NormalizedFact>} */
  const identified = new Map();
  /** @type {NormalizedFact[]} */
  const anonymous = [];
  const sources = factSources(classification, record);
  const primarySourceIndex = sources.findIndex((facts) => facts.length > 0);
  sources.forEach((facts, sourceIndex) => {
    facts.forEach((fact, index) => {
      const normalized = normalizedFact(object(fact), index);
      if (!normalized.factId) {
        if (sourceIndex === primarySourceIndex) anonymous.push(normalized);
        return;
      }
      const existing = identified.get(normalized.factId);
      identified.set(
        normalized.factId,
        existing ? mergeFacts(existing, normalized) : normalized,
      );
    });
  });
  const mappings = new Map(
    mappingSources(classification, record).map((mapping) => [
      stringValue(mapping.fact_id),
      mapping,
    ]),
  );
  return [...identified.values(), ...anonymous].map((fact) => {
    const mapping = mappings.get(fact.factId);
    if (!mapping) return fact;
    return mergeFacts(fact, {
      mappingReason: stringValue(mapping.reason),
      relationType: stringValue(mapping.relation_type),
      relatedFactIds: stringArray(mapping.related_fact_ids),
    });
  });
}

export {
  object,
  array,
  stringArray,
  stringValue,
  classificationOf,
  isConfirmed,
  firstText,
  coalescedText,
  normalizedFact,
  sourceFacts,
  meaningful,
};
