import { Quotes } from "@phosphor-icons/react";
import { formatPercent, partLabel } from "./returnReasonInsightPresentation";
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {import("./analysisDashboardContracts").InsightSemanticProfile} InsightSemanticProfile */

/** @param {{label: string, items: Array<{key: string, text: string, onClick?: () => void}>}} props */
function SemanticGroup({ label, items }) {
  return (
    <div className="return-semantic-group">
      <b>{label}</b>
      <div>
        {items.length ? (
          items.map((item) =>
            item.onClick ? (
              <button key={item.key} onClick={item.onClick}>
                {item.text}
              </button>
            ) : (
              <span key={item.key}>{item.text}</span>
            ),
          )
        ) : (
          <span>暂无稳定特征</span>
        )}
      </div>
    </div>
  );
}

/** @param {InsightSemanticProfile} semanticProfile @param {InsightReason[]} coReasons @param {(changes: Partial<DashboardRoute>) => void} onUpdateRoute */
function semanticItems(semanticProfile, coReasons, onUpdateRoute) {
  const parts = (semanticProfile.parts ?? []).slice(0, 3).map((item) => ({
    key: item.value,
    text: `${partLabel(item.value)} ${item.record_count}`,
  }));
  const companions = coReasons.slice(0, 3).map((item) => ({
    key: item.value,
    text: `${item.label} ${item.record_count} · ${Number(item.lift || 0).toFixed(2)}×`,
    onClick: () => onUpdateRoute({ problem: item.value, recordPage: 1 }),
  }));
  const opinions = (semanticProfile.opinions ?? []).slice(0, 2).map((item) => ({
    key: `${item.opinion}-${item.part}`,
    text: `${item.opinion} ${item.record_count}`,
  }));
  return { parts, companions, opinions };
}

/** @param {{semanticProfile: InsightSemanticProfile, coReasons: InsightReason[], onUpdateRoute: (changes: Partial<DashboardRoute>) => void}} props */
export function ReturnReasonDiagnosticSemantics({
  semanticProfile,
  coReasons,
  onUpdateRoute,
}) {
  const { parts, companions, opinions } = semanticItems(
    semanticProfile,
    coReasons,
    onUpdateRoute,
  );
  return (
    <section className="return-semantic-profile">
      <header>
        <div>
          <Quotes size={18} />
          <div>
            <h3>语义特征</h3>
            <span>
              {semanticProfile.record_count || 0} 条评论具有对应语义证据 · 覆盖
              {formatPercent(semanticProfile.coverage)}
            </span>
          </div>
        </div>
      </header>
      <div>
        <SemanticGroup label="问题部位" items={parts} />
        <SemanticGroup label="伴随原因" items={companions} />
        <SemanticGroup label="高频表述" items={opinions} />
      </div>
    </section>
  );
}
