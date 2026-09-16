import { expect, test } from "vitest";

import {
  areaForFile,
  evaluateTypeBudget,
  formatGroup,
  parseTypeScriptDiagnostics,
  summarizeDiagnostics,
} from "../scripts/type-audit.mjs";

const baseline = {
  expectedErrors: 2,
  protectedPaths: [
    "src/shared/api/generated/classification-results",
    "src/shared/api/resultApi.ts",
  ],
};

const diagnostics = [
  {
    code: "TS7006",
    file: "src/features/tasks/TaskList.jsx",
    area: "features/tasks",
  },
  {
    code: "TS2339",
    file: "src/pages/Home.jsx",
    area: "pages",
  },
];

test("只按 TypeScript error 诊断计数并忽略续行", () => {
  const output = [
    "src/features/tasks/TaskList.jsx(10,2): error TS7006: 参数缺少类型。",
    "  这一行只是诊断说明，不应重复计数。",
    "src/pages/Home.jsx(5,1): error TS2339: 属性不存在。",
    "Found 2 errors in 2 files.",
  ].join("\n");

  expect(parseTypeScriptDiagnostics(output)).toEqual(diagnostics);
});

test("按错误代码、文件和业务区域聚合", () => {
  const summary = summarizeDiagnostics([...diagnostics, diagnostics[0]]);

  expect(summary.total).toBe(3);
  expect(summary.byCode[0]).toEqual({ name: "TS7006", count: 2 });
  expect(summary.byFile[0]).toEqual({
    name: "src/features/tasks/TaskList.jsx",
    count: 2,
  });
  expect(summary.byArea[0]).toEqual({ name: "features/tasks", count: 2 });
  expect(areaForFile("src/shared/api/request.js")).toBe("shared/api");
});

test("聚合输出限制条目并显示省略数量", () => {
  const rows = Array.from({ length: 23 }, (_, index) => ({
    name: `file-${index + 1}`,
    count: 23 - index,
  }));

  const output = formatGroup("按文件", rows, 20);

  expect(output).toContain("file-20");
  expect(output).not.toContain("file-21");
  expect(output).toContain("其余 3 项已省略");
});

test("类型错误高于或低于基线都失败", () => {
  const above = evaluateTypeBudget({
    diagnostics: [...diagnostics, diagnostics[0]],
    baseline,
  });
  const below = evaluateTypeBudget({ diagnostics: diagnostics.slice(0, 1), baseline });

  expect(above.ok).toBe(false);
  expect(above.messages.join(" ")).toContain("禁止新增类型债");
  expect(below.ok).toBe(false);
  expect(below.messages.join(" ")).toContain("人工下调为 1");
});

test.each([
  "src/shared/api/resultApi.ts",
  "src/shared/api/generated/classification-results/types.gen.ts",
])("总数命中基线但受保护路径 %s 回归时失败", (file) => {
  const protectedRegression = [
    diagnostics[0],
    { code: "TS2322", file, area: "shared/api" },
  ];
  const result = evaluateTypeBudget({ diagnostics: protectedRegression, baseline });

  expect(result.ok).toBe(false);
  expect(result.messages.join(" ")).toContain("出现 1 条类型错误");
});

test("工具异常且没有诊断时失败", () => {
  const result = evaluateTypeBudget({
    diagnostics: [],
    baseline: { expectedErrors: 0, protectedPaths: [] },
    compilerFailedWithoutDiagnostics: true,
  });

  expect(result.ok).toBe(false);
  expect(result.messages).toContain(
    "TypeScript 工具异常退出，且没有产生可计数的诊断。",
  );
});

test("总数和受保护路径均符合基线时通过", () => {
  expect(evaluateTypeBudget({ diagnostics, baseline })).toEqual({
    ok: true,
    messages: [],
  });
});
