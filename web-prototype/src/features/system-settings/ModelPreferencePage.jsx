import { WarningCircle } from "@phosphor-icons/react";
import { EmptyState, PageHeading, PageLoadingState } from "../../components/SharedUi";
import { ModelPreferenceForm } from "./ModelPreferenceForm";
import { useModelPreference } from "./useModelPreference";

/** @param {{notify: (message: string, tone?: string) => void}} props */
export function ModelPreferencePage({ notify }) {
  const preference = useModelPreference(notify);
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
    </div>
  );
}
