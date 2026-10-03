import { useState } from "react";
import { navigateHash } from "../../app/hashRouter";
import { reviewBatchApi } from "../../shared/api/reviewBatchApi";
import { resultRouteQuery } from "./reviewBatchRoute";
import { requestError } from "./reviewRecordDrafts";

/** @param {import("./reviewWorkspaceContracts").ReviewEditingInput} input */
export function useReviewPublication({ route, notify, batch, pending, loadBatch }) {
  const [publishOpen, setPublishOpen] = useState(false);
  const [publishReason, setPublishReason] = useState("");
  const [publishError, setPublishError] = useState("");
  const [publishing, setPublishing] = useState(false);

  const publish = async () => {
    if (!batch || pending > 0 || !publishReason.trim()) return;
    setPublishing(true);
    setPublishError("");
    try {
      const derived = await reviewBatchApi.publishReviewBatch(route.batchId, {
        expected_revision: batch.revision,
        reason: publishReason.trim(),
      });
      setPublishOpen(false);
      notify(`分类结果 v${derived.version} 已发布`);
      navigateHash(
        "classification-results",
        resultRouteQuery(route, derived.version_id, "history"),
      );
    } catch (error) {
      const failure = requestError(error);
      if (failure.status === 409) {
        setPublishError(`${failure.message}。已刷新批次，请重新确认后发布。`);
        try {
          await loadBatch();
        } catch {
          // 批次读取错误已由页面状态展示。
        }
      } else {
        setPublishError(failure.message);
      }
    } finally {
      setPublishing(false);
    }
  };
  return {
    publishOpen,
    setPublishOpen,
    publishReason,
    setPublishReason,
    publishError,
    setPublishError,
    publishing,
    publish,
  };
}
