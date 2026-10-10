import { X } from "@phosphor-icons/react";
import { useState } from "react";

import { useDialogFocus } from "../../hooks/useDialogFocus";
import { resultLabelText } from "../../lib/taxonomyPresentation";
import { SemanticResultPanel } from "./SemanticResultPanel";
import { ManualSemanticEditor } from "./ManualSemanticEditor";

/**
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultGroupResponse} ClassificationResultGroup
 */

/**
 * @param {{
 *   group: ClassificationResultGroup,
 *   analysisContext: string,
 *   onClose: () => void,
 *   onSaved?: (versionId: string) => void,
 *   returnFocusRef: { current: HTMLElement | null }
 * }} props
 */
export function EvidenceDrawer({
  group,
  analysisContext,
  onClose,
  onSaved,
  returnFocusRef,
}) {
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const requestClose = () => {
    if (saving) return;
    if (dirty) {
      setConfirmClose(true);
      return;
    }
    onClose();
  };
  const record = group.record;
  const isUserFeedback = analysisContext === "user_feedback";
  const classification = record.classification ?? {};
  const { dialogRef } = useDialogFocus({
    open: true,
    onClose: requestClose,
    returnFocusRef,
  });

  return (
    <div
      className="evidence-drawer-layer"
      role="presentation"
      onMouseDown={requestClose}
    >
      <aside
        ref={dialogRef}
        className="evidence-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-drawer-title"
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span id="evidence-drawer-title">分类结果与证据</span>
            <h2>{record.order_id || record.source_record_id}</h2>
          </div>
          <button
            data-dialog-initial-focus
            className="icon-button"
            aria-label="关闭证据抽屉"
            onClick={requestClose}
          >
            <X size={19} />
          </button>
        </header>
        {confirmClose && (
          <section className="drawer-section" role="alert">
            <p>有未保存的修改，是否放弃？</p>
            <button className="secondary-button" onClick={() => setConfirmClose(false)}>
              继续编辑
            </button>
            <button className="secondary-button" onClick={onClose}>
              放弃修改
            </button>
          </section>
        )}

        <section className="drawer-section">
          <b>业务信息</b>
          <DrawerField label="店铺/站点" value={record.store_site} />
          <DrawerField label="Listing" value={record.listing} />
          <DrawerField label="产品名称" value={record.product_name} />
          <DrawerField
            label={isUserFeedback ? "来源SKU（MSKU）" : "退货SKU（MSKU）"}
            value={record.source_sku}
          />
          <DrawerField label="匹配MSKU" value={record.matched_msku} />
          <DrawerField label="产品SKU" value={record.product_sku} />
          <DrawerField
            label="产品匹配"
            value={record.product_match_status === "matched" ? "已匹配" : "未匹配"}
          />
        </section>

        <section className="drawer-section">
          <b>{isUserFeedback ? "用户反馈原文" : "退货原文"}</b>
          <DrawerField
            label={isUserFeedback ? "反馈标题" : "Amazon原因"}
            value={record.reason}
          />
          <blockquote>
            {record.comment || (isUserFeedback ? "未提供反馈正文" : "未提供退货评论")}
          </blockquote>
        </section>

        {group.member_count > 1 && (
          <section className="drawer-section drawer-source-members">
            <b>关联源明细（{group.member_count}）</b>
            {group.members.map((member) => (
              <details key={member.source_record_id}>
                <summary>
                  源记录 {member.source_row} · {member.return_date || "日期未提供"}
                </summary>
                <DrawerField label="源记录ID" value={member.source_record_id} />
                {member.source_origin_id && (
                  <DrawerField label="源表明细ID" value={member.source_origin_id} />
                )}
                <DrawerField label="原因" value={member.reason} />
                <blockquote>{member.comment || "未提供反馈正文"}</blockquote>
              </details>
            ))}
          </section>
        )}

        <section className="drawer-section">
          <b>业务标签</b>
          <DrawerField
            label={isUserFeedback ? "主要问题（如有）" : "主要问题"}
            value={resultLabelText(record, classification.primary_label_codes)}
          />
          <DrawerField
            label="问题标签"
            value={resultLabelText(record, classification.problem_label_codes)}
          />
          {isUserFeedback && (
            <DrawerField
              label="正向标签"
              value={resultLabelText(record, classification.positive_label_codes)}
            />
          )}
          <DrawerField label="处理状态" value={record.processing_status} />
          <DrawerField
            label="复核原因"
            value={classification.review_reasons?.join("；")}
          />
        </section>

        <section className="drawer-section">
          <SemanticResultPanel record={record} />
          {onSaved && !editing && (
            <button className="secondary-button" onClick={() => setEditing(true)}>
              人工修正
            </button>
          )}
          {onSaved && editing && (
            <ManualSemanticEditor
              group={group}
              onSaved={onSaved}
              onDirtyChange={setDirty}
              onSavingChange={setSaving}
              onCancel={() => {
                if (dirty) {
                  setConfirmClose(true);
                } else {
                  setEditing(false);
                }
              }}
            />
          )}
        </section>

        <section className="drawer-section drawer-lineage">
          <b>运行来源</b>
          <DrawerField label="模型" value={classification.model_name} />
          <DrawerField label="提示词版本" value={classification.prompt_version} />
          <DrawerField label="分类体系" value={classification.taxonomy_version} />
          <DrawerField label="classification_key" value={record.classification_key} />
          <DrawerField label="源记录ID" value={record.source_record_id} />
          {record.source_origin_id && (
            <DrawerField label="源表明细ID" value={record.source_origin_id} />
          )}
        </section>
      </aside>
    </div>
  );
}

/**
 * @param {{ label: string, value: string | number | null | undefined }} props
 */
function DrawerField({ label, value }) {
  return (
    <div className="drawer-field">
      <span>{label}</span>
      <b>{value || "未提供"}</b>
    </div>
  );
}
