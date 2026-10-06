import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

/** 按实际导入顺序读取测试样式，保留原规则断言。
 * @param {string} file
 */
export function readStyles(file) {
  const path = resolve(process.cwd(), file);
  return readFileSync(path, "utf8").replace(/@import\s+"([^"]+)";/g, (_, imported) =>
    readStyles(resolve(dirname(path), imported)),
  );
}
