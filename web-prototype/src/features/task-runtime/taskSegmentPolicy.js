export function resultPublishStatus(segment) {
  return (
    segment.result_publish_status || (segment.result_version_id ? "published" : "")
  );
}

export function isPublishedResult(segment) {
  return resultPublishStatus(segment) === "published";
}

export function isLegacyResult(segment) {
  return (
    !segment.result_publish_status &&
    !segment.result_version_id &&
    Boolean(segment.result_file_path)
  );
}

export function moveSegmentKey(keys, segmentKey, targetIndex) {
  const currentIndex = keys.indexOf(segmentKey);
  if (currentIndex < 0 || currentIndex === targetIndex) return keys;
  const next = [...keys];
  next.splice(currentIndex, 1);
  next.splice(targetIndex, 0, segmentKey);
  return next;
}
