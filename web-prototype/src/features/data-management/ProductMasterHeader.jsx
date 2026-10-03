import { DownloadSimple } from "@phosphor-icons/react";
import { api } from "../../api";
import { formatTime } from "../../lib/presentation";

/** @typedef {import("./productMasterContracts").DatasetRecord} DatasetRecord */

/** @param {{selected: DatasetRecord}} props */
export function ProductMasterHeader({ selected }) {
  return (
    <header className="dataset-header">
      <div className="dataset-heading-copy">
        <small className="asset-name-label">当前版本</small>
        <div className="dataset-title-line">
          <h2>商品信息汇总</h2>
          <span>v{selected.current_version} · 当前生效</span>
        </div>
      </div>
      <div className="dataset-summary">
        <span>
          <small>产品记录</small>
          <strong>{selected.row_count.toLocaleString()} 条</strong>
        </span>
        <span>
          <small>核心字段数</small>
          <strong>{selected.schema?.length ?? selected.column_count} 个字段</strong>
        </span>
        <span>
          <small>必填完整度</small>
          <strong>{selected.quality?.complete_rate ?? 0}%</strong>
        </span>
        <span>
          <small>最近更新</small>
          <strong>{formatTime(selected.updated_at)}</strong>
        </span>
      </div>
      <div className="dataset-actions">
        <div className="dataset-utility-actions">
          <a className="text-button" href={api.datasetDownloadUrl(selected.id)}>
            <DownloadSimple size={16} />
            下载版本
          </a>
        </div>
      </div>
    </header>
  );
}
