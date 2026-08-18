import { useEffect, useMemo, useRef, useState } from "react";
import {
  CaretRight,
  CheckCircle,
  EyeSlash,
  PencilSimple,
  WarningCircle,
  X,
} from "@phosphor-icons/react";

const WORKFLOW_STATUS_LABELS = {
  pending: "待处理",
  resolved: "已处理",
  excluded: "已排除",
};

function values(item, key) {
  return Array.isArray(item?.[key]) ? item[key].filter(Boolean) : [];
}

function valueText(items, empty = "未提供") {
  return items.length ? items.join("、") : empty;
}

function groupedLabels(labels, query = "") {
  const keyword = query.trim().toLowerCase();
  return labels
    .filter((label) =>
      !keyword
        ? true
        : `${label.name || ""} ${label.code || ""}`.toLowerCase().includes(keyword),
    )
    .reduce((groups, label) => {
      const group = label.group || "其他";
      groups[group] = [...(groups[group] ?? []), label];
      return groups;
    }, {});
}

export function ReviewRecordRow({
  record,
  selectionEnabled,
  selectable,
  checked,
  onCheck,
  onOpen,
}) {
  const classification = record.classification ?? {};
  const labelCodes =
    classification.primary_label_codes ?? classification.problem_label_codes ?? [];
  return (
    <article className="review-record-row" role="row">
      {selectionEnabled &&
        (selectable ? (
          <label className="review-record-checkbox">
            <input
              type="checkbox"
              aria-label={`选择 ${valueText(values(record, "order_ids"))}`}
              checked={checked}
              onChange={(event) => onCheck(event.target.checked)}
            />
          </label>
        ) : (
          <span className="review-record-checkbox" aria-hidden="true" />
        ))}
      <div>
        <b>{valueText(values(record, "order_ids"))}</b>
        <span>{valueText(values(record, "product_names"))}</span>
        {Number(record.record_count || 0) > 1 && (
          <small>{Number(record.record_count).toLocaleString()} 条退货记录</small>
        )}
      </div>
      <div>
        <b>{valueText(values(record, "listings"), "未提供 Listing")}</b>
        <span>产品SKU：{valueText(values(record, "product_skus"))}</span>
      </div>
      <div>
        <b>{valueText(values(record, "source_skus"))}</b>
        <span>匹配MSKU：{valueText(values(record, "matched_mskus"), "未匹配")}</span>
      </div>
      <div>
        <b>{labelCodes.length ? labelCodes.join("、") : "未形成标签"}</b>
        <span>{record.comment || "没有评论证据"}</span>
      </div>
      <div>
        <span className={`review-record-status ${record.workflow_status}`}>
          {WORKFLOW_STATUS_LABELS[record.workflow_status] ?? record.workflow_status}
        </span>
        <button className="secondary-button compact-button" onClick={onOpen}>
          {record.workflow_status === "pending" ? "处理" : "查看"}
          <CaretRight size={15} />
        </button>
      </div>
    </article>
  );
}

export function ReviewRecordDrawer({
  record,
  readOnly,
  labels,
  mode,
  labelCode,
  reason,
  conflict,
  saving,
  onMode,
  onLabelCode,
  onReason,
  onSave,
  onSaveAndNext,
  onClose,
  onUseServer,
  onContinueWithServer,
}) {
  const closeRef = useRef(null);
  const drawerRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const [labelQuery, setLabelQuery] = useState("");
  const editable = !readOnly && record.workflow_status === "pending";
  const classification = record.classification ?? {};
  const semanticUnits = classification.semantic_units ?? [];
  const labelGroups = useMemo(
    () => groupedLabels(labels, labelQuery),
    [labelQuery, labels],
  );

  useEffect(() => {
    setLabelQuery("");
  }, [record.id]);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const returnFocus = document.activeElement;
    closeRef.current?.focus();
    const handleKey = (event) => {
      if (event.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        drawerRef.current?.querySelectorAll(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
      if (!focusable.length) return;
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
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      returnFocus?.focus?.();
    };
  }, []);

  return (
    <div className="review-drawer-layer">
      <aside
        ref={drawerRef}
        className="review-record-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-record-drawer-title"
      >
        <header>
          <div>
            <span>{editable ? "处理复核记录" : "查看复核记录"}</span>
            <h2 id="review-record-drawer-title">
              {valueText(values(record, "order_ids"))}
            </h2>
          </div>
          <button ref={closeRef} aria-label="关闭复核抽屉" onClick={onClose}>
            <X size={20} />
          </button>
        </header>
        <div className="review-drawer-scroll">
          <section className="review-business-evidence">
            <dl>
              <div>
                <dt>产品名称</dt>
                <dd>{valueText(values(record, "product_names"))}</dd>
              </div>
              <div>
                <dt>Listing</dt>
                <dd>{valueText(values(record, "listings"), "未提供 Listing")}</dd>
              </div>
              <div>
                <dt>产品SKU</dt>
                <dd>{valueText(values(record, "product_skus"))}</dd>
              </div>
              <div>
                <dt>退货SKU（MSKU）</dt>
                <dd>{valueText(values(record, "source_skus"))}</dd>
              </div>
              <div>
                <dt>匹配MSKU</dt>
                <dd>{valueText(values(record, "matched_mskus"), "未匹配")}</dd>
              </div>
              <div>
                <dt>分类单元记录数</dt>
                <dd>{Number(record.record_count || 0).toLocaleString()}</dd>
              </div>
            </dl>
            <blockquote>“{record.comment || "没有评论证据"}”</blockquote>
          </section>

          <section className="review-current-result">
            <b>当前分类结果与证据</b>
            <p>
              {(classification.primary_label_codes ?? []).join("、") || "未形成主标签"}
            </p>
            {semanticUnits.length ? (
              semanticUnits.map((unit, index) => (
                <div key={`${unit.label_code || "evidence"}-${index}`}>
                  <span>{unit.label_code || "未提供标签"}</span>
                  <p>{unit.evidence || "未提供证据"}</p>
                </div>
              ))
            ) : (
              <small>模型未提取到结构化证据。</small>
            )}
          </section>

          {conflict && (
            <section className="review-conflict-panel" role="alert">
              <header>
                <WarningCircle size={18} />
                <b>记录已被其他用户修改</b>
              </header>
              <p>{conflict.message}</p>
              <div className="review-conflict-compare">
                <div>
                  <span>服务器最新</span>
                  <b>修订 #{conflict.serverRecord?.revision ?? "读取失败"}</b>
                </div>
                <div>
                  <span>我的未保存</span>
                  <b>
                    {mode === "confirm"
                      ? "确认原结果"
                      : mode === "exclude"
                        ? "排除本条"
                        : labelCode || "未选择标签"}
                  </b>
                  <small>{reason}</small>
                </div>
              </div>
              <div>
                <button
                  className="secondary-button"
                  disabled={!conflict.serverRecord}
                  onClick={onUseServer}
                >
                  采用服务器最新
                </button>
                <button
                  className="primary-button"
                  disabled={!conflict.serverRecord}
                  onClick={onContinueWithServer}
                >
                  基于新修订继续编辑
                </button>
              </div>
            </section>
          )}

          {editable && (
            <section className="review-record-editor">
              <b>复核结论</b>
              <div className="review-resolution-options">
                <button
                  className={mode === "confirm" ? "active" : ""}
                  onClick={() => onMode("confirm")}
                >
                  <CheckCircle size={17} />
                  确认原结果
                </button>
                <button
                  className={mode === "modify" ? "active" : ""}
                  onClick={() => onMode("modify")}
                >
                  <PencilSimple size={17} />
                  修改分类
                </button>
                <button
                  className={mode === "exclude" ? "active is-exclude" : ""}
                  onClick={() => onMode("exclude")}
                >
                  <EyeSlash size={17} />
                  排除本条
                </button>
              </div>
              {mode === "modify" && (
                <div className="review-label-picker">
                  <label>
                    搜索分类标签
                    <input
                      aria-label="搜索分类标签"
                      value={labelQuery}
                      onChange={(event) => setLabelQuery(event.target.value)}
                      placeholder="输入标签名称或编码"
                    />
                  </label>
                  <label>
                    修改为
                    <select
                      aria-label="修改分类标签"
                      value={labelCode}
                      onChange={(event) => onLabelCode(event.target.value)}
                    >
                      <option value="">请选择分类标签</option>
                      {Object.entries(labelGroups).map(([group, options]) => (
                        <optgroup key={group} label={group}>
                          {options.map((label) => (
                            <option key={label.code} value={label.code}>
                              {label.name} · {label.code}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </label>
                </div>
              )}
              {mode === "exclude" && (
                <div className="review-exclude-note" role="status">
                  <EyeSlash size={18} />
                  此记录会保留在系统和审计历史中，但不进入语义分析和看板指标。
                </div>
              )}
              <label>
                处理原因
                <textarea
                  rows="4"
                  required
                  value={reason}
                  onChange={(event) => onReason(event.target.value)}
                  placeholder="必填：说明确认、修改或排除的判断依据"
                />
              </label>
              <div className="review-record-save-actions">
                <button
                  className="secondary-button"
                  disabled={
                    saving ||
                    Boolean(conflict) ||
                    !reason.trim() ||
                    (mode === "modify" && !labelCode)
                  }
                  onClick={onSave}
                >
                  仅保存
                </button>
                <button
                  className="primary-button"
                  disabled={
                    saving ||
                    Boolean(conflict) ||
                    !reason.trim() ||
                    (mode === "modify" && !labelCode)
                  }
                  onClick={onSaveAndNext}
                >
                  {saving ? "正在保存…" : "保存并下一条"}
                </button>
              </div>
            </section>
          )}
        </div>
      </aside>
    </div>
  );
}
