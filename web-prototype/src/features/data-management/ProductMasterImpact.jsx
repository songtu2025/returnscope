import { ArrowRight } from "@phosphor-icons/react";
import { CardHeading } from "../../components/SharedUi";
import { DatasetReferences } from "./DatasetReferences";
import { formatTime } from "../../lib/presentation";

/** @typedef {import("./productMasterContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("./productMasterContracts").ProductMasterProps} ProductMasterProps */
/** @typedef {ReturnType<typeof import("./useProductMasterState").useProductMasterState>} ProductMasterState */

/** @param {Pick<ProductMasterState,"dimensionAudit"|"currentVersionId"> & {selected: DatasetRecord} & Pick<ProductMasterProps,"routeReferenceVersion"|"routeReferencePage"|"onReferenceRouteChange"|"onNavigate">} props */
export function ProductMasterImpact({
  dimensionAudit,
  currentVersionId,
  selected,
  routeReferenceVersion = "",
  routeReferencePage = 1,
  onReferenceRouteChange,
  onNavigate,
}) {
  return (
    <div className="product-master-impact">
      <section className="dataset-view-panel">
        <CardHeading title="信息修改记录" note="记录原值、新值和修改原因" />
        <div className="data-audit-list">
          {dimensionAudit.map((entry) => (
            <ProductAuditEntry key={entry.id} entry={entry} />
          ))}
          {dimensionAudit.length === 0 && (
            <p className="muted-line">尚无产品信息人工修改。</p>
          )}
        </div>
      </section>
      <DatasetReferences
        versions={selected.versions ?? []}
        currentVersionId={currentVersionId}
        routeVersionId={routeReferenceVersion}
        page={Number(routeReferencePage) || 1}
        onRouteChange={onReferenceRouteChange}
        onNavigate={onNavigate}
      />
    </div>
  );
}

/** @param {{entry: NonNullable<DatasetRecord["audit"]>[number]}} props */
function ProductAuditEntry({ entry }) {
  if (entry.action === "dimension_category_completion")
    return <ProductCategoryAudit entry={entry} />;
  const changes = Object.keys(entry.after?.values ?? {}).filter(
    (field) => entry.before?.values?.[field] !== entry.after?.values?.[field],
  );
  return (
    <div key={entry.id}>
      <b>
        {entry.actor_name} · 第 {(entry.after?.row_index ?? 0) + 2} 行
      </b>
      {changes.map((field) => (
        <p key={field}>
          <span>{field}</span>
          <code>{entry.before?.values?.[field] || "空"}</code>
          <ArrowRight size={12} />
          <code>{entry.after?.values?.[field] || "空"}</code>
        </p>
      ))}
      <small>
        原因：{entry.after?.note} · {formatTime(entry.created_at)}
      </small>
    </div>
  );
}
/** @param {{entry: NonNullable<DatasetRecord["audit"]>[number]}} props */
function ProductCategoryAudit({ entry }) {
  return (
    <div key={entry.id}>
      <b>
        {entry.actor_name} · 批量补充 {(entry.after?.items ?? []).length} 个商品
      </b>
      <p>
        <span>店铺</span>
        <code>{entry.after?.store || "—"}</code>
        <span>品类补充</span>
      </p>
      <small>
        原因：{entry.after?.note} · {formatTime(entry.created_at)}
      </small>
    </div>
  );
}
