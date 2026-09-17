import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptFile = fileURLToPath(import.meta.url);
const frontendRoot = resolve(dirname(scriptFile), "..");
const baselineFile = resolve(frontendRoot, "type-audit-baseline.json");
const typeScriptCli = resolve(
  frontendRoot,
  "node_modules/.bin",
  process.platform === "win32" ? "tsc.cmd" : "tsc",
);

function normalizePath(file) {
  return file.replaceAll("\\", "/").replace(/^\.\//, "");
}

export function areaForFile(file) {
  const normalized = normalizePath(file);
  const parts = normalized.split("/");
  if (parts[0] !== "src") return parts[0] || "global";
  if (parts[1] === "features" && parts[2]) return `features/${parts[2]}`;
  if (parts[1] === "shared" && parts[2]) return `shared/${parts[2]}`;
  return parts[1] || "src";
}

export function parseTypeScriptDiagnostics(output) {
  const diagnostics = [];
  const pattern = /^(?:(.+?)\(\d+,\d+\): )?error (TS\d+):/gm;
  for (const match of output.matchAll(pattern)) {
    const file = match[1] ? normalizePath(match[1].trim()) : "global";
    diagnostics.push({ code: match[2], file, area: areaForFile(file) });
  }
  return diagnostics;
}

function countBy(diagnostics, key) {
  const counts = new Map();
  for (const diagnostic of diagnostics) {
    const value = diagnostic[key];
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort(
      (left, right) => right.count - left.count || left.name.localeCompare(right.name),
    );
}

export function summarizeDiagnostics(diagnostics) {
  return {
    total: diagnostics.length,
    byCode: countBy(diagnostics, "code"),
    byFile: countBy(diagnostics, "file"),
    byArea: countBy(diagnostics, "area"),
  };
}

function isProtectedFile(file, protectedPath) {
  const normalizedFile = normalizePath(file);
  const normalizedPath = normalizePath(protectedPath).replace(/\/$/, "");
  return (
    normalizedFile === normalizedPath || normalizedFile.startsWith(`${normalizedPath}/`)
  );
}

export function evaluateTypeBudget({
  diagnostics,
  baseline,
  compilerFailedWithoutDiagnostics = false,
  missingProtectedPaths = [],
}) {
  const messages = [];
  if (compilerFailedWithoutDiagnostics) {
    messages.push("TypeScript 工具异常退出，且没有产生可计数的诊断。");
  }
  if (missingProtectedPaths.length > 0) {
    messages.push(`受保护路径不存在：${missingProtectedPaths.join("、")}`);
  }

  if (!compilerFailedWithoutDiagnostics) {
    const actualErrors = diagnostics.length;
    if (actualErrors > baseline.expectedErrors) {
      messages.push(
        `类型错误总数 ${actualErrors} 高于基线 ${baseline.expectedErrors}，禁止新增类型债。`,
      );
    } else if (actualErrors < baseline.expectedErrors) {
      messages.push(
        `类型错误总数 ${actualErrors} 低于基线 ${baseline.expectedErrors}；请将 type-audit-baseline.json 的 expectedErrors 人工下调为 ${actualErrors}。`,
      );
    }
  }

  for (const protectedPath of baseline.protectedPaths) {
    const count = diagnostics.filter((diagnostic) =>
      isProtectedFile(diagnostic.file, protectedPath),
    ).length;
    if (count > 0) {
      messages.push(`受保护路径 ${protectedPath} 出现 ${count} 条类型错误。`);
    }
  }

  return { ok: messages.length === 0, messages };
}

function readBaseline() {
  const baseline = JSON.parse(readFileSync(baselineFile, "utf8"));
  if (
    !Number.isInteger(baseline.expectedErrors) ||
    baseline.expectedErrors < 0 ||
    !Array.isArray(baseline.protectedPaths) ||
    baseline.protectedPaths.some(
      (protectedPath) => typeof protectedPath !== "string" || !protectedPath.trim(),
    )
  ) {
    throw new Error("type-audit-baseline.json 格式不合法。");
  }
  return baseline;
}

function runCompiler() {
  const result = spawnSync(
    typeScriptCli,
    ["-p", "jsconfig.quality.json", "--pretty", "false"],
    {
      cwd: frontendRoot,
      encoding: "utf8",
      windowsHide: true,
      shell: process.platform === "win32",
    },
  );
  const output = [result.stdout ?? "", result.stderr ?? ""].filter(Boolean).join("\n");
  const diagnostics = parseTypeScriptDiagnostics(output);
  return {
    diagnostics,
    compilerFailedWithoutDiagnostics:
      Boolean(result.error) ||
      result.signal !== null ||
      (result.status !== 0 && diagnostics.length === 0),
    failureDetail:
      result.error?.message ||
      (result.signal ? `TypeScript 被信号 ${result.signal} 中止。` : output.trim()),
  };
}

export function formatGroup(title, rows, limit = rows.length) {
  const visibleRows = rows.slice(0, limit);
  const lines = [title];
  for (const row of visibleRows) {
    lines.push(`${String(row.count).padStart(5)}  ${row.name}`);
  }
  const omitted = rows.length - visibleRows.length;
  if (omitted > 0) lines.push(`其余 ${omitted} 项已省略`);
  return lines.join("\n");
}

function printGroup(title, rows, limit) {
  console.log(`\n${formatGroup(title, rows, limit)}`);
}

function report(audit) {
  const summary = summarizeDiagnostics(audit.diagnostics);
  console.log(`TypeScript 类型审计：${summary.total} 条诊断`);
  printGroup("按错误代码", summary.byCode);
  printGroup("按文件", summary.byFile, 20);
  printGroup("按区域", summary.byArea, 20);
}

function check(audit, baseline) {
  const missingProtectedPaths = baseline.protectedPaths.filter(
    (protectedPath) => !existsSync(resolve(frontendRoot, protectedPath)),
  );
  const result = evaluateTypeBudget({
    diagnostics: audit.diagnostics,
    baseline,
    compilerFailedWithoutDiagnostics: audit.compilerFailedWithoutDiagnostics,
    missingProtectedPaths,
  });
  if (result.ok) {
    console.log(
      `类型债门禁通过：${audit.diagnostics.length} 条历史错误，受保护路径保持清零。`,
    );
    return true;
  }
  for (const message of result.messages) console.error(message);
  if (audit.compilerFailedWithoutDiagnostics && audit.failureDetail) {
    console.error(audit.failureDetail);
  }
  return false;
}

function main() {
  const command = process.argv[2] ?? "report";
  if (!new Set(["report", "check"]).has(command)) {
    console.error("用法：node scripts/type-audit.mjs <report|check>");
    return 1;
  }

  try {
    const baseline = readBaseline();
    const audit = runCompiler();
    if (command === "report") {
      report(audit);
      if (audit.compilerFailedWithoutDiagnostics) {
        console.error(audit.failureDetail || "TypeScript 工具异常退出。");
        return 1;
      }
      return 0;
    }
    return check(audit, baseline) ? 0 : 1;
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    return 1;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === scriptFile) {
  process.exitCode = main();
}
