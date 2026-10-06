/** @param {{reviewFile: File | null, setReviewFile: (file: File | null) => void}} props */
export function ValidationReviewUpload({ reviewFile, setReviewFile }) {
  return (
    <div className="standard-review-upload">
      <div>
        <label className="secondary-button standard-json-import-button">
          选择 Review Excel
          <input
            id="standard-validation-review-file"
            type="file"
            accept=".xlsx"
            aria-label="Review 表格"
            aria-describedby="standard-validation-review-file-help"
            onChange={(event) => setReviewFile(event.target.files?.[0] ?? null)}
          />
        </label>
        {reviewFile && <span role="status">已选择：{reviewFile.name}</span>}
        <small id="standard-validation-review-file-help">
          需包含评论内容列，可含评论标题、评论编号、一级品类、ASIN；无品类列时按当前标准验证。
        </small>
      </div>
      <details className="standard-review-reference-help">
        <summary>导入人工参考答案（可选）</summary>
        <p>
          同一文件可增加“人工参考答案”工作表，列为评论编号、标签编码、评价方向、部位、证据；多标签逐行填写，无标签填写“无标签”。可用“存在歧义”列标记“是”，排除不确定答案。事实策略还需填写“事实状态”（EXPERIENCE、EVALUATION、RECOMMENDATION、INTENT、PREDICTION、HYPOTHESIS、REPORTED、NEGATED、NOT_TESTED、ADVICE）；无标签行也需事实状态和证据。“使用者”“商品对象”可选，仅明确填写时比较。参考答案只用于评分，不发送给模型。
        </p>
      </details>
    </div>
  );
}
