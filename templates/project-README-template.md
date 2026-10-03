# 项目名称

## 1. 项目用途

填写项目解决的问题和主要用户。

## 2. 适用范围

填写业务范围、用户范围和运行环境。

## 3. 明确不做

- 待填写；没有时填写“无”。

## 4. 规范基线

- 公司规范版本：SEEKWAY Codex V2.0.0。
- 接入来源：待填写仓库地址和版本标签；无 Git 接入时填写版本 ZIP 地址。
- 接入日期：待填写。
- 版本控制：Git / 其他 / 未配置；未配置时填写本次备份方式和无法提交、推送或可靠回滚的限制。
- 加载验证：待填写新建 Codex 任务实际加载的 `AGENTS.md` 路径。
- 项目差异：待填写；没有差异时填写“无”。

已有 `AGENTS.md` 时，按 `docs/codex/workflow.md` 审计并差异合并，不得覆盖。

## 5. 关键业务规则

以下业务规则不得被开发或重构破坏：

1. 待填写。

## 6. 技术栈

列出项目实际使用的前端、后端、数据和部署技术；不适用的类别不要保留。

## 7. 系统架构

填写前端、API、数据库、Worker 和外部系统的关系。

## 8. Web 界面规范

界面核心规则和专项索引维护在 `docs/web-ui-standard.md`，布局、表单和数据规则按任务加载；没有 Web 界面时填写“不适用”。

- 主题入口：`frontend/src/theme/seekway-antd-theme.ts` 和 `frontend/src/styles/seekway-theme.css`，或 `docs/web-ui-standard.md` 声明的现有配置。
- 专项规范：`docs/web-ui-layout-standard.md`、`docs/web-ui-form-standard.md`、`docs/web-ui-data-standard.md`。
- 公司设计参考：[SEEKWAY Web UI Kit V1.2.0](https://www.figma.com/design/eed9GukOv7zM7n04Lu1xUl)。

## 9. 项目结构

填写主要目录及其职责。

## 10. 本地开发

填写 Windows 环境的安装和启动命令。

## 11. 测试与检查

填写实际可执行的命令。Windows 和 Linux/CI 命令可以不同，但必须覆盖相同能力；交付前删除无效占位。

- Windows：`待填写`
- Linux 或 CI：`待填写`

## 12. 配置说明

复制 `.env.example` 创建本地 `.env`。

不得将 `.env` 或真实凭据提交到仓库。

## 13. 部署说明

生产环境由部署负责人统一操作。部署步骤、数据库迁移和回滚方式记录在 `docs/deployment`；没有部署流程时填写“不适用”。
