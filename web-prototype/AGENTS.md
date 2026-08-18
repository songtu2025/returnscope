# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## 当前产品约束

- 这是退货语义分析智能体的桌面 Web 原型，视觉方向采用绿色、克制、信息密集的“运行驾驶舱”。
- 系统支持多个同权限用户，不设计管理员、审核员等角色体系。
- 同时使用人数预计不超过 5 人；每个用户最多同时运行 3 个任务，其他用户的任务可查看和修改。
- 所有人工修改必须展示操作者、修改时间、原值、新值和修改原因，并用版本校验避免覆盖他人的更新。
- API 与模型配置为共享配置，所有用户都能修改；运行中的任务继续使用启动时的配置快照。
- 后续视觉与交互打磨参考行业顶级生产力工具：快捷操作要接近 Linear，运行诊断和恢复要接近 GitHub Actions/Vercel，共享 API 配置要具备 Stripe Workbench 式的验证与留痕意识。
- 保持绿色运行驾驶舱方向，优先提升任务识别、恢复能力、复核效率和长期阅读舒适度，不做无关的视觉重构。
- 仅设计桌面端；以有效 CSS 视口而不是设备英寸判断适配，最低支持 1024px 宽，并覆盖 1024×640、1280×720、1440×900、1920×1080 以及 125%/150% 缩放检查。
- 交付以本地可运行原型和代码为准，不依赖 Figma。

## 产品信息模块边界

- 顶层“产品信息”只负责维护跨任务复用的标准产品信息及其版本、修改留痕和任务引用。
- 退货明细是单次分析任务的输入，只能在“分析任务”创建流程中导入或选择。
- 商品匹配、异常处理和排除确认属于分析任务预检，不设置独立的全局匹配板块。
