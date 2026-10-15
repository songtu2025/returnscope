import { useMemo, useState } from "react";
import { useClassificationResultListData } from "../classification-results/useClassificationResultListData";

/** @typedef {import("./analysisDashboardContracts").DashboardSource} DashboardSource */

/** @param {{sources: DashboardSource[], onChange: (sources: DashboardSource[]) => void, disabled: boolean}} props */
export function DashboardSourceSelector({ sources, onChange, disabled }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const resultQuery = useMemo(() => ({ page, page_size: 20, q: query }), [page, query]);
  const resultState = useClassificationResultListData(resultQuery);
  const ids = sources.map((source) => source.result_version_id);
  return (
    <fieldset className="dashboard-settings-fields" disabled={disabled}>
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
      <section aria-label="已选来源">
        <p>已选择 {sources.length} 个来源</p>
        {sources.map((source) => (
          <div key={source.result_version_id}>
            {source.store_site} · {source.listing}
            <button
              className="text-button"
              type="button"
              aria-label={`移除来源 ${source.store_site} · ${source.listing}`}
              onClick={() =>
                onChange(
                  sources.filter(
                    (item) => item.result_version_id !== source.result_version_id,
                  ),
                )
              }
            >
              移除此来源
            </button>
          </div>
        ))}
      </section>
      <div className="dashboard-settings-source-list">
        {resultState.data?.items.map((item) => (
          <label key={item.version_id}>
            <input
              type="checkbox"
              checked={ids.includes(item.version_id)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [
                        ...sources,
                        {
                          result_version_id: item.version_id,
                          store_site: item.store_site ?? "",
                          listing: item.listing ?? "",
                        },
                      ]
                    : sources.filter(
                        (source) => source.result_version_id !== item.version_id,
                      ),
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
      {resultState.error && (
        <p role="alert">
          来源结果读取失败：{resultState.error}
          <button type="button" onClick={() => void resultState.load()}>
            重试
          </button>
        </p>
      )}
    </fieldset>
  );
}
