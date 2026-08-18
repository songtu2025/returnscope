import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  ClockCounterClockwise,
  ListChecks,
  WarningCircle,
} from "@phosphor-icons/react";

import { api } from "../../api";
import { navigateHash } from "../../app/hashRouter";
import { EmptyState, InlineLoading, Modal } from "../../components/SharedUi";
import {
  activeReviewBatch,
  resultActionPolicy,
} from "../classification-results/resultActionPolicy";
import { formatTime } from "../../lib/presentation";

function versionId(item) {
  return item.version_id || item.id;
}

function batchId(item) {
  return item.id;
}

export function ResultVersionReviewPanel({
  result,
  onSelectVersion,
  notify,
  requestedAction = "",
  routeContext = {},
  onActionHandled,
}) {
  const [state, setState] = useState({
    loading: true,
    error: "",
    history: [],
    batches: [],
  });
  const [createOpen, setCreateOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [creating, setCreating] = useState(false);
  const generationRef = useRef(0);
  const controllerRef = useRef(null);

  const load = useCallback(async () => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const [history, batches] = await Promise.all([
        api.classificationResultVersions(result.version_id, {
          signal: controller.signal,
        }),
        api.reviewBatches(
          {
            page: 1,
            page_size: 100,
            base_result_version_id: result.version_id,
          },
          { signal: controller.signal },
        ),
      ]);
      if (generationRef.current === generation) {
        setState({
          loading: false,
          error: "",
          history: Array.isArray(history) ? history : (history.items ?? []),
          batches: batches.items ?? [],
        });
      }
    } catch (error) {
      if (generationRef.current === generation && error.name !== "AbortError") {
        setState((current) => ({ ...current, loading: false, error: error.message }));
      }
    }
  }, [result.version_id]);

  useEffect(() => {
    load();
    return () => {
      generationRef.current += 1;
      controllerRef.current?.abort();
    };
  }, [load]);

  const history = useMemo(
    () => [...state.history].sort((left, right) => left.version - right.version),
    [state.history],
  );
  const latest = history.at(-1);
  const isLatest = !latest || versionId(latest) === result.version_id;
  const draft = activeReviewBatch(state.batches);
  const policy = resultActionPolicy(result, { activeBatch: draft });

  const openBatch = useCallback(
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

  useEffect(() => {
    if (requestedAction !== "review" || state.loading || state.error) return;
    onActionHandled?.();
    if (draft) {
      openBatch(draft);
      return;
    }
    if (policy.state === "needs_review") {
      setReason("");
      setCreateOpen(true);
    }
  }, [
    draft,
    onActionHandled,
    openBatch,
    policy.state,
    requestedAction,
    state.error,
    state.loading,
  ]);

  const createBatch = async () => {
    if (!reason.trim()) return;
    setCreating(true);
    try {
      const batch = await api.createReviewBatch(result.version_id, {
        reason: reason.trim(),
      });
      notify("复核批次已创建");
      setCreateOpen(false);
      openBatch(batch);
    } catch (error) {
      if (error.status === 409) {
        try {
          const batches = await api.reviewBatches({
            page: 1,
            page_size: 100,
            base_result_version_id: result.version_id,
          });
          const draft = activeReviewBatch(batches.items ?? []);
          if (draft) {
            notify("该版本已有复核批次，已为你打开");
            setCreateOpen(false);
            openBatch(draft);
            return;
          }
        } catch (refreshError) {
          notify(refreshError.message, "error");
          return;
        }
      }
      notify(error.message, "error");
    } finally {
      setCreating(false);
    }
  };

  return (
    <section className="result-version-review-panel">
      <header>
        <div>
          <ClockCounterClockwise size={21} />
          <span>
            <b>版本历史与复核</b>
            <small>每次复核发布都会生成完整的新版本，旧版本保持不变。</small>
          </span>
        </div>
        {!state.loading && !state.error && (
          <div className="result-version-actions">
            {!isLatest && latest ? (
              <button
                className="primary-button"
                onClick={() => onSelectVersion(versionId(latest))}
              >
                查看最新版本 v{latest.version}
                <ArrowRight size={17} />
              </button>
            ) : draft ? (
              <button className="primary-button" onClick={() => openBatch(draft)}>
                进入复核批次 <ArrowRight size={17} />
              </button>
            ) : policy.state === "needs_review" ? (
              <button
                className="primary-button"
                onClick={() => {
                  setReason("");
                  setCreateOpen(true);
                }}
              >
                创建复核批次
              </button>
            ) : policy.state === "unusable" ? (
              <span className="result-version-ready">
                当前版本不可用，不能创建复核批次
              </span>
            ) : policy.state === "review-derived" ? (
              <span className="result-version-ready">复核派生版本已发布</span>
            ) : (
              <span className="result-version-ready">当前版本无需复核</span>
            )}
          </div>
        )}
      </header>

      <div className="result-version-panel-body">
        {state.loading && <InlineLoading label="正在读取版本历史…" />}
        {state.error && (
          <div className="review-batch-error" role="alert">
            <WarningCircle size={22} />
            <div>
              <b>版本历史读取失败</b>
              <p>{state.error}</p>
            </div>
            <button className="secondary-button" onClick={load}>
              重新加载
            </button>
          </div>
        )}
        {!state.loading && !state.error && history.length === 0 && (
          <EmptyState
            icon={ClockCounterClockwise}
            title="暂无版本历史"
            description="当前接口没有返回可展示的版本记录。"
          />
        )}
        {!state.error && history.length > 0 && (
          <ol className={`result-version-chain ${state.loading ? "is-loading" : ""}`}>
            {history.map((version, index) => {
              const current = versionId(version) === result.version_id;
              const parent = history.find(
                (item) => versionId(item) === version.parent_version_id,
              );
              const parentVersionNo = version.parent_version_no ?? parent?.version;
              const hasChangeSummary =
                version.parent_version_no != null &&
                version.changed_unit_count != null &&
                version.inherited_unit_count != null;
              return (
                <li key={versionId(version)} className={current ? "active" : ""}>
                  <span>{index + 1}</span>
                  <div>
                    <header>
                      <b>
                        v{version.version} ·{" "}
                        {version.version === 1 ? "原始分类" : "复核派生"}
                      </b>
                      {current && <em>当前查看</em>}
                    </header>
                    <p>
                      {parentVersionNo ? `来源 v${parentVersionNo}` : "首次发布"} ·{" "}
                      {version.created_by_name || "发布人信息未提供"}·{" "}
                      {formatTime(version.published_at || version.created_at)}
                    </p>
                    <p>{version.version_reason || "未提供发布原因"}</p>
                    {hasChangeSummary && (
                      <p>
                        基于 v{version.parent_version_no} 修改{" "}
                        {Number(version.changed_unit_count).toLocaleString()}
                        {" 个分类单元，其余 "}
                        {Number(version.inherited_unit_count).toLocaleString()}
                        {" 个沿用来源版本"}
                      </p>
                    )}
                    <small>
                      {Number(version.record_count || 0).toLocaleString()} 条记录 ·{" "}
                      {Number(version.unit_count || 0).toLocaleString()} 个分类单元
                    </small>
                    <details>
                      <summary>查看技术信息</summary>
                      <code>{versionId(version)}</code>
                      {version.created_by && (
                        <code>发布账号：{version.created_by}</code>
                      )}
                      {version.source_review_batch_id && (
                        <code>复核批次：{version.source_review_batch_id}</code>
                      )}
                    </details>
                  </div>
                  {!current && (
                    <button
                      className="secondary-button compact-button"
                      onClick={() => onSelectVersion(versionId(version))}
                    >
                      查看版本
                    </button>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>

      {createOpen && (
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
              <textarea
                aria-describedby="review-create-reason-hint"
                rows="4"
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
              <button
                className="secondary-button"
                disabled={creating}
                onClick={() => setCreateOpen(false)}
              >
                取消
              </button>
              <button
                className="primary-button"
                disabled={creating || !reason.trim()}
                onClick={createBatch}
              >
                {creating ? "正在创建…" : "创建并进入批次"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </section>
  );
}
