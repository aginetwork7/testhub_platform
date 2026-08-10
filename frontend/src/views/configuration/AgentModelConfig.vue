<template>
  <div class="agent-model-config">
    <div class="page-header">
      <div>
        <h1>AI Agent配置</h1>
        <p>分别配置 Chat 模型与 Agent 模型，不复用 AI 智能模式配置。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增模型</el-button>
    </div>

    <el-tabs v-model="role" @tab-change="loadConfigs">
      <el-tab-pane label="Chat模型" name="chat" />
      <el-tab-pane label="Agent模型" name="agent" />
    </el-tabs>

    <el-table v-loading="loading" :data="configs" class="config-table">
      <el-table-column prop="name" label="配置名称" min-width="180" />
      <el-table-column prop="model_type" label="提供商" width="130" />
      <el-table-column prop="model_name" label="模型名称" min-width="180" />
      <el-table-column prop="base_url" label="Base URL" min-width="240" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-popconfirm title="确定删除此模型配置？" @confirm="removeConfig(row)">
            <template #reference><el-button link type="danger">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑模型配置' : '新增模型配置'" width="620px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="105px">
        <el-form-item label="配置名称" prop="name"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="配置角色"><el-input :model-value="role === 'chat' ? 'Chat模型' : 'Agent模型'" disabled /></el-form-item>
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
import { Plus } from '@element-plus/icons-vue'
import api from '@/utils/api'

const role = ref('chat')
const configs = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const emptyForm = () => ({ name: '', model_type: 'other', base_url: '', model_name: '', api_key: '', api_key_masked: '', max_tokens: 4096, temperature: 0.7, top_p: 0.9, is_active: true })
const form = ref(emptyForm())
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
  base_url: [{ required: true, message: '请输入 Base URL', trigger: 'blur' }, { type: 'url', message: '请输入有效 URL', trigger: 'blur' }],
  model_name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
}))

const loadConfigs = async () => {
  loading.value = true
  try {
    const response = await api.get('/assistant/config/agent-models/', { params: { role: role.value } })
    configs.value = response.data.results || response.data || []
  } catch (error) {
    ElMessage.error('无法加载 AI Agent 模型配置')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingId.value = null
  form.value = emptyForm()
  dialogVisible.value = true
}

const applyProviderBaseUrl = (provider) => {
  form.value.base_url = providerBaseUrls[provider] || ''
}

const openEdit = (config) => {
  editingId.value = config.id
  form.value = { ...emptyForm(), ...config, api_key: '' }
  dialogVisible.value = true
}

const saveConfig = async () => {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload = { ...form.value, role: role.value }
    if (!payload.api_key) delete payload.api_key
    if (editingId.value) await api.patch(`/assistant/config/agent-models/${editingId.value}/`, payload)
    else await api.post('/assistant/config/agent-models/', payload)
    ElMessage.success('模型配置已保存')
    dialogVisible.value = false
    await loadConfigs()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '保存模型配置失败')
  } finally {
    saving.value = false
  }
}

const removeConfig = async (config) => {
  try {
    await api.delete(`/assistant/config/agent-models/${config.id}/`)
    ElMessage.success('模型配置已删除')
    await loadConfigs()
  } catch (error) {
    ElMessage.error('删除模型配置失败')
  }
}

onMounted(loadConfigs)
</script>

<style scoped>
.agent-model-config { max-width: 1100px; margin: 0 auto; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 20px; }
.page-header h1 { margin: 0; color: #1c2b3a; font-size: 24px; }
.page-header p { margin: 8px 0 0; color: #667085; font-size: 14px; }
.config-table { border: 1px solid #e4eaf1; }
.key-status { margin-top: 5px; color: #667085; font-size: 12px; }
</style>