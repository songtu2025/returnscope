import { ProductDimensionRows } from "./ProductDimensionRows";
import { ProductMasterImpact } from "./ProductMasterImpact";

/** @typedef {import("./productMasterContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("./productMasterContracts").ProductMasterProps} ProductMasterProps */
/** @typedef {ReturnType<typeof import("./useProductMasterState").useProductMasterState>} ProductMasterState */

/** @param {{state: ProductMasterState,selected: DatasetRecord,props: ProductMasterProps}} input */
export function ProductMasterDataView({ state, selected, props }) {
  const { detailTab, setDetailTab, currentVersionId, onProductChanged } = state;
  const { onDetailTabChange, onReferenceRouteChange, notify } = props;
  return (
    <>
      {" "}
      <nav className="dataset-view-tabs" aria-label="产品信息详情">
        <button
          className={detailTab === "rows" ? "active" : ""}
          onClick={() => {
            setDetailTab("rows");
            onDetailTabChange?.("rows");
          }}
        >
          产品列表
        </button>
        <button
          className={detailTab === "impact" ? "active" : ""}
          onClick={() => {
            setDetailTab("impact");
            onDetailTabChange?.("impact");
            onReferenceRouteChange?.({
              tab: "impact",
              reference_version: "",
              reference_page: 1,
            });
          }}
        >
          修改记录与任务引用
        </button>
      </nav>
      <div className="dataset-view">
        {detailTab === "rows" && (
          <ProductDimensionRows
            dataset={selected}
            notify={notify}
            onChanged={onProductChanged}
            onEditingChange={state.setProtectedOperation}
            onRefresh={state.retry}
            parentError={Boolean(state.error)}
          />
        )}
        {(detailTab === "impact" || props.onReturnAudit) && (
          <div hidden={detailTab !== "impact"}>
            <ProductMasterImpact
              active={detailTab === "impact"}
              returnPosition={props.returnPosition}
              selected={selected}
              onProductChanged={onProductChanged}
              dimensionAudit={state.dimensionAudit}
              currentVersionId={currentVersionId}
              routeReferencePage={props.routeReferencePage}
              onReferenceRouteChange={onReferenceRouteChange}
              onNavigate={props.onNavigate}
            />
          </div>
        )}
      </div>{" "}
    </>
  );
}
