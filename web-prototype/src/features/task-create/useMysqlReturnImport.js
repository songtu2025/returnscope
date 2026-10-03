import { useEffect, useState } from "react";
import useSWR from "swr";
import { api } from "../../api";
import { serverStateKeys } from "../../shared/serverState";
import { datePresets } from "./mysqlReturnDates";
import { mysqlImportReadiness } from "./mysqlImportReadiness";

/** @typedef {import("./mysqlReturnContracts").MysqlSchema} MysqlSchema */
/** @typedef {import("./mysqlReturnContracts").MysqlReturnRequest} MysqlReturnRequest */
/** @typedef {import("./mysqlReturnContracts").MysqlImportResult} MysqlImportResult */
/** @typedef {import("./mysqlReturnContracts").MysqlReturnFormState} MysqlReturnFormState */
/** @typedef {import("./mysqlReturnContracts").MysqlPreview} MysqlPreview */

/**
 * 本组件使用的 MySQL API 边界。共享请求层尚未声明响应类型，因此在消费端集中约束一次。
 * @type {{
 *   mysqlReturnSchema: (options?: { refresh?: boolean, signal?: AbortSignal }) => Promise<MysqlSchema>,
 *   previewMysqlReturns: (payload: MysqlReturnRequest, options?: { signal?: AbortSignal }) => Promise<MysqlPreview>,
 *   importMysqlReturns: (payload: MysqlReturnRequest) => Promise<MysqlImportResult>
 * }}
 */
const mysqlReturnApi = api;

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

/** @param {Partial<MysqlReturnFormState> | undefined} draft */
function initialForm(draft) {
  const defaultRange = datePresets()[2];
  return {
    default_store: "",
    date_from: defaultRange.date_from,
    date_to: defaultRange.date_to,
    store: "",
    sku: "",
    ...draft,
    mapping: draft?.mapping ?? {},
  };
}

/** @param {import("./mysqlReturnContracts").MysqlReturnImportFormProps} props */
export function useMysqlReturnImport({
  onDone,
  draft,
  onDraftChange,
  onStateChange,
  onInvalidate,
  prepared = false,
  disabled = false,
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState(/** @type {MysqlPreview | null} */ (null));
  const [refreshingSchema, setRefreshingSchema] = useState(false);
  const [previewRevision, setPreviewRevision] = useState(0);
  const [form, setForm] = useState(() => initialForm(draft));
  const {
    data: schema,
    error: schemaError,
    isLoading: loadingSchema,
    mutate: mutateSchema,
  } = useSWR(serverStateKeys.mysqlReturnSchema, () =>
    mysqlReturnApi.mysqlReturnSchema(),
  );
  const loading = (loadingSchema && !schema) || refreshingSchema;
  const displayError = error || (schemaError ? errorMessage(schemaError) : "");

  useEffect(() => {
    if (!schema?.configured) return;
    setForm((current) => ({
      ...current,
      mapping: {
        ...schema.mapping,
        ...current.mapping,
      },
    }));
  }, [schema]);

  useEffect(() => {
    onDraftChange?.(form);
  }, [form, onDraftChange]);

  const refreshSchema = () => {
    onInvalidate?.();
    setPreview(null);
    setBusy("");
    setError("");
    setRefreshingSchema(true);
    void mysqlReturnApi
      .mysqlReturnSchema({ refresh: true })
      .then((result) => mutateSchema(result, { revalidate: false }))
      .catch((requestError) => setError(errorMessage(requestError)))
      .finally(() => setRefreshingSchema(false));
  };

  /** @param {Partial<MysqlReturnFormState>} changes */
  const update = (changes) => {
    onInvalidate?.();
    setBusy("");
    setForm((current) => ({ ...current, ...changes }));
    setPreview(null);
    setError("");
  };
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const importData = async (event) => {
    event.preventDefault();
    if (!canPrepare || busy || disabled) return;
    setBusy("import");
    setError("");
    try {
      await onDone(
        await mysqlReturnApi.importMysqlReturns({
          ...form,
          date_from: form.date_from || null,
          date_to: form.date_to || null,
        }),
      );
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy("");
    }
  };
  const { mappingReady, invalidDateRange, canPrepare } = mysqlImportReadiness(
    schema,
    form,
    loading,
    preview,
  );

  useEffect(() => {
    onStateChange?.({ ready: canPrepare, busy, rowCount: preview?.row_count ?? 0 });
  }, [canPrepare, busy, preview, onStateChange]);

  useEffect(() => {
    if (prepared || loading || !schema?.configured || !mappingReady || invalidDateRange)
      return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setBusy("preview");
      setError("");
      try {
        const result = await mysqlReturnApi.previewMysqlReturns(
          {
            ...form,
            date_from: form.date_from || null,
            date_to: form.date_to || null,
          },
          { signal: controller.signal },
        );
        if (!controller.signal.aborted) setPreview(result);
      } catch (requestError) {
        if (!controller.signal.aborted) setError(errorMessage(requestError));
      } finally {
        if (!controller.signal.aborted) setBusy("");
      }
    }, 450);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [
    form,
    loading,
    schema,
    mappingReady,
    invalidDateRange,
    previewRevision,
    prepared,
  ]);

  return {
    error,
    busy,
    preview,
    form,
    schema,
    loading,
    displayError,
    mappingReady,
    invalidDateRange,
    refreshSchema,
    update,
    importData,
    setPreviewRevision,
  };
}
