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
  const [rows, setRows] = useState(/** @type {LegacyReviewRecord[]} */ ([]));
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [selected, setSelected] = useState(
    /** @type {LegacyReviewRecord | null} */ (null),
  );
  const [labels, setLabels] = useState(/** @type {ReviewLabel[]} */ ([]));
  const [labelCode, setLabelCode] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const loadRequest = useRef(0);

  const load = useCallback(async () => {
    const request = ++loadRequest.current;
    const values = await api.reviews(status);
    if (request !== loadRequest.current) return;
    setRows(values);
    setSelectedId((current) =>
      values.some((item) => item.id === current) ? current : (values[0]?.id ?? null),
    );
  }, [status]);
  useEffect(() => {
    load().catch((error) => notify(reviewError(error).message, "error"));
  }, [load, notify]);
  useEffect(() => {
    if (!focus) return;
    setStatus(focus.status ?? "pending");
    setSelectedId(focus.id);
  }, [focus]);
  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      return;
    }
    api
      .review(selectedId)
      .then((value) => {
        setSelected(value);
        setLabelCode(
          value.classification.primary_label_codes?.[0] ??
            value.classification.problem_label_codes?.[0] ??
            "",
        );
        setNote("");
        return api.reviewTaxonomy(value.base_result_version_id);
      })
      .then((value) => {
        if (value) setLabels(value.labels ?? []);
      })
      .catch((error) => notify(reviewError(error).message, "error"));
  }, [selectedId, notify]);

  const resolve = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      await api.resolveReview(selected.id, {
        expected_revision: selected.revision,
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
      notify(
        requestError.status === 409
          ? "该记录已被他人修改，已为你刷新"
          : requestError.message,
        "error",
      );
      if (requestError.status === 409) setSelected(await api.review(selected.id));
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
          onStatus={setStatus}
          onSelectId={setSelectedId}
        />
        <LegacyReviewWorkspace
          selected={selected}
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
