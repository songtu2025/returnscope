import { useEffect, useRef } from "react";
import { X } from "@phosphor-icons/react";

import { resultLabelText } from "../../lib/taxonomyPresentation";
import { SemanticResultPanel } from "./SemanticResultPanel";

export function EvidenceDrawer({ record, onClose, returnFocusRef }) {
  const classification = record.classification ?? {};
  const drawerRef = useRef(null);
  const closeButtonRef = useRef(null);

  useEffect(() => {
    const drawer = drawerRef.current;
    if (!drawer) return undefined;
    const returnFocus = returnFocusRef.current;
    const handleKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        drawer.querySelectorAll(
          'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
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
          <DrawerField label="退货SKU（MSKU）" value={record.source_sku} />
          <DrawerField label="匹配MSKU" value={record.matched_msku} />
          <DrawerField label="产品SKU" value={record.product_sku} />
          <DrawerField
            label="产品匹配"
            value={record.product_match_status === "matched" ? "已匹配" : "未匹配"}
          />
        </section>

        <section className="drawer-section">
          <b>退货原文</b>
          <DrawerField label="Amazon原因" value={record.reason} />
          <blockquote>{record.comment || "未提供退货评论"}</blockquote>
        </section>

        <section className="drawer-section">
          <b>业务标签</b>
          <DrawerField
            label="主要问题"
            value={resultLabelText(record, classification.primary_label_codes)}
          />
          <DrawerField
            label="问题标签"
            value={resultLabelText(record, classification.problem_label_codes)}
          />
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
        </section>
      </aside>
    </div>
  );
}

function DrawerField({ label, value }) {
  return (
    <div className="drawer-field">
      <span>{label}</span>
      <b>{value || "未提供"}</b>
    </div>
  );
}
