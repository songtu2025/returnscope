import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowClockwise, MagnifyingGlass, ShieldCheck } from "@phosphor-icons/react";

import { navigateHash } from "../../app/hashRouter";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { dataApi } from "../../shared/api/dataApi";
import { DataAssetTabs } from "./DataAssetTabs";

const ISSUE_LABELS = {
  missing_store: "缺失店铺/站点",
  missing_source_sku: "缺失退货SKU（MSKU）",
  unmatched_product: "未匹配商品",
  missing_category: "缺失品类",
  missing_product_name: "缺失产品名称",
};

const COUNT_FIELDS = [
  ["total_records", "退货记录"],
  ["matched_records", "匹配成功"],
  ["unmatched_records", "未匹配商品"],
  ["missing_store_records", "缺失店铺/站点"],
  ["missing_source_sku_records", "缺失退货SKU（MSKU）"],
  ["missing_category_records", "缺失品类"],
  ["missing_product_name_records", "缺失产品名称"],
];

function numberParam(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function writeQualityRoute(route, changes) {
  navigateHash("data-assets", {
    view: "quality",
    returns_version_id: route.query.returns_version_id || "",
    products_version_id: route.query.products_version_id || "",
    issue_type: route.query.issue_type || "",
    q: route.query.q || "",
    page: numberParam(route.query.page, 1) > 1 ? route.query.page : "",
    page_size:
      numberParam(route.query.page_size, 20) !== 20 ? route.query.page_size : "",
    ...changes,
  });
}

export function DataQualityPage({ route }) {
  const returnsVersionId = route.query.returns_version_id || "";
  const productsVersionId = route.query.products_version_id || "";
  const issueType = route.query.issue_type || "";
  const page = numberParam(route.query.page, 1);
  const pageSize = [20, 50, 100].includes(numberParam(route.query.page_size, 20))
    ? numberParam(route.query.page_size, 20)
    : 20;
  const [queryDraft, setQueryDraft] = useState(route.query.q || "");
  const [versionsState, setVersionsState] = useState({
    loading: true,
    error: "",
    items: [],
  });
  const [planState, setPlanState] = useState({ loading: false, error: "", data: null });
  const [issuesState, setIssuesState] = useState({
    loading: false,
    error: "",
    data: null,
  });
  const pairReady = Boolean(returnsVersionId && productsVersionId);

  useEffect(() => setQueryDraft(route.query.q || ""), [route.query.q]);

  const loadVersions = useCallback(async (signal) => {
    setVersionsState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const items = await dataApi.dataVersions("", { signal });
      setVersionsState({ loading: false, error: "", items });
    } catch (error) {
      if (error.name !== "AbortError") {
        setVersionsState({ loading: false, error: error.message, items: [] });
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    loadVersions(controller.signal);
    return () => controller.abort();
  }, [loadVersions]);

  const loadPlan = useCallback(
    async (signal) => {
      if (!pairReady) return;
      setPlanState({ loading: true, error: "", data: null });
      try {
        const data = await dataApi.qualityPreflight(
          returnsVersionId,
          productsVersionId,
          { signal },
        );
        setPlanState({ loading: false, error: "", data });
      } catch (error) {
        if (error.name !== "AbortError") {
          setPlanState({ loading: false, error: error.message, data: null });
        }
      }
    },
    [pairReady, productsVersionId, returnsVersionId],
  );

  const loadIssues = useCallback(
    async (signal) => {
      if (!pairReady) return;
      setIssuesState({ loading: true, error: "", data: null });
      try {
        const data = await dataApi.qualityIssues(
          {
            returns_version_id: returnsVersionId,
            products_version_id: productsVersionId,
            issue_type: issueType,
            q: route.query.q || "",
            page,
            page_size: pageSize,
          },
          { signal },
        );
        setIssuesState({ loading: false, error: "", data });
      } catch (error) {
        if (error.name !== "AbortError") {
          setIssuesState({ loading: false, error: error.message, data: null });
        }
      }
    },
    [
      issueType,
      page,
      pageSize,
      pairReady,
      productsVersionId,
      returnsVersionId,
      route.query.q,
    ],
  );

  useEffect(() => {
    if (!pairReady) {
      setPlanState({ loading: false, error: "", data: null });
      setIssuesState({ loading: false, error: "", data: null });
      return undefined;
    }
    const planController = new AbortController();
    const issuesController = new AbortController();
    loadPlan(planController.signal);
    loadIssues(issuesController.signal);
    return () => {
      planController.abort();
      issuesController.abort();
    };
  }, [loadIssues, loadPlan, pairReady]);

  const returnsVersions = useMemo(
    () => versionsState.items.filter((item) => item.kind === "returns"),
    [versionsState.items],
  );
  const productsVersions = useMemo(
    () => versionsState.items.filter((item) => item.kind === "products"),
    [versionsState.items],
  );

  return (
    <div className="standard-page data-page data-quality-page">
      <PageHeading
        eyebrow="可复用数据资产"
        title="数据资产"
        description="选择两个不可变版本，检查真实匹配结果和数据问题。"
      />
      <DataAssetTabs
        current="quality"
        onChange={(view) => navigateHash("data-assets", { view })}
      />

      <section className="content-card quality-pair-card">
        <header>
          <div>
            <b>选择质量检查版本对</b>
            <span>退货数据与产品信息都必须明确到具体版本。</span>
          </div>
        </header>
        {versionsState.loading ? (
          <InlineLoading label="正在读取可用数据版本…" />
        ) : versionsState.error ? (
          <LocalError
            title="数据版本读取失败"
            message={versionsState.error}
            onRetry={() => loadVersions()}
          />
        ) : (
          <div className="quality-version-selectors">
            <label>
              退货数据版本
              <select
                value={returnsVersionId}
                onChange={(event) =>
                  writeQualityRoute(route, {
                    returns_version_id: event.target.value,
                    page: "",
                  })
                }
              >
                <option value="">请选择退货数据版本</option>
                {returnsVersions.map((version) => (
                  <option
                    key={version.id ?? version.version_id}
                    value={version.id ?? version.version_id}
                  >
                    {version.dataset_name} · v{version.version}
                  </option>
                ))}
              </select>
            </label>
            <span className="quality-match-arrow">+</span>
            <label>
              产品信息版本
              <select
                value={productsVersionId}
                onChange={(event) =>
                  writeQualityRoute(route, {
                    products_version_id: event.target.value,
                    page: "",
                  })
                }
              >
                <option value="">请选择产品信息版本</option>
                {productsVersions.map((version) => (
                  <option
                    key={version.id ?? version.version_id}
                    value={version.id ?? version.version_id}
                  >
                    {version.dataset_name} · v{version.version}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
      </section>

      {!versionsState.loading && !versionsState.error && !pairReady && (
        <EmptyState
          icon={ShieldCheck}
          title="请先选择完整版本对"
          description="未选齐版本前不会展示旧统计，也不会发起质量计算。"
        />
      )}

      {pairReady && (
        <>
          <section className="content-card quality-plan-card">
            {planState.loading ? (
              <QualityLoading label="正在匹配两个数据版本…" />
            ) : planState.error ? (
              <LocalError
                title="匹配预检失败"
                message={planState.error}
                onRetry={() => loadPlan()}
              />
            ) : planState.data ? (
              <QualityPlan data={planState.data} />
            ) : null}
          </section>

          <section className="content-card quality-issues-card">
            <header>
              <div>
                <b>质量问题记录</b>
                <span>按真实问题类型、业务字段和记录数查看。</span>
              </div>
              <form
                className="quality-issue-search"
                onSubmit={(event) => {
                  event.preventDefault();
                  writeQualityRoute(route, { q: queryDraft.trim(), page: "" });
                }}
              >
                <select
                  aria-label="问题类型"
                  value={issueType}
                  onChange={(event) =>
                    writeQualityRoute(route, {
                      issue_type: event.target.value,
                      page: "",
                    })
                  }
                >
                  <option value="">全部问题</option>
                  {Object.entries(ISSUE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <label>
                  <MagnifyingGlass size={16} />
                  <input
                    aria-label="搜索质量问题"
                    value={queryDraft}
                    onChange={(event) => setQueryDraft(event.target.value)}
                    placeholder="搜索店铺、退货SKU、Listing…"
                  />
                </label>
                <button className="secondary-button">搜索</button>
              </form>
            </header>
            {issuesState.loading ? (
              <QualityLoading label="正在读取质量问题…" />
            ) : issuesState.error ? (
              <LocalError
                title="质量问题读取失败"
                message={issuesState.error}
                onRetry={() => loadIssues()}
              />
            ) : issuesState.data ? (
              <QualityIssues
                data={issuesState.data}
                page={page}
                pageSize={pageSize}
                onPage={(nextPage) => writeQualityRoute(route, { page: nextPage })}
                onPageSize={(nextPageSize) =>
                  writeQualityRoute(route, { page_size: nextPageSize, page: "" })
                }
              />
            ) : null}
          </section>
        </>
      )}
    </div>
  );
}

function QualityLoading({ label }) {
  return (
    <div className="quality-stable-loading">
      <InlineLoading label={label} />
      <span>首次读取大型版本可能需要数秒，请保持页面开启。</span>
    </div>
  );
}

function QualityPlan({ data }) {
  const counts = data.counts ?? {};
  const returnsMatchKey = formatMatchKey(data.match_key?.returns);
  const productsMatchKey = formatMatchKey(data.match_key?.products);
  return (
    <>
      <header className="quality-plan-heading">
        <div>
          <b>版本匹配结果</b>
          <span>
            {data.returns_version?.name || "未提供退货数据"} · v
            {data.returns_version?.version ?? "-"} +{" "}
            {data.products_version?.name || "未提供产品信息"} · v
            {data.products_version?.version ?? "-"}
          </span>
        </div>
        <div className="quality-match-key">
          <span>匹配键</span>
          <b>退货 {returnsMatchKey}</b>
          <span>→</span>
          <b>商品 {productsMatchKey}</b>
        </div>
      </header>
      <div className="quality-count-grid">
        {COUNT_FIELDS.map(([key, label]) => (
          <article key={key}>
            <span>{label}</span>
            <b>{Number(counts[key] ?? 0).toLocaleString()}</b>
          </article>
        ))}
      </div>
      <details className="quality-technical-details">
        <summary>技术信息</summary>
        <code>quality_hash: {data.quality_hash || "未提供"}</code>
      </details>
    </>
  );
}

function formatMatchKey(value) {
  if (Array.isArray(value)) return value.length ? value.join(" + ") : "未提供";
  return value || "未提供";
}

function QualityIssues({ data, page, pageSize, onPage, onPageSize }) {
  const total = Number(data.total || 0);
  const pages = Math.max(Math.ceil(total / pageSize), 1);
  if (!data.items?.length) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="当前筛选没有质量问题"
        description="可调整问题类型或搜索条件。"
      />
    );
  }
  return (
    <>
      <div className="quality-issue-table">
        {data.items.map((item, index) => (
          <article
            key={`${item.issue_type}-${item.store_site}-${item.source_sku}-${index}`}
          >
            <span className="quality-issue-type">
              {ISSUE_LABELS[item.issue_type] ?? item.issue_type}
            </span>
            <QualityIssueField label="店铺/站点" value={item.store_site} />
            <QualityIssueField label="退货SKU（MSKU）" value={item.source_sku} />
            <QualityIssueField label="Listing" value={item.listing} />
            <QualityIssueField label="产品名称" value={item.product_name} />
            <QualityIssueField
              label="品类"
              value={[item.category_a, item.category_b].filter(Boolean).join(" / ")}
            />
            <QualityIssueField label="原因" value={item.reason} />
            <span className="quality-issue-count">
              <small>记录数</small>
              <b>{Number(item.record_count ?? 0).toLocaleString()}</b>
            </span>
          </article>
        ))}
      </div>
      <footer className="quality-pagination">
        <span>
          共 {total.toLocaleString()} 条 · 第 {page}/{pages} 页
        </span>
        <label>
          每页
          <select
            value={pageSize}
            onChange={(event) => onPageSize(Number(event.target.value))}
          >
            {[20, 50, 100].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondary-button"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          上一页
        </button>
        <button
          className="secondary-button"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
        >
          下一页
        </button>
      </footer>
    </>
  );
}

function QualityIssueField({ label, value }) {
  return (
    <span>
      <small>{label}</small>
      <b>{value || "未提供"}</b>
    </span>
  );
}

function LocalError({ title, message, onRetry }) {
  return (
    <div className="plan-state error data-quality-error" role="alert">
      <div>
        <b>{title}</b>
        <p>{message}</p>
      </div>
      <button className="secondary-button" onClick={onRetry}>
        <ArrowClockwise size={16} />
        重新加载
      </button>
    </div>
  );
}
