import Button from "antd/es/button";
import { Modal } from "../../components/SharedUi";

/** @typedef {import("./classificationStandardWorkspaceContracts").StandardWorkspaceContext} StandardWorkspaceContext */

/** @param {import("./classificationStandardWorkspaceContracts").StandardWorkspaceContext} context */
export function StandardWorkspaceConfirmations(context) {
  const {
    confirmBack,
    setConfirmBack,
    onBack,
    confirmPublish,
    draft,
    setConfirmPublish,
    validationEvidence,
    onPublish,
  } = context;
  return (
    <>
      {confirmBack && (
        <Modal
          eyebrow="未保存修改"
          title="离开编辑页？"
          onClose={() => setConfirmBack(false)}
        >
          <div className="label-action-confirm">
            <p>尚未保存的修改会丢失。可以继续编辑并保存草稿，或放弃本次未保存内容。</p>
            <div>
              <Button onClick={() => setConfirmBack(false)}>继续编辑</Button>
              <Button type="primary" danger onClick={onBack}>
                放弃修改并返回
              </Button>
            </div>
          </div>
        </Modal>
      )}
      {confirmPublish && draft && (
        <Modal
          eyebrow="发布标签体系"
          title="发布并立即启用当前草稿？"
          onClose={() => setConfirmPublish(false)}
        >
          <div className="label-action-confirm">
            <p>
              发布后会生成新的不可变版本，并立即用于新任务；当前已发布版本仍保留，可用于恢复。
            </p>
            {validationEvidence ? (
              <p>
                已选择草稿 r{validationEvidence.draft_revision} 的测试记录。
                {validationEvidence.quality_gate?.passed === false
                  ? "自动质量检查未通过，你仍可根据业务判断验收并发布。"
                  : "自动质量检查已通过，仍请以业务判断为准。"}
              </p>
            ) : (
              <p>当前没有可关联的已完成测试，本次将作为直接发布记录。</p>
            )}
            <div>
              <Button onClick={() => setConfirmPublish(false)}>取消</Button>
              {validationEvidence && (
                <Button
                  onClick={() => {
                    setConfirmPublish(false);
                    void onPublish(null);
                  }}
                >
                  直接发布
                </Button>
              )}
              <Button
                type="primary"
                onClick={() => {
                  setConfirmPublish(false);
                  void onPublish(validationEvidence?.id ?? null);
                }}
              >
                {standardConfirmationLabel(validationEvidence)}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

/** @param {StandardWorkspaceContext["validationEvidence"]} validationEvidence */
function standardConfirmationLabel(validationEvidence) {
  return validationEvidence
    ? validationEvidence.quality_gate?.passed === false
      ? "接受测试结果并发布"
      : "验收并发布"
    : "确认直接发布";
}
