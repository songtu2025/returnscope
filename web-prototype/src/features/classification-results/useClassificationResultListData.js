import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";

import { api } from "../../api";
import { serverStateKeys } from "../../shared/serverState";

/**
 * @param {NonNullable<import("../../shared/api/generated/classification-results/types.gen").ListResultsApiClassificationResultsGetData["query"]>} query
 */
export function useClassificationResultListData(query) {
  const [hasNewResults, setHasNewResults] = useState(false);
  const firstResultRef = useRef("");
  const listControllerRef = useRef(/** @type {AbortController | null} */ (null));
  const pollGenerationRef = useRef(0);
  const pollControllerRef = useRef(/** @type {AbortController | null} */ (null));

  const fetchResults = useCallback(async () => {
    listControllerRef.current?.abort();
    const controller = new AbortController();
    listControllerRef.current = controller;
    try {
      return await api.classificationResults(query, {
        signal: controller.signal,
      });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return undefined;
      throw error;
    } finally {
      if (listControllerRef.current === controller) {
        listControllerRef.current = null;
      }
    }
  }, [query]);
  const {
    data = null,
    error: loadError,
    isLoading,
    isValidating,
    mutate,
  } = useSWR(serverStateKeys.classificationResultList(query), fetchResults, {
    keepPreviousData: true,
  });

  const load = useCallback(async () => {
    setHasNewResults(false);
    await mutate();
  }, [mutate]);

  useEffect(() => {
    firstResultRef.current = data?.items?.[0]?.version_id ?? "";
    setHasNewResults(false);
  }, [data, query]);

  useEffect(() => {
    const generation = pollGenerationRef.current + 1;
    pollGenerationRef.current = generation;
    const timer = window.setInterval(() => {
      if (document.hidden) return;
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

  return {
    data,
    loading: isLoading || isValidating,
    error: loadError
      ? loadError instanceof Error
        ? loadError.message
        : "请求失败"
      : "",
    hasNewResults,
    load,
  };
}
