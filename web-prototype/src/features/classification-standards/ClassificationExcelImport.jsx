import { useRef, useState } from "react";
import { Modal } from "../../components/SharedUi";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import { taxonomyPath } from "../../lib/taxonomyPresentation";

export function ClassificationExcelImport({ prepareDraft, onApply, disabled }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
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
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  const changeSheet = async (sheet) => {
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
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  const preview = async () => {
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
      setError(cause.message);
    } finally {
      setBusy(false);
    }
  };
  const updateColumns = (columns) =>
    setState({ ...state, columns, data: { ...state.data, content: null } });
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
              <label>
                工作表
                <select
                  aria-label="标签框架工作表"
                  value={state.sheet}
                  onChange={(event) => changeSheet(event.target.value)}
                >
                  <option value="">请选择工作表</option>
                  {state.data.sheets.map((sheet) => (
                    <option
                      key={typeof sheet === "string" ? sheet : sheet.name}
                      value={typeof sheet === "string" ? sheet : sheet.name}
                    >
                      {typeof sheet === "string" ? sheet : sheet.name}
                    </option>
                  ))}
                </select>
              </label>
              {state.sheet && (
                <>
                  {state.columns.hierarchy_columns.map((column, index) => (
                    <label key={index}>
                      第 {index + 1} 级
                      <select
                        aria-label={`第 ${index + 1} 级来源列`}
                        value={column}
                        onChange={(event) =>
                          updateColumns({
                            ...state.columns,
                            hierarchy_columns: state.columns.hierarchy_columns.map(
                              (value, position) =>
                                position === index ? event.target.value : value,
                            ),
                          })
                        }
                      >
                        <option value="">请选择列</option>
                        {(state.data.headers ?? []).map((header) => (
                          <option key={header}>{header}</option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className="secondary-button compact-button"
                        onClick={() =>
                          updateColumns({
                            ...state.columns,
                            hierarchy_columns: state.columns.hierarchy_columns.filter(
                              (_value, position) => position !== index,
                            ),
                          })
                        }
                      >
                        移除此级
                      </button>
                    </label>
                  ))}
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() =>
                      updateColumns({
                        ...state.columns,
                        hierarchy_columns: [...state.columns.hierarchy_columns, ""],
                      })
                    }
                  >
                    增加层级列
                  </button>
                  {[
                    ["source_label_column", "原始说法列"],
                    ["sentiment_column", "评价方向列"],
                  ].map(([field, label]) => (
                    <label key={field}>
                      {label}
                      <select
                        aria-label={label}
                        value={state.columns[field]}
                        onChange={(event) =>
                          updateColumns({
                            ...state.columns,
                            [field]: event.target.value,
                          })
                        }
                      >
                        <option value="">不指定</option>
                        {(state.data.headers ?? []).map((header) => (
                          <option key={header}>{header}</option>
                        ))}
                      </select>
                    </label>
                  ))}
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={
                      state.columns.hierarchy_columns.length < 2 ||
                      state.columns.hierarchy_columns.some((value) => !value)
                    }
                    onClick={preview}
                  >
                    生成预览
                  </button>
                </>
              )}
            </fieldset>
            {error && <p role="alert">{error}</p>}
            {content && (
              <>
                <p>
                  {content.categories.length} 个分类节点，{content.labels.length}{" "}
                  个末端标签。
                </p>
                <div className="taxonomy-import-paths">
                  {content.labels.map((label) => (
                    <p key={label.code}>{taxonomyPath(content, label).join(" → ")}</p>
                  ))}
                </div>
                {content.import_sources?.length > 0 && (
                  <details>
                    <summary>
                      核对原始说法与归并结果（{content.import_sources.length} 行）
                    </summary>
                    <div className="taxonomy-import-paths">
                      {content.import_sources.map((source, index) => (
                        <p key={index}>
                          第 {source.row} 行：{source.source_label || "未指定原始说法"}{" "}
                          → {source.path.join(" → ")}；原方向：
                          {source.source_sentiment || "空白"}
                        </p>
                      ))}
                    </div>
                  </details>
                )}
              </>
            )}
            {state.data.issues?.length > 0 && (
              <div className="taxonomy-import-issues" aria-label="导入检查结果">
                {state.data.issues.map((item, index) => (
                  <p key={index}>
                    {item.row ? `第 ${item.row} 行：` : ""}
                    {item.severity === "blocking" ? "需修正：" : "提示："}
                    {item.message}
                  </p>
                ))}
              </div>
            )}
            {state.data.validation?.blocking?.length > 0 && (
              <div className="taxonomy-import-issues">
                <b>采用后仍需完成以下发布检查</b>
                {state.data.validation.blocking.map((message, index) => (
                  <p key={index}>{message}</p>
                ))}
              </div>
            )}
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
