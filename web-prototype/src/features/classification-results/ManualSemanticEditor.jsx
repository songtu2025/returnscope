import { useEffect, useRef, useState } from "react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import Select from "antd/es/select";
import { api } from "../../api";
import { AntdProvider } from "../../components/AntdProvider";
import { labelText } from "../../lib/taxonomyPresentation";
import { errorMessage } from "../analysis-dashboards/dashboardRequestErrors";
import { selectedSentiment } from "../review-batches/semanticReviewDrafts";
import { SentimentField } from "../review-batches/SemanticSentimentField";

/** @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultGroupResponse} Group */
/** @typedef {import("../review-batches/semanticLedgerContracts").ReviewLabel} ReviewLabel */
/** @typedef {{item_id: string, evidence_text: string, opinion: string, label_code: string, sentiment: string}} Draft */

/** @param {{group: Group, onSaved: (versionId: string) => void, onCancel: () => void, onDirtyChange: (dirty: boolean) => void, onSavingChange: (saving: boolean) => void}} props */
export function ManualSemanticEditor({
  group,
  onSaved,
  onCancel,
  onDirtyChange,
  onSavingChange,
}) {
  const record = group.record;
  const [items, setItems] = useState(() =>
    (record.classification.semantic_units ?? []).map((unit, index) => ({
      item_id: `unit:${index}`,
      evidence_text: unit.evidence || "",
      opinion: unit.opinion || "",
      label_code: unit.label_code,
      sentiment: unit.sentiment || "",
    })),
  );
  const [labels, setLabels] = useState(/** @type {ReviewLabel[]} */ ([]));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const editorRef = useRef(/** @type {HTMLDivElement | null} */ (null));
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    api
      .resultTaxonomy(record.result_version_id, { signal: controller.signal })
      .then((taxonomy) => {
        setLabels(taxonomy.labels ?? []);
        setLoading(false);
        setError("");
      })
      .catch((reason) => {
        if (controller.signal.aborted) return;
        setError(errorMessage(reason));
        setLoading(false);
      });
    return () => controller.abort();
  }, [record.result_version_id, attempt]);
  useEffect(() => {
    if (loading) return;
    const field =
      editorRef.current?.querySelector("input") ||
      editorRef.current?.querySelector("button");
    if (field instanceof HTMLElement) field.focus();
  }, [loading]);

  /** @param {number} index @param {Partial<Draft>} change */
  const edit = (index, change) => {
    setItems((current) =>
      current.map((item, position) =>
        position === index ? { ...item, ...change } : item,
      ),
    );
    onDirtyChange(true);
  };
  const valid = items.every(
    (item) =>
      item.opinion.trim() &&
      item.evidence_text.trim() &&
      labels.some((label) => label.code === item.label_code) &&
      selectedSentiment(item.label_code, labels, item.sentiment),
  );
  const save = async () => {
    setSaving(true);
    onSavingChange(true);
    setError("");
    try {
      const result = await api.correctClassificationResult(
        record.result_version_id,
        record.id,
        {
          semantic_items: items.map((item) => ({
            ...item,
            sentiment: /** @type {"POSITIVE" | "NEGATIVE" | "NEUTRAL"} */ (
              selectedSentiment(item.label_code, labels, item.sentiment)
            ),
          })),
        },
      );
      onDirtyChange(false);
      onSaved(result.version_id);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(false);
      onSavingChange(false);
    }
  };

  return (
    <AntdProvider>
      <div ref={editorRef} className="manual-semantic-editor">
        <header>
          <b>人工修正</b>
          <span>保存影响当前反馈组及其 {group.member_count} 条源明细</span>
        </header>
        {loading && <p role="status">正在读取分类标准…</p>}
        {error && (
          <p role="alert">
            {error}
            {!labels.length && (
              <Button onClick={() => setAttempt((value) => value + 1)}>重试</Button>
            )}
          </p>
        )}
        <fieldset disabled={saving || loading}>
          {items.map((item, index) => (
            <div className="manual-semantic-item" key={item.item_id}>
              <div className="manual-semantic-item-heading">
                <b>观点 {index + 1}</b>
                <Button
                  disabled={saving}
                  onClick={() => {
                    setItems(items.filter((_, position) => position !== index));
                    onDirtyChange(true);
                  }}
                >
                  删除观点 {index + 1}
                </Button>
              </div>
              <label>
                原文证据
                <Input
                  aria-label={`观点 ${index + 1} 原文证据`}
                  value={item.evidence_text}
                  onChange={(event) =>
                    edit(index, { evidence_text: event.target.value })
                  }
                />
              </label>
              <label>
                用户观点
                <Input
                  aria-label={`观点 ${index + 1} 用户观点`}
                  value={item.opinion}
                  onChange={(event) => edit(index, { opinion: event.target.value })}
                />
              </label>
              <label>
                归类标签
                <Select
                  aria-label={`观点 ${index + 1} 归类标签`}
                  disabled={saving}
                  showSearch
                  optionFilterProp="label"
                  value={item.label_code || undefined}
                  placeholder="请选择分类标签"
                  onChange={(label_code) => edit(index, { label_code, sentiment: "" })}
                  options={labels.map((label) => ({
                    value: label.code,
                    label: labelText(label),
                  }))}
                  getPopupContainer={(trigger) => trigger.parentElement}
                />
              </label>
              <SentimentField
                code={item.label_code}
                labels={labels}
                value={item.sentiment}
                disabled={saving || loading}
                name={`观点 ${index + 1} 评价方向`}
                onChange={(sentiment) => edit(index, { sentiment })}
              />
            </div>
          ))}
          {!items.length && <p>当前没有语义观点；保存将标记为人工已处理。</p>}
          <Button
            disabled={saving || loading || items.length >= 100}
            onClick={() => {
              setItems([
                ...items,
                {
                  item_id: crypto.randomUUID(),
                  evidence_text: "",
                  opinion: "",
                  label_code: "",
                  sentiment: "",
                },
              ]);
              onDirtyChange(true);
            }}
          >
            补充观点
          </Button>
        </fieldset>
        <footer>
          <Button disabled={saving} onClick={onCancel}>
            取消
          </Button>
          <Button
            aria-label="保存修正"
            type="primary"
            loading={saving}
            disabled={loading || !labels.length || !valid}
            onClick={save}
          >
            保存修正
          </Button>
        </footer>
      </div>
    </AntdProvider>
  );
}
