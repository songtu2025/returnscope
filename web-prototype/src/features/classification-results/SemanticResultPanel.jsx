import { CaretDown, Info, WarningCircle } from "@phosphor-icons/react";
import {
  factPresentation,
  semanticConclusions,
  semanticRelations,
  semanticRecordStatus,
  semanticStatusLabel,
  semanticUnknownGroups,
} from "./semanticResultPresentation";

/**
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultRecordResponse} GeneratedRecord
 * @typedef {GeneratedRecord | Record<string, unknown>} SemanticRecord
 * @typedef {ReturnType<typeof factPresentation>} PresentedFact
 * @typedef {ReturnType<typeof semanticConclusions>[number]["facts"][number]} NormalizedFact
 * @typedef {ReturnType<typeof semanticUnknownGroups>["review"][number]} NormalizedUnknownSemantic
 * @typedef {ReturnType<typeof semanticUnknownGroups>} UnknownSemanticGroups
 * @typedef {{ source: string, text: string }} FactEvidence
 * @typedef {{ fact: NormalizedFact, factIds: string[], evidences: FactEvidence[] }} DisplayFact
 */

/** @type {Record<string, string>} */
const RELATION_LABELS = {
  CONFLICT: "疑似冲突",
  MIXED: "条件差异",
  MULTI_ACTOR: "多位使用者",
  MULTI_PRODUCT: "多个商品",
};

/**
 * @param {string | number | null | undefined} value
 * @param {boolean} [legacy]
 * @returns {string | number}
 */
function display(value, legacy = false) {
  return value || (legacy ? "旧结果未提供" : "未提供");
}

/**
 * @param {string | null | undefined} value
 * @param {boolean} [legacy]
 * @returns {string}
 */
function evidenceDisplay(value, legacy = false) {
  return value || (legacy ? "旧结果未提供文本证据" : "无文本证据");
}

/** @param {Array<string | null | undefined>} values @param {boolean} legacy */
function joinedDisplay(values, legacy) {
  const text = values.filter((value) => value && value !== "UNSPECIFIED").join(" / ");
  return display(text, legacy);
}

/** @param {PresentedFact} item */
function isOtherLabel(item) {
  return (
    item.labelPath.some((value) => String(value).trim() === "其他") ||
    /(?:^|_)OTHER(?:_|$)/i.test(item.labelCode || "")
  );
}

/** @param {NormalizedFact[]} facts */
function groupFactsByLabel(facts) {
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
    const identity = JSON.stringify([
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

/** @param {{item: PresentedFact, legacy: boolean}} props */
function ScopeDetails({ item, legacy }) {
  return (
    <dl className="semantic-review-fields">
      <div>
        <dt>对象 / 部位</dt>
        <dd>{joinedDisplay([item.subjectLabel, item.partLabel], legacy)}</dd>
      </div>
      <div>
        <dt>使用者 / 商品</dt>
        <dd>
          {joinedDisplay(
            [item.experiencerLabel, item.productLabel, item.variantRef],
            legacy,
          )}
        </dd>
      </div>
      <div>
        <dt>任务 / 场景</dt>
        <dd>
          {joinedDisplay([item.operation, item.condition, item.eventRef], legacy)}
        </dd>
      </div>
      <div>
        <dt>观点来源 / 参照</dt>
        <dd>{joinedDisplay([item.sourceLabel, item.referenceBasisLabel], legacy)}</dd>
      </div>
      <div>
        <dt>因果归属</dt>
        <dd>{display(item.causalAttribution, legacy)}</dd>
      </div>
      <div>
        <dt>判定理由</dt>
        <dd>{display(item.decisionReason, legacy)}</dd>
      </div>
    </dl>
  );
}

/** @param {{fact: NormalizedFact, legacy: boolean, context?: boolean, position?: number, factIds?: string[], evidences?: FactEvidence[]}} props */
function FactDetail({ fact, legacy, context = false, position, factIds, evidences }) {
  const item = factPresentation(fact);
  const path = item.labelPath.join(" → ");
  return (
    <article className={`semantic-fact-card${context ? " is-context" : ""}`}>
      <header>
        <div>
          {context && <small>裁决上下文</small>}
          {position === undefined ? (
            <b>{path || item.labelCode || (context ? "未映射上下文" : "未映射标签")}</b>
          ) : (
            <small>事实 {position + 1}</small>
          )}
        </div>
        <span>{display(factIds?.join("、") || item.factId, legacy)}</span>
      </header>
      {!context && (
        <dl className="semantic-fact-verdict">
          <div>
            <dt>评价方向</dt>
            <dd>{display(item.directionLabel, legacy)}</dd>
          </div>
          <div>
            <dt>确定性</dt>
            <dd>{display(item.assertionLabel, legacy)}</dd>
          </div>
        </dl>
      )}
      <div className="semantic-fact-summary">
        <span>中文事实</span>
        <b>{item.opinion || (legacy ? "旧结果未提供中文事实" : "未提供中文事实")}</b>
      </div>
      {isOtherLabel(item) && (
        <div className="semantic-other-explanation">
          <b>“其他”具体内容</b>
          <span>{display(item.opinion, legacy)}</span>
          <small>映射说明：{display(item.decisionReason, legacy)}</small>
        </div>
      )}
      <ScopeDetails item={item} legacy={legacy} />
      {(evidences ?? [{ source: fact.evidenceSource, text: fact.evidence }]).map(
        (evidence, index) => {
          const presented = factPresentation({
            ...fact,
            evidence_source: evidence.source,
          });
          return (
            <div key={`${evidence.source}-${evidence.text}-${index}`}>
              <div className="semantic-evidence-source">
                证据来源：{display(presented.evidenceSourceLabel, legacy)}
              </div>
              <blockquote>“{evidenceDisplay(evidence.text, legacy)}”</blockquote>
            </div>
          );
        },
      )}
      {legacy && item.labelPath.length > 0 && item.labelPath.length < 3 && (
        <small className="semantic-legacy-note">旧结果未保存完整标签路径。</small>
      )}
    </article>
  );
}

/** @param {{item: NormalizedUnknownSemantic}} props */
function UnknownDetail({ item }) {
  const presented = factPresentation(item);
  return (
    <article className="semantic-unknown-card">
      <header>
        <div>
          <small>事实摘要</small>
          <b>{item.opinion || "未提供语义描述"}</b>
        </div>
        <span>{item.dispositionLabel}</span>
      </header>
      <p>
        <b>未映射原因：</b>
        {item.reason || "未提供"}
      </p>
      <ScopeDetails item={presented} legacy={item.legacyDisposition} />
      <div className="semantic-evidence-source">
        证据来源：{display(presented.evidenceSourceLabel, item.legacyDisposition)}
      </div>
      <blockquote>
        “{evidenceDisplay(item.evidence, item.legacyDisposition)}”
      </blockquote>
    </article>
  );
}

/** @param {{groups: UnknownSemanticGroups}} props */
function UnknownSemantics({ groups }) {
  return (
    <>
      {groups.review.length > 0 && (
        <section className="semantic-unknown-group is-review" aria-label="需要复核">
          <header>
            <WarningCircle size={17} aria-hidden="true" />
            <div>
              <b>需要复核 · {groups.review.length} 项</b>
              <span>标签体系缺口或映射不确定会影响最终打标。</span>
            </div>
          </header>
          <div>
            {groups.review.map((item) => (
              <UnknownDetail key={item.id} item={item} />
            ))}
          </div>
        </section>
      )}
      {groups.informational.length > 0 && (
        <details className="semantic-unknown-group is-informational">
          <summary>
            <Info size={17} aria-hidden="true" />
            <div>
              <b>未参与打标信息 · {groups.informational.length} 项</b>
              <span>正常弃权、范围外内容和辅助证据不会作为错误处理。</span>
            </div>
            <CaretDown size={15} aria-hidden="true" />
          </summary>
          <div>
            {groups.informational.map((item) => (
              <UnknownDetail key={item.id} item={item} />
            ))}
          </div>
        </details>
      )}
    </>
  );
}

/** @param {{status: string}} props */
export function SemanticStatusBadge({ status }) {
  const normalized = status || "NO_CONFIRMED";
  return (
    <span className={`semantic-status-badge is-${normalized.toLowerCase()}`}>
      {semanticStatusLabel(normalized)}
    </span>
  );
}

/** @param {{record: SemanticRecord, title?: string}} props */
export function SemanticResultPanel({ record, title = "评论级结论" }) {
  const conclusions = semanticConclusions(record);
  const groupedConclusions = conclusions.map((conclusion) => ({
    ...conclusion,
    topicLabel: conclusion.topicPath.join(" → ") || conclusion.topic,
    labelGroups: groupFactsByLabel(conclusion.facts),
  }));
  const overallStatus = semanticRecordStatus(record);
  const relations = semanticRelations(record);
  const unknownGroups = semanticUnknownGroups(record);
  const legacy = conclusions.some((item) => item.legacy);

  return (
    <div className="semantic-result-panel">
      <header className="semantic-result-header">
        <div>
          <b>{title}</b>
          <span>按标签维度归并；作用域不同的评价保留各自边界</span>
        </div>
        <SemanticStatusBadge status={overallStatus} />
      </header>
      {legacy && conclusions.length > 0 && (
        <p className="semantic-compatibility-note">
          当前为旧结果兼容视图；缺少作用域字段时会明确显示“旧结果未提供”。
        </p>
      )}
      {conclusions.length === 0 ? (
        <div className="semantic-empty-state">
          <b>无确定评价</b>
          <span>这条评论没有可用于业务统计的确定观点。</span>
        </div>
      ) : (
        <div className="semantic-conclusion-list">
          {groupedConclusions.map((conclusion) => (
            <details key={conclusion.id} className="semantic-conclusion-item" open>
              <summary>
                <div>
                  <span>{conclusion.topicLabel}</span>
                  {conclusion.summary &&
                    conclusion.summary !== conclusion.topicLabel && (
                      <b>{conclusion.summary}</b>
                    )}
                </div>
                <SemanticStatusBadge status={conclusion.status} />
                <small>
                  {conclusion.labelGroups.length} 个标签 ·{" "}
                  {conclusion.labelGroups.reduce(
                    (count, group) => count + group.facts.length,
                    0,
                  )}{" "}
                  条事实
                </small>
                <CaretDown size={15} aria-hidden="true" />
              </summary>
              {conclusion.status === "MIXED" && (
                <p className="semantic-boundary-note">
                  条件差异：正负评价对应不同使用者、商品、规格、事件、条件、操作或部位。
                </p>
              )}
              {conclusion.status === "CONFLICT" && (
                <p className="semantic-conflict-note" role="status">
                  <WarningCircle size={16} aria-hidden="true" />
                  同一作用域出现相反结论，需要复核事实或裁决。
                </p>
              )}
              <div className="semantic-fact-list">
                {conclusion.labelGroups.length ? (
                  conclusion.labelGroups.map((group) => (
                    <section
                      key={group.key}
                      className="semantic-label-group"
                      aria-label={group.label}
                    >
                      <header>
                        <b>{group.label}</b>
                        <span>{group.facts.length} 条事实</span>
                      </header>
                      {group.facts.map(({ fact, factIds, evidences }, index) => (
                        <FactDetail
                          key={fact.factId || `${group.key}-${index}`}
                          fact={fact}
                          factIds={factIds}
                          evidences={evidences}
                          legacy={conclusion.legacy}
                          position={index}
                        />
                      ))}
                    </section>
                  ))
                ) : (
                  <p className="drawer-empty">当前结论没有返回原子事实。</p>
                )}
                {(conclusion.contextFacts ?? []).map((fact, index) => (
                  <FactDetail
                    key={`context-${fact.factId || `${conclusion.id}-${index}`}`}
                    fact={fact}
                    legacy={conclusion.legacy}
                    context
                  />
                ))}
              </div>
            </details>
          ))}
        </div>
      )}
      <UnknownSemantics groups={unknownGroups} />
      {relations.length > 0 && (
        <section className="semantic-relation-list" aria-label="观点关系">
          <b>观点关系</b>
          {relations.map((relation) => (
            <div key={relation.id}>
              <span
                className={`semantic-relation-badge is-${relation.type.toLowerCase()}`}
              >
                {RELATION_LABELS[relation.type] || relation.type}
              </span>
              <span>{relation.reason}</span>
              <small>{relation.factIds.join("、") || "未提供事实编号"}</small>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
