import { ClockCounterClockwise, WarningCircle } from "@phosphor-icons/react";
import { EmptyState, InlineLoading } from "../../components/SharedUi";
import Button from "antd/es/button";
import { formatTime } from "../../lib/presentation";
/** @typedef {import("../../shared/api/reviewBatchContracts").ResultVersion} ResultVersion */
/**
 * @param {{version: ResultVersion, parentVersionNo?: number | null, hasChangeSummary: boolean}} props
 */
function ResultVersionPublication({ version, parentVersionNo, hasChangeSummary }) {
  return (
    <>
      <p>
        {parentVersionNo ? `来源 v${parentVersionNo}` : "首次发布"} ·{" "}
        {version.created_by_name || "发布人信息未提供"}·{" "}
        {formatTime(version.published_at || version.created_at)}
      </p>
      <p>{version.version_reason || "未提供发布原因"}</p>
      {hasChangeSummary && (
        <p>
          基于 v{version.parent_version_no} 修改{" "}
          {Number(version.changed_unit_count).toLocaleString()}
          {" 个分类单元，其余 "}
          {Number(version.inherited_unit_count).toLocaleString()}
          {" 个沿用来源版本"}
        </p>
      )}
      <small>
        {Number(version.record_count || 0).toLocaleString()} 条记录 ·{" "}
        {Number(version.unit_count || 0).toLocaleString()} 个分类单元
      </small>
      <details>
        <summary>查看技术信息</summary>
        <code>{version.version_id}</code>
        {version.created_by && <code>发布账号：{version.created_by}</code>}
        {version.source_review_batch_id && (
          <code>复核批次：{version.source_review_batch_id}</code>
        )}
      </details>
    </>
  );
}
/**
 * @param {{version: ResultVersion, index: number, current: boolean, parentVersionNo?: number | null,
 *   hasChangeSummary: boolean, onSelectVersion: (versionId: string) => void}} props
 */
function ResultVersionHistoryItem({
  version,
  index,
  current,
  parentVersionNo,
  hasChangeSummary,
  onSelectVersion,
}) {
  return (
    <li key={version.version_id} className={current ? "active" : ""}>
      <span>{index + 1}</span>
      <div>
        <header>
          <b>
            v{version.version} · {version.version === 1 ? "原始分类" : "结果更新"}
          </b>
          {current && <em>当前查看</em>}
        </header>
        <ResultVersionPublication
          version={version}
          parentVersionNo={parentVersionNo}
          hasChangeSummary={hasChangeSummary}
        />
      </div>
      {!current && (
        <Button size="small" onClick={() => onSelectVersion(version.version_id)}>
          查看版本
        </Button>
      )}
    </li>
  );
}
/**
 * @param {{history: ResultVersion[], resultVersionId: string, loading: boolean,
 *   onSelectVersion: (versionId: string) => void}} props
 */
function ResultVersionChain({ history, resultVersionId, loading, onSelectVersion }) {
  return (
    <ol className={`result-version-chain ${loading ? "is-loading" : ""}`}>
      {history.map((version, index) => {
        const current = version.version_id === resultVersionId;
        const parent = history.find(
          (item) => item.version_id === version.parent_version_id,
        );
        const parentVersionNo = version.parent_version_no ?? parent?.version;
        const hasChangeSummary =
          version.parent_version_no != null &&
          version.changed_unit_count != null &&
          version.inherited_unit_count != null;

        return (
          <ResultVersionHistoryItem
            key={version.version_id}
            version={version}
            index={index}
            current={current}
            parentVersionNo={parentVersionNo}
            hasChangeSummary={hasChangeSummary}
            onSelectVersion={onSelectVersion}
          />
        );
      })}
    </ol>
  );
}

/**
 * @param {{history: ResultVersion[], resultVersionId: string, loading: boolean,
 *   error: string, onReload: () => void, onSelectVersion: (versionId: string) => void}} props
 */
export function ResultVersionHistory({
  history,
  resultVersionId,
  loading,
  error,
  onReload,
  onSelectVersion,
}) {
  const ready = !loading && !error;
  return (
    <div className="result-version-panel-body">
      {loading && <InlineLoading label="正在读取版本历史…" />}
      {error && (
        <div className="review-batch-error" role="alert">
          <WarningCircle size={22} />
          <div>
            <b>版本历史读取失败</b>
            <p>{error}</p>
          </div>
          <Button onClick={onReload}>重新加载</Button>
        </div>
      )}
      {ready && history.length === 0 && (
        <EmptyState
          icon={ClockCounterClockwise}
          title="暂无版本历史"
          description="当前接口没有返回可展示的版本记录。"
        />
      )}
      {!error && history.length > 0 && (
        <ResultVersionChain
          history={history}
          resultVersionId={resultVersionId}
          loading={loading}
          onSelectVersion={onSelectVersion}
        />
      )}
    </div>
  );
}
