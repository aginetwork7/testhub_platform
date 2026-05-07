<template>
  <div class="page-container">
    <div class="page-header">
      <el-button @click="goBack">
        <el-icon><Back /></el-icon>
        {{ $t('common.back') }}
      </el-button>
      <h1 class="page-title">{{ project?.name }}</h1>
      <el-button type="primary" @click="openEditDialog">
        <el-icon><Edit /></el-icon>
        {{ $t('common.edit') }}
      </el-button>
    </div>

    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="10" animated />
    </div>

    <div v-else-if="project" class="project-detail">
      <el-card class="basic-info-card">
        <template #header>
          <div class="card-header">
            <span>{{ $t('unifiedProject.basicInfo') }}</span>
          </div>
        </template>

        <el-descriptions bordered column="2">
          <el-descriptions-item :label="$t('unifiedProject.projectName')">
            {{ project.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('project.status')">
            <el-tag :type="getStatusType(project.status)">
              {{ getStatusText(project.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('unifiedProject.owner')">
            {{ project.owner_info?.username }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('unifiedProject.createdAt')">
            {{ formatDate(project.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('unifiedProject.description')" :span="2">
            {{ project.description || '-' }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card class="modules-card">
        <template #header>
          <div class="card-header">
            <span>{{ $t('unifiedProject.modules') }}</span>
          </div>
        </template>

        <div class="modules-list">
          <el-card
            v-for="module in project.modules"
            :key="module.id"
            class="module-card"
            shadow="hover"
          >
            <template #header>
              <div class="module-header">
                <span class="module-type">{{ getModuleLabel(module.module_type) }}</span>
                <ProjectJumpButton
                  :module-type="module.module_type"
                  :meta-project-id="project.id"
                  :child-project-id="module.child_project_id"
                />
              </div>
            </template>

            <el-descriptions column="1" border size="small">
              <el-descriptions-item
                v-for="([key, value]) in getSortedConfigEntries(module)"
                :key="key"
                :label="getConfigLabel(module.module_type, key)"
              >
                {{ formatConfigValue(key, value) }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </div>

        <div v-if="!project.modules?.length" class="empty-modules">
          <el-empty :description="$t('unifiedProject.noModules')" />
        </div>
      </el-card>
    </div>

    <UnifiedProjectDialog
      v-model:visible="dialogVisible"
      :is-edit="true"
      :project-data="project"
      @success="loadProjectDetail"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Back, Edit } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

import { getMetaProjectDetail } from '@/api/unified-projects'
import { getModuleLabel } from '@/utils/project-form-config'
import UnifiedProjectDialog from '@/components/project/UnifiedProjectDialog.vue'
import ProjectJumpButton from '@/components/project/ProjectJumpButton.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const loading = ref(false)
const project = ref(null)
const dialogVisible = ref(false)

const projectId = route.params.id

const loadProjectDetail = async () => {
  loading.value = true
  try {
    const response = await getMetaProjectDetail(projectId)
    project.value = response.data
    const queryName = route.query.name
    const nameStr = Array.isArray(queryName) ? queryName[0] : queryName
    if (nameStr) {
      sessionStorage.setItem('metaProjectName', decodeURIComponent(nameStr))
    }
  } catch (error) {
    ElMessage.error(t('unifiedProject.messages.fetchDetailFailed'))
    router.push('/configuration/project-center')
  } finally {
    loading.value = false
  }
}

const goBack = () => {
  sessionStorage.removeItem('metaProjectName')
  router.push('/configuration/project-center')
}

const openEditDialog = () => {
  dialogVisible.value = true
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

const getConfigLabel = (moduleType, key) => {
  const labels = {
    API: {
      base_url: '基础URL',
      timeout: '超时时间',
      retry_count: '重试次数'
    },
    UI: {
      base_url: '基础URL',
      browser: '浏览器',
      headless: '无头模式',
      viewport_width: '视口宽度',
      viewport_height: '视口高度'
    },
    APP: {
      platform: '平台',
      device_id: '设备ID',
      app_package: 'APP包名',
      app_activity: '启动Activity'
    },
    COMMON: {
      owner: '负责人',
      end_date: '结束日期',
      member_ids: '成员',
      start_date: '开始日期',
      project_type: '项目类型'
    }
  }
  return labels[moduleType]?.[key] || labels.COMMON?.[key] || key
}

const formatConfigValue = (key, value) => {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  if (typeof value === 'boolean') {
    return value ? '是' : '否'
  }
  if (Array.isArray(value)) {
    return value.length > 0 ? value.join(', ') : '-'
  }
  return String(value)
}

const configFieldOrder = {
  API: ['project_type', 'owner', 'member_ids', 'start_date', 'end_date', 'base_url', 'timeout', 'retry_count'],
  UI: ['base_url', 'browser', 'headless', 'viewport_width', 'viewport_height', 'start_date', 'end_date'],
  APP: ['platform', 'device_id', 'app_package', 'app_activity', 'start_date', 'end_date']
}

const getSortedConfigEntries = (module) => {
  const order = configFieldOrder[module.module_type] || []
  const config = module.config || {}
  const entries = Object.entries(config)
  return entries.sort((a, b) => {
    const indexA = order.indexOf(a[0])
    const indexB = order.indexOf(b[0])
    if (indexA === -1 && indexB === -1) return 0
    if (indexA === -1) return 1
    if (indexB === -1) return -1
    return indexA - indexB
  })
}

onMounted(() => {
  loadProjectDetail()
})
</script>

<style lang="scss" scoped>
.page-container {
  padding: 20px;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  flex: 1;
}

.loading-container {
  padding: 20px;
}

.project-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.card-header {
  font-weight: 600;
}

.modules-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 20px;
}

.module-card {
  .module-header {
    display: flex;
    justify-content: space-between;
    align-items: center;

    .module-type {
      font-weight: 600;
      font-size: 16px;
    }
  }
}

.empty-modules {
  padding: 40px 0;
}
</style>
