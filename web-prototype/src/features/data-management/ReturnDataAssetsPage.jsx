import { useEffect, useMemo, useState } from "react";
import { FileCsv, UploadSimple } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { ReturnImportDialog } from "../task-create/ReturnImportDialog";
import { DataAssetTabs } from "./DataAssetTabs";
import { SourceDetail } from "./ReturnDataAssetDetail";
import { ReturnDataAssetRegistry } from "./ReturnDataAssetRegistry";
import {
  dataStatus,
  sourceDisplayName,
  sourceScopeLabel,
} from "./returnDataAssetPresentation";
import { useReturnSources, useReturnSourceDetails } from "./useReturnDataAssetSources";

const PAGE_SIZE = 20;

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetSource} DatasetSource */
/** @typedef {import("../task-create/taskCreateContracts").ReturnImportResult} ReturnImportResult */
/** @typedef {{query: {dataset?: string, tab?: string, q?: string, status?: string, page?: string | number}}} DataAssetsRoute */

/** @param {DataAssetsRoute["query"]} query */
function sourceListQuery(query) {
  return {
    query: query.q ?? "",
    status: ["all", "available", "attention"].includes(query.status ?? "")
      ? query.status
      : "all",
    requestedPage: Number(query.page) || 1,
  };
}

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
  const { query, status, requestedPage } = sourceListQuery(route.query);
  const {
    data: sourceData,
    error: sourcesError,
    isLoading,
    mutate: mutateSources,
  } = useReturnSources();
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
  } = useReturnSourceDetails(expandedSource);

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

  const expandedContent = expandedDetail ? (
    <SourceDetail
      source={expandedDetail}
      notify={notify}
      onStorageChanged={async () => {
        await Promise.all([mutateSources(), mutateDetail()]);
      }}
      initiallyShowTrace={["imports", "snapshots"].includes(route.query.tab ?? "")}
    />
  ) : detailLoading ? (
    <InlineLoading label="正在读取数据源详情…" />
  ) : null;

  return (
    <div className="standard-page data-page returns-assets-page">
      <PageHeading
        eyebrow="数据资产"
        title="用户反馈数据源管理"
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
        <ReturnDataAssetRegistry
          sourceCount={sources.length}
          availableCount={availableCount}
          latestUpdate={latestUpdate}
          query={query}
          status={status}
          onRouteChange={onRouteChange}
          visibleSources={visibleSources}
          expandedId={expandedId}
          selectSource={selectSource}
          filteredCount={filteredSources.length}
          page={page}
          totalPages={totalPages}
          expandedContent={expandedContent}
        />
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
