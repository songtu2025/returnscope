/**
 * @typedef {import("./semanticResultFacts").NormalizedFact} NormalizedFact
 * @typedef {{ source: string, text: string }} FactEvidence
 * @typedef {{ fact: NormalizedFact, factIds: string[], evidences: FactEvidence[] }} DisplayFact
 */

/** @param {NormalizedFact} fact */
function factIdentity(fact) {
  return JSON.stringify([
    fact.labelCode,
    fact.labelPath,
    fact.opinion || fact.evidence,
    fact.subject,
    fact.direction,
    fact.assertion,
    fact.sourceRef,
    fact.experiencerRef,
    fact.productRef,
    fact.variantRef,
    fact.eventRef,
    fact.referenceBasis,
    fact.condition,
    fact.operation,
    fact.part,
    fact.decisionReason,
    fact.mappingReason,
    fact.relationType,
    fact.relatedFactIds,
    fact.causalAttribution,
  ]);
}

/** @param {NormalizedFact[]} facts */
export function groupFactsByLabel(facts) {
  /** @type {Map<string, { key: string, label: string, facts: DisplayFact[], identities: Map<string, DisplayFact> }>} */
  const groups = new Map();
  facts.forEach((fact, index) => {
    const path = fact.labelPath.join(" → ");
    const key = fact.labelCode
      ? `code:${fact.labelCode}`
      : path
        ? `path:${path}`
        : `unlabeled:${index}`;
    /** @type {{ key: string, label: string, facts: DisplayFact[], identities: Map<string, DisplayFact> }} */
    const group = groups.get(key) ?? {
      key,
      label: path || fact.labelCode || "未映射标签",
      facts: [],
      identities: new Map(),
    };
    const identity = factIdentity(fact);
    let current = group.identities.get(identity);
    if (!current) {
      current = { fact, factIds: [], evidences: [] };
      group.identities.set(identity, current);
      group.facts.push(current);
    }
    if (fact.factId && !current.factIds.includes(fact.factId)) {
      current.factIds.push(fact.factId);
    }
    if (
      !current.evidences.some(
        (evidence) =>
          evidence.source === fact.evidenceSource && evidence.text === fact.evidence,
      )
    ) {
      current.evidences.push({ source: fact.evidenceSource, text: fact.evidence });
    }
    groups.set(key, group);
  });
  return [...groups.values()].map(({ key, label, facts: groupedFacts }) => ({
    key,
    label,
    facts: groupedFacts,
  }));
}
