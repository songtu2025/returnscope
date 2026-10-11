/** @typedef {import("./semanticLedgerContracts").SemanticReviewLedgerItem} SemanticReviewLedgerItem */

/** @param {import("./semanticLedgerContracts").SemanticLedgerContext & {renderItem: (item: import("../../shared/api/reviewBatchContracts").SemanticReviewLedgerItem) => import("react").ReactNode}} context */
export function SemanticReviewGroups(context) {
  const { systemItems, businessItems, displayedSummary, renderItem } = context;
  return (
    <div className="semantic-review-groups">
      {systemItems.length > 0 && (
        <section className="semantic-review-group is-system" aria-label="系统异常">
          <header>
            <div>
              <b>系统异常 · {systemItems.length} 项</b>
              <span>展示当时分析中记录的技术诊断。</span>
            </div>
            <span>历史记录</span>
          </header>
          <div className="semantic-review-items">{systemItems.map(renderItem)}</div>
        </section>
      )}
      <section className="semantic-review-group is-business" aria-label="待人工判断">
        <header>
          <div>
            <b>待人工判断 · {displayedSummary.needsReview} 项</b>
            <span>展示当时记录的业务观点、证据与人工调整。</span>
          </div>
        </header>
        {businessItems.length > 0 ? (
          <div className="semantic-review-items">{businessItems.map(renderItem)}</div>
        ) : (
          <p className="semantic-review-group-empty">当前没有业务语义项。</p>
        )}
      </section>
    </div>
  );
}
