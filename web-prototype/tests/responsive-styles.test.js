import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

test("business pages use tiered desktop work widths", () => {
  expect(styles).toMatch(/--layout-wide-max:\s*1680px/);
  expect(styles).toMatch(/--layout-workflow-max:\s*1560px/);
  expect(styles).toMatch(/--layout-narrow-max:\s*1180px/);
  expect(styles).toMatch(
    /@media \(min-width:\s*1920px\)\s*{\s*:root\s*{[^}]*--layout-wide-max:\s*2200px;[^}]*--layout-workflow-max:\s*2040px;/s,
  );
  expect(styles).toMatch(
    /@media \(min-width:\s*3200px\)\s*{\s*:root\s*{[^}]*--layout-wide-max:\s*2800px;[^}]*--layout-workflow-max:\s*2480px;/s,
  );
  expect(styles).toMatch(
    /\.standard-page\s*{[^}]*width:\s*100%;[^}]*max-width:\s*var\(--page-max-width\);[^}]*margin-inline:\s*auto;/s,
  );
  expect(styles).toMatch(
    /\.new-task-page\s*{[^}]*--page-max-width:\s*var\(--layout-workflow-max\);[^}]*max-width:\s*var\(--page-max-width\);/s,
  );
  expect(styles).toMatch(
    /\.dashboard-create-page\s*{[^}]*--page-max-width:\s*var\(--layout-workflow-max\);/s,
  );
  expect(styles).toMatch(
    /\.narrow-page\s*{[^}]*--page-max-width:\s*var\(--layout-narrow-max\);/s,
  );
  expect(styles).toMatch(
    /\.page-breadcrumb\s*{[^}]*width:\s*100%;[^}]*max-width:\s*var\(--layout-workflow-max\);/s,
  );
  expect(styles).not.toMatch(/--desktop-(?:form-)?page-max-width/);
  expect(styles).not.toMatch(/width:\s*min\(100%,\s*1029px\)/);
  expect(styles).not.toMatch(/max-width:\s*(1220px|1280px|1480px)/);
});

test("模型服务默认使用摘要布局，高级编辑不保留常驻三栏", () => {
  expect(styles).toMatch(
    /\.model-service-summary\s*{[^}]*grid-template-columns:\s*minmax\(0, 3fr\) minmax\(0, 2fr\);[^}]*gap:\s*var\(--desktop-section-gap\);/s,
  );
  expect(styles).toMatch(
    /\.model-service-editor\s*{[^}]*grid-template-columns:\s*minmax\(0, 1fr\);[^}]*gap:\s*var\(--desktop-section-gap\);/s,
  );
  expect(styles).toMatch(
    /\.model-service-editor\.has-connections\s*{[^}]*grid-template-columns:\s*190px minmax\(0, 1fr\);/s,
  );
  expect(styles).toMatch(
    /\.model-service-editor\.panel-versions > \.config-inspector\s*{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\);[^}]*grid-auto-rows:\s*max-content;/s,
  );
});

test("桌面端共享尺寸以分类结果页为统一基准", () => {
  expect(styles).toMatch(/--desktop-page-padding:\s*24px/);
  expect(styles).toMatch(/--desktop-section-gap:\s*16px/);
  expect(styles).toMatch(/--desktop-control-height:\s*36px/);
  expect(styles).toMatch(/--desktop-table-head-height:\s*40px/);
  expect(styles).toMatch(/--desktop-business-row-height:\s*80px/);
  expect(styles).toMatch(/--desktop-empty-height:\s*208px/);
  expect(styles).toMatch(
    /\.standard-page\s*{[^}]*padding-right:\s*var\(--desktop-page-padding\);[^}]*padding-left:\s*var\(--desktop-page-padding\);/s,
  );
});

test("工作台和创建任务使用冻结的桌面双栏比例", () => {
  expect(styles).toMatch(
    /\.workbench-focus-grid\s*{[^}]*grid-template-columns:\s*minmax\(0, 3fr\) minmax\(0, 2fr\);/s,
  );
  expect(styles).toMatch(
    /\.workbench-grid\s*{[^}]*gap:\s*var\(--desktop-section-gap\);/s,
  );
  expect(styles).toMatch(
    /\.task-create-layout\s*{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) clamp\(320px, 24vw, 380px\);[^}]*gap:\s*var\(--desktop-section-gap\);/s,
  );
  expect(styles).toMatch(
    /\.task-plan-layout\s*{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) clamp\(320px, 24vw, 380px\);/s,
  );
  expect(styles).toMatch(
    /\.task-create-summary\s*{[^}]*width:\s*100%;[^}]*max-width:\s*none;/s,
  );
  expect(styles).toMatch(
    /\.new-task-page \.task-config-choice,[\s\S]*?\.new-task-page \.task-data-quality\s*{[^}]*width:\s*100%;[^}]*max-width:\s*none;/,
  );
  expect(styles).not.toMatch(/\.task-create-summary\s*{[^}]*max-width:\s*295px;/s);
});

test("关键筛选条、表格行和空状态复用共享尺寸", () => {
  expect(styles).toMatch(
    /\.result-pool-filters,[\s\S]*?\.dashboard-list-filters\s*{[^}]*min-height:\s*var\(--desktop-filter-height\);[^}]*padding:\s*10px 12px;/,
  );
  expect(styles).toMatch(
    /\.listing-table-head\s*{[^}]*min-height:\s*var\(--desktop-table-head-height\);/s,
  );
  expect(styles).toMatch(
    /\.listing-row\s*{[^}]*min-height:\s*var\(--desktop-business-row-height\);/s,
  );
  expect(styles).toMatch(
    /\.dashboard-create-empty,[\s\S]*?\.dashboard-unavailable-state\s*{[^}]*min-height:\s*var\(--desktop-empty-height\);/,
  );
});

test("分类结果选择表在目标桌面宽度保留完整操作区", () => {
  expect(styles).toMatch(
    /\.result-pool-table\.is-selecting \.result-pool-head,[\s\S]*?grid-template-columns:\s*92px 96px 132px minmax\(132px, 1\.2fr\) 110px 118px 186px;/,
  );
  expect(styles).toMatch(
    /@media \(max-width:\s*1320px\)[\s\S]*?grid-template-columns:\s*72px 86px 124px minmax\(124px, 1fr\) 100px 186px;/,
  );
  expect(styles).toMatch(
    /@media \(max-width:\s*1120px\)[\s\S]*?grid-template-columns:\s*72px 86px 124px minmax\(124px, 1fr\) 186px;/,
  );
  expect(styles).toMatch(
    /\.classification-results-page \.result-row-actions\s*{[^}]*min-width:\s*0;/s,
  );
  expect(styles).not.toMatch(
    /\.classification-results-page \.result-row-actions\s*{[^}]*min-width:\s*max-content;/s,
  );
});

test("用户与安全和审计记录使用紧凑桌面布局", () => {
  expect(styles).toMatch(
    /\.team-layout\s*{[^}]*display:\s*flex;[^}]*flex-direction:\s*column;[^}]*gap:\s*var\(--desktop-section-gap\);/s,
  );
  expect(styles).not.toMatch(
    /\.team-layout\s*{[^}]*grid-template-columns:[^;}]*620px[^;}]*310px;/s,
  );
  expect(styles).toMatch(
    /\.team-security-bar\s*{[^}]*justify-content:\s*space-between;[^}]*padding:\s*14px 16px;/s,
  );
  expect(styles).toMatch(
    /\.audit-filter-form\s*{[^}]*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\);/s,
  );
  expect(styles).toMatch(
    /\.audit-filter-form \.primary-button\s*{[^}]*grid-row:\s*2;[^}]*grid-column:\s*3;[^}]*min-height:\s*var\(--desktop-control-height\);/s,
  );
  expect(styles).toMatch(
    /\.audit-filter-form label:nth-of-type\(6\)\s*{[^}]*grid-row:\s*2;[^}]*grid-column:\s*3;/s,
  );
  expect(styles).toMatch(
    /\.audit-list article\s*{[^}]*padding:\s*var\(--desktop-card-padding\);/s,
  );
});
