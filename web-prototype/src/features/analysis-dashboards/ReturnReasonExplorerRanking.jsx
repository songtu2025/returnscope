import { Pagination } from "../../components/Pagination";
import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { formatPercent } from "./returnReasonInsightPresentation";
import { REASON_PAGE_SIZE } from "./returnReasonExplorerPresentation";
/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel */
/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightHierarchyNode} InsightHierarchyNode */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {ReturnType<typeof import("./analysisContextPresentation").analysisContextTerms>} AnalysisContextTerms */
/** @typedef {ReturnType<typeof import("./returnReasonExplorerPresentation").reasonPagePresentation>} ReasonPageView */
/** @typedef {{route: DashboardRoute, subjects: InsightReason[], view: ReasonPageView, selectedSubject: string, pendingReason: string, reasonStatus: string, data: DashboardInsights, taxonomyLabels: Map<string, ReviewLabel>, terms: AnalysisContextTerms, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} ReasonRankingProps */

/** @param {{rank: number, reason: InsightReason, data: DashboardInsights, taxonomyLabels: Map<string, ReviewLabel>, topReasonCount: number}} props */
function ReasonRowLabel({ rank, reason, data, taxonomyLabels, topReasonCount }) {
  return (
    <>
      <span className="return-reason-rank">{rank}</span>
      <div>
        <b>
          {taxonomyLabels.has(reason.value)
            ? taxonomyPath(
                data.taxonomy,
                /** @type {ReviewLabel} */ (taxonomyLabels.get(reason.value)),
              ).join(" → ")
            : reason.label}
        </b>
        <i aria-hidden="true">
          <span
            style={{
              width: `${Math.max(
                (Number(reason.record_count) / topReasonCount) * 100,
                2,
              )}%`,
            }}
          />
        </i>
      </div>
    </>
  );
}

/** @param {{reason: InsightReason, index: number, view: ReasonPageView, pendingReason: string, reasonStatus: string, data: DashboardInsights, taxonomyLabels: Map<string, ReviewLabel>, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
function ReasonChoice({
  reason,
  index,
  view,
  pendingReason,
  reasonStatus,
  data,
  taxonomyLabels,
  onUpdateRoute,
}) {
  const { activeReason, reasonPageStart, topReasonCount } = view;
  return (
    <li>
      <button
        className={[
          activeReason?.value === reason.value ? "active" : "",
          pendingReason === reason.value ? "is-pending" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        aria-label={
          pendingReason === reason.value
            ? `${reason.label}，${reasonStatus}`
            : undefined
        }
        onClick={() =>
          onUpdateRoute({
            problem: reason.value,
            recordPage: 1,
            reasonPage: 0,
          })
        }
      >
        <ReasonRowLabel
          rank={reasonPageStart + index + 1}
          reason={reason}
          data={data}
          taxonomyLabels={taxonomyLabels}
          topReasonCount={topReasonCount}
        />
        <strong>
          {pendingReason === reason.value
            ? reasonStatus
            : `${Number(reason.record_count).toLocaleString()} · ${formatPercent(reason.percentage)}`}
        </strong>
      </button>
    </li>
  );
}

/** @param {ReasonRankingProps} props */
function ReasonList(props) {
  const { view, pendingReason, reasonStatus, data, taxonomyLabels, onUpdateRoute } =
    props;
  const { visibleReasons, reasonPageStart } = view;
  if (!visibleReasons.length)
    return <div className="return-insight-empty">当前对象下没有匹配原因</div>;
  return (
    <ol>
      {visibleReasons
        .slice(reasonPageStart, reasonPageStart + REASON_PAGE_SIZE)
        .map((reason, index) => (
          <ReasonChoice
            key={reason.value}
            reason={reason}
            index={index}
            view={view}
            pendingReason={pendingReason}
            reasonStatus={reasonStatus}
            data={data}
            taxonomyLabels={taxonomyLabels}
            onUpdateRoute={onUpdateRoute}
          />
        ))}
    </ol>
  );
}

/** @param {ReasonRankingProps} props */
export function ReturnReasonExplorerRanking(props) {
  const { route, subjects, view, selectedSubject, terms, onUpdateRoute } = props;
  const { visibleReasons, currentReasonPage, reasonPageCount } = view;
  return (
    <section
      className={`return-reason-ranking${visibleReasons.length > REASON_PAGE_SIZE ? " is-paginated" : ""}`}
    >
      <header>
        <div>
          <h3>{terms.reasonHeading}</h3>
          <p>
            {selectedSubject
              ? `对象：${subjects.find((subject) => subject.value === selectedSubject)?.label} · ${route.labelGroup || "全部类别"}`
              : "按有效评论排序"}
          </p>
        </div>
        <span>{visibleReasons.length} 项</span>
      </header>
      <ReasonList {...props} />
      {visibleReasons.length > REASON_PAGE_SIZE && (
        <Pagination
          page={currentReasonPage}
          pageSize={REASON_PAGE_SIZE}
          total={visibleReasons.length}
          totalPages={reasonPageCount}
          onPage={(reasonPage) => onUpdateRoute({ reasonPage })}
          showTotal={false}
          simple
        />
      )}
    </section>
  );
}

/** @param {{node: InsightHierarchyNode, taxonomyLabels: Map<string, ReviewLabel>, activeReason?: InsightReason, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
function HierarchyChoice({ node, taxonomyLabels, activeReason, onUpdateRoute }) {
  return (
    <li>
      <button
        disabled={!taxonomyLabels.has(node.value)}
        className={activeReason?.value === node.value ? "active" : ""}
        onClick={() =>
          onUpdateRoute({
            problem: node.value,
            recordPage: 1,
            reasonPage: 0,
          })
        }
      >
        <div>
          <b>{node.label_path?.join(" → ") || node.label_name}</b>
        </div>
        <strong>{Number(node.record_count).toLocaleString()} 条</strong>
      </button>
    </li>
  );
}

/** @param {{page: number, hierarchy: InsightHierarchyNode[], taxonomyLabels: Map<string, ReviewLabel>, activeReason?: InsightReason, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
export function ReturnReasonExplorerHierarchy({
  page,
  hierarchy,
  taxonomyLabels,
  activeReason,
  onUpdateRoute,
}) {
  if (!hierarchy.length) return null;
  const pageCount = Math.ceil(hierarchy.length / REASON_PAGE_SIZE);
  const currentPage = Math.min(page || 1, pageCount);
  const pageStart = (currentPage - 1) * REASON_PAGE_SIZE;
  return (
    <section
      className={`return-reason-ranking return-hierarchy-ranking${pageCount > 1 ? " is-paginated" : ""}`}
      aria-label="标签层级统计"
    >
      <header>
        <div>
          <h3>标签层级</h3>
          <p>父级按评论去重；选择末端标签查看诊断</p>
        </div>
        <span>{hierarchy.length} 项</span>
      </header>
      <ol>
        {hierarchy.slice(pageStart, pageStart + REASON_PAGE_SIZE).map((node) => (
          <HierarchyChoice
            key={node.value}
            node={node}
            taxonomyLabels={taxonomyLabels}
            activeReason={activeReason}
            onUpdateRoute={onUpdateRoute}
          />
        ))}
      </ol>
      {pageCount > 1 && (
        <Pagination
          page={currentPage}
          pageSize={REASON_PAGE_SIZE}
          total={hierarchy.length}
          totalPages={pageCount}
          onPage={(hierarchyPage) => onUpdateRoute({ hierarchyPage })}
          showTotal={false}
          simple
        />
      )}
    </section>
  );
}
