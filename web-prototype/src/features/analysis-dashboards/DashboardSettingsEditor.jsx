import { useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { UnsavedChangesDialog } from "../../components/UnsavedChangesActions";
import { useUnsavedNavigation } from "../../hooks/useUnsavedNavigation";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { useClassificationResultListData } from "../classification-results/useClassificationResultListData";
import { DashboardQualityScope } from "./DashboardQualityScope";
import { errorMessage } from "./dashboardRequestErrors";
import "../../styles/dashboard-settings.css";

/** @param {string} name @param {string[]} ids @param {string[]} statuses @param {Record<string, string | string[] | null>} filters */
function settingsKey(name, ids, statuses, filters) {
  return JSON.stringify([
    name.trim(),
    [...ids].sort(),
    [...statuses].sort(),
    filters.date_from || "",
    filters.date_to || "",
  ]);
}

/** @param {{dashboard: import("./analysisDashboardContracts").Dashboard, onClose: () => void, onSaved: (id: string) => void | Promise<void>}} props */
export function DashboardSettingsEditor({ dashboard, onClose, onSaved }) {
  const [name, setName] = useState(dashboard.name ?? "");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [ids, setIds] = useState(/** @type {string[]} */ ([]));
  const [sources, setSources] = useState(
    /** @type {import("./analysisDashboardContracts").DashboardSource[]} */ ([]),
  );
  const [statuses, setStatuses] = useState(/** @type {string[]} */ (["ready"]));
  const [filters, setFilters] = useState(
    /** @type {Record<string, string | string[] | null>} */ ({}),
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const formRef = useRef(/** @type {HTMLFormElement | null} */ (null));
  const leavingRef = useRef(false);
  const [baseline, setBaseline] = useState(() =>
    settingsKey(dashboard.name ?? "", [], ["ready"], {}),
  );
  const draftKey = settingsKey(name, ids, statuses, filters);
  const dirty = draftKey !== baseline;
  const resultQuery = useMemo(() => ({ page, page_size: 20, q: query }), [page, query]);
  const resultState = useClassificationResultListData(resultQuery);
  useEffect(() => {
    let active = true;
    dashboardApi
      .analysisDashboardSources(dashboard.id, dashboard.current_version_id ?? "")
      .then(
        (
          /** @type {import("./analysisDashboardContracts").DashboardSource[]} */ sources,
        ) => {
          if (!active) return;
          setSources(sources);
          const sourceIds = sources
            .map((source) => source.result_version_id)
            .filter((id) => typeof id === "string");
          setIds(sourceIds);
          const currentFilters = dashboard.version?.filters ?? {};
          setFilters(currentFilters);
          const quality = currentFilters.quality_status;
          setStatuses(Array.isArray(quality) ? quality : ["ready"]);
          setBaseline(
            settingsKey(
              dashboard.name ?? "",
              sourceIds,
              Array.isArray(quality) ? quality : ["ready"],
              currentFilters,
            ),
          );
          setLoading(false);
        },
      )
      .catch((failure) => {
        if (active) {
          setError(errorMessage(failure));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [dashboard]);
  const save = async (complete = true) => {
    if (loading || saving || !ids.length || !formRef.current?.reportValidity())
      return false;
    setSaving(true);
    setError("");
    try {
      const selectedFilters = { ...filters, quality_status: statuses };
      const plan = await dashboardApi.dashboardPreflight({
        result_version_ids: ids,
        filters: selectedFilters,
      });
      if (plan.conflicts?.length)
        throw new Error("同一 Listing 存在多个来源结果，请只保留一个");
      const updated = await dashboardApi.updateAnalysisDashboard(dashboard.id, {
        name: name.trim(),
        expected_revision: dashboard.revision,
        result_version_ids: ids,
        filters: selectedFilters,
        plan_hash: plan.plan_hash,
        reason: "修改看板设置",
      });
      const leaving = !complete || leavingRef.current;
      // 已保存的内容不再拦截成功跳转，也不覆盖用户已确认的离页目标。
      flushSync(() => {
        setBaseline(draftKey);
        setSaving(false);
      });
      if (leaving) onClose();
      else await onSaved(updated.current_version_id);
      return true;
    } catch (failure) {
      setError(errorMessage(failure));
      return false;
    } finally {
      setSaving(false);
    }
  };
  const exit = useUnsavedNavigation({
    dirty,
    busy: dirty && saving,
    canSave: !loading && Boolean(ids.length),
    save: () => save(false),
    discard: onClose,
    onRequest: () => {
      leavingRef.current = true;
    },
  });
  useEffect(() => {
    if (!exit.pendingExit) leavingRef.current = false;
  }, [exit.pendingExit]);
  return (
    <section className="content-card dashboard-settings-editor">
      <h2>编辑看板</h2>
      <form
        ref={formRef}
        className="dashboard-settings-form"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <fieldset className="dashboard-settings-fields" disabled={loading || saving}>
          <label>
            看板名称
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={120}
            />
          </label>
          <label>
            搜索来源结果
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
            />
          </label>
          <p>已选择 {ids.length} 个来源</p>
          {sources
            .filter(
              (source) =>
                source.result_version_id && ids.includes(source.result_version_id),
            )
            .map((source) => (
              <div key={source.result_version_id}>
                {source.store_site} · {source.listing}
                <button
                  className="text-button"
                  type="button"
                  onClick={() =>
                    setIds(ids.filter((id) => id !== source.result_version_id))
                  }
                >
                  移除此来源
                </button>
              </div>
            ))}
          <div className="dashboard-settings-source-list">
            {resultState.data?.items.map((item) => (
              <label key={item.version_id}>
                <input
                  type="checkbox"
                  checked={ids.includes(item.version_id)}
                  onChange={(event) =>
                    setIds(
                      event.target.checked
                        ? [...ids, item.version_id]
                        : ids.filter((id) => id !== item.version_id),
                    )
                  }
                />
                {item.store_site} · {item.listing} · v
                {String(item.version_no ?? item.version ?? "")}
              </label>
            ))}
          </div>
          <div className="modal-actions">
            <button
              className="secondary-button"
              type="button"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              上一页
            </button>
            <button
              className="secondary-button"
              type="button"
              disabled={page * 20 >= (resultState.data?.total ?? 0)}
              onClick={() => setPage(page + 1)}
            >
              下一页
            </button>
          </div>
          <DashboardQualityScope statuses={statuses} onChange={setStatuses} />
          <label>
            反馈开始日期
            <input
              type="date"
              value={String(filters.date_from ?? "")}
              onChange={(event) =>
                setFilters({ ...filters, date_from: event.target.value || null })
              }
            />
          </label>
          <label>
            反馈结束日期
            <input
              type="date"
              value={String(filters.date_to ?? "")}
              onChange={(event) =>
                setFilters({ ...filters, date_to: event.target.value || null })
              }
            />
          </label>
        </fieldset>
        {error && <p role="alert">{error}</p>}
        {resultState.error && (
          <p role="alert">
            来源结果读取失败：{resultState.error}
            <button type="button" onClick={() => void resultState.load()}>
              重试
            </button>
          </p>
        )}
        <div className="modal-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={saving}
            onClick={onClose}
          >
            取消编辑
          </button>
          <button
            className="primary-button"
            disabled={loading || saving || !ids.length}
          >
            {saving ? "保存中…" : "保存修改"}
          </button>
        </div>
      </form>
      <UnsavedChangesDialog guard={exit} title="看板修改尚未保存" />
    </section>
  );
}
