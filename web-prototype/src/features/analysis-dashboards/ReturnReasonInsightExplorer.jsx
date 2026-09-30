import { useMemo } from "react";
import { ArrowCounterClockwise } from "@phosphor-icons/react";
import { Pagination } from "../../components/Pagination";
import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { formatPercent } from "./returnReasonInsightPresentation";
import { analysisContextTerms } from "./analysisContextPresentation";

/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel */
/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightHierarchyNode} InsightHierarchyNode */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {{route: DashboardRoute, data: DashboardInsights, reasons: InsightReason[], hierarchy: InsightHierarchyNode[], taxonomyLabels: Map<string, ReviewLabel>, selected?: InsightReason, subjects: InsightReason[], groups: string[], pendingReason?: string, reasonStatus?: string, analysisContext: string, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} ReturnReasonInsightExplorerProps */

const REASON_PAGE_SIZE = 10;

/** @param {ReturnReasonInsightExplorerProps} props */
export function ReturnReasonInsightExplorer({
  route,
  data,
  reasons,
  hierarchy,
  taxonomyLabels,
  selected,
  subjects,
  groups,
  pendingReason = "",
  reasonStatus = "更新中",
  analysisContext,
  onUpdateRoute,
}) {
  const terms = analysisContextTerms(analysisContext);
  const selectedSubject = subjects.some((subject) => subject.value === route.subject)
    ? route.subject
    : "";
  const visibleReasons = useMemo(
    () =>
      selectedSubject
        ? reasons.filter((reason) => reason.subjects?.includes(selectedSubject))
        : reasons,
    [reasons, selectedSubject],
  );
  const reasonPageCount = Math.max(
    1,
    Math.ceil(visibleReasons.length / REASON_PAGE_SIZE),
  );
  const activeReason = pendingReason
    ? selected
    : visibleReasons.find((reason) => reason.value === route.problem) || selected;
  const pageReason =
    visibleReasons.find((reason) => reason.value === pendingReason) || activeReason;
  const selectedIndex = visibleReasons.findIndex(
    (reason) => reason.value === pageReason?.value,
  );
  const selectedReasonPage =
    selectedIndex < 0 ? 1 : Math.floor(selectedIndex / REASON_PAGE_SIZE) + 1;
  const currentReasonPage = Math.min(
    route.reasonPage || selectedReasonPage,
    reasonPageCount,
  );
  const reasonPageStart = (currentReasonPage - 1) * REASON_PAGE_SIZE;
  const topReasonCount = Math.max(
    ...visibleReasons.map((item) => item.record_count),
    1,
  );

  /** @param {string} subject */
  const chooseSubject = (subject) => {
    const firstReason = subject
      ? reasons.find((reason) => reason.subjects?.includes(subject))
      : reasons[0];
    onUpdateRoute({
      subject,
      reasonPage: 0,
      problem:
        activeReason && (!subject || activeReason.subjects?.includes(subject))
          ? activeReason.value
          : firstReason?.value || "",
      recordPage: 1,
    });
  };

  const resetReasonFilters = () => {
    onUpdateRoute({
      subject: "",
      reasonPage: 0,
      labelGroup: "",
      problem: "",
      recordPage: 1,
    });
  };

  return (
    <aside className="return-insight-explorer" aria-label={terms.reasonChooserAria}>
      <header>
        <div>
          <span>1</span>
          <div>
            <h2>选择主题与原因</h2>
            <p>先定位问题对象，再进入具体原因</p>
          </div>
        </div>
        <button onClick={resetReasonFilters}>
          <ArrowCounterClockwise size={15} /> 重置
        </button>
      </header>

      <section className="return-subject-list">
        <h3>问题对象</h3>
        {subjects.map((subject) => (
          <button
            key={subject.value}
            className={selectedSubject === subject.value ? "active" : ""}
            onClick={() =>
              chooseSubject(selectedSubject === subject.value ? "" : subject.value)
            }
          >
            <div>
              <b>{subject.label}</b>
              <span>{subject.record_count} 条评论</span>
            </div>
            <i aria-hidden="true">
              <span style={{ width: `${Math.min(subject.percentage, 100)}%` }} />
            </i>
            <strong>
              {subject.record_count > 0 && subject.percentage === 0
                ? "<0.1%"
                : formatPercent(subject.percentage)}
            </strong>
          </button>
        ))}
      </section>

      <section className="return-reason-groups">
        <h3>原因类别</h3>
        <nav aria-label={terms.reasonCategoryAria}>
          {["", ...groups].map((group) => (
            <button
              key={group || "all"}
              className={route.labelGroup === group ? "active" : ""}
              onClick={() =>
                onUpdateRoute({
                  labelGroup: group,
                  problem: "",
                  recordPage: 1,
                  reasonPage: 0,
                })
              }
            >
              {group || "全部"}
            </button>
          ))}
        </nav>
      </section>

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
        {visibleReasons.length ? (
          <ol>
            {visibleReasons
              .slice(reasonPageStart, reasonPageStart + REASON_PAGE_SIZE)
              .map((reason, index) => (
                <li key={reason.value}>
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
                    <span className="return-reason-rank">
                      {reasonPageStart + index + 1}
                    </span>
                    <div>
                      <b>
                        {taxonomyLabels.has(reason.value)
                          ? taxonomyPath(
                              data.taxonomy,
                              /** @type {ReviewLabel} */ (
                                taxonomyLabels.get(reason.value)
                              ),
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
                    <strong>
                      {pendingReason === reason.value
                        ? reasonStatus
                        : `${Number(reason.record_count).toLocaleString()} · ${formatPercent(reason.percentage)}`}
                    </strong>
                  </button>
                </li>
              ))}
          </ol>
        ) : (
          <div className="return-insight-empty">当前对象下没有匹配原因</div>
        )}
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
      {hierarchy.length > 0 && (
        <section
          className="return-reason-ranking return-hierarchy-ranking"
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
            {hierarchy.map((node) => (
              <li key={node.value}>
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
            ))}
          </ol>
        </section>
      )}
    </aside>
  );
}
