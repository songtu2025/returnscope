import { taxonomyPath } from "../../lib/taxonomyPresentation";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraftContent} ClassificationStandardDraftContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardExcelPreview} ClassificationStandardExcelPreview */
/** @param {{content: ClassificationStandardDraftContent}} props */
function ImportSources({ content }) {
  return (
    <>
      {content.import_sources?.length > 0 && (
        <details>
          <summary>
            核对原始说法与归并结果（{content.import_sources.length} 行）
          </summary>
          <div className="taxonomy-import-paths">
            {content.import_sources.map((source, index) => (
              <p key={index}>
                第 {source.row} 行：{source.source_label || "未指定原始说法"} →{" "}
                {source.path?.join(" → ") || "未识别路径"}；原方向：
                {source.source_sentiment || "空白"}
              </p>
            ))}
          </div>
        </details>
      )}
    </>
  );
}
/** @param {{data: ClassificationStandardExcelPreview}} props */
function ImportIssues({ data }) {
  return (
    <>
      {data.issues?.length > 0 && (
        <div className="taxonomy-import-issues" aria-label="导入检查结果">
          {data.issues.map((item, index) => (
            <p key={index}>
              {item.row ? `第 ${item.row} 行：` : ""}
              {item.severity === "blocking" ? "需修正：" : "提示："}
              {item.message}
            </p>
          ))}
        </div>
      )}
      {Boolean(data.validation?.blocking?.length) && (
        <div className="taxonomy-import-issues">
          <b>采用后仍需完成以下发布检查</b>
          {data.validation?.blocking?.map((message, index) => (
            <p key={index}>{message}</p>
          ))}
        </div>
      )}
    </>
  );
}
/** @param {{data: ClassificationStandardExcelPreview}} props */
export function ExcelImportPreview({ data }) {
  const content = data.content;
  return (
    <>
      {content && (
        <>
          <p>
            {content.categories.length} 个分类节点，{content.labels.length} 个末端标签。
          </p>
          <div className="taxonomy-import-paths">
            {content.labels.map((label) => (
              <p key={label.code}>{taxonomyPath(content, label).join(" → ")}</p>
            ))}
          </div>
          <ImportSources content={content} />
        </>
      )}
      <ImportIssues data={data} />
    </>
  );
}
