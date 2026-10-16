import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../api";
import { resolveTaskModelPolicy } from "./newTaskPolicy";

/** @typedef {import("./taskCreateContracts").ApiConnection} ApiConnection */
/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/** @typedef {import("./taskCreateContracts").TaskPreflightState} TaskPreflightState */
/** @typedef {import("../task-planning/taskPlanContracts").TaskExecutionPlan} TaskExecutionPlan */

/**
 * @param {{configs: ApiConnection[], form: TaskForm, loadingSetup: boolean, prepared: boolean, setSubmitError: import("react").Dispatch<import("react").SetStateAction<string>>}} options
 */

export function useTaskPreflight({
  configs,
  form,
  loadingSetup,
  prepared,
  setSubmitError,
}) {
  const requestRef = useRef(0);
  const [preflight, setPreflight] = useState(
    /** @type {TaskPreflightState} */ ({
      status: "idle",
      data: null,
      error: "",
    }),
  );
  const [unresolvedPolicy, setUnresolvedPolicy] = useState("");
  const [scopeConfirmed, setScopeConfirmed] = useState(false);
  const [segmentOrder, setSegmentOrder] = useState(/** @type {string[]} */ ([]));
  const [selectedKeys, setSelectedKeys] = useState(/** @type {string[]} */ ([]));
  const selectionInitialized = useRef(false);

  const invalidatePreflight = useCallback(() => {
    selectionInitialized.current = false;
    requestRef.current += 1;
    setPreflight({ status: "idle", data: null, error: "" });
    setScopeConfirmed(false);
    setUnresolvedPolicy("");
  }, []);

  const runPreflight = useCallback(async () => {
    const requestId = ++requestRef.current;
    setSubmitError("");
    setPreflight({ status: "loading", data: null, error: "" });
    setUnresolvedPolicy("");
    setScopeConfirmed(false);
    try {
      const data = /** @type {TaskExecutionPlan} */ (
        await api.preflightTask({
          dataset_version_id: form.dataset_version_id,
          product_version_id: form.product_version_id,
          config_version_id: form.config_version_id,
          model_policy: resolveTaskModelPolicy(configs, form),
          store: null,
          listing: null,
        })
      );
      if (requestId !== requestRef.current) return;
      setPreflight({ status: "ready", data, error: "" });
      const keys = data.segments.map((segment) => segment.segment_key);
      const preserve = selectionInitialized.current;
      setSegmentOrder((previous) =>
        preserve
          ? [
              ...previous.filter((key) => keys.includes(key)),
              ...keys.filter((key) => !previous.includes(key)),
            ]
          : keys,
      );
      setSelectedKeys((previous) =>
        preserve ? previous.filter((key) => keys.includes(key)) : keys,
      );
      selectionInitialized.current = true;
      setUnresolvedPolicy(data.blocked_count > 0 ? "" : "block_all");
    } catch (error) {
      if (requestId !== requestRef.current) return;
      const status =
        typeof error === "object" && error !== null && "status" in error
          ? error.status
          : undefined;
      const message =
        status === 405
          ? "当前运行服务未加载任务预检能力，请重启服务后重试（PF-405）。"
          : error instanceof Error
            ? error.message
            : "任务预检失败";
      setPreflight({ status: "error", data: null, error: message });
    }
  }, [configs, form, setSubmitError]);

  useEffect(() => {
    if (
      prepared &&
      !loadingSetup &&
      form.dataset_version_id &&
      preflight.status === "idle"
    ) {
      const timer = setTimeout(runPreflight, 350);
      return () => clearTimeout(timer);
    }
  }, [form.dataset_version_id, loadingSetup, preflight.status, runPreflight, prepared]);

  useEffect(
    () => () => {
      requestRef.current += 1;
    },
    [],
  );

  return {
    invalidatePreflight,
    preflight,
    runPreflight,
    scopeConfirmed,
    segmentOrder,
    segmentSelection: {
      keys: selectedKeys,
      onChange: (/** @type {string[]} */ keys) => {
        setSelectedKeys(keys);
        setScopeConfirmed(false);
      },
    },
    setPreflight,
    setScopeConfirmed,
    setSegmentOrder,
    setUnresolvedPolicy,
    unresolvedPolicy,
  };
}
