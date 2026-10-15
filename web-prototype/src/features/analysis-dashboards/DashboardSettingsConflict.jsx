import { useState } from "react";
import { resultStateLabel } from "../classification-results/resultStatePolicy";
import { settingsValues } from "./useDashboardSettingsConflict";

/** @typedef {import("./useDashboardSettingsConflict").DashboardSettings} DashboardSettings */
/** @typedef {ReturnType<typeof import("./useDashboardSettingsConflict").useDashboardSettingsConflict>} ConflictState */

/** @type {{key: keyof ReturnType<typeof settingsValues>, label: string}[]} */
const FIELDS = [
  { key: "name", label: "看板名称" },
  { key: "sources", label: "来源结果" },
  { key: "statuses", label: "统计记录范围" },
  { key: "date_from", label: "反馈开始日期" },
  { key: "date_to", label: "反馈结束日期" },
];

/** @param {DashboardSettings} settings @param {string} key */
function displayValue(settings, key) {
  if (key === "sources")
    return (
      settings.sources
        .map((source) => `${source.store_site} · ${source.listing}`)
        .join("；") || "--"
    );
  if (key === "statuses")
    return settings.statuses
      .map((status) =>
        status === "excluded" ? "已忽略" : resultStateLabel({ quality_status: status }),
      )
      .join("、");
  return String((key === "name" ? settings.name : settings.filters[key]) || "--");
}

/** @param {{original: DashboardSettings, latest: DashboardSettings, draft: DashboardSettings, onApply: (settings: DashboardSettings) => void}} props */
function SettingsComparison({ original, latest, draft, onApply }) {
  const [choices, setChoices] = useState(
    /** @type {Record<string, {choice: string, value: string}>} */ ({}),
  );
  const before = settingsValues(original);
  const current = settingsValues(draft);
  const newest = settingsValues(latest);
  const rows = FIELDS.map(({ key, label }) => {
    const mine = JSON.stringify(current[key]);
    const changed = mine !== JSON.stringify(before[key]);
    const conflict =
      changed &&
      JSON.stringify(newest[key]) !== JSON.stringify(before[key]) &&
      mine !== JSON.stringify(newest[key]);
    const choice = choices[key]?.value === mine ? choices[key].choice : "";
    return { key, label, mine, changed, conflict, choice };
  });
  const unresolved = rows.some((row) => row.conflict && !row.choice);
  const apply = () => {
    if (unresolved) return;
    const selected = Object.fromEntries(
      rows.map((row) => [
        row.key,
        row.changed && (!row.conflict || row.choice === "mine") ? draft : latest,
      ]),
    );
    onApply({
      name: selected.name.name,
      sources: selected.sources.sources,
      statuses: selected.statuses.statuses,
      filters: {
        ...latest.filters,
        date_from: selected.date_from.filters.date_from ?? null,
        date_to: selected.date_to.filters.date_to ?? null,
      },
    });
  };
  return (
    <section className="dashboard-settings-comparison" aria-label="最新看板配置核对">
      <div className="dashboard-settings-comparison-table">
        <table>
          <thead>
            <tr>
              <th>字段</th>
              <th>编辑前</th>
              <th>最新配置</th>
              <th>我的输入</th>
              <th>采用值</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <th scope="row">{row.label}</th>
                <td>{displayValue(original, row.key)}</td>
                <td>{displayValue(latest, row.key)}</td>
                <td>{displayValue(draft, row.key)}</td>
                <td>
                  {row.conflict ? (
                    <fieldset>
                      <legend>{row.label}冲突</legend>
                      {[
                        { choice: "mine", label: "我的输入" },
                        { choice: "latest", label: "最新配置" },
                      ].map(({ choice, label }) => (
                        <label key={choice}>
                          <input
                            type="radio"
                            name={`dashboard-conflict-${row.key}`}
                            checked={row.choice === choice}
                            onChange={() =>
                              setChoices({
                                ...choices,
                                [row.key]: { choice, value: row.mine },
                              })
                            }
                          />
                          {label}
                        </label>
                      ))}
                    </fieldset>
                  ) : row.changed ? (
                    "采用我的输入"
                  ) : (
                    "采用最新配置"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        className="secondary-button"
        type="button"
        disabled={unresolved}
        onClick={apply}
      >
        应用核对结果
      </button>
    </section>
  );
}

/** @param {{state: ConflictState, draft: DashboardSettings, onApply: (settings: DashboardSettings) => void}} props */
export function DashboardSettingsConflict({ state, draft, onApply }) {
  if (!state.conflict) return null;
  return (
    <section className="dashboard-settings-conflict" aria-label="看板配置冲突">
      <p>输入已保留，请读取最新配置并核对后保存。</p>
      {state.error && <p role="alert">最新配置读取失败：{state.error}</p>}
      <button
        className="secondary-button"
        type="button"
        disabled={state.loading}
        onClick={() => void state.loadLatest()}
      >
        {state.loading ? "正在读取…" : "读取最新配置"}
      </button>
      {state.latest && (
        <SettingsComparison
          key={state.latest.dashboard.revision}
          original={state.original}
          latest={state.latest.settings}
          draft={draft}
          onApply={onApply}
        />
      )}
    </section>
  );
}
