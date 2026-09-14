import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CaretDown,
  CaretLeft,
  CaretRight,
  CheckCircle,
  Database,
  FileCsv,
  Funnel,
  MagnifyingGlass,
  UploadSimple,
  WarningCircle,
} from "@phosphor-icons/react";

import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { dataApi } from "../../shared/api/dataApi";
import { ReturnImportDialog } from "../task-create/ReturnImportDialog";
import { DataAssetTabs } from "./DataAssetTabs";
import { SourceDetail } from "./ReturnDataAssetDetail";
import {
  canonicalSources,
  dataStatus,
  mergeSourceDetails,
  sourceDisplayName,
  sourceScopeLabel,
} from "./returnDataAssetPresentation";

const PAGE_SIZE = 20;

export function ReturnDataAssetsPage({ route, notify, onRouteChange }) {
  const [sources, setSources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [detailsBySource, setDetailsBySource] = useState({});
  const [expandedOverride, setExpandedOverride] = useState(null);

  const loadSources = useCallback(async () => {
    setLoading(true);
    try {
      const items = canonicalSources(await dataApi.managedDatasets("returns"));
      setSources(items);
      setDetailsBySource({});
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    setPage(1);
  }, [query, status]);

  const filteredSources = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return sources.filter((source) => {
      const sourceStatus = dataStatus(source).value;
      if (status !== "all" && sourceStatus !== status) return false;
      if (!keyword) return true;
      return [
        sourceDisplayName(source),
        sourceScopeLabel(source),
        ...(source.quality?.stores ?? []),
      ].some((value) => String(value).toLowerCase().includes(keyword));
    });
  }, [query, sources, status]);

  const totalPages = Math.max(1, Math.ceil(filteredSources.length / PAGE_SIZE));
  const visibleSources = filteredSources.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE,
  );
  const requestedSource = sources.find((source) =>
    source.member_ids.includes(route.query.dataset),
  );
  const defaultExpandedId =
    visibleSources.find((source) => source.id === requestedSource?.id)?.id ||
    visibleSources[0]?.id ||
    "";
  const expandedId = expandedOverride ?? defaultExpandedId;

  useEffect(() => {
    setExpandedOverride(null);
  }, [route.query.dataset]);

  useEffect(() => {
    const source = sources.find((item) => item.id === expandedId);
    if (!source || detailsBySource[expandedId]) return undefined;
    const controller = new AbortController();
    Promise.all(
      source.member_ids.map((id) =>
        dataApi.dataset(id, {
          include: "versions,imports",
          signal: controller.signal,
        }),
      ),
    )
      .then((members) => {
        if (!controller.signal.aborted) {
          setDetailsBySource((current) => ({
            ...current,
            [expandedId]: mergeSourceDetails(source, members),
          }));
        }
      })
      .catch((error) => {
        if (error.name !== "AbortError") notify(error.message, "error");
      });
    return () => controller.abort();
  }, [detailsBySource, expandedId, notify, sources]);
  const availableCount = sources.filter(
    (source) => dataStatus(source).value === "available",
  ).length;
  const latestUpdate = sources.reduce(
    (latest, source) =>
      String(source.updated_at || "") > String(latest || "")
        ? source.updated_at
        : latest,
    "",
  );

  const selectSource = (source) => {
    if (source.id === expandedId) {
      setExpandedOverride("");
      return;
    }
    setExpandedOverride(source.id);
    onRouteChange({ view: "returns", dataset: source.id, tab: "" });
  };

  const finishImport = async (result) => {
    setUploadOpen(false);
    await loadSources();
    if (result.dataset?.id) {
      onRouteChange({ view: "returns", dataset: result.dataset.id, tab: "" });
    }
    notify(result.duplicate ? "该批次已存在，已定位到原数据源" : "退货数据源已更新");
  };

  return (
    <div className="standard-page data-page returns-assets-page">
      <PageHeading
        eyebrow="数据资产"
        title="退货数据源管理"
        description="管理可复用的退货数据源和最近导入状态。"
        action={
          <button className="primary-button" onClick={() => setUploadOpen(true)}>
            <UploadSimple size={18} />
            导入新批次
          </button>
        }
      />
      <DataAssetTabs
        current="returns"
        onChange={(view) => onRouteChange({ view, dataset: "", tab: "" })}
      />

      {loading ? (
        <section className="content-card returns-assets-loading">
          <InlineLoading label="正在读取退货数据源…" />
        </section>
      ) : sources.length === 0 ? (
        <EmptyState
          icon={FileCsv}
          title="尚未建立退货数据源"
          description="导入首个批次后，系统会识别业务范围并建立可复用的数据源。"
          action={
            <button className="primary-button" onClick={() => setUploadOpen(true)}>
              <UploadSimple size={17} />
              导入首个批次
            </button>
          }
        />
      ) : (
        <section className="returns-registry" aria-label="退货数据源清单">
          <header className="returns-registry-toolbar">
            <div className="returns-registry-summary">
              <span>
                <Database size={18} />
                <b>{sources.length} 个数据源</b>
              </span>
              <i aria-hidden="true">•</i>
              <strong>{availableCount} 个当前可用</strong>
              <i aria-hidden="true">•</i>
              <em>{sources.length - availableCount} 个需关注</em>
              <i aria-hidden="true">•</i>
              <span>最近导入：{formatTime(latestUpdate)}</span>
            </div>
            <div className="returns-registry-filters">
              <label className="returns-registry-search">
                <MagnifyingGlass size={17} />
                <input
                  aria-label="搜索退货数据源"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索数据源或业务范围"
                />
              </label>
              <label className="returns-registry-filter">
                <Funnel size={17} />
                <select
                  aria-label="按数据状态筛选"
                  value={status}
                  onChange={(event) => setStatus(event.target.value)}
                >
                  <option value="all">全部状态</option>
                  <option value="available">当前可用</option>
                  <option value="attention">需关注</option>
                </select>
              </label>
            </div>
          </header>

          {visibleSources.length ? (
            <div className="returns-registry-table" role="table">
              <div className="returns-registry-head" role="row">
                <span>数据源</span>
                <span>业务范围</span>
                <span>当前数据</span>
                <span>最近导入</span>
                <span>数据状态</span>
                <span>被任务使用</span>
                <span>操作</span>
              </div>
              {visibleSources.map((source) => {
                const expanded = source.id === expandedId;
                const sourceState = dataStatus(source);
                return (
                  <article
                    className={`returns-registry-record ${expanded ? "expanded" : ""}`}
                    key={source.id}
                  >
                    <div className="returns-registry-row" role="row">
                      <div className="returns-registry-name">
                        <Database size={19} weight="duotone" />
                        <b>{sourceDisplayName(source)}</b>
                      </div>
                      <span>{sourceScopeLabel(source)}</span>
                      <b>{Number(source.row_count || 0).toLocaleString()} 行</b>
                      <span>{formatTime(source.updated_at)}</span>
                      <span className={`returns-source-status ${sourceState.value}`}>
                        {sourceState.value === "available" ? (
                          <CheckCircle size={18} weight="fill" />
                        ) : (
                          <WarningCircle size={18} weight="fill" />
                        )}
                        <span>
                          <b>{sourceState.label}</b>
                          <small>{sourceState.description}</small>
                        </span>
                      </span>
                      <span>
                        {Number(source.task_reference_count || 0).toLocaleString()}{" "}
                        个任务
                      </span>
                      <button
                        className="returns-detail-button"
                        aria-expanded={expanded}
                        onClick={() => selectSource(source)}
                      >
                        {expanded ? "收起详情" : "查看详情"}
                        <CaretDown size={17} />
                      </button>
                    </div>
                    {expanded &&
                      (detailsBySource[source.id] ? (
                        <SourceDetail
                          source={detailsBySource[source.id]}
                          notify={notify}
                          onStorageChanged={loadSources}
                          initiallyShowTrace={["imports", "snapshots"].includes(
                            route.query.tab,
                          )}
                        />
                      ) : (
                        <InlineLoading label="正在读取数据源详情…" />
                      ))}
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="returns-registry-empty">
              <MagnifyingGlass size={23} />
              <b>没有符合条件的数据源</b>
              <span>请修改搜索词或数据状态。</span>
            </div>
          )}

          <footer className="returns-registry-footer">
            <span>共 {filteredSources.length} 个数据源</span>
            {totalPages > 1 && (
              <div>
                <button
                  aria-label="上一页"
                  disabled={page === 1}
                  onClick={() => setPage((current) => current - 1)}
                >
                  <CaretLeft size={16} />
                </button>
                <b>{page}</b>
                <span>/ {totalPages}</span>
                <button
                  aria-label="下一页"
                  disabled={page === totalPages}
                  onClick={() => setPage((current) => current + 1)}
                >
                  <CaretRight size={16} />
                </button>
              </div>
            )}
          </footer>
        </section>
      )}

      {uploadOpen && (
        <ReturnImportDialog
          purpose="asset"
          onClose={() => setUploadOpen(false)}
          onDone={finishImport}
        />
      )}
    </div>
  );
}
