# Codex Python、FastAPI 与 SQLite 规范

涉及 Python、FastAPI、后端接口、SQLite、数据库或迁移时，必须读取本文件。

## 1. Python

生成或修改的 Python 代码必须：

1. 遵循 PEP 8，并使用 Ruff 格式化和检查。
2. 使用清晰的英文变量名、函数名、类名和文件名，不得使用拼音或无意义缩写。
3. 普通注释和 docstring 使用中文。
4. 公共函数和复杂业务逻辑必须有类型注解。
5. 使用项目选定的 Mypy 或 Pyright 进行类型检查。
6. 不得使用裸 `except`、吞掉异常或通过关闭 Ruff、类型检查规则掩盖问题。

## 2. FastAPI 分层

本项目后端基本依赖方向：

```text
API Router → Service → Database
```

职责约定：

- `web_backend/routers`：接收请求、校验参数、执行后端权限检查、调用服务并返回结果。
- `web_backend/api_schemas.py`：定义请求和响应结构。
- `web_backend/*_service.py`：处理业务规则、业务流程和内聚的数据访问。
- `web_backend/database.py`：管理 SQLite 连接、事务、基础结构和应用迁移记录。
- `web_backend/settings.py`、`security.py` 等模块：管理配置和安全能力。

FastAPI 路由只处理接口职责，不得堆积业务逻辑或大量数据库查询。只有在重复数据访问已经妨碍测试和维护时才提取 Repository，不得为套用分层模板创建空壳转发层。

## 3. 数据库与迁移

涉及数据库时必须：

1. 保持现有 `sqlite3`、`app_migrations` 表和 `web_backend/database.py` 中的自定义迁移机制，不自动引入 SQLAlchemy 或 Alembic。
2. 每次结构变更必须有稳定迁移标识和校验信息，事务内执行，并提供升级、备份和可验证的回滚方案。
3. 明确受影响的表、字段、索引、数据量及兼容范围，保持 Schema、业务代码和迁移逻辑一致。
4. 迁移和生产数据搬运必须分别覆盖测试；涉及现有生产数据路径时复用 `web_backend/production_migration.py` 的受控流程。
5. 批量操作必须说明影响范围和回滚方式。

不得：

1. 直接修改生产数据库或手工修改生产表结构。
2. 擅自删除表、字段、索引或业务数据。
3. 擅自增加需求中没有的业务字段。
4. 未经确认增加系统字段、派生字段或管理字段。
5. 使用浮点数存储或计算金额。
6. 绕过 `app_migrations` 直接修改已部署数据库结构。
7. 自动执行生产数据库迁移。

生产数据库迁移只能由部署负责人执行。
