import {
  object,
  array,
  stringArray,
  stringValue,
  classificationOf,
  firstText,
  coalescedText,
  normalizedFact,
  isSemanticObject,
} from "./semanticFactNormalization.js";

/**
 * @typedef {import("./semanticFactNormalization.js").GeneratedRecord} GeneratedRecord
 * @typedef {import("./semanticFactNormalization.js").GeneratedFact} GeneratedFact
 * @typedef {import("./semanticFactNormalization.js").SemanticObject} SemanticObject
 * @typedef {import("./semanticFactNormalization.js").SemanticRecord} SemanticRecord
 * @typedef {import("./semanticFactNormalization.js").RawFact} RawFact
 * @typedef {import("./semanticFactNormalization.js").NormalizedFactFields} NormalizedFactFields
 * @typedef {import("./semanticFactNormalization.js").NormalizedFact} NormalizedFact
 */

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
  firstText,
  coalescedText,
  normalizedFact,
  sourceFacts,
  meaningful,
};
