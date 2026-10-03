import { DownloadSimple } from "@phosphor-icons/react";
import { api } from "../../api";
import { CardHeading } from "../../components/SharedUi";
import { ProductDimensionRows } from "./ProductDimensionRows";
import { formatTime } from "../../lib/presentation";
import { ProductMasterImpact } from "./ProductMasterImpact";

/** @typedef {import("./productMasterContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("./productMasterContracts").ProductMasterProps} ProductMasterProps */
/** @typedef {ReturnType<typeof import("./useProductMasterState").useProductMasterState>} ProductMasterState */

/** @param {{state: ProductMasterState,selected: DatasetRecord,props: ProductMasterProps}} input */
export function ProductMasterDataView({ state, selected, props }) {
  const { detailTab, setDetailTab, currentVersionId, mutateSelected, mutateDatasets } =
    state;
  const {
    onDetailTabChange,
    onReferenceRouteChange,
    routeReferenceVersion = "",
    notify,
  } = props;
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
          className={detailTab === "versions" ? "active" : ""}
          onClick={() => {
            setDetailTab("versions");
            onDetailTabChange?.("versions");
          }}
        >
          版本历史
        </button>
        <button
          className={detailTab === "impact" ? "active" : ""}
          onClick={() => {
            setDetailTab("impact");
            onDetailTabChange?.("impact");
            onReferenceRouteChange?.({
              tab: "impact",
              reference_version: routeReferenceVersion || currentVersionId || "",
              reference_page: 1,
            });
          }}
        >
          变更追踪与影响
        </button>
      </nav>
      <div className="dataset-view">
        {detailTab === "rows" && (
          <ProductDimensionRows
            dataset={selected}
            notify={notify}
            onChanged={(dataset) => {
              void mutateSelected(dataset, false);
              void mutateDatasets();
            }}
          />
        )}
        {detailTab === "versions" && (
          <section className="dataset-view-panel">
            <CardHeading title="版本记录" note="每次更新都会保留不可变快照" />
            <div className="version-list">
              {(selected.versions ?? []).map((version) => (
                <div key={version.id}>
                  <span>v{version.version}</span>
                  <div>
                    <b>{version.original_name}</b>
                    <p>{version.change_note || "未填写变更说明"}</p>
                    <small>
                      {version.creator_name} · {formatTime(version.created_at)} ·{" "}
                      {Number(version.row_count ?? 0).toLocaleString()} 行
                    </small>
                  </div>
                  <div className="version-actions">
                    {version.version === selected.current_version && <em>当前</em>}
                    <a
                      href={api.datasetDownloadUrl(selected.id, version.version)}
                      title={`下载 v${version.version}`}
                    >
                      <DownloadSimple size={15} />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
        {detailTab === "impact" && (
          <ProductMasterImpact
            dimensionAudit={state.dimensionAudit}
            currentVersionId={currentVersionId}
            selected={selected}
            routeReferenceVersion={props.routeReferenceVersion}
            routeReferencePage={props.routeReferencePage}
            onReferenceRouteChange={onReferenceRouteChange}
            onNavigate={props.onNavigate}
          />
        )}
      </div>{" "}
    </>
  );
}
