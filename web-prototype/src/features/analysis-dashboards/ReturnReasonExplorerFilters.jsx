import { ArrowCounterClockwise } from "@phosphor-icons/react";
import { formatPercent } from "./returnReasonInsightPresentation";
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {ReturnType<typeof import("./analysisContextPresentation").analysisContextTerms>} AnalysisContextTerms */

/** @param {{onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
function ExplorerHeader({ onUpdateRoute }) {
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
  );
}

/** @param {{subjects: InsightReason[], selectedSubject: string, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
function SubjectSelector({ subjects, selectedSubject, onUpdateRoute }) {
  /** @param {string} subject */
  const chooseSubject = (subject) => {
    onUpdateRoute({
      subject,
      labelGroup: "",
      reasonPage: 0,
      problem: "",
      recordPage: 1,
    });
  };

  return (
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
  );
}

/** @param {{route: DashboardRoute, groups: string[], terms: AnalysisContextTerms, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
function ReasonGroups({ route, groups, terms, onUpdateRoute }) {
  return (
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
  );
}

/** @param {{route: DashboardRoute, groups: string[], terms: AnalysisContextTerms, subjects: InsightReason[], selectedSubject: string, onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
export function ReturnReasonExplorerFilters({
  route,
  groups,
  terms,
  subjects,
  selectedSubject,
  onUpdateRoute,
}) {
  return (
    <>
      <ExplorerHeader onUpdateRoute={onUpdateRoute} />
      <SubjectSelector
        subjects={subjects}
        selectedSubject={selectedSubject}
        onUpdateRoute={onUpdateRoute}
      />
      <ReasonGroups
        route={route}
        groups={groups}
        terms={terms}
        onUpdateRoute={onUpdateRoute}
      />
    </>
  );
}
