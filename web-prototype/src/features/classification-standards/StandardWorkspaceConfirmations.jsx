import Button from "antd/es/button";
import { Modal } from "../../components/SharedUi";

/** @typedef {import("./classificationStandardWorkspaceContracts").StandardWorkspaceContext} StandardWorkspaceContext */

/** @param {import("./classificationStandardWorkspaceContracts").StandardWorkspaceContext} context */
export function StandardWorkspaceConfirmations(context) {
  const { confirmBack, setConfirmBack, onBack } = context;
  return (
    <>
      {confirmBack && (
        <Modal
          eyebrow="未保存修改"
          title="离开编辑页？"
          onClose={() => setConfirmBack(false)}
        >
          <div className="label-action-confirm">
            <p>尚未保存的修改会丢失。可以继续编辑，或放弃本次未保存内容。</p>
            <div>
              <Button onClick={() => setConfirmBack(false)}>继续编辑</Button>
              <Button type="primary" danger onClick={onBack}>
                放弃修改并返回
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
