import { useEffect, useRef } from "react";
import { X } from "@phosphor-icons/react";

import { resultLabelText } from "../../lib/taxonomyPresentation";
import { SemanticResultPanel } from "./SemanticResultPanel";

/**
 * @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultGroupResponse} ClassificationResultGroup
 */

/**
 * @param {{
 *   group: ClassificationResultGroup,
 *   analysisContext: string,
 *   onClose: () => void,
 *   returnFocusRef: { current: HTMLElement | null }
 * }} props
 */
export function EvidenceDrawer({ group, analysisContext, onClose, returnFocusRef }) {
  const record = group.record;
  const isUserFeedback = analysisContext === "user_feedback";
  const classification = record.classification ?? {};
  const drawerRef = useRef(/** @type {HTMLElement | null} */ (null));
  const closeButtonRef = useRef(/** @type {HTMLButtonElement | null} */ (null));

  useEffect(() => {
    const drawer = drawerRef.current;
    if (!drawer) return undefined;
    const returnFocus = returnFocusRef.current;
    /** @param {KeyboardEvent} event */
    const handleKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = /** @type {HTMLElement[]} */ (
        Array.from(
          drawer.querySelectorAll(
            'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ),
        )
      );
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    closeButtonRef.current?.focus();
    drawer.addEventListener("keydown", handleKey);
    return () => {
      drawer.removeEventListener("keydown", handleKey);
      returnFocus?.focus();
    };
  }, [onClose, returnFocusRef]);

  return (
    <div className="evidence-drawer-layer" role="presentation" onMouseDown={onClose}>
      <aside
        ref={drawerRef}
        className="evidence-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-drawer-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <span id="evidence-drawer-title">分类结果与证据</span>
            <h2>{record.order_id || record.source_record_id}</h2>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button"
            aria-label="关闭证据抽屉"
            onClick={onClose}
          >
            <X size={19} />
          </button>
        </header>

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
