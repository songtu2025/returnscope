import { SlidersHorizontal } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { formatTime } from "../../lib/presentation";

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceEditorProps, "selectedVersion" | "selectedConnection" | "editing" | "activePanel" | "validationActive" | "busy" | "onBeginEdit">} props */
export function ModelServiceEditorHeader({
  selectedVersion,
  selectedConnection,
  editing,
  activePanel,
  validationActive,
  busy,
  onBeginEdit,
}) {
  return (
    <header>
      <ModelServiceVersionIdentity
        selectedVersion={selectedVersion}
        selectedConnection={selectedConnection}
        editing={editing}
      />
      {selectedVersion &&
        !editing &&
        ["connection", "limits"].includes(activePanel) && (
          <Button
            autoInsertSpace={false}
            icon={<SlidersHorizontal size={17} />}
            disabled={validationActive || Boolean(busy)}
            onClick={() => onBeginEdit(activePanel)}
          >
            编辑配置
          </Button>
        )}
    </header>
  );
}

/** @param {Pick<import("./modelServiceViewContracts").ModelServiceEditorProps, "selectedVersion" | "selectedConnection" | "editing">} props */
function ModelServiceVersionIdentity({ selectedVersion, selectedConnection, editing }) {
  const validationStatus = selectedVersion?.validation_status;
  const label = editing
    ? "编辑中"
    : validationStatus === "validated"
      ? "已验证"
      : validationStatus === "failed"
        ? "验证失败"
        : "配置草稿";
  return (
    <div>
      <span className="asset-type">{label}</span>
      <h2>
        {selectedConnection?.name ?? selectedVersion?.connection_name ?? "新建模型服务"}
      </h2>
      <p>
        {selectedVersion
          ? `配置 #${selectedVersion.version} · ${selectedVersion.creator_name ?? "—"} · ${formatTime(selectedVersion.created_at)}`
          : "创建一条 Responses API 兼容模型服务"}
      </p>
    </div>
  );
}
