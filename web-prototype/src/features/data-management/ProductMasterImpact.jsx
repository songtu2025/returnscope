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
        <CategoryCompletionDetails entry={entry} />
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

/** @typedef {{store?: string, msku?: string, category_a?: string, category_b?: string, rows?: number[]}} CategoryAuditItem */

/** @param {{entry: NonNullable<DatasetRecord["audit"]>[number]}} props */
function CategoryCompletionDetails({ entry }) {
  const items = /** @type {CategoryAuditItem[]} */ (entry.after?.items ?? []);
  const before = /** @type {CategoryAuditItem[]} */ (entry.before?.items ?? []);
  return (
    <>
      <p>店铺：{entry.after?.store || "--"} · 品类补充</p>
      {items.map((item, index) => {
        const store = item.store || entry.after?.store;
        // 审计按店铺与 MSKU 保存身份，不能按数组位置或仅按 MSKU 配对。
        const previous =
          item.msku && store
            ? before.find((value) => value.store === store && value.msku === item.msku)
            : undefined;
        return (
          <CategoryCompletionItem
            key={`${store}-${item.msku}-${index}`}
            item={item}
            previous={previous}
            store={store}
          />
        );
      })}
      {!items.length && <p className="muted-line">未记录商品明细。</p>}
    </>
  );
}

/** @param {{item: CategoryAuditItem, previous?: CategoryAuditItem, store?: string}} props */
function CategoryCompletionItem({ item, previous, store }) {
  const rows = previous?.rows;
  const added = Array.isArray(rows) && rows.length === 0;
  const hasDetails = [item.category_a, item.category_b].some(
    (value) => value !== undefined,
  );
  return (
    <details className="audit-unchanged">
      <summary>
        店铺：{store || "未记录"} · MSKU：{item.msku || "未记录"}
        {added ? " · 新增商品" : ""}
      </summary>
      {hasDetails ? (
        <AuditDiff
          before={categoryValues(previous, added ? "新增商品" : "未记录")}
          after={categoryValues(item)}
        />
      ) : (
        <p className="muted-line">未记录品类明细，无法展示前后变化。</p>
      )}
      {rows && rows.length > 1 && (
        <p className="muted-line">
          本次关联 {rows.length} 行，修改前品类取审计记录保存的首行值。
        </p>
      )}
    </details>
  );
}

/** @param {CategoryAuditItem | undefined} item @param {string} [fallback] */
function categoryValues(item, fallback = "未记录") {
  return { 品类A: item?.category_a ?? fallback, 品类B: item?.category_b ?? fallback };
}
