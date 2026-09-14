import { Quotes, Target, WarningCircle } from "@phosphor-icons/react";
import {
  Bar,
  BarChart,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatTime } from "../../lib/presentation";
import { EvidenceLine, SectionHeading } from "./AiInsightReportCommon";
import {
  number,
  percent,
  reportLabel,
  STATUS_LABELS,
} from "./AiInsightReportPresentation";

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
  );
}

export function ReportActionsSection({
  primaryAction,
  followupActions,
  informationFinding,
  informationDiagnostic,
  informationReason,
}) {
  return (
    <section className="ai-report-section" id="report-actions">
      <SectionHeading
        number={
          informationFinding || informationDiagnostic || informationReason ? "04" : "03"
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
  );
}

export function ReportBoundarySection({ content }) {
  return (
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
  );
}

export function ReportAppendix({
  attempts,
  report,
  inputTokens,
  outputTokens,
  onSelect,
}) {
  return (
    <>
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
    </>
  );
}
