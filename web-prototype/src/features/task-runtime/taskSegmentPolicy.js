/** @typedef {import("./taskRuntimeContracts").TaskSegment} TaskSegment */

/** @param {TaskSegment} segment */
export function resultPublishStatus(segment) {
  return (
    segment.result_publish_status || (segment.result_version_id ? "published" : "")
  );
}

/**
 * @param {TaskSegment} segment
 * @returns {segment is TaskSegment & {result_version_id: string}}
 */
export function isPublishedResult(segment) {
  return resultPublishStatus(segment) === "published";
}

/** @param {TaskSegment} segment */
export function isLegacyResult(segment) {
  return (
    !segment.result_publish_status &&
    !segment.result_version_id &&
    Boolean(segment.result_file_path)
  );
}

/**
 * @param {string[]} keys
 * @param {string} segmentKey
 * @param {number} targetIndex
 */
export function moveSegmentKey(keys, segmentKey, targetIndex) {
  const currentIndex = keys.indexOf(segmentKey);
  if (currentIndex < 0 || currentIndex === targetIndex) return keys;
  const next = [...keys];
  next.splice(currentIndex, 1);
  next.splice(targetIndex, 0, segmentKey);
  return next;
}
