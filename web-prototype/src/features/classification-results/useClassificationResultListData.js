import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../../api";

/**
 * @param {NonNullable<import("../../shared/api/generated/classification-results/types.gen").ListResultsApiClassificationResultsGetData["query"]>} query
 */
export function useClassificationResultListData(query) {
  const [data, setData] = useState(
    /** @type {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultListResponse | null} */ (
      null
    ),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hasNewResults, setHasNewResults] = useState(false);
  const firstResultRef = useRef("");
  const listGenerationRef = useRef(0);
  const listControllerRef = useRef(/** @type {AbortController | null} */ (null));
  const pollGenerationRef = useRef(0);
  const pollControllerRef = useRef(/** @type {AbortController | null} */ (null));

  const load = useCallback(async () => {
    const generation = listGenerationRef.current + 1;
    listGenerationRef.current = generation;
    listControllerRef.current?.abort();
    const controller = new AbortController();
    listControllerRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const value = await api.classificationResults(query, {
        signal: controller.signal,
      });
      if (listGenerationRef.current !== generation) return;
      setData(value);
      firstResultRef.current = value.items?.[0]?.version_id ?? "";
      setHasNewResults(false);
    } catch (loadError) {
      if (
        listGenerationRef.current === generation &&
        (!(loadError instanceof Error) || loadError.name !== "AbortError")
      ) {
        setError(loadError instanceof Error ? loadError.message : "请求失败");
      }
    } finally {
      if (listGenerationRef.current === generation) setLoading(false);
      if (listControllerRef.current === controller) {
        listControllerRef.current = null;
      }
    }
  }, [query]);

  useEffect(() => {
    const generation = listGenerationRef.current + 1;
    listGenerationRef.current = generation;
    listControllerRef.current?.abort();
    const controller = new AbortController();
    listControllerRef.current = controller;
    setLoading(true);
    setError("");
    api
      .classificationResults(query, { signal: controller.signal })
      .then((value) => {
        if (listGenerationRef.current !== generation) return;
        setData(value);
        firstResultRef.current = value.items?.[0]?.version_id ?? "";
        setHasNewResults(false);
      })
      .catch((loadError) => {
        if (
          listGenerationRef.current === generation &&
          (!(loadError instanceof Error) || loadError.name !== "AbortError")
        ) {
          setError(loadError instanceof Error ? loadError.message : "请求失败");
        }
      })
      .finally(() => {
        if (listGenerationRef.current === generation) setLoading(false);
        if (listControllerRef.current === controller) {
          listControllerRef.current = null;
        }
      });
    return () => {
      if (listGenerationRef.current === generation) {
        listGenerationRef.current += 1;
      }
      listControllerRef.current?.abort();
      listControllerRef.current = null;
    };
  }, [query]);

  useEffect(() => {
    const generation = pollGenerationRef.current + 1;
    pollGenerationRef.current = generation;
    const timer = window.setInterval(() => {
      pollControllerRef.current?.abort();
      const controller = new AbortController();
      pollControllerRef.current = controller;
      api
        .classificationResults(query, { signal: controller.signal })
        .then((value) => {
          if (pollGenerationRef.current !== generation) return;
          const firstId = value.items?.[0]?.version_id ?? "";
          if (firstResultRef.current && firstId && firstId !== firstResultRef.current) {
            setHasNewResults(true);
          }
        })
        .catch((pollError) => {
          if (!(pollError instanceof Error) || pollError.name !== "AbortError") return;
        })
        .finally(() => {
          if (pollControllerRef.current === controller) {
            pollControllerRef.current = null;
          }
        });
    }, 15000);
    return () => {
      if (pollGenerationRef.current === generation) {
        pollGenerationRef.current += 1;
      }
      window.clearInterval(timer);
      pollControllerRef.current?.abort();
      pollControllerRef.current = null;
    };
  }, [query]);

  return { data, loading, error, hasNewResults, load };
}
