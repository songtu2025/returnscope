import { useEffect, useRef, useState } from "react";

/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */
/** @param {TaskSegment[]} segments @param {string} identity */
export function useSegmentSelection(segments, identity) {
  const [keys, setKeys] = useState(/** @type {Set<string>} */ (new Set()));
  const [result, setResult] = useState(
    /** @type {import("./taskSegmentBatchActions").SegmentBatchResult | null} */ (null),
  );
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  useEffect(() => {
    setKeys(new Set());
    setResult(null);
  }, [identity]);
  useEffect(() => {
    const active = new Set(segments.map((segment) => segment.segment_key));
    setKeys((current) => {
      const next = new Set([...current].filter((key) => active.has(key)));
      return next.size === current.size ? current : next;
    });
  }, [segments]);
  /** @param {string[]} changed */
  const toggle = (changed) => {
    if (lock.current) return;
    setKeys((current) => {
      const next = new Set(current);
      const remove = changed.every((key) => current.has(key));
      changed.forEach((key) => (remove ? next.delete(key) : next.add(key)));
      return next;
    });
  };
  /** @param {() => Promise<import("./taskSegmentBatchActions").SegmentBatchResult | false>} submit */
  const apply = async (submit) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    try {
      const next = await submit();
      if (!next) return;
      setResult(next);
      setKeys(
        (current) =>
          new Set([...current].filter((key) => !next.succeeded.includes(key))),
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return {
    keys,
    result,
    busy,
    toggle,
    apply,
    setResult,
    selected: segments.filter((segment) => keys.has(segment.segment_key)),
    clear: () => {
      if (!lock.current) setKeys(new Set());
    },
  };
}
