import { factPresentation } from "./semanticResultPresentation";

/**
 * @typedef {import("./semanticResultFacts").NormalizedFact} NormalizedFact
 * @typedef {import("./semanticResultPresentation").NormalizedUnknownSemantic} NormalizedUnknownSemantic
 * @typedef {ReturnType<typeof factPresentation>} PresentedFact
 * @typedef {import("./semanticFactGroups").FactEvidence} FactEvidence
 */

/** @param {{item: PresentedFact, legacy: boolean}} props */
function FactVerdict({ item, legacy }) {
  return (
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
  );
}

/** @param {{fact: NormalizedFact, legacy: boolean, evidences?: FactEvidence[]}} props */
function FactEvidenceList({ fact, evidences, legacy }) {
  return (
    <>
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
    </>
  );
}

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

/** @param {{item: PresentedFact, legacy: boolean, context: boolean, position?: number, factIds?: string[]}} props */
function FactHeading({ item, legacy, context, position, factIds }) {
  const path = item.labelPath.join(" → ");
  return (
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
  );
}

/** @param {{fact: NormalizedFact, legacy: boolean, context?: boolean, position?: number, factIds?: string[], evidences?: FactEvidence[]}} props */
export function FactDetail({
  fact,
  legacy,
  context = false,
  position,
  factIds,
  evidences,
}) {
  const item = factPresentation(fact);
  return (
    <article className={`semantic-fact-card${context ? " is-context" : ""}`}>
      <FactHeading
        item={item}
        legacy={legacy}
        context={context}
        position={position}
        factIds={factIds}
      />
      {!context && <FactVerdict item={item} legacy={legacy} />}
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
      <FactEvidenceList fact={fact} evidences={evidences} legacy={legacy} />
      {legacy && item.labelPath.length > 0 && item.labelPath.length < 3 && (
        <small className="semantic-legacy-note">旧结果未保存完整标签路径。</small>
      )}
    </article>
  );
}

/** @param {{item: NormalizedUnknownSemantic}} props */
export function UnknownDetail({ item }) {
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
