import { Database, UploadSimple } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { DatasetUploadDialog } from "../../components/DatasetUploadDialog";
import { EmptyState, PageHeading } from "../../components/SharedUi";
import { ProductLoadFeedback } from "./ProductLoadFeedback";
import { DataAssetTabs } from "./DataAssetTabs";
import { useProductMasterState } from "./useProductMasterState";
import { ProductMasterHeader } from "./ProductMasterHeader";
import { ProductMasterDataView } from "./ProductMasterDataView";
import { ProductTaskRepair } from "./ProductTaskRepair";

/** @typedef {import("./productMasterContracts").ProductMasterProps} ProductMasterProps */

/** @param {ProductMasterProps} props */
export function ProductMasterWorkspace(props) {
  const state = useProductMasterState(props);
  const { selected, dialog, setDialog, onProductChanged, currentVersionId } = state;
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
        title="产品信息管理"
        description="维护跨分析任务复用的产品名称、店铺映射和品类信息；用户反馈在分析任务中导入。"
        action={
          <Button
            type="primary"
            disabled={state.loading || Boolean(state.error)}
            icon={<UploadSimple size={18} />}
            onClick={() =>
              setDialog(
                selected
                  ? { mode: "update", dataset: selected }
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
        <ProductLoadFeedback
          error={state.error}
          loading={state.loading}
          hasData={Boolean(selected)}
          label="正在读取产品信息…"
          onRetry={state.retry}
        />
        {!selected && !state.error && !state.loading && (
          <EmptyState
            icon={Database}
            title="尚未建立产品信息"
            description="导入产品资料后，可维护产品映射、品类和修改记录。"
            action={
              <Button
                type="primary"
                icon={<UploadSimple size={17} />}
                onClick={() => setDialog({ mode: "create", kind: "products" })}
              >
                导入产品信息
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
          onConflict={async (dataset) => {
            await onProductChanged(dataset);
          }}
          onDone={async () => {
            setDialog(null);
            await onProductChanged();
            notify(dialog.mode === "create" ? "产品信息已创建" : "产品信息已更新");
          }}
        />
      )}
    </div>
  );
}
