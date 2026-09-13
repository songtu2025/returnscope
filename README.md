# 退货语义分析智能体

本项目把 Amazon 退货数据转换为可追溯的语义分类、人工复核、分析看板和业务洞察。核心原则是：模型理解语义，程序执行确定性规则，人工处理不确定结果。

## 系统边界

- 普通用户共享分析任务和人工复核结果。
- 模型服务维护和存储清理仅允许管理员执行；权限以后端校验为准。
- 前端是简体中文桌面 Web 驾驶舱，最低支持 `1024px` 宽，不承担移动端交付。
- 默认使用 SQLite 保存应用状态，可选 MySQL 作为退货数据源。

## 架构与目录

| 路径 | 作用 |
| --- | --- |
| `return_semantics/` | 退货语义分类、标签体系和模型调用 |
| `return_analysis/` | 分类结果分析 |
| `web_backend/` | FastAPI API、任务、复核、权限和 SQLite 持久化 |
| `web-prototype/` | React 19、JavaScript/JSX、Vite、自定义 CSS、Phosphor Icons 和 Recharts 前端 |
| `config/` | 分类和模型相关配置 |
| `tests/` | 后端与语义处理自动化测试 |
| `docs/architecture/README.md` | 系统、业务、数据流和部署架构入口 |
| `compose.yaml`、`Dockerfile`、`Caddyfile` | Docker Compose 与 Caddy 生产部署入口 |

## 环境要求

- Python 3.11
- Node.js 22 与 npm
- 生产部署另需 Docker Engine 和 Docker Compose

## Windows 本地开发

在 PowerShell 中安装依赖：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Set-Location web-prototype
npm ci
Set-Location ..
```

启动后端：

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn web_backend.app:app --host 127.0.0.1 --port 8000 --reload
```

另开一个 PowerShell 窗口启动前端：

```powershell
Set-Location web-prototype
npm run dev
```

Vite 会在终端显示访问地址，并将 `/api` 请求代理到 `http://127.0.0.1:8000`。本地开发默认管理员为 `admin@example.com`，密码为 `change-me-now`；该默认值不能用于生产环境。MySQL 数据源需要时，将 `.env.mysql.example` 复制为 `.env.mysql` 并填写连接信息。

## Linux 与 CI

安装依赖：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cd web-prototype
npm ci
cd ..
```

本地启动使用两个终端：

```bash
source .venv/bin/activate
python -m uvicorn web_backend.app:app --host 127.0.0.1 --port 8000 --reload
```

```bash
cd web-prototype
npm run dev
```

## 质量检查

Windows PowerShell、Linux 和 CI 使用相同入口：

```bash
python scripts/quality.py check
```

`check` 是阻断检查，覆盖 Ruff、敏感信息扫描（当前待提交文件与 Git 全历史对象）、pytest、Python 死代码检查，以及前端格式、ESLint、重复代码、死代码、循环依赖、测试和生产构建。

```bash
python scripts/quality.py audit
```

`audit` 用于盘点现有 Python 类型、圈复杂度、分支数、参数数量、语句数、前端类型与未使用导出等历史债务。当前审计仍有未清理项，命令可能以非零状态退出；CI 将其作为非阻断审计运行，不得将其报告为已通过。

## 生产部署

Docker Compose 构建前端并由 FastAPI 提供静态资源和 API，Caddy 负责 HTTPS、反向代理和安全响应头。先基于 `.env.example` 创建 Compose 自动读取的 `.env`，设置有效的 `APP_DOMAIN`、初始管理员信息、至少 14 位密码和 `WEBAPP_ENCRYPTION_KEY`，再执行：

```bash
docker compose up -d --build
docker compose ps
```

运行数据保存在 Compose 的 `app_data` 卷，`backup` 服务每天写入 `backup_data` 卷。生产迁移入口是 `compose.yaml` 中的 `migration` profile，迁移前必须停止应用并按部署负责人确认的源目录执行。

## SEEKWAY 规范基线

- 版本：V1.8.1
- 来源提交：`181397ca1510db153f77695e820dcf1907062bb4`
- 接入日期：2026-09-09

本项目保留既有差异：前端继续使用 JavaScript/JSX、自定义 CSS、Phosphor Icons 和 Recharts；持久化继续使用 SQLite 与自定义迁移；部署继续使用 Docker Compose 和 Caddy。不迁移 Ant Design、TypeScript、SQLAlchemy、Alembic 或 Nginx。
