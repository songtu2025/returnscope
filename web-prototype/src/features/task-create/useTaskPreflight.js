import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../api";
import { resolveTaskModelPolicy } from "./newTaskPolicy";

export function useTaskPreflight({
  configs,
  form,
  loadingSetup,
  prepared,
  setSubmitError,
}) {
  const requestRef = useRef(0);
  const [preflight, setPreflight] = useState({
    status: "idle",
    data: null,
    error: "",
  });
  const [dataQuality, setDataQuality] = useState(null);
  const [unresolvedPolicy, setUnresolvedPolicy] = useState("");
  const [scopeConfirmed, setScopeConfirmed] = useState(false);
  const [segmentOrder, setSegmentOrder] = useState([]);

  const invalidatePreflight = useCallback(() => {
    requestRef.current += 1;
    setPreflight({ status: "idle", data: null, error: "" });
    setScopeConfirmed(false);
    setUnresolvedPolicy("");
  }, []);

  const runPreflight = useCallback(async () => {
    const requestId = ++requestRef.current;
    setSubmitError("");
    setPreflight({ status: "loading", data: null, error: "" });
    setDataQuality(null);
    setUnresolvedPolicy("");
    setScopeConfirmed(false);
    setSegmentOrder([]);
    try {
      const [data, quality] = await Promise.all([
        api.preflightTask({
          dataset_version_id: form.dataset_version_id,
          product_version_id: form.product_version_id,
          config_version_id: form.config_version_id,
          model_policy: resolveTaskModelPolicy(configs, form),
          store: null,
          listing: null,
        }),
        api.qualityPreflight(form.dataset_version_id, form.product_version_id),
      ]);
      if (requestId !== requestRef.current) return;
      setDataQuality(quality);
      setPreflight({ status: "ready", data, error: "" });
      setSegmentOrder(data.segments.map((segment) => segment.segment_key));
      setUnresolvedPolicy(data.blocked_count > 0 ? "" : "block_all");
    } catch (error) {
      if (requestId !== requestRef.current) return;
      const message =
        error.status === 405
          ? "当前运行服务未加载任务预检能力，请重启服务后重试（PF-405）。"
          : error.message;
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
    dataQuality,
    invalidatePreflight,
    preflight,
    runPreflight,
    scopeConfirmed,
    segmentOrder,
    setPreflight,
    setScopeConfirmed,
    setSegmentOrder,
    setUnresolvedPolicy,
    unresolvedPolicy,
  };
}
