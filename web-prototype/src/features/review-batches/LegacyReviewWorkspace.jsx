import { CheckCircle, ListChecks } from "@phosphor-icons/react";
import {
  CardHeading,
  EmptyState,
  InfoRow,
  StatusBadge,
} from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";

/** @typedef {import("../../shared/api/reviewBatchContracts").LegacyReviewRecord} LegacyReviewRecord */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewClassification} ReviewClassification */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel */
/** @typedef {{selected: LegacyReviewRecord | null, labels: ReviewLabel[], labelCode: string, note: string, saving: boolean, onLabelCode: (code: string) => void, onNote: (note: string) => void, onResolve: () => Promise<void>}} LegacyReviewWorkspaceProps */

/** @param {{selected: LegacyReviewRecord}} props */
function LegacyReviewHeader({ selected }) {
  return (
    <header className="review-header">
      <div>
        <span className="asset-type">
          {selected.workflow_status === "pending" ? "等待人工判断" : "已完成复核"}
        </span>
        <h2>{selected.task_title}</h2>
        <p>
          记录版本 #{selected.revision} · 最近修改 {formatTime(selected.updated_at)}
        </p>
      </div>
      <StatusBadge value={selected.classification.status} />
    </header>
  );
}

/** @param {{selected: LegacyReviewRecord}} props */
function LegacyReviewEvidence({ selected }) {
  return (
    <section className="evidence-panel">
      <span>客户评论原文</span>
      <blockquote>“{selected.comment}”</blockquote>
      <div className="model-evidence">
        <b>模型证据</b>
        <p>
          {selected.classification.semantic_units
            ?.map((unit) => unit.evidence)
            .join(" · ") || "模型未提取到有效证据"}
        </p>
      </div>
    </section>
  );
}

/** @param {Omit<LegacyReviewWorkspaceProps, "saving" | "onResolve"> & {selected: LegacyReviewRecord}} props */
function LegacyReviewFields({
  selected,
  labels,
  labelCode,
  note,
  onLabelCode,
  onNote,
}) {
  return (
    <>
      <label>
        最终标签
        <select
          disabled={selected.workflow_status === "resolved"}
          value={labelCode}
          onChange={(event) => onLabelCode(event.target.value)}
        >
          <option value="">保持模型结论</option>
          {labels.map((label) => (
            <option key={label.code} value={label.code}>
              {label.name} · {label.code}
            </option>
          ))}
        </select>
      </label>
      <label>
        修改说明
        <textarea
          disabled={selected.workflow_status === "resolved"}
          value={note}
          onChange={(event) => onNote(event.target.value)}
          rows={4}
          placeholder="必填：说明判断依据，便于后续追溯"
          required
        />
      </label>
    </>
  );
}

/** @param {LegacyReviewWorkspaceProps & {selected: LegacyReviewRecord}} props */
function LegacyReviewEditor({
  selected,
  labels,
  labelCode,
  note,
  saving,
  onLabelCode,
  onNote,
  onResolve,
}) {
  return (
    <section className="content-card">
      <CardHeading title="复核结论" note="修改会生成新结果版本" />
      <LegacyReviewFields
        selected={selected}
        labels={labels}
        labelCode={labelCode}
        note={note}
        onLabelCode={onLabelCode}
        onNote={onNote}
      />
      {selected.workflow_status === "pending" && (
        <button
          className="primary-button full-button"
          disabled={saving || !note.trim()}
          onClick={onResolve}
        >
          {saving ? "正在写入新版本…" : "确认并完成复核"}
          <CheckCircle size={18} />
        </button>
      )}
    </section>
  );
}

/** @param {{selected: LegacyReviewRecord}} props */
function LegacyReviewModel({ selected }) {
  return (
    <section className="content-card">
      <CardHeading title="模型判断" note={selected.classification.model_name} />
      <InfoRow
        label="主因标签"
        value={selected.classification.primary_label_codes?.join("、") || "—"}
      />
      <InfoRow
        label="问题标签"
        value={selected.classification.problem_label_codes?.join("、") || "—"}
      />
      <InfoRow
        label="复核原因"
        value={selected.classification.review_reasons?.join("；") || "—"}
      />
      <InfoRow label="分类体系" value={selected.classification.taxonomy_version} />
    </section>
  );
}

/** @param {{selected: LegacyReviewRecord, labels: ReviewLabel[]}} props */
function LegacyReviewHistory({ selected, labels }) {
  /** @param {ReviewClassification | null | undefined} classification */
  const revisionLabel = (classification) => {
    const codes = classification?.primary_label_codes ?? [];
    return (
      codes
        .map((code) => labels.find((label) => label.code === code)?.name ?? code)
        .join("、") || "未标注"
    );
  };

  return (
    <section className="content-card revision-card">
      <CardHeading
        title="修改留痕"
        note={`${selected.revisions?.length ?? 0} 次人工修改`}
      />
      {selected.revisions?.length === 0 && <p className="muted-line">尚无人工修改。</p>}
      {selected.revisions?.map((revision) => (
        <div className="revision-row" key={revision.id}>
          <span>{revision.actor_name?.slice(0, 1)}</span>
          <div>
            <b>
              {revision.actor_name} · 结果版本 #{revision.revision}
            </b>
            <p className="revision-change">
              {revisionLabel(revision.before)} → {revisionLabel(revision.after)}
            </p>
            <p>{revision.note}</p>
            <small>{formatTime(revision.created_at)}</small>
          </div>
        </div>
      ))}
    </section>
  );
}

/** @param {LegacyReviewWorkspaceProps} props */
export function LegacyReviewWorkspace({
  selected,
  labels,
  labelCode,
  note,
  saving,
  onLabelCode,
  onNote,
  onResolve,
}) {
  return (
    <section className="review-workspace">
      {!selected && (
        <EmptyState
          icon={ListChecks}
          title="选择一条复核记录"
          description="查看证据并完成标签确认。"
        />
      )}
      {selected && (
        <>
          <LegacyReviewHeader selected={selected} />
          <LegacyReviewEvidence selected={selected} />
          <div className="review-grid">
            <LegacyReviewEditor
              selected={selected}
              labels={labels}
              labelCode={labelCode}
              note={note}
              saving={saving}
              onLabelCode={onLabelCode}
              onNote={onNote}
              onResolve={onResolve}
            />
            <LegacyReviewModel selected={selected} />
            <LegacyReviewHistory selected={selected} labels={labels} />
          </div>
        </>
      )}
    </section>
  );
}
