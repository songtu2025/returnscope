/** @typedef {import("./classificationStandardWorkspaceContracts").StandardWorkspaceContext} StandardWorkspaceContext */

/** @param {Pick<StandardWorkspaceContext,"content"|"baseContent">} context */
export function StandardStrategyChanges({ content, baseContent }) {
  return (
    <>
      {" "}
      {content.recognition_profile !== baseContent?.recognition_profile && (
        <p>
          识别策略：
          {strategyLabel(baseContent?.recognition_profile, false)}
          {" → "}
          {strategyLabel(content.recognition_profile, true)}
        </p>
      )}
      {content.review_role !== baseContent?.review_role && (
        <p>
          复核模型：
          {baseContent?.review_role === "secondary" ? "独立模型" : "主模型"}
          {" → "}
          {content.review_role === "secondary" ? "独立模型" : "主模型"}
        </p>
      )}
    </>
  );
}

/** @param {StandardWorkspaceContext["content"]["recognition_profile"] | undefined} profile @param {boolean} expanded */
function strategyLabel(profile, expanded) {
  if (profile === "fact_v2") {
    return expanded ? "事实策略（对象、条件与证据对齐）" : "事实策略";
  }
  if (profile === "semantic_v1") {
    return expanded ? "语义策略（定义、边界与证据）" : "语义策略";
  }
  return expanded ? "现有策略（定义与关键词）" : "现有策略";
}
