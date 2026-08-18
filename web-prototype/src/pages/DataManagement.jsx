import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  ArrowClockwise,
  CaretLeft,
  CaretRight,
  CheckCircle,
  Database,
  DownloadSimple,
  MagnifyingGlass,
  ShieldCheck,
  UploadSimple,
} from "@phosphor-icons/react";
import { api } from "../api";
import { DatasetUploadDialog } from "../components/DatasetUploadDialog";
import {
  CardHeading,
  EmptyState,
  InlineLoading,
  Modal,
  PageHeading,
} from "../components/SharedUi";
import { STATUS_LABELS } from "../constants";
import { formatTime } from "../lib/presentation";

export function DataManagement({
  notify,
  onNavigate,
  focus,
  taskDraft,
  onReturnToTask,
  routeDetailTab = "",
  onDetailTabChange,
  routeReferenceVersion = "",
  routeReferencePage = 1,
  onReferenceRouteChange,
}) {
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [detailTab, setDetailTab] = useState("rows");

  const load = useCallback(async () => {
    const values = await api.datasets("products");
    setSelectedId((current) =>
      values.some((item) => item.id === current) ? current : (values[0]?.id ?? null),
    );
  }, []);
  useEffect(() => {
    if (["rows", "versions", "impact"].includes(routeDetailTab)) {
      setDetailTab(routeDetailTab);
    } else if (["audit", "references"].includes(routeDetailTab)) {
      setDetailTab("impact");
    }
  }, [routeDetailTab]);
  useEffect(() => {
    load().catch((error) => notify(error.message, "error"));
  }, [load, notify]);
  useEffect(() => {
    if (!focus || focus.datasetKind !== "products") return;
    setSelectedId(focus.id);
    setDetailTab("rows");
  }, [focus]);
  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      return;
    }
    api
      .dataset(selectedId)
      .then(setSelected)
      .catch((error) => notify(error.message, "error"));
  }, [selectedId, notify]);

  const dimensionAudit =
    selected?.audit?.filter((entry) =>
      ["dimension_row_update", "dimension_category_completion"].includes(entry.action),
    ) ?? [];
  const currentProductVersionId = selected?.versions?.find(
    (version) => version.version === selected.current_version,
  )?.id;
  const currentVersionId = selected?.versions?.find(
    (version) => version.version === selected.current_version,
  )?.id;
  return (
    <div className="standard-page data-page product-master-page">
      <PageHeading
        eyebrow="系统产品资料"
        title="产品信息"
        description="维护跨分析任务复用的产品名称、店铺映射和品类信息；退货明细在分析任务中导入。"
        action={
          <button
            className="primary-button"
            onClick={() =>
              setDialog(
                selected
                  ? { mode: "version", dataset: selected }
                  : { mode: "create", kind: "products" },
              )
            }
          >
            <UploadSimple size={18} />
            {selected ? "更新产品信息" : "导入产品信息"}
          </button>
        }
      />
      {focus?.returnToTask && taskDraft && (
        <section className="task-return-banner" role="status">
          <div>
            <b>正在补充任务所需的商品信息</b>
            <p>
              {focus.unresolvedProducts?.length
                ? `已定位 ${focus.unresolvedProducts.length.toLocaleString()} 个商品，影响 ${(focus.blockedCommentCount ?? 0).toLocaleString()} 条评论。`
                : "完成维度修改后，返回原任务并重新生成执行计划。"}
            </p>
          </div>
          <button
            className="primary-button"
            disabled={!currentProductVersionId}
            onClick={() => onReturnToTask?.(currentProductVersionId)}
          >
            返回任务并重新预检
            <ArrowRight size={17} />
          </button>
        </section>
      )}
      {focus?.returnToTask && focus.unresolvedProducts?.length > 0 && selected && (
        <TaskCategoryCompletion
          dataset={selected}
          focus={focus}
          notify={notify}
          onReturnToTask={onReturnToTask}
        />
      )}
      <section className="dataset-detail">
        {!selected && (
          <EmptyState
            icon={Database}
            title="尚未建立产品信息"
            description="导入首个产品信息版本后，可维护商品映射、版本和修改留痕。"
            action={
              <button
                className="primary-button"
                onClick={() => setDialog({ mode: "create", kind: "products" })}
              >
                <UploadSimple size={17} />
                导入首个产品信息版本
              </button>
            }
          />
        )}
        {selected && (
          <>
            <header className="dataset-header">
              <div className="dataset-heading-copy">
                <small className="asset-name-label">当前版本</small>
                <div className="dataset-title-line">
                  <h2>{selected.name}</h2>
                  <span>v{selected.current_version} · 当前生效</span>
                </div>
                <p>{selected.description || "系统范围内统一复用的标准产品信息"}</p>
              </div>
              <div className="dataset-summary">
                <span>
                  <small>产品记录</small>
                  <strong>{selected.row_count.toLocaleString()} 条</strong>
                </span>
                <span>
                  <small>核心字段数</small>
                  <strong>
                    {selected.schema?.length ?? selected.column_count} 个字段
                  </strong>
                </span>
                <span>
                  <small>必填完整度</small>
                  <strong>{selected.quality?.complete_rate ?? 0}%</strong>
                </span>
                <span>
                  <small>最近更新</small>
                  <strong>{formatTime(selected.updated_at)}</strong>
                </span>
              </div>
              <div className="dataset-actions">
                <div className="dataset-utility-actions">
                  <a className="text-button" href={api.datasetDownloadUrl(selected.id)}>
                    <DownloadSimple size={16} />
                    下载版本
                  </a>
                </div>
              </div>
            </header>
            <nav className="dataset-view-tabs" aria-label="产品信息详情">
              <button
                className={detailTab === "rows" ? "active" : ""}
                onClick={() => {
                  setDetailTab("rows");
                  onDetailTabChange?.("rows");
                }}
              >
                产品列表
              </button>
              <button
                className={detailTab === "versions" ? "active" : ""}
                onClick={() => {
                  setDetailTab("versions");
                  onDetailTabChange?.("versions");
                }}
              >
                版本历史
              </button>
              <button
                className={detailTab === "impact" ? "active" : ""}
                onClick={() => {
                  setDetailTab("impact");
                  onDetailTabChange?.("impact");
                  onReferenceRouteChange?.({
                    tab: "impact",
                    reference_version: routeReferenceVersion || currentVersionId,
                    reference_page: 1,
                  });
                }}
              >
                变更追踪与影响
              </button>
            </nav>
            <div className="dataset-view">
              {detailTab === "rows" && (
                <ProductDimensionRows
                  dataset={selected}
                  notify={notify}
                  onChanged={async () => {
                    await load();
                    setSelected(await api.dataset(selected.id));
                  }}
                />
              )}
              {detailTab === "versions" && (
                <section className="dataset-view-panel">
                  <CardHeading title="版本记录" note="每次更新都会保留不可变快照" />
                  <div className="version-list">
                    {selected.versions.map((version) => (
                      <div key={version.id}>
                        <span>v{version.version}</span>
                        <div>
                          <b>{version.original_name}</b>
                          <p>{version.change_note || "未填写变更说明"}</p>
                          <small>
                            {version.creator_name} · {formatTime(version.created_at)} ·{" "}
                            {version.row_count.toLocaleString()} 行
                          </small>
                        </div>
                        <div className="version-actions">
                          {version.version === selected.current_version && (
                            <em>当前</em>
                          )}
                          <a
                            href={api.datasetDownloadUrl(selected.id, version.version)}
                            title={`下载 v${version.version}`}
                          >
                            <DownloadSimple size={15} />
                          </a>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}
              {detailTab === "impact" && (
                <div className="product-master-impact">
                  <section className="dataset-view-panel">
                    <CardHeading title="信息修改记录" note="记录原值、新值和修改原因" />
                    <div className="data-audit-list">
                      {dimensionAudit.map((entry) => {
                        if (entry.action === "dimension_category_completion") {
                          return (
                            <div key={entry.id}>
                              <b>
                                {entry.actor_name} · 批量补充{" "}
                                {(entry.after?.items ?? []).length} 个商品
                              </b>
                              <p>
                                <span>店铺</span>
                                <code>{entry.after?.store || "—"}</code>
                                <span>品类补充</span>
                              </p>
                              <small>
                                原因：{entry.after?.note} ·{" "}
                                {formatTime(entry.created_at)}
                              </small>
                            </div>
                          );
                        }
                        const changes = Object.keys(entry.after?.values ?? {}).filter(
                          (field) =>
                            entry.before?.values?.[field] !==
                            entry.after?.values?.[field],
                        );
                        return (
                          <div key={entry.id}>
                            <b>
                              {entry.actor_name} · 第{" "}
                              {(entry.after?.row_index ?? 0) + 2} 行
                            </b>
                            {changes.map((field) => (
                              <p key={field}>
                                <span>{field}</span>
                                <code>{entry.before.values[field] || "空"}</code>
                                <ArrowRight size={12} />
                                <code>{entry.after.values[field] || "空"}</code>
                              </p>
                            ))}
                            <small>
                              原因：{entry.after?.note} · {formatTime(entry.created_at)}
                            </small>
                          </div>
                        );
                      })}
                      {dimensionAudit.length === 0 && (
                        <p className="muted-line">尚无产品信息人工修改。</p>
                      )}
                    </div>
                  </section>
                  <DatasetReferences
                    versions={selected.versions ?? []}
                    currentVersionId={currentVersionId}
                    routeVersionId={routeReferenceVersion}
                    page={Number(routeReferencePage) || 1}
                    onRouteChange={onReferenceRouteChange}
                    onNavigate={onNavigate}
                  />
                </div>
              )}
            </div>
          </>
        )}
      </section>
      {dialog && (
        <DatasetUploadDialog
          dialog={dialog}
          onClose={() => setDialog(null)}
          onDone={async () => {
            setDialog(null);
            await load();
            notify(dialog.mode === "create" ? "产品信息已创建" : "新版本已创建");
          }}
        />
      )}
    </div>
  );
}

export function DatasetReferences({
  versions,
  currentVersionId,
  routeVersionId,
  page,
  onRouteChange,
  onNavigate,
}) {
  const availableVersionIds = versions.map((item) =>
    String(item.id ?? item.version_id),
  );
  const selectedVersionId = availableVersionIds.includes(String(routeVersionId))
    ? String(routeVersionId)
    : String(currentVersionId ?? availableVersionIds[0] ?? "");
  const [state, setState] = useState({ loading: true, error: "", data: null });

  const load = useCallback(
    async (signal) => {
      if (!selectedVersionId) {
        setState({ loading: false, error: "", data: null });
        return;
      }
      setState({ loading: true, error: "", data: null });
      try {
        const data = await api.dataVersionReferences(
          selectedVersionId,
          { page, page_size: 20 },
          { signal },
        );
        setState({ loading: false, error: "", data });
      } catch (error) {
        if (error.name !== "AbortError") {
          setState({ loading: false, error: error.message, data: null });
        }
      }
    },
    [page, selectedVersionId],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const total = Number(state.data?.total ?? 0);
  const pages = Math.max(Math.ceil(total / 20), 1);

  return (
    <section className="dataset-view-panel dataset-reference-panel">
      <CardHeading title="任务引用" note="历史任务始终保留启动时固化的数据版本" />
      <div className="dataset-reference-toolbar">
        <label>
          数据版本
          <select
            value={selectedVersionId}
            onChange={(event) =>
              onRouteChange?.({
                tab: "references",
                reference_version: event.target.value,
                reference_page: 1,
              })
            }
          >
            {versions.map((version) => {
              const id = String(version.id ?? version.version_id);
              return (
                <option key={id} value={id}>
                  v{version.version} · {version.original_name || "未提供文件名"}
                </option>
              );
            })}
          </select>
        </label>
        {state.data?.version && (
          <span>
            当前查看：{state.data.version.name || "数据版本"} · v
            {state.data.version.version ?? "-"}
          </span>
        )}
      </div>
      {state.loading ? (
        <InlineLoading label="正在读取任务引用…" />
      ) : state.error ? (
        <div className="plan-state error dataset-reference-error" role="alert">
          <div>
            <b>任务引用读取失败</b>
            <p>{state.error}</p>
          </div>
          <button className="secondary-button" onClick={() => load()}>
            <ArrowClockwise size={16} />
            重新加载
          </button>
        </div>
      ) : !state.data?.items?.length ? (
        <EmptyState
          icon={Database}
          title="此版本尚未被任务引用"
          description="任务创建并固化该版本后会显示在这里。"
        />
      ) : (
        <>
          <div className="dataset-reference-list">
            {state.data.items.map((item) => (
              <article key={`${item.task_id}-${item.reference_type}`}>
                <span className="dataset-reference-role">
                  {item.reference_type === "returns" ? "退货明细" : "产品信息"}
                </span>
                <div>
                  <b>{item.title || `任务 #${item.task_id}`}</b>
                  <p>
                    {STATUS_LABELS[item.status] ?? item.status ?? "未提供状态"} ·{" "}
                    {item.owner?.name || "未提供所有者"} · {formatTime(item.created_at)}
                  </p>
                  <details>
                    <summary>固化版本快照</summary>
                    <SnapshotFields value={item.version_snapshot} />
                  </details>
                </div>
                <button
                  className="secondary-button"
                  onClick={() =>
                    onNavigate?.("analysis-tasks", { kind: "task", id: item.task_id })
                  }
                >
                  查看任务
                  <ArrowRight size={15} />
                </button>
              </article>
            ))}
          </div>
          <footer className="quality-pagination">
            <span>
              共 {total.toLocaleString()} 条 · 第 {page}/{pages} 页
            </span>
            <button
              className="secondary-button"
              disabled={page <= 1}
              onClick={() => onRouteChange?.({ reference_page: page - 1 })}
            >
              上一页
            </button>
            <button
              className="secondary-button"
              disabled={page >= pages}
              onClick={() => onRouteChange?.({ reference_page: page + 1 })}
            >
              下一页
            </button>
          </footer>
        </>
      )}
    </section>
  );
}

function SnapshotFields({ value }) {
  const entries = Object.entries(value ?? {});
  if (!entries.length) return <p>未提供快照明细</p>;
  return (
    <dl className="snapshot-field-list">
      {entries.map(([key, fieldValue]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>
            {fieldValue && typeof fieldValue === "object"
              ? JSON.stringify(fieldValue)
              : String(fieldValue ?? "未提供")}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function TaskCategoryCompletion({ dataset, focus, notify, onReturnToTask }) {
  const categoryOptions = focus.categoryOptions ?? [];
  const [items, setItems] = useState(() =>
    (focus.unresolvedProducts ?? []).map((item) => ({
      ...item,
      listing: item.suggested_listing ?? "",
      category_a: "",
      category_b: "",
      selected: false,
    })),
  );
  const [listingFilter, setListingFilter] = useState("all");
  const [bulkCategory, setBulkCategory] = useState("");
  const [changeNote, setChangeNote] = useState(
    `补充任务“${focus.taskTitle || focus.store}”缺失的商品品类`,
  );
  const [saving, setSaving] = useState(false);
  const listingGroups = Array.from(
    new Set(items.map((item) => item.suggested_listing).filter(Boolean)),
  ).sort();
  const visibleItems = items.filter(
    (item) => listingFilter === "all" || item.suggested_listing === listingFilter,
  );
  const selectedCount = items.filter((item) => item.selected).length;
  const completedItems = items.filter(
    (item) => item.editable && item.listing && item.category_a && item.category_b,
  );
  const coveredComments = completedItems.reduce(
    (total, item) => total + Number(item.comment_count || 0),
    0,
  );

  const updateItem = (productKey, changes) => {
    setItems((current) =>
      current.map((item) =>
        item.product_key === productKey ? { ...item, ...changes } : item,
      ),
    );
  };
  const selectVisible = () => {
    const visibleKeys = new Set(
      visibleItems.filter((item) => item.editable).map((item) => item.product_key),
    );
    const allSelected = visibleItems
      .filter((item) => item.editable)
      .every((item) => item.selected);
    setItems((current) =>
      current.map((item) =>
        visibleKeys.has(item.product_key) ? { ...item, selected: !allSelected } : item,
      ),
    );
  };
  const applyBulkCategory = () => {
    const option = categoryOptions[Number(bulkCategory)];
    if (!option) return;
    setItems((current) =>
      current.map((item) =>
        item.selected
          ? {
              ...item,
              category_a: option.category_a,
              category_b: option.category_b,
              selected: false,
            }
          : item,
      ),
    );
    setBulkCategory("");
  };
  const save = async () => {
    if (!completedItems.length || !changeNote.trim()) return;
    setSaving(true);
    try {
      const result = await api.completeProductCategories(dataset.id, {
        expected_version: dataset.current_version,
        store: focus.store,
        items: completedItems.map((item) => ({
          msku: item.msku,
          listing: item.listing,
          category_a: item.category_a,
          category_b: item.category_b,
          product_name: item.product_name || "",
        })),
        change_note: changeNote.trim(),
      });
      const versionId = result.versions?.find(
        (version) => version.version === result.current_version,
      )?.id;
      notify(
        `已补充 ${completedItems.length} 个商品，并创建产品信息 v${result.current_version}`,
      );
      if (versionId) onReturnToTask?.(versionId);
    } catch (error) {
      notify(
        error.status === 409
          ? "产品信息已被其他用户修改，请刷新后重新提交"
          : error.message,
        "error",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="task-category-completion" aria-label="当前任务待补充商品">
      <header>
        <div>
          <span>当前任务待补充</span>
          <h3>{focus.taskTitle || `${focus.store} 退货分析`}</h3>
          <p>这里只显示阻断当前任务的商品，不需要在完整产品信息中搜索。</p>
        </div>
        <div className="completion-stats">
          <span>
            <small>待补充商品</small>
            <strong>{items.length}</strong>
          </span>
          <span>
            <small>已填写商品</small>
            <strong>{completedItems.length}</strong>
          </span>
          <span>
            <small>覆盖阻断评论</small>
            <strong>
              {coveredComments}/{focus.blockedCommentCount ?? 0}
            </strong>
          </span>
        </div>
      </header>
      <div className="completion-toolbar">
        <label>
          按 Listing 分组
          <select
            value={listingFilter}
            onChange={(event) => setListingFilter(event.target.value)}
          >
            <option value="all">全部商品（{items.length}）</option>
            {listingGroups.map((listing) => (
              <option key={listing} value={listing}>
                {listing}（
                {items.filter((item) => item.suggested_listing === listing).length}）
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="secondary-button" onClick={selectVisible}>
          选择当前 {visibleItems.length} 个
        </button>
        <label className="completion-category-select">
          批量设置品类
          <select
            value={bulkCategory}
            onChange={(event) => setBulkCategory(event.target.value)}
          >
            <option value="">选择品类A / 品类B</option>
            {categoryOptions.map((option, index) => (
              <option key={`${option.category_a}-${option.category_b}`} value={index}>
                {option.category_a} / {option.category_b}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="primary-button"
          disabled={!selectedCount || bulkCategory === ""}
          onClick={applyBulkCategory}
        >
          应用到已选 {selectedCount} 个
        </button>
      </div>
      <div className="completion-table">
        <div className="table-head">
          <span>选择</span>
          <span>商品 / 问题</span>
          <span>Listing</span>
          <span>品类A / 品类B</span>
          <span>影响</span>
        </div>
        {visibleItems.map((item) => {
          const categoryIndex = categoryOptions.findIndex(
            (option) =>
              option.category_a === item.category_a &&
              option.category_b === item.category_b,
          );
          return (
            <div key={item.product_key}>
              <span>
                <input
                  type="checkbox"
                  aria-label={`选择 ${item.msku || "缺失 SKU"}`}
                  checked={item.selected}
                  disabled={!item.editable}
                  onChange={(event) =>
                    updateItem(item.product_key, { selected: event.target.checked })
                  }
                />
              </span>
              <span>
                <code>{item.msku || "缺失 SKU"}</code>
                <small>{item.product_name || "暂无商品名称"}</small>
                <em>
                  {item.issue === "product_not_found"
                    ? "产品信息中不存在，将新增"
                    : item.issue === "missing_category"
                      ? "商品已存在，品类为空"
                      : item.issue === "unsupported_category"
                        ? "当前品类未配置分类逻辑"
                        : "缺少商品标识，需修正退货源数据"}
                </em>
              </span>
              <span>
                <input
                  aria-label={`${item.msku} Listing`}
                  value={item.listing}
                  disabled={!item.editable}
                  onChange={(event) =>
                    updateItem(item.product_key, { listing: event.target.value })
                  }
                />
              </span>
              <span>
                <select
                  aria-label={`${item.msku} 品类`}
                  value={categoryIndex >= 0 ? String(categoryIndex) : ""}
                  disabled={!item.editable}
                  onChange={(event) => {
                    const option =
                      event.target.value === ""
                        ? null
                        : categoryOptions[Number(event.target.value)];
                    updateItem(item.product_key, {
                      category_a: option?.category_a ?? "",
                      category_b: option?.category_b ?? "",
                    });
                  }}
                >
                  <option value="">待选择</option>
                  {categoryOptions.map((option, index) => (
                    <option
                      key={`${option.category_a}-${option.category_b}`}
                      value={index}
                    >
                      {option.category_a} / {option.category_b}
                    </option>
                  ))}
                </select>
              </span>
              <span>
                <strong>{item.comment_count} 条评论</strong>
                <small>{item.record_count} 条记录</small>
              </span>
            </div>
          );
        })}
      </div>
      <footer className="completion-footer">
        <label>
          修改原因
          <input
            value={changeNote}
            onChange={(event) => setChangeNote(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="primary-button"
          disabled={!completedItems.length || !changeNote.trim() || saving}
          onClick={save}
        >
          {saving
            ? "正在创建新版本…"
            : `保存 ${completedItems.length} 个商品并重新预检`}
        </button>
      </footer>
    </section>
  );
}

function ProductDimensionRows({ dataset, notify, onChanged }) {
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
      await api.updateDatasetRow(dataset.id, {
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
      await onChanged();
      await load();
      notify("产品信息已更新，并创建了新版本");
    } catch (error) {
      if (error.status === 409) {
        setEditing(null);
        await onChanged();
        notify("数据已被其他用户更新，已刷新到最新版本，请重新修改", "error");
      } else notify(error.message, "error");
    } finally {
      setSaving(false);
    }
  };
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
              <p className="dimension-empty">没有匹配的产品信息。</p>
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
