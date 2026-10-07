import { PageHeading, PageLoadingState } from "../../components/SharedUi";
import { ModelPreferenceForm } from "./ModelPreferenceForm";
import { useModelPreference } from "./useModelPreference";

/** @param {{notify: (message: string, tone?: string) => void}} props */
export function ModelPreferencePage({ notify }) {
  const preference = useModelPreference(notify);
  return (
    <div className="standard-page model-preference-page">
      <PageHeading
        eyebrow="个人默认设置"
        title="我的模型偏好"
        description="新建任务会默认带入此策略；你仍可在创建任务时针对本次执行调整。"
      />
      {preference.loading ? (
        <PageLoadingState label="正在读取个人模型偏好…" heading={false} />
      ) : (
        <ModelPreferenceForm {...preference} />
      )}
    </div>
  );
}
