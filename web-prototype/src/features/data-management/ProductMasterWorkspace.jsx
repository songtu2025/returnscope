import { Database, UploadSimple } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { DatasetUploadDialog } from "../../components/DatasetUploadDialog";
import { EmptyState, PageHeading } from "../../components/SharedUi";
import { DataAssetTabs } from "./DataAssetTabs";
import { useProductMasterState } from "./useProductMasterState";
import { ProductMasterHeader } from "./ProductMasterHeader";
import { ProductMasterDataView } from "./ProductMasterDataView";
import { ProductTaskRepair } from "./ProductTaskRepair";

/** @typedef {import("./productMasterContracts").ProductMasterProps} ProductMasterProps */

/** @param {ProductMasterProps} props */
export function ProductMasterWorkspace(props) {
  const state = useProductMasterState(props);
  const {
    selected,
    dialog,
    setDialog,
    mutateDatasets,
    mutateSelected,
    currentVersionId,
  } = state;
  const {
    notify,
    focus,
    taskDraft,
    onReturnToTask,
    onAssetViewChange = () => {},
  } = props;
  return (
    <div className="standard-page data-page product-master-page">
      <PageHeading
        title="商品信息汇总"
        description="维护跨分析任务复用的产品名称、店铺映射和品类信息；退货明细在分析任务中导入。"
        action={
          <Button
            type="primary"
            icon={<UploadSimple size={18} />}
            onClick={() =>
              setDialog(
                selected
                  ? { mode: "version", dataset: selected }
                  : { mode: "create", kind: "products" },
              )
            }
          >
            {selected ? "更新产品信息" : "导入产品信息"}
          </Button>
        }
      />
      <DataAssetTabs current="products" onChange={onAssetViewChange} />
      <ProductTaskRepair
        focus={focus}
        taskDraft={taskDraft}
        onReturnToTask={onReturnToTask}
        notify={notify}
        selected={selected}
        currentVersionId={currentVersionId}
      />{" "}
      <section className="dataset-detail">
        {!selected && (
          <EmptyState
            icon={Database}
            title="尚未建立产品信息"
            description="导入首个产品信息版本后，可维护商品映射、版本和修改留痕。"
            action={
              <Button
                type="primary"
                icon={<UploadSimple size={17} />}
                onClick={() => setDialog({ mode: "create", kind: "products" })}
              >
                导入首个产品信息版本
              </Button>
            }
          />
        )}
        {selected && (
          <>
            <ProductMasterHeader selected={selected} />

            <ProductMasterDataView state={state} selected={selected} props={props} />
          </>
        )}
      </section>
      {dialog && (
        <DatasetUploadDialog
          dialog={dialog}
          onClose={() => setDialog(null)}
          onDone={async () => {
            setDialog(null);
            await Promise.all([mutateDatasets(), mutateSelected()]);
            notify(dialog.mode === "create" ? "产品信息已创建" : "新版本已创建");
          }}
        />
      )}
    </div>
  );
}
