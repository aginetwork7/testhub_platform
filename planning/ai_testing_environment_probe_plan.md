# AI 智能测试：真实页面探测（Environment Probe）实施计划

状态：待实施（2026-09-15 立项，验收 run 32 通过后提出）
范围：仅 `backend/apps/ai_testing/`，不改动其他功能模块的代码；对环境配置只写 `runtime_settings` 数据。

## 1. 背景与问题

验收期间反复出现同一类失败模式：模型知道要点什么，却把意图对到了错误的控件或过早取证。根因都能追溯到页面观测信息不足，而不是用例本身：

| 现象 | 记录 | 根因 | 现状 |
|---|---|---|---|
| 直播页关闭流时点到相邻的下载按钮，消耗 6/8 次重规划 | #680（run 31，TC_005 第 6 步） | 底部工具栏 17 个图标按钮只有 2 个被 tooltip 命名，其他页面能命名 9–13 个 | 通过流启动等待间接缓解，命名问题未解 |
| 首个搜索结果预览缩略图需 2–4 次尝试，耗时 320–793s | #673、#691（TC_002 第 4 步） | 展开控件在不同版本里是 `Toggle collapse` 或 `down`，每次错误尝试付 45s 图片等待 | 通过，但波动大 |
| 新开直播流首次取证必然失败，重规划再点其他摄像头 | #680（TC_005 第 5 步） | stream_state 未等待首帧；canvas 新元素无基线 | 已修复（STREAM_START_WAIT_MS、canvas 首帧基线） |
| UI 结构在数天内变化（出现 `#playerLayout`，关闭控件改名） | run 29–32 之间 | 被测系统持续部署 | 靠重规划吸收，无预警 |

结论：需要一个可重复运行的“页面画像”工具，把观测层的假设（tooltip 延迟、媒体类型、懒加载时长、网络空闲可达性）变成按环境测得的数据，并回灌为运行参数。

## 2. 目标与非目标

目标：
1. 对指定环境的关键页面输出探测报告（JSON + Markdown），指标可比对、可存档。
2. 将建议参数写入 `EnvironmentConfiguration.runtime_settings.ai_testing_browser`，运行时“配置优先、常量兜底”。
3. 两次探测之间输出差异，用于预警 UI 变化。
4. 直接修复已定位的观测缺陷：tooltip 探测脚本支持 `#root` 内渲染的 tooltip 与两阶段悬停等待。

非目标：
- 不把探测发现的具体选择器写入用例或代码（防止“探测变硬编码”）。
- 不替代模型的视觉判断；无名控件仍多的页面，后续另立“控件编号标注（Set-of-Mark）”改造。
- 不在生产环境运行；探测只做只读或可撤销动作。

## 3. 总体设计

### 3.1 组件与文件

| 文件 | 职责 |
|---|---|
| `management/commands/probe_ai_environment.py` | 命令入口：参数解析、登录、逐页探测、报告输出、`--apply` 回灌 |
| `execution/environment_probe.py` | 探测逻辑与指标计算（纯函数为主，便于单元测试）；报告数据结构；差异比较 |
| `execution/environment_probe_js.py` | 探测用 JS 片段（tooltip 采集、img 加载时间、canvas 帧采样、scroll 容器） |
| `runtime/pyui_compat/runner.py` | 常量改为配置优先：`icon_tooltip_hover_ms`、`icon_tooltip_probe_limit`、`image_render_wait_ms`、`stream_start_wait_ms`、`collection_settle_strategy`；`TOOLTIP_PROBE_JS` 增强 |
| `tests/test_environment_probe.py` | 指标计算、报告 diff、参数建议、配置读取的单元测试 |
| `planning/`（本文件） | 计划与验收标准 |

复用而不重写：
- 登录：`_bootstrap_pyuitest_session` + `apps.core.browser_auth.resolve_browser_login`。
- 观测：`_build_actionable_controls`、`_build_observable_elements`、`_rendered_visual_elements`、`capture_accessibility_snapshot`、`build_blocking_state`、`_enrich_icon_control_names`。
- 浏览器启动参数：与 runner 的 `playwright.chromium.launch(**launch_kwargs)` 一致，保证探测与执行环境相同。

### 3.2 命令接口

```
python manage.py probe_ai_environment --env-id 1 \
  --pages /dashboard/streaming,/dashboard/home/search,/dashboard/cases,/dashboard/alerts/basic,/dashboard/playback \
  --hover-delays 200,350,700,1200 \
  --from-record 687 \
  --json /tmp/probe_env1.json --markdown /tmp/probe_env1.md \
  [--apply] [--compare /tmp/probe_env1_prev.json]
```

- `--pages` 缺省时从 `ai_testing_execution_evidence_artifacts` 的 `url_snapshot` 收集近 30 天访问过的路径。
- `--from-record <id>` 回放该已通过记录的动作序列（按步骤持久化的 action），到达“已打开一路流 / 已打开弹窗”等状态后再探测；回放只使用记录中状态为 completed 的动作。
- `--apply` 仅写第 4 节列出的参数键；写前打印 diff，要求确认（或 `--yes`）。
- 报告头部记录：环境 id、base_url、探测时间、前端构建标识（`<script src>` 的 hash 或 build id）、浏览器版本。

## 4. 探测项、指标与回灌

| # | 探测项 | 方法 | 指标 | 回灌 |
|---|---|---|---|---|
| P1 | 控件命名覆盖 | 采集可操作控件，统计无名控件与其容器分组 | 无名率；无名图标按钮组（≥3）的数量与大小；命名来源分布（text/aria/title/tooltip） | 校验 `icon_tooltip_probe_limit`；无名组作为编号标注的输入 |
| P2 | tooltip 机制与延迟 | 每个无名图标按钮按 200/350/700/1200ms 悬停；采集新增文本节点（含 `#root` 内）、`role=tooltip`、`aria-describedby`、`data-state`、`title` | 各延迟下命名覆盖率；tooltip 渲染位置分类 | `icon_tooltip_hover_ms`；探测脚本增加 `#root` 内选择器与两阶段等待 |
| P3 | 阻塞层与弹层 | 打开历史记录中点击过的弹窗再关闭 | 阻塞层识别正确率；关闭控件可访问名称；遮罩是否拦截 | 校正 `build_blocking_state` 选择器集合 |
| P4 | 媒体与直播流 | 开流后每 500ms 采样 video 的 readyState/currentTime；canvas 首帧时间与帧变化间隔 | 首帧时间分布；原生进度是否推进；播放器类型 | `stream_start_wait_ms`；确认 canvas 路径 |
| P5 | 图片懒加载 | 打开列表后记录每个 img 变为已加载的时间 | 缩略图加载时间分布；>45s 比例 | `image_render_wait_ms` |
| P6 | 滚动容器与虚拟列表 | 采集 scroll_containers；滚动后统计条目变化 | 是否虚拟化；每次滚动新增条目数 | 校准重复滚动规则的剩余量判断 |
| P7 | 网络空闲 | 测 networkidle 在 10s 内是否可达 | 长连接/轮询是否阻止空闲 | `collection_settle_strategy`（networkidle / dom_stable） |
| P8 | 稳定锚点 | 统计 id、data-testid、aria-label 存在率；结构选择器深度 | 锚点覆盖率；平均深度 | 评估 group_selector 与计划缓存稳定性 |
| P9 | 页面就绪 | 登录到可交互、路由切换到渲染完成的时间 | 就绪时间分布 | 步骤开头等待校准 |
| P10 | 变更检测 | 与上次报告比较控件名集合、锚点集合、无名组 | 新增/消失/改名清单 | 预警（如 `Toggle collapse` → `down`） |

新增配置键（`runtime_settings.ai_testing_browser`）：

| 键 | 类型 | 兜底常量 | 说明 |
|---|---|---|---|
| `icon_tooltip_hover_ms` | int | `ICON_TOOLTIP_HOVER_MS`=350 | 图标悬停等待 |
| `icon_tooltip_probe_limit` | int | `ICON_TOOLTIP_PROBE_LIMIT`=20 | 每次观测最多探测的图标数 |
| `image_render_wait_ms` | int | `IMAGE_RENDER_WAIT_MS`=45000 | 图片渲染等待上限 |
| `stream_start_wait_ms` | int | `STREAM_START_WAIT_MS`=20000 | 直播流首帧等待上限 |
| `collection_settle_strategy` | str | `networkidle` | 集合断言取证前的稳定判定方式 |

## 5. 报告格式

JSON 顶层：`environment`、`build_fingerprint`、`probed_at`、`pages[]`、`suggestions{}`、`diff{}`。每页：`path`、`ready_ms`、`controls{total, unnamed, unnamed_groups[]}`、`tooltip{coverage_by_delay{}, render_location}`、`blocking{}`、`media{}`、`images{}`、`scroll{}`、`network_idle{}`、`anchors{}`、`issues[]`。

Markdown 摘要每页一段：三行指标、问题列表、建议参数；末尾给出 `--apply` 将写入的 diff。

## 6. 实施阶段与验收标准

阶段 1（约 1 天）
- 命令骨架、登录复用、P1、P2、报告输出（JSON + Markdown）。
- 先跑五个页面：`/dashboard/streaming`、`/dashboard/home/search`、`/dashboard/cases`、`/dashboard/alerts/basic`、`/dashboard/playback`。
- 完成 `TOOLTIP_PROBE_JS` 增强与两阶段悬停；单元测试覆盖指标计算。
- 验收：直播页图标命名覆盖从 2/17 提升到 ≥ 12/17（以探测报告为据）。

阶段 2（约 1 天）
- P3–P9；`--from-record` 状态回放。
- 验收：报告能给出 `stream_start_wait_ms`、`image_render_wait_ms` 的数据依据（分布图或分位数）。

阶段 3（约半天）
- `--apply` 回灌、运行时配置优先读取、P10 差异比较。
- 把探测加入验收前置流程：每次全量验收前运行一次并存档报告。
- 验收：回灌后 TC_005 与 TC_002 各跑 3 次，TC_005 关闭流一次通过；TC_002 第 4 步重规划 ≤ 1 次；总耗时较 run 32 下降。

## 7. 风险与边界

- 探测结果随 UI 版本过期：报告带前端构建标识，标识不一致的旧报告不得回灌。
- 悬停会移动鼠标并关闭悬停菜单：探测前确认无打开的悬停态，探测后把鼠标移回角落。
- 探测会与被测系统交互（开流、开弹窗）：只用可撤销动作，结束时恢复初始状态；不在生产环境运行。
- 环境配置表属于 core 模块：命令只写其 `runtime_settings` 数据，不改其代码。
- 探测不能替代视觉判断：命名覆盖仍低的页面，转入“控件编号标注”改造。

## 8. 待决问题

- 回灌是否需要审批流（`--apply` 直接写 vs 生成待确认的建议文件）。
- 探测报告的存档位置（当前建议 `media/ai_testing/probes/<env>/<date>/`）。
- 是否把 P10 差异检测接入每日回归，UI 变化时自动通知。
