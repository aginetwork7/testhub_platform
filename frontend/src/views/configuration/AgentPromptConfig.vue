<template>
  <div class="agent-prompt-config">
    <div class="page-header">
      <div>
        <h1>AI Agent提示词配置</h1>
        <p>分别配置 Chat 与 Agent 提示词，不复用 AI 智能测试提示词。</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增提示词</el-button>
    </div>

    <el-tabs v-model="role" @tab-change="loadConfigs">
      <el-tab-pane label="Chat提示词" name="chat" />
      <el-tab-pane label="Agent提示词" name="agent" />
    </el-tabs>

    <el-table v-loading="loading" :data="configs" class="config-table">
      <el-table-column prop="name" label="配置名称" min-width="200" />
      <el-table-column label="提示词预览" min-width="420" show-overflow-tooltip>
        <template #default="{ row }">{{ row.content }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-popconfirm title="确定删除此提示词配置？" @confirm="removeConfig(row)">
            <template #reference><el-button link type="danger">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑提示词配置' : '新增提示词配置'" width="720px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="配置名称" prop="name"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="配置角色"><el-input :model-value="role === 'chat' ? 'Chat提示词' : 'Agent提示词'" disabled /></el-form-item>
        <el-form-item label="提示词内容" prop="content"><el-input v-model="form.content" type="textarea" :rows="14" /></el-form-item>
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
const emptyForm = () => ({ name: '', content: '', is_active: true })
const form = ref(emptyForm())
const rules = computed(() => ({
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  content: [{ required: true, message: '请输入提示词内容', trigger: 'blur' }]
}))

const loadConfigs = async () => {
  loading.value = true
  try {
    const response = await api.get('/ai-agent/prompts/', { params: { role: role.value } })
    configs.value = response.data.results || response.data || []
  } catch (error) {
    ElMessage.error('无法加载 AI Agent提示词配置')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingId.value = null
  form.value = emptyForm()
  dialogVisible.value = true
}

const openEdit = (config) => {
  editingId.value = config.id
  form.value = { ...config }
  dialogVisible.value = true
}

const saveConfig = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload = { ...form.value, role: role.value }
    if (editingId.value) await api.patch(`/ai-agent/prompts/${editingId.value}/`, payload)
    else await api.post('/ai-agent/prompts/', payload)
    ElMessage.success('提示词配置已保存')
    dialogVisible.value = false
    await loadConfigs()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '保存提示词配置失败')
  } finally {
    saving.value = false
  }
}

const removeConfig = async (config) => {
  try {
    await api.delete(`/ai-agent/prompts/${config.id}/`)
    ElMessage.success('提示词配置已删除')
    await loadConfigs()
  } catch (error) {
    ElMessage.error('删除提示词配置失败')
  }
}

onMounted(loadConfigs)
</script>

<style scoped>
.agent-prompt-config { max-width: 1100px; margin: 0 auto; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 20px; }
.page-header h1 { margin: 0; color: #1c2b3a; font-size: 24px; }
.page-header p { margin: 8px 0 0; color: #667085; font-size: 14px; }
.config-table { border: 1px solid #e4eaf1; }
</style>