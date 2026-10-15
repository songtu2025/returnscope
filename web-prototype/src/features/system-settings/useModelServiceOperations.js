import { modelApi } from "../../shared/api/modelApi";
import { errorMessage } from "./modelServiceConfig";

/** @param {{connectionState: ReturnType<typeof import('./useModelServiceConnections').useModelServiceConnections>, form: import('./modelServiceViewContracts').ModelServiceForm, draftModels: import('./modelServiceViewContracts').CatalogModel[], selectedVersion: import('./modelServiceViewContracts').ConfigVersion | null, onSaved: (value: import('./modelServiceViewContracts').ConfigVersion) => void, onDiscarded: () => void, setBusy: (value: string) => void, notify: (message: string, type?: 'success' | 'error') => void}} options */
export function useModelServiceOperations({
  connectionState,
  form,
  draftModels,
  selectedVersion,
  onSaved,
  onDiscarded,
  setBusy,
  notify,
}) {
  const { selectedConnection, draftVersion, load } = connectionState;
  const refresh = async (/** @type {string | null} */ connectionId = null) => {
    try {
      await load(false, connectionId);
    } catch {
      notify("操作已完成，列表刷新失败，请重新加载。", "error");
    }
  };
  const save = async () => {
    setBusy("save");
    try {
      const value = await modelApi.createConfig({
        ...form,
        cheap_model: null,
        secondary_model: null,
        change_note: "",
        connection_id: selectedConnection?.id ?? null,
        models: selectedConnection
          ? undefined
          : draftModels.map(
              ({ model_key, display_name, supported_efforts, active }) => ({
                model_key,
                display_name,
                supported_efforts,
                active,
              }),
            ),
      });
      onSaved(value);
      await refresh(value.connection_id);
      notify(`配置 #${value.version} 草稿已保存，请验证连接与选定模型`);
      return true;
    } catch (error) {
      notify(errorMessage(error), "error");
      return false;
    } finally {
      setBusy("");
    }
  };
  const publishVersion = async (
    /** @type {import('./modelServiceViewContracts').ConfigVersion | null} */ version = selectedVersion,
  ) => {
    if (!version) return;
    setBusy("publish");
    try {
      await modelApi.publishConfig(version.id);
      await refresh();
      notify(`配置 #${version.version} 已发布`);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };
  const discardDraft = async () => {
    if (!draftVersion) return;
    setBusy("discard-draft");
    try {
      await modelApi.discardConfig(draftVersion.id);
      await refresh();
      notify(`草稿 #${draftVersion.version} 已放弃`);
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
      onDiscarded();
    }
  };
  return { save, publish: () => publishVersion(), publishVersion, discardDraft };
}
