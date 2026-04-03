# TestHub AI 自动化端到端测试 —— 架构、配置与使用指南

## 目录

- [一、项目概览](#一项目概览)
- [二、部署安装](#二部署安装)
- [三、AI 能力架构总览](#三ai-能力架构总览)
- [四、AI 浏览器自动化（端到端测试）](#四ai-浏览器自动化端到端测试)
- [五、AI 需求分析与测试用例生成](#五ai-需求分析与测试用例生成)
- [六、AI 助手（Dify 集成）](#六ai-助手dify-集成)
- [七、LLM 接入配置详解](#七llm-接入配置详解)
- [八、启动与使用流程](#八启动与使用流程)
- [九、关键源码文件索引](#九关键源码文件索引)

---

## 一、项目概览

TestHub 是一个 AI 驱动的测试管理平台，技术栈为 **Django 4.2（后端）+ Vue 3（前端）**。平台提供三大 AI 能力：

| AI 能力 | 说明 | 核心库 |
|---------|------|--------|
| **AI 浏览器自动化** | 用自然语言描述测试任务，AI 自动操控浏览器执行端到端测试 | `browser-use` + `langchain-openai` |
| **AI 需求分析** | 上传需求文档，AI 解析并自动生成测试用例，支持 AI 评审和改进 | `httpx`（OpenAI 兼容 API） |
| **AI 助手** | 接入 Dify 聊天机器人，提供测试相关的 AI 问答 | Dify API |

---

## 二、部署安装

### 2.1 环境要求

| 组件 | 版本要求 |
|------|---------|
| Python | 3.12+ |
| Node.js | 22.12+（Vite 7 要求） |
| MySQL | 8.0+（utf8mb4） |
| Redis | 7+（Celery broker + Channels） |
| Docker | 可选，用于运行 MySQL/Redis |

### 2.2 使用 Docker 部署 MySQL 和 Redis

```bash
# 拉取 MySQL 镜像（国内镜像源）
docker pull docker.1ms.run/library/mysql:8.0

# 启动 MySQL 容器
docker run -d \
  --name testhub-mysql \
  -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=testhub123 \
  -e MYSQL_DATABASE=testhub \
  docker.1ms.run/library/mysql:8.0 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci

# 拉取并启动 Redis 容器
docker pull docker.1ms.run/library/redis:7-alpine
docker run -d --name testhub-redis -p 6379:6379 redis:7-alpine
```

### 2.3 后端部署

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\Activate.ps1  # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 创建 .env 配置文件（见下方模板）

# 4. 数据库迁移（首次需要先生成迁移文件）
python manage.py makemigrations
python manage.py migrate

# 5. 创建超级用户
python manage.py createsuperuser
# 或使用命令行：
echo "from apps.users.models import User; User.objects.create_superuser('admin', 'admin@testhub.com', 'admin123')" | python manage.py shell

# 6. 启动后端服务
python manage.py runserver 0.0.0.0:8000
```

### 2.4 前端部署

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
# 默认运行在 http://localhost:3000
```

### 2.5 `.env` 配置文件模板

在项目根目录创建 `.env` 文件：

```env
# Django
SECRET_KEY=django-insecure-your-secret-key-here
DEBUG=True

# Database（对应 Docker MySQL 容器）
DB_NAME=testhub
DB_USER=root
DB_PASSWORD=testhub123
DB_HOST=127.0.0.1
DB_PORT=3306

# Redis（对应 Docker Redis 容器，无密码时不带 :password@）
REDIS_URL=redis://127.0.0.1:6379/0

# CORS（前端地址）
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# 语言
LANGUAGE_CODE=zh-hans
TIME_ZONE=Asia/Shanghai

# --- AI 浏览器自动化备用配置（优先从数据库读取） ---
# AUTH_TOKEN=your-llm-api-key
# BASE_URL=https://api.openai.com/v1
# MODEL_NAME=gpt-4o
```

---

## 三、AI 能力架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                      Vue 3 前端                               │
│  ┌──────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│  │ AI 测试  │  │ 需求分析/用例生成 │  │   AI 助手对话    │    │
│  └────┬─────┘  └───────┬──────────┘  └───────┬──────────┘    │
│       │                │                      │               │
└───────┼────────────────┼──────────────────────┼──────────────┘
        │ REST API       │ REST API + SSE       │ REST API
┌───────┼────────────────┼──────────────────────┼──────────────┐
│       ▼                ▼                      ▼              │
│  ┌──────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│  │AICaseView│  │TestCaseGeneration│  │  ChatViewSet     │    │
│  │ Set /    │  │  TaskViewSet     │  │  (Dify代理)      │    │
│  │AIExecRec │  └───────┬──────────┘  └───────┬──────────┘    │
│  │ ViewSet  │          │                      │              │
│  └────┬─────┘          │                      │              │
│       │                │                      │              │
│       ▼                ▼                      ▼              │
│  ┌──────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│  │ai_agent  │  │ AIModelService   │  │  DifyConfig      │    │
│  │ .py      │  │ (httpx调LLM API) │  │  POST chat-msgs  │    │
│  └────┬─────┘  └───────┬──────────┘  └───────┬──────────┘    │
│       │                │                      │              │
│       ▼                │                      │              │
│  ┌──────────┐          │                      │              │
│  │ai_base   │          │                      │              │
│  │ .py      │          │                      │              │
│  │(Browser  │          │                      │              │
│  │ Agent)   │          │                      │              │
│  └────┬─────┘          │                      │              │
│       │                │                      │              │
│       ▼                ▼                      ▼              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │             AIModelConfig（数据库统一 LLM 配置）       │    │
│  │  model_type | role | api_key | base_url | model_name │    │
│  └──────────────────────────────────────────────────────┘    │
│                     Django 后端                               │
└──────────────────────────────────────────────────────────────┘
        │                │                      │
        ▼                ▼                      ▼
   browser-use      OpenAI 兼容 API         Dify Server
   (Playwright       (DeepSeek/Qwen/        (外部服务)
    浏览器控制)       SiliconFlow/...)
```

### 核心数据模型

```
AIModelConfig (requirement_analysis)     ← 统一 LLM 配置中心
├── role='writer'                        → 测试用例编写
├── role='reviewer'                      → 测试用例评审
└── role='browser_use_text'              → AI 浏览器自动化

AICase (ui_automation)                   ← AI 测试用例
AIExecutionRecord (ui_automation)        ← AI 测试执行记录

TestCaseGenerationTask (requirement)     ← 测试用例生成任务
DifyConfig (assistant)                   ← Dify 聊天配置
```

---

## 四、AI 浏览器自动化（端到端测试）

### 4.1 原理

AI 浏览器自动化是 TestHub 最核心的 AI 能力。用户用**自然语言**描述测试任务，系统利用 LLM + browser-use 库自动操控真实浏览器完成端到端测试。

**执行流程：**

```
用户输入自然语言任务描述
        │
        ▼
┌─────────────────────────┐
│ 1. analyze_task()       │  ← LLM 将自然语言拆解为有序子任务
│    提取结构化步骤        │     例："1. 打开登录页  2. 输入用户名..."
│    或调用 LLM 分解       │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ 2. run_task()           │
│    ┌───────────────┐    │
│    │ 构建强化 Prompt│    │  ← 注入任务列表 + 12条执行规则
│    └──────┬────────┘    │
│           │             │
│    ┌──────▼────────┐    │
│    │ 注册 Controller│   │  ← mark_task_complete/failed/skipped
│    │ Actions        │   │     update_task_status, close_tab, done
│    └──────┬────────┘    │
│           │             │
│    ┌──────▼────────────┐│
│    │ browser-use Agent │ │  ← 核心执行引擎
│    │ .run(max_steps=100)│ │
│    └──────┬────────────┘│
│           │             │
│    ┌──────▼────────┐    │
│    │ on_step_end   │    │  ← 每步回调：写日志、推进状态、标签页切换
│    │ 回调处理       │    │
│    └───────────────┘    │
└─────────────────────────┘
           │
           ▼
┌─────────────────────────┐
│ 3. 结果收集              │
│    - planned_tasks 状态  │
│    - 执行日志 logs       │
│    - GIF 录屏            │
│    - 耗时统计            │
└─────────────────────────┘
```

### 4.2 browser-use 库增强

`ai_base.py` 对 `browser-use` 做了大量 monkey patch 增强，解决 LLM 输出不规范的问题：

| 增强点 | 说明 |
|--------|------|
| `Agent.get_model_output` patch | 处理 `<thinking>` 标签、JSON 格式修复、动作参数归一化 |
| `TokenCost.register_llm` patch | 消息类型兼容、响应解析增强、重试逻辑 |
| `_normalize_action_params()` | 将 LLM 产生的不同参数名（`element_index`、`node_id`、`content`）统一为 browser-use 标准参数（`index`、`text`） |
| `_enforce_single_task_step()` | 强制每步只完成一个子任务，防止 LLM 在单步中跨任务操作 |
| `_enforce_pending_status_settlement()` | 检测上一步执行了任务但未标记，强制当前步先标记再继续 |
| 登录失败检测 | 通过关键字检测连续 3 次登录失败，自动标记任务失败并终止 |
| 新标签页自动切换 | 检测链接点击后打开的新标签页，自动切换焦点 |

### 4.3 LLM 强化 Prompt

在 `run_task()` 中构建的 Prompt 包含 12 条关键执行规则：

1. **任务标记规则** — 每个子任务完成后必须调用 `mark_task_complete(task_id=N)`
2. **禁止 JavaScript 注入** — 不允许在输入框中使用 `Date.now()` 等
3. **下拉框/模态框隔离** — 触发 UI 变化后必须等待下一步才能操作新元素
4. **标签页处理** — 新标签页需立即切换，不重复点击
5. **极简思维** — 保持 thinking 字段 10 词以内
6. **表单验证检测** — 提交前检查红色错误提示
7. **重试逻辑** — 保存失败时检查验证错误并修复
8. **禁止重复操作** — 已完成的任务标记后继续下一个
9. **结果验证** — 列表页确认数据可见后才标记完成
10. **元素识别** — 避免误点关闭/取消按钮
11. **参数格式** — 使用 browser-use 原生参数名
12. **凭据规则** — 不猜测密码，连续失败后停止

### 4.4 Controller Actions

`run_task()` 中注册的自定义动作：

```python
@controller.action('mark_task_complete')   # 标记子任务完成
@controller.action('mark_task_failed')     # 标记子任务失败
@controller.action('mark_task_skipped')    # 标记子任务跳过
@controller.action('update_task_status')   # 通用状态更新
@controller.action('close_tab')            # 关闭标签页（含自动回退）
@controller.action('Done')                 # 全部任务完成
```

### 4.5 数据模型

```python
# apps/ui_automation/models.py

class AICase:                    # AI 测试用例（可复用）
    name                         # 用例名称
    description                  # 描述
    task_description             # 自然语言任务描述
    project                      # 关联项目

class AIExecutionRecord:         # 单次执行记录
    case_name                    # 用例名（快照）
    task_description             # 任务描述
    execution_mode = 'text'      # 执行模式（仅文本）
    status                       # pending/running/completed/failed/stopped
    logs                         # 执行日志（JSON）
    planned_tasks                # 子任务列表（JSON）
    steps_completed              # 已完成步骤数
    gif_path                     # GIF 录屏路径
    start_time / end_time        # 起止时间
    duration                     # 耗时
```

### 4.6 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/ui-automation/ai-execution-records/run_adhoc/` | POST | 临时任务执行（无需先建 AICase） |
| `/api/ui-automation/ai-cases/{id}/run/` | POST | 执行已保存的 AI 用例 |
| `/api/ui-automation/ai-execution-records/{id}/` | GET | 获取执行状态和日志 |
| `/api/ui-automation/ai-execution-records/{id}/stop_task/` | POST | 停止正在执行的任务 |
| `/api/ui-automation/ai-execution-records/{id}/generate_report/` | GET | 生成执行报告 |
| `/api/ui-automation/ai-execution-records/{id}/export_pdf/` | GET | 导出 PDF 报告 |

---

## 五、AI 需求分析与测试用例生成

### 5.1 原理

上传需求文档（PDF/Word/TXT/Markdown），AI 自动解析文档结构化内容，然后生成测试用例。支持 **Writer-Reviewer-Reviser** 三阶段流水线。

**执行流程：**

```
上传需求文档
     │
     ▼
┌──────────────────┐
│ 文档解析          │  ← PyPDF2/python-docx 提取文本
│ 需求拆分          │  ← AI 识别功能点/模块
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Stage 1: Writer  │  ← role='writer' 的 AIModelConfig
│ 生成测试用例      │     使用 tester.md 提示词模板
│ (流式/完整)       │     支持 SSE 实时输出
└────────┬─────────┘
         │
         ▼ (如果 enable_auto_review=true)
┌──────────────────┐
│ Stage 2: Reviewer│  ← role='reviewer' 的 AIModelConfig
│ AI 评审用例       │     使用 tester_pro.md 提示词模板
│ 评分+问题清单     │     输出质量评分 0-100
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Stage 3: Reviser │  ← 基于评审意见改进用例
│ 修正和补充        │     排序/去重/重编号
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 结果输出          │  ← final_test_cases（Markdown 表格）
│ 可采纳到用例库    │
└──────────────────┘
```

### 5.2 AIModelService 关键方法

```python
# apps/requirement_analysis/models.py

class AIModelService:
    call_openai_compatible_api(...)          # 同步调用 LLM
    call_openai_compatible_api_stream(...)   # 流式调用 LLM（SSE）
    generate_test_cases(...)                 # Stage 1 - 生成用例
    review_test_cases(...)                   # Stage 2 - 评审用例
    revise_test_cases_based_on_review(...)   # Stage 3 - 改进用例
    sort_test_cases_by_id(...)              # 用例排序
    fix_incomplete_last_case(...)            # 修复不完整的尾部用例
    renumber_test_cases(...)                 # 重新编号
```

### 5.3 提示词模板

- **`docs/tester.md`（Writer）**：设定 10 年经验测试专家角色，要求按 Markdown 表格格式输出，覆盖正向流程、异常流程、边界值、业务约束
- **`docs/tester_pro.md`（Reviewer）**：设定 Test Architect 角色，从覆盖率、逻辑性、规范性三维度评审，输出评分+问题+补充建议

提示词可在前端「需求分析 → 提示词配置」页面动态修改，存储在 `PromptConfig` 模型中。

### 5.4 数据模型

```python
# apps/requirement_analysis/models.py

class TestCaseGenerationTask:
    title                        # 任务标题
    requirement_text             # 需求文本
    status                       # pending/generating/reviewing/revising/completed/failed/cancelled
    output_mode                  # stream（流式）/ complete（完整）
    stream_buffer                # 流式输出缓冲区
    stream_position              # 流式输出位置
    generated_content            # 生成的原始内容
    review_content               # 评审内容
    final_test_cases             # 最终测试用例
```

### 5.5 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/requirement-analysis/ai-models/` | CRUD | AI 模型配置管理 |
| `/api/requirement-analysis/prompts/` | CRUD | 提示词配置管理 |
| `/api/requirement-analysis/generation-config/` | CRUD | 生成行为配置 |
| `/api/requirement-analysis/testcase-generation/` | POST | 创建用例生成任务 |
| `/api/requirement-analysis/testcase-generation/{id}/generate/` | POST | 开始生成 |
| `/api/requirement-analysis/documents/upload-and-analyze/` | POST | 上传文档并解析 |

---

## 六、AI 助手（Dify 集成）

### 6.1 原理

通过集成 [Dify](https://dify.ai) 平台，提供测试领域的 AI 问答助手。

```
前端 AssistantView.vue
        │
        ▼ POST /api/assistant/chat/send_message/
Django ChatViewSet.send_message()
        │
        ├── 1. 读取 DifyConfig（api_url + api_key）
        ├── 2. POST {api_url}/chat-messages（blocking 模式）
        ├── 3. 维护 conversation_id（多轮对话）
        └── 4. 保存消息到 ChatMessage 表
```

### 6.2 配置

在前端「AI 助手 → 配置管理」页面设置：

| 字段 | 说明 |
|------|------|
| `api_url` | Dify 服务地址，如 `https://api.dify.ai/v1` |
| `api_key` | Dify 应用的 API Key |
| `is_active` | 是否启用 |

---

## 七、LLM 接入配置详解

### 7.1 统一配置模型

所有 AI 能力共享 `AIModelConfig` 模型（`apps/requirement_analysis/models.py`）：

```python
class AIModelConfig:
    name         # 配置名称
    model_type   # deepseek / qwen / siliconflow / zhipu / other
    role         # writer / reviewer / browser_use_text
    api_key      # API Key
    base_url     # API Base URL
    model_name   # 模型名称
    max_tokens   # 最大 Token 数
    temperature  # 温度参数
    top_p        # Top P 参数
    is_active    # 是否启用（同一 role 只能有一个 active）
```

### 7.2 角色说明

| role | 用途 | 调用方 |
|------|------|--------|
| `writer` | 测试用例编写 | `AIModelService.generate_test_cases()` |
| `reviewer` | 测试用例评审 | `AIModelService.review_test_cases()` |
| `browser_use_text` | AI 浏览器自动化 | `BaseBrowserAgent.__init__()` |

### 7.3 支持的 LLM Provider

所有 Provider 均通过 **OpenAI 兼容 API** 接入，只需配置 `base_url` 和 `api_key`：

| Provider | base_url 示例 | 推荐模型 |
|----------|--------------|----------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat`、`deepseek-reasoner` |
| 通义千问 Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus`、`qwen-max` |
| 硅基流动 SiliconFlow | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-72B-Instruct` |
| 智谱 Zhipu | `https://open.bigmodel.cn/api/paas/v4` | `glm-4`、`glm-4-flash` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o`、`gpt-4o-mini` |
| Moonshot Kimi | `https://api.moonshot.cn/v1` | `kimi-2.5`（强制 temperature=1.0） |
| 其他兼容 API | 自定义 | 自定义 |

### 7.4 在前端配置 LLM

1. 登录后进入 **「需求分析」→「AI 模型配置」** 页面（`/requirement-analysis` → AI 模型配置 Tab）
2. 点击「新增配置」
3. 填写：
   - **配置名称**：如 "DeepSeek-浏览器自动化"
   - **模型类型**：选择 Provider
   - **角色**：选择用途（browser_use_text / writer / reviewer）
   - **API Key**：填入对应 Provider 的密钥
   - **Base URL**：填入 API 地址
   - **模型名称**：填入具体模型标识
   - **温度/Token 等参数**
4. 启用配置（同一角色只能有一个处于启用状态）

### 7.5 备用 .env 配置

如果未在数据库中配置 `browser_use_text` 角色的模型，系统会回退读取 `.env` 文件：

```env
AUTH_TOKEN=your-api-key
BASE_URL=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat
```

---

## 八、启动与使用流程

### 8.1 完整启动步骤

```bash
# 1. 启动 Docker 服务（MySQL + Redis）
docker start testhub-mysql testhub-redis  # 如果已创建容器

# 2. 启动后端
cd /path/to/testhub_platform
source .venv/bin/activate
python manage.py runserver 0.0.0.0:8000

# 3. 启动前端
cd frontend
npm run dev

# 4.（可选）启动 Celery Worker（定时任务/异步任务）
celery -A backend worker --loglevel=info
```

### 8.2 使用 AI 浏览器自动化

1. **配置 LLM**：在「需求分析 → AI 模型配置」中为 `browser_use_text` 角色配置一个 LLM
2. 进入 **「UI 自动化 → AI 智能测试」** 页面
3. 输入自然语言任务描述，例如：
   ```
   打开 http://localhost:3001 ，使用用户名 admin，密码 admin123 登录系统。
   登录后进入"项目管理"页面，创建一个名为"测试项目A"的新项目。
   验证项目列表中能看到刚创建的项目。
   ```
4. 点击「执行」，系统将：
   - 自动拆解子任务（analyze_task）
   - 启动 Chromium 浏览器
   - LLM 逐步决策并执行操作
   - 实时显示执行日志和子任务状态
5. 执行完成后可查看：
   - 执行报告
   - GIF 录屏回放
   - 导出 PDF 报告

### 8.3 使用 AI 生成测试用例

1. **配置 LLM**：为 `writer` 和 `reviewer` 角色各配置一个 LLM
2. 进入 **「需求分析」** 模块
3. 上传需求文档或直接输入需求文本
4. 点击「生成测试用例」
5. 选择输出模式（流式实时输出 / 完整输出）
6. 等待三阶段处理：生成 → 评审 → 改进
7. 查看最终测试用例，可采纳到用例库

### 8.4 使用 AI 助手

1. **配置 Dify**：在「AI 助手 → 配置管理」中填入 Dify 的 API 地址和 Key
2. 进入 **「AI 助手」** 页面
3. 直接对话提问

---

## 九、关键源码文件索引

### 后端

| 文件 | 说明 |
|------|------|
| `apps/ui_automation/ai_agent.py` | AI 浏览器自动化入口：`BrowserAgent` 类和工厂函数 |
| `apps/ui_automation/ai_base.py` | **核心**：`BaseBrowserAgent` 类、browser-use monkey patches、LLM 初始化、任务拆解与执行 |
| `apps/ui_automation/models.py` | `AICase`、`AIExecutionRecord` 模型 |
| `apps/ui_automation/views.py` | `AICaseViewSet`、`AIExecutionRecordViewSet`（执行/停止/报告） |
| `apps/ui_automation/serializers.py` | AI 相关序列化器 |
| `apps/ui_automation/urls.py` | AI 路由：`ai-cases`、`ai-execution-records` |
| `apps/requirement_analysis/models.py` | **核心**：`AIModelConfig`（LLM 统一配置）、`AIModelService`（LLM 调用）、`TestCaseGenerationTask` |
| `apps/requirement_analysis/views.py` | 需求分析视图：文档上传、用例生成、SSE 流式输出 |
| `apps/requirement_analysis/serializers.py` | 需求分析序列化器 |
| `apps/assistant/views.py` | Dify 聊天代理：`ChatViewSet` |
| `apps/assistant/views_config.py` | Dify 配置管理：`DifyConfigViewSet` |
| `apps/assistant/models.py` | `DifyConfig`、`ChatMessage` 模型 |
| `docs/tester.md` | AI 用例编写提示词模板 |
| `docs/tester_pro.md` | AI 用例评审提示词模板 |
| `backend/settings.py` | Django 配置（数据库、Redis、Celery、CORS） |

### 前端

| 文件 | 说明 |
|------|------|
| `frontend/src/views/ui-automation/ai/AITesting.vue` | AI 智能测试主页面 |
| `frontend/src/views/ui-automation/ai/AICaseList.vue` | AI 用例列表 |
| `frontend/src/views/ui-automation/ai/AIExecutionRecords.vue` | AI 执行记录列表 |
| `frontend/src/views/ui-automation/ai/AIExecutionReport.vue` | AI 执行报告 |
| `frontend/src/views/requirement-analysis/RequirementAnalysisView.vue` | 需求分析主页面 |
| `frontend/src/views/requirement-analysis/AIModelConfig.vue` | AI 模型配置页面 |
| `frontend/src/views/requirement-analysis/PromptConfig.vue` | 提示词配置页面 |
| `frontend/src/views/assistant/AssistantView.vue` | AI 助手对话页面 |
| `frontend/src/api/ui_automation.js` | UI 自动化 API 调用 |
| `frontend/src/api/requirement-analysis.js` | 需求分析 API 调用 |

---

## 附录：特殊模型注意事项

| 模型 | 注意事项 |
|------|---------|
| Kimi (kimi-2.5, kimi-k2.5) | 强制 `temperature=1.0`（模型限制） |
| DeepSeek / Qwen | Prompt 中额外要求极简输出以提速 |
| 所有模型 | LLM 调用超时 60 秒，每步超时 90 秒，最大重试 2 次 |
| 浏览器自动化 | `use_vision=False`（仅文本模式），`max_steps=100` |
