import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";

/**
 * @param {NonNullable<import("../../shared/api/generated/classification-results/types.gen").ListResultsApiClassificationResultsGetData["query"]>} query
 * @param {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultListResponse | null | undefined} data
 */
export function useNewResultNotice(query, data) {
  const [hasNewResults, setHasNewResults] = useState(false);
  const firstResultRef = useRef("");
  const pollGenerationRef = useRef(0);
  const pollControllerRef = useRef(/** @type {AbortController | null} */ (null));
  const resetNotice = useCallback(() => setHasNewResults(false), []);
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

  return { hasNewResults, resetNotice };
}
