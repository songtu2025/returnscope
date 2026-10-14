import { act, cleanup, renderHook } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useEvidenceNavigation } from "../src/features/classification-results/useEvidenceNavigation";

const mocks = vi.hoisted(() => ({ classificationResultRecordGroups: vi.fn() }));
vi.mock("../src/api", () => ({ api: mocks }));
const groups = [0, 1, 2, 3].map((index) => ({
  record: { id: `r${index}`, source_record_id: `s${index}`, result_version_id: "v1" },
}));
const initialRoute = {
  version: "v1",
  recordPage: 1,
  pageSize: 2,
  tab: "records",
  problem: "FIT",
  productName: "product",
  productSku: "sku",
  orderId: "",
  recordQualityStatus: "review_required",
  commentStatus: "NEGATIVE",
  systemRerunRequired: "true",
};
beforeEach(() => {
  mocks.classificationResultRecordGroups.mockReset();
});
afterEach(cleanup);
function setup(page = 1) {
  const notify = vi.fn();
  const view = renderHook(() => {
    const [route, setRoute] = useState({ ...initialRoute, recordPage: page });
    const [group, setGroup] = useState(null);
    const navigation = useEvidenceNavigation({
      route,
      records: { items: groups.slice((page - 1) * 2, page * 2), total: 4 },
      group,
      setGroup,
      updateRoute: (changes) => setRoute((current) => ({ ...current, ...changes })),
      notify,
    });
    return { route, group, navigation };
  });
  return { ...view, notify };
}
function pages(values, version = "v1") {
  mocks.classificationResultRecordGroups.mockImplementation(async (_, query) => ({
    items: values
      .slice((query.page - 1) * query.page_size, query.page * query.page_size)
      .map((group) => ({
        ...group,
        record: { ...group.record, result_version_id: version },
      })),
    total: values.length,
  }));
}
test("上一条下一条按当前查询跨页衔接，首条不向前请求", async () => {
  pages(groups);
  const { result } = setup();
  act(() => result.current.navigation.open(groups[0]));
  await act(async () => result.current.navigation.move(-1));
  expect(mocks.classificationResultRecordGroups).not.toHaveBeenCalled();
  act(() => result.current.navigation.open(groups[1]));
  await act(async () => result.current.navigation.move(1));
  expect(result.current.group.record.source_record_id).toBe("s2");
  expect(result.current.route.recordPage).toBe(2);
  expect(mocks.classificationResultRecordGroups).toHaveBeenCalledWith(
    "v1",
    expect.objectContaining({
      page: 2,
      page_size: 2,
      problem: "FIT",
      product_name: "product",
      product_sku: "sku",
      quality_status: "review_required",
      comment_status: "NEGATIVE",
      system_rerun_required: "true",
    }),
  );
  await act(async () => result.current.navigation.move(-1));
  expect(result.current.group.record.source_record_id).toBe("s1");
  expect(result.current.route.recordPage).toBe(1);
});
test.each([true, false])("保存后是否移出筛选都不会跳过下一条：%s", async (retained) => {
  const { result } = setup();
  act(() => result.current.navigation.open(groups[1]));
  const next = retained ? groups : groups.filter((group) => group !== groups[1]);
  mocks.classificationResultRecordGroups.mockImplementation(async (_, query) =>
    query.feedback_source_record_id
      ? { items: retained ? [groups[1]] : [], total: retained ? 1 : 0 }
      : {
          items: next.slice((query.page - 1) * 2, query.page * 2).map((group) => ({
            ...group,
            record: { ...group.record, result_version_id: "v2" },
          })),
          total: next.length,
        },
  );
  await act(async () => result.current.navigation.saved("v2", true));
  expect(result.current.group.record.source_record_id).toBe("s2");
  expect(result.current.route.version).toBe("v2");
  expect(result.current.route.recordPage).toBe(retained ? 2 : 1);
});
test("保存成功但读取下一条失败可重试，不能重复提交旧记录", async () => {
  const { result } = setup();
  act(() => result.current.navigation.open(groups[0]));
  mocks.classificationResultRecordGroups.mockRejectedValueOnce(new Error("合成断网"));
  await act(async () => result.current.navigation.saved("v2", true));
  expect(result.current.navigation.error).toContain("修正已保存");
  expect(result.current.navigation.locked).toBe(true);
  expect(result.current.route.version).toBe("v2");
  await act(async () => result.current.navigation.move(1));
  expect(mocks.classificationResultRecordGroups).toHaveBeenCalledTimes(1);
  pages(groups, "v2");
  await act(async () => result.current.navigation.retry());
  expect(result.current.group.record.source_record_id).toBe("s1");
  expect(result.current.navigation.locked).toBe(false);
});
test("最后一条保存后没有下一条时关闭抽屉，保留有效末页", async () => {
  const { result, notify } = setup(2);
  act(() => result.current.navigation.open(groups[3]));
  pages(groups, "v2");
  await act(async () => result.current.navigation.saved("v2", true));
  expect(result.current.group).toBeNull();
  expect(result.current.route.recordPage).toBe(2);
  expect(notify).toHaveBeenCalledWith("当前筛选范围已没有下一条反馈");
});
