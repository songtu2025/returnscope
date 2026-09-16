import { CaretDown, Info, WarningCircle } from "@phosphor-icons/react";
import {
  factPresentation,
  semanticConclusions,
  semanticRelations,
  semanticRecordStatus,
  semanticStatusLabel,
  semanticUnknownGroups,
} from "./semanticResultPresentation";

/** @typedef {Record<string, any>} SemanticData */

/** @type {Record<string, string>} */
const RELATION_LABELS = {
  CONFLICT: "疑似冲突",
  MIXED: "条件差异",
  MULTI_ACTOR: "多位使用者",
  MULTI_PRODUCT: "多个商品",
};

/** @param {any} value @param {boolean} [legacy] @returns {any} */
function display(value, legacy = false) {
  return value || (legacy ? "旧结果未提供" : "未提供");
}

/** @param {any} value @param {boolean} [legacy] @returns {string} */
function evidenceDisplay(value, legacy = false) {
  return value || (legacy ? "旧结果未提供文本证据" : "无文本证据");
}

/** @param {any[]} values @param {boolean} legacy */
function joinedDisplay(values, legacy) {
  const text = values.filter((value) => value && value !== "UNSPECIFIED").join(" / ");
  return display(text, legacy);
}

/** @param {SemanticData} item */
function isOtherLabel(item) {
  return (
    item.labelPath.some(
      (/** @type {any} */ value) => String(value).trim() === "其他",
    ) || /(?:^|_)OTHER(?:_|$)/i.test(item.labelCode || "")
  );
}

/** @param {{item: SemanticData, legacy: boolean}} props */
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

/** @param {{fact: SemanticData, legacy: boolean, context?: boolean}} props */
function FactDetail({ fact, legacy, context = false }) {
  const item = factPresentation(fact);
  const path = item.labelPath.join(" → ");
  return (
    <article className={`semantic-fact-card${context ? " is-context" : ""}`}>
      <header>
        <div>
          {context && <small>裁决上下文</small>}
          <b>{path || item.labelCode || (context ? "未映射上下文" : "未映射标签")}</b>
        </div>
        <span>{display(item.factId, legacy)}</span>
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
      <div className="semantic-evidence-source">
        证据来源：{display(item.evidenceSourceLabel, legacy)}
      </div>
      <blockquote>“{evidenceDisplay(item.evidence, legacy)}”</blockquote>
      {legacy && item.labelPath.length > 0 && item.labelPath.length < 3 && (
        <small className="semantic-legacy-note">旧结果未保存完整标签路径。</small>
      )}
    </article>
  );
}

/** @param {{item: SemanticData}} props */
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

/** @param {{groups: {review: SemanticData[], informational: SemanticData[]}}} props */
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

/** @param {{record: SemanticData, title?: string}} props */
export function SemanticResultPanel({ record, title = "评论级结论" }) {
  const conclusions = semanticConclusions(record);
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
          {conclusions.map((conclusion) => (
            <details key={conclusion.id} className="semantic-conclusion-item" open>
              <summary>
                <div>
                  <span>{conclusion.topicPath.join(" → ") || conclusion.topic}</span>
                  <b>{conclusion.summary || conclusion.topic}</b>
                </div>
                <SemanticStatusBadge status={conclusion.status} />
                <small>{conclusion.facts.length} 条确定结论</small>
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
                {conclusion.facts.length ? (
                  /** @type {SemanticData[]} */ (conclusion.facts).map(
                    (fact, index) => (
                      <FactDetail
                        key={fact.factId || `${conclusion.id}-${index}`}
                        fact={fact}
                        legacy={conclusion.legacy}
                      />
                    ),
                  )
                ) : (
                  <p className="drawer-empty">当前结论没有返回原子事实。</p>
                )}
                {
                  /** @type {SemanticData[]} */ (conclusion.contextFacts ?? []).map(
                    (fact, index) => (
                      <FactDetail
                        key={`context-${fact.factId || `${conclusion.id}-${index}`}`}
                        fact={fact}
                        legacy={conclusion.legacy}
                        context
                      />
                    ),
                  )
                }
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
