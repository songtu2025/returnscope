import { ClockCounterClockwise, WarningCircle } from "@phosphor-icons/react";
import { CardHeading, EmptyState, InlineLoading } from "../../components/SharedUi";
import Button from "antd/es/button";
import { formatTime } from "../../lib/presentation";
import { SemanticResultPanel } from "../classification-results/SemanticResultPanel";
/** @typedef {import("../../shared/api/reviewBatchContracts").ResultVersion} ResultVersion */
/**
 * @param {{version: ResultVersion, parentVersionNo?: number | null, hasChangeSummary: boolean}} props
 */
function ResultVersionPublication({ version, parentVersionNo, hasChangeSummary }) {
  return (
    <>
      <p>
        {parentVersionNo ? `来源 v${parentVersionNo}` : "首次发布"} ·{" "}
        {version.created_by_name || "操作者信息未提供"} ·{" "}
        {formatTime(version.published_at || version.created_at)}
      </p>
      {version.version_reason && <p>{version.version_reason}</p>}
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
      {version.manual_change && (
        <details className="result-manual-change">
          <summary>查看人工修正前后</summary>
          <p>修改原因：{version.manual_change.reason}</p>
          <section aria-label="修正前语义">
            <b>修正前</b>
            <SemanticResultPanel record={version.manual_change.before} />
          </section>
          <section aria-label="修正后语义">
            <b>修正后</b>
            <SemanticResultPanel record={version.manual_change.after} />
          </section>
        </details>
      )}
      <details>
        <summary>查看技术信息</summary>
        <code>{version.version_id}</code>
        {version.created_by && <code>操作账号：{version.created_by}</code>}
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
            v{version.version} ·{" "}
            {version.version === 1
              ? "原始分类"
              : version.version_reason === "反馈组人工修正"
                ? "人工修正"
                : version.source_review_batch_id
                  ? "历史批次复核"
                  : "分析结果更新"}
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
          查看修改记录
        </Button>
      )}
    </li>
  );
}
/**
 * @param {{history: ResultVersion[], resultVersionId: string,
 *   onSelectVersion: (versionId: string) => void}} props
 */
function ResultVersionChain({ history, resultVersionId, onSelectVersion }) {
  return (
    <ol className="result-version-chain">
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
    <div className="result-version-panel-body" aria-busy={loading}>
      <CardHeading
        title="修改历史"
        note="此处查看历史修改记录；分类数据始终显示最新结果。"
        action={
          <InlineLoading
            label="更新中…"
            compact
            active={loading && history.length > 0}
          />
        }
      />
      {loading && !history.length && (
        <InlineLoading scope="page" label="正在读取修改历史…" />
      )}
      {error && (
        <div className="review-batch-error" role="alert">
          <WarningCircle size={22} />
          <div>
            <b>
              {history.length
                ? "修改历史更新失败，当前显示上一次数据"
                : "修改历史读取失败"}
            </b>
            <p>{error}</p>
          </div>
          <Button onClick={onReload}>重新加载</Button>
        </div>
      )}
      {ready && history.length === 0 && (
        <EmptyState
          icon={ClockCounterClockwise}
          title="暂无修改历史"
          description="当前没有可展示的修改记录。"
        />
      )}
      {history.length > 0 && (
        <ResultVersionChain
          history={history}
          resultVersionId={resultVersionId}
          onSelectVersion={onSelectVersion}
        />
      )}
    </div>
  );
}
