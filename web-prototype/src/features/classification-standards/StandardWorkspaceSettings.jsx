import { UploadSimple } from "@phosphor-icons/react";
import { ClassificationRuleIssues } from "./ClassificationRuleIssues";
import { ClassificationStandardVersionHistory } from "./ClassificationStandardVersionHistory";

/** @typedef {import("./classificationStandardWorkspaceContracts").ClassificationStandardReviewRole} ClassificationStandardReviewRole */
/** @typedef {import("./classificationStandardWorkspaceContracts").ReadableRecognitionProfile} ReadableRecognitionProfile */
/** @typedef {import("./classificationStandardWorkspaceContracts").StandardWorkspaceContext} StandardWorkspaceContext */

/** @param {StandardWorkspaceContext} context */
export function StandardWorkspaceSettings(context) {
  const {
    versions,
    onRestore,
    isNew,
    detail,
    draft,
    content,
    busy,
    onContentChange,
    onImport,
    section,
    fixRequest,
    editable,
  } = context;
  return (
    <div className="standard-settings-extra" hidden={section !== "settings"}>
      <ClassificationRuleIssues
        content={content}
        onChange={onContentChange}
        focusRequest={fixRequest}
        disabled={!editable || Boolean(busy)}
      />
      <section className="standard-detail-section">
        <h2>识别策略</h2>
        <label>
          当前草稿使用
          <select
            aria-label="识别策略"
            disabled={!editable}
            value={content.recognition_profile ?? "legacy_v3"}
            onChange={(event) =>
              onContentChange({
                ...content,
                recognition_profile: /** @type {ReadableRecognitionProfile} */ (
                  event.target.value
                ),
              })
            }
          >
            <option value="legacy_v3">现有策略 · 定义与关键词</option>
            <option value="semantic_v1">语义策略 · 定义、边界与证据</option>
            <option value="fact_v2">事实策略 · 对象、条件与证据对齐</option>
          </select>
        </label>
        <label>
          复核模型
          <select
            aria-label="复核模型"
            disabled={!editable}
            value={content.review_role ?? "primary"}
            onChange={(event) =>
              onContentChange({
                ...content,
                review_role: /** @type {ClassificationStandardReviewRole} */ (
                  event.target.value
                ),
              })
            }
          >
            <option value="primary">主模型复核</option>
            <option value="secondary">独立模型复核</option>
          </select>
        </label>
        <p>保存只修改草稿；通过发布验证并启用后，新任务才使用该策略。</p>
      </section>
      {!isNew && editable && (
        <section className="standard-json-transfer">
          <div>
            <b>JSON 数据交换</b>
            <span>导入只替换当前草稿的业务内容，不会直接发布。</span>
          </div>
          <label
            className={`secondary-button standard-json-import-button ${
              busy ? "disabled" : ""
            }`}
          >
            <UploadSimple size={15} />
            {busy === "import" ? "导入中" : "导入JSON"}
            <input
              type="file"
              accept="application/json,.json"
              aria-label="选择分类标准 JSON 文件"
              disabled={Boolean(busy)}
              onChange={onImport}
            />
          </label>
        </section>
      )}

      {detail && (
        <ClassificationStandardVersionHistory
          standard={{ ...detail, draft_id: draft?.id }}
          versions={versions}
          onRestore={onRestore}
        />
      )}
    </div>
  );
}
