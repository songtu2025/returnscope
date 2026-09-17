# 用户反馈语义分析智能体架构

更新时间：2026-09-12

## 项目定位

本项目定位为用户反馈语义分析智能体，当前支持 Amazon 退货反馈的语义分类、人工复核、分析看板和业务洞察。核心设计是“模型理解语义、程序执行规则、人工处理不确定性”，模型不直接修改分类体系或业务规则；现阶段不扩展数据来源、业务流程或系统能力边界。

## 技术栈

- 前端：React 19、Vite、Recharts
- 后端：Python 3.11、FastAPI、Uvicorn
- 数据处理：pandas、openpyxl、Pydantic
- 数据存储：SQLite、运行时文件目录，可选 MySQL 退货数据源
- 模型服务：Sub2API Responses API
- 部署：Docker Compose、Caddy

## 架构视图

| 视图 | 内容 | Archify 源文件 |
| --- | --- | --- |
| [系统架构](system-architecture.html) | 核心服务、数据库和外部依赖 | [JSON](system-architecture.json) |
| [业务流程](business-workflow.html) | 用户操作流程和核心业务链路 | [JSON](business-workflow.json) |
| [数据流](data-flow.html) | 数据来源、处理、存储和消费 | [JSON](data-flow.json) |
| [部署架构](deployment-architecture.html) | Docker Compose 服务与数据卷关系 | [JSON](deployment-architecture.json) |

## 维护方式

架构发生变化时，修改对应 JSON，再使用 Archify 执行 `validate`、`deliver` 和 `visual-check`。HTML 是交付物，JSON 是唯一维护源。

主要事实来源：`web_backend/app.py`、`web_backend/worker.py`、`return_semantics/`、`web-prototype/src/`、`compose.yaml`、`Dockerfile`、`Caddyfile`。
