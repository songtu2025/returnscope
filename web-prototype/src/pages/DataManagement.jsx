import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  Database,
  DownloadSimple,
  UploadSimple,
} from "@phosphor-icons/react";
import { api } from "../api";
import { DatasetUploadDialog } from "../components/DatasetUploadDialog";
import { CardHeading, EmptyState, PageHeading } from "../components/SharedUi";
import { DataAssetTabs } from "../features/data-management/DataAssetTabs";
import { DatasetReferences } from "../features/data-management/DatasetReferences";
import { ProductDimensionRows } from "../features/data-management/ProductDimensionRows";
import { TaskCategoryCompletion } from "../features/data-management/TaskCategoryCompletion";
import { formatTime } from "../lib/presentation";

export { DatasetReferences } from "../features/data-management/DatasetReferences";

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
  onAssetViewChange = () => {},
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
      .dataset(selectedId, {
        include: detailTab === "impact" ? "versions,audit" : "versions",
      })
      .then(setSelected)
      .catch((error) => notify(error.message, "error"));
  }, [detailTab, selectedId, notify]);

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
        title="商品信息汇总"
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
      <DataAssetTabs current="products" onChange={onAssetViewChange} />
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
                  <h2>商品信息汇总</h2>
                  <span>v{selected.current_version} · 当前生效</span>
                </div>
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
                  onChanged={setSelected}
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
