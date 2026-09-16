import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { createClient } from "@hey-api/openapi-ts";
import { format, resolveConfig } from "prettier";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(scriptDirectory, "..");
const projectRoot = resolve(frontendRoot, "..");
const generatedDirectory = resolve(
  frontendRoot,
  "src/shared/api/generated/classification-results",
);
const generatedFileName = "types.gen.ts";
const generatedFile = join(generatedDirectory, generatedFileName);

function exportOpenApi() {
  const python = process.env.OPENAPI_PYTHON ?? "python";
  const result = spawnSync(python, ["-m", "scripts.export_openapi"], {
    cwd: projectRoot,
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(result.stderr.trim() || "OpenAPI 导出失败");
  }
  return JSON.parse(result.stdout);
}

async function generateTypes() {
  const temporaryDirectory = await mkdtemp(join(tmpdir(), "classification-api-types-"));
  try {
    process.chdir(frontendRoot);
    await createClient({
      input: exportOpenApi(),
      output: {
        path: temporaryDirectory,
        clean: true,
        entryFile: false,
        header: ["// 此文件由 OpenAPI 自动生成，请勿手动修改。"],
      },
      plugins: ["@hey-api/typescript"],
      logs: { level: "silent", file: false },
    });
    const content = await readFile(join(temporaryDirectory, generatedFileName), "utf8");
    const prettierConfig =
      (await resolveConfig(join(frontendRoot, "package.json"))) ?? {};
    return await format(content, {
      ...prettierConfig,
      filepath: generatedFile,
    });
  } finally {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
}

async function checkTypes(expected) {
  let files;
  let current;
  try {
    files = await readdir(generatedDirectory);
    current = await readFile(generatedFile, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") {
      console.error("API 类型尚未生成，请先运行 npm run generate:api-types。");
      return false;
    }
    throw error;
  }
  if (files.length !== 1 || files[0] !== generatedFileName || current !== expected) {
    console.error("API 类型已漂移，请运行 npm run generate:api-types。", files);
    return false;
  }
  console.log("API 类型与 OpenAPI 契约一致。");
  return true;
}

const expected = await generateTypes();
if (process.argv.includes("--check")) {
  if (!(await checkTypes(expected))) process.exitCode = 1;
} else {
  await rm(generatedDirectory, { recursive: true, force: true });
  await mkdir(generatedDirectory, { recursive: true });
  await writeFile(generatedFile, expected, "utf8");
  console.log(
    "已生成分类结果 API 类型：src/shared/api/generated/classification-results/types.gen.ts",
  );
}
