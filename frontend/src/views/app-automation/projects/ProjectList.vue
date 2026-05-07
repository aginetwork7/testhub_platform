<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">{{ t('appAutomation.project.title') }}</h2>
      <el-button type="primary" @click="openCreateDialog">
        <el-icon><Plus /></el-icon>{{ t('appAutomation.project.newProject') }}
      </el-button>
    </div>

    <div class="card-container">
      <!-- 筛选 -->
      <div class="filter-bar">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-input v-model="searchText" :placeholder="t('appAutomation.project.searchPlaceholder')" clearable @clear="loadProjects" @keyup.enter="loadProjects">
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
          </el-col>
          <el-col :span="4">
            <el-select v-model="statusFilter" :placeholder="t('appAutomation.project.statusFilter')" clearable @change="loadProjects">
              <el-option :label="t('appAutomation.project.status.notStarted')" value="not_started" />
              <el-option :label="t('appAutomation.project.status.active')" value="active" />
              <el-option :label="t('appAutomation.project.status.paused')" value="paused" />
              <el-option :label="t('appAutomation.project.status.completed')" value="completed" />
              <el-option :label="t('appAutomation.project.status.archived')" value="archived" />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-button type="primary" @click="loadProjects"><el-icon><Search /></el-icon>{{ t('appAutomation.common.query') }}</el-button>
            <el-button @click="searchText = ''; statusFilter = ''; loadProjects()">{{ t('appAutomation.common.reset') }}</el-button>
          </el-col>
        </el-row>
      </div>

      <!-- 项目列表 -->
      <el-table :data="projects" v-loading="loading" border stripe :row-class-name="tableRowClassName">
        <el-table-column :label="t('appAutomation.project.projectName')" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.id === highlightProjectId" class="highlight-text">{{ row.name }}</span>
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" :label="t('appAutomation.project.projectDesc')" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('appAutomation.project.projectStatus')" min-width="90">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusDisplayText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('appAutomation.project.testCaseCount')" min-width="70" align="center">
          <template #default="{ row }">{{ row.test_case_count || 0 }}</template>
        </el-table-column>
        <el-table-column :label="t('appAutomation.project.testSuiteCount')" min-width="70" align="center">
          <template #default="{ row }">{{ row.test_suite_count || 0 }}</template>
        </el-table-column>
        <el-table-column :label="t('appAutomation.project.owner')" min-width="80">
          <template #default="{ row }">{{ row.owner_name || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('appAutomation.project.memberCount')" min-width="70" align="center">
          <template #default="{ row }">{{ row.member_count || 0 }}</template>
        </el-table-column>
        <el-table-column :label="t('appAutomation.project.startDate')" min-width="110">
          <template #default="{ row }">{{ row.start_date || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('appAutomation.project.endDate')" min-width="110">
          <template #default="{ row }">{{ row.end_date || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('appAutomation.project.createTime')" min-width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column :label="t('appAutomation.common.operation')" min-width="150">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewDetail(row)">{{ t('appAutomation.common.detail') }}</el-button>
            <el-button type="warning" link size="small" @click="openEditDialog(row)">{{ t('appAutomation.common.edit') }}</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">{{ t('appAutomation.common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.current"
          v-model:page-size="pagination.size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadProjects"
          @current-change="loadProjects"
        />
      </div>
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? t('appAutomation.project.editProject') : t('appAutomation.project.createProject')" width="520px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="80px">
        <el-form-item :label="t('appAutomation.project.projectName')" prop="name">
          <el-input v-model="form.name" :placeholder="t('appAutomation.project.projectNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('appAutomation.project.projectDesc')" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" :placeholder="t('appAutomation.project.projectDescPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('appAutomation.project.projectStatus')" prop="status">
          <el-select v-model="form.status" :placeholder="t('appAutomation.project.selectStatus')" style="width:100%">
            <el-option :label="t('appAutomation.project.status.notStarted')" value="not_started" />
            <el-option :label="t('appAutomation.project.status.active')" value="active" />
            <el-option :label="t('appAutomation.project.status.paused')" value="paused" />
            <el-option :label="t('appAutomation.project.status.completed')" value="completed" />
            <el-option :label="t('appAutomation.project.status.archived')" value="archived" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('appAutomation.project.startDate')">
          <el-date-picker v-model="form.start_date" type="date" :placeholder="t('appAutomation.project.startDate')" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item :label="t('appAutomation.project.endDate')">
          <el-date-picker v-model="form.end_date" type="date" :placeholder="t('appAutomation.project.endDate')" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('appAutomation.common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">{{ t('appAutomation.common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="t('appAutomation.project.projectName')" width="600px">
      <div v-if="selectedProject">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('appAutomation.project.projectName')">{{ selectedProject.name }}</el-descriptions-item>
          <el-descriptions-item :label="t('appAutomation.project.projectStatus')">
            <el-tag :type="getStatusType(selectedProject.status)">
              {{ getStatusDisplayText(selectedProject.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('appAutomation.project.owner')">{{ selectedProject.owner_name || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('appAutomation.project.memberCount')">{{ selectedProject.member_count || 0 }} 人</el-descriptions-item>
          <el-descriptions-item :label="t('appAutomation.project.testCaseCount')">{{ selectedProject.test_case_count || 0 }} 个</el-descriptions-item>
          <el-descriptions-item :label="t('appAutomation.project.testSuiteCount')">{{ selectedProject.test_suite_count || 0 }} 个</el-descriptions-item>
          <el-descriptions-item :label="t('appAutomation.project.startDate')">{{ selectedProject.start_date || '未设置' }}</el-descriptions-item>
          <el-descriptions-item :label="t('appAutomation.project.endDate')">{{ selectedProject.end_date || '未设置' }}</el-descriptions-item>
          <el-descriptions-item :label="t('appAutomation.project.createTime')" :span="2">{{ formatDateTime(selectedProject.created_at) }}</el-descriptions-item>
          <el-descriptions-item :label="t('appAutomation.project.projectDesc')" :span="2">{{ selectedProject.description || '无描述' }}</el-descriptions-item>
        </el-descriptions>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">{{ t('appAutomation.common.close') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import { getAppProjects, createAppProject, updateAppProject, deleteAppProject } from '@/api/app-automation.js'

const route = useRoute()
const { t } = useI18n()

const loading = ref(false)
const submitting = ref(false)
const projects = ref([])
const searchText = ref('')
const statusFilter = ref('')
const pagination = reactive({ current: 1, size: 20, total: 0 })
const highlightProjectId = ref(null)
const fromMetaProject = ref(null)

const statusMap = computed(() => ({
  'not_started': t('appAutomation.project.status.notStarted'),
  'active': t('appAutomation.project.status.active'),
  'paused': t('appAutomation.project.status.paused'),
  'completed': t('appAutomation.project.status.completed'),
  'archived': t('appAutomation.project.status.archived')
}))

const getStatusType = (status) => {
  const map = {
    'not_started': 'warning',
    'active': 'primary',
    'paused': 'info',
    'completed': 'success',
    'archived': 'info'
  }
  return map[status] || 'info'
}

const getStatusText = (status) => {
  return statusMap.value[status] || status
}

const getStatusDisplayText = (status) => {
  return statusMap.value[status] || status
}

// 对话框
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref(null)
const form = reactive({
  name: '',
  description: '',
  status: 'active',
  start_date: null,
  end_date: null,
})
const formRules = {
  name: [
    { required: true, message: t('appAutomation.project.pleaseEnterProjectName'), trigger: 'blur' },
    { min: 2, max: 200, message: t('appAutomation.project.nameLengthValidation'), trigger: 'blur' },
  ],
}

// 详情
const detailVisible = ref(false)
const selectedProject = ref(null)

const tableRowClassName = ({ row }) => {
  if (row.id === highlightProjectId.value) {
    return 'highlight-row'
  }
  return ''
}

const formatDateToISO = (date) => {
  if (!date) return null
  const d = new Date(date)
  return d.toISOString().split('T')[0]
}

onMounted(() => {
  highlightProjectId.value = route.query.projectId ? Number(route.query.projectId) : null
  fromMetaProject.value = route.query.fromMetaProject || null
  loadProjects()

  if (highlightProjectId.value) {
    nextTick(() => {
      setTimeout(() => {
        const row = document.querySelector(`[data-project-id="${highlightProjectId.value}"]`)
        if (row) {
          row.scrollIntoView({ behavior: 'smooth', block: 'center' })
          row.classList.add('highlight-row')
          setTimeout(() => row.classList.remove('highlight-row'), 3000)
        }
      }, 100)
    })
  }
})

async function loadProjects() {
  loading.value = true
  try {
    const params = { page: pagination.current, page_size: pagination.size }
    if (searchText.value) params.search = searchText.value
    if (statusFilter.value) params.status = statusFilter.value
    const res = await getAppProjects(params)
    projects.value = res.data.results || res.data || []
    pagination.total = res.data.count || projects.value.length
  } catch { ElMessage.error('加载项目列表失败') }
  finally { loading.value = false }
}

function openCreateDialog() {
  isEdit.value = false
  editId.value = null
  Object.assign(form, { name: '', description: '', status: 'active', start_date: null, end_date: null })
  dialogVisible.value = true
}

function openEditDialog(row) {
  isEdit.value = true
  editId.value = row.id
  Object.assign(form, {
    name: row.name,
    description: row.description || '',
    status: row.status,
    start_date: row.start_date ? new Date(row.start_date) : null,
    end_date: row.end_date ? new Date(row.end_date) : null,
  })
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const projectData = {
      ...form,
      start_date: formatDateToISO(form.start_date),
      end_date: formatDateToISO(form.end_date)
    }
    if (isEdit.value) {
      await updateAppProject(editId.value, projectData)
      ElMessage.success('项目更新成功')
    } else {
      await createAppProject(projectData)
      ElMessage.success('项目创建成功')
    }
    dialogVisible.value = false
    loadProjects()
  } catch (e) {
    ElMessage.error(isEdit.value ? '更新失败' : '创建失败')
  } finally { submitting.value = false }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确认删除项目「${row.name}」？此操作不可恢复`, '删除确认', { type: 'warning' })
    await deleteAppProject(row.id)
    ElMessage.success('已删除')
    loadProjects()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

function viewDetail(row) {
  selectedProject.value = row
  detailVisible.value = true
}

function formatDateTime(dt) {
  if (!dt) return '-'
  return new Date(dt).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.page-container { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-title { margin: 0; font-size: 20px; }
.card-container { background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.filter-bar { margin-bottom: 20px; }
.pagination-container { margin-top: 20px; display: flex; justify-content: flex-end; }
.highlight-row { background-color: #ecf5ff !important; }
.highlight-text { color: #409eff; font-weight: 600; }
</style>
