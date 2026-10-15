import { useEffect, useState } from "react";
import { api } from "../../api";
import { errorMessage } from "../../shared/api/requestErrors";
import {
  importNotification,
  importSelectionLabel,
  normalizeReturnVersion,
} from "./newTaskPolicy";

/** @typedef {import("./taskCreateContracts").DataVersion} DataVersion */
/** @typedef {import("./taskCreateContracts").ReturnImportResult} ReturnImportResult */
/** @typedef {import("./taskCreateContracts").TaskDraft} TaskDraft */
/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/** @typedef {import("./mysqlReturnContracts").MysqlReturnFormState} MysqlReturnFormState */

/**
 * @param {{draft?: TaskDraft | null, focusAfterPreparationRef: import("react").MutableRefObject<boolean>, form: TaskForm, invalidatePreflight: () => void, invalidateUnavailableSource: () => void, loadingSetup: boolean, notify: (message: string, type?: "success" | "error") => void, onChanged: () => void | Promise<unknown>, onDraftChange?: (draft: TaskDraft) => void, prepared: boolean, setForm: import("react").Dispatch<import("react").SetStateAction<TaskForm>>, setPrepared: import("react").Dispatch<import("react").SetStateAction<boolean>>, setVersions: import("react").Dispatch<import("react").SetStateAction<DataVersion[]>>, setupError: string, versions: DataVersion[]}} options
 */

export function useTaskImport({
  draft,
  focusAfterPreparationRef,
  form,
  invalidatePreflight,
  invalidateUnavailableSource,
  loadingSetup,
  notify,
  onChanged,
  onDraftChange,
  prepared,
  setForm,
  setPrepared,
  setVersions,
  setupError,
  versions,
}) {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [refreshError, setRefreshError] = useState("");
  const [refreshingVersions, setRefreshingVersions] = useState(false);
  const [mysqlDraft, setMysqlDraft] = useState(
    /** @type {Partial<MysqlReturnFormState> | undefined} */ (draft?.mysqlDraft),
  );
  const [dataEntryMode, setDataEntryMode] = useState(draft?.dataEntryMode ?? "mysql");
  const [selectedDataLabel, setSelectedDataLabel] = useState(
    draft?.selectedDataLabel ?? "",
  );
  const allReturns = versions
    .filter((item) => item.kind === "returns" && item.usage_scope === "task_input")
    .map(normalizeReturnVersion);
  const selectedReturns = allReturns.find(
    (item) => item.version_id === form.dataset_version_id,
  );

  useEffect(() => {
    onDraftChange?.({
      form,
      step: prepared ? 2 : 1,
      resumePreflight: prepared,
      dataEntryMode,
      selectedDataLabel,
      mysqlDraft,
    });
  }, [dataEntryMode, form, mysqlDraft, onDraftChange, selectedDataLabel, prepared]);

  useEffect(() => {
    if (
      loadingSetup ||
      setupError ||
      refreshingVersions ||
      !form.dataset_version_id ||
      selectedReturns
    )
      return;
    setPrepared(false);
    invalidateUnavailableSource();
    setForm((current) => ({ ...current, dataset_version_id: "" }));
    notify(
      "草稿中的分析数据已失效，请重新读取数据库或上传文件；其他设置已保留。",
      "error",
    );
  }, [
    loadingSetup,
    setupError,
    refreshingVersions,
    form.dataset_version_id,
    selectedReturns,
    invalidateUnavailableSource,
    setForm,
    setPrepared,
    notify,
  ]);

  /** @param {TaskForm} next */
  const updateForm = (next) => {
    if (next.dataset_version_id !== form.dataset_version_id) {
      invalidatePreflight();
      setPrepared(false);
    }
    setForm(next);
  };

  /** @param {"mysql" | "upload"} nextMode */
  const changeDataEntryMode = (nextMode) => {
    if (nextMode === dataEntryMode) return;
    setDataEntryMode(nextMode);
    setSelectedDataLabel("");
    updateForm({ ...form, dataset_version_id: "" });
  };

  const invalidateMysql = () => {
    invalidatePreflight();
    setPrepared(false);
    setForm((current) => ({ ...current, dataset_version_id: "" }));
  };

  const refreshVersions = async () => {
    setRefreshingVersions(true);
    try {
      setVersions(await api.dataVersions());
      setRefreshError("");
    } catch (error) {
      setRefreshError(errorMessage(error));
    } finally {
      setRefreshingVersions(false);
    }
  };

  /**
   * @param {ReturnImportResult} result
   * @param {"mysql" | "upload"} source
   */
  const finishImport = async (result, source) => {
    setRefreshError("");
    const dataset = result.dataset;
    const version = dataset?.versions?.find((item) => item.id === result.version_id);
    if (dataset && version) {
      // 导入已经写入成功，直接使用返回的来源，列表刷新不决定导入结果。
      const imported = {
        ...version,
        version_id: result.version_id,
        dataset_name: dataset.name ?? "用户反馈数据",
        kind: dataset.kind,
        current_version: dataset.current_version,
        usage_scope: dataset.usage_scope,
        source_name: dataset.source_name,
      };
      setVersions((current) => [
        imported,
        ...current.filter((item) => item.version_id !== result.version_id),
      ]);
    }
    invalidatePreflight();
    setDataEntryMode(source);
    setSelectedDataLabel(
      source === "mysql" ? "本次数据库取数快照" : importSelectionLabel(result),
    );
    setForm((current) => ({
      ...current,
      dataset_version_id: result.version_id,
      title:
        current.title ||
        `${source === "mysql" ? mysqlDraft?.store || "全部店铺" : result.dataset?.name || "用户反馈数据"} · 用户语义分析`,
    }));
    setUploadOpen(false);
    onChanged();
    notify(
      source === "mysql"
        ? "数据库退货明细已导入并自动选中"
        : importNotification(result),
    );
    focusAfterPreparationRef.current = true;
    setPrepared(true);
    await refreshVersions();
  };

  return {
    changeDataEntryMode,
    dataEntryMode,
    invalidateMysql,
    mysqlDraft,
    selectedDataLabel,
    selectedReturns,
    setMysqlDraft,
    updateForm,
    upload: {
      open: uploadOpen,
      onOpen: () => setUploadOpen(true),
      onClose: () => setUploadOpen(false),
      onDone: finishImport,
      refreshError,
      refreshing: refreshingVersions,
      onRefresh: refreshVersions,
    },
  };
}
