import { AuditDiff } from "../system-settings/AuditLogDiff";
import { CardHeading } from "../../components/SharedUi";
import { DatasetReferences } from "./DatasetReferences";
import { formatTime } from "../../lib/presentation";
import { HistoryRestoreButton } from "../../components/HistoryRestoreButton";
import { restoreProductChange } from "../../shared/api/historyRestore";

/** @typedef {import("./productMasterContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("./productMasterContracts").ProductMasterProps} ProductMasterProps */
/** @typedef {ReturnType<typeof import("./useProductMasterState").useProductMasterState>} ProductMasterState */

/** @param {Pick<ProductMasterState,"dimensionAudit"|"currentVersionId"|"onProductChanged"> & Pick<ProductMasterProps,"routeReferencePage"|"onReferenceRouteChange"|"onNavigate"> & {selected: DatasetRecord}} props */
export function ProductMasterImpact({
  dimensionAudit,
  currentVersionId,
  routeReferencePage = 1,
  onReferenceRouteChange,
  onNavigate,
  selected,
  onProductChanged,
}) {
  return (
    <div className="product-master-impact">
      <section className="dataset-view-panel">
        <CardHeading title="信息修改记录" />
        <div className="data-audit-list">
          {dimensionAudit.map((entry) => (
            <div key={entry.id}>
              <ProductAuditEntry entry={entry} />
              {entry.action === "dimension_row_update" && (
                <HistoryRestoreButton
                  onRestore={async () => {
                    const updated = await restoreProductChange(
                      selected.id,
                      entry.id,
                      selected.current_version,
                    );
                    await onProductChanged(updated);
                  }}
                />
              )}
            </div>
          ))}
          {dimensionAudit.length === 0 && (
            <p className="muted-line">尚无产品信息人工修改。</p>
          )}
        </div>
      </section>
      <DatasetReferences
        currentVersionId={currentVersionId}
        page={Number(routeReferencePage) || 1}
        onRouteChange={onReferenceRouteChange}
        onNavigate={onNavigate}
      />
    </div>
  );
}

/** @param {{entry: NonNullable<DatasetRecord["audit"]>[number]}} props */
function ProductAuditEntry({ entry }) {
  const update = entry.action === "product_update";
  const category = entry.action === "dimension_category_completion";
  const title = update
    ? "产品资料更新"
    : category
      ? `批量补充 ${(entry.after?.items ?? []).length} 个商品`
      : `修改第 ${(entry.after?.row_index ?? 0) + 2} 行`;
  return (
    <div className="product-audit-entry">
      <header>
        <b>
          {entry.actor_name || "未提供操作人"} · {title}
        </b>
        <time>{formatTime(entry.created_at)}</time>
      </header>
      {category ? (
        <p>店铺：{entry.after?.store || "--"} · 品类补充</p>
      ) : (
        <AuditDiff
          partialAfter={entry.action === "dimension_row_update"}
          before={
            update ? { 产品记录数: entry.before?.row_count } : entry.before?.values
          }
          after={update ? { 产品记录数: entry.after?.row_count } : entry.after?.values}
        />
      )}
      {entry.after?.note && (
        <p className="product-audit-reason">修改原因：{entry.after.note}</p>
      )}
    </div>
  );
}
