import { WarningCircle } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import {
  EmptyState,
  Modal,
  PageHeading,
  PageLoadingState,
} from "../../components/SharedUi";
import { NAVIGATION_REQUEST_EVENT } from "../../app/navigationGuard";
import { useExitConfirmation } from "../../hooks/useExitConfirmation";
import { ModelPreferenceForm } from "./ModelPreferenceForm";
import { useModelPreference } from "./useModelPreference";

/** @param {{notify: (message: string, tone?: string) => void}} props */
export function ModelPreferencePage({ notify }) {
  const preference = useModelPreference(notify);
  const exit = useExitConfirmation();
  const saveButtonRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const [failedSaveAttempt, setFailedSaveAttempt] = useState(0);
  useEffect(() => {
    if (failedSaveAttempt > 0) saveButtonRef.current?.focus();
  }, [failedSaveAttempt]);
  useEffect(() => {
    if (!preference.dirty && !preference.saving) return;
    const requestExit = (/** @type {Event} */ event) => {
      event.preventDefault();
      const request = /** @type {CustomEvent<{proceed: () => void}>} */ (event);
      exit.requestExit(true, request.detail.proceed);
    };
    const beforeUnload = (/** @type {BeforeUnloadEvent} */ event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener(NAVIGATION_REQUEST_EVENT, requestExit);
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      window.removeEventListener(NAVIGATION_REQUEST_EVENT, requestExit);
      window.removeEventListener("beforeunload", beforeUnload);
    };
  }, [exit, preference.dirty, preference.saving]);
  const continueEditing = () => {
    if (!preference.saving) exit.continueEditing();
  };
  return (
    <div className="standard-page model-preference-page">
      <PageHeading title="我的模型偏好" />
      {preference.loading ? (
        <PageLoadingState label="正在读取个人模型偏好…" />
      ) : preference.error && !preference.hasData ? (
        <div role="alert">
          <EmptyState
            icon={WarningCircle}
            title="模型偏好读取失败"
            description={preference.error}
            action={
              <button className="secondary-button" onClick={preference.load}>
                重试
              </button>
            }
          />
        </div>
      ) : (
        <>
          {preference.error && (
            <p role="alert">模型偏好更新失败，当前显示上次数据：{preference.error}</p>
          )}
          <ModelPreferenceForm {...preference} />
        </>
      )}
      {exit.pendingExit && (
        <Modal title="模型偏好尚未保存" onClose={continueEditing}>
          <div className="modal-form">
            <p>离开前是否保存本次模型偏好修改？</p>
            <div className="modal-actions">
              <button
                className="secondary-button"
                disabled={preference.saving}
                onClick={continueEditing}
              >
                继续编辑
              </button>
              <button
                className="secondary-button"
                disabled={preference.saving}
                onClick={() => {
                  preference.reset();
                  exit.discardChanges();
                }}
              >
                放弃修改并离开
              </button>
              <button
                ref={saveButtonRef}
                className="primary-button"
                disabled={preference.saving}
                onClick={async () => {
                  if (await preference.save()) exit.discardChanges();
                  else setFailedSaveAttempt((attempt) => attempt + 1);
                }}
              >
                {preference.saving ? "保存中…" : "保存后离开"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
