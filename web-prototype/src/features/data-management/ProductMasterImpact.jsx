import { AuditDiff } from "../system-settings/AuditLogDiff";
import { CardHeading } from "../../components/SharedUi";
import { DatasetReferences } from "./DatasetReferences";
import { formatTime } from "../../lib/presentation";
import { HistoryRestoreButton } from "../../components/HistoryRestoreButton";
import { restoreProductChange } from "../../shared/api/historyRestore";
import { navigateHash } from "../../app/hashRouter";
import { useListReturnPosition } from "../../hooks/useListReturnPosition";
import { productAuditQuery } from "./productAuditRoute";

/** @typedef {import("./productMasterContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("./productMasterContracts").ProductMasterProps} ProductMasterProps */
/** @typedef {ReturnType<typeof import("./useProductMasterState").useProductMasterState>} ProductMasterState */

/** @param {Pick<ProductMasterState,"dimensionAudit"|"currentVersionId"|"onProductChanged"> & Pick<ProductMasterProps,"routeReferencePage"|"onReferenceRouteChange"|"onNavigate"|"returnPosition"> & {selected: DatasetRecord, active?: boolean}} props */
export function ProductMasterImpact({
  dimensionAudit,
  currentVersionId,
  routeReferencePage = 1,
  onReferenceRouteChange,
  onNavigate,
  selected,
  onProductChanged,
  returnPosition,
  active = true,
}) {
  const { containerRef, titleRef, remember } = useListReturnPosition({
    identity: selected.id,
    active,
    ready: true,
  });
  return (
    <div className="product-master-impact">
      <section ref={containerRef} className="dataset-view-panel">
        <CardHeading titleRef={titleRef} title="信息修改记录" />
        <div className="data-audit-list">
          {dimensionAudit.map((entry) => (
            <div key={entry.id}>
              <ProductAuditEntry entry={entry} onBeforeOpen={remember} />
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
      {active && (
        <DatasetReferences
          returnPosition={returnPosition}
          currentVersionId={currentVersionId}
          page={Number(routeReferencePage) || 1}
          onRouteChange={onReferenceRouteChange}
          onNavigate={onNavigate}
        />
      )}
    </div>
  );
}

/** @param {{entry: NonNullable<DatasetRecord["audit"]>[number], onBeforeOpen: (id: string) => void}} props */
function ProductAuditEntry({ entry, onBeforeOpen }) {
  const values = { ...entry.before?.values, ...entry.after?.values };
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
        <CategoryCompletionDetails entry={entry} onBeforeOpen={onBeforeOpen} />
      ) : (
        <AuditDiff
          partialAfter={entry.action === "dimension_row_update"}
          before={
            update ? { 产品记录数: entry.before?.row_count } : entry.before?.values
          }
          after={update ? { 产品记录数: entry.after?.row_count } : entry.after?.values}
        />
      )}
      {entry.action === "dimension_row_update" && (
        <ProductAuditLink
          returnId={entry.id}
          onBeforeOpen={onBeforeOpen}
          msku={values.MSKU}
          store={values["店铺/站点"]}
        />
      )}
      {entry.after?.note && (
        <p className="product-audit-reason">修改原因：{entry.after.note}</p>
      )}
    </div>
  );
}

/** @typedef {{store?: string, msku?: string, category_a?: string, category_b?: string, rows?: number[]}} CategoryAuditItem */

/** @param {{entry: NonNullable<DatasetRecord["audit"]>[number], onBeforeOpen: (id: string) => void}} props */
function CategoryCompletionDetails({ entry, onBeforeOpen }) {
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
            returnId={`${entry.id}:${store}:${item.msku}`}
            onBeforeOpen={onBeforeOpen}
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

/** @param {{item: CategoryAuditItem, previous?: CategoryAuditItem, store?: string, returnId: string, onBeforeOpen: (id: string) => void}} props */
function CategoryCompletionItem({ item, previous, store, returnId, onBeforeOpen }) {
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
      <ProductAuditLink
        msku={item.msku}
        store={store}
        returnId={returnId}
        onBeforeOpen={onBeforeOpen}
      />
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

/** @param {{msku: unknown, store: unknown, returnId: string, onBeforeOpen: (id: string) => void}} props */
function ProductAuditLink({ msku, store, returnId, onBeforeOpen }) {
  const query = productAuditQuery(msku, store);
  if (!query) return null;
  return (
    <button
      className="text-button"
      data-list-return-id={returnId}
      onClick={() => {
        onBeforeOpen(returnId);
        navigateHash("data-assets", query);
      }}
    >
      查看当前产品
    </button>
  );
}

/** @param {CategoryAuditItem | undefined} item @param {string} [fallback] */
function categoryValues(item, fallback = "未记录") {
  return { 品类A: item?.category_a ?? fallback, 品类B: item?.category_b ?? fallback };
}
