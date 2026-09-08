import {
  CaretRight,
  Check,
  ClockCountdown,
  Database,
  Eye,
  Question,
  ShieldCheck,
  WarningCircle,
} from "@phosphor-icons/react";

const DECISION_LABELS = {
  pending: "待决策",
  ignored: "暂不处理",
  watching: "继续观察",
  verify: "待验证",
};

const READINESS_LABELS = {
  unusable: "不可使用",
  diagnostic_only: "仅供诊断",
  verification_ready: "可进入验证",
};

export function InsightReportVersionSelect({ report, reports, onSelect, optionLabel }) {
  if (reports.length <= 1) return null;

  return (
    <label>
      报告版本
      <select value={report.id} onChange={(event) => onSelect(event.target.value)}>
        {reports.map((item) => (
          <option key={item.id} value={item.id}>
            {optionLabel(item)}
          </option>
        ))}
      </select>
    </label>
  );
}

function number(value) {
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

function percentage(value, signed = false) {
  if (value === null || value === undefined) return "—";
  const parsed = number(value);
  return `${signed && parsed > 0 ? "+" : ""}${parsed.toFixed(1)}%`;
}

function percentagePoints(value) {
  if (value === null || value === undefined) return "—";
  const parsed = number(value);
  return `${parsed > 0 ? "+" : ""}${parsed.toFixed(1)}pp`;
}

function date(value) {
  return value ? String(value).slice(0, 10).replaceAll("-", "/") : "未提供";
}

function issueDecision(report, issueId) {
  return (
    (report.decisions ?? []).find((item) => item.issue_id === issueId)?.status ||
    "pending"
  );
}

function scopeText(scope) {
  return (
    [scope?.listing, scope?.product, scope?.sku].filter(Boolean).join(" / ") ||
    "当前范围"
  );
}

function MetricCard({ label, value, note, tone = "neutral" }) {
  return (
    <div className={`ai-decision-metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

export function AiInsightDecisionReport({
  report,
  reports,
  selectedIssueId,
  decisionState,
  onDecision,
  onSelect,
  onSelectIssue,
}) {
  const content = report.content ?? {};
  const source = report.evidence?.source ?? {};
  const catalog = report.evidence?.catalog ?? {};
  const issues = content.issues ?? [];
  const selectedIssue =
    issues.find((issue) => issue.id === selectedIssueId) ?? issues[0] ?? null;
  const selectedDecision = selectedIssue
    ? issueDecision(report, selectedIssue.id)
    : "pending";
  const readiness = selectedIssue?.readiness ??
    report.quality_gate?.decision_readiness ?? { status: "diagnostic_only" };
  const statusCounts = issues.reduce(
    (counts, issue) => {
      const status = issueDecision(report, issue.id);
      counts[status] = (counts[status] || 0) + 1;
      return counts;
    },
    { pending: 0, watching: 0, verify: 0, ignored: 0 },
  );

  if (!selectedIssue) {
    return (
      <section className="ai-report-empty-state">
        <WarningCircle size={34} weight="duotone" />
        <h2>当前报告没有可判断的问题</h2>
        <p>请检查分类结果覆盖或重新生成报告。</p>
      </section>
    );
  }

  const metrics = selectedIssue.metrics ?? {};
  const pendingReviewCount = number(source.pending_review_record_count);
  const isSaving = decisionState?.loading && decisionState.issueId === selectedIssue.id;

  return (
    <section className="ai-decision-report" aria-labelledby="ai-decision-report-title">
      <header className="ai-decision-report-header">
        <div>
          <span>AI 洞察报告 · 报告 V{report.version_no}</span>
          <h2 id="ai-decision-report-title">{content.title}</h2>
          <p>
            {source.report_profile?.category_name || "通用品类"} · {issues.length}{" "}
            个问题 · {date(source.date_range?.date_from)}–
            {date(source.date_range?.date_to)}
          </p>
        </div>
        <div className="ai-decision-report-tools">
          <strong className={`ai-decision-readiness ${readiness.status}`}>
            {READINESS_LABELS[readiness.status] || readiness.label}
          </strong>
          <InsightReportVersionSelect
            report={report}
            reports={reports}
            onSelect={onSelect}
            optionLabel={(item) => `报告 V${item.version_no}`}
          />
        </div>
      </header>

      <div className="ai-decision-workbench">
        <aside className="ai-decision-queue" aria-label="问题队列">
          <header>
            <div>
              <h3>问题队列</h3>
              <p>按确定性证据排序</p>
            </div>
            <b>{issues.length}</b>
          </header>
          <div className="ai-decision-queue-summary" aria-label="问题状态统计">
            <span>待决策 {statusCounts.pending}</span>
            <span>观察 {statusCounts.watching}</span>
            <span>待验证 {statusCounts.verify}</span>
          </div>
          <ol>
            {issues.map((issue) => {
              const status = issueDecision(report, issue.id);
              return (
                <li key={issue.id}>
                  <button
                    className={issue.id === selectedIssue.id ? "active" : ""}
                    onClick={() => onSelectIssue(issue.id)}
                    aria-current={issue.id === selectedIssue.id ? "true" : undefined}
                  >
                    <span>
                      {String(issue.rank).padStart(2, "0")} ·{" "}
                      {issue.id === selectedIssue.id
                        ? "当前选择"
                        : DECISION_LABELS[status]}
                    </span>
                    <b>{issue.title}</b>
                    <small>{scopeText(issue.scope)}</small>
                    <em>
                      {percentage(issue.metrics?.return_sample_share)} ·{" "}
                      {percentagePoints(issue.metrics?.gap_percentage_points)}
                    </em>
                    <i>{DECISION_LABELS[status]}</i>
                    <CaretRight size={16} />
                  </button>
                </li>
              );
            })}
          </ol>
          <p className="ai-decision-queue-note">这里仅记录判断状态，不下发后续执行。</p>
        </aside>

        <article className="ai-decision-detail">
          <header className="ai-decision-detail-header">
            <div>
              <span>问题 {String(selectedIssue.rank).padStart(2, "0")} · 当前选择</span>
              <h3>{selectedIssue.title}</h3>
              <p>{scopeText(selectedIssue.scope)}</p>
            </div>
            <strong className={`ai-decision-status ${selectedDecision}`}>
              {DECISION_LABELS[selectedDecision]}
            </strong>
          </header>

          <section className="ai-decision-question">
            <div>
              <span>需要你作出的判断</span>
              <h4>{selectedIssue.recommendation?.validation_question}</h4>
            </div>
            <b>约 3 分钟</b>
          </section>

          <div className="ai-decision-metrics">
            <MetricCard
              label="退货样本内占比"
              value={percentage(metrics.return_sample_share)}
              note={`${number(metrics.matched_return_samples)} / ${number(
                metrics.scoped_return_samples,
              )} 条命中`}
            />
            <MetricCard
              label="高于同口径基线"
              value={percentagePoints(metrics.gap_percentage_points)}
              note={
                metrics.baseline_return_sample_share === null ||
                metrics.baseline_return_sample_share === undefined
                  ? "当前没有可用基线"
                  : `整体基线 ${percentage(metrics.baseline_return_sample_share)}`
              }
              tone="risk"
            />
            <MetricCard
              label="近期变化"
              value={percentagePoints(metrics.recent_change_percentage_points)}
              note={
                metrics.trend_direction === "insufficient"
                  ? "趋势样本不足"
                  : `趋势 ${metrics.trend_direction}`
              }
              tone={
                number(metrics.recent_change_percentage_points) > 0 ? "risk" : "neutral"
              }
            />
          </div>

          <section
            className={`ai-decision-trust ${report.quality_gate?.status || "warning"}`}
          >
            <div>
              <ShieldCheck size={22} weight="duotone" />
              <span>证据可信状态</span>
              <strong>{readiness.label || READINESS_LABELS[readiness.status]}</strong>
              <small>{readiness.reason}</small>
            </div>
            <ul>
              <li>
                <Check size={15} /> 已纳入 {number(source.included_record_count)} /{" "}
                {number(source.total_record_count)} 条记录
              </li>
              <li>
                <Check size={15} /> 标签覆盖 {percentage(source.label_coverage)}
              </li>
              {pendingReviewCount > 0 && (
                <li className="warning">
                  <WarningCircle size={15} /> {pendingReviewCount} 条待审核未纳入统计
                </li>
              )}
            </ul>
          </section>

          <section className="ai-decision-evidence">
            <header>
              <strong>证据摘要</strong>
              <span>已知事实与未知问题分开呈现</span>
            </header>
            <div className="ai-decision-evidence-columns">
              <div>
                <h4>
                  <Check size={17} /> 已经知道
                </h4>
                <ul>
                  {(selectedIssue.known ?? []).map((item) => (
                    <li key={item}>
                      <Check size={14} /> {item}
                    </li>
                  ))}
                </ul>
                <p>{selectedIssue.evidence_explanation}</p>
              </div>
              <div>
                <h4>
                  <ClockCountdown size={17} /> 还不知道
                </h4>
                <ul>
                  {(selectedIssue.unknown ?? []).map((item) => (
                    <li key={item}>
                      <Question size={14} /> {item}
                    </li>
                  ))}
                </ul>
                <p className="ai-decision-hypothesis">
                  当前只能提出验证问题，不能据此直接决定如何改商品。
                </p>
              </div>
            </div>
            <footer>
              <span>口径：多标签占比不可直接相加，也不等于退货率。</span>
              <details>
                <summary>
                  <Database size={15} />
                  <span className="ai-evidence-expand-label">
                    查看 {selectedIssue.evidence_ids.length} 项证据
                  </span>
                  <span className="ai-evidence-collapse-label">
                    收起 {selectedIssue.evidence_ids.length} 项证据
                  </span>
                </summary>
                <ul aria-label="证据明细">
                  {selectedIssue.evidence_ids.map((evidenceId) => (
                    <li key={evidenceId}>
                      <b>{catalog[evidenceId]?.label || evidenceId}</b>
                      <span>{catalog[evidenceId]?.value || "结构化证据"}</span>
                    </li>
                  ))}
                </ul>
              </details>
            </footer>
          </section>

          <section className="ai-decision-recommendation">
            <header>
              <div>
                <h4>选择处理方式</h4>
                <p>{selectedIssue.recommendation?.rationale}</p>
              </div>
              <span>{selectedIssue.recommendation?.label}</span>
            </header>
            <ul>
              {(selectedIssue.recommendation?.suggested_evidence ?? []).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            {decisionState?.error && decisionState.issueId === selectedIssue.id && (
              <p className="ai-decision-error" role="alert">
                {decisionState.error}
              </p>
            )}
            <div className="ai-decision-actions">
              <button
                className={selectedDecision === "ignored" ? "active" : ""}
                disabled={isSaving}
                aria-pressed={selectedDecision === "ignored"}
                onClick={() => onDecision(selectedIssue.id, "ignored")}
              >
                暂不处理
              </button>
              <button
                className={selectedDecision === "watching" ? "active" : ""}
                disabled={isSaving}
                aria-pressed={selectedDecision === "watching"}
                onClick={() => onDecision(selectedIssue.id, "watching")}
              >
                <Eye size={16} /> 继续观察
              </button>
              <button
                className={`primary ${selectedDecision === "verify" ? "active" : ""}`}
                disabled={isSaving || readiness.status === "unusable"}
                aria-pressed={selectedDecision === "verify"}
                onClick={() => onDecision(selectedIssue.id, "verify")}
              >
                <ShieldCheck size={16} /> {isSaving ? "正在保存…" : "建议验证"}
              </button>
              <div>
                <span>报告输出</span>
                <b>验证问题 + 所需证据</b>
              </div>
            </div>
          </section>
        </article>
      </div>
    </section>
  );
}
