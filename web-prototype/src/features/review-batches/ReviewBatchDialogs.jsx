import { EyeSlash, WarningCircle } from "@phosphor-icons/react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import Select from "antd/es/select";

import { Modal } from "../../components/SharedUi";
import { labelText } from "../../lib/taxonomyPresentation";

export function ReviewPublishDialog({
  open,
  batch,
  reason,
  error,
  publishing,
  onReason,
  onClose,
  onPublish,
}) {
  if (!open) return null;

  return (
    <Modal
      eyebrow="发布复核结果"
      title="生成新的分类结果版本"
      onClose={() => !publishing && onClose()}
    >
      <div className="review-publish-modal">
        <p>
          已确认或修改 {Number(batch.resolved_count || 0).toLocaleString()} 条， 已排除{" "}
          {Number(batch.excluded_count || 0).toLocaleString()} 条。
          发布会保留全部原始记录与审计轨迹；排除记录不进入语义分析和看板指标。
        </p>
        <label>
          发布原因
          <Input.TextArea
            rows="4"
            required
            value={reason}
            onChange={(event) => onReason(event.target.value)}
            placeholder="必填：说明本次复核版本的发布原因"
          />
        </label>
        {error && (
          <div className="review-conflict-message" role="alert">
            <WarningCircle size={18} /> {error}
          </div>
        )}
        <div className="modal-actions">
          <Button disabled={publishing} onClick={onClose}>
            取消
          </Button>
          <Button
            type="primary"
            disabled={publishing || !reason.trim()}
            onClick={onPublish}
          >
            {publishing ? "正在发布…" : "确认生成新版本"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function ReviewBulkDialog({
  action,
  checkedCount,
  labels,
  labelCode,
  reason,
  error,
  saving,
  onLabelCode,
  onReason,
  onClose,
  onSave,
}) {
  if (!action) return null;

  return (
    <Modal
      eyebrow="批量复核"
      title={
        {
          confirm: "批量确认原结果",
          modify: "批量修改分类",
          exclude: "批量排除记录",
        }[action]
      }
      onClose={() => !saving && onClose()}
    >
      <div className="review-publish-modal">
        <p>本次将处理 {checkedCount} 条待处理记录。</p>
        {action === "exclude" && (
          <div className="review-exclude-note" role="status">
            <EyeSlash size={18} />
            排除后仍保留原始记录和操作记录，但不纳入语义分析及看板指标。
          </div>
        )}
        {action === "modify" && (
          <label>
            修改为
            <Select
              aria-label="批量修改分类标签"
              value={labelCode}
              onChange={onLabelCode}
              options={[
                { value: "", label: "请选择分类标签" },
                ...labels.map((label) => ({
                  value: label.code,
                  label: `${labelText(label)} · ${label.code}`,
                })),
              ]}
            />
          </label>
        )}
        <label>
          处理原因
          <Input.TextArea
            rows="4"
            required
            value={reason}
            onChange={(event) => onReason(event.target.value)}
            placeholder="必填：说明本次批量处理的判断依据"
          />
        </label>
        {error && (
          <div className="review-conflict-message" role="alert">
            <WarningCircle size={18} /> {error}
          </div>
        )}
        <div className="modal-actions">
          <Button disabled={saving} onClick={onClose}>
            取消
          </Button>
          <Button
            type="primary"
            disabled={saving || !reason.trim() || (action === "modify" && !labelCode)}
            onClick={onSave}
          >
            {saving ? "正在处理…" : `确认处理 ${checkedCount} 条`}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
