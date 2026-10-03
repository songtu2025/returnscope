import { useState } from "react";
import { modelApi as modelServiceApi } from "../../shared/api/modelApi";
import { errorMessage, getModelDraftError } from "./modelServiceConfig";

/** @typedef {import("./modelServiceViewContracts").CatalogModel} CatalogModel */
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelEditorMode} ModelEditorMode */
/** @typedef {import("../../shared/api/systemSettingsContracts").ModelDraft} ModelDraft */
/** @typedef {import("./modelServiceViewContracts").ValidationRun} ValidationRun */

/**
 * @param {object} options
 * @param {ReturnType<typeof import("./useModelServiceConnections").useModelServiceConnections>} options.connectionState
 * @param {ReturnType<typeof import("./useModelServiceConfiguration").useModelServiceConfiguration>} options.configuration
 * @param {(message: string, type?: "success" | "error") => void} options.notify
 * @param {CatalogModel[]} options.draftModels
 * @param {import("react").Dispatch<import("react").SetStateAction<CatalogModel[]>>} options.setDraftModels
 * @param {string} options.busy
 * @param {(busy: string) => void} options.setBusy
 * @param {(run: ValidationRun, ownerId: string | null) => void} options.showValidationRun
 */
export function useModelServiceCatalog({
  connectionState,
  configuration,
  notify,
  draftModels,
  setDraftModels,
  busy,
  setBusy,
  showValidationRun,
}) {
  const { setConnections, selectedConnection, selectedConnectionId, load } =
    connectionState;
  const { form, editing, preserveConfigFormRef } = configuration;
  const catalogModels = selectedConnection?.models ?? draftModels;
  const [modelEditor, setModelEditor] = useState(
    /** @type {ModelEditorMode | null} */ (null),
  );
  const [modelDraft, setModelDraft] = useState(/** @type {ModelDraft | null} */ (null));
  /** @param {CatalogModel | null} [model] */
  const openModelEditor = (model = null) => {
    setModelEditor(model ? "edit" : "create");
    setModelDraft(
      model
        ? {
            ...model,
            supported_efforts: [...model.supported_efforts],
          }
        : {
            model_key: "",
            display_name: "",
            supported_efforts: ["low", "medium", "high"],
            active: true,
          },
    );
  };

  const closeModelEditor = () => {
    if (busy === "model-save") return;
    setModelEditor(null);
    setModelDraft(null);
  };

  /**
   * @param {CatalogModel} value
   * @param {boolean} [append]
   */
  const mergeModel = (value, append = false) => {
    preserveConfigFormRef.current = editing;
    setConnections((current) =>
      current.map((connection) =>
        connection.id === value.connection_id
          ? {
              ...connection,
              models: append
                ? [...(connection.models ?? []), value]
                : (connection.models ?? []).map((model) =>
                    model.id === value.id ? value : model,
                  ),
            }
          : connection,
      ),
    );
  };

  const saveModel = async () => {
    if (!modelDraft) return;
    const error = getModelDraftError(modelDraft, modelEditor, catalogModels);
    if (error) {
      notify(error, "error");
      return;
    }
    const modelKey = modelDraft.model_key.trim();
    const modelId = modelDraft.id;
    const payload = {
      model_key: modelKey,
      display_name: modelDraft.display_name.trim() || modelKey,
      supported_efforts: modelDraft.supported_efforts,
      active: modelDraft.active,
    };
    setBusy("model-save");
    try {
      if (!selectedConnection) {
        if (modelEditor === "create") {
          setDraftModels((current) => [
            ...current,
            {
              ...payload,
              id: `draft-${modelKey}`,
              validation_status: "draft",
            },
          ]);
        } else {
          setDraftModels((current) =>
            current.map((model) =>
              model.id === modelDraft.id ? { ...model, ...payload } : model,
            ),
          );
        }
      } else if (modelEditor === "create") {
        const value = await modelServiceApi.createModel(selectedConnection.id, payload);
        mergeModel(value, true);
      } else {
        if (!modelId) return;
        const value = await modelServiceApi.updateModel(modelId, {
          display_name: payload.display_name,
          supported_efforts: payload.supported_efforts,
          active: payload.active,
        });
        mergeModel(value);
      }
      setModelEditor(null);
      setModelDraft(null);
      notify(modelEditor === "create" ? "模型已添加" : "模型已更新");
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };

  /** @param {CatalogModel} model */
  const toggleModel = async (model) => {
    if (
      !selectedConnection &&
      model.active &&
      [form.cheap_model, form.primary_model, form.secondary_model].includes(
        model.model_key,
      )
    ) {
      notify("请先从模型流水线中移除该模型", "error");
      return;
    }
    if (!selectedConnection) {
      setDraftModels((current) =>
        current.map((item) =>
          item.id === model.id ? { ...item, active: !item.active } : item,
        ),
      );
      return;
    }
    setBusy(`model-toggle-${model.id}`);
    try {
      const value = await modelServiceApi.updateModel(model.id, {
        display_name: model.display_name,
        supported_efforts: model.supported_efforts,
        active: !model.active,
      });
      mergeModel(value);
      notify(model.active ? "模型已停用" : "模型已启用");
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };

  /** @param {CatalogModel} model */
  const validateCatalogModel = async (model) => {
    const ownerId = selectedConnectionId;
    setBusy("validation-start");
    try {
      const value = await modelServiceApi.startModelValidation(model.id);
      showValidationRun(value, ownerId);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };

  const discoverModels = async () => {
    if (!selectedConnection) return;
    setBusy("model-discover");
    try {
      const value = await modelServiceApi.discoverModels(selectedConnection.id);
      await load();
      notify(`已读取 ${value.count} 个接入方模型；目录外模型已停用`, "success");
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };

  return {
    catalogModels,
    modelEditor,
    modelDraft,
    setModelDraft,
    openModelEditor,
    closeModelEditor,
    saveModel,
    toggleModel,
    validateCatalogModel,
    discoverModels,
  };
}
