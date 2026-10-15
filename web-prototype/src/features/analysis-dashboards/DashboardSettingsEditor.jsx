import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { UnsavedChangesDialog } from "../../components/UnsavedChangesActions";
import { useUnsavedNavigation } from "../../hooks/useUnsavedNavigation";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { DashboardQualityScope } from "./DashboardQualityScope";
import { DashboardSourceSelector } from "./DashboardSourceSelector";
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
  const [sources, setSources] = useState(
    /** @type {import("./analysisDashboardContracts").DashboardSource[]} */ ([]),
  );
  const originalFilters = dashboard.version?.filters ?? {};
  const originalQuality = originalFilters.quality_status;
  const originalStatuses = Array.isArray(originalQuality) ? originalQuality : ["ready"];
  const [statuses, setStatuses] = useState(originalStatuses);
  const [filters, setFilters] = useState(originalFilters);
  const [loading, setLoading] = useState(true);
  const [sourcesLoaded, setSourcesLoaded] = useState(false);
  const [sourceError, setSourceError] = useState("");
  const [sourceAttempt, setSourceAttempt] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const formRef = useRef(/** @type {HTMLFormElement | null} */ (null));
  const leavingRef = useRef(false);
  const [baseline, setBaseline] = useState(() =>
    settingsKey(dashboard.name ?? "", [], originalStatuses, originalFilters),
  );
  const ids = sources
    .map((source) => source.result_version_id)
    .filter((id) => typeof id === "string");
  const draftKey = settingsKey(name, ids, statuses, filters);
  const dirty = draftKey !== baseline;
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
          const currentFilters = dashboard.version?.filters ?? {};
          const quality = currentFilters.quality_status;
          setBaseline(
            settingsKey(
              dashboard.name ?? "",
              sourceIds,
              Array.isArray(quality) ? quality : ["ready"],
              currentFilters,
            ),
          );
          setSourcesLoaded(true);
          setLoading(false);
        },
      )
      .catch((failure) => {
        if (active) {
          setSourceError(errorMessage(failure));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [dashboard, sourceAttempt]);
  const save = async (complete = true) => {
    if (
      !sourcesLoaded ||
      loading ||
      saving ||
      !ids.length ||
      !formRef.current?.reportValidity()
    )
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
    canSave: sourcesLoaded && !loading && Boolean(ids.length),
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
        <fieldset className="dashboard-settings-fields" disabled={saving}>
          <label>
            看板名称
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={120}
            />
          </label>
          {sourceError && (
            <p role="alert">
              已绑定来源读取失败：{sourceError}
              <button
                type="button"
                disabled={loading}
                onClick={() => {
                  setLoading(true);
                  setSourceError("");
                  setSourceAttempt((attempt) => attempt + 1);
                }}
              >
                重试已绑定来源
              </button>
            </p>
          )}
          {loading && <p role="status">正在读取已绑定来源…</p>}
          <DashboardSourceSelector
            sources={sources}
            onChange={setSources}
            disabled={!sourcesLoaded || loading}
          />
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
            disabled={!sourcesLoaded || loading || saving || !ids.length}
          >
            {saving ? "保存中…" : "保存修改"}
          </button>
        </div>
      </form>
      <UnsavedChangesDialog guard={exit} title="看板修改尚未保存" />
    </section>
  );
}
