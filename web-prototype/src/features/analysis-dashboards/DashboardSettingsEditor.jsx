import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { UnsavedChangesDialog } from "../../components/UnsavedChangesActions";
import { useUnsavedNavigation } from "../../hooks/useUnsavedNavigation";
import { dashboardApi } from "../../shared/api/dashboardApi";
import { DashboardQualityScope } from "./DashboardQualityScope";
import { DashboardSourceSelector } from "./DashboardSourceSelector";
import { DashboardSettingsConflict } from "./DashboardSettingsConflict";
import {
  dashboardSettings,
  settingsKey,
  useDashboardSettingsConflict,
} from "./useDashboardSettingsConflict";
import { errorMessage, errorStatus } from "./dashboardRequestErrors";
import "../../styles/dashboard-settings.css";

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
  const conflict = useDashboardSettingsConflict(dashboard);
  const { setOriginal } = conflict;
  const busy = saving || conflict.loading;
  const formRef = useRef(/** @type {HTMLFormElement | null} */ (null));
  const leavingRef = useRef(false);
  const [baseline, setBaseline] = useState(() =>
    settingsKey(dashboardSettings(dashboard, [])),
  );
  const ids = sources
    .map((source) => source.result_version_id)
    .filter((id) => typeof id === "string");
  const draft = { name, sources, statuses, filters };
  const draftKey = settingsKey(draft);
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
          const original = dashboardSettings(dashboard, sources);
          setOriginal(original);
          setBaseline(settingsKey(original));
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
  }, [dashboard, sourceAttempt, setOriginal]);
  const save = async (complete = true) => {
    if (
      !sourcesLoaded ||
      loading ||
      busy ||
      conflict.conflict ||
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
        expected_revision: conflict.revision,
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
      if (errorStatus(failure) === 409) conflict.requireReview();
      return false;
    } finally {
      setSaving(false);
    }
  };
  const exit = useUnsavedNavigation({
    dirty,
    busy: dirty && busy,
    canSave: sourcesLoaded && !loading && !conflict.conflict && Boolean(ids.length),
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
        <fieldset className="dashboard-settings-fields" disabled={busy}>
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
        <DashboardSettingsConflict
          state={conflict}
          draft={draft}
          onApply={(merged) => {
            if (!conflict.latest) return;
            setName(merged.name);
            setSources(merged.sources);
            setStatuses(merged.statuses);
            setFilters(merged.filters);
            setBaseline(settingsKey(conflict.latest.settings));
            setError("");
            conflict.acceptLatest();
          }}
        />
        <div className="modal-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={busy}
            onClick={onClose}
          >
            取消编辑
          </button>
          <button
            className="primary-button"
            disabled={
              !sourcesLoaded || loading || busy || conflict.conflict || !ids.length
            }
          >
            {saving ? "保存中…" : "保存修改"}
          </button>
        </div>
      </form>
      <UnsavedChangesDialog guard={exit} title="看板修改尚未保存" />
    </section>
  );
}
