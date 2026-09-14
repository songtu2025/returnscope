export function formatBytes(value) {
  let size = Number(value || 0);
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  const digits = unitIndex === 0 || size >= 10 ? 0 : 1;
  return `${size.toFixed(digits)} ${units[unitIndex]}`;
}

export function canonicalSources(items) {
  const sources = new Map();
  items.forEach((item) => {
    const key = item.source_key || item.id;
    const source = sources.get(key);
    if (source) {
      source.member_ids.push(item.id);
    } else {
      sources.set(key, { ...item, member_ids: [item.id] });
    }
  });
  return [...sources.values()];
}

export function mergeSourceDetails(source, items) {
  const current = items.find((item) => item.id === source.id) || items[0];
  const versions = items
    .flatMap((item) => item.versions ?? [])
    .sort((left, right) => String(right.created_at).localeCompare(left.created_at));
  const notesByVersion = new Map(
    versions.map((item) => [item.id, item.change_note || ""]),
  );
  return {
    ...current,
    member_ids: source.member_ids,
    source_name: sourceDisplayName(source),
    task_reference_count: items.reduce(
      (total, item) => total + Number(item.task_reference_count || 0),
      0,
    ),
    versions,
    imports: items
      .flatMap((item) => item.imports ?? [])
      .map((item) => ({
        ...item,
        change_note:
          item.change_note || notesByVersion.get(item.resulting_version_id) || "",
      }))
      .sort((left, right) => String(right.created_at).localeCompare(left.created_at)),
  };
}

export function sourceDisplayName(item) {
  if (item.name) return item.name;
  if (item.source_name) return item.source_name;
  const stores = item.quality?.stores ?? [];
  const brands = [
    ...new Set(
      stores.map((value) => String(value).split(":")[0].trim()).filter(Boolean),
    ),
  ];
  if (brands.length === 1) return `${brands[0]} 退货数据`;
  return "未命名退货数据";
}

export function sourceScopeLabel(item) {
  const stores = item.quality?.stores ?? [];
  if (!stores.length) return "未识别";
  return [...new Set(stores.map((value) => String(value)))].join(" · ");
}

export function dataStatus(item) {
  const quality = item.quality ?? {};
  const missingStoreRows = Number(quality.missing_store_rows || 0);
  const readyRate = Number(quality.matching_key_ready_rate ?? 100);
  if (missingStoreRows > 0) {
    return {
      value: "attention",
      label: "需关注",
      description: `${missingStoreRows.toLocaleString()} 行缺少店铺/站点`,
    };
  }
  if (readyRate < 100) {
    return {
      value: "attention",
      label: "需关注",
      description: `匹配键完整度 ${readyRate.toLocaleString()}%`,
    };
  }
  return {
    value: "available",
    label: "当前可用",
    description: "数据质量就绪",
  };
}

export function importModeLabel(mode) {
  return (
    {
      analyze_only: "仅分析本批",
      create: "首次建立数据源",
      append: "追加数据",
      replace: "替换当前数据",
    }[mode] ?? mode
  );
}
