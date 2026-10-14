import { useState } from "react";
import { api } from "../../api";

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRow} DatasetRow */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRecord} DatasetRecord */
export const PRODUCT_EDIT_FIELDS = [
  "MSKU",
  "店铺/站点",
  "Listing",
  "产品名称",
  "品类A",
  "品类B",
];

/** @param {{dataset: DatasetRecord, notify: (message: string, tone?: string) => void, onChanged: (dataset: DatasetRecord) => void}} props */
export function useProductRowEditing({ dataset, notify, onChanged }) {
  const [editing, setEditing] = useState(/** @type {DatasetRow | null} */ (null));
  const [original, setOriginal] = useState(/** @type {DatasetRow | null} */ (null));
  const [version, setVersion] = useState(dataset.current_version);
  const [saving, setSaving] = useState(false);
  const [changeNote, setChangeNote] = useState("");
  const [conflict, setConflict] = useState(false);
  const [latest, setLatest] = useState(
    /** @type {{row: DatasetRow, dataset: DatasetRecord} | null} */ (null),
  );
  const [error, setError] = useState("");
  const [confirmClose, setConfirmClose] = useState(false);
  const dirty = Boolean(
    changeNote || PRODUCT_EDIT_FIELDS.some((key) => editing?.[key] !== original?.[key]),
  );
  const close = () => {
    if (saving) return;
    if (dirty) setConfirmClose(true);
    else setEditing(null);
  };
  const loadLatest = async () => {
    if (!original) return;
    setSaving(true);
    setError("");
    try {
      const current = await api.dataset(dataset.id, { include: "" });
      const rows = await api.datasetRows(dataset.id, original.MSKU, 0, 100, {
        store: original["店铺/站点"],
        version: current.current_version,
      });
      const matches = rows.records.filter(
        (row) =>
          row.MSKU === original.MSKU && row["店铺/站点"] === original["店铺/站点"],
      );
      if (matches.length !== 1)
        throw new Error("最新资料中无法唯一定位此产品，输入已保留，请核对产品标识。");
      setLatest({ row: matches[0], dataset: current });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "最新资料读取失败，请重试");
    } finally {
      setSaving(false);
    }
  };
  const acceptLatest = () => {
    if (!latest || !editing || !original) return;
    const merged = { ...latest.row };
    // 只叠加用户修改过的字段，保留其他人更新的字段。
    PRODUCT_EDIT_FIELDS.forEach((key) => {
      if (editing[key] !== original[key]) merged[key] = editing[key];
    });
    setEditing(merged);
    setOriginal(latest.row);
    setVersion(latest.dataset.current_version);
    onChanged(latest.dataset);
    setConflict(false);
    setLatest(null);
    setError("");
  };
  const save = async (
    /** @type {import("react").FormEvent<HTMLFormElement>} */ event,
  ) => {
    event.preventDefault();
    if (!editing || saving || conflict) return;
    setSaving(true);
    setError("");
    try {
      const changes = Object.fromEntries(
        PRODUCT_EDIT_FIELDS.filter((key) => editing[key] !== undefined).map((key) => [
          key,
          editing[key],
        ]),
      );
      const updated = await api.updateDatasetRow(dataset.id, {
        row_index: editing._row_index,
        expected_version: version,
        changes,
        change_note: changeNote,
      });
      setEditing(null);
      onChanged(updated);
      notify("产品信息已更新");
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : "请求失败";
      if (failure instanceof Error && "status" in failure && failure.status === 409) {
        setConflict(true);
        setLatest(null);
        setError("数据已更新，输入已保留。请读取最新资料并核对后保存。");
      } else {
        setError(message);
        notify(message, "error");
      }
    } finally {
      setSaving(false);
    }
  };
  return {
    editing,
    setEditing,
    changeNote,
    setChangeNote,
    saving,
    conflict,
    latest,
    error,
    confirmClose,
    close,
    save,
    loadLatest,
    acceptLatest,
    continueEditing: () => setConfirmClose(false),
    discard: () => {
      if (!saving) {
        setConfirmClose(false);
        setEditing(null);
      }
    },
    open: (/** @type {DatasetRow} */ row) => {
      setOriginal(row);
      setEditing(row);
      setVersion(dataset.current_version);
      setChangeNote("");
      setConflict(false);
      setLatest(null);
      setError("");
      setConfirmClose(false);
    },
  };
}
