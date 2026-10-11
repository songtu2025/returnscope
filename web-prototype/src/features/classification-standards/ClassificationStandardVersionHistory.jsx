import { ClockCounterClockwise, DownloadSimple } from "@phosphor-icons/react";
import { formatDate } from "../../lib/presentation";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDetail} ClassificationStandardDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVersion} ClassificationStandardVersion */

/**
 * @param {{
 *   standard: Pick<ClassificationStandardDetail, "standard_version_id"> & {draft_id?: string | null},
 *   versions: ClassificationStandardVersion[],
 *   onRestore: (version: ClassificationStandardVersion) => void,
 * }} props
 */
export function ClassificationStandardVersionHistory({
  standard,
  versions,
  onRestore,
}) {
  return (
    <details className="standard-version-history">
      <summary>
        <ClockCounterClockwise size={17} /> 修改记录（{versions.length}）
      </summary>
      <div>
        {versions.map((version) => (
          <div key={version.id}>
            <b>第 {version.version_no} 次更新</b>
            <span>{version.version_reason}</span>
            <small>{formatDate(version.published_at)}</small>
            <a
              href={classificationStandardApi.classificationStandardVersionExportUrl(
                version.id,
              )}
              aria-label={`导出第 ${version.version_no} 次更新 JSON`}
            >
              <DownloadSimple size={14} /> 导出JSON
            </a>
            {version.id === standard.standard_version_id ? (
              <span className="standard-version-current">当前生效</span>
            ) : (
              <button
                type="button"
                className="standard-version-restore"
                disabled={Boolean(standard.draft_id)}
                title={standard.draft_id ? "请先处理暂存修改" : undefined}
                aria-label={`采用第 ${version.version_no} 次更新内容`}
                onClick={() => onRestore(version)}
              >
                <ClockCounterClockwise size={14} /> 采用此记录
              </button>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}
