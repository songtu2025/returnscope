import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  CaretRight,
  CheckCircle,
  GitBranch,
  WarningCircle,
} from "@phosphor-icons/react";

import { navigateHash } from "../../app/hashRouter";
import { InlineLoading, PageHeading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { dashboardApi } from "../../shared/api/dashboardApi";
import {
  productCatalogVersionLabel,
  resultSourceVersionNumber,
} from "./dashboardFields";
import {
  clearDashboardSelection,
  readDashboardSelection,
  updateDashboardSelection,
} from "./dashboardSelectionStorage";

function itemVersionId(item) {
  return item.result_version_id || item.version_id || item.id;
}

function conflictId(conflict, index) {
  return (
    conflict.conflict_id ||
    conflict.key ||
    `${conflict.store_site}:${conflict.listing}:${index}`
  );
}

function conflictCandidates(conflict, selection, sources = []) {
  const ids = new Set(conflict.result_version_ids ?? []);
  const planned = sources.filter((item) => ids.has(item.result_version_id));
  return planned.length
    ? planned
    : (selection?.selected ?? []).filter((item) => ids.has(item.result_version_id));
}

function selectedForIds(selection, ids) {
  const allowed = new Set(ids);
  return (selection?.selected ?? []).filter((item) =>
    allowed.has(item.result_version_id),
  );
}

export function DashboardCreateFlow({ route, updateRoute, notify, userId }) {
  const [selection, setSelection] = useState(() =>
    readDashboardSelection(userId, route.selectionToken),
  );
  const [state, setState] = useState({ loading: true, error: "", plan: null });
  const [choices, setChoices] = useState({});
  const [form, setForm] = useState({ name: "", description: "", reason: "" });
  const [submitting, setSubmitting] = useState(false);
  const [confirmationMessage, setConfirmationMessage] = useState("");
  const generationRef = useRef(0);
  const controllerRef = useRef(null);

  useEffect(() => {
    setSelection(readDashboardSelection(userId, route.selectionToken));
  }, [route.selectionToken, userId]);

  const resultVersionIds = useMemo(() => {
    const resolved = selection?.resolved_result_version_ids ?? [];
    if (resolved.length) return resolved;
    return (selection?.selected ?? []).map((item) => item.result_version_id);
  }, [selection]);

  const runPreflight = useCallback(
    async (ids, nextStep = true) => {
      const generation = generationRef.current + 1;
      generationRef.current = generation;
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setState((current) => ({ ...current, loading: true, error: "" }));
      try {
        const plan = await dashboardApi.dashboardPreflight(
          { result_version_ids: ids, filters: selection?.filters ?? {} },
          { signal: controller.signal },
        );
        if (generationRef.current !== generation) return null;
        setState({ loading: false, error: "", plan });
        setConfirmationMessage("");
        if (nextStep) {
          updateRoute(
            { step: (plan.conflicts ?? []).length ? "conflicts" : "confirm" },
            { replace: true },
          );
        }
        return plan;
      } catch (error) {
        if (generationRef.current === generation && error.name !== "AbortError") {
          setState((current) => ({ ...current, loading: false, error: error.message }));
        }
        return null;
      }
    },
    [selection?.filters, updateRoute],
  );

  useEffect(() => {
    if (resultVersionIds.length === 0) {
      setState({ loading: false, error: "", plan: null });
      return undefined;
    }
    if (route.step === "check") runPreflight(resultVersionIds, true);
    return () => {
      generationRef.current += 1;
      controllerRef.current?.abort();
    };
  }, [resultVersionIds, route.step, runPreflight]);

  const conflicts = state.plan?.conflicts ?? [];
  const blockers = state.plan?.blockers ?? [];
  const warnings = state.plan?.warnings ?? [];
  const currentSources = state.plan?.sources?.length
    ? state.plan.sources
    : selectedForIds(selection, resultVersionIds);
  const summary = state.plan?.summary ?? {};
  const isVersionCreation = Boolean(selection?.target_dashboard_id);

  const resolveConflicts = async () => {
    if (conflicts.some((conflict, index) => !choices[conflictId(conflict, index)])) {
      setConfirmationMessage("请为每个冲突 Listing 选择一个结果版本。");
      return;
    }
    const candidateIds = new Set(
      conflicts.flatMap((conflict) => conflict.result_version_ids ?? []),
    );
    const resolvedIds = [
      ...resultVersionIds.filter((id) => !candidateIds.has(id)),
      ...Object.values(choices),
    ];
    const next = updateDashboardSelection(userId, route.selectionToken, (current) => ({
      ...current,
      resolved_result_version_ids: [...new Set(resolvedIds)],
    }));
    const plan = await runPreflight(next.resolved_result_version_ids, false);
    setSelection(next);
    if (plan && (plan.conflicts ?? []).length === 0) {
      updateRoute({ step: "confirm" });
    } else if (plan) {
      setConfirmationMessage("服务端仍检测到冲突，请重新选择。");
    }
  };

  const submit = async () => {
    if ((!isVersionCreation && !form.name.trim()) || !form.reason.trim()) return;
    setSubmitting(true);
    setConfirmationMessage("");
    const common = {
      result_version_ids: resultVersionIds,
      filters: selection?.filters ?? {},
      plan_hash: state.plan?.plan_hash,
      reason: form.reason.trim(),
    };
    try {
      const created = isVersionCreation
        ? await dashboardApi.createAnalysisDashboardVersion(
            selection.target_dashboard_id,
            {
              expected_revision: selection.expected_revision,
              ...common,
            },
          )
        : await dashboardApi.createAnalysisDashboard({
            name: form.name.trim(),
            description: form.description.trim(),
            ...common,
          });
      const dashboard = created.dashboard ?? created;
      const version = created.version ?? created.current_version ?? created;
      const dashboardId =
        dashboard.dashboard_id || dashboard.id || selection?.target_dashboard_id;
      const versionId =
        version.version_id || dashboard.current_version_id || created.version_id;
      if (!dashboardId || !versionId) {
        throw new Error("看板已生成，但服务端没有返回看板或版本标识");
      }
      clearDashboardSelection(userId, route.selectionToken);
      notify(isVersionCreation ? "看板新版本已生成" : "分析看板已生成");
      navigateHash("analysis-dashboards", {
        dashboard: dashboardId,
        version: versionId,
        tab: "overview",
      });
    } catch (error) {
      if (error.status === 409) {
        const [plan, latest] = await Promise.all([
          runPreflight(resultVersionIds, false),
          isVersionCreation
            ? dashboardApi
                .analysisDashboard(selection.target_dashboard_id)
                .catch(() => null)
            : Promise.resolve(null),
        ]);
        if (latest?.revision != null) {
          const next = updateDashboardSelection(
            userId,
            route.selectionToken,
            (current) => ({ ...current, expected_revision: latest.revision }),
          );
          setSelection(next);
        }
        setConfirmationMessage(
          plan
            ? "数据计划已变化，已保留你的输入并刷新计划。请核对后再次确认。"
            : "数据计划已变化，已保留你的输入。请重新检查计划后再提交。",
        );
      } else {
        setConfirmationMessage(error.message);
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (!selection || resultVersionIds.length === 0) {
    return (
      <div className="standard-page analysis-dashboard-page">
        <PageHeading
          eyebrow="生成分析看板"
          title="还没有选择分类结果"
          description="选择内容只保存在当前账号的本次浏览器会话中。"
        />
        <section className="dashboard-create-empty">
          <button
            className="primary-button"
            onClick={() => navigateHash("classification-results")}
          >
            选择分类结果
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="standard-page analysis-dashboard-page dashboard-create-page">
      <button
        className="text-button result-back-button"
        onClick={() =>
          navigateHash("classification-results", {
            selection_token: route.selectionToken,
          })
        }
      >
        <ArrowLeft size={17} /> 返回选择分类结果
      </button>
      <PageHeading
        eyebrow={isVersionCreation ? "创建看板新版本" : "生成不可变看板数据集"}
        title={isVersionCreation ? "基于新分类结果创建版本" : "创建分析看板"}
        description="流程固定为选择结果、解决 Listing 冲突、确认并生成。"
      />
      <DashboardCreateSteps step={route.step} />

      {state.loading && <InlineLoading label="正在检查分类结果与 Listing 冲突…" />}
      {state.error && (
        <section className="dashboard-error" role="alert">
          <b>执行计划检查失败</b>
          <span>{state.error}</span>
          <button
            className="secondary-button"
            onClick={() => runPreflight(resultVersionIds)}
          >
            重新检查
          </button>
        </section>
      )}

      {!state.loading && !state.error && route.step === "conflicts" && (
        <section className="dashboard-conflict-page">
          <header>
            <div>
              <WarningCircle size={24} />
              <span>
                <b>同一 Listing 选择了多个结果版本</b>
                <small>系统不会自动取最新版，请逐组确认要用于看板的数据。</small>
              </span>
            </div>
          </header>
          <div className="dashboard-conflict-list">
            {conflicts.map((conflict, index) => {
              const id = conflictId(conflict, index);
              return (
                <fieldset key={id}>
                  <legend>
                    {conflict.store_site || "未提供店铺/站点"} ·{" "}
                    {conflict.listing || "未提供 Listing"}
                  </legend>
                  {conflictCandidates(conflict, selection, state.plan?.sources).map(
                    (candidate) => {
                      const versionId = itemVersionId(candidate);
                      const hasProductVersion =
                        candidate.product_dataset_name &&
                        candidate.product_version != null;
                      return (
                        <label key={versionId}>
                          <input
                            type="radio"
                            name={id}
                            value={versionId}
                            checked={choices[id] === versionId}
                            onChange={() => setChoices({ ...choices, [id]: versionId })}
                          />
                          <span>
                            <b>结果 v{resultSourceVersionNumber(candidate) ?? "-"}</b>
                            <small>
                              {hasProductVersion
                                ? `产品信息：${candidate.product_dataset_name} · v${candidate.product_version}`
                                : "产品信息版本未记录"}
                            </small>
                            <small>
                              {Number(candidate.record_count || 0).toLocaleString()}{" "}
                              条记录 · {formatTime(candidate.published_at)}
                            </small>
                          </span>
                        </label>
                      );
                    },
                  )}
                </fieldset>
              );
            })}
          </div>
          {confirmationMessage && (
            <p className="dashboard-form-error">{confirmationMessage}</p>
          )}
          <footer>
            <button className="primary-button" onClick={resolveConflicts}>
              确认冲突选择 <CaretRight size={17} />
            </button>
          </footer>
        </section>
      )}

      {!state.loading && !state.error && route.step === "confirm" && (
        <section className="dashboard-confirm-page">
          <div className="dashboard-confirm-main">
            <header>
              <CheckCircle size={24} />
              <div>
                <b>执行计划已生成</b>
                <span>请核对每个 Listing 使用的结果版本，再生成不可变数据集。</span>
              </div>
            </header>
            {blockers.length > 0 && (
              <div className="dashboard-blockers" role="alert">
                <b>仍有阻断项</b>
                {blockers.map((blocker, index) => (
                  <span key={blocker.type || index}>
                    {blocker.message || String(blocker)}
                  </span>
                ))}
              </div>
            )}
            {warnings.length > 0 && (
              <div className="dashboard-warnings" role="status">
                <b>当前看板将按可用范围生成</b>
                {warnings.map((warning, index) => (
                  <span key={warning.type || index}>
                    {warning.message || String(warning)}
                  </span>
                ))}
              </div>
            )}
            <div className="dashboard-source-mapping">
              <div className="dashboard-source-head">
                <span>店铺/站点</span>
                <span>Listing</span>
                <span>结果版本</span>
                <span>产品信息版本</span>
                <span>记录数</span>
                <span>发布时间</span>
              </div>
              {currentSources.map((source) => (
                <div key={itemVersionId(source)}>
                  <span>{source.store_site || "未提供"}</span>
                  <b>{source.listing || "未提供"}</b>
                  <span>v{resultSourceVersionNumber(source) ?? "-"}</span>
                  <span title={productCatalogVersionLabel(source)}>
                    {productCatalogVersionLabel(source)}
                  </span>
                  <span>{Number(source.record_count || 0).toLocaleString()}</span>
                  <span>{formatTime(source.published_at)}</span>
                </div>
              ))}
            </div>
          </div>
          <aside className="dashboard-confirm-aside">
            <div className="dashboard-plan-stats">
              <span>
                结果版本
                <b>{summary.source_count ?? resultVersionIds.length}</b>
              </span>
              <span>
                Listing
                <b>{summary.listing_count ?? currentSources.length}</b>
              </span>
              <span>
                记录
                <b>
                  {summary.record_count == null
                    ? "暂无统计"
                    : Number(summary.record_count).toLocaleString()}
                </b>
              </span>
            </div>
            {summary.total_record_count != null &&
              Number(summary.total_record_count) !== Number(summary.record_count) && (
                <div className="dashboard-coverage-note" role="status">
                  <b>
                    纳入 {Number(summary.record_count || 0).toLocaleString()} /{" "}
                    {Number(summary.total_record_count || 0).toLocaleString()} 条记录
                  </b>
                  <span>
                    待复核{" "}
                    {Number(summary.pending_review_record_count || 0).toLocaleString()}{" "}
                    条；已排除{" "}
                    {Number(summary.excluded_record_count || 0).toLocaleString()} 条。
                  </span>
                </div>
              )}
            {!isVersionCreation && (
              <>
                <label>
                  看板名称
                  <input
                    required
                    value={form.name}
                    onChange={(event) => setForm({ ...form, name: event.target.value })}
                    placeholder="例如：美国站水鞋退货问题"
                  />
                </label>
                <label>
                  看板说明
                  <textarea
                    rows="3"
                    value={form.description}
                    onChange={(event) =>
                      setForm({ ...form, description: event.target.value })
                    }
                    placeholder="可选：说明使用场景"
                  />
                </label>
              </>
            )}
            <label>
              {isVersionCreation ? "版本原因" : "生成原因"}
              <textarea
                rows="3"
                required
                value={form.reason}
                onChange={(event) => setForm({ ...form, reason: event.target.value })}
                placeholder="必填：说明为什么生成本次看板数据集"
              />
            </label>
            <div className="dashboard-lineage-note">
              <GitBranch size={19} />
              <span>
                {isVersionCreation
                  ? "新版本会保留旧版本，历史看板不会自动漂移。"
                  : "生成后固化数据来源，后续分类结果变化不会影响当前版本。"}
              </span>
            </div>
            {confirmationMessage && (
              <p className="dashboard-form-error" role="alert">
                {confirmationMessage}
              </p>
            )}
            <button
              className="primary-button dashboard-submit-button"
              disabled={
                submitting ||
                blockers.length > 0 ||
                state.plan?.ready !== true ||
                !form.reason.trim() ||
                (!isVersionCreation && !form.name.trim()) ||
                !state.plan?.plan_hash
              }
              onClick={submit}
            >
              {submitting
                ? "正在生成…"
                : isVersionCreation
                  ? "确认生成新版本"
                  : "确认生成分析看板"}
            </button>
          </aside>
        </section>
      )}
    </div>
  );
}

function DashboardCreateSteps({ step }) {
  const active = step === "conflicts" ? 2 : step === "confirm" ? 3 : 1;
  return (
    <ol className="dashboard-create-steps" aria-label="看板生成步骤">
      {["选择分类结果", "解决版本冲突", "确认并生成"].map((label, index) => (
        <li key={label} className={active >= index + 1 ? "active" : ""}>
          <span>{index + 1}</span>
          {label}
        </li>
      ))}
    </ol>
  );
}
