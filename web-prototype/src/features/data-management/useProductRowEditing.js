import { useRef, useState } from "react";
import { api } from "../../api";
import { useUnsavedNavigation } from "../../hooks/useUnsavedNavigation";

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
  const saveLock = useRef(false);
  const formRef = useRef(/** @type {HTMLFormElement | null} */ (null));
  const [changeNote, setChangeNote] = useState("");
  const [conflict, setConflict] = useState(false);
  const [latest, setLatest] = useState(
    /** @type {{row: DatasetRow, dataset: DatasetRecord} | null} */ (null),
  );
  const [error, setError] = useState("");
  const [followingRows, setFollowingRows] = useState(/** @type {DatasetRow[]} */ ([]));
  const [resolutions, setResolutions] = useState(
    /** @type {Record<string, {choice: "mine" | "latest", value: unknown}>} */ ({}),
  );
  const conflictFields =
    latest && original && editing
      ? PRODUCT_EDIT_FIELDS.filter(
          (key) =>
            editing[key] !== original[key] &&
            latest.row[key] !== original[key] &&
            editing[key] !== latest.row[key],
        )
      : [];
  const unresolved = conflictFields.filter(
    (key) => !resolutions[key] || resolutions[key].value !== editing?.[key],
  );
  const [confirmClose, setConfirmClose] = useState(false);
  const dirty = Boolean(
    editing &&
    (changeNote || PRODUCT_EDIT_FIELDS.some((key) => editing[key] !== original?.[key])),
  );
  const close = () => {
    if (saving) return;
    if (dirty) setConfirmClose(true);
    else setEditing(null);
  };
  const readCurrentRow = async (/** @type {DatasetRow} */ identity) => {
    const current = await api.dataset(dataset.id, { include: "" });
    const rows = await api.datasetRows(dataset.id, identity.MSKU, 0, 100, {
      store: identity["店铺/站点"],
      version: current.current_version,
    });
    const matches = rows.records.filter(
      (row) => row.MSKU === identity.MSKU && row["店铺/站点"] === identity["店铺/站点"],
    );
    if (matches.length !== 1)
      throw new Error("最新资料中无法唯一定位此产品，请核对产品标识。");
    return { row: matches[0], dataset: current };
  };
  const loadLatest = async () => {
    if (!original) return;
    setLatest(null);
    setResolutions({});
    setSaving(true);
    setError("");
    try {
      setLatest(await readCurrentRow(original));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "最新资料读取失败，请重试");
    } finally {
      setSaving(false);
    }
  };
  const startEditing = (
    /** @type {DatasetRow} */ row,
    /** @type {number} */ currentVersion,
  ) => {
    setResolutions({});
    setOriginal(row);
    setEditing(row);
    setVersion(currentVersion);
    setChangeNote("");
    setConflict(false);
    setLatest(null);
    setError("");
    setConfirmClose(false);
  };
  const editNext = async () => {
    try {
      const current = await readCurrentRow(followingRows[0]);
      startEditing(current.row, current.dataset.current_version);
      setFollowingRows((rows) => rows.slice(1));
      onChanged(current.dataset);
    } catch (failure) {
      setEditing(null);
      notify(
        `当前产品已保存，下一条读取失败：${failure instanceof Error ? failure.message : "请在列表中重新打开下一条"}`,
        "error",
      );
    }
  };
  const acceptLatest = () => {
    if (!latest || !editing || !original || unresolved.length) return;
    const merged = { ...latest.row };
    // 单方改动自动合并，双方修改同一字段时必须使用用户明确选择的值。
    PRODUCT_EDIT_FIELDS.forEach((key) => {
      if (
        editing[key] !== original[key] &&
        (!conflictFields.includes(key) || resolutions[key].choice === "mine")
      )
        merged[key] = editing[key];
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
    /** @type {import("react").FormEvent<HTMLFormElement> | undefined} */ event,
    advance = false,
  ) => {
    event?.preventDefault();
    if (!editing || saving || saveLock.current || conflict) return false;
    saveLock.current = true;
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
      onChanged(updated);
      notify("产品信息已更新");
      if (advance && followingRows.length) await editNext();
      else setEditing(null);
      return true;
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
      return false;
    } finally {
      saveLock.current = false;
      setSaving(false);
    }
  };
  const discard = () => {
    if (!saving) {
      setConfirmClose(false);
      setEditing(null);
    }
  };
  const navigationExit = useUnsavedNavigation({
    dirty,
    busy: saving,
    discard,
    canSave: !conflict,
    onRequest: () => setConfirmClose(false),
    save: async () => (formRef.current?.reportValidity() ? save(undefined) : false),
  });
  return {
    formRef,
    navigationExit,
    editing,
    setEditing,
    changeNote,
    setChangeNote,
    saving,
    dirty,
    conflict,
    latest,
    original,
    conflictFields,
    unresolved,
    resolutions,
    resolveField: (
      /** @type {string} */ key,
      /** @type {"mine" | "latest"} */ choice,
    ) => {
      setResolutions((current) => ({
        ...current,
        [key]: { choice, value: editing?.[key] },
      }));
    },
    error,
    confirmClose,
    close,
    save,
    hasNext: followingRows.length > 0,
    saveNext: async () =>
      formRef.current?.reportValidity() ? save(undefined, true) : false,
    loadLatest,
    acceptLatest,
    continueEditing: () => setConfirmClose(false),
    discard,
    open: (
      /** @type {DatasetRow} */ row,
      /** @type {DatasetRow[]} */ pageRows = [],
    ) => {
      const index = pageRows.findIndex((item) => item._row_index === row._row_index);
      setFollowingRows(index < 0 ? [] : pageRows.slice(index + 1));
      startEditing(row, dataset.current_version);
    },
  };
}
