import { useCallback, useEffect, useMemo } from "react";
import { ArrowRight, ClockCounterClockwise, ListChecks } from "@phosphor-icons/react";
import Button from "antd/es/button";
import Input from "antd/es/input";

import { navigateHash } from "../../app/hashRouter";
import { Modal } from "../../components/SharedUi";
import { activeReviewBatch } from "../classification-results/resultActionPolicy";
import { AntdProvider } from "../../components/AntdProvider";
import { ResultVersionHistory } from "./ResultVersionHistory";
import { useResultVersionReview } from "./useResultVersionReview";

/** @typedef {import("../../shared/api/reviewBatchContracts").ResultVersion} ResultVersion */
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewBatch} ReviewBatch */
/** @typedef {{taskId?: string, segmentId?: string, listing?: string}} ResultReviewRouteContext */

/** @param {ResultVersion} item */
function versionId(item) {
  return item.version_id;
}

/** @param {ReviewBatch} item */
function batchId(item) {
  return item.id;
}

/**
 * @param {{latest?: ResultVersion, isLatest: boolean, draft?: ReviewBatch | null,
 *   published: boolean, onSelectVersion: (versionId: string) => void,
 *   openBatch: (batch: ReviewBatch) => void, onCreate: () => void}} props
 */
function ResultVersionActions({
  latest,
  isLatest,
  draft,
  published,
  onSelectVersion,
  openBatch,
  onCreate,
}) {
  return (
    <div className="result-version-actions">
      {!isLatest && latest ? (
        <Button
          type="primary"
          icon={<ArrowRight size={17} />}
          iconPlacement="end"
          onClick={() => onSelectVersion(versionId(latest))}
        >
          查看最新版本 v{latest.version}
        </Button>
      ) : draft ? (
        <Button
          type="primary"
          icon={<ArrowRight size={17} />}
          iconPlacement="end"
          onClick={() => openBatch(draft)}
        >
          进入复核批次
        </Button>
      ) : published ? (
        <Button type="primary" onClick={onCreate}>
          创建复核批次
        </Button>
      ) : (
        <span className="result-version-ready">当前版本尚未发布</span>
      )}
    </div>
  );
}

/**
 * @param {{result: ResultVersion, reason: string, setReason: (reason: string) => void,
 *   creating: boolean, setCreateOpen: (open: boolean) => void, createBatch: () => void}} props
 */
function ResultReviewCreateDialog({
  result,
  reason,
  setReason,
  creating,
  setCreateOpen,
  createBatch,
}) {
  return (
    <Modal
      eyebrow="创建复核批次"
      title={`基于分类结果 v${result.version} 创建批次`}
      onClose={() => !creating && setCreateOpen(false)}
    >
      <div className="review-create-modal">
        <div className="review-create-scope">
          <ListChecks size={21} />
          <p>
            批次只加入当前版本中“需复核”的分类单元。全部处理并发布后，系统会生成包含全部记录的完整新版本。
          </p>
        </div>
        <label>
          创建原因
          <Input.TextArea
            aria-describedby="review-create-reason-hint"
            rows={4}
            required
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="必填：说明为什么需要发起本次复核"
          />
        </label>
        <small id="review-create-reason-hint" className="review-create-reason-hint">
          {reason.trim()
            ? `已填写 ${reason.trim().length} 个字；该说明会随批次保留，供后续追溯。`
            : "请简要说明触发复核的原因；填写后即可创建批次。"}
        </small>
        <div className="modal-actions">
          <Button disabled={creating} onClick={() => setCreateOpen(false)}>
            取消
          </Button>
          <Button
            type="primary"
            disabled={creating || !reason.trim()}
            onClick={createBatch}
          >
            {creating ? "正在创建…" : "创建并进入批次"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/**
 * @param {{
 *   result: ResultVersion,
 *   onSelectVersion: (versionId: string) => void,
 *   notify: (message: string, type?: string) => void,
 *   requestedAction?: string,
 *   routeContext?: ResultReviewRouteContext,
 *   onActionHandled?: () => void,
 * }} props
 */
export function ResultVersionReviewPanel({
  result,
  onSelectVersion,
  notify,
  requestedAction = "",
  routeContext = {},
  onActionHandled,
}) {
  const openBatch = useCallback(
    /** @param {ReviewBatch} batch */
    (batch) => {
      navigateHash("classification-results", {
        view: "reviews",
        review_batch_id: batchId(batch),
        result_version_id: result.version_id,
        task_id: routeContext.taskId,
        segment_id: routeContext.segmentId,
        listing: routeContext.listing,
        return_to: window.location.hash.replace(/^#/, ""),
      });
    },
    [
      result.version_id,
      routeContext.listing,
      routeContext.segmentId,
      routeContext.taskId,
    ],
  );

  const {
    state,
    load,
    createOpen,
    setCreateOpen,
    reason,
    setReason,
    creating,
    createBatch,
  } = useResultVersionReview(result.version_id, notify, openBatch);

  const history = useMemo(
    () => [...state.history].sort((left, right) => left.version - right.version),
    [state.history],
  );
  const latest = history.at(-1);
  const isLatest = !latest || versionId(latest) === result.version_id;
  const draft = activeReviewBatch(state.batches);
  const published = result.publish_status === "published";

  useEffect(() => {
    if (requestedAction !== "review" || state.loading || state.error) return;
    onActionHandled?.();
    if (draft) {
      openBatch(draft);
      return;
    }
    if (published) {
      setReason("");
      setCreateOpen(true);
    }
  }, [
    draft,
    onActionHandled,
    openBatch,
    published,
    requestedAction,
    setCreateOpen,
    setReason,
    state.error,
    state.loading,
  ]);

  const ready = !state.loading && !state.error;

  const content = (
    <section className="result-version-review-panel">
      <header>
        <div>
          <ClockCounterClockwise size={21} />
          <span>
            <b>版本历史与复核</b>
            <small>每次复核发布都会生成完整的新版本，旧版本保持不变。</small>
          </span>
        </div>
        {ready && (
          <ResultVersionActions
            latest={latest}
            isLatest={isLatest}
            draft={draft}
            published={published}
            onSelectVersion={onSelectVersion}
            openBatch={openBatch}
            onCreate={() => {
              setReason("");
              setCreateOpen(true);
            }}
          />
        )}
      </header>

      <ResultVersionHistory
        history={history}
        resultVersionId={result.version_id}
        loading={state.loading}
        error={state.error}
        onReload={load}
        onSelectVersion={onSelectVersion}
      />

      {createOpen && (
        <ResultReviewCreateDialog
          result={result}
          reason={reason}
          setReason={setReason}
          creating={creating}
          setCreateOpen={setCreateOpen}
          createBatch={createBatch}
        />
      )}
    </section>
  );

  return <AntdProvider>{content}</AntdProvider>;
}
