import { useRef, useState } from "react";
import { Modal } from "../../components/SharedUi";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import { ExcelMappingFields } from "./ExcelMappingFields";
import { ExcelImportPreview } from "./ExcelImportPreview";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraftContent} ClassificationStandardDraftContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardExcelColumns} ClassificationStandardExcelColumns */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardExcelPreview} ClassificationStandardExcelPreview */
/** @typedef {{file: File, draftId: string, data: ClassificationStandardExcelPreview, sheet: string, columns: Required<ClassificationStandardExcelColumns>}} ClassificationExcelImportState */
/** @typedef {{prepareDraft: () => Promise<ClassificationStandardDraft>, onApply: (content: ClassificationStandardDraftContent, filename: string) => void, disabled: boolean}} ClassificationExcelImportProps */

/** @param {unknown} cause */
function errorMessage(cause) {
  return cause instanceof Error ? cause.message : "读取 Excel 失败";
}

/** @param {ClassificationExcelImportProps} props */
export function ClassificationExcelImport({ prepareDraft, onApply, disabled }) {
  const [state, setState] = useState(
    /** @type {ClassificationExcelImportState | null} */ (null),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  /** @param {import("react").ChangeEvent<HTMLInputElement>} event */
  const load = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const requestId = ++generation.current;
    setBusy(true);
    setError("");
    try {
      const draft = await prepareDraft();
      const data = await classificationStandardApi.previewClassificationExcel(
        draft.id,
        file,
      );
      if (requestId === generation.current)
        setState({
          file,
          draftId: draft.id,
          data,
          sheet: "",
          columns: {
            hierarchy_columns: [],
            source_label_column: "",
            sentiment_column: "",
          },
        });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  /** @param {string} sheet */
  const changeSheet = async (sheet) => {
    if (!state) return;
    setBusy(true);
    setError("");
    try {
      const data = await classificationStandardApi.previewClassificationExcel(
        state.draftId,
        state.file,
        sheet,
      );
      const headers = data.headers ?? [];
      const hierarchy = headers.filter((header) =>
        /^(一|二|三|四|五|六|七|八|九|十)级标签$/.test(header),
      );
      if (headers.includes("三级标签-处理")) {
        const index = hierarchy.indexOf("三级标签");
        if (index >= 0) hierarchy.splice(index, 1);
        hierarchy.push("三级标签-处理");
      }
      setState({
        ...state,
        sheet,
        data: { ...data, content: null },
        columns: {
          hierarchy_columns: hierarchy,
          source_label_column: headers.includes("三级标签-AI") ? "三级标签-AI" : "",
          sentiment_column: headers.includes("标签类型") ? "标签类型" : "",
        },
      });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  const preview = async () => {
    if (!state) return;
    setBusy(true);
    setError("");
    try {
      const data = await classificationStandardApi.previewClassificationExcel(
        state.draftId,
        state.file,
        state.sheet,
        state.columns,
      );
      setState({ ...state, data });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };
  /** @param {Required<ClassificationStandardExcelColumns>} columns */
  const updateColumns = (columns) => {
    if (!state) return;
    setState({ ...state, columns, data: { ...state.data, content: null } });
  };
  const content = state?.data.content;
  const blocked = state?.data.issues?.some((item) => item.severity === "blocking");
  return (
    <>
      <label className="secondary-button standard-json-import-button">
        {busy ? "正在读取…" : "导入 Excel 标签框架"}
        <input
          type="file"
          accept=".xlsx"
          aria-label="选择标签框架 Excel"
          disabled={disabled || busy}
          onChange={load}
        />
      </label>
      {error && !state && <p role="alert">{error}</p>}
      {state && (
        <Modal
          eyebrow="标签框架导入"
          title="预览标签框架"
          onClose={() => {
            if (!busy) {
              generation.current += 1;
              setState(null);
              setError("");
            }
          }}
        >
          <div className="taxonomy-import-content">
            <p>
              确认层级列的顺序。导入会替换草稿中的标签框架，请检查层级和评价方向，保存后可运行样本验证。
            </p>
            <fieldset disabled={busy}>
              <ExcelMappingFields
                sheet={state.sheet}
                sheets={state.data.sheets}
                columns={state.columns}
                headers={state.data.headers}
                updateColumns={updateColumns}
                onSheetChange={changeSheet}
                onPreview={preview}
              />
            </fieldset>
            {error && <p role="alert">{error}</p>}
            <ExcelImportPreview data={state.data} />
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                disabled={busy}
                onClick={() => setState(null)}
              >
                取消
              </button>
              <button
                type="button"
                className="primary-button"
                disabled={busy || !content || blocked}
                onClick={() => {
                  if (!content) return;
                  onApply(content, state.file.name);
                  setState(null);
                }}
              >
                采用预览并继续编辑
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
