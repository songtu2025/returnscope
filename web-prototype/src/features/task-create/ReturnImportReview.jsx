import { CheckCircle, Info, UploadSimple, WarningCircle } from "@phosphor-icons/react";
/** @typedef {import("./taskCreateContracts").ReturnImportInspection} ReturnImportInspection */
/** @typedef {{duplicate?: ReturnImportInspection["duplicate"], missingStoreRows: number, submitting: boolean, submitLabel: string, error: string}} ImportSelection */
/** @typedef {{onClose: () => void, onSubmit: () => void | Promise<void>, onChangeFile: () => void}} ImportActions */

/** @param {{inspection: ReturnImportInspection, selection: ImportSelection, actions: ImportActions}} props */
export function ReturnImportReview({ inspection, selection, actions }) {
  const { duplicate, missingStoreRows, submitting, submitLabel, error } = selection;
  return (
    <div className="return-import-review">
      <ImportDetection inspection={inspection} onChangeFile={actions.onChangeFile} />

      <ImportNotices duplicate={duplicate} missingStoreRows={missingStoreRows} />
      {error && <ImportError message={error} />}
      <div className="modal-actions">
        <button type="button" className="secondary-button" onClick={actions.onClose}>
          取消
        </button>
        <button
          type="button"
          className="primary-button"
          onClick={actions.onSubmit}
          disabled={submitting || missingStoreRows > 0}
        >
          {submitting
            ? "正在处理…"
            : missingStoreRows > 0
              ? "请先修正文件"
              : submitLabel}
          {!submitting && <UploadSimple size={17} />}
        </button>
      </div>
    </div>
  );
}

/** @param {{message: string}} props */
export function ImportError({ message }) {
  return (
    <div className="form-error">
      <WarningCircle size={17} />
      {message}
    </div>
  );
}

/** @param {{inspection: ReturnImportInspection, onChangeFile: ImportActions["onChangeFile"]}} props */
function ImportDetection({ inspection, onChangeFile }) {
  return (
    <section className="return-import-detection" aria-label="文件识别结果">
      <header>
        <CheckCircle size={21} weight="fill" />
        <div>
          <b>文件检查完成</b>
          <span>{inspection.original_name}</span>
        </div>
        <button type="button" className="link-button" onClick={onChangeFile}>
          更换文件
        </button>
      </header>
      <dl>
        <div>
          <dt>识别的分析数据</dt>
          <dd>{inspection.suggested_name}</dd>
        </div>
        <div>
          <dt>店铺/站点</dt>
          <dd>{inspection.stores?.join("、") || "未识别"}</dd>
        </div>
        <div>
          <dt>数据行数</dt>
          <dd>{Number(inspection.row_count).toLocaleString()} 行</dd>
        </div>
        <div>
          <dt>有效评论</dt>
          <dd>
            {Number(inspection.quality?.valid_comment_rows ?? 0).toLocaleString()} 行
          </dd>
        </div>
      </dl>
    </section>
  );
}

/** @param {{duplicate: ImportSelection["duplicate"], missingStoreRows: number}} props */
function ImportNotices({ duplicate, missingStoreRows }) {
  return (
    <>
      {duplicate && (
        <div className="return-import-notice duplicate" role="status">
          <Info size={18} weight="fill" />
          <span>
            这份文件已经导入到“{duplicate.dataset_name}
            ”。本次任务会直接复用这份输入快照。
          </span>
        </div>
      )}

      {missingStoreRows > 0 && (
        <div className="return-import-notice warning" role="alert">
          <WarningCircle size={18} weight="fill" />
          <span>
            有 {missingStoreRows.toLocaleString()}{" "}
            行缺少店铺/站点。请修正文件后重新检查。
          </span>
        </div>
      )}
    </>
  );
}
