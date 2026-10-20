import { EvidenceDrawerField as DrawerField } from "./EvidenceDrawerField";
import { X } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { SemanticHistory } from "./SemanticHistory";

import { useDialogFocus } from "../../hooks/useDialogFocus";
import { resultLabelText } from "../../lib/taxonomyPresentation";
import { factLabelPaths } from "./semanticResultFacts";
import { formatTime } from "../../lib/presentation";
import { resultStateLabel } from "./resultActionPolicy";
import { SemanticResultPanel } from "./SemanticResultPanel";
import { ManualSemanticEditor } from "./ManualSemanticEditor";
import { EvidenceRecordNavigation } from "./EvidenceRecordNavigation";

/**
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultGroupResponse} ClassificationResultGroup
 */

/**
 * @param {{
 *   group: ClassificationResultGroup,
 *   analysisContext: string,
 *   onClose: () => void,
 *   onViewProduct?: () => void,
 *   onSaved?: (versionId: string, advance?: boolean) => void | Promise<void>,
 *   onSavedBeforeExit?: () => void | Promise<void>,
 *   navigation?: ReturnType<typeof import("./useEvidenceNavigation").useEvidenceNavigation>,
 *   disabled?: boolean,
 *   returnFocusRef: { current: HTMLElement | null }
 * }} props
 */
export function EvidenceDrawer({
  group,
  analysisContext,
  onClose,
  onViewProduct,
  onSaved,
  onSavedBeforeExit,
  disabled,
  returnFocusRef,
  navigation,
}) {
  const [editing, setEditing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const routeExitRef = useRef(/** @type {(() => void) | null} */ (null));
  const setRouteExit = useCallback((/** @type {(() => void) | null} */ close) => {
    routeExitRef.current = close;
  }, []);
  const [pendingAction, setPendingAction] = useState(
    /** @returns {(() => void) | null} */ () => null,
  );
  const requestAction = (/** @type {() => void} */ action) => {
    if (routeExitRef.current) {
      routeExitRef.current();
      return;
    }
    if (saving || navigation?.busy) return;
    if (dirty) {
      setPendingAction(() => action);
      return;
    }
    action();
  };
  const requestClose = () => requestAction(onClose);
  const record = group.record;
  const isUserFeedback = analysisContext === "user_feedback";
  const classification = record.classification ?? {};
  const labelPaths = factLabelPaths(record);
  const labelText = (/** @type {string[] | undefined} */ codes) =>
    resultLabelText(record, codes, labelPaths);
  const { dialogRef } = useDialogFocus({
    open: true,
    onClose: requestClose,
    returnFocusRef,
  });
  useEffect(() => {
    const closeButton = dialogRef.current?.querySelector("[data-dialog-initial-focus]");
    if (closeButton instanceof HTMLElement) closeButton.focus();
  }, [record.source_record_id, dialogRef]);

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
        {navigation && (
          <EvidenceRecordNavigation
            navigation={navigation}
            saving={saving}
            onMove={(direction) =>
              requestAction(() => {
                setEditing(false);
                void navigation.move(direction);
              })
            }
          />
        )}
        <section className="drawer-section drawer-correction-heading">
          <div>
            <b>
              {classification.human_review_assessment?.resolved
                ? "人工已修正"
                : "分类语义"}
            </b>
            {classification.human_review_assessment?.resolved && (
              <small>
                {classification.human_review_assessment.assessed_by_name ||
                  "操作者信息未提供"}
                {" · "}
                {formatTime(classification.human_review_assessment.assessed_at)}
              </small>
            )}
          </div>
          {onSaved && !disabled && !editing && !navigation?.locked && (
            <button
              className="primary-button compact-button"
              onClick={() => setEditing(true)}
            >
              人工修正
            </button>
          )}
        </section>
        {onSaved && !disabled && !editing && !navigation?.locked && (
          <SemanticHistory
            versionId={record.result_version_id}
            recordId={record.id}
            onSaved={onSaved}
            onBusyChange={setSaving}
          />
        )}
        {pendingAction && (
          <section className="drawer-section" role="alert">
            <p>有未保存的修改，是否放弃？</p>
            <button className="secondary-button" onClick={() => setPendingAction(null)}>
              继续编辑
            </button>
            <button
              className="secondary-button"
              onClick={() => {
                setDirty(false);
                setEditing(false);
                setPendingAction(null);
                pendingAction();
              }}
            >
              放弃修改
            </button>
          </section>
        )}

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

        <section className="drawer-section">
          {onSaved && editing && !navigation?.locked ? (
            <ManualSemanticEditor
              key={`${record.source_record_id}:${record.result_version_id}`}
              group={group}
              onSaved={onSaved}
              onDirtyChange={setDirty}
              onSavedBeforeExit={onSavedBeforeExit}
              onSavingChange={setSaving}
              onNavigationRequest={() => setPendingAction(null)}
              onExitConfirmationChange={setRouteExit}
              canAdvance={Boolean(navigation)}
              onCancel={() => requestAction(() => setEditing(false))}
            />
          ) : (
            <SemanticResultPanel record={record} />
          )}
        </section>

        <details className="drawer-section drawer-context">
          <summary>业务信息</summary>
          {onViewProduct && (
            <button
              className="secondary-button compact-button"
              disabled={saving || navigation?.busy}
              onClick={onViewProduct}
            >
              查看产品资料
            </button>
          )}
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
        </details>

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

        <details className="drawer-section drawer-context">
          <summary>业务标签与记录状态</summary>
          <DrawerField
            label={isUserFeedback ? "主要问题（如有）" : "主要问题"}
            value={labelText(classification.primary_label_codes)}
            title={classification.primary_label_codes?.join("、")}
          />
          <DrawerField
            label="问题标签"
            value={labelText(classification.problem_label_codes)}
            title={classification.problem_label_codes?.join("、")}
          />
          {isUserFeedback && (
            <DrawerField
              label="正向标签"
              value={labelText(classification.positive_label_codes)}
              title={classification.positive_label_codes?.join("、")}
            />
          )}
          <DrawerField label="记录状态" value={resultStateLabel(record)} />
          {Boolean(classification.review_reasons?.length) && (
            <DrawerField
              label="需处理原因"
              value={classification.review_reasons?.join("；")}
            />
          )}
        </details>

        <details className="drawer-section drawer-context drawer-lineage">
          <summary>
            {classification.human_review_assessment?.resolved
              ? "原始分析来源"
              : "运行来源"}
          </summary>
          <DrawerField label="模型" value={classification.model_name} />
          <DrawerField label="提示词版本" value={classification.prompt_version} />
          <DrawerField label="分类体系" value={classification.taxonomy_version} />
          <DrawerField label="classification_key" value={record.classification_key} />
          <DrawerField label="源记录ID" value={record.source_record_id} />
          {record.source_origin_id && (
            <DrawerField label="源表明细ID" value={record.source_origin_id} />
          )}
        </details>
      </aside>
    </div>
  );
}
