import { describe, expect, it } from "vitest";
import { formatDate, formatTime } from "../src/lib/presentation";

describe("展示格式化", () => {
  it("无偏移系统时间按 UTC 解析并使用北京时间展示", () => {
    expect(formatDate("2026-08-09T07:05:00")).toBe("2026-08-09");
    expect(formatTime("2026-08-09T07:05:00")).toBe("2026-08-09 15:05");
  });

  it("空值使用统一占位，保留无效源值", () => {
    expect(formatDate(null)).toBe("--");
    expect(formatTime(null)).toBe("--");
    expect(formatDate("无效日期")).toBe("无效日期");
    expect(formatTime("无效日期")).toBe("无效日期");
  });
});

describe("北京时间与业务日期边界", () => {
  it("UTC 与带偏移的时间戳跨日转换一致", () => {
    expect(formatTime("2026-10-11T18:05:00Z")).toBe("2026-10-12 02:05");
    expect(formatTime("2026-10-11T11:05:00-07:00")).toBe("2026-10-12 02:05");
    expect(formatDate("2026-10-11T18:05:00Z")).toBe("2026-10-12");
    expect(formatTime("2026-10-12T00:00:00+08:00")).toBe("2026-10-12 00:00");
  });
  it("业务源纯日期保持原值，不补造时刻", () => {
    expect(formatDate("2026-10-11")).toBe("2026-10-11");
    expect(formatTime("2026-10-11")).toBe("2026-10-11");
  });
  it("日期对象和毫秒时间戳也使用北京时间，零不是空值", () => {
    expect(formatTime(new Date("2026-10-11T18:05:00Z"))).toBe("2026-10-12 02:05");
    expect(formatTime(0)).toBe("1970-01-01 08:00");
  });
});
