<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('unifiedProject.title') }}</h1>
      <el-button type="primary" @click="openCreateDialog">
        <el-icon><Plus /></el-icon>
        {{ $t('unifiedProject.createProject') }}
      </el-button>
    </div>

    <div class="card-container">
      <div class="filter-bar">
        <el-row :gutter="20">
          <el-col :span="6">
            <el-input
              v-model="searchText"
              :placeholder="$t('unifiedProject.searchPlaceholder')"
              clearable
              @input="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </el-col>
          <el-col :span="4">
            <el-select
              v-model="statusFilter"
              :placeholder="$t('unifiedProject.statusFilter')"
              clearable
              @change="handleFilter"
            >
              <el-option :label="$t('project.notStarted')" value="not_started" />
              <el-option :label="$t('project.active')" value="active" />
              <el-option :label="$t('project.paused')" value="paused" />
              <el-option :label="$t('project.completed')" value="completed" />
              <el-option :label="$t('project.archived')" value="archived" />
            </el-select>
          </el-col>
        </el-row>
      </div>

      <el-table :data="projects" v-loading="loading" style="width: 100%">
        <el-table-column prop="name" :label="$t('unifiedProject.projectName')" min-width="150" width="150">
          <template #default="{ row }">
            <el-link @click="goToDetail(row.id)" type="primary">
              {{ row.name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="description" :label="$t('unifiedProject.description')" min-width="300" show-overflow-tooltip />
        <el-table-column prop="status" :label="$t('project.status')" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ getStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('unifiedProject.modules')" min-width="200" width="250">
          <template #default="{ row }">
            <el-tag v-for="module in row.modules" :key="module.id" size="small" style="margin-right: 4px; margin-bottom: 4px;">
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
        <el-table-column :label="$t('unifiedProject.actions')" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="editProject(row)">{{ $t('common.edit') }}</el-button>
            <el-button size="small" type="danger" @click="deleteProject(row)">{{ $t('common.delete') }}</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>

    <UnifiedProjectDialog
      v-model="dialogVisible"
      :is-edit="isEdit"
      :project-data="currentProject"
      @success="loadProjects"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

import { getMetaProjects, deleteMetaProject } from '@/api/unified-projects'
import { getModuleLabel } from '@/utils/project-form-config'
import UnifiedProjectDialog from '@/components/project/UnifiedProjectDialog.vue'

const router = useRouter()
const { t } = useI18n()

const loading = ref(false)
const projects = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const searchText = ref('')
const statusFilter = ref('')

const dialogVisible = ref(false)
const isEdit = ref(false)
const currentProject = ref(null)

const fetchProjects = async () => {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value
    }
    if (searchText.value) params.search = searchText.value
    if (statusFilter.value) params.status = statusFilter.value

    const response = await getMetaProjects(params)
    projects.value = response.data.results
    total.value = response.data.count
  } catch (error) {
    ElMessage.error(t('unifiedProject.messages.fetchListFailed'))
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  currentPage.value = 1
  fetchProjects()
}

const handleFilter = () => {
  currentPage.value = 1
  fetchProjects()
}

const handleSizeChange = () => {
  fetchProjects()
}

const handleCurrentChange = () => {
  fetchProjects()
}

const goToDetail = (id) => {
  router.push(`/meta-projects/${id}`)
}

const openCreateDialog = () => {
  isEdit.value = false
  currentProject.value = null
  dialogVisible.value = true
}

const editProject = (project) => {
  isEdit.value = true
  currentProject.value = project
  dialogVisible.value = true
}

const deleteProject = async (project) => {
  try {
    await ElMessageBox.confirm(
      t('unifiedProject.messages.deleteConfirm'),
      t('common.warning'),
      { type: 'warning' }
    )
    await deleteMetaProject(project.id)
    ElMessage.success(t('unifiedProject.messages.deleteSuccess'))
    fetchProjects()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(t('unifiedProject.messages.deleteFailed'))
    }
  }
}

const getStatusType = (status) => {
  const typeMap = {
    not_started: 'info',
    active: 'success',
    paused: 'warning',
    completed: 'info',
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

const formatDate = (dateString) => {
  return dayjs(dateString).format('YYYY-MM-DD HH:mm')
}

onMounted(() => {
  loadProjects()
})

const loadProjects = () => {
  fetchProjects()
}

defineExpose({
  loadProjects
})
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 24px;
}

.card-container {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.filter-bar {
  margin-bottom: 20px;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
