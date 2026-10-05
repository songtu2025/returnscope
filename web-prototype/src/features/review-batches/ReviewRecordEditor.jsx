import { useMemo } from "react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import Select from "antd/es/select";
import {
  CheckCircle,
  EyeSlash,
  PencilSimple,
  WarningCircle,
} from "@phosphor-icons/react";
import { labelText } from "../../lib/taxonomyPresentation";
import { REVIEW_ASSESSMENT_FIELDS } from "./reviewAssessment";

/** @typedef {import("../../shared/api/reviewBatchContracts").ReviewLabel} ReviewLabel */

/** @param {ReviewLabel[]} labels @param {string} [query] */
function groupedLabels(labels, query = "") {
  const keyword = query.trim().toLowerCase();
  return labels
    .filter((label) =>
      !keyword
        ? true
        : `${labelText(label)} ${label.code || ""}`.toLowerCase().includes(keyword),
    )
    .reduce((groups, label) => {
      const group = label.group || "其他";
      groups[group] = [...(groups[group] ?? []), label];
      return groups;
    }, /** @type {Record<string, ReviewLabel[]>} */ ({}));
}

/** @param {Pick<import("./reviewRecordPresentation").ReviewRecordDrawerProps, "mode" | "labelCode" | "reason" | "onUseServer" | "onContinueWithServer"> & {conflict: import("../../shared/api/reviewBatchContracts").ReviewConflict}} props */
function ReviewRecordConflict({
  conflict,
  mode,
  labelCode,
  reason,
  onUseServer,
  onContinueWithServer,
}) {
  return (
    <section className="review-conflict-panel" role="alert">
      <header>
        <WarningCircle size={18} />
        <b>记录已被其他用户修改</b>
      </header>
      <p>{conflict.message}</p>
      <div className="review-conflict-compare">
        <div>
          <span>服务器最新</span>
          <b>修订 #{conflict.serverRecord?.revision ?? "读取失败"}</b>
        </div>
        <div>
          <span>我的未保存</span>
          <b>
            {mode === "confirm"
              ? "确认原结果"
              : mode === "exclude"
                ? "排除本条"
                : labelCode || "未选择标签"}
          </b>
          <small>{reason}</small>
        </div>
      </div>
      <div>
        <Button disabled={!conflict.serverRecord} onClick={onUseServer}>
          采用服务器最新
        </Button>
        <Button
          type="primary"
          disabled={!conflict.serverRecord}
          onClick={onContinueWithServer}
        >
          基于新修订继续编辑
        </Button>
      </div>
    </section>
  );
}

/** @param {Pick<import("./reviewRecordPresentation").ReviewRecordDrawerProps, "mode" | "onMode">} props */
function ReviewResolutionOptions({ mode, onMode }) {
  return (
    <div className="review-resolution-options">
      <Button
        className={mode === "confirm" ? "active" : ""}
        icon={<CheckCircle size={17} />}
        onClick={() => onMode("confirm")}
      >
        确认原结果
      </Button>
      <Button
        className={mode === "modify" ? "active" : ""}
        icon={<PencilSimple size={17} />}
        onClick={() => onMode("modify")}
      >
        修改分类
      </Button>
      <Button
        className={mode === "exclude" ? "active is-exclude" : ""}
        icon={<EyeSlash size={17} />}
        onClick={() => onMode("exclude")}
      >
        排除本条
      </Button>
    </div>
  );
}

/** @param {Pick<import("./reviewRecordPresentation").ReviewRecordDrawerProps, "labels" | "mode" | "labelCode" | "reason" | "conflict" | "saving" | "assessment" | "onMode" | "onAssessment" | "onLabelCode" | "onReason" | "onSave" | "onSaveAndNext" | "onUseServer" | "onContinueWithServer"> & {editable: boolean, labelQuery: string, onLabelQuery: (query: string) => void}} props */
export function ReviewRecordEditor({
  labels,
  editable,
  mode,
  labelCode,
  reason,
  conflict,
  saving,
  assessment,
  labelQuery,
  onLabelQuery,
  onMode,
  onAssessment,
  onLabelCode,
  onReason,
  onSave,
  onSaveAndNext,
  onUseServer,
  onContinueWithServer,
}) {
  const labelGroups = useMemo(
    () => groupedLabels(labels, labelQuery),
    [labelQuery, labels],
  );
  const saveDisabled =
    saving || Boolean(conflict) || !reason.trim() || (mode === "modify" && !labelCode);
  return (
    <>
      {conflict && (
        <ReviewRecordConflict
          conflict={conflict}
          mode={mode}
          labelCode={labelCode}
          reason={reason}
          onUseServer={onUseServer}
          onContinueWithServer={onContinueWithServer}
        />
      )}
      {editable && (
        <section className="review-record-editor">
          <b>复核结论</b>
          <ReviewResolutionOptions mode={mode} onMode={onMode} />
          <fieldset className="review-assessment-fields">
            <legend>复核质量判断</legend>
            <p>分别评价标签、证据和是否应进入人工复核。</p>
            <div>
              {REVIEW_ASSESSMENT_FIELDS.map((field) => (
                <label key={field.key}>
                  {field.label}
                  <Select
                    aria-label={field.label}
                    value={assessment[field.key]}
                    onChange={(value) =>
                      onAssessment({
                        ...assessment,
                        [field.key]: value,
                      })
                    }
                    options={field.options.map(([value, label]) => ({
                      value,
                      label,
                    }))}
                  />
                </label>
              ))}
            </div>
          </fieldset>
          {mode === "modify" && (
            <div className="review-label-picker">
              <label>
                搜索分类标签
                <Input
                  aria-label="搜索分类标签"
                  value={labelQuery}
                  onChange={(event) => onLabelQuery(event.target.value)}
                  placeholder="输入标签名称或编码"
                />
              </label>
              <label>
                修改为
                <Select
                  aria-label="修改分类标签"
                  value={labelCode}
                  onChange={onLabelCode}
                  options={[
                    { value: "", label: "请选择分类标签" },
                    ...Object.entries(labelGroups).map(([group, options]) => ({
                      label: group,
                      options: options.map((label) => ({
                        value: label.code,
                        label: `${labelText(label)} · ${label.code}`,
                      })),
                    })),
                  ]}
                />
              </label>
            </div>
          )}
          {mode === "exclude" && (
            <div className="review-exclude-note" role="status">
              <EyeSlash size={18} />
              此记录会保留在系统和审计历史中，但不进入语义分析和看板指标。
            </div>
          )}
          <label>
            处理原因
            <Input.TextArea
              rows={4}
              required
              value={reason}
              onChange={(event) => onReason(event.target.value)}
              placeholder="必填：说明确认、修改或排除的判断依据"
            />
          </label>
          <div className="review-record-save-actions">
            <Button disabled={saveDisabled} onClick={onSave}>
              仅保存
            </Button>
            <Button type="primary" disabled={saveDisabled} onClick={onSaveAndNext}>
              {saving ? "正在保存…" : "保存并下一条"}
            </Button>
          </div>
        </section>
      )}
    </>
  );
}
