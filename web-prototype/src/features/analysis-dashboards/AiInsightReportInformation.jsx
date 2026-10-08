import { Quotes, WarningCircle } from "@phosphor-icons/react";
import {
  Bar,
  BarChart,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EvidenceLine, SectionHeading } from "./AiInsightReportCommon";
import { number, percent } from "./AiInsightReportPresentation";
/** @typedef {import("./analysisDashboardContracts").InsightEvidenceCatalog} InsightEvidenceCatalog */
/** @typedef {import("./analysisDashboardContracts").InsightOpinion} InsightOpinion */
/** @typedef {import("./analysisDashboardContracts").ReportFinding} ReportFinding */
/** @typedef {import("./analysisDashboardContracts").ReportDiagnostic} ReportDiagnostic */
/** @typedef {import("./analysisDashboardContracts").ReportReason} ReportReason */
/** @typedef {import("./analysisDashboardContracts").ReportSample} ReportSample */

/** @param {{rows: InsightOpinion[]}} props */
function OpinionChart({ rows }) {
  return (
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
          tick={{ fill: "#34463d", fontSize: 12 }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          formatter={(value) => [`${number(value).toLocaleString()} 条`, "记录数"]}
        />
        <Bar dataKey="record_count" fill="#5b8574" radius={[0, 3, 3, 0]} barSize={13}>
          <LabelList
            dataKey="record_count"
            position="right"
            formatter={(value) => `${number(value).toLocaleString()} 条`}
            fill="#58655e"
            fontSize={12}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** @param {{opinions: InsightOpinion[]}} props */
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
        <OpinionChart rows={rows} />
      </div>
    </figure>
  );
}

/** @param {{informationFinding?: ReportFinding, informationReason?: ReportReason}} props */
function InformationLead({ informationFinding, informationReason }) {
  return (
    <div className="ai-report-information-lead">
      {informationReason && (
        <div>
          <span>{informationReason.label || "该原因"}占已纳入样本</span>
          <strong>{percent(informationReason.percentage)}</strong>
          <small>{number(informationReason.record_count).toLocaleString()} 条</small>
        </div>
      )}
      <p>
        <b>{informationFinding?.conclusion}</b>
      </p>
      <p>{informationFinding?.interpretation}</p>
    </div>
  );
}

/** @param {{informationSamples: ReportSample[]}} props */
function InformationSamples({ informationSamples }) {
  return (
    <>
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
    </>
  );
}

/** @param {{informationFinding?: ReportFinding, informationDiagnostic?: ReportDiagnostic, informationReason?: ReportReason, informationOpinions: InsightOpinion[], informationSamples: ReportSample[], catalog: InsightEvidenceCatalog}} props */
export function ReportInformationSection({
  informationFinding,
  informationDiagnostic,
  informationReason,
  informationOpinions,
  informationSamples,
  catalog,
}) {
  if (!informationFinding && !informationDiagnostic && !informationReason) return null;

  return (
    <section className="ai-report-section" id="report-information">
      <SectionHeading
        number="03"
        title={informationFinding?.title || "宽泛原因需要进一步拆解"}
        description="区分顾客意图、订单操作和商品问题，避免把非商品原因转化为商品整改。"
      />
      <InformationLead
        informationFinding={informationFinding}
        informationReason={informationReason}
      />
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
      <InformationSamples informationSamples={informationSamples} />
      <div className="ai-report-implication">
        <span>这意味着</span>
        <p>{informationFinding?.implication}</p>
      </div>
      <EvidenceLine ids={informationFinding?.evidence_ids} catalog={catalog} />
    </section>
  );
}
