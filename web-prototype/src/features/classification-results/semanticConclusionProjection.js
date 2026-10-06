import {
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
} from "./semanticResultFacts";
import { normalizedStatus } from "./semanticStatusPresentation";

/**
 * @typedef {import("./semanticResultFacts").SemanticObject} SemanticObject
 * @typedef {import("./semanticResultFacts").SemanticRecord} SemanticRecord
 * @typedef {import("./semanticResultFacts").NormalizedFact} NormalizedFact
 * @typedef {import("./semanticStatusPresentation").SemanticStatus} SemanticStatus
 * @typedef {{ key: string, label: string, path: string[] }} SemanticTopic
 * @typedef {{
 *   id: string,
 *   topic: string,
 *   topicPath: string[],
 *   status: SemanticStatus,
 *   summary: string,
 *   facts: NormalizedFact[],
 *   contextFacts: NormalizedFact[],
 *   legacy: boolean
 * }} SemanticConclusion
 */

/**
 * @param {SemanticObject} classification
 * @param {SemanticObject} record
 * @returns {unknown[]}
 */
function conclusionSources(classification, record) {
  const source =
    record.comment_conclusions ??
    record.aspect_summaries ??
    record.semantic_summaries ??
    record.topic_summaries ??
    classification.comment_conclusions ??
    classification.aspect_summaries ??
    classification.semantic_summaries ??
    classification.topic_summaries;
  return array(source);
}

/**
 * @param {SemanticObject} classification
 * @param {SemanticObject} record
 * @returns {unknown[]}
 */
function dimensionDecisionSources(classification, record) {
  return array(record.dimension_decisions ?? classification.dimension_decisions);
}

/** @param {NormalizedFact} fact @returns {SemanticTopic} */
function topicForFact(fact) {
  const explicit = coalescedText(
    fact.aspect_label ??
      fact.aspect_name ??
      fact.topic_label ??
      fact.aspect ??
      fact.topic,
  );
  if (explicit) {
    return {
      key: coalescedText(fact.aspect_code, fact.topic_code, explicit),
      label: explicit,
      path: stringArray(fact.aspect_path),
    };
  }
  const topicPath = fact.labelPath.length > 1 ? fact.labelPath.slice(0, -1) : [];
  return {
    key: topicPath.join("/") || fact.labelCode || "未归类主题",
    label: topicPath.at(-1) || fact.labelCode || "未归类主题",
    path: topicPath,
  };
}

/** @param {SemanticObject} conclusion @param {NormalizedFact[]} allFacts */
function conclusionFacts(conclusion, allFacts) {
  const factIds = stringArray(conclusion.supporting_fact_ids ?? conclusion.fact_ids);
  const labelCodes = stringArray(conclusion.label_codes);
  const embeddedFacts = array(conclusion.facts ?? conclusion.atomic_facts).map(
    (fact, factIndex) => normalizedFact(object(fact), factIndex),
  );
  const matchedById = factIds.length
    ? allFacts.filter((fact) => factIds.includes(fact.factId))
    : [];
  const matchedByLabel = allFacts.filter((fact) => labelCodes.includes(fact.labelCode));
  const topicIdentities = new Set(
    [
      conclusion.aspect_code,
      conclusion.topic_code,
      conclusion.aspect_label,
      conclusion.aspect_name,
      conclusion.topic_label,
      conclusion.topic_name,
      ...stringArray(conclusion.aspect_path),
      ...stringArray(conclusion.topic_path),
    ]
      .filter(Boolean)
      .map(String),
  );
  const matchedByTopic = allFacts.filter((fact) => {
    const topic = topicForFact(fact);
    return [topic.key, topic.label, ...topic.path].some((value) =>
      topicIdentities.has(String(value)),
    );
  });
  const matchedFacts = matchedById.length
    ? matchedById
    : matchedByLabel.length
      ? matchedByLabel
      : matchedByTopic;
  return embeddedFacts.length ? embeddedFacts : matchedFacts;
}

/**
 * @param {unknown} conclusionValue
 * @param {number} index
 * @param {NormalizedFact[]} allFacts
 * @returns {SemanticConclusion}
 */
function normalizeConclusion(conclusionValue, index, allFacts) {
  const conclusion = object(conclusionValue);
  const facts = conclusionFacts(conclusion, allFacts);
  const topicPath = stringArray(conclusion.aspect_path ?? conclusion.topic_path);
  return {
    id: coalescedText(
      conclusion.id,
      conclusion.aspect_code,
      conclusion.topic_code,
      `topic-${index}`,
    ),
    topic: coalescedText(
      conclusion.aspect_label,
      conclusion.aspect_name,
      conclusion.topic_label,
      conclusion.topic_name,
      conclusion.label,
      topicPath.at(-1),
      "未归类主题",
    ),
    topicPath,
    status: normalizedStatus(
      conclusion.summary_status ?? conclusion.status ?? conclusion.sentiment_status,
    ),
    summary: coalescedText(
      conclusion.summary,
      conclusion.statement,
      conclusion.conclusion,
    ),
    facts,
    contextFacts: [],
    legacy: facts.some((fact) =>
      [
        fact.sourceRef,
        fact.experiencerRef,
        fact.productRef,
        fact.variantRef,
        fact.eventRef,
        fact.referenceBasis,
      ].some((value) => !meaningful(value)),
    ),
  };
}

/** @param {SemanticObject} decision @param {number} index @param {NormalizedFact[]} allFacts */
function decisionFacts(decision, index, allFacts) {
  const supportingIds = stringArray(decision.supporting_fact_ids);
  const contextIds = stringArray(decision.context_fact_ids);
  const supportingFacts = supportingIds.map((factId) => {
    const matched = allFacts.find((fact) => fact.factId === factId) ?? {
      fact_id: factId,
    };
    return normalizedFact(
      {
        ...matched,
        label_code: stringValue(decision.verdict_label_code),
        decision_reason: stringValue(decision.reason),
      },
      index,
      decision.scope,
    );
  });
  const contextFacts = contextIds.map((factId) => {
    const matched = allFacts.find((fact) => fact.factId === factId) ?? {
      fact_id: factId,
    };
    return normalizedFact(matched, index, decision.scope);
  });
  return { supportingFacts, contextFacts };
}

/**
 * @param {unknown[]} decisions
 * @param {NormalizedFact[]} allFacts
 * @returns {Omit<SemanticConclusion, "status">[]}
 */
function decisionConclusions(decisions, allFacts) {
  /** @type {Map<string, Omit<SemanticConclusion, "status"> & {reasons: string[]}>} */
  const groups = new Map();
  decisions.forEach((decisionValue, index) => {
    const decision = object(decisionValue);
    const { supportingFacts, contextFacts } = decisionFacts(decision, index, allFacts);
    const verdictLabelCode = stringValue(decision.verdict_label_code);
    const verdictFact =
      supportingFacts.find((fact) => fact.labelCode === verdictLabelCode) ??
      allFacts.find((fact) => fact.labelCode === verdictLabelCode);
    const topic = topicForFact(
      verdictFact ?? supportingFacts[0] ?? normalizedFact({}, index),
    );
    const key = firstText(decision.parent_code, topic.key, `decision-${index}`);
    const current = groups.get(key) ?? {
      id: key,
      topic: topic.label || key,
      topicPath: topic.path,
      summary: "",
      facts: [],
      contextFacts: [],
      reasons: [],
      legacy: false,
    };
    current.facts.push(...supportingFacts);
    current.contextFacts.push(...contextFacts);
    const reason = stringValue(decision.reason);
    if (reason) current.reasons.push(reason);
    groups.set(key, current);
  });
  return [...groups.values()].map(({ reasons, ...group }) => ({
    ...group,
    summary: reasons.join("；"),
  }));
}

/**
 * @param {SemanticConclusion[]} provided
 * @param {Omit<SemanticConclusion, "status">[]} decisions
 * @returns {SemanticConclusion[]}
 */
function suppliedDecisionConclusions(provided, decisions) {
  /** @type {Set<number>} */
  const matched = new Set();
  const resolved = decisions.flatMap((decision) => {
    const index = provided.findIndex(
      (item, itemIndex) =>
        !matched.has(itemIndex) &&
        (item.id === decision.id ||
          item.facts.some((fact) =>
            decision.facts.some(
              (current) => current.factId && current.factId === fact.factId,
            ),
          )),
    );
    if (index < 0) return [];
    matched.add(index);
    return [{ ...decision, status: provided[index].status }];
  });
  return [...resolved, ...provided.filter((_, index) => !matched.has(index))];
}

/** @param {SemanticRecord} record @returns {SemanticConclusion[]} */
export function semanticConclusions(record) {
  const source = object(record);
  const classification = classificationOf(record);
  const facts = sourceFacts(classification, source);
  const provided = conclusionSources(classification, source).map((conclusion, index) =>
    normalizeConclusion(conclusion, index, facts),
  );
  const decisions = dimensionDecisionSources(classification, source);
  if (!decisions.length) return provided;
  return suppliedDecisionConclusions(provided, decisionConclusions(decisions, facts));
}
