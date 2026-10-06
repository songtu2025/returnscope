import { CaretDown, Info, WarningCircle } from "@phosphor-icons/react";
import { FactDetail, UnknownDetail } from "./SemanticFactDetails";
import { groupFactsByLabel } from "./semanticFactGroups";
import {
  semanticConclusions,
  semanticRelations,
  semanticRecordStatus,
  semanticStatusLabel,
  semanticUnknownGroups,
} from "./semanticResultPresentation";

/**
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultRecordResponse} GeneratedRecord
 * @typedef {GeneratedRecord | Record<string, unknown>} SemanticRecord
 * @typedef {ReturnType<typeof semanticUnknownGroups>} UnknownSemanticGroups
 * @typedef {ReturnType<typeof semanticConclusions>[number] & {topicLabel: string, labelGroups: ReturnType<typeof groupFactsByLabel>}} DisplayedConclusion
 */

/** @type {Record<string, string>} */
const RELATION_LABELS = {
  CONFLICT: "疑似冲突",
  MIXED: "条件差异",
  MULTI_ACTOR: "多位使用者",
  MULTI_PRODUCT: "多个商品",
};

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

/** @param {{conclusion: DisplayedConclusion}} props */
function ConclusionFacts({ conclusion }) {
  return (
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
  );
}

/** @param {{conclusion: DisplayedConclusion}} props */
function SemanticConclusion({ conclusion }) {
  return (
    <details className="semantic-conclusion-item" open>
      <summary>
        <div>
          <span>{conclusion.topicLabel}</span>
          {conclusion.summary && conclusion.summary !== conclusion.topicLabel && (
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
      <ConclusionFacts conclusion={conclusion} />
    </details>
  );
}

/** @param {{relations: ReturnType<typeof semanticRelations>}} props */
function SemanticRelations({ relations }) {
  return (
    <section className="semantic-relation-list" aria-label="观点关系">
      <b>观点关系</b>
      {relations.map((relation) => (
        <div key={relation.id}>
          <span className={`semantic-relation-badge is-${relation.type.toLowerCase()}`}>
            {RELATION_LABELS[relation.type] || relation.type}
          </span>
          <span>{relation.reason}</span>
          <small>{relation.factIds.join("、") || "未提供事实编号"}</small>
        </div>
      ))}
    </section>
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
            <SemanticConclusion key={conclusion.id} conclusion={conclusion} />
          ))}
        </div>
      )}
      <UnknownSemantics groups={unknownGroups} />
      {relations.length > 0 && <SemanticRelations relations={relations} />}
    </div>
  );
}
