import { ArrowLeft, WarningCircle } from "@phosphor-icons/react";
import { navigateHash } from "../../app/hashRouter";
import { EmptyState, PageLoadingState } from "../../components/SharedUi";
function ClassificationStandardBackButton() {
  return (
    <button
      type="button"
      className="icon-button"
      aria-label="返回"
      onClick={() => navigateHash("classification-standards")}
    >
      <ArrowLeft size={18} />
    </button>
  );
}
/** @param {{mode: string}} props */
export function ClassificationStandardPageLoading({ mode }) {
  return (
    <div className="standard-page classification-standard-page">
      {mode === "edit" && <ClassificationStandardBackButton />}
      <PageLoadingState label="正在读取分类标准…" />
    </div>
  );
}
/** @param {{pending: boolean, error: string, onRetry: () => void}} props */
export function ClassificationStandardDetailState({ pending, error, onRetry }) {
  return (
    <>
      <ClassificationStandardBackButton />
      {pending ? (
        <PageLoadingState label="正在读取分类标准…" />
      ) : (
        <EmptyState
          icon={WarningCircle}
          title="分类标准读取失败"
          description={error}
          action={
            <button className="secondary-button" onClick={onRetry}>
              重新加载
            </button>
          }
        />
      )}
    </>
  );
}
