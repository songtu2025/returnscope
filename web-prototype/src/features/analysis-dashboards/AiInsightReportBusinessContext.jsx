import { Quotes } from "@phosphor-icons/react";
import { number } from "./AiInsightReportPresentation";
/** @typedef {ReturnType<typeof import("./reportBusinessIssuePresentation").businessIssueView>} BusinessIssueView */

/** @param {{opinions: BusinessIssueView["opinions"], parts: BusinessIssueView["parts"]}} props */
function BusinessIssueOpinions({ opinions, parts }) {
  return (
    <div>
      <span>评论具体在说什么</span>
      {opinions.length > 0 ? (
        <ul>
          {opinions.slice(0, 3).map((opinion, index) => (
            <li key={`${opinion.opinion}-${index}`}>
              <b>{opinion.opinion}</b>
              <small>{number(opinion.record_count).toLocaleString()} 条</small>
            </li>
          ))}
        </ul>
      ) : (
        <p>有效评论尚未形成稳定的具体表述。</p>
      )}
      {parts.length > 0 && (
        <p>
          具体部位：
          {parts
            .slice(0, 3)
            .map((item) => item.value)
            .join("、")}
        </p>
      )}
    </div>
  );
}

/** @param {{view: BusinessIssueView}} props */
export function BusinessIssueContext({ view }) {
  const { terms, opinions, parts, samples } = view;
  if (!opinions.length && !parts.length && !samples.length) return null;
  return (
    <div className="ai-report-business-context">
      <BusinessIssueOpinions opinions={opinions} parts={parts} />
      {samples.length > 0 && (
        <blockquote>
          <Quotes size={18} weight="fill" />
          <p>“{samples[0].comment || samples[0].reason}”</p>
          <cite>{samples[0].product_name || terms.originalFeedback}</cite>
        </blockquote>
      )}
    </div>
  );
}
