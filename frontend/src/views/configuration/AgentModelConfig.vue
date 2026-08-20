<template>
  <div class="agent-model-config">
    <div class="page-header">
      <div>
        <h1>AI Agent配置</h1>
        <p>Chat 与 Agent 工作流使用独立模型配置；Alpha 规划和反思各自选择专用模型。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增模型</el-button>
    </div>

    <div v-loading="loading" class="model-workflows">
      <section v-for="group in roleGroups" :key="group.key" class="role-group" :class="group.key">
        <header class="role-group-header">
          <h2>{{ group.title }}</h2>
          <p>{{ group.description }}</p>
        </header>
        <div class="role-slots">
          <article v-for="slot in group.slots" :key="slot.role" class="role-slot">
            <div class="slot-label">{{ slot.label }}</div>
            <template v-if="configsByRole(slot.role).length">
              <div v-for="config in configsByRole(slot.role)" :key="config.id" class="config-card">
                <div class="config-header">
                  <div>
                    <h3>{{ config.name }}</h3>
                    <div class="config-badges">
                      <span class="provider-badge">{{ providerLabel(config.model_type) }}</span>
                      <span class="model-name-badge">{{ config.model_name }}</span>
                      <el-tag size="small" :type="config.is_active ? 'success' : 'info'">{{ config.is_active ? '启用' : '停用' }}</el-tag>
                    </div>
                  </div>
                  <div class="config-actions">
                    <el-switch v-model="config.is_active" size="small" @change="toggleActive(config)" />
                    <el-tooltip content="编辑模型配置"><el-button :icon="EditPen" circle size="small" @click="openEdit(config)" /></el-tooltip>
                    <el-popconfirm title="确定删除此模型配置？" @confirm="removeConfig(config)">
                      <template #reference><el-button :icon="Delete" circle size="small" type="danger" plain /></template>
                    </el-popconfirm>
                  </div>
                </div>
                <div class="base-url">{{ config.base_url }}</div>
              </div>
            </template>
            <button v-else class="empty-slot" @click="openCreate(slot.role)">
              <el-icon><Plus /></el-icon>
              配置{{ slot.label }}
            </button>
          </article>
        </div>
      </section>
    </div>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑模型配置' : '新增模型配置'" width="620px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="105px">
        <el-form-item label="配置名称" prop="name"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="配置角色" prop="role">
          <el-select v-model="form.role" style="width: 100%">
            <el-option v-for="option in roleOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型提供商" prop="model_type">
          <el-select v-model="form.model_type" style="width: 100%" @change="applyProviderBaseUrl">
            <el-option label="OpenAI" value="openai" />
            <el-option label="Azure OpenAI" value="azure_openai" />
            <el-option label="Anthropic Claude" value="anthropic" />
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="通义千问" value="qwen" />
            <el-option label="Google Gemini" value="gemini" />
            <el-option label="Moonshot / Kimi" value="moonshot" />
            <el-option label="百川智能" value="baichuan" />
            <el-option label="MiniMax" value="minimax" />
            <el-option label="硅基流动" value="siliconflow" />
            <el-option label="智谱" value="zhipu" />
            <el-option label="OpenRouter" value="openrouter" />
            <el-option label="Together AI" value="together" />
            <el-option label="Groq" value="groq" />
            <el-option label="Ollama" value="ollama" />
            <el-option label="vLLM" value="vllm" />
            <el-option label="其他 OpenAI 兼容模型" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL" prop="base_url"><el-input v-model="form.base_url" placeholder="https://api.example.com/v1" /></el-form-item>
        <el-form-item label="模型名称" prop="model_name"><el-input v-model="form.model_name" /></el-form-item>
        <el-form-item label="API Key" prop="api_key">
          <el-input v-model="form.api_key" type="password" show-password :placeholder="editingId ? '留空则保持原 Key 不变' : ''" />
          <div v-if="editingId && form.api_key_masked" class="key-status">已保存：{{ form.api_key_masked }}</div>
        </el-form-item>
        <el-form-item label="最大Tokens"><el-input-number v-model="form.max_tokens" :min="1" :max="32768" /></el-form-item>
        <el-form-item label="Temperature"><el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" /></el-form-item>
        <el-form-item label="Top P"><el-input-number v-model="form.top_p" :min="0" :max="1" :step="0.1" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.is_active" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, EditPen, Plus } from '@element-plus/icons-vue'
import api from '@/utils/api'

const configs = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const emptyForm = (role = 'chat') => ({ name: '', role, model_type: 'other', base_url: '', model_name: '', api_key: '', api_key_masked: '', max_tokens: 4096, temperature: 0.7, top_p: 0.9, is_active: true })
const form = ref(emptyForm())
const roleOptions = [
  { value: 'chat', label: 'Chat 模型' },
  { value: 'agent', label: 'Agent 模型' },
  { value: 'alpha_planner', label: 'Alpha Planner 模型' },
  { value: 'alpha_reflection', label: 'Alpha Reflection 模型' },
]
const roleGroups = [
  {
    key: 'chat',
    title: 'Chat',
    description: '用于 AI Assistant 对话。',
    slots: [{ role: 'chat', label: 'Chat 模型' }],
  },
  {
    key: 'agent',
    title: 'AI Agent 工作流',
    description: 'Agent 提示词由 Agent、Alpha Planner 和 Alpha Reflection 共享；模型独立配置。',
    slots: [
      { role: 'agent', label: 'Agent 模型' },
      { role: 'alpha_planner', label: 'Alpha Planner 模型' },
      { role: 'alpha_reflection', label: 'Alpha Reflection 模型' },
    ],
  },
]
const providerBaseUrls = {
  openai: 'https://api.openai.com/v1',
  azure_openai: 'https://YOUR_RESOURCE_NAME.openai.azure.com/openai/deployments/YOUR_DEPLOYMENT_NAME',
  anthropic: 'https://api.anthropic.com/v1',
  deepseek: 'https://api.deepseek.com/v1',
  qwen: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  gemini: 'https://generativelanguage.googleapis.com/v1beta/openai',
  moonshot: 'https://api.moonshot.cn/v1',
  baichuan: 'https://api.baichuan-ai.com/v1',
  minimax: 'https://api.minimaxi.com/v1',
  siliconflow: 'https://api.siliconflow.cn/v1',
  zhipu: 'https://open.bigmodel.cn/api/paas/v4',
  openrouter: 'https://openrouter.ai/api/v1',
  together: 'https://api.together.xyz/v1',
  groq: 'https://api.groq.com/openai/v1',
  ollama: 'http://localhost:11434/v1',
  vllm: 'http://localhost:8000/v1',
}
const rules = computed(() => ({
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  role: [{ required: true, message: '请选择配置角色', trigger: 'change' }],
  base_url: [{ required: true, message: '请输入 Base URL', trigger: 'blur' }, { type: 'url', message: '请输入有效 URL', trigger: 'blur' }],
  model_name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
}))

const loadConfigs = async () => {
  loading.value = true
  try {
    const response = await api.get('/ai-agent/models/')
    configs.value = response.data.results || response.data || []
  } catch (error) {
    ElMessage.error('无法加载 AI Agent 模型配置')
  } finally {
    loading.value = false
  }
}

const openCreate = (role = 'chat') => {
  editingId.value = null
  form.value = emptyForm(role)
  dialogVisible.value = true
}

const applyProviderBaseUrl = (provider) => {
  form.value.base_url = providerBaseUrls[provider] || ''
}

const openEdit = (config) => {
  editingId.value = config.id
  form.value = { ...emptyForm(config.role), ...config, api_key: '' }
  dialogVisible.value = true
}

const saveConfig = async () => {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload = { ...form.value }
    if (!payload.api_key) delete payload.api_key
    if (editingId.value) await api.patch(`/ai-agent/models/${editingId.value}/`, payload)
    else await api.post('/ai-agent/models/', payload)
    ElMessage.success('模型配置已保存')
    dialogVisible.value = false
    await loadConfigs()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '保存模型配置失败')
  } finally {
    saving.value = false
  }
}

const configsByRole = (role) => configs.value.filter((config) => config.role === role)
const providerLabel = (provider) => ({
  openai: 'OpenAI', azure_openai: 'Azure OpenAI', anthropic: 'Anthropic', deepseek: 'DeepSeek', qwen: '通义千问', gemini: 'Gemini', moonshot: 'Moonshot', baichuan: '百川', minimax: 'MiniMax', siliconflow: '硅基流动', zhipu: '智谱', openrouter: 'OpenRouter', together: 'Together AI', groq: 'Groq', ollama: 'Ollama', vllm: 'vLLM', other: 'OpenAI 兼容',
}[provider] || provider)

const toggleActive = async (config) => {
  try {
    await api.patch(`/ai-agent/models/${config.id}/`, { is_active: config.is_active })
    ElMessage.success(`模型已${config.is_active ? '启用' : '停用'}`)
    await loadConfigs()
  } catch (error) {
    config.is_active = !config.is_active
    ElMessage.error('更新模型状态失败')
  }
}

const removeConfig = async (config) => {
  try {
    await api.delete(`/ai-agent/models/${config.id}/`)
    ElMessage.success('模型配置已删除')
    await loadConfigs()
  } catch (error) {
    ElMessage.error('删除模型配置失败')
  }
}

onMounted(loadConfigs)
</script>

<style scoped>
.agent-model-config { max-width: 1240px; margin: 0 auto; padding: 8px 0 36px; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 26px; }
.page-header h1 { margin: 0; color: #1c2b3a; font-size: 24px; }
.page-header p { margin: 8px 0 0; color: #667085; font-size: 14px; }
.model-workflows { display: grid; grid-template-columns: minmax(260px, 0.8fr) minmax(0, 2fr); gap: 18px; }
.role-group { border: 1px solid #dfe5ec; border-top: 3px solid #2563eb; background: #f8fafc; padding: 16px; }
.role-group.agent { border-top-color: #0f766e; }
.role-group-header h2 { margin: 0; color: #1e293b; font-size: 17px; }
.role-group-header p { margin: 5px 0 16px; color: #64748b; font-size: 13px; line-height: 1.5; }
.role-slots { display: grid; gap: 12px; }
.role-group.agent .role-slots { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.slot-label { margin-bottom: 7px; color: #475569; font-size: 12px; font-weight: 700; }
.config-card { min-height: 116px; border: 1px solid #dfe5ec; background: #fff; padding: 14px; }
.config-header { display: flex; justify-content: space-between; gap: 10px; }
.config-header h3 { margin: 0 0 8px; color: #1e293b; font-size: 15px; overflow-wrap: anywhere; }
.config-badges { display: flex; flex-wrap: wrap; gap: 5px; }
.provider-badge, .model-name-badge { padding: 3px 7px; border-radius: 12px; font-size: 11px; line-height: 1.25; }
.provider-badge { background: #e0f2fe; color: #075985; }
.model-name-badge { background: #f1f5f9; color: #475569; overflow-wrap: anywhere; }
.config-actions { display: flex; align-items: center; gap: 5px; }
.base-url { margin-top: 13px; padding-top: 10px; border-top: 1px solid #edf0f4; color: #64748b; font-size: 12px; line-height: 1.45; overflow-wrap: anywhere; }
.empty-slot { display: inline-flex; align-items: center; justify-content: center; gap: 7px; width: 100%; min-height: 116px; border: 1px dashed #94a3b8; background: transparent; color: #475569; cursor: pointer; font-size: 13px; }
.empty-slot:hover { border-color: #2563eb; color: #1d4ed8; }
.key-status { margin-top: 5px; color: #667085; font-size: 12px; }
@media (max-width: 900px) { .model-workflows { grid-template-columns: 1fr; } .role-group.agent .role-slots { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .page-header { align-items: stretch; flex-direction: column; } .page-header > .el-button { align-self: flex-start; } }
</style>