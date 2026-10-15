import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import Button from "antd/es/button";
import { api } from "../../api";
import { AntdProvider } from "../../components/AntdProvider";
import {
  errorMessage,
  errorStatus,
} from "../analysis-dashboards/dashboardRequestErrors";
import { SemanticResultPanel } from "./SemanticResultPanel";
import { ManualSemanticFields } from "./ManualSemanticFields";
import { semanticDraftChanged, semanticItemErrors } from "./manualSemanticValidation";
import { selectedSentiment } from "../review-batches/semanticReviewDrafts";
import { useUnsavedNavigation } from "../../hooks/useUnsavedNavigation";
import { UnsavedChangesActions } from "../../components/UnsavedChangesActions";

/** @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultGroupResponse} Group */
/** @typedef {import("../review-batches/semanticLedgerContracts").ReviewLabel} ReviewLabel */
/** @typedef {{item_id: string, evidence_text: string, opinion: string, label_code: string, sentiment: string}} Draft */

/** @param {Group["record"]} record @returns {Draft[]} */
function semanticDraft(record) {
  return (record.classification.semantic_units ?? []).map((unit, index) => ({
    item_id: `unit:${index}`,
    evidence_text: unit.evidence || "",
    opinion: unit.opinion || "",
    label_code: unit.label_code,
    sentiment: unit.sentiment || "",
  }));
}

/** @param {{group: Group, onSaved: (versionId: string, advance?: boolean) => void | Promise<void>, onSavedBeforeExit?: () => void | Promise<void>, canAdvance?: boolean, onCancel: () => void, onDirtyChange: (dirty: boolean) => void, onSavingChange: (saving: boolean) => void, onNavigationRequest?: () => void, onExitConfirmationChange?: (close: (() => void) | null) => void}} props */
export function ManualSemanticEditor({
  group,
  onSaved,
  onSavedBeforeExit,
  onCancel,
  onDirtyChange,
  onSavingChange,
  onNavigationRequest,
  onExitConfirmationChange,
  canAdvance = false,
}) {
  const [currentGroup, setCurrentGroup] = useState(group);
  const record = currentGroup.record;
  const [conflict, setConflict] = useState(false);
  const [recovering, setRecovering] = useState(false);
  const [recovered, setRecovered] = useState(false);
  const [baseline, setBaseline] = useState(() => semanticDraft(record));
  const [items, setItems] = useState(baseline);
  const dirty = semanticDraftChanged(items, baseline);
  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);
  const [labels, setLabels] = useState(/** @type {ReviewLabel[]} */ ([]));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const saveLock = useRef(false);
  const leavingRef = useRef(false);
  const [saveNext, setSaveNext] = useState(false);
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
  };
  const valid = items.every((item) =>
    Object.values(semanticItemErrors(item, labels)).every((message) => !message),
  );
  const save = async (advance = false, complete = true) => {
    if (
      saving ||
      saveLock.current ||
      loading ||
      recovering ||
      conflict ||
      !labels.length ||
      !valid
    )
      return false;
    saveLock.current = true;
    setSaveNext(advance);
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
      const leaving = !complete || leavingRef.current;
      if (leaving) await onSavedBeforeExit?.();
      // 已提交的结果导航不应被上一轮渲染的未保存状态拦截。
      flushSync(() => {
        onDirtyChange(false);
        setBaseline(items);
      });
      if (!leaving) {
        if (advance) await onSaved(result.version_id, true);
        else await onSaved(result.version_id);
      }
      return true;
    } catch (reason) {
      setError(errorMessage(reason));
      setConflict(errorStatus(reason) === 409);
      return false;
    } finally {
      saveLock.current = false;
      setSaving(false);
      onSavingChange(false);
    }
  };
  const exit = useUnsavedNavigation({
    dirty,
    busy: dirty && (saving || recovering),
    save: () => save(false, false),
    canSave: !loading && !conflict && valid && Boolean(labels.length),
    onRequest: () => {
      leavingRef.current = true;
      onNavigationRequest?.();
    },
  });
  useEffect(() => {
    if (!exit.pendingExit) leavingRef.current = false;
  }, [exit.pendingExit]);
  useEffect(() => {
    onExitConfirmationChange?.(exit.pendingExit ? exit.continueEditing : null);
    return () => onExitConfirmationChange?.(null);
  }, [exit.pendingExit, exit.continueEditing, onExitConfirmationChange]);

  const loadLatest = async () => {
    setRecovering(true);
    onSavingChange(true);
    try {
      const versions = await api.classificationResultVersions(record.result_version_id);
      const latest = versions[0];
      if (!latest || latest.version_id === record.result_version_id) {
        setError("当前结果未变化；若 Listing 正在运行，请结束后再保存。输入已保留。");
        setConflict(false);
        return;
      }
      const groups = await api.classificationResultRecordGroups(latest.version_id, {
        feedback_source_record_id: record.source_record_id,
      });
      const latestGroup = groups.items[0];
      if (!latestGroup) throw new Error("最新结果中未找到这条反馈，输入已保留。");
      setCurrentGroup(latestGroup);
      setBaseline(semanticDraft(latestGroup.record));
      setRecovered(true);
      setConflict(false);
      setError("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setRecovering(false);
      onSavingChange(false);
    }
  };

  return (
    <AntdProvider>
      <div ref={editorRef} className="manual-semantic-editor">
        <header>
          <b>人工修正</b>
          <span>保存影响当前反馈组及其 {currentGroup.member_count} 条源明细</span>
        </header>
        {loading && <p role="status">正在读取分类标准…</p>}
        {exit.pendingExit && <UnsavedChangesActions guard={exit} />}
        {error && (
          <p role="alert">
            {error}
            {!labels.length && (
              <Button onClick={() => setAttempt((value) => value + 1)}>重试</Button>
            )}
          </p>
        )}
        {conflict && (
          <Button loading={recovering} onClick={loadLatest}>
            加载最新结果并保留输入
          </Button>
        )}
        {recovered && (
          <section aria-label="最新结果核对">
            <p role="status">已保留你的输入，请核对最新结果后再保存。</p>
            <SemanticResultPanel record={record} title="最新结果" />
          </section>
        )}
        <fieldset disabled={saving || loading || recovering}>
          <ManualSemanticFields
            items={items}
            labels={labels}
            disabled={saving || loading || recovering}
            loading={loading}
            onEdit={edit}
            onRemove={(index) => {
              setItems(items.filter((_, position) => position !== index));
            }}
          />
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
            }}
          >
            补充观点
          </Button>
        </fieldset>
        <footer>
          <Button disabled={saving || recovering} onClick={onCancel}>
            取消
          </Button>
          <Button
            aria-label="保存修正"
            type={canAdvance ? "default" : "primary"}
            loading={saving && !saveNext}
            disabled={
              saving ||
              Boolean(exit.pendingExit) ||
              loading ||
              recovering ||
              conflict ||
              !labels.length ||
              !valid
            }
            onClick={() => save()}
          >
            保存修正
          </Button>
          {canAdvance && (
            <Button
              type="primary"
              loading={saving && saveNext}
              disabled={
                saving ||
                Boolean(exit.pendingExit) ||
                loading ||
                recovering ||
                conflict ||
                !labels.length ||
                !valid
              }
              onClick={() => save(true)}
            >
              保存并查看下一条
            </Button>
          )}
        </footer>
      </div>
    </AntdProvider>
  );
}
