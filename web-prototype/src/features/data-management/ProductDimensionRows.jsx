import { useCallback, useEffect, useState } from "react";
import {
  ArrowClockwise,
  CaretLeft,
  CaretRight,
  CheckCircle,
  MagnifyingGlass,
  ShieldCheck,
} from "@phosphor-icons/react";
import { api } from "../../api";
import { InlineLoading, Modal } from "../../components/SharedUi";

export function ProductDimensionRows({ dataset, notify, onChanged }) {
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(null);
  const [query, setQuery] = useState("");
  const [draftQuery, setDraftQuery] = useState("");
  const [store, setStore] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [saving, setSaving] = useState(false);
  const [changeNote, setChangeNote] = useState("");
  const pageSize = 15;
  const load = useCallback(
    () =>
      api
        .datasetRows(dataset.id, query, (page - 1) * pageSize, pageSize, {
          store,
          category,
        })
        .then(setData),
    [category, dataset.id, page, query, store],
  );
  useEffect(() => {
    load().catch((error) => notify(error.message, "error"));
  }, [load, notify, dataset.current_version]);
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize));
  const pageStart = Math.min(Math.max(1, page - 2), Math.max(1, totalPages - 4));
  const visiblePages = Array.from(
    { length: Math.min(5, totalPages) },
    (_, index) => pageStart + index,
  );
  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const updated = await api.updateDatasetRow(dataset.id, {
        row_index: editing._row_index,
        expected_version: dataset.current_version,
        changes: {
          MSKU: editing.MSKU,
          "店铺/站点": editing["店铺/站点"],
          Listing: editing.Listing,
          ...(editing["产品名称"] !== undefined
            ? { 产品名称: editing["产品名称"] }
            : {}),
          ...(editing["品类A"] !== undefined ? { 品类A: editing["品类A"] } : {}),
          ...(editing["品类B"] !== undefined ? { 品类B: editing["品类B"] } : {}),
        },
        change_note: changeNote,
      });
      setEditing(null);
      onChanged(updated);
      notify("产品信息已更新，并创建了新版本");
    } catch (error) {
      if (error.status === 409) {
        setEditing(null);
        onChanged(await api.dataset(dataset.id, { include: "versions" }));
        notify("数据已被其他用户更新，已刷新到最新版本，请重新修改", "error");
      } else notify(error.message, "error");
    } finally {
      setSaving(false);
    }
  };
  const clearFilters = () => {
    setDraftQuery("");
    setQuery("");
    setStore("");
    setCategory("");
    setPage(1);
  };
  const hasFilters = Boolean(query || store || category);
  return (
    <section className="dimension-table-panel">
      <div className="dimension-table-toolbar">
        <form
          className="dimension-search"
          onSubmit={(event) => {
            event.preventDefault();
            setPage(1);
            setQuery(draftQuery);
          }}
        >
          <MagnifyingGlass size={15} />
          <input
            aria-label="搜索产品信息"
            value={draftQuery}
            onChange={(event) => setDraftQuery(event.target.value)}
            placeholder="搜索 MSKU、商品名称或 Listing"
          />
          <button type="submit">搜索</button>
        </form>
        <div className="product-master-filters">
          <label>
            店铺/站点
            <select
              value={store}
              onChange={(event) => {
                setPage(1);
                setStore(event.target.value);
              }}
            >
              <option value="">全部</option>
              {(data?.facets?.stores ?? []).map((value) => (
                <option value={value} key={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            品类
            <select
              value={category}
              onChange={(event) => {
                setPage(1);
                setCategory(event.target.value);
              }}
            >
              <option value="">全部</option>
              {(data?.facets?.categories ?? []).map((value) => (
                <option value={value} key={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div>
          <span>共 {(data?.total ?? dataset.row_count).toLocaleString()} 条产品</span>
          <button
            type="button"
            onClick={() => load().catch((error) => notify(error.message, "error"))}
          >
            <ArrowClockwise size={15} />
            刷新
          </button>
        </div>
      </div>
      {!data && <InlineLoading label="读取产品信息…" />}
      {data && (
        <>
          <div className="dimension-table">
            <div className="table-head">
              <span>MSKU</span>
              <span>店铺 / 站点</span>
              <span>Listing</span>
              <span>产品名称</span>
              <span>品类</span>
              <span>状态</span>
              <span>操作</span>
            </div>
            {data.records.map((row) => (
              <div key={row._row_index}>
                <code title={row.MSKU}>{row.MSKU || "—"}</code>
                <span title={row["店铺/站点"]}>{row["店铺/站点"] || "—"}</span>
                <span title={row.Listing}>{row.Listing || "—"}</span>
                <span title={row["产品名称"]}>{row["产品名称"] || "—"}</span>
                <span title={[row["品类A"], row["品类B"]].filter(Boolean).join(" > ")}>
                  {[row["品类A"], row["品类B"]].filter(Boolean).join(" > ") || "待补充"}
                </span>
                <span className="product-master-status">
                  <CheckCircle size={14} weight="fill" />
                  生效
                </span>
                <button
                  type="button"
                  aria-label={`编辑 ${row.MSKU} 产品信息`}
                  onClick={() => {
                    setEditing(row);
                    setChangeNote("");
                  }}
                >
                  编辑信息
                </button>
              </div>
            ))}
            {data.records.length === 0 && (
              <div className="dimension-empty">
                <span>没有匹配的产品信息。</span>
                {hasFilters && (
                  <button type="button" onClick={clearFilters}>
                    清除筛选
                  </button>
                )}
              </div>
            )}
          </div>
          <footer className="dimension-pagination">
            <span className="dimension-page-size">{pageSize} 条/页</span>
            <div>
              <button
                type="button"
                aria-label="上一页"
                disabled={page === 1}
                onClick={() => setPage((current) => current - 1)}
              >
                <CaretLeft size={15} />
              </button>
              {pageStart > 1 && (
                <>
                  <button type="button" onClick={() => setPage(1)}>
                    1
                  </button>
                  <span>…</span>
                </>
              )}
              {visiblePages.map((value) => (
                <button
                  type="button"
                  className={value === page ? "active" : ""}
                  key={value}
                  onClick={() => setPage(value)}
                >
                  {value}
                </button>
              ))}
              {visiblePages.at(-1) < totalPages && (
                <>
                  <span>…</span>
                  <button type="button" onClick={() => setPage(totalPages)}>
                    {totalPages}
                  </button>
                </>
              )}
              <button
                type="button"
                aria-label="下一页"
                disabled={page === totalPages}
                onClick={() => setPage((current) => current + 1)}
              >
                <CaretRight size={15} />
              </button>
            </div>
          </footer>
        </>
      )}
      {editing && (
        <Modal
          eyebrow="产品信息"
          title={`编辑产品信息 · ${editing.MSKU}`}
          onClose={() => setEditing(null)}
        >
          <form className="modal-form product-info-edit-form" onSubmit={save}>
            <fieldset className="product-info-form-section product-info-identity-fields">
              <legend>匹配标识</legend>
              <div>
                <label>
                  MSKU
                  <input
                    value={editing.MSKU}
                    onChange={(event) =>
                      setEditing({ ...editing, MSKU: event.target.value })
                    }
                    required
                  />
                </label>
                <label>
                  店铺 / 站点
                  <input
                    value={editing["店铺/站点"]}
                    onChange={(event) =>
                      setEditing({ ...editing, "店铺/站点": event.target.value })
                    }
                    required
                  />
                </label>
                <label>
                  Listing
                  <input
                    value={editing.Listing}
                    onChange={(event) =>
                      setEditing({ ...editing, Listing: event.target.value })
                    }
                    required
                  />
                </label>
              </div>
            </fieldset>
            <fieldset className="product-info-form-section product-info-attribute-fields">
              <legend>产品属性</legend>
              <div>
                {editing["产品名称"] !== undefined && (
                  <label className="product-info-name-field">
                    产品名称
                    <input
                      value={editing["产品名称"]}
                      onChange={(event) =>
                        setEditing({ ...editing, 产品名称: event.target.value })
                      }
                    />
                  </label>
                )}
                {editing["品类A"] !== undefined && (
                  <label>
                    品类A
                    <input
                      value={editing["品类A"]}
                      onChange={(event) =>
                        setEditing({ ...editing, 品类A: event.target.value })
                      }
                    />
                  </label>
                )}
                {editing["品类B"] !== undefined && (
                  <label>
                    品类B
                    <input
                      value={editing["品类B"]}
                      onChange={(event) =>
                        setEditing({ ...editing, 品类B: event.target.value })
                      }
                    />
                  </label>
                )}
              </div>
            </fieldset>
            <label className="product-info-change-note">
              修改原因
              <textarea
                value={changeNote}
                onChange={(event) => setChangeNote(event.target.value)}
                rows="2"
                maxLength="500"
                placeholder="必填：说明为什么修改这条产品信息"
                required
              />
            </label>
            <div className="snapshot-notice">
              <ShieldCheck size={18} />
              <span>
                保存后创建 v{dataset.current_version + 1}，历史任务仍保留 v
                {dataset.current_version} 快照。
              </span>
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setEditing(null)}
              >
                取消
              </button>
              <button className="primary-button" disabled={saving}>
                {saving ? "正在创建新版本…" : "保存并创建新版本"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}
