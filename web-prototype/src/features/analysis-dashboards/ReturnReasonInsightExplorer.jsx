import { useState } from "react";
import { ArrowCounterClockwise } from "@phosphor-icons/react";
import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { formatPercent } from "./returnReasonInsightPresentation";
import { analysisContextTerms } from "./analysisContextPresentation";

/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel */
/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightHierarchyNode} InsightHierarchyNode */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {{route: DashboardRoute, data: DashboardInsights, reasons: InsightReason[], hierarchy: InsightHierarchyNode[], taxonomyLabels: Map<string, ReviewLabel>, selected?: InsightReason, subjects: InsightReason[], groups: string[], analysisContext: string, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} ReturnReasonInsightExplorerProps */

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
  analysisContext,
  onUpdateRoute,
}) {
  const terms = analysisContextTerms(analysisContext);
  const [selectedSubject, setSelectedSubject] = useState("");
  const visibleReasons = selectedSubject
    ? reasons.filter((reason) => reason.subjects?.includes(selectedSubject))
    : reasons;
  const topReasonCount = Math.max(
    ...visibleReasons.map((item) => item.record_count),
    1,
  );

  /** @param {string} subject */
  const chooseSubject = (subject) => {
    setSelectedSubject(subject);
    const firstReason = subject
      ? reasons.find((reason) => reason.subjects?.includes(subject))
      : reasons[0];
    onUpdateRoute({
      problem:
        selected && (!subject || selected.subjects?.includes(subject))
          ? selected.value
          : firstReason?.value || "",
      recordPage: 1,
    });
  };

  const resetReasonFilters = () => {
    setSelectedSubject("");
    onUpdateRoute({ labelGroup: "", problem: "", recordPage: 1 });
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
            <strong>{formatPercent(subject.percentage)}</strong>
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
                onUpdateRoute({ labelGroup: group, problem: "", recordPage: 1 })
              }
            >
              {group || "全部"}
            </button>
          ))}
        </nav>
      </section>

      <section className="return-reason-ranking">
        <header>
          <div>
            <h3>{terms.reasonHeading}</h3>
            <p>按有效评论排序</p>
          </div>
          <span>{visibleReasons.length} 项</span>
        </header>
        {visibleReasons.length ? (
          <ol>
            {visibleReasons.map((reason, index) => (
              <li key={reason.value}>
                <button
                  className={selected?.value === reason.value ? "active" : ""}
                  onClick={() =>
                    onUpdateRoute({ problem: reason.value, recordPage: 1 })
                  }
                >
                  <span className="return-reason-rank">{index + 1}</span>
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
                    {Number(reason.record_count).toLocaleString()} ·{" "}
                    {formatPercent(reason.percentage)}
                  </strong>
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <div className="return-insight-empty">当前对象下没有匹配原因</div>
        )}
      </section>
      {hierarchy.length > 0 && (
        <section className="return-reason-ranking" aria-label="标签层级统计">
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
                  className={selected?.value === node.value ? "active" : ""}
                  onClick={() => onUpdateRoute({ problem: node.value, recordPage: 1 })}
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
