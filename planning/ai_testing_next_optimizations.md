# AI 智能测试：下一步优化方向

状态：待实施（2026-09-16 立项）
范围：仅 `backend/apps/ai_testing/`；不改动其他功能模块的代码。
依据：2026-09-15 完成的缓存重构（run 40 稳态 21/21）与随后的一次冷启动单轮运行（清空执行记录后 5/7）。

## 1. 冷启动单轮运行暴露的问题

| 现象 | 记录 | 根因 | 归类 |
|---|---|---|---|
| TC_002 计划生成失败，浏览器一步未执行 | 冷启动 #2 | 文本模型连续 5 次生成的计划中，“选择 Magic Search V2 下拉选项”一步没有验证所选值的断言，`_validate_dropdown_selection_assertion` 每次拒绝，最终 “Planner 未生成有效计划” | 计划契约合规 |
| TC_007 第 7 步（点击 Confirm 提交 Investigate）失败 | 冷启动 #7 | 新计划把验证方式改成“确认对话框消失”（popup 断言），历史已验证计划用的是“状态显示 Investigate”（field_value）。点击后被绑定的对话框元素仍可见，模型随后只返回裸 assert，重试耗尽 | 计划验证策略漂移 |
| 全部 7 个用例耗时明显变长（TC_003 110s→495s，TC_006 260s→648s） | 冷启动 #1–#7 | 清空执行记录连带删除了全部计划版本，全局计划缓存为空；新计划措辞变化又使步骤动作缓存的键全部失配（命中 0） | 计划与报告耦合 |

结论：稳态 21/21 建立在“已验证计划 + 已填充缓存”之上；冷启动下两个失败都在计划层，不在运行时绑定器。

## 2. 优化方向（按优先级）

### P1 已验证计划与执行记录解耦

- 问题：`_load_cached_plan_steps` 从 `AIExecutionPlanRevision`（挂在执行记录下）读取计划，清空报告即清空计划缓存。
- 方案：新增按用例保存的“已验证计划”表（如 `AIVerifiedPlan`：ai_case、environment、source_goal、context_fingerprint、plan、plan_hash、verified_count、last_passed_record_id、created/updated）。执行通过时写入或累加；`create_plan` 优先读该表，其次才回退到计划版本表。清空报告不触碰该表。
- 附带：`manage_action_cache` 同款的管理命令（列出/清除某用例的已验证计划），以及导出/导入 JSON 便于环境迁移。
- 验收：清空全部执行记录后再跑 3 轮，`plan_source` 应为 `verified`，通过率与稳态一致。

### P2 规划契约被拒时的示例注入

- 问题：契约校验拒绝后只把错误文本追加进 `retry_messages`，模型 5 次都没改对。
- 方案：按拒绝类型附带最小合规示例。例如下拉选择步骤被拒时，追加一段 JSON 示例：`{"description": "Select X from the Y dropdown", "assertions": [{"assert_kind": "field_value", "operator": "starts_with", "expected": {"value": "X"}, "target": {"intent": "Y dropdown committed selected value"}}]}`；对“缺少 transition”“集合断言绑到容器”等已有校验各配一个示例。
- 验收：对历史被拒计划回放（离线单元测试），第 2 次尝试即通过校验；冷启动 TC_002 计划生成成功。

### P3 提交类步骤的验证策略引导

- 问题：同一步骤在不同计划里可能选“对话框消失”或“状态值显示”两种验证，前者对可关闭但仍挂在 DOM 中的弹层不稳定。
- 方案：规划提示词与校验中，对“Confirm/Submit/Save 提交”类步骤优先要求 `field_value`/`element_state` 文本断言验证提交后的可见结果，`popup not_exists` 只作为附加断言；运行时已支持“对话框关闭后接受已显示的提交值”。
- 验收：TC_007 冷启动计划的第 7 步应生成值断言。

### P4 用例计划质量（需与用例作者确认）

- TC_004 第 13/14 步：`Click the Deactivate button` 的断言只检查搜索框存在，不能证明停用；建议描述中明确“并验证用户状态显示为 Deactivated”。
- TC_006 第 1 步：`camera list result items after filtering` 集合断言在未过滤时也能通过；建议描述中要求“结果只包含 萧山区 分组”。
- TC_002 第 4 步：“首个搜索结果的预览缩略图”在地图标记与左侧列表之间有歧义，是耗时 320–620s 波动的来源；建议描述指明是地图标记还是列表项。

### P5 运行时细项

- 目标卡片未出现时的渲染等待改为两阶段预算：卡片出现最多等 10s，卡片内缩略图渲染最多等 45s（当前一律 45s）。
- 直播页工具栏图标 tooltip 命名覆盖低（2/17），已在 `ai_testing_environment_probe_plan.md` 中立项。
- 启用第二个 planner_vision 模型以激活已实现的故障切换（需在 AI 模型配置中启用，无需改代码）。
- qcluster worker 需重启才能加载新代码；`backend/docs/` 被 gitignore，运行说明文档只在本地。

## 3. 实施顺序建议

1. P1（约 1 天）→ 2. P2（约半天，含离线回放测试）→ 3. P3（约半天）→ 4. P4 与用例作者对齐后修改描述 → 5. P5 视情况。
每一步完成后用 `run_ai_acceptance --rounds 3` 验证，并另做一次“清空执行记录后的冷启动单轮”对照。
