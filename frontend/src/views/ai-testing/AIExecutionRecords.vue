<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('uiAutomation.ai.executionRecords.title') }}</h1>
      <div class="header-actions">
        <el-select v-model="projectId" placeholder="ALL" style="width: 220px; margin-right: 15px" @change="onProjectChange">
          <el-option v-for="project in projectOptions" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-button
          type="danger"
          :disabled="selectedRecords.length === 0"
          @click="batchDeleteRecords"
          :loading="isDeleting"
        >
          <el-icon><Delete /></el-icon>
          {{ $t('uiAutomation.common.batchDelete') }}
        </el-button>
        <el-button @click="openLearningDialog">
          学习指标
        </el-button>
      </div>
    </div>

    <div class="card-container">
      <el-table
        :data="records"
        v-loading="loading"
        style="width: 100%"
        @selection-change="handleSelectionChange"
        ref="tableRef"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column :label="$t('uiAutomation.ai.executionRecords.serialNumber')" width="80">
          <template #default="{ row }">
            {{ row.id }}
          </template>
        </el-table-column>
        <el-table-column prop="case_number" label="用例编号" width="130" show-overflow-tooltip />
        <el-table-column prop="case_name" :label="$t('uiAutomation.ai.executionRecords.caseName')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="project_name" label="项目" min-width="140" show-overflow-tooltip />

        <el-table-column prop="status" :label="$t('uiAutomation.ai.executionRecords.status')" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusTag(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="duration" :label="$t('uiAutomation.ai.executionRecords.durationSeconds')" width="120">
          <template #default="{ row }">
            {{ row.duration ? row.duration.toFixed(2) : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="start_time" :label="$t('uiAutomation.ai.executionRecords.startTime')" width="180" :formatter="formatDate" />
        <el-table-column prop="executed_by.username" :label="$t('uiAutomation.ai.executionRecords.executor')" width="120" />
        <el-table-column :label="$t('uiAutomation.common.operation')" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row)">
              {{ $t('uiAutomation.ai.executionRecords.viewDetail') }}
            </el-button>
            <el-button size="small" type="success" @click="viewReport(row)">
              {{ $t('uiAutomation.ai.executionRecords.viewReport') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.currentPage"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="showDetailDialog"
      :title="$t('uiAutomation.ai.executionRecords.executionDetail')"
      width="800px"
      @close="handleDetailDialogClose"
    >
      <div v-if="currentRecord" class="record-detail">
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.ai.executionRecords.caseName') }}:</span>
          <span class="value">{{ currentRecord.case_name }}</span>
        </div>

        <div class="detail-item">
          <span class="label">执行模式:</span>
          <el-tag :type="getExecutionModeTag(currentRecord.execution_mode)">
            {{ getExecutionModeText(currentRecord.execution_mode) }}
          </el-tag>
        </div>

        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.ai.executionRecords.status') }}:</span>
          <el-tag :type="getStatusTag(currentRecord.status)">
            {{ getStatusText(currentRecord.status) }}
          </el-tag>
        </div>
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.ai.executionRecords.startTime') }}:</span>
          <span>{{ formatDate(null, null, currentRecord.start_time) }}</span>
        </div>
        <div class="detail-item">
          <span class="label">{{ $t('uiAutomation.ai.executionRecords.duration') }}:</span>
          <span>{{ currentRecord.duration ? currentRecord.duration.toFixed(2) + ' ' + $t('uiAutomation.ai.executionRecords.seconds') : $t('uiAutomation.ai.executionRecords.unknown') }}</span>
        </div>

        <!-- 任务描述 -->
        <div v-if="currentRecord.task_description" class="detail-item mt-15">
          <span class="label">{{ $t('uiAutomation.ai.executionRecords.taskDescription') }}:</span>
        </div>
        <div v-if="currentRecord.task_description" class="task-description-container">
          <div class="task-description-content">{{ currentRecord.task_description }}</div>
        </div>

        <!-- 执行日志 -->
        <div class="detail-item mt-15">
          <span class="label">{{ $t('uiAutomation.ai.executionRecords.executionLogs') }}:</span>
        </div>
        <div class="log-container">
          <pre>{{ currentRecord.logs }}</pre>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button type="success" @click="openReportFromDetail">{{ $t('uiAutomation.ai.executionRecords.viewReport') }}</el-button>
          <el-button @click="showDetailDialog = false">{{ $t('uiAutomation.common.close') }}</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 报告对话框 -->
    <AIExecutionReport
      v-model="showReportDialog"
      :record-id="reportRecordId"
    />

    <el-dialog v-model="showLearningDialog" title="AI 学习指标与经验审核" width="960px">
      <el-descriptions v-if="learningMetrics" :column="3" border>
        <el-descriptions-item label="首跑通过率">
          {{ formatRate(learningMetrics.executions.first_run_pass_rate) }}
        </el-descriptions-item>
        <el-descriptions-item label="经验命中">
          {{ learningMetrics.learning.experience_hits }}
        </el-descriptions-item>
        <el-descriptions-item label="有效经验">
          {{ learningMetrics.learning.experience_confirmed }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="learning-toolbar">
        <el-radio-group v-model="experienceStatus" @change="loadLearningData">
          <el-radio-button value="pending">待定</el-radio-button>
          <el-radio-button value="verified">有效</el-radio-button>
        </el-radio-group>
        <el-button type="danger" :disabled="experiences.length === 0" @click="clearExperiences">
          清空
        </el-button>
      </div>

      <el-table v-loading="learningLoading" :data="experiences" style="margin-top: 16px">
        <el-table-column prop="step_description" label="步骤" min-width="260" show-overflow-tooltip />
        <el-table-column prop="environment_key" label="环境" min-width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.review_status === 'confirmed' ? 'success' : 'warning'">
              {{ row.review_status === 'confirmed' ? '有效' : '待定' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="success_count" label="成功次数" width="100" />
        <el-table-column label="审核" width="110">
          <template #default="{ row }">
            <el-tag :type="row.review_status === 'confirmed' ? 'success' : 'info'">
              {{ row.review_status === 'confirmed' ? '已确认' : '待确认' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-tooltip v-if="row.review_status !== 'confirmed'" content="确认经验" placement="top">
              <el-button circle type="success" :icon="Check" @click="confirmExperience(row)" />
            </el-tooltip>
            <el-tooltip content="删除经验" placement="top">
              <el-button circle type="danger" :icon="Delete" @click="deleteExperience(row)" />
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Delete } from '@element-plus/icons-vue'
import { batchDeleteAIExecutionRecords, clearAIExecutionExperiences, confirmAIExecutionExperience, deleteAIExecutionExperience, getAIExecutionExperiences, getAIExecutionRecord, getAIExecutionRecords, getAILearningMetrics, getAiProjects } from '@/api/ai-testing'
import AIExecutionReport from './AIExecutionReport.vue'

const { t } = useI18n()
const projects = ref([])
const ALL_PROJECT_VALUE = '__ALL__'
const UNARCHIVED_PROJECT_VALUE = '__UNARCHIVED__'
const projectId = ref(ALL_PROJECT_VALUE)
const records = ref([])
const loading = ref(false)
const total = ref(0)
const pagination = reactive({
  currentPage: 1,
  pageSize: 20
})

const showDetailDialog = ref(false)
const currentRecord = ref(null)
let pollTimer = null
let detailPollTimer = null

const selectedRecords = ref([])
const isDeleting = ref(false)
const tableRef = ref(null)

// 报告相关状态
const showReportDialog = ref(false)
const reportRecordId = ref(null)
const showLearningDialog = ref(false)
const learningMetrics = ref(null)
const learningLoading = ref(false)
const experiences = ref([])
const experienceStatus = ref('pending')

const projectOptions = computed(() => [
  { id: ALL_PROJECT_VALUE, name: 'ALL' },
  { id: UNARCHIVED_PROJECT_VALUE, name: '未归档' },
  ...projects.value,
])

// 加载项目列表
const loadProjects = async () => {
  try {
    const response = await getAiProjects({ page_size: 100 })
    projects.value = response.data.results || response.data
  } catch (error) {
    ElMessage.error('获取项目列表失败')
    console.error('获取项目列表失败:', error)
  }
}

const onProjectChange = () => {
  pagination.currentPage = 1
  loadRecords()
}

const buildRecordQueryParams = () => {
  if (projectId.value === UNARCHIVED_PROJECT_VALUE) {
    return { project_scope: 'unarchived' }
  }

  if (projectId.value && projectId.value !== ALL_PROJECT_VALUE) {
    return { project: projectId.value }
  }

  return {}
}

// 加载记录列表
const loadRecords = async () => {
  loading.value = true
  try {
    const response = await getAIExecutionRecords({
      ...buildRecordQueryParams(),
      page: pagination.currentPage,
      page_size: pagination.pageSize
    })

    records.value = response.data.results || []
    total.value = response.data.count || 0
    // 清空选择
    if (tableRef.value) {
      tableRef.value.clearSelection()
    }
  } catch (error) {
    console.error('获取执行记录失败:', error)
    ElMessage.error(t('uiAutomation.ai.executionRecords.messages.loadFailed'))
  } finally {
    loading.value = false
  }
}

const handleSizeChange = () => {
  pagination.currentPage = 1
  loadRecords()
}

const handleCurrentChange = () => {
  loadRecords()
}

const syncRecordInList = (record) => {
  const index = records.value.findIndex(item => item.id === record.id)
  if (index >= 0) {
    records.value[index] = {
      ...records.value[index],
      ...record
    }
  }
}

const loadRecordDetail = async (recordId, { silent = false } = {}) => {
  try {
    const response = await getAIExecutionRecord(recordId)
    const record = response.data
    currentRecord.value = record
    syncRecordInList(record)
    return record
  } catch (error) {
    if (!silent) {
      console.error('获取执行记录详情失败:', error)
      ElMessage.error(t('uiAutomation.ai.executionRecords.messages.loadFailed'))
    }
    return null
  }
}

const stopDetailPolling = () => {
  if (detailPollTimer) {
    clearInterval(detailPollTimer)
    detailPollTimer = null
  }
}

const startDetailPolling = () => {
  stopDetailPolling()

  detailPollTimer = setInterval(async () => {
    if (!showDetailDialog.value || !currentRecord.value?.id) {
      stopDetailPolling()
      return
    }

    const status = currentRecord.value.status
    if (status !== 'running' && status !== 'pending') {
      stopDetailPolling()
      return
    }

    await loadRecordDetail(currentRecord.value.id, { silent: true })
  }, 3000)
}

const viewDetail = async (row) => {
  currentRecord.value = row
  showDetailDialog.value = true
  await loadRecordDetail(row.id, { silent: true })
  startDetailPolling()
}

const handleDetailDialogClose = () => {
  stopDetailPolling()
}

// 查看报告
const viewReport = (row) => {
  reportRecordId.value = row.id
  showReportDialog.value = true
}

// 从详情页打开报告
const openReportFromDetail = () => {
  if (currentRecord.value) {
    reportRecordId.value = currentRecord.value.id
    showReportDialog.value = true
  }
}

const formatRate = (value) => `${((Number(value) || 0) * 100).toFixed(1)}%`

const learningQueryParams = () => {
  if (projectId.value && projectId.value !== ALL_PROJECT_VALUE && projectId.value !== UNARCHIVED_PROJECT_VALUE) {
    return { project: projectId.value }
  }
  return {}
}

const loadLearningData = async () => {
  learningLoading.value = true
  try {
    const params = learningQueryParams()
    const [metricsResponse, experiencesResponse] = await Promise.all([
      getAILearningMetrics(params),
      getAIExecutionExperiences({ ...params, review_scope: experienceStatus.value, page_size: 100 })
    ])
    learningMetrics.value = metricsResponse.data
    experiences.value = experiencesResponse.data.results || experiencesResponse.data
  } catch (error) {
    console.error('获取 AI 学习数据失败:', error)
    ElMessage.error('获取 AI 学习数据失败')
  } finally {
    learningLoading.value = false
  }
}

const openLearningDialog = async () => {
  showLearningDialog.value = true
  await loadLearningData()
}

const confirmExperience = async (experience) => {
  try {
    await confirmAIExecutionExperience(experience.id)
    ElMessage.success('经验已确认')
    await loadLearningData()
  } catch (error) {
    console.error('确认 AI 经验失败:', error)
    ElMessage.error('确认 AI 经验失败')
  }
}

const deleteExperience = async (experience) => {
  try {
    await ElMessageBox.confirm('删除后无法恢复该经验。', '删除经验', {
      confirmButtonText: '确认删除',
      cancelButtonText: t('uiAutomation.common.cancel'),
      type: 'warning'
    })
    await deleteAIExecutionExperience(experience.id)
    ElMessage.success('经验已删除')
    await loadLearningData()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除 AI 经验失败:', error)
      ElMessage.error('删除 AI 经验失败')
    }
  }
}

const clearExperiences = async () => {
  try {
    await ElMessageBox.confirm(`确认清空当前页面的${experienceStatus.value === 'pending' ? '待定' : '有效'}经验？`, '清空经验', {
      confirmButtonText: '确认清空',
      cancelButtonText: t('uiAutomation.common.cancel'),
      type: 'warning'
    })
    await clearAIExecutionExperiences({ ...learningQueryParams(), review_scope: experienceStatus.value })
    ElMessage.success('当前页面经验已清空')
    await loadLearningData()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('清空 AI 经验失败:', error)
      ElMessage.error('清空 AI 经验失败')
    }
  }
}

const getStatusTag = (status) => {
  const map = {
    'pending': 'info',
    'running': 'warning',
    'passed': 'success',
    'failed': 'danger',
    'stopped': 'warning'
  }
  return map[status] || 'info'
}

const getStatusText = (status) => {
  const map = {
    'pending': t('uiAutomation.status.pending'),
    'running': t('uiAutomation.status.running'),
    'passed': t('uiAutomation.status.success'),
    'failed': t('uiAutomation.status.failed'),
    'stopped': t('uiAutomation.status.stopped')
  }
  return map[status] || status
}

const getExecutionModeText = (executionMode) => {
  if (executionMode === 'hermes') {
    return t('uiAutomation.ai.executionRecords.hermesMode')
  }
  if (executionMode === 'planner_v2') {
    return t('uiAutomation.ai.executionRecords.plannerV2Mode')
  }
  return t('uiAutomation.ai.executionRecords.browserMode')
}

const getExecutionModeTag = (executionMode) => {
  if (executionMode === 'hermes') {
    return 'success'
  }
  if (executionMode === 'planner_v2') {
    return 'warning'
  }
  return 'info'
}

const formatDate = (row, column, cellValue) => {
  if (!cellValue) return ''
  return new Date(cellValue).toLocaleString()
}

// 处理选择变化
const handleSelectionChange = (selection) => {
  selectedRecords.value = selection
}

// 批量删除
const batchDeleteRecords = async () => {
  if (selectedRecords.value.length === 0) return

  try {
    await ElMessageBox.confirm(
      t('uiAutomation.ai.executionRecords.messages.batchDeleteConfirm', { count: selectedRecords.value.length }),
      t('uiAutomation.ai.executionRecords.messages.batchDeleteTitle'),
      {
        confirmButtonText: t('uiAutomation.common.confirm'),
        cancelButtonText: t('uiAutomation.common.cancel'),
        type: 'warning'
      }
    )

    isDeleting.value = true
    const ids = selectedRecords.value.map(item => item.id)
    await batchDeleteAIExecutionRecords(ids)

    ElMessage.success(t('uiAutomation.ai.executionRecords.messages.deleteSuccess'))

    // 如果当前页数据全部被删除，且不是第一页，则跳转到上一页
    if (records.value.length === ids.length && pagination.currentPage > 1) {
      pagination.currentPage--
    }

    loadRecords()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('批量删除失败:', error)
      ElMessage.error(t('uiAutomation.ai.executionRecords.messages.batchDeleteFailed'))
    }
  } finally {
    isDeleting.value = false
  }
}



// 轮询更新状态
const startPolling = () => {
  pollTimer = setInterval(() => {
    // 只有在第一页且没有打开详情框且没有正在加载时才轮询
    if (pagination.currentPage === 1 && !showDetailDialog.value && !loading.value) {
      // 优化：检查当前列表是否有正在运行的任务，如果没有运行中的任务，则不轮询（或者降低频率）
      const hasActiveTasks = records.value.some(r => r.status === 'running' || r.status === 'pending')
      if (!hasActiveTasks) {
        return
      }

      // 静默刷新，不显示 loading
      getAIExecutionRecords({
        ...buildRecordQueryParams(),
        page: 1,
        page_size: pagination.pageSize
      }).then(response => {
        // 只有当没有选中项时才更新列表，避免干扰用户选择
        if (selectedRecords.value.length === 0) {
          records.value = response.data.results || []
          total.value = response.data.count || 0
        }
      }).catch(console.error)
    }
  }, 5000)
}

onMounted(async () => {
  await loadProjects()
  loadRecords()
  startPolling()
})

onUnmounted(() => {
  stopDetailPolling()
  if (pollTimer) {
    clearInterval(pollTimer)
  }
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

  .page-title {
    font-size: 20px;
    font-weight: 600;
    margin: 0;
  }

  .header-actions {
    display: flex;
    align-items: center;
  }
}

.card-container {
  background-color: #fff;
  border-radius: 4px;
  padding: 20px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.record-detail {
  .detail-item {
    margin-bottom: 15px;
    .label {
      font-weight: bold;
      margin-right: 10px;
    }
  }

  .log-container {
    background-color: #1e1e1e;
    color: #fff;
    padding: 15px;
    border-radius: 4px;
    max-height: 400px;
    overflow-y: auto;
    font-family: monospace;

    pre {
      margin: 0;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
  }

  .task-description-container {
    background-color: #f5f7fa;
    border: 1px solid #e4e7ed;
    border-radius: 4px;
    padding: 12px 15px;
    margin-top: 8px;

    .task-description-content {
      color: #606266;
      line-height: 1.6;
      white-space: pre-wrap;
      word-wrap: break-word;
    }
  }
}

.mt-15 {
  margin-top: 15px;
}

.learning-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
}
</style>
