import Button from "antd/es/button";
import { Modal } from "../../components/SharedUi";
import { UnsavedChangesActions } from "../../components/UnsavedChangesActions";
import { PRODUCT_EDIT_FIELDS } from "./useProductRowEditing";

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
      备注（可选）
      <textarea
        value={changeNote}
        onChange={(event) => setChangeNote(event.target.value)}
        rows={2}
        maxLength={500}
        placeholder="可补充本次修改的说明"
      />
    </label>
  );
}

/** @param {{saving: boolean, pendingExit: boolean, conflict?: boolean, onClose: () => void}} props */
function ProductEditActions({ saving, pendingExit, conflict, onClose }) {
  return (
    <div className="modal-actions">
      <Button
        autoInsertSpace={false}
        disabled={saving || pendingExit}
        onClick={onClose}
      >
        取消
      </Button>
      <Button
        type="primary"
        htmlType="submit"
        disabled={saving || pendingExit || conflict}
        autoInsertSpace={false}
      >
        {saving ? "正在保存…" : "保存"}
      </Button>
    </div>
  );
}

/** @param {ReturnType<typeof import("./useProductRowEditing").useProductRowEditing> & {editing: DatasetRow, onSave: (event?: import("react").FormEvent<HTMLFormElement>) => Promise<boolean>, onClose: () => void}} props */
export function ProductDimensionEditDialog({
  editing,
  setEditing,
  changeNote,
  setChangeNote,
  saving,
  formRef,
  navigationExit: exit,
  conflict = false,
  onSave,
  onClose,
  latest,
  error,
  confirmClose,
  continueEditing,
  discard,
  loadLatest,
  acceptLatest,
  original,
  conflictFields,
  unresolved,
  resolutions,
  resolveField,
}) {
  const close = exit.pendingExit ? exit.continueEditing : onClose;
  return (
    <Modal title={`编辑产品信息 · ${editing.MSKU}`} onClose={close}>
      <form
        ref={formRef}
        className="modal-form product-info-edit-form"
        onSubmit={onSave}
      >
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {exit.pendingExit && <UnsavedChangesActions guard={exit} />}
        {confirmClose && !exit.pendingExit && (
          <section role="alert" className="product-edit-confirm">
            <p>有未保存的修改，是否放弃？</p>
            <Button onClick={continueEditing}>继续编辑</Button>
            <Button onClick={discard}>放弃修改</Button>
          </section>
        )}
        {conflict && (
          <Button disabled={saving} onClick={loadLatest}>
            {saving ? "正在读取…" : "读取最新资料"}
          </Button>
        )}
        {latest && (
          <section className="product-edit-comparison" aria-label="最新资料核对">
            <table>
              <thead>
                <tr>
                  <th>字段</th>
                  <th>原始资料</th>
                  <th>最新资料</th>
                  <th>我的输入</th>
                  <th>采用值</th>
                </tr>
              </thead>
              <tbody>
                {PRODUCT_EDIT_FIELDS.filter(
                  (key) => editing[key] !== undefined || latest.row[key] !== undefined,
                ).map((key) => (
                  <tr key={key}>
                    <th>{key}</th>
                    <td>{String(original?.[key] ?? "--")}</td>
                    <td>{String(latest.row[key] ?? "--")}</td>
                    <td>{String(editing[key] ?? "--")}</td>
                    <td>
                      {conflictFields.includes(key) ? (
                        <fieldset className="product-conflict-choice" disabled={saving}>
                          <legend>{key}冲突</legend>
                          {[
                            { value: "mine", label: "我的输入" },
                            { value: "latest", label: "最新资料" },
                          ].map(({ value, label }) => (
                            <label key={value}>
                              <input
                                type="radio"
                                name={`resolve-${key}`}
                                checked={
                                  resolutions[key]?.choice === value &&
                                  resolutions[key]?.value === editing[key]
                                }
                                onChange={() =>
                                  resolveField(
                                    key,
                                    /** @type {"mine" | "latest"} */ (value),
                                  )
                                }
                              />
                              {label}
                            </label>
                          ))}
                        </fieldset>
                      ) : (
                        "自动合并"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p role="status">
              {unresolved.length
                ? `${unresolved.length} 个字段待选择`
                : "字段已核对，可应用结果后保存"}
            </p>
            <Button disabled={saving || unresolved.length > 0} onClick={acceptLatest}>
              应用核对结果
            </Button>
          </section>
        )}
        <fieldset disabled={saving} className="product-edit-fields">
          <ProductIdentityFields editing={editing} setEditing={setEditing} />
          <ProductAttributeFields editing={editing} setEditing={setEditing} />
          <ProductChangeNote changeNote={changeNote} setChangeNote={setChangeNote} />
        </fieldset>
        <ProductEditActions
          saving={saving}
          pendingExit={Boolean(exit.pendingExit)}
          conflict={conflict}
          onClose={close}
        />
      </form>
    </Modal>
  );
}
