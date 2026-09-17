import { useState } from "react";

import { api } from "../../api";
import { importNotification, importSelectionLabel } from "./newTaskPolicy";

/** @typedef {import("./taskCreateContracts").DataVersion} DataVersion */
/** @typedef {import("./taskCreateContracts").ReturnImportResult} ReturnImportResult */
/** @typedef {import("./taskCreateContracts").TaskDraft} TaskDraft */
/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/** @typedef {import("./MysqlReturnImportForm").MysqlReturnFormState} MysqlReturnFormState */
/**
 * @param {{draft?: TaskDraft | null, focusAfterPreparationRef: import("react").MutableRefObject<boolean>, invalidatePreflight: () => void, notify: (message: string, type?: "success" | "error") => void, onChanged: () => void | Promise<unknown>, setForm: import("react").Dispatch<import("react").SetStateAction<TaskForm>>, setPrepared: import("react").Dispatch<import("react").SetStateAction<boolean>>, setVersions: import("react").Dispatch<import("react").SetStateAction<DataVersion[]>>}} options
 */

export function useTaskImport({
  draft,
  focusAfterPreparationRef,
  invalidatePreflight,
  notify,
  onChanged,
  setForm,
  setPrepared,
  setVersions,
}) {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [mysqlDraft, setMysqlDraft] = useState(
    /** @type {Partial<MysqlReturnFormState> | undefined} */ (draft?.mysqlDraft),
  );
  const [dataEntryMode, setDataEntryMode] = useState(
    draft?.dataEntryMode ?? (draft?.form?.dataset_version_id ? "existing" : "mysql"),
  );
  const [selectedDataLabel, setSelectedDataLabel] = useState(
    draft?.selectedDataLabel ?? "",
  );

  /**
   * @param {ReturnImportResult} result
   * @param {"mysql" | "upload"} source
   */
  const finishImport = async (result, source) => {
    setVersions(await api.dataVersions());
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
        `${source === "mysql" ? mysqlDraft?.store || "全部店铺" : "退货数据"} · 退货分析`,
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
  };

  return {
    dataEntryMode,
    finishImport,
    mysqlDraft,
    selectedDataLabel,
    setDataEntryMode,
    setMysqlDraft,
    setSelectedDataLabel,
    setUploadOpen,
    uploadOpen,
  };
}
