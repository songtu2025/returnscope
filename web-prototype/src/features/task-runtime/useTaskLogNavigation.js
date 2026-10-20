import { useState } from "react";

/** @param {import("react").Dispatch<import("react").SetStateAction<string>>} setActiveTab */
export function useTaskLogNavigation(setActiveTab) {
  const [listing, setListing] = useState(
    /** @type {import("./TaskEventList").LogListingTarget | null} */ (null),
  );
  /** @param {import("./taskRuntimeContracts").TaskSegment} segment */
  const open = (segment) => {
    setListing({
      key: segment.segment_key || segment.id,
      label: segment.scope?.listing || segment.segment_key,
      store: segment.scope?.store,
    });
    setActiveTab("events");
    requestAnimationFrame(() => {
      const panel = document.getElementById("task-view-panel");
      panel?.scrollIntoView({ block: "start" });
      panel?.focus({ preventScroll: true });
    });
  };
  return { listing, open };
}
