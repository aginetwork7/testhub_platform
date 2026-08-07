<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('uiAutomation.ai.caseList.title') }}</h1>
      <div class="header-actions">
        <el-button type="primary" style="margin-right: 15px" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          {{ $t('uiAutomation.ai.caseList.newCase') }}
        </el-button>
        <el-select v-model="projectId" :placeholder="$t('uiAutomation.project.selectProject')" style="width: 200px; margin-right: 15px" @change="onProjectChange">
          <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-select v-model="executionMode" :placeholder="$t('uiAutomation.ai.caseList.executionBackend')" style="width: 140px;">
          <el-option :label="$t('uiAutomation.ai.backends.browser')" value="text" />
          <el-option :label="$t('uiAutomation.ai.backends.plannerV2')" value="planner_v2" />
        </el-select>
        <el-switch
          v-model="disableCache"
          class="cache-switch"
          :active-text="$t('uiAutomation.ai.caseList.disableCache')"
        />
      </div>
    </div>

    <div class="card-container">
      <div class="filter-bar">
        <el-input
          v-model="searchText"
          :placeholder="$t('uiAutomation.ai.caseList.searchPlaceholder')"
          clearable
          @input="handleSearch"
          style="width: 300px;"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="success" :disabled="selectedCases.length === 0" @click="openBatchRunDialog">
          <el-icon><VideoPlay /></el-icon>
          批量执行 ({{ selectedCases.length }})
        </el-button>
      </div>

      <el-table :data="cases" v-loading="loading" style="width: 100%" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="name" :label="$t('uiAutomation.ai.caseList.caseName')" min-width="200" show-overflow-tooltip />
        <el-table-column :label="$t('uiAutomation.ai.caseMode')" width="140">
          <template #default="{ row }">
            <el-tag :type="getCaseModeTag(row.case_mode)">
              {{ getCaseModeText(row.case_mode) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('uiAutomation.ai.caseList.taskDescription')" min-width="340">
          <template #default="{ row }">
            <div class="task-description-cell">
              <div
                class="task-description-text"
                :class="{ expanded: isTaskDescriptionExpanded(row.id) }"
              >
                {{ row.task_description || '-' }}
              </div>
              <el-button
                v-if="shouldShowTaskDescriptionToggle(row.task_description)"
                link
                type="primary"
                class="task-description-toggle"
                @click="toggleTaskDescription(row.id)"
              >
                {{ isTaskDescriptionExpanded(row.id)
                  ? $t('uiAutomation.ai.caseList.collapseTaskDescription')
                  : $t('uiAutomation.ai.caseList.expandTaskDescription') }}
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="执行步骤" min-width="280">
          <template #default="{ row }">
            <div class="task-description-cell">
              <div class="task-description-text" :class="{ expanded: isTaskDescriptionExpanded(`planned-${row.id}`) }">
                {{ formatPlannedSteps(row.planned_steps) || '-' }}
              </div>
              <el-button
                v-if="shouldShowTaskDescriptionToggle(formatPlannedSteps(row.planned_steps))"
                link
                type="primary"
                class="task-description-toggle"
                @click="toggleTaskDescription(`planned-${row.id}`)"
              >
                {{ isTaskDescriptionExpanded(`planned-${row.id}`) ? $t('uiAutomation.ai.caseList.collapseTaskDescription') : $t('uiAutomation.ai.caseList.expandTaskDescription') }}
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('uiAutomation.common.createTime')" width="180" :formatter="formatDate" />
        <el-table-column :label="$t('uiAutomation.common.operation')" width="140" fixed="right">
          <template #default="{ row }">
            <div class="action-buttons">
              <el-tooltip :content="$t('uiAutomation.common.run')" placement="top">
                <el-button circle size="small" type="success" @click="runCase(row)">
                  <el-icon><VideoPlay /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip :content="$t('uiAutomation.common.edit')" placement="top">
                <el-button circle size="small" type="primary" @click="editCase(row)">
                  <el-icon><Edit /></el-icon>
                </el-button>
              </el-tooltip>
              <el-tooltip :content="$t('uiAutomation.common.delete')" placement="top">
                <el-button circle size="small" type="danger" @click="deleteCase(row.id)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </el-tooltip>
            </div>
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

    <el-dialog v-model="showRunDialog" title="执行用例" width="480px" :close-on-click-modal="false">
      <el-form label-width="100px">
        <el-form-item label="待执行用例">
          <span>已选择 {{ runTargetCases.length }} 个用例</span>
        </el-form-item>
        <el-form-item label="运行环境">
          <el-select v-model="executionEnvironmentId" clearable placeholder="使用用例或默认环境" style="width: 100%">
            <el-option
              v-for="configuration in automationConfigurations"
              :key="configuration.id"
              :label="formatEnvironmentLabel(configuration)"
              :value="configuration.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRunDialog = false">{{ $t('uiAutomation.common.cancel') }}</el-button>
        <el-button type="primary" :loading="submittingRun" @click="confirmRun">执行</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="showEditDialog" :title="dialogTitle" width="720px" :close-on-click-modal="false">
      <el-form :model="editForm" :rules="formRules" ref="editFormRef" label-width="100px">
        <el-form-item :label="$t('uiAutomation.ai.caseList.caseName')" prop="name">
          <el-input v-model="editForm.name" :placeholder="$t('uiAutomation.ai.caseNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.common.description')" prop="description">
          <el-input v-model="editForm.description" type="textarea" :placeholder="$t('uiAutomation.ai.caseDescPlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.ai.caseMode')" prop="case_mode">
          <el-select v-model="editForm.case_mode" style="width: 220px;">
            <el-option :label="$t('uiAutomation.ai.caseModes.freeform')" value="freeform" />
            <el-option :label="$t('uiAutomation.ai.caseModes.hybrid')" value="hybrid" />
            <el-option :label="$t('uiAutomation.ai.caseModes.structured')" value="structured" />
          </el-select>
          <span class="case-mode-tip">
            {{ caseModeTipText }}
          </span>
        </el-form-item>
        <el-form-item v-if="editForm.case_mode === 'freeform'" :label="$t('uiAutomation.ai.caseList.taskDescription')" prop="task_description">
          <el-input
            v-model="editForm.task_description"
            type="textarea"
            :rows="6"
            :placeholder="$t('uiAutomation.ai.taskPlaceholder')"
          />
        </el-form-item>
        <el-form-item v-if="editForm.case_mode === 'freeform'" label="执行步骤">
          <div class="planned-steps-editor">
            <div v-for="(step, index) in editForm.planned_steps" :key="step.id || index" class="planned-step-row">
              <span class="planned-step-number">{{ index + 1 }}</span>
              <el-select v-model="step.step_mode" class="planned-step-mode">
                <el-option :label="$t('uiAutomation.ai.stepModes.ai')" value="ai" />
                <el-option :label="$t('uiAutomation.ai.stepModes.direct')" value="direct" />
              </el-select>
              <el-input v-model="step.description" type="textarea" :rows="2" placeholder="执行步骤描述" />
              <el-button text type="danger" @click="removePlannedStep(index)"><el-icon><Delete /></el-icon></el-button>
            </div>
            <el-button plain type="primary" @click="addPlannedStep"><el-icon><Plus /></el-icon>新增执行步骤</el-button>
          </div>
        </el-form-item>
        <el-form-item v-else :label="stepsSectionTitle" prop="task_steps">
          <div class="structured-steps">
            <div v-for="(step, index) in editForm.task_steps" :key="index" class="structured-step-card">
              <div class="structured-step-header">
                <span>{{ $t('uiAutomation.ai.structuredStep') }} {{ index + 1 }}</span>
                <el-button text type="danger" @click="removeStructuredStep(index)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>

              <div v-if="editForm.case_mode === 'hybrid'" class="structured-step-grid hybrid-meta-grid">
                <el-select v-model="step.step_mode">
                  <el-option :label="$t('uiAutomation.ai.stepModes.ai')" value="ai" />
                  <el-option :label="$t('uiAutomation.ai.stepModes.direct')" value="direct" />
                </el-select>
                <el-input-number v-model="step.timeout_ms" :min="1000" :step="1000" :controls="false" />
              </div>

              <div v-if="editForm.case_mode === 'hybrid' && step.step_mode === 'ai'" class="structured-step-grid single-line">
                <el-input v-model="step.description" type="textarea" :rows="3" :placeholder="$t('uiAutomation.ai.aiStepPlaceholder')" />
              </div>

              <template v-else>
                <div class="structured-step-grid">
                  <el-input v-model="step.description" :placeholder="$t('uiAutomation.ai.stepDescriptionPlaceholder')" />
                  <el-select v-model="step.action">
                    <el-option v-for="option in stepActionOptions" :key="option.value" :label="option.label" :value="option.value" />
                  </el-select>
                  <el-input-number v-model="step.timeout_ms" :min="1000" :step="1000" :controls="false" />
                </div>

              <div v-if="step.action === 'navigate'" class="structured-step-grid single-line">
                <el-input v-model="step.url" :placeholder="$t('uiAutomation.ai.stepUrlPlaceholder')" />
              </div>

              <div v-else-if="step.action === 'click'" class="structured-step-grid single-line">
                <el-input v-model="step.selector" :placeholder="$t('uiAutomation.ai.stepSelectorPlaceholder')" />
              </div>

              <div v-else-if="['fill', 'press', 'select'].includes(step.action)" class="structured-step-grid">
                <el-input v-model="step.selector" :placeholder="$t('uiAutomation.ai.stepSelectorPlaceholder')" />
                <el-input v-model="step.value" :placeholder="$t('uiAutomation.ai.stepValuePlaceholder')" />
              </div>

              <div v-else-if="step.action === 'assert_url_contains'" class="structured-step-grid single-line">
                <el-input v-model="step.expected" :placeholder="$t('uiAutomation.ai.stepExpectedPlaceholder')" />
              </div>

              <div v-else-if="step.action === 'assert_text_contains'" class="structured-step-grid">
                <el-input v-model="step.selector" :placeholder="$t('uiAutomation.ai.stepSelectorPlaceholder')" />
                <el-input v-model="step.expected" :placeholder="$t('uiAutomation.ai.stepExpectedPlaceholder')" />
              </div>
              </template>
            </div>

            <div class="structured-actions">
              <el-button plain type="primary" class="structured-add-btn" @click="addStructuredStep()">
                <el-icon><Plus /></el-icon>
                {{ $t('uiAutomation.ai.addStructuredStep') }}
              </el-button>

              <el-button v-if="editForm.case_mode === 'hybrid'" plain type="success" class="structured-add-btn" @click="addStructuredStep('direct')">
                <el-icon><Plus /></el-icon>
                {{ $t('uiAutomation.ai.addDirectStep') }}
              </el-button>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showEditDialog = false">{{ $t('uiAutomation.common.cancel') }}</el-button>
          <el-button type="primary" @click="confirmEdit" :loading="saving">{{ $t('uiAutomation.common.save') }}</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, VideoPlay, Edit, Delete, Plus } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { getAICases, createAICase, updateAICase, deleteAICase, executeAICase, batchExecuteAICases, getAiProjects } from '@/api/ai-testing'
import { getAutomationConfigurations } from '@/api/api-automation'

const { t } = useI18n()
const router = useRouter()
const projects = ref([])
const projectId = ref('')
const cases = ref([])
const loading = ref(false)
const searchText = ref('')
const executionMode = ref('planner_v2')
const disableCache = ref(false)
const selectedCases = ref([])
const runTargetCases = ref([])
const showRunDialog = ref(false)
const submittingRun = ref(false)
const automationConfigurations = ref([])
const executionEnvironmentId = ref(null)
const total = ref(0)
const pagination = reactive({
  currentPage: 1,
  pageSize: 20
})

const showEditDialog = ref(false)
const saving = ref(false)
const currentCaseId = ref(null)
const isCreateMode = ref(false)
const expandedTaskDescriptionIds = ref([])

const createStructuredStep = (stepMode = 'ai') => ({
  step_mode: stepMode,
  action: 'navigate',
  description: '',
  url: '',
  selector: '',
  value: '',
  expected: '',
  timeout_ms: 10000
})

const editForm = reactive({
  name: '',
  description: '',
  task_description: '',
  case_mode: 'freeform',
  planned_steps: [],
  task_steps: [createStructuredStep()]
})
const editFormRef = ref(null)

const stepActionOptions = computed(() => [
  { label: t('uiAutomation.ai.stepActions.navigate'), value: 'navigate' },
  { label: t('uiAutomation.ai.stepActions.click'), value: 'click' },
  { label: t('uiAutomation.ai.stepActions.fill'), value: 'fill' },
  { label: t('uiAutomation.ai.stepActions.press'), value: 'press' },
  { label: t('uiAutomation.ai.stepActions.select'), value: 'select' },
  { label: t('uiAutomation.ai.stepActions.wait'), value: 'wait' },
  { label: t('uiAutomation.ai.stepActions.assertUrlContains'), value: 'assert_url_contains' },
  { label: t('uiAutomation.ai.stepActions.assertTextContains'), value: 'assert_text_contains' }
])

const dialogTitle = computed(() => isCreateMode.value ? t('uiAutomation.ai.caseList.createCase') : t('uiAutomation.ai.caseList.editCase'))

const stepsSectionTitle = computed(() => editForm.case_mode === 'hybrid'
  ? t('uiAutomation.ai.hybridSteps')
  : t('uiAutomation.ai.structuredSteps'))

const caseModeTipText = computed(() => {
  if (editForm.case_mode === 'hybrid') {
    return t('uiAutomation.ai.hybridCaseModeTip')
  }
  return t('uiAutomation.ai.caseModeTip')
})

const formRules = computed(() => ({
  name: [{ required: true, message: t('uiAutomation.ai.rules.nameRequired'), trigger: 'blur' }],
  task_description: [{
    validator: (_rule, value, callback) => {
      if (editForm.case_mode === 'freeform' && !String(value || '').trim()) {
        callback(new Error(t('uiAutomation.ai.caseList.rules.taskDescriptionRequired')))
        return
      }
      callback()
    },
    trigger: 'blur'
  }]
}))

watch(
  () => editForm.case_mode,
  (mode) => {
    if (mode === 'structured' && editForm.task_steps.length === 0) {
      editForm.task_steps.push(createStructuredStep())
    }
  }
)

const normalizeStructuredStep = (step = {}, index = 0) => ({
  step_mode: step.step_mode || (editForm.case_mode === 'hybrid' ? 'ai' : 'direct'),
  action: step.action || 'navigate',
  description: step.description || '',
  url: step.url || '',
  selector: step.selector || '',
  value: step.value || '',
  expected: step.expected || '',
  timeout_ms: Number(step.timeout_ms) || 10000,
  step_no: Number(step.step_no) || index + 1
})

const buildTaskStepsPayload = () => editForm.task_steps.map((step, index) => ({
  ...normalizeStructuredStep(step, index),
  step_no: index + 1
}))

const buildTaskDescriptionFromSteps = (taskSteps) => taskSteps.map((step, index) => {
  const prefix = step.step_mode === 'direct' ? '[DIRECT]' : '[AI]'
  return `${index + 1}. ${prefix} ${step.description || ''}`.trim()
}).join('\n')

const addStructuredStep = (stepMode = null) => {
  const fallbackMode = editForm.case_mode === 'hybrid' ? 'ai' : 'direct'
  editForm.task_steps.push(createStructuredStep(stepMode || fallbackMode))
}

const removeStructuredStep = (index) => {
  if (editForm.task_steps.length === 1) {
    editForm.task_steps.splice(0, 1, createStructuredStep(editForm.case_mode === 'hybrid' ? 'ai' : 'direct'))
    return
  }
  editForm.task_steps.splice(index, 1)
}

const addPlannedStep = () => {
  editForm.planned_steps.push({
    id: editForm.planned_steps.length + 1,
    executor: 'browser',
    step_mode: 'ai',
    description: ''
  })
}

const removePlannedStep = (index) => {
  editForm.planned_steps.splice(index, 1)
}

const validateStructuredSteps = () => {
  if (!Array.isArray(editForm.task_steps) || editForm.task_steps.length === 0) {
    ElMessage.error(t('uiAutomation.ai.messages.structuredStepsRequired'))
    return false
  }

  for (const [index, step] of editForm.task_steps.entries()) {
    const label = `${t('uiAutomation.ai.structuredStep')} ${index + 1}`
    if (!String(step.description || '').trim()) {
      ElMessage.error(`${label}: ${t('uiAutomation.ai.messages.stepDescriptionRequired')}`)
      return false
    }
    if (editForm.case_mode === 'hybrid' && step.step_mode === 'ai') {
      continue
    }
    if (!String(step.action || '').trim()) {
      ElMessage.error(`${label}: ${t('uiAutomation.ai.messages.stepActionRequired')}`)
      return false
    }
    if (step.action === 'navigate' && !String(step.url || '').trim()) {
      ElMessage.error(`${label}: ${t('uiAutomation.ai.messages.stepUrlRequired')}`)
      return false
    }
    if (['click', 'fill', 'press', 'select', 'assert_text_contains'].includes(step.action) && !String(step.selector || '').trim()) {
      ElMessage.error(`${label}: ${t('uiAutomation.ai.messages.stepSelectorRequired')}`)
      return false
    }
    if (['fill', 'press', 'select'].includes(step.action) && !String(step.value || '').trim()) {
      ElMessage.error(`${label}: ${t('uiAutomation.ai.messages.stepValueRequired')}`)
      return false
    }
    if (['assert_url_contains', 'assert_text_contains'].includes(step.action) && !String(step.expected || '').trim()) {
      ElMessage.error(`${label}: ${t('uiAutomation.ai.messages.stepExpectedRequired')}`)
      return false
    }
  }

  return true
}

const resetEditForm = () => {
  currentCaseId.value = null
  editForm.name = ''
  editForm.description = ''
  editForm.task_description = ''
  editForm.case_mode = 'freeform'
  editForm.planned_steps = []
  editForm.task_steps = [createStructuredStep('ai')]
}

const openCreateDialog = () => {
  isCreateMode.value = true
  resetEditForm()
  showEditDialog.value = true
}

const getCaseModeText = (caseMode) => {
  if (caseMode === 'hybrid') {
    return t('uiAutomation.ai.caseModes.hybrid')
  }
  if (caseMode === 'structured') {
    return t('uiAutomation.ai.caseModes.structured')
  }
  return t('uiAutomation.ai.caseModes.freeform')
}

const getCaseModeTag = (caseMode) => {
  if (caseMode === 'hybrid') {
    return 'success'
  }
  if (caseMode === 'structured') {
    return 'warning'
  }
  return 'info'
}

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
  selectedCases.value = []
  loadCases()
}

// 加载用例列表
const loadCases = async () => {
  if (!projectId.value) {
    cases.value = []
    selectedCases.value = []
    total.value = 0
    return
  }

  loading.value = true
  selectedCases.value = []
  try {
    const response = await getAICases({
      project: projectId.value,
      page: pagination.currentPage,
      page_size: pagination.pageSize,
      search: searchText.value
    })

    cases.value = response.data.results || []
    total.value = response.data.count || 0
  } catch (error) {
    console.error('获取用例列表失败:', error)
    ElMessage.error(t('uiAutomation.ai.caseList.messages.loadFailed'))
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.currentPage = 1
  loadCases()
}

const shouldShowTaskDescriptionToggle = (text) => String(text || '').trim().length > 90

const formatPlannedSteps = (steps) => {
  if (!Array.isArray(steps)) return ''
  return steps.map((step, index) => `${index + 1}. ${step.description || step.name || step}`).join('\n')
}

const isTaskDescriptionExpanded = (caseId) => expandedTaskDescriptionIds.value.includes(caseId)

const toggleTaskDescription = (caseId) => {
  if (isTaskDescriptionExpanded(caseId)) {
    expandedTaskDescriptionIds.value = expandedTaskDescriptionIds.value.filter((id) => id !== caseId)
    return
  }
  expandedTaskDescriptionIds.value = [...expandedTaskDescriptionIds.value, caseId]
}

const handleSizeChange = () => {
  pagination.currentPage = 1
  loadCases()
}

const handleCurrentChange = () => {
  loadCases()
}

const handleSelectionChange = (rows) => {
  selectedCases.value = rows
}

const loadAutomationConfigurations = async () => {
  try {
    const response = await getAutomationConfigurations({ page_size: 100 })
    automationConfigurations.value = response.data.results || response.data || []
  } catch (error) {
    console.error('获取运行环境失败:', error)
    ElMessage.error('获取运行环境失败')
  }
}

const formatEnvironmentLabel = (configuration) => {
  return configuration.environment
    ? `${configuration.name} (${configuration.environment})`
    : configuration.name
}

const validateRunCases = (targetCases) => {
  if (targetCases.some((testCase) => ['structured', 'hybrid'].includes(testCase.case_mode) && executionMode.value !== 'planner_v2')) {
    ElMessage.warning(t('uiAutomation.ai.caseList.messages.structuredCasePlannerModeRequired'))
    return false
  }
  return true
}

const openRunDialog = async (targetCases) => {
  if (!validateRunCases(targetCases)) return
  runTargetCases.value = targetCases
  executionEnvironmentId.value = null
  showRunDialog.value = true
  if (automationConfigurations.value.length === 0) {
    await loadAutomationConfigurations()
  }
}

const openBatchRunDialog = () => {
  openRunDialog(selectedCases.value)
}

const confirmRun = async () => {
  submittingRun.value = true
  const payload = {
    execution_mode: executionMode.value,
    use_cache: !disableCache.value,
    ...(executionEnvironmentId.value !== null ? { api_automation_configuration_id: executionEnvironmentId.value } : {})
  }

  try {
    if (runTargetCases.value.length === 1) {
      await executeAICase(runTargetCases.value[0].id, payload)
    } else {
      await batchExecuteAICases({
        ...payload,
        case_ids: runTargetCases.value.map((testCase) => testCase.id)
      })
    }
    ElMessage.success(t('uiAutomation.ai.caseList.messages.runSuccess'))
    showRunDialog.value = false
    router.push('/ai-intelligent-mode/execution-records')
  } catch (error) {
    console.error('执行失败:', error)
    ElMessage.error(t('uiAutomation.ai.caseList.messages.runFailed'))
  } finally {
    submittingRun.value = false
  }
}

// 编辑用例
const editCase = (row) => {
  isCreateMode.value = false
  currentCaseId.value = row.id
  editForm.name = row.name
  editForm.description = row.description
  editForm.task_description = row.task_description
  editForm.case_mode = row.case_mode || 'freeform'
  editForm.planned_steps = Array.isArray(row.planned_steps)
    ? row.planned_steps.map((step, index) => ({
      id: step.id || index + 1,
      executor: step.executor || 'browser',
      step_mode: step.step_mode || 'ai',
      description: step.description || ''
    }))
    : []
  editForm.task_steps = Array.isArray(row.task_steps) && row.task_steps.length > 0
    ? row.task_steps.map((step, index) => normalizeStructuredStep(step, index))
    : [createStructuredStep(row.case_mode === 'hybrid' ? 'ai' : 'direct')]
  showEditDialog.value = true
}

const confirmEdit = async () => {
  if (!editFormRef.value) return

  await editFormRef.value.validate(async (valid) => {
    if (valid) {
      if (['structured', 'hybrid'].includes(editForm.case_mode) && !validateStructuredSteps()) {
        return
      }

      saving.value = true
      try {
        const payload = {
          name: editForm.name,
          description: editForm.description,
          task_description: editForm.case_mode === 'freeform'
            ? editForm.task_description
            : buildTaskDescriptionFromSteps(editForm.task_steps),
          case_mode: editForm.case_mode,
          task_steps: editForm.case_mode === 'freeform' ? [] : buildTaskStepsPayload(),
          planned_steps: editForm.case_mode === 'freeform'
            ? editForm.planned_steps.filter(step => String(step.description || '').trim())
            : [],
          project_id: projectId.value || null,
        }

        if (isCreateMode.value) {
          await createAICase(payload)
          ElMessage.success(t('uiAutomation.ai.caseList.messages.createSuccess'))
        } else {
          await updateAICase(currentCaseId.value, payload)
          ElMessage.success(t('uiAutomation.ai.caseList.messages.updateSuccess'))
        }

        showEditDialog.value = false
        loadCases()
      } catch (error) {
        console.error('更新失败:', error)
        ElMessage.error(isCreateMode.value
          ? t('uiAutomation.ai.caseList.messages.createFailed')
          : t('uiAutomation.ai.caseList.messages.updateFailed'))
      } finally {
        saving.value = false
      }
    }
  })
}

// 删除用例
const deleteCase = async (id) => {
  try {
    await ElMessageBox.confirm(
      t('uiAutomation.ai.caseList.messages.deleteConfirm'),
      t('uiAutomation.messages.confirm.tip'),
      {
        confirmButtonText: t('uiAutomation.common.confirm'),
        cancelButtonText: t('uiAutomation.common.cancel'),
        type: 'warning'
      }
    )

    await deleteAICase(id)
    ElMessage.success(t('uiAutomation.ai.caseList.messages.deleteSuccess'))
    loadCases()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
      ElMessage.error(t('uiAutomation.ai.caseList.messages.deleteFailed'))
    }
  }
}

// 执行用例
const runCase = (row) => {
  openRunDialog([row])
}

const formatDate = (row, column, cellValue) => {
  if (!cellValue) return ''
  return new Date(cellValue).toLocaleString()
}

onMounted(async () => {
  await loadProjects()
  await loadAutomationConfigurations()
  if (projects.value.length > 0) {
    projectId.value = projects.value[0].id
    loadCases()
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
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.card-container {
  background-color: #fff;
  border-radius: 4px;
  padding: 20px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.cache-switch {
  margin-left: 4px;
}

.task-description-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.task-description-text {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.task-description-text.expanded {
  display: block;
  -webkit-line-clamp: unset;
  overflow: visible;
}

.task-description-toggle {
  align-self: flex-start;
  padding: 0;
}

.action-buttons {
  display: flex;
  align-items: center;
  gap: 8px;
}

.case-mode-tip {
  display: inline-block;
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}

.structured-steps {
  width: 100%;
}

.planned-steps-editor {
  width: 100%;
  display: grid;
  gap: 8px;
}

.planned-step-row {
  display: grid;
  grid-template-columns: 28px 110px minmax(0, 1fr) 32px;
  gap: 8px;
  align-items: start;
}

.planned-step-number {
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  font-size: 0.82rem;
  font-weight: 700;
}

.planned-step-mode {
  width: 110px;
}

.structured-step-card {
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid #EBEEF5;
  border-radius: 8px;
  background: #FAFAFA;
}

.structured-step-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 500;
}

.structured-step-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(96px, 120px);
  gap: 12px;
  margin-bottom: 12px;
}

.structured-step-grid > * {
  min-width: 0;
}

.structured-step-grid :deep(.el-input),
.structured-step-grid :deep(.el-select),
.structured-step-grid :deep(.el-input-number) {
  width: 100%;
}

.structured-step-grid.single-line {
  grid-template-columns: 1fr;
}

.structured-add-btn {
  flex: 1;
}

.structured-actions {
  display: flex;
  gap: 12px;
}

.hybrid-meta-grid {
  grid-template-columns: minmax(0, 1fr) minmax(96px, 120px);
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
