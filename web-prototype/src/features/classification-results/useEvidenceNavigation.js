import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { resultRecordQuery } from "./classificationResultReads";

/** @typedef {import("./classificationResultDetailContracts").ClassificationResultGroup} Group */
/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} Route */
/** @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultGroupsResponse} Groups */
/** @param {{route: Route, records: Groups|null, group: Group|null, setGroup: import("react").Dispatch<import("react").SetStateAction<Group|null>>, updateRoute: (changes: Partial<Route>) => void, notify: (message: string, tone?: string) => void}} props */
export function useEvidenceNavigation({
  route,
  records,
  group,
  setGroup,
  updateRoute,
  notify,
}) {
  const [position, setPosition] = useState(0);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [savedVersion, setSavedVersion] = useState("");
  const retryRef = useRef(/** @type {(() => Promise<void>) | null} */ (null));
  const requestRef = useRef(0);
  useEffect(
    () => () => {
      requestRef.current += 1;
    },
    [],
  );
  useEffect(() => {
    if (!group) {
      requestRef.current += 1;
      setBusy(false);
      return;
    }
    if (
      group &&
      route.version !== group.record.result_version_id &&
      route.version !== savedVersion
    ) {
      requestRef.current += 1;
      setBusy(false);
      setGroup(null);
    }
  }, [route.version, group, savedVersion, setGroup]);
  const open = (/** @type {Group} */ selected) => {
    const index =
      records?.items.findIndex(
        (item) => item.record.source_record_id === selected.record.source_record_id,
      ) ?? 0;
    setPosition((route.recordPage - 1) * route.pageSize + Math.max(index, 0));
    setTotal(records?.total ?? 0);
    setSavedVersion("");
    setError("");
    setGroup(selected);
  };
  const close = () => {
    requestRef.current += 1;
    setGroup(null);
    setError("");
    setBusy(false);
    setSavedVersion("");
  };
  const select = async (
    /** @type {string} */ version,
    /** @type {number} */ ordinal,
    /** @type {number} */ request,
  ) => {
    const page = Math.floor(ordinal / route.pageSize) + 1;
    const values = await api.classificationResultRecordGroups(version, {
      ...resultRecordQuery(route),
      page,
    });
    if (request !== requestRef.current) return;
    setTotal(values.total);
    const selected = values.items[ordinal % route.pageSize];
    if (!selected) {
      close();
      updateRoute({
        version,
        recordPage: Math.max(1, Math.ceil(values.total / route.pageSize)),
      });
      notify("当前筛选范围已没有下一条反馈");
      return;
    }
    setGroup(selected);
    setPosition(ordinal);
    setSavedVersion("");
    updateRoute({ version, recordPage: page });
  };
  const run = async (
    /** @type {(request: number) => Promise<void>} */ operation,
    /** @type {boolean} */ saved = false,
  ) => {
    const request = ++requestRef.current;
    setBusy(true);
    setError("");
    retryRef.current = () => run(operation, saved);
    try {
      await operation(request);
    } catch (failure) {
      if (request !== requestRef.current) return;
      const message = failure instanceof Error ? failure.message : "读取失败";
      setError(`${saved ? "修正已保存，下一条读取失败" : "反馈读取失败"}：${message}`);
    } finally {
      if (request === requestRef.current) setBusy(false);
    }
  };
  const move = (/** @type {number} */ direction) => {
    if (
      busy ||
      savedVersion ||
      position + direction < 0 ||
      position + direction >= total
    )
      return;
    return run((request) => select(route.version, position + direction, request));
  };
  const saved = async (/** @type {string} */ version, advance = false) => {
    const filtered =
      ["review_required", "unusable", "excluded"].includes(route.recordQualityStatus) ||
      route.systemRerunRequired === "true" ||
      Boolean(route.commentStatus);
    notify(
      filtered
        ? "人工修正已保存，无需重跑；记录可能已移出当前筛选。"
        : "人工修正已保存，无需重跑",
    );
    if (!advance || !group) {
      close();
      updateRoute({ version });
      return;
    }
    const source = group.record.source_record_id;
    setSavedVersion(version);
    updateRoute({ version });
    await run(async (request) => {
      const match = await api.classificationResultRecordGroups(version, {
        ...resultRecordQuery(route),
        page: 1,
        page_size: 1,
        feedback_source_record_id: source,
      });
      if (request !== requestRef.current) return;
      // 保存后若移出筛选，下一条占据原位置，不能额外跳过一条。
      await select(version, position + (match.total ? 1 : 0), request);
    }, true);
  };
  return {
    position,
    total,
    busy,
    error,
    locked: Boolean(savedVersion),
    open,
    close,
    move,
    saved,
    retry: () => retryRef.current?.(),
  };
}
