import {
  ArrowsClockwise,
  CheckCircle,
  Clock,
  Database,
  Quotes,
  ShieldCheck,
  Sparkle,
  Target,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatTime } from "../../lib/presentation";
import { dashboardVersionNumber } from "./dashboardFields";

const STATUS_LABELS = {
  queued: "等待生成",
  running: "正在生成",
  completed: "生成完成",
  failed: "生成失败",
};

const QUALITY_GATE_LABELS = {
  passed: "质量通过",
  warning: "质量警告",
  blocked: "质量阻断",
};

const STAGE_LABELS = {
  queued: "等待生成",
  preparing_evidence: "正在准备确定性证据",
  calling_model: "模型正在解释证据",
  assembling_report: "正在装配报告",
  publishing: "正在发布报告",
};

function reportLabel(report) {
  return report.version_no
    ? `报告 V${report.version_no}`
    : `生成尝试 ${report.attempt_no ?? "-"}`;
}

function number(value) {
  return Number(value || 0);
}

function percent(value) {
  return `${number(value).toFixed(1)}%`;
}

function date(value) {
  return value ? String(value).slice(0, 10).replaceAll("-", "/") : "未提供";
}

function shortDate(value) {
  const text = date(value);
  return text === "未提供" ? text : text.slice(5);
}

function evidenceItems(ids, catalog) {
  return (ids ?? []).map((id) => catalog[id]).filter(Boolean);
}

function EvidenceLine({ ids, catalog }) {
  const items = evidenceItems(ids, catalog);
  if (!items.length) return null;
  return (
    <aside className="ai-report-source-note" aria-label="本节数据证据">
      <span>数据证据 · {items.length} 项</span>
      <div className="ai-report-evidence-list" aria-label="结论证据">
        {items.map((item, index) => (
          <span key={`${item.label}-${index}`}>
            <b>{item.label}</b>
            <small>{item.value}</small>
          </span>
        ))}
      </div>
    </aside>
  );
}

function diagnosticMap(analysis) {
  return new Map(
    (analysis.diagnostics ?? []).map((item) => [String(item.reason_code), item]),
  );
}

function findingReasonCode(finding) {
  const reasonId = (finding?.evidence_ids ?? []).find((item) =>
    String(item).startsWith("reason."),
  );
  return reasonId ? String(reasonId).slice("reason.".length) : "";
}

function mergeSizeTrend(diagnostics, dateTo) {
  const rows = new Map();
  const append = (code, field) => {
    const diagnostic = diagnostics.get(code);
    for (const item of diagnostic?.trend ?? []) {
      if (item.low_sample || (dateTo && item.period_end > dateTo)) continue;
      const row = rows.get(item.period_start) ?? {
        period_start: item.period_start,
        period_end: item.period_end,
        total_record_count: item.total_record_count,
      };
      row[field] = number(item.percentage);
      rows.set(item.period_start, row);
    }
  };
  append("FIT_TOO_SMALL", "too_small");
  append("FIT_TOO_LARGE", "too_large");
  return [...rows.values()]
    .filter((item) => item.too_small !== undefined || item.too_large !== undefined)
    .sort((left, right) => String(left.period_start).localeCompare(right.period_start));
}

function hotspotGroups(diagnostics) {
  const groups = [];
  for (const code of ["FIT_TOO_SMALL", "FIT_TOO_LARGE"]) {
    const diagnostic = diagnostics.get(code);
    const label = diagnostic?.selected_reason?.label || code;
    const rows = [...(diagnostic?.hotspots ?? [])]
      .sort(
        (left, right) =>
          number(right.excess_record_count) - number(left.excess_record_count) ||
          number(right.lift) - number(left.lift),
      )
      .slice(0, 3);
    if (rows.length) groups.push({ code, label, rows });
  }
  return groups;
}

function signedPercentagePoints(value) {
  const numericValue = number(value);
  return `${numericValue > 0 ? "+" : ""}${numericValue.toFixed(1)}pp`;
}

function HotspotBenchmark({ group }) {
  const baseline = number(group.rows[0]?.overall_reason_rate);
  const maxRate = Math.max(
    baseline,
    ...group.rows.map((item) => number(item.product_reason_rate)),
  );
  const upperBound = Math.max(10, Math.ceil((maxRate + 5) / 5) * 5);

  return (
    <figure className="ai-report-benchmark-figure">
      <figcaption>
        <div>
          <span>{group.label}高风险商品</span>
          <b>商品内发生比例与整体基线比较</b>
        </div>
        <strong>整体 {percent(baseline)}</strong>
      </figcaption>
      <div className="ai-report-benchmark-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={group.rows}
            layout="vertical"
            margin={{ top: 10, right: 62, bottom: 8, left: 12 }}
          >
            <CartesianGrid stroke="#e8edea" horizontal={false} />
            <XAxis
              type="number"
              domain={[0, upperBound]}
              tickFormatter={(value) => `${value}%`}
              tick={{ fill: "#7a867f", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              type="category"
              dataKey="value"
              width={170}
              tick={{ fill: "#34463d", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              formatter={(value, name, item) => [
                `${percent(value)} · ${number(item.payload.record_count)} / ${number(
                  item.payload.total_record_count,
                )} 条 · ${number(item.payload.lift).toFixed(2)}×`,
                name,
              ]}
            />
            <ReferenceLine x={baseline} stroke="#8b9690" strokeDasharray="4 4" />
            <Bar
              name="商品内占比"
              dataKey="product_reason_rate"
              fill={group.code === "FIT_TOO_SMALL" ? "#23775e" : "#b77a27"}
              radius={[0, 3, 3, 0]}
              barSize={15}
            >
              <LabelList
                dataKey="product_reason_rate"
                position="right"
                formatter={percent}
                fill="#435249"
                fontSize={10}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p>虚线为整体基线；悬停可查看相关记录、商品样本量和相对倍数。</p>
    </figure>
  );
}

function OpinionRanking({ opinions }) {
  const rows = [...opinions]
    .sort((left, right) => number(right.record_count) - number(left.record_count))
    .slice(0, 4);
  if (!rows.length) return null;
  return (
    <figure className="ai-report-opinion-figure">
      <figcaption>
        <b>“买家原因”中的高频具体意图</b>
        <span>按语义单元命中记录数排序</span>
      </figcaption>
      <div className="ai-report-opinion-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={rows}
            layout="vertical"
            margin={{ top: 4, right: 60, bottom: 4, left: 10 }}
          >
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="opinion"
              width={165}
              tick={{ fill: "#34463d", fontSize: 10 }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              formatter={(value) => [`${number(value).toLocaleString()} 条`, "记录数"]}
            />
            <Bar
              dataKey="record_count"
              fill="#5b8574"
              radius={[0, 3, 3, 0]}
              barSize={13}
            >
              <LabelList
                dataKey="record_count"
                position="right"
                formatter={(value) => `${number(value).toLocaleString()} 条`}
                fill="#58655e"
                fontSize={10}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

function reasonSamples(diagnostic) {
  return (diagnostic?.samples ?? []).filter(
    (item, index, items) =>
      index ===
      items.findIndex(
        (candidate) =>
          (candidate.comment || candidate.reason) === (item.comment || item.reason),
      ),
  );
}

function SectionHeading({ number: sectionNumber, title, description }) {
  return (
    <header className="ai-report-section-heading">
      <span>{sectionNumber}</span>
      <div>
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </div>
    </header>
  );
}

function ReportStatus({ report, latestReport, onRetry, onSelect }) {
  const running = report.status === "queued" || report.status === "running";
  const historicalFailure =
    report.status === "failed" && latestReport && latestReport.id !== report.id;
  return (
    <section className={`ai-report-runtime-state ${report.status}`} role="status">
      {running ? <Clock size={28} /> : <WarningCircle size={28} />}
      <div>
        <span>
          {historicalFailure ? "历史生成记录 · " : ""}
          {reportLabel(report)}
        </span>
        <h2>
          {running
            ? "AI 正在生成洞察报告"
            : historicalFailure
              ? "这是一次历史生成失败"
              : "本次报告生成失败"}
        </h2>
        <p>
          {running
            ? `${STAGE_LABELS[report.stage] || "系统正在生成报告"}。可以离开当前页面，进度也会显示在首页。`
            : historicalFailure
              ? `这次生成没有发布，也不会影响当前的报告 V${latestReport.version_no}。`
              : report.error || "模型没有返回可用的结构化报告。"}
        </p>
        <small>
          {report.model_name || report.model_key} · {report.reasoning_effort} 推理强度
        </small>
      </div>
      {historicalFailure && (
        <button className="primary-button" onClick={() => onSelect(latestReport.id)}>
          <CheckCircle size={17} /> 查看最新报告
        </button>
      )}
      {running && latestReport && (
        <button className="secondary-button" onClick={() => onSelect(latestReport.id)}>
          查看已发布报告
        </button>
      )}
      {report.status === "failed" && !historicalFailure && (
        <button className="primary-button" onClick={onRetry}>
          <ArrowsClockwise size={17} /> 重试
        </button>
      )}
    </section>
  );
}

export function AiInsightReport({
  report,
  reports,
  attempts = [],
  latestReport,
  dashboard,
  version,
  onGenerate,
  onRetry,
  onSelect,
}) {
  if (!report) {
    return (
      <section className="ai-report-empty-state">
        <Sparkle size={34} weight="duotone" />
        <h2>当前数据版本还没有 AI 洞察报告</h2>
        <p>生成尝试会保留过程记录，只有成功发布后才产生报告版本号。</p>
        <button className="primary-button" onClick={onGenerate}>
          生成第一版报告
        </button>
      </section>
    );
  }

  if (report.status !== "completed") {
    return (
      <ReportStatus
        report={report}
        latestReport={latestReport}
        onRetry={onRetry}
        onSelect={onSelect}
      />
    );
  }

  const content = report.content ?? {};
  const evidence = report.evidence ?? {};
  const analysis = evidence.analysis ?? {};
  const source = evidence.source ?? {};
  const catalog = evidence.catalog ?? {};
  const summary = analysis.summary ?? {};
  const groups = analysis.label_group_breakdown ?? [];
  const findings = content.findings ?? [];
  const diagnostics = diagnosticMap(analysis);
  const structureFinding =
    findings.find((item) => item.kind === "structure") ?? findings[0];
  const diagnosticFinding = findings.find((item) => item.kind === "diagnostic");
  const informationFinding = findings.find((item) => item.kind === "information");
  const otherFindings = findings.filter(
    (item) =>
      item !== structureFinding &&
      item !== diagnosticFinding &&
      item !== informationFinding,
  );
  const primaryGroup = groups.find((item) => item.value !== "其他原因") ?? groups[0];
  const maxGroupCount = Math.max(...groups.map((item) => number(item.record_count)), 1);
  const sizeTrend = mergeSizeTrend(diagnostics, source.date_range?.date_to);
  const hotspotBenchmarks = hotspotGroups(diagnostics);
  const smallTrend = diagnostics.get("FIT_TOO_SMALL")?.trend_summary ?? {};
  const largeTrend = diagnostics.get("FIT_TOO_LARGE")?.trend_summary ?? {};
  const informationReasonCode = findingReasonCode(informationFinding);
  const informationDiagnostic = diagnostics.get(informationReasonCode);
  const informationReason =
    informationDiagnostic?.selected_reason ??
    (analysis.reasons ?? []).find(
      (item) => String(item.value) === informationReasonCode,
    );
  const informationOpinions = informationDiagnostic?.semantic_profile?.opinions ?? [];
  const informationSamples = reasonSamples(informationDiagnostic);
  const productMapping = source.product_mapping ?? {};
  const textQuality = source.text_quality ?? report.quality_gate?.text_quality ?? {};
  const qualityStatus = report.quality_gate?.status;
  const decisionReadiness = report.quality_gate?.decision_readiness;
  const inputTokens = number(report.usage?.input_tokens);
  const outputTokens = number(report.usage?.output_tokens);
  const actions = [...(content.actions ?? [])].sort(
    (left, right) =>
      ({ P0: 0, P1: 1, P2: 2 })[left.priority] -
      { P0: 0, P1: 1, P2: 2 }[right.priority],
  );
  const [primaryAction, ...followupActions] = actions;

  const scrollTo = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="ai-insight-report ai-generated-report">
      <header className="ai-report-cover" aria-labelledby="ai-report-name">
        <div>
          <span>AI 洞察报告 · 报告 V{report.version_no}</span>
          <h2 id="ai-report-name">{content.title || `${dashboard.name}洞察报告`}</h2>
          <p>
            分析周期 {date(source.date_range?.date_from)}–
            {date(source.date_range?.date_to)}
            <i />
            数据版本 v
            {report.dashboard_version_no || dashboardVersionNumber(version) || 1}
          </p>
        </div>
        <div className="ai-report-cover-status">
          <span>
            {report.resolved_model || report.model_name || report.model_key} ·{" "}
            {report.reasoning_effort}
          </span>
          {source.report_status === "provisional" && (
            <strong className="ai-report-provisional">临时报告</strong>
          )}
          <strong className="ai-report-generation-status">
            <CheckCircle size={17} /> {STATUS_LABELS[report.status]}
          </strong>
          {qualityStatus && (
            <strong className={`ai-report-quality-status ${qualityStatus}`}>
              {QUALITY_GATE_LABELS[qualityStatus] || qualityStatus}
            </strong>
          )}
          {decisionReadiness?.status && (
            <strong
              className={`ai-report-decision-status ${decisionReadiness.status}`}
              title={decisionReadiness.reason}
            >
              {decisionReadiness.label || decisionReadiness.status}
            </strong>
          )}
          {reports.length > 1 && (
            <label>
              报告版本
              <select
                value={report.id}
                onChange={(event) => onSelect(event.target.value)}
              >
                {reports.map((item) => (
                  <option key={item.id} value={item.id}>
                    {reportLabel(item)} · {STATUS_LABELS[item.status]}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </header>

      <nav className="ai-report-chapters" aria-label="报告目录">
        <button onClick={() => scrollTo("report-summary")}>执行摘要</button>
        <button onClick={() => scrollTo("report-structure")}>问题结构</button>
        <button onClick={() => scrollTo("report-diagnostic")}>尺码诊断</button>
        <button onClick={() => scrollTo("report-actions")}>行动计划</button>
      </nav>

      <article className="ai-report-document">
        <section className="ai-report-executive" id="report-summary">
          <span className="ai-report-eyebrow">Executive Summary</span>
          <h3>执行摘要</h3>
          <ol className="ai-report-summary-list ai-report-generated-summary">
            {(content.executive_summary ?? []).map((item, index) => (
              <li className={item.tone || "neutral"} key={item.title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <b>{item.title}</b>
                  <p>{item.statement}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="ai-report-trust-strip" aria-label="报告可信范围">
            <div>
              <Database size={18} />
              <span>已纳入</span>
              <b>{number(summary.record_count).toLocaleString()} 条</b>
            </div>
            <div>
              <ShieldCheck size={18} />
              <span>标签覆盖</span>
              <b>{percent(source.label_coverage)}</b>
            </div>
            <div
              className={number(summary.pending_review_record_count) ? "warning" : ""}
            >
              <WarningCircle size={18} />
              <span>待审核</span>
              <b>{number(summary.pending_review_record_count).toLocaleString()} 条</b>
            </div>
            <p>
              多标签问题占比不可直接相加；当前占比描述退货样本结构，不代表真实退货率。
            </p>
          </div>
          {productMapping.status === "needs_review" && (
            <div className="ai-report-review-note">
              <b>商品主数据需先核对：</b> {productMapping.note}
            </div>
          )}
          {textQuality.status === "needs_review" && (
            <div className="ai-report-review-note">
              <b>评论文本质量未通过：</b> {textQuality.note}
              本报告只可用于定位数据问题，不可直接下发商品整改。
            </div>
          )}
        </section>

        <section className="ai-report-section" id="report-structure">
          <SectionHeading
            number="01"
            title={structureFinding?.title || "退货问题结构"}
            description="先区分可行动的商品问题与宽泛的非商品原因。"
          />
          <div className="ai-report-editorial-intro">
            <p>
              <b>{structureFinding?.conclusion}</b>
            </p>
            <p>{structureFinding?.interpretation}</p>
          </div>
          {groups.length > 0 && (
            <figure className="ai-report-structure-figure">
              <figcaption>
                <div>
                  <span>首要可行动问题</span>
                  <strong>{primaryGroup?.value || "当前问题组"}</strong>
                </div>
                <b>{percent(primaryGroup?.percentage)}</b>
                <small>
                  {number(primaryGroup?.record_count).toLocaleString()} 条相关记录
                </small>
              </figcaption>
              <div className="ai-report-size-bars" aria-label="退货问题组规模比较">
                {groups.slice(0, 6).map((group) => (
                  <div key={group.value}>
                    <span>{group.value}</span>
                    <i aria-hidden="true">
                      <span
                        style={{
                          width: `${Math.max(
                            (number(group.record_count) / maxGroupCount) * 100,
                            2,
                          )}%`,
                        }}
                      />
                    </i>
                    <b>{percent(group.percentage)}</b>
                    <em>{number(group.record_count).toLocaleString()} 条</em>
                  </div>
                ))}
              </div>
            </figure>
          )}
          <div className="ai-report-implication">
            <span>这意味着</span>
            <p>{structureFinding?.implication}</p>
          </div>
          <EvidenceLine ids={structureFinding?.evidence_ids} catalog={catalog} />
        </section>

        {(diagnosticFinding || sizeTrend.length > 0 || otherFindings.length > 0) && (
          <section className="ai-report-section" id="report-diagnostic">
            <SectionHeading
              number="02"
              title={diagnosticFinding?.title || "关键发现与业务含义"}
              description="比较时间变化和商品内部发生比例，避免把总量误当成整改优先级。"
            />
            {diagnosticFinding && (
              <div className="ai-report-editorial-intro">
                <p>
                  <b>{diagnosticFinding.conclusion}</b>
                </p>
                <p>{diagnosticFinding.interpretation}</p>
              </div>
            )}

            {(smallTrend.status === "available" ||
              largeTrend.status === "available") && (
              <div className="ai-report-delta-strip" aria-label="尺码问题趋势变化摘要">
                {smallTrend.status === "available" && (
                  <div className="small">
                    <span>偏小 · 最近 {number(smallTrend.window_weeks)} 周</span>
                    <strong>
                      {signedPercentagePoints(smallTrend.delta_percentage_points)}
                    </strong>
                    <p>
                      {percent(smallTrend.early_rate)} →{" "}
                      {percent(smallTrend.recent_rate)}
                    </p>
                  </div>
                )}
                {largeTrend.status === "available" && (
                  <div className="large">
                    <span>偏大 · 最近 {number(largeTrend.window_weeks)} 周</span>
                    <strong>
                      {signedPercentagePoints(largeTrend.delta_percentage_points)}
                    </strong>
                    <p>
                      {percent(largeTrend.early_rate)} →{" "}
                      {percent(largeTrend.recent_rate)}
                    </p>
                  </div>
                )}
              </div>
            )}

            {sizeTrend.length >= 8 && (
              <figure className="ai-report-trend-figure">
                <figcaption>
                  <div>
                    <b>偏小与偏大问题占比趋势</b>
                    <span>按完整自然周统计，占当周已分析退货记录的比例</span>
                  </div>
                  <div className="ai-report-chart-legend" aria-label="图例">
                    <span>
                      <i className="small" />
                      偏小
                      {smallTrend.status === "available" && (
                        <b>{percent(smallTrend.recent_rate)}</b>
                      )}
                    </span>
                    <span>
                      <i className="large" />
                      偏大
                      {largeTrend.status === "available" && (
                        <b>{percent(largeTrend.recent_rate)}</b>
                      )}
                    </span>
                  </div>
                </figcaption>
                <div
                  className="ai-report-trend-chart"
                  role="img"
                  aria-label="偏小与偏大问题占比的每周变化"
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={sizeTrend}
                      margin={{ top: 12, right: 18, bottom: 4, left: 0 }}
                    >
                      <CartesianGrid stroke="#e5ebe7" vertical={false} />
                      <XAxis
                        dataKey="period_start"
                        tickFormatter={shortDate}
                        tick={{ fill: "#66736c", fontSize: 10 }}
                        tickLine={false}
                        axisLine={{ stroke: "#cfd9d3" }}
                        minTickGap={34}
                      />
                      <YAxis
                        domain={[0, "auto"]}
                        tickFormatter={(value) => `${value}%`}
                        tick={{ fill: "#66736c", fontSize: 10 }}
                        tickLine={false}
                        axisLine={false}
                        width={38}
                      />
                      <Tooltip
                        labelFormatter={(value) => `周起始 ${date(value)}`}
                        formatter={(value, name) => [
                          `${number(value).toFixed(1)}%`,
                          name,
                        ]}
                      />
                      <Line
                        name="偏小"
                        type="monotone"
                        dataKey="too_small"
                        stroke="#176f56"
                        strokeWidth={2.4}
                        dot={false}
                        activeDot={{ r: 4 }}
                        connectNulls
                      />
                      <Line
                        name="偏大"
                        type="monotone"
                        dataKey="too_large"
                        stroke="#b7791f"
                        strokeWidth={2.4}
                        dot={false}
                        activeDot={{ r: 4 }}
                        connectNulls
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <p>
                  趋势用于识别问题方向变化；它描述样本结构，不能单独证明尺码设计变化造成了结果。
                </p>
              </figure>
            )}

            {hotspotBenchmarks.length > 0 && (
              <div className="ai-report-benchmark-section">
                <div className="ai-report-subheading">
                  <span>商品热点与整体基线</span>
                  <p>优先关注“商品内占比明显高于整体、且超额记录较多”的商品。</p>
                </div>
                {hotspotBenchmarks.map((group) => (
                  <HotspotBenchmark group={group} key={group.code} />
                ))}
              </div>
            )}

            {diagnosticFinding && (
              <div className="ai-report-implication">
                <span>这意味着</span>
                <p>{diagnosticFinding.implication}</p>
              </div>
            )}

            {diagnosticFinding && (
              <EvidenceLine ids={diagnosticFinding.evidence_ids} catalog={catalog} />
            )}
            {otherFindings.length > 0 && (
              <div className="ai-report-generated-findings">
                {otherFindings.map((finding) => (
                  <article key={finding.id || finding.title}>
                    <h4>{finding.title}</h4>
                    <b>{finding.conclusion}</b>
                    <p>{finding.interpretation}</p>
                    <p>
                      <b>业务含义：</b>
                      {finding.implication}
                    </p>
                  </article>
                ))}
              </div>
            )}
          </section>
        )}

        {(informationFinding || informationDiagnostic || informationReason) && (
          <section className="ai-report-section" id="report-information">
            <SectionHeading
              number="03"
              title={informationFinding?.title || "宽泛原因需要进一步拆解"}
              description="区分顾客意图、订单操作和商品问题，避免把非商品原因转化为商品整改。"
            />
            <div className="ai-report-information-lead">
              {informationReason && (
                <div>
                  <span>{informationReason.label || "该原因"}占已纳入样本</span>
                  <strong>{percent(informationReason.percentage)}</strong>
                  <small>
                    {number(informationReason.record_count).toLocaleString()} 条
                  </small>
                </div>
              )}
              <p>
                <b>{informationFinding?.conclusion}</b>
              </p>
              <p>{informationFinding?.interpretation}</p>
            </div>
            {informationDiagnostic ? (
              <OpinionRanking opinions={informationOpinions} />
            ) : (
              <div className="ai-report-missing-diagnostic" role="status">
                <WarningCircle size={18} />
                <span>
                  当前历史报告未保存该原因的语义诊断；占比来自分类结果，
                  高频表述和原始评论暂不展示。
                </span>
              </div>
            )}
            {informationSamples.length > 0 && (
              <blockquote className="ai-report-featured-quote">
                <Quotes size={22} weight="fill" />
                <p>“{informationSamples[0].comment || informationSamples[0].reason}”</p>
                <cite>{informationSamples[0].product_name || "未提供商品名称"}</cite>
              </blockquote>
            )}
            {informationSamples.length > 1 && (
              <details className="ai-report-quote-details">
                <summary>
                  <Quotes size={16} /> 查看更多代表性原始评论
                </summary>
                <div>
                  {informationSamples.slice(1, 3).map((sample, index) => (
                    <blockquote key={`${sample.comment || sample.reason}-${index}`}>
                      “{sample.comment || sample.reason}”
                      <cite>{sample.product_name || "未提供商品名称"}</cite>
                    </blockquote>
                  ))}
                </div>
              </details>
            )}
            <div className="ai-report-implication">
              <span>这意味着</span>
              <p>{informationFinding?.implication}</p>
            </div>
            <EvidenceLine ids={informationFinding?.evidence_ids} catalog={catalog} />
          </section>
        )}

        <section className="ai-report-section" id="report-actions">
          <SectionHeading
            number={
              informationFinding || informationDiagnostic || informationReason
                ? "04"
                : "03"
            }
            title="按证据强度执行行动计划"
            description="每项行动绑定目标对象和可观察的验证条件。"
          />
          {primaryAction && (
            <article className="ai-report-primary-action">
              <span>{primaryAction.priority} · 首要行动</span>
              <h4>{primaryAction.target || "对应问题范围"}</h4>
              <p>{primaryAction.action}</p>
              <div>
                <b>验证标准</b>
                <p>{primaryAction.success_signal}</p>
              </div>
              {primaryAction.rationale && (
                <details>
                  <summary>查看优先依据</summary>
                  <p>{primaryAction.rationale}</p>
                </details>
              )}
            </article>
          )}
          {followupActions.length > 0 && (
            <div className="ai-report-followup-actions">
              {followupActions.map((action) => (
                <article key={action.id || action.action}>
                  <span>{action.priority}</span>
                  <div>
                    <h4>{action.target || "对应问题范围"}</h4>
                    <p>{action.action}</p>
                    <small>
                      <b>验证：</b>
                      {action.success_signal}
                    </small>
                    {action.rationale && (
                      <details>
                        <summary>查看行动依据</summary>
                        <p>{action.rationale}</p>
                      </details>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="ai-report-section ai-report-boundary" id="report-boundary">
          <div className="ai-report-open-questions">
            <Target size={20} />
            <b>仍需回答的问题</b>
            <ul>
              {(content.further_questions ?? []).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
          {(content.caveats ?? []).length > 0 && (
            <>
              <p className="ai-report-primary-caveat">
                <WarningCircle size={16} /> {content.caveats[0]}
              </p>
              {(content.caveats ?? []).length > 1 && (
                <details className="ai-report-limitations">
                  <summary>查看其余报告口径与限制</summary>
                  <ul>
                    {content.caveats.slice(1).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </section>
      </article>

      {attempts.length > 0 && (
        <details className="ai-report-attempt-history">
          <summary>
            <span>生成记录</span>
            <small>{attempts.length} 条过程记录</small>
          </summary>
          <div className="ai-report-attempt-list">
            {attempts.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-label={`查看${reportLabel(item)}`}
                onClick={() => onSelect(item.id)}
              >
                <span>
                  <b>{reportLabel(item)}</b>
                  <small>
                    {item.model_name || item.model_key} · {item.reasoning_effort}{" "}
                    推理强度
                  </small>
                </span>
                <strong className={item.status}>{STATUS_LABELS[item.status]}</strong>
              </button>
            ))}
          </div>
        </details>
      )}

      <footer className="ai-report-footer">
        <span>生成于 {formatTime(report.completed_at)}</span>
        <span>提示词 {report.prompt_version}</span>
        {(inputTokens > 0 || outputTokens > 0) && (
          <span>
            输入 {inputTokens.toLocaleString()} · 输出 {outputTokens.toLocaleString()}{" "}
            tokens
          </span>
        )}
        <small>
          本报告绑定证据哈希 {String(report.evidence_hash || "").slice(0, 12)}
        </small>
      </footer>
    </div>
  );
}
