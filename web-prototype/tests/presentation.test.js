import { describe, expect, it } from "vitest";
import { formatDate, formatTime } from "../src/lib/presentation";

describe("展示格式化", () => {
  it("以统一格式展示本地日期和时间", () => {
    expect(formatDate("2026-08-09T07:05:00")).toBe("2026-08-09");
    expect(formatTime("2026-08-09T07:05:00")).toBe("2026-08-09 07:05");
  });

  it("保留空值和无效值的既有回退行为", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatTime(null)).toBe("—");
    expect(formatDate("无效日期")).toBe("无效日期");
    expect(formatTime("无效日期")).toBe("无效日期");
  });
});
