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
              <span>不属于业务标签判断，需由系统重跑或管理员处理。</span>
            </div>
            <span>已锁定编辑</span>
          </header>
          <div className="semantic-review-items">{systemItems.map(renderItem)}</div>
        </section>
      )}
      <section className="semantic-review-group is-business" aria-label="待人工判断">
        <header>
          <div>
            <b>待人工判断 · {displayedSummary.needsReview} 项</b>
            <span>核对业务观点、证据与标签；已归类项也可按证据修正。</span>
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
