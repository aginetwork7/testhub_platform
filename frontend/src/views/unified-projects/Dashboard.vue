<template>
  <div class="dashboard-container">
    <div class="page-header">
      <h2>{{ $t('unifiedProject.title') }}</h2>
      <el-button type="primary" @click="handleCreate">
        <el-icon><Plus /></el-icon>
        {{ $t('unifiedProject.createProject') }}
      </el-button>
    </div>

    <el-row :gutter="20" class="stats-row">
      <el-col :xs="12" :sm="8" :md="4" :lg="4">
        <div class="stat-card">
          <div class="stat-icon bg-blue">
            <el-icon :size="24"><Folder /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.totalProjects }}</div>
            <div class="stat-label" :title="$t('unifiedProject.dashboard.totalProjects')">{{ $t('unifiedProject.dashboard.totalProjects') }}</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :md="4" :lg="4">
        <div class="stat-card">
          <div class="stat-icon bg-purple" style="background: linear-gradient(135deg, #e0c3fc 0%, #8ec5fc 100%);">
            <el-icon :size="24"><Tickets /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.aiProjects }}</div>
            <div class="stat-label" :title="$t('unifiedProject.dashboard.aiProjects')">{{ $t('unifiedProject.dashboard.aiProjects') }}</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :md="4" :lg="4">
        <div class="stat-card ai-test-card">
          <div class="stat-icon bg-cyan">
            <el-icon :size="24"><MagicStick /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.aiTestProjects }}</div>
            <div class="stat-label" :title="$t('unifiedProject.dashboard.aiTestProjects')">{{ $t('unifiedProject.dashboard.aiTestProjects') }}</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :md="4" :lg="4">
        <div class="stat-card">
          <div class="stat-icon bg-green">
            <el-icon :size="24"><Link /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.apiProjects }}</div>
            <div class="stat-label" :title="$t('unifiedProject.dashboard.apiProjects')">{{ $t('unifiedProject.dashboard.apiProjects') }}</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :md="4" :lg="4">
        <div class="stat-card">
          <div class="stat-icon bg-purple">
            <el-icon :size="24"><Monitor /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.uiProjects }}</div>
            <div class="stat-label" :title="$t('unifiedProject.dashboard.uiProjects')">{{ $t('unifiedProject.dashboard.uiProjects') }}</div>
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8" :md="4" :lg="4">
        <div class="stat-card">
          <div class="stat-icon bg-orange">
            <el-icon :size="24"><Cellphone /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.appProjects }}</div>
            <div class="stat-label" :title="$t('unifiedProject.dashboard.appProjects')">{{ $t('unifiedProject.dashboard.appProjects') }}</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-card class="list-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>{{ $t('unifiedProject.title') }}</span>
        </div>
      </template>

      <div class="filter-bar">
        <el-input
          v-model="searchQuery"
          :placeholder="$t('unifiedProject.searchPlaceholder')"
          clearable
          @input="handleSearch"
          style="width: 300px;"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select
          v-model="statusFilter"
          :placeholder="$t('unifiedProject.statusFilter')"
          clearable
          @change="handleFilter"
          style="width: 150px;"
        >
          <el-option :label="$t('project.notStarted')" value="not_started" />
          <el-option :label="$t('project.active')" value="active" />
          <el-option :label="$t('project.paused')" value="paused" />
          <el-option :label="$t('project.completed')" value="completed" />
          <el-option :label="$t('project.archived')" value="archived" />
        </el-select>
      </div>

      <div v-if="loading" class="loading">
        <el-skeleton :rows="5" animated />
      </div>
      <div v-else-if="projects.length === 0" class="empty">
        <el-empty :description="$t('unifiedProject.dashboard.noProjects')" />
      </div>
      <el-table v-else :data="projects" style="width: 100%">
        <el-table-column prop="name" :label="$t('unifiedProject.projectName')" min-width="150" width="150">
          <template #default="{ row }">
            <el-link @click="goToDetail(row.id, row.name)" type="primary">
              {{ row.name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="description" :label="$t('unifiedProject.description')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" :label="$t('project.status')" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('unifiedProject.modules')" min-width="200" width="250">
          <template #default="{ row }">
            <el-tag
              v-for="module in row.modules"
              :key="module.id"
              size="small"
              class="module-tag"
            >
              {{ getModuleLabel(module.module_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="owner_info.username" :label="$t('unifiedProject.owner')" width="120" />
        <el-table-column prop="created_at" :label="$t('unifiedProject.createdAt')" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('unifiedProject.actions')" width="150" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleEdit(row)">
              {{ $t('common.edit') }}
            </el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row.id)">
              {{ $t('common.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination" v-if="total > 0">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <UnifiedProjectDialog
      v-model:visible="dialogVisible"
      :is-edit="isEdit"
      :project-data="currentProject"
      @success="handleDialogSuccess"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Folder, Link, Monitor, Cellphone, Plus, Search, MagicStick } from '@element-plus/icons-vue'
import { getMetaProjects, deleteMetaProject } from '@/api/unified-projects'
import UnifiedProjectDialog from '@/components/project/UnifiedProjectDialog.vue'
import dayjs from 'dayjs'

const router = useRouter()
const { t } = useI18n()

const loading = ref(false)
const projects = ref([])
const searchQuery = ref('')
const statusFilter = ref('')
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)

const stats = ref({
  totalProjects: 0,
  aiProjects: 0,
  aiTestProjects: 0,
  apiProjects: 0,
  uiProjects: 0,
  appProjects: 0
})

const dialogVisible = ref(false)
const isEdit = ref(false)
const currentProject = ref(null)

const handleCreate = () => {
  isEdit.value = false
  currentProject.value = null
  dialogVisible.value = true
}

const loadProjects = async () => {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value
    }
    if (searchQuery.value) {
      params.search = searchQuery.value
    }
    if (statusFilter.value) {
      params.status = statusFilter.value
    }
    const response = await getMetaProjects(params)
    projects.value = response.data.results || []
    total.value = response.data.count || 0
  } catch (error) {
    console.error('获取项目列表失败:', error)
    ElMessage.error(t('unifiedProject.messages.fetchListFailed'))
  } finally {
    loading.value = false
  }
}

const loadStats = async () => {
  try {
    const response = await getMetaProjects({ page_size: 1000 })
    const allProjects = response.data.results || []
    let aiCount = 0, aiTestCount = 0, apiCount = 0, uiCount = 0, appCount = 0
    allProjects.forEach(p => {
      if (p.modules) {
        p.modules.forEach(m => {
          if (m.module_type === 'AI') aiCount++
          if (m.module_type === 'AI_TEST') aiTestCount++
          if (m.module_type === 'API') apiCount++
          if (m.module_type === 'UI') uiCount++
          if (m.module_type === 'APP') appCount++
        })
      }
    })
    
    stats.value.totalProjects = aiCount + aiTestCount + apiCount + uiCount + appCount
    stats.value.aiProjects = aiCount
    stats.value.aiTestProjects = aiTestCount
    stats.value.apiProjects = apiCount
    stats.value.uiProjects = uiCount
    stats.value.appProjects = appCount
  } catch (error) {
    console.error('加载统计数据失败:', error)
  }
}

const handleSearch = () => {
  currentPage.value = 1
  loadProjects()
}

const handleFilter = () => {
  currentPage.value = 1
  loadProjects()
}

const handlePageChange = (page) => {
  currentPage.value = page
  loadProjects()
}

const getStatusType = (status) => {
  const typeMap = {
    not_started: 'info',
    active: 'success',
    paused: 'warning',
    completed: 'primary',
    archived: 'info'
  }
  return typeMap[status] || 'info'
}

const getStatusText = (status) => {
  const keyMap = {
    not_started: 'project.notStarted',
    active: 'project.active',
    paused: 'project.paused',
    completed: 'project.completed',
    archived: 'project.archived'
  }
  return t(keyMap[status] || status)
}

const getModuleLabel = (type) => {
  const keyMap = { AI: 'AI', AI_TEST: 'AI_TEST', API: 'API', UI: 'UI', APP: 'APP' }
  const key = keyMap[type]
  return key ? t(`unifiedProject.moduleTypes.${key}`) : type
}

const formatDate = (dateStr) => {
  return dayjs(dateStr).format('YYYY-MM-DD HH:mm')
}

const goToDetail = (id, name) => {
  router.push(`/configuration/meta-projects/${id}?name=${encodeURIComponent(name)}`)
}

const handleEdit = (row) => {
  isEdit.value = true
  currentProject.value = row
  dialogVisible.value = true
}

const handleDelete = async (id) => {
  try {
    await ElMessageBox.confirm(
      t('unifiedProject.messages.deleteConfirm'),
      t('common.warning'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    )
    await deleteMetaProject(id)
    ElMessage.success(t('unifiedProject.messages.deleteSuccess'))
    loadProjects()
    loadStats()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除项目失败:', error)
      ElMessage.error(t('unifiedProject.messages.deleteFailed'))
    }
  }
}

const handleDialogSuccess = () => {
  loadProjects()
  loadStats()
}

onMounted(() => {
  loadProjects()
  loadStats()

  const urlParams = new URLSearchParams(window.location.search)
  if (urlParams.get('action') === 'create') {
    handleCreate()
  }
})
</script>

<style scoped>
.dashboard-container {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.stats-row {
  margin-bottom: 20px;
}

.stats-row :deep(.el-col) {
  display: flex;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 88px;
  padding: 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.stat-icon.bg-blue { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.stat-icon.bg-cyan { background: linear-gradient(135deg, #00bcd4 0%, #80deea 100%); }
.stat-icon.bg-green { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
.stat-icon.bg-purple { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
.stat-icon.bg-orange { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }

.stat-info {
  flex: 1;
  min-width: 0;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #1a1a1a;
  line-height: 1.2;
}

.stat-label {
  font-size: 13px;
  color: #666;
  margin-top: 4px;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.list-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.loading,
.empty {
  padding: 40px 0;
}

.module-tag {
  margin-right: 4px;
}

.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
