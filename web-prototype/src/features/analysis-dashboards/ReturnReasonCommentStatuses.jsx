import { SEMANTIC_STATUS_LABELS } from "../classification-results/semanticResultPresentation";
import { COMMENT_STATUS_ORDER } from "./returnReasonInsightPresentation";

/** @param {{statusCounts: Record<string, number> | null, feedbackGroups: boolean}} props */
export function ReturnReasonCommentStatuses({ statusCounts, feedbackGroups }) {
  if (!statusCounts) return null;
  return (
    <section className="return-comment-statuses" aria-label="评论级结论分布">
      <header>
        <b>评论级结论</b>
        <span>互斥口径，每{feedbackGroups ? "个反馈组" : "条评论"}只进入一种状态</span>
      </header>
      <div>
        {COMMENT_STATUS_ORDER.map((status) => (
          <article key={status} className={`is-${status.toLowerCase()}`}>
            <span>{SEMANTIC_STATUS_LABELS[status]}</span>
            <b>{Number(statusCounts[status] || 0).toLocaleString()}</b>
            <small>{feedbackGroups ? "个反馈组" : "条评论"}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
