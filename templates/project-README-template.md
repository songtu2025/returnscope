# 项目名称

## 1. 项目用途

说明本项目解决的业务问题和主要用户。

## 2. 适用范围

说明项目适用的业务范围、用户范围和运行环境。

## 3. 明确不做

- 待填写。
- 待填写。
- 待填写。

## 4. 规范基线

- 公司规范版本：SEEKWAY Codex V1.5.0。
- 接入日期：待填写。
- 项目差异：待填写；没有差异时填写“无”。

项目已有 `AGENTS.md` 时不得使用公司模板覆盖；应先审计现有规则，再以差异合并方式接入公司规范。

## 5. 关键业务规则

以下规则属于项目级业务契约，任何开发和重构不得破坏：

1. 待填写。
2. 待填写。
3. 待填写。

## 6. 技术栈

### 前端

- React
- TypeScript
- Vite

### 后端

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- pytest
- Ruff
- Mypy / Pyright（项目选择并配置一种）

### 部署

- Docker
- Docker Compose
- Nginx
- 阿里云 ECS

## 7. 系统架构

说明前端、API、数据库、Worker 和外部系统之间的关系。

## 8. Web 界面规范

本项目的组件库、图标体系、设计来源、目标视口、页面状态和项目差异只在 `docs/web-ui-standard.md` 中维护，本 README 不重复记录。没有 Web 界面时填写“不适用”。

- 项目运行时主题入口：`frontend/src/styles/seekway-theme.css` 或 `docs/web-ui-standard.md` 中声明的现有主题配置。
- 公司设计参考：[SEEKWAY Web UI Kit V1.2.0](https://www.figma.com/design/eed9GukOv7zM7n04Lu1xUl)。

## 9. 项目结构

说明主要目录及其职责。

## 10. 本地开发

说明 Windows 环境下的依赖安装和启动方式。

## 11. 测试与检查

填写项目实际可执行的命令。Windows 和 Linux/CI 命令可以不同，但必须覆盖相同检查能力；不得保留无效占位后直接交付项目。

Windows：

```powershell
# 待填写，例如项目已有的格式、静态检查、测试和构建命令。
```

Linux 或 CI：

```bash
# 待填写与 Windows 等价的项目命令。
```

## 12. 配置说明

复制 `.env.example` 创建本地 `.env`。

不得将 `.env` 或真实凭据提交到仓库。

## 13. 部署说明

生产环境由部署负责人统一操作。

部署步骤、数据库迁移和回滚方式记录在 `docs/deployment`。
