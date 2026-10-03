import { CheckCircle, Power, WarningCircle } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { classNames } from "../../lib/presentation";

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceEditorProps, "selectedVersion" | "editing" | "busy" | "validationActive" | "validationRun" | "configFormErrors" | "onCancelEdit" | "onSave" | "saveDisabled" | "onValidate" | "onPublish" | "selectedVersionIsActive">} props */

export function ModelServiceActionBar({
  selectedVersion,
  editing,
  busy,
  validationActive,
  validationRun,
  configFormErrors,
  onCancelEdit,
  onSave,
  saveDisabled,
  onValidate,
  onPublish,
  selectedVersionIsActive,
}) {
  return (
    <div className="sticky-config-bar">
      <ModelServiceValidationStatus
        selectedVersion={selectedVersion}
        editing={editing}
        configFormErrors={configFormErrors}
      />
      {editing ? (
        <>
          <Button
            autoInsertSpace={false}
            onClick={onCancelEdit}
            disabled={Boolean(busy)}
          >
            取消
          </Button>
          <button className="primary-button" onClick={onSave} disabled={saveDisabled}>
            {busy === "save" ? "保存中…" : "保存草稿"}
          </button>
        </>
      ) : (
        selectedVersion && (
          <ModelServicePublishActions
            selectedVersion={selectedVersion}
            busy={busy}
            validationActive={validationActive}
            validationRun={validationRun}
            selectedVersionIsActive={selectedVersionIsActive}
            onValidate={onValidate}
            onPublish={onPublish}
          />
        )
      )}
    </div>
  );
}

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceEditorProps, "selectedVersion" | "editing" | "configFormErrors">} props */
function ModelServiceValidationStatus({ selectedVersion, editing, configFormErrors }) {
  const validationStatus = selectedVersion?.validation_status;
  return (
    <div>
      <span className={classNames("validation-state", validationStatus)}>
        {validationStatus === "validated" ? (
          <CheckCircle size={18} />
        ) : (
          <WarningCircle size={18} />
        )}
        {selectedVersion?.validation_message ||
          (editing ? "修改会创建新草稿版本" : "配置尚未验证")}
      </span>
      {configFormErrors.length > 0 && (
        <small className="config-save-disabled-reason" role="status">
          暂时无法保存：{configFormErrors.join("；")}
        </small>
      )}
    </div>
  );
}

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceEditorProps, "busy" | "validationActive" | "validationRun" | "selectedVersionIsActive" | "onValidate" | "onPublish"> & {selectedVersion: NonNullable<import("./modelServiceViewContracts").ModelServiceEditorProps["selectedVersion"]>}} props */
function ModelServicePublishActions({
  selectedVersion,
  busy,
  validationActive,
  validationRun,
  selectedVersionIsActive,
  onValidate,
  onPublish,
}) {
  const validationLabel = getValidationActionLabel(
    validationActive,
    validationRun,
    busy,
  );
  return (
    <>
      <button
        className="secondary-button"
        onClick={onValidate}
        disabled={Boolean(busy) || validationActive}
      >
        <Power size={17} />
        {validationLabel}
      </button>
      <button
        className="primary-button"
        disabled={
          selectedVersion.validation_status !== "validated" ||
          Boolean(busy) ||
          validationActive ||
          selectedVersionIsActive
        }
        onClick={onPublish}
      >
        {busy === "publish"
          ? "发布中…"
          : selectedVersionIsActive
            ? "当前已发布"
            : "发布为当前配置"}
      </button>
    </>
  );
}

/** @param {boolean} validationActive @param {import("./modelServiceViewContracts").ModelServiceEditorProps["validationRun"]} validationRun @param {string} busy */
function getValidationActionLabel(validationActive, validationRun, busy) {
  if (validationActive && validationRun?.kind === "config") return "验证进行中…";
  return busy === "validation-start" ? "启动中…" : "验证连接与模型";
}
