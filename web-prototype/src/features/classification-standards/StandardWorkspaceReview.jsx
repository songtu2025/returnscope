import { StandardStrategyChanges } from "./StandardStrategyChanges";
import { StandardLabelChange } from "./StandardLabelChange";
import Input from "antd/es/input";
import { ClassificationHierarchyChanges } from "./ClassificationHierarchyEditor";
import { ClassificationStandardValidation } from "./ClassificationStandardValidation";
import { ClassificationStructureIssues } from "./ClassificationStructureIssues";

/** @typedef {import("./classificationStandardWorkspaceContracts").StandardWorkspaceContext} StandardWorkspaceContext */

/** @param {StandardWorkspaceContext} context */
export function StandardWorkspaceReview(context) {
  const {
    draft,
    content,
    changeReason,
    busy,
    dirty,
    validationSources,
    validationRuns,
    selectedValidation,
    validationSourceId,
    validationSampleSize,
    onReasonChange,
    onValidationSourceChange,
    onValidationSampleSizeChange,
    onValidationRun,
    onValidationSelect,
    section,
    fixIssue,
    baseContent,
    changes,
  } = context;
  return (
    <div className="standard-review-panel" hidden={section !== "review"}>
      <section className="standard-editor-section standard-change-preview">
        <header>
          <h2>发布前检查</h2>
          <span>对比当前启用版本</span>
        </header>
        <p>保存草稿不会影响运行中的标准。可以直接发布，也可以先测试验收。</p>
        <ClassificationHierarchyChanges content={content} baseContent={baseContent} />
        <StandardStrategyChanges content={content} baseContent={baseContent} />
        {changes.length ? (
          changes.map(({ label, before, status }) => (
            <StandardLabelChange
              label={label}
              before={before}
              status={status}
              key={label.code}
            />
          ))
        ) : (
          <p>标签没有变化。基本信息与分类设置的修改会随草稿一起保存。</p>
        )}
        {JSON.stringify(content.validation_rules) !==
          JSON.stringify(baseContent?.validation_rules ?? {}) && (
          <p className="label-unsaved-hint">
            标签校验规则有变化，请检查相关语义边界、分类指令与 Listing 承诺配置。
          </p>
        )}
        {!dirty && draft && draft.validation.blocking.length > 0 && (
          <ClassificationStructureIssues
            validation={draft.validation}
            content={content}
            onFix={fixIssue}
            busy={Boolean(busy)}
          />
        )}
      </section>
      <section className="standard-change-reason">
        <label>
          变更说明
          <Input
            value={changeReason}
            onChange={(event) => onReasonChange(event.target.value)}
          />
        </label>
        <span>用于版本记录，不影响智能体判断。</span>
      </section>

      <section
        className="standard-required-validation"
        aria-labelledby="standard-required-validation-title"
      >
        <header className="standard-required-validation-heading">
          <div>
            <h2 id="standard-required-validation-title">可选测试验收</h2>
            <p>运行测试可辅助判断分类效果，但不会代替你的发布决定。</p>
          </div>
          <span>可选</span>
        </header>
        {draft ? (
          <ClassificationStandardValidation
            draft={draft}
            sources={validationSources}
            runs={validationRuns}
            selectedRun={selectedValidation}
            sourceId={validationSourceId}
            sampleSize={validationSampleSize}
            busy={busy === "validation"}
            dirty={dirty}
            onSourceChange={onValidationSourceChange}
            onSampleSizeChange={onValidationSampleSizeChange}
            onRun={onValidationRun}
            onSelectRun={onValidationSelect}
          />
        ) : (
          <p>请先保存草稿，再按需运行测试验收。</p>
        )}
      </section>
    </div>
  );
}
