import { ShieldCheck } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { Modal } from "../../components/SharedUi";

/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRowsPage} DatasetRowsPage */
/** @typedef {import("../../shared/api/dataManagementContracts").DatasetRow} DatasetRow */
/** @typedef {import("react").Dispatch<import("react").SetStateAction<DatasetRow | null>>} SetEditing */
/** @typedef {import("react").Dispatch<import("react").SetStateAction<number>>} SetPage */

/** @param {{editing: DatasetRow, setEditing: SetEditing}} props */
function ProductIdentityFields({ editing, setEditing }) {
  return (
    <fieldset className="product-info-form-section product-info-identity-fields">
      <legend>匹配标识</legend>
      <div>
        <label>
          MSKU
          <input
            value={editing.MSKU}
            onChange={(event) => setEditing({ ...editing, MSKU: event.target.value })}
            required
          />
        </label>
        <label>
          店铺 / 站点
          <input
            value={editing["店铺/站点"]}
            onChange={(event) =>
              setEditing({ ...editing, "店铺/站点": event.target.value })
            }
            required
          />
        </label>
        <label>
          Listing
          <input
            value={editing.Listing}
            onChange={(event) =>
              setEditing({ ...editing, Listing: event.target.value })
            }
            required
          />
        </label>
      </div>
    </fieldset>
  );
}

/** @param {{editing: DatasetRow, setEditing: SetEditing}} props */
function ProductAttributeFields({ editing, setEditing }) {
  return (
    <fieldset className="product-info-form-section product-info-attribute-fields">
      <legend>产品属性</legend>
      <div>
        {editing["产品名称"] !== undefined && (
          <label className="product-info-name-field">
            产品名称
            <input
              value={editing["产品名称"]}
              onChange={(event) =>
                setEditing({ ...editing, 产品名称: event.target.value })
              }
            />
          </label>
        )}
        {editing["品类A"] !== undefined && (
          <label>
            品类A
            <input
              value={editing["品类A"]}
              onChange={(event) =>
                setEditing({ ...editing, 品类A: event.target.value })
              }
            />
          </label>
        )}
        {editing["品类B"] !== undefined && (
          <label>
            品类B
            <input
              value={editing["品类B"]}
              onChange={(event) =>
                setEditing({ ...editing, 品类B: event.target.value })
              }
            />
          </label>
        )}
      </div>
    </fieldset>
  );
}

/** @param {{changeNote: string, setChangeNote: (value: string) => void}} props */
function ProductChangeNote({ changeNote, setChangeNote }) {
  return (
    <label className="product-info-change-note">
      修改原因
      <textarea
        value={changeNote}
        onChange={(event) => setChangeNote(event.target.value)}
        rows={2}
        maxLength={500}
        placeholder="必填：说明为什么修改这条产品信息"
        required
      />
    </label>
  );
}

/** @param {{dataset: DatasetRecord}} props */
function ProductVersionNotice({ dataset }) {
  return (
    <div className="snapshot-notice">
      <ShieldCheck size={18} />
      <span>
        保存后创建 v{dataset.current_version + 1}，历史任务仍保留 v
        {dataset.current_version} 快照。
      </span>
    </div>
  );
}

/** @param {{saving: boolean, onClose: () => void}} props */
function ProductEditActions({ saving, onClose }) {
  return (
    <div className="modal-actions">
      <Button autoInsertSpace={false} onClick={onClose}>
        取消
      </Button>
      <Button type="primary" htmlType="submit" disabled={saving}>
        {saving ? "正在创建新版本…" : "保存并创建新版本"}
      </Button>
    </div>
  );
}

/** @param {{dataset: DatasetRecord, editing: DatasetRow, setEditing: SetEditing, changeNote: string, setChangeNote: (value: string) => void, saving: boolean, onSave: (event: import("react").FormEvent<HTMLFormElement>) => void | Promise<void>, onClose: () => void}} props */
export function ProductDimensionEditDialog({
  dataset,
  editing,
  setEditing,
  changeNote,
  setChangeNote,
  saving,
  onSave,
  onClose,
}) {
  return (
    <Modal
      eyebrow="产品信息"
      title={`编辑产品信息 · ${editing.MSKU}`}
      onClose={onClose}
    >
      <form className="modal-form product-info-edit-form" onSubmit={onSave}>
        <ProductIdentityFields editing={editing} setEditing={setEditing} />
        <ProductAttributeFields editing={editing} setEditing={setEditing} />
        <ProductChangeNote changeNote={changeNote} setChangeNote={setChangeNote} />
        <ProductVersionNotice dataset={dataset} />
        <ProductEditActions saving={saving} onClose={onClose} />
      </form>
    </Modal>
  );
}
