<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('uiAutomation.ai.title') }}</h1>
      <div class="header-actions">
        <el-select v-model="projectId" :placeholder="$t('uiAutomation.project.selectProject')" style="width: 200px;" @change="onProjectChange">
          <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
      </div>
    </div>

    <div class="card-container">
      <el-row :gutter="20">
        <el-col :span="12">
          <div class="section-title">{{ $t('uiAutomation.ai.taskInput') }}</div>
          <el-form :model="taskForm" label-position="top">
            <el-form-item :label="$t('uiAutomation.ai.executionBackend')">
              <el-select v-model="taskForm.executionMode" style="width: 220px;">
                <el-option :label="$t('uiAutomation.ai.backends.browser')" value="text" />
                <el-option :label="$t('uiAutomation.ai.backends.plannerV2')" value="planner_v2" />
              </el-select>
            </el-form-item>

            <el-form-item :label="$t('uiAutomation.ai.caseMode')">
              <el-select v-model="taskForm.caseMode" style="width: 220px;">
                <el-option :label="$t('uiAutomation.ai.caseModes.freeform')" value="freeform" />
                <el-option :label="$t('uiAutomation.ai.caseModes.hybrid')" value="hybrid" :disabled="taskForm.executionMode !== 'planner_v2'" />
                <el-option :label="$t('uiAutomation.ai.caseModes.structured')" value="structured" :disabled="taskForm.executionMode !== 'planner_v2'" />
              </el-select>
              <span style="margin-left: 10px; color: #909399; font-size: 12px;">
                {{ caseModeTipText }}
              </span>
            </el-form-item>

            <el-form-item v-if="taskForm.caseMode === 'freeform'" :label="$t('uiAutomation.ai.taskDescription')" required>
              <el-input
                v-model="taskForm.description"
                type="textarea"
                :rows="10"
                :placeholder="$t('uiAutomation.ai.taskPlaceholder')"
                maxlength="2000"
                show-word-limit
              />
            </el-form-item>

            <el-form-item v-else :label="stepsSectionTitle" required>
              <div class="structured-steps">
                <div v-for="(step, index) in taskForm.taskSteps" :key="index" class="structured-step-card">
                  <div class="structured-step-header">
                    <span>{{ $t('uiAutomation.ai.structuredStep') }} {{ index + 1 }}</span>
                    <el-button text type="danger" @click="removeStructuredStep(index)">
                      <el-icon><Delete /></el-icon>
                    </el-button>
                  </div>

                  <div v-if="taskForm.caseMode === 'hybrid'" class="structured-step-grid hybrid-meta-grid">
                    <el-select v-model="step.step_mode">
                      <el-option :label="$t('uiAutomation.ai.stepModes.ai')" value="ai" />
                      <el-option :label="$t('uiAutomation.ai.stepModes.direct')" value="direct" />
                    </el-select>
                    <el-input-number v-model="step.timeout_ms" :min="1000" :step="1000" :controls="false" />
                  </div>

                  <div v-if="taskForm.caseMode === 'hybrid' && step.step_mode === 'ai'" class="structured-step-grid single-line">
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

                    <div v-else-if="step.action === 'assert'" class="structured-step-grid">
                      <el-select v-model="step.assert_kind">
                        <el-option v-for="assertKind in assertionKindOptions" :key="assertKind" :label="assertKind" :value="assertKind" />
                      </el-select>
                      <el-input v-model="step.selector" :placeholder="$t('uiAutomation.ai.stepSelectorPlaceholder')" />
                      <el-select v-model="step.operator">
                        <el-option label="contains" value="contains" />
                        <el-option label="equals" value="equals" />
                        <el-option label="exists" value="exists" />
                        <el-option label="not_exists" value="not_exists" />
                      </el-select>
                      <el-input v-model="step.expected" :placeholder="$t('uiAutomation.ai.stepExpectedPlaceholder')" />
                    </div>
                  </template>
                </div>

                <div class="structured-actions">
                  <el-button plain type="primary" class="structured-add-btn" @click="addStructuredStep()">
                    <el-icon><Plus /></el-icon>
                    {{ $t('uiAutomation.ai.addStructuredStep') }}
                  </el-button>
                  <el-button v-if="taskForm.caseMode === 'hybrid'" plain type="success" class="structured-add-btn" @click="addStructuredStep('direct')">
                    <el-icon><Plus /></el-icon>
                    {{ $t('uiAutomation.ai.addDirectStep') }}
                  </el-button>
                </div>
              </div>
            </el-form-item>

            <el-form-item :label="$t('uiAutomation.ai.gifRecording')">
              <el-switch
                v-model="taskForm.enableGif"
                :active-text="$t('uiAutomation.ai.on')"
                :inactive-text="$t('uiAutomation.ai.off')"
                :disabled="taskForm.executionMode !== 'text'"
              />
              <span style="margin-left: 10px; color: #909399; font-size: 12px;">
                {{ taskForm.executionMode === 'text' ? $t('uiAutomation.ai.gifTip') : $t('uiAutomation.ai.nonBrowserGifTip') }}
              </span>
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                @click="handleRun"
                :loading="running"
                :disabled="!canRun"
              >
                <el-icon><VideoPlay /></el-icon>
                {{ $t('uiAutomation.ai.startExecution') }}
              </el-button>
              <el-button
                type="danger"
                @click="handleStop"
                :disabled="!running || analyzing"
                v-if="running"
              >
                <el-icon><SwitchButton /></el-icon>
                {{ $t('uiAutomation.ai.stopExecution') }}
              </el-button>
              <el-button
                type="success"
                @click="handleSaveAsCase"
                :disabled="!canRun"
              >
                <el-icon><DocumentAdd /></el-icon>
                {{ $t('uiAutomation.ai.saveAsCase') }}
              </el-button>
            </el-form-item>
          </el-form>

          <el-alert
            :title="$t('uiAutomation.ai.tip')"
            type="info"
            :closable="false"
            style="margin-top: 20px;"
          >
            <template #default>
              <div>{{ $t('uiAutomation.ai.tipContent1') }}</div>
              <div>{{ $t('uiAutomation.ai.tipContent2') }}</div>
            </template>
          </el-alert>

          <div class="section-title" style="margin-top: 20px;">{{ $t('uiAutomation.ai.executionLogs') }}</div>
          <div class="log-container" ref="logContainer">
            <div v-if="!logs && !running" class="empty-logs">
              {{ $t('uiAutomation.ai.noLogs') }}
            </div>
            <pre v-else class="log-content">{{ logs }}</pre>
          </div>
        </el-col>

        <el-col :span="12">
          <div class="section-title">{{ $t('uiAutomation.ai.taskDetails') }}</div>
          <div class="task-list-container">
            <div v-if="analyzing" class="analyzing-state">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>{{ $t('uiAutomation.ai.analyzing') }}</span>
            </div>
            <div v-else-if="plannedTasks.length > 0">
              <div
                v-for="task in plannedTasks"
                :key="task.id"
                class="task-item"
                :class="task.status"
              >
                <div class="task-status-icon">
                  <el-icon v-if="task.status === 'completed'" color="#67C23A"><CircleCheckFilled /></el-icon>
                  <el-icon v-else-if="task.status === 'in_progress'" class="is-loading" color="#409EFF"><Loading /></el-icon>
                  <el-icon v-else color="#909399"><CircleCheck /></el-icon>
                </div>
                <div class="task-content">
                  <span class="task-id">{{ task.id }}.</span>
                  <span class="task-desc">{{ task.description }}</span>
                </div>
              </div>
            </div>
            <div v-else class="empty-tasks">
              {{ $t('uiAutomation.ai.noTasks') }}
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 保存为用例对话框 -->
    <el-dialog v-model="showSaveDialog" :title="$t('uiAutomation.ai.saveAsCaseTitle')" width="500px" :close-on-click-modal="false">
      <el-form :model="saveForm" :rules="saveRules" ref="saveFormRef" label-width="80px">
        <el-form-item :label="$t('uiAutomation.ai.caseName')" prop="name">
          <el-input v-model="saveForm.name" :placeholder="$t('uiAutomation.ai.caseNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.common.description')" prop="description">
          <el-input v-model="saveForm.description" type="textarea" :placeholder="$t('uiAutomation.ai.caseDescPlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showSaveDialog = false">{{ $t('uiAutomation.common.cancel') }}</el-button>
          <el-button type="primary" @click="confirmSaveCase" :loading="saving">{{ $t('uiAutomation.common.save') }}</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPlay, DocumentAdd, CircleCheckFilled, CircleCheck, Loading, SwitchButton, Plus, Delete } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { createAICase, stopAIExecution, getAIExecutionRecord, getAiProjects, runAdhocAICase } from '@/api/ai-testing'

const { t } = useI18n()

const projects = ref([])
const projectId = ref('')
const running = ref(false)
const analyzing = ref(false)
const saving = ref(false)
const logs = ref('')
const plannedTasks = ref([])
const currentExecutionId = ref(null)
const logContainer = ref(null)

const createStructuredStep = (stepMode = 'direct') => ({
  step_mode: stepMode,
  action: 'navigate',
  description: '',
  url: '',
  selector: '',
  value: '',
  expected: '',
  assert_kind: 'text',
  operator: 'contains',
  timeout_ms: 10000
})

const taskForm = reactive({
  description: '',
  enableGif: true,  // GIF录制开关，默认开启
  executionMode: 'planner_v2',
  caseMode: 'freeform',
  taskSteps: [createStructuredStep()]
})

const showSaveDialog = ref(false)
const saveForm = reactive({
  name: '',
  description: ''
})
const saveFormRef = ref(null)

const saveRules = computed(() => ({
  name: [{ required: true, message: t('uiAutomation.ai.rules.nameRequired'), trigger: 'blur' }]
}))

const requiresStructuredMode = computed(() => taskForm.executionMode === 'planner_v2')

const stepActionOptions = computed(() => [
  { label: t('uiAutomation.ai.stepActions.navigate'), value: 'navigate' },
  { label: t('uiAutomation.ai.stepActions.click'), value: 'click' },
  { label: t('uiAutomation.ai.stepActions.fill'), value: 'fill' },
  { label: t('uiAutomation.ai.stepActions.press'), value: 'press' },
  { label: t('uiAutomation.ai.stepActions.select'), value: 'select' },
  { label: t('uiAutomation.ai.stepActions.wait'), value: 'wait' },
  { label: 'Unified assertion', value: 'assert' }
])

const assertionKindOptions = ['text', 'field_value', 'popup', 'media', 'video', 'visual_change', 'stream_state', 'playback', 'element_state', 'url', 'network', 'api_resource', 'command_result', 'collection', 'absence']
const assertionEvidenceRequirements = {
  text: ['dom_snapshot'], field_value: ['structured_value'], popup: ['dom_snapshot'], media: ['media_state'], video: ['media_state', 'media_event'], visual_change: ['dom_snapshot_before', 'dom_snapshot_after'], stream_state: ['media_state_before', 'media_state_after', 'playback_time_progress'], playback: ['media_state_before', 'media_state_after', 'playback_time_progress'], element_state: ['dom_snapshot'], url: ['url_snapshot'], network: ['network_response'], api_resource: ['api_response'], command_result: ['command_receipt'], collection: ['dom_snapshot'], absence: ['absence_check']
}

const stepsSectionTitle = computed(() => taskForm.caseMode === 'hybrid'
  ? t('uiAutomation.ai.hybridSteps')
  : t('uiAutomation.ai.structuredSteps'))

const caseModeTipText = computed(() => {
  if (taskForm.executionMode !== 'planner_v2') {
    return t('uiAutomation.ai.caseModeTip')
  }
  if (taskForm.caseMode === 'hybrid') {
    return t('uiAutomation.ai.hybridCaseModeTip')
  }
  return t('uiAutomation.ai.plannerV2Tip')
})

const canRun = computed(() => {
  if (taskForm.caseMode !== 'freeform') {
    return taskForm.taskSteps.some(step => String(step.description || '').trim())
  }
  return !!String(taskForm.description || '').trim()
})

watch(
  () => taskForm.executionMode,
  (mode) => {
    if (mode === 'planner_v2') {
      taskForm.enableGif = false
      if (taskForm.caseMode !== 'freeform' && taskForm.taskSteps.length === 0) {
        taskForm.taskSteps.push(createStructuredStep(taskForm.caseMode === 'hybrid' ? 'ai' : 'direct'))
      }
      return
    }

    if (taskForm.caseMode !== 'freeform') {
      taskForm.caseMode = 'freeform'
    }
  },
  { immediate: true }
)

watch(
  () => taskForm.caseMode,
  (mode) => {
    if (mode !== 'freeform' && taskForm.taskSteps.length === 0) {
      taskForm.taskSteps.push(createStructuredStep(mode === 'hybrid' ? 'ai' : 'direct'))
    }
  }
)

const addStructuredStep = (stepMode = null) => {
  const fallbackMode = taskForm.caseMode === 'hybrid' ? 'ai' : 'direct'
  taskForm.taskSteps.push(createStructuredStep(stepMode || fallbackMode))
}

const removeStructuredStep = (index) => {
  if (taskForm.taskSteps.length === 1) {
    taskForm.taskSteps.splice(0, 1, createStructuredStep(taskForm.caseMode === 'hybrid' ? 'ai' : 'direct'))
    return
  }
  taskForm.taskSteps.splice(index, 1)
}

const normalizeStructuredStep = (step = {}, index = 0) => ({
  step_mode: step.step_mode || (taskForm.caseMode === 'hybrid' ? 'ai' : 'direct'),
  action: step.action || 'navigate',
  description: step.description || '',
  url: step.url || '',
  selector: step.selector || '',
  value: step.value || '',
  expected: step.expected || '',
  assert_kind: step.assert_kind || 'text',
  operator: step.operator || 'contains',
  timeout_ms: Number(step.timeout_ms) || 10000,
  step_no: Number(step.step_no) || index + 1
})

const validateStructuredSteps = () => {
  if (!Array.isArray(taskForm.taskSteps) || taskForm.taskSteps.length === 0) {
    ElMessage.error(t('uiAutomation.ai.messages.structuredStepsRequired'))
    return false
  }

  for (const [index, step] of taskForm.taskSteps.entries()) {
    const label = `${t('uiAutomation.ai.structuredStep')} ${index + 1}`
    if (!String(step.description || '').trim()) {
      ElMessage.error(`${label}: ${t('uiAutomation.ai.messages.stepDescriptionRequired')}`)
      return false
    }
    if (taskForm.caseMode === 'hybrid' && step.step_mode === 'ai') {
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
    if (['click', 'fill', 'press', 'select', 'assert'].includes(step.action) && !String(step.selector || '').trim()) {
      ElMessage.error(`${label}: ${t('uiAutomation.ai.messages.stepSelectorRequired')}`)
      return false
    }
    if (['fill', 'press', 'select'].includes(step.action) && !String(step.value || '').trim()) {
      ElMessage.error(`${label}: ${t('uiAutomation.ai.messages.stepValueRequired')}`)
      return false
    }
    if (step.action === 'assert' && !String(step.expected || '').trim()) {
      ElMessage.error(`${label}: ${t('uiAutomation.ai.messages.stepExpectedRequired')}`)
      return false
    }
  }

  return true
}

const buildTaskStepsPayload = () => taskForm.taskSteps.map((step, index) => {
  const normalized = normalizeStructuredStep(step, index)
  return {
    ...normalized,
    assertions: normalized.action === 'assert' ? [{ action: 'assert', assert_kind: normalized.assert_kind, target: { locator: normalized.selector }, operator: normalized.operator, expected: { value: normalized.expected }, evidence_requirements: assertionEvidenceRequirements[normalized.assert_kind] || [] }] : [],
    step_no: index + 1
  }
})

const buildTaskDescriptionFromSteps = (taskSteps) => taskSteps.map((step, index) => {
  const prefix = step.step_mode === 'direct' ? '[DIRECT]' : '[AI]'
  return `${index + 1}. ${prefix} ${step.description || ''}`.trim()
}).join('\n')

const loadProjects = async () => {
  try {
    const response = await getAiProjects({ page_size: 100 })
    projects.value = response.data.results || response.data
    if (projects.value.length > 0 && !projectId.value) {
      projectId.value = projects.value[0].id
    }
  } catch (error) {
    ElMessage.error('获取项目列表失败')
    console.error('获取项目列表失败:', error)
  }
}

const onProjectChange = () => {
  // 重置当前执行状态
  running.value = false
  analyzing.value = false
  logs.value = ''
  plannedTasks.value = []
  currentExecutionId.value = null
}

// 执行任务
const handleRun = async () => {
  if (taskForm.caseMode !== 'freeform' && !validateStructuredSteps()) {
    return
  }

  const taskSteps = taskForm.caseMode === 'freeform' ? [] : buildTaskStepsPayload()
  const taskDescription = taskForm.caseMode === 'freeform'
    ? taskForm.description
    : buildTaskDescriptionFromSteps(taskSteps)

  running.value = true
  analyzing.value = true
  logs.value = t('uiAutomation.ai.messages.initAgent')
  plannedTasks.value = []

  try {
    const response = await runAdhocAICase({
      project_id: projectId.value || null,
      task_description: taskDescription,
      execution_mode: taskForm.executionMode,
      enable_gif: taskForm.executionMode === 'text' ? taskForm.enableGif : false,
      case_mode: taskForm.caseMode,
      task_steps: taskSteps
    })

    // analyzing.value = false // 移除过早设置，改为在轮询获取到任务列表后再取消

    currentExecutionId.value = response.data.execution_id
    ElMessage.success(t('uiAutomation.ai.messages.startSuccess'))

    // 开始轮询日志
    pollLogs()

  } catch (error) {
    console.error('执行失败:', error)
    ElMessage.error(t('uiAutomation.ai.messages.startFailed') + ': ' + (error.response?.data?.error || error.message))
    running.value = false
    analyzing.value = false
  }
}

// 停止任务
const handleStop = async () => {
  if (!currentExecutionId.value) return

  try {
    await stopAIExecution(currentExecutionId.value)
    ElMessage.warning(t('uiAutomation.ai.messages.stopping'))
    // 不立即设置 running = false，等待轮询检测到状态变化
  } catch (error) {
    console.error('停止失败:', error)
    ElMessage.error(t('uiAutomation.ai.messages.stopFailed'))
  }
}

// 轮询日志
const pollLogs = () => {
  const pollInterval = setInterval(async () => {
    if (!currentExecutionId.value) {
      clearInterval(pollInterval)
      return
    }
    
    try {
      const response = await getAIExecutionRecord(currentExecutionId.value)
      const record = response.data
      
      logs.value = record.logs || ''
      plannedTasks.value = record.planned_tasks || []
      
      // 如果获取到了任务列表，则取消“分析中”状态
      if (plannedTasks.value.length > 0) {
        analyzing.value = false
      }
      
      // 滚动到底部
      nextTick(() => {
        if (logContainer.value) {
          logContainer.value.scrollTop = logContainer.value.scrollHeight
        }
      })
      
      if (record.status === 'passed' || record.status === 'failed' || record.status === 'inconclusive' || record.status === 'stopped') {
        clearInterval(pollInterval)
        running.value = false
        analyzing.value = false // 确保结束时必然取消分析状态
        if (record.status === 'passed') {
          ElMessage.success(t('uiAutomation.ai.messages.executionSuccess'))
        } else if (record.status === 'stopped') {
          ElMessage.warning(t('uiAutomation.ai.messages.taskStopped'))
        } else if (record.status === 'inconclusive') {
          ElMessage.warning(t('uiAutomation.status.inconclusive'))
        } else {
          ElMessage.error(t('uiAutomation.ai.messages.executionFailed'))
        }
      }
    } catch (error) {
      console.error('获取日志失败:', error)
      // 不停止轮询，可能是临时网络问题
    }
  }, 2000) // 每2秒轮询一次
}

// 保存为用例
const handleSaveAsCase = () => {
  showSaveDialog.value = true
  saveForm.name = ''
  saveForm.description = ''
}

const confirmSaveCase = async () => {
  if (!saveFormRef.value) return

  await saveFormRef.value.validate(async (valid) => {
    if (valid) {
      if (taskForm.caseMode !== 'freeform' && !validateStructuredSteps()) {
        return
      }

      const taskSteps = taskForm.caseMode === 'freeform' ? [] : buildTaskStepsPayload()
      const taskDescription = taskForm.caseMode === 'freeform'
        ? taskForm.description
        : buildTaskDescriptionFromSteps(taskSteps)

      saving.value = true
      try {
        await createAICase({
          name: saveForm.name,
          description: saveForm.description,
          task_description: taskDescription,
          project_id: projectId.value || null,
          case_mode: taskForm.caseMode,
          task_steps: taskSteps
        })

        ElMessage.success(t('uiAutomation.ai.messages.saveSuccess'))
        showSaveDialog.value = false
      } catch (error) {
        console.error('保存失败:', error)
        ElMessage.error(t('uiAutomation.ai.messages.saveFailed'))
      } finally {
        saving.value = false
      }
    }
  })
}

onMounted(() => {
  loadProjects()
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

.card-container {
  background-color: #fff;
  border-radius: 4px;
  padding: 20px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  min-height: calc(100vh - 140px);
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 15px;
  padding-left: 10px;
  border-left: 4px solid #409eff;
}

.task-list-container {
  background-color: #f5f7fa;
  border-radius: 4px;
  padding: 15px;
  margin-bottom: 20px;
  height: calc(100vh - 200px);
  overflow-y: auto;
  
  .task-item {
    display: flex;
    align-items: flex-start;
    padding: 10px;
    border-bottom: 1px solid #e4e7ed;
    transition: all 0.3s;
    
    &:last-child {
      border-bottom: none;
    }
    
    &.completed {
      background-color: #f0f9eb;
      .task-desc {
        color: #67c23a;
        text-decoration: line-through;
      }
    }
    
    &.in_progress {
      background-color: #ecf5ff;
      .task-desc {
        color: #409eff;
        font-weight: bold;
      }
    }
    
    .task-status-icon {
      margin-right: 10px;
      margin-top: 2px;
      font-size: 16px;
    }
    
    .task-content {
      flex: 1;
      line-height: 1.5;
      
      .task-id {
        font-weight: bold;
        margin-right: 5px;
      }
    }
  }
}

.empty-tasks {
  color: #909399;
  text-align: center;
  padding: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.analyzing-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #409eff;
  
  .el-icon {
    font-size: 24px;
    margin-bottom: 10px;
  }
}

.log-container {
  background-color: #1e1e1e;
  border-radius: 4px;
  height: 300px;
  overflow-y: auto;
  padding: 15px;
  color: #fff;
  font-family: 'Consolas', 'Monaco', monospace;
  
  .empty-logs {
    color: #909399;
    text-align: center;
    margin-top: 100px;
  }
  
  .log-content {
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-size: 14px;
    line-height: 1.5;
  }
}

.structured-steps {
  width: 100%;
}

.structured-step-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  background-color: #fafafa;
}

.structured-step-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  font-weight: 600;
}

.structured-step-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 140px;
  gap: 10px;
  margin-bottom: 10px;
}

.structured-step-grid.single-line {
  grid-template-columns: 1fr;
}

.hybrid-meta-grid {
  grid-template-columns: 1fr 140px;
}

.structured-actions {
  display: flex;
  gap: 10px;
}

.structured-add-btn {
  width: 100%;
}
</style>
