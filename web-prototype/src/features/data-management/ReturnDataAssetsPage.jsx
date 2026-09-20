import { useEffect, useMemo, useState } from "react";
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
import Button from "antd/es/button";
import Input from "antd/es/input";
import useSWR from "swr";

import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { dataApi } from "../../shared/api/dataApi";
import { serverStateKeys } from "../../shared/serverState";
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

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetSource} DatasetSource */
/** @typedef {import("../task-create/taskCreateContracts").ReturnImportResult} ReturnImportResult */
/** @typedef {{query: {dataset?: string, tab?: string, q?: string, status?: string, page?: string | number}}} DataAssetsRoute */
/**
 * @param {{
 *   route: DataAssetsRoute,
 *   notify: (message: string, tone?: string) => void,
 *   onRouteChange: (changes: Record<string, string | number>) => void,
 * }} props
 */
export function ReturnDataAssetsPage({ route, notify, onRouteChange }) {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [expandedOverride, setExpandedOverride] = useState(
    /** @type {string | null} */ (null),
  );
  const query = route.query.q ?? "";
  const status = ["all", "available", "attention"].includes(route.query.status ?? "")
    ? route.query.status
    : "all";
  const requestedPage = Number(route.query.page) || 1;
  const {
    data: sourceData,
    error: sourcesError,
    isLoading,
    mutate: mutateSources,
  } = useSWR(serverStateKeys.returnSources, async () =>
    canonicalSources(await dataApi.managedDatasets("returns")),
  );
  const sources = useMemo(() => sourceData ?? [], [sourceData]);

  useEffect(() => {
    if (!sourcesError) return;
    notify(
      sourcesError instanceof Error ? sourcesError.message : "用户反馈数据源读取失败",
      "error",
    );
  }, [notify, sourcesError]);

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
  const page = Math.min(requestedPage, totalPages);
  const visibleSources = filteredSources.slice(
    (page - 1) * PAGE_SIZE,
    page * PAGE_SIZE,
  );
  const requestedSource = sources.find((source) =>
    source.member_ids.includes(route.query.dataset ?? ""),
  );
  const defaultExpandedId =
    visibleSources.find((source) => source.id === requestedSource?.id)?.id ||
    visibleSources[0]?.id ||
    "";
  const expandedId = expandedOverride ?? defaultExpandedId;
  const expandedSource = sources.find((source) => source.id === expandedId);
  const {
    data: expandedDetail,
    error: detailError,
    isLoading: detailLoading,
    mutate: mutateDetail,
  } = useSWR(
    expandedSource
      ? serverStateKeys.returnSourceDetails(
          expandedSource.id,
          expandedSource.member_ids,
        )
      : null,
    async () => {
      if (!expandedSource) return null;
      const members = await Promise.all(
        expandedSource.member_ids.map((id) =>
          dataApi.dataset(id, { include: "versions,imports" }),
        ),
      );
      return mergeSourceDetails(expandedSource, members);
    },
  );

  useEffect(() => {
    setExpandedOverride(null);
  }, [route.query.dataset]);

  useEffect(() => {
    if (!detailError) return;
    notify(
      detailError instanceof Error ? detailError.message : "数据源详情读取失败",
      "error",
    );
  }, [detailError, notify]);
  const availableCount = sources.filter(
    (source) => dataStatus(source).value === "available",
  ).length;
  const latestUpdate = sources.reduce(
    (latest, source) =>
      String(source.updated_at || "") > String(latest || "")
        ? (source.updated_at ?? "")
        : latest,
    "",
  );

  /** @param {DatasetSource} source */
  const selectSource = (source) => {
    if (source.id === expandedId) {
      setExpandedOverride("");
      return;
    }
    setExpandedOverride(source.id);
    onRouteChange({ view: "returns", dataset: source.id, tab: "" });
  };

  /** @param {ReturnImportResult} result */
  const finishImport = async (result) => {
    setUploadOpen(false);
    await Promise.all([mutateSources(), mutateDetail()]);
    if (result.dataset?.id) {
      onRouteChange({ view: "returns", dataset: result.dataset.id, tab: "" });
    }
    notify(
      result.duplicate ? "该批次已存在，已定位到原数据源" : "用户反馈数据源已更新",
    );
  };

  return (
    <div className="standard-page data-page returns-assets-page">
      <PageHeading
        eyebrow="数据资产"
        title="用户反馈数据源管理"
        description="管理可复用的用户反馈数据源和最近导入状态。"
        action={
          <Button
            type="primary"
            icon={<UploadSimple size={18} />}
            onClick={() => setUploadOpen(true)}
          >
            导入新批次
          </Button>
        }
      />
      <DataAssetTabs
        current="returns"
        onChange={(view) => onRouteChange({ view, dataset: "", tab: "" })}
      />

      {isLoading && sourceData === undefined ? (
        <section className="content-card returns-assets-loading">
          <InlineLoading label="正在读取用户反馈数据源…" />
        </section>
      ) : sources.length === 0 ? (
        <EmptyState
          icon={FileCsv}
          title="尚未建立用户反馈数据源"
          description="导入首个批次后，系统会识别业务范围并建立可复用的数据源。"
          action={
            <Button
              type="primary"
              icon={<UploadSimple size={17} />}
              onClick={() => setUploadOpen(true)}
            >
              导入首个批次
            </Button>
          }
        />
      ) : (
        <section className="returns-registry" aria-label="用户反馈数据源清单">
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
              <Input
                className="returns-registry-search"
                aria-label="搜索用户反馈数据源"
                prefix={<MagnifyingGlass size={17} />}
                value={query}
                onChange={(event) => onRouteChange({ q: event.target.value, page: 1 })}
                placeholder="搜索数据源或业务范围"
              />
              <label className="returns-registry-filter">
                <Funnel size={17} />
                <select
                  aria-label="按数据状态筛选"
                  value={status}
                  onChange={(event) =>
                    onRouteChange({ status: event.target.value, page: 1 })
                  }
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
                      (expandedDetail ? (
                        <SourceDetail
                          source={expandedDetail}
                          notify={notify}
                          onStorageChanged={async () => {
                            await Promise.all([mutateSources(), mutateDetail()]);
                          }}
                          initiallyShowTrace={["imports", "snapshots"].includes(
                            route.query.tab ?? "",
                          )}
                        />
                      ) : detailLoading ? (
                        <InlineLoading label="正在读取数据源详情…" />
                      ) : null)}
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
                  onClick={() => onRouteChange({ page: page - 1 })}
                >
                  <CaretLeft size={16} />
                </button>
                <b>{page}</b>
                <span>/ {totalPages}</span>
                <button
                  aria-label="下一页"
                  disabled={page === totalPages}
                  onClick={() => onRouteChange({ page: page + 1 })}
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
