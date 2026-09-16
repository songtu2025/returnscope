import { useState } from "react";

import { api } from "../../api";
import { importNotification, importSelectionLabel } from "./newTaskPolicy";

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
  const [mysqlDraft, setMysqlDraft] = useState(draft?.mysqlDraft);
  const [dataEntryMode, setDataEntryMode] = useState(
    draft?.dataEntryMode ?? (draft?.form?.dataset_version_id ? "existing" : "mysql"),
  );
  const [selectedDataLabel, setSelectedDataLabel] = useState(
    draft?.selectedDataLabel ?? "",
  );

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
