import { TaskModelSettings } from "./TaskModelSettings";

/** @typedef {import("./taskCreateContracts").AvailableModel} AvailableModel */
/** @typedef {import("./taskCreateContracts").PublishedConfig} PublishedConfig */
/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/** @typedef {import("./taskCreateContracts").TaskModelPolicy} TaskModelPolicy */
/**
 * @typedef {{
 *   headingRef: import("react").RefObject<HTMLHeadingElement | null>,
 *   form: TaskForm,
 *   onFormChange: (form: TaskForm) => void,
 *   publishedConfigs: PublishedConfig[],
 *   selectedConfig?: PublishedConfig,
 *   availableModels: AvailableModel[],
 *   modelPolicy: TaskModelPolicy,
 *   onConnectionChange: (configId: string) => void,
 *   onModelPolicyChange: (changes: Record<string, string | number>) => void,
 *   children?: import("react").ReactNode
 * }} TaskConfigurationStepProps
 */

/** @param {TaskConfigurationStepProps} props */
export function TaskConfigurationStep({
  headingRef,
  form,
  onFormChange,
  publishedConfigs,
  selectedConfig,
  availableModels,
  modelPolicy,
  onConnectionChange,
  onModelPolicyChange,
  children,
}) {
  return (
    <section
      className="task-config-panel task-launch-panel"
      aria-labelledby="task-launch-title"
    >
      <div className="task-config-section">
        <header className="task-launch-heading">
          <h2 id="task-launch-title" ref={headingRef} tabIndex={-1}>
            确认并开始分析
          </h2>
        </header>
        <label className="task-config-choice task-title-input">
          任务名称
          <input
            value={form.title}
            maxLength={120}
            placeholder="为本次分析起个名字"
            onChange={(event) => onFormChange({ ...form, title: event.target.value })}
          />
        </label>
        <TaskModelSettings
          form={form}
          publishedConfigs={publishedConfigs}
          selectedConfig={selectedConfig}
          availableModels={availableModels}
          modelPolicy={modelPolicy}
          onConnectionChange={onConnectionChange}
          onModelPolicyChange={onModelPolicyChange}
        />
      </div>
      {children}
    </section>
  );
}
