import { useCallback, useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import "../styles/review-center.css";

import { api } from "../api";
import { PageHeading } from "../components/SharedUi";
import { LegacyReviewList } from "../features/review-batches/LegacyReviewList";
import { LegacyReviewWorkspace } from "../features/review-batches/LegacyReviewWorkspace";

/** @typedef {import("../shared/api/reviewBatchContracts").LegacyReviewRecord} LegacyReviewRecord */
/** @typedef {import("../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel */
/** @typedef {import("../shared/api/reviewBatchContracts").ReviewRequestError} ReviewRequestError */
/** @typedef {{notify: (message: string, tone?: string) => void, onChanged: () => void | Promise<void>, focus?: {kind?: "review", id: string, status?: string} | null}} ReviewCenterProps */

/** @param {unknown} error */
function reviewError(error) {
  return /** @type {ReviewRequestError} */ (
    error instanceof Error ? error : new Error("复核请求失败")
  );
}

/** @param {ReviewCenterProps} props */
export function ReviewCenter({ notify, onChanged, focus }) {
  const { mutate: mutateServerState } = useSWRConfig();
  const [status, setStatus] = useState("pending");
  const [listState, setListState] = useState({
    status: "pending",
    rows: /** @type {LegacyReviewRecord[]} */ ([]),
    loading: true,
    error: "",
  });
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [selected, setSelected] = useState(
    /** @type {LegacyReviewRecord | null} */ (null),
  );
  const [labels, setLabels] = useState(/** @type {ReviewLabel[]} */ ([]));
  const [labelCode, setLabelCode] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const loadRequest = useRef(0);
  const detailRequest = useRef(0);
  const [detailState, setDetailState] = useState({ id: "", loading: false, error: "" });
  const rows = listState.status === status ? listState.rows : [];
  const visibleSelected = selected?.id === selectedId ? selected : null;
  const detailLoading =
    Boolean(selectedId) && (detailState.id !== selectedId || detailState.loading);
  const detailError = detailState.id === selectedId ? detailState.error : "";

  const load = useCallback(async () => {
    const request = ++loadRequest.current;
    setListState((current) => ({
      status,
      rows: current.status === status ? current.rows : [],
      loading: true,
      error: "",
    }));
    try {
      const values = await api.reviews(status);
      if (request !== loadRequest.current) return;
      setListState({ status, rows: values, loading: false, error: "" });
      setSelectedId((current) =>
        values.some((item) => item.id === current) ? current : (values[0]?.id ?? null),
      );
    } catch (error) {
      if (request === loadRequest.current)
        setListState((current) => ({
          ...current,
          loading: false,
          error: reviewError(error).message,
        }));
    }
  }, [status]);
  useEffect(() => {
    load();
    return () => {
      loadRequest.current += 1;
    };
  }, [load]);
  useEffect(() => {
    if (!focus) return;
    setStatus(focus.status ?? "pending");
    setSelectedId(focus.id);
  }, [focus]);
  const loadDetail = useCallback(
    /** @param {{preserveDraft?: boolean, loadTaxonomy?: boolean}} [options] */
    async ({ preserveDraft = false, loadTaxonomy = true } = {}) => {
      if (!selectedId) return null;
      const request = ++detailRequest.current;
      setDetailState({ id: selectedId, loading: true, error: "" });
      try {
        const value = await api.review(selectedId);
        if (request !== detailRequest.current) return null;
        const taxonomy = loadTaxonomy
          ? await api.reviewTaxonomy(value.base_result_version_id)
          : null;
        if (request !== detailRequest.current) return null;
        setSelected(value);
        if (taxonomy) setLabels(taxonomy.labels ?? []);
        if (!preserveDraft) {
          setLabelCode(
            value.classification.primary_label_codes?.[0] ??
              value.classification.problem_label_codes?.[0] ??
              "",
          );
          setNote("");
        }
        setDetailState({ id: selectedId, loading: false, error: "" });
        return value;
      } catch (error) {
        if (request === detailRequest.current)
          setDetailState({
            id: selectedId,
            loading: false,
            error: reviewError(error).message,
          });
        return null;
      }
    },
    [selectedId],
  );
  useEffect(() => {
    setSelected(null);
    setLabels([]);
    setNote("");
    loadDetail();
    return () => {
      detailRequest.current += 1;
    };
  }, [loadDetail]);

  const resolve = async () => {
    if (!visibleSelected || detailLoading || detailError) return;
    setSaving(true);
    try {
      await api.resolveReview(visibleSelected.id, {
        expected_revision: visibleSelected.revision,
        label_code: labelCode || null,
        note,
      });
      notify("复核修改已写入新的结果版本");
      await load();
      await mutateServerState(
        (key) => Array.isArray(key) && key[0] === "classification-results",
        undefined,
        { revalidate: false },
      );
      onChanged();
    } catch (error) {
      const requestError = reviewError(error);
      if (requestError.status === 409) {
        const refreshed = await loadDetail({
          preserveDraft: true,
          loadTaxonomy: false,
        });
        notify(
          refreshed
            ? "该记录已被他人修改，已为你刷新"
            : "最新复核记录读取失败，输入已保留",
          "error",
        );
      } else notify(requestError.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="standard-page review-page">
      <PageHeading
        eyebrow="人工质量闸门"
        title="复核中心"
        description="所有用户可处理任意任务的待复核项；提交时使用版本号防止相互覆盖。"
      />
      <div className="review-layout">
        <LegacyReviewList
          status={status}
          rows={rows}
          selectedId={selectedId}
          loading={listState.status !== status || listState.loading}
          showLoading={!detailLoading}
          error={listState.status === status ? listState.error : ""}
          onReload={load}
          disabled={saving}
          onStatus={(value) => {
            setStatus(value);
            setSelectedId(null);
          }}
          onSelectId={setSelectedId}
        />
        <LegacyReviewWorkspace
          selected={visibleSelected}
          loading={detailLoading}
          error={detailError}
          onRetry={() => loadDetail({ preserveDraft: Boolean(visibleSelected) })}
          labels={labels}
          labelCode={labelCode}
          note={note}
          saving={saving}
          onLabelCode={setLabelCode}
          onNote={setNote}
          onResolve={resolve}
        />
      </div>
    </div>
  );
}
