<template>
  <div class="scheduled-tasks">
    <div class="header">
      <h3>{{ t('appAutomation.scheduledTask.title') }}</h3>
      <el-button type="primary" @click="handleCreate">
        <el-icon><Plus /></el-icon>
        {{ t('appAutomation.scheduledTask.newTask') }}
      </el-button>
    </div>

    <!-- 筛选 -->
    <div class="filters">
      <el-row :gutter="20">
        <el-col :span="5">
          <el-select v-model="filters.project" :placeholder="t('appAutomation.scheduledTask.allProjects')" clearable filterable>
            <el-option v-for="p in projectList" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-col>
        <el-col :span="5">
          <el-select v-model="filters.task_type" :placeholder="t('appAutomation.scheduledTask.taskTypeFilter')" clearable>
            <el-option :label="t('appAutomation.scheduledTask.taskTypeTestSuite')" value="APP_TEST_SUITE" />
            <el-option :label="t('appAutomation.scheduledTask.taskTypeTestCase')" value="APP_TEST_CASE" />
          </el-select>
        </el-col>
        <el-col :span="5">
          <el-select v-model="filters.schedule_type" :placeholder="t('appAutomation.scheduledTask.scheduleType')" clearable>
            <el-option :label="t('appAutomation.scheduledTask.scheduleTypes.cron')" value="C" />
            <el-option :label="t('appAutomation.scheduledTask.scheduleTypes.once')" value="O" />
            <el-option :label="t('appAutomation.scheduledTask.scheduleTypes.interval')" value="I" />
            <el-option :label="t('appAutomation.scheduledTask.scheduleTypes.hourly')" value="H" />
            <el-option :label="t('appAutomation.scheduledTask.scheduleTypes.daily')" value="D" />
            <el-option :label="t('appAutomation.scheduledTask.scheduleTypes.weekly')" value="W" />
            <el-option :label="t('appAutomation.scheduledTask.scheduleTypes.biweekly')" value="BW" />
            <el-option :label="t('appAutomation.scheduledTask.scheduleTypes.monthly')" value="M" />
            <el-option :label="t('appAutomation.scheduledTask.scheduleTypes.bimonthly')" value="BM" />
            <el-option :label="t('appAutomation.scheduledTask.scheduleTypes.quarterly')" value="Q" />
            <el-option :label="t('appAutomation.scheduledTask.scheduleTypes.yearly')" value="Y" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.status" :placeholder="t('appAutomation.scheduledTask.status')" clearable>
            <el-option :label="t('appAutomation.scheduledTask.statusTypes.active')" value="ACTIVE" />
            <el-option :label="t('appAutomation.scheduledTask.statusTypes.paused')" value="PAUSED" />
            <el-option :label="t('appAutomation.scheduledTask.statusTypes.completed')" value="COMPLETED" />
            <el-option :label="t('appAutomation.scheduledTask.statusTypes.failed')" value="FAILED" />
          </el-select>
        </el-col>
        <el-col :span="5">
          <el-button @click="resetFilters">{{ t('appAutomation.common.reset') }}</el-button>
          <el-button type="primary" @click="loadTasks">{{ t('appAutomation.common.query') }}</el-button>
        </el-col>
      </el-row>
    </div>

    <!-- 列表 -->
    <el-table :data="tasks" v-loading="loading" border>
      <el-table-column prop="name" :label="t('appAutomation.scheduledTask.taskName')" min-width="180" />
      <el-table-column prop="task_type_display" :label="t('appAutomation.scheduledTask.taskType')" width="120">
        <template #default="{ row }">
          <el-tag :type="row.task_type === 'APP_TEST_SUITE' ? 'success' : 'primary'" size="small">
            {{ row.task_type_display || row.task_type }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="schedule_type_display" :label="t('appAutomation.scheduledTask.scheduleType')" width="100">
        <template #default="{ row }">
          <el-tag size="small">{{ row.schedule_type_display || getScheduleTypeText(row.schedule_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('appAutomation.scheduledTask.notificationType')" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.notification_type_display && row.notification_type_display !== '未配置'" :type="getNotificationTypeTag(row.notification_type_display)" size="small">
            {{ row.notification_type_display }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" :label="t('appAutomation.scheduledTask.status')" width="90">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status_display)" size="small">
            {{ row.status_display }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('appAutomation.scheduledTask.device')" width="130">
        <template #default="{ row }">
          {{ row.device_name || '-' }}
        </template>
      </el-table-column>
      <el-table-column :label="t('appAutomation.scheduledTask.nextRunTime')" width="170">
        <template #default="{ row }">
          {{ row.next_run_display || '-' }}
        </template>
      </el-table-column>
      <el-table-column :label="t('appAutomation.scheduledTask.lastRunTime')" width="170">
        <template #default="{ row }">
          {{ row.last_run_display || '-' }}
        </template>
      </el-table-column>
      <el-table-column :label="t('appAutomation.scheduledTask.executionStats')" width="140">
        <template #default="{ row }">
          <span>{{ t('appAutomation.scheduledTask.total') }} {{ row.total_runs || 0 }}  </span>
          <span style="color:#67c23a">{{ t('appAutomation.scheduledTask.success') }} {{ row.successful_runs || 0 }}  </span>
          <span style="color:#f56c6c">{{ t('appAutomation.scheduledTask.failed') }} {{ row.failed_runs || 0 }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('appAutomation.common.operation')" width="200" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="runNow(row)" :loading="row._running">{{ t('appAutomation.scheduledTask.actions.execute') }}</el-button>
          <el-dropdown @command="cmd => handleAction(cmd, row)">
            <el-button size="small">{{ t('appAutomation.scheduledTask.more') }}<el-icon><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit">{{ t('appAutomation.scheduledTask.actions.edit') }}</el-dropdown-item>
                <el-dropdown-item command="pause" v-if="row.status === 'ACTIVE'">{{ t('appAutomation.scheduledTask.actions.pause') }}</el-dropdown-item>
                <el-dropdown-item command="resume" v-if="row.status === 'PAUSED'">{{ t('appAutomation.scheduledTask.actions.resume') }}</el-dropdown-item>
                <el-dropdown-item command="delete" divided>{{ t('appAutomation.scheduledTask.actions.delete') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        v-model:current-page="pagination.current"
        v-model:page-size="pagination.size"
        :total="pagination.total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadTasks"
        @current-change="loadTasks"
      />
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="showDialog" :title="editingTask ? t('appAutomation.scheduledTask.editTask') : t('appAutomation.scheduledTask.createTask')" width="720px" :close-on-click-modal="false" @close="resetForm">
      <el-form :model="form" label-width="110px">
        <el-form-item :label="t('appAutomation.scheduledTask.form.taskName')" required>
          <el-input v-model="form.name" :placeholder="t('appAutomation.scheduledTask.form.taskNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('appAutomation.scheduledTask.form.relatedProject')">
          <el-select v-model="form.project" :placeholder="t('appAutomation.scheduledTask.selectProject')" clearable filterable style="width:100%">
            <el-option v-for="p in projectList" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('appAutomation.scheduledTask.form.taskDesc')">
          <el-input v-model="form.description" type="textarea" :placeholder="t('appAutomation.scheduledTask.form.taskDescPlaceholder')" />
        </el-form-item>

        <el-form-item :label="t('appAutomation.scheduledTask.form.taskType')" required>
          <el-radio-group v-model="form.task_type">
            <el-radio value="APP_TEST_SUITE">{{ t('appAutomation.scheduledTask.form.testSuite') }}</el-radio>
            <el-radio value="APP_TEST_CASE">{{ t('appAutomation.scheduledTask.form.testCase') }}</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="form.task_type === 'APP_TEST_SUITE'" :label="t('appAutomation.scheduledTask.form.testSuite')" required>
          <el-select v-model="form.test_suite" :placeholder="t('appAutomation.scheduledTask.form.selectSuite')" filterable>
            <el-option v-for="s in suites" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>

        <el-form-item v-if="form.task_type === 'APP_TEST_CASE'" :label="t('appAutomation.scheduledTask.form.testCase')" required>
          <el-select v-model="form.test_case" :placeholder="t('appAutomation.scheduledTask.form.selectTestCase')" filterable>
            <el-option v-for="tc in testCases" :key="tc.id" :label="tc.name" :value="tc.id" />
          </el-select>
        </el-form-item>

        <el-form-item :label="t('appAutomation.scheduledTask.form.executeDevice')" required>
          <el-select v-model="form.device" :placeholder="t('appAutomation.scheduledTask.form.selectDevice')" filterable>
            <el-option v-for="d in devices" :key="d.id" :label="d.name || d.device_id" :value="d.id" />
          </el-select>
        </el-form-item>

        <el-form-item :label="t('appAutomation.scheduledTask.form.appPackage')">
          <el-select v-model="form.app_package" :placeholder="t('appAutomation.scheduledTask.form.selectAppPackage')" filterable clearable>
            <el-option v-for="p in packages" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>

        <el-form-item :label="t('appAutomation.scheduledTask.scheduleType')" required>
          <el-radio-group v-model="form.schedule_type">
            <el-radio value="C">{{ t('appAutomation.scheduledTask.scheduleTypes.cron') }}</el-radio>
            <el-radio value="O">{{ t('appAutomation.scheduledTask.scheduleTypes.once') }}</el-radio>
            <el-radio value="I">{{ t('appAutomation.scheduledTask.scheduleTypes.interval') }}</el-radio>
            <el-radio value="H">{{ t('appAutomation.scheduledTask.scheduleTypes.hourly') }}</el-radio>
            <el-radio value="D">{{ t('appAutomation.scheduledTask.scheduleTypes.daily') }}</el-radio>
            <el-radio value="W">{{ t('appAutomation.scheduledTask.scheduleTypes.weekly') }}</el-radio>
            <el-radio value="BW">{{ t('appAutomation.scheduledTask.scheduleTypes.biweekly') }}</el-radio>
            <el-radio value="M">{{ t('appAutomation.scheduledTask.scheduleTypes.monthly') }}</el-radio>
            <el-radio value="BM">{{ t('appAutomation.scheduledTask.scheduleTypes.bimonthly') }}</el-radio>
            <el-radio value="Q">{{ t('appAutomation.scheduledTask.scheduleTypes.quarterly') }}</el-radio>
            <el-radio value="Y">{{ t('appAutomation.scheduledTask.scheduleTypes.yearly') }}</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="form.schedule_type === 'C'" :label="t('appAutomation.scheduledTask.cronExpression')" required>
          <el-input v-model="form.cron" :placeholder="t('appAutomation.scheduledTask.cronPlaceholder')" />
          <div class="cron-help">
            <el-tooltip raw-content placement="top">
              <template #content>
                <div style="line-height: 1.6; text-align: left;">
                  <div>{{ t('appAutomation.scheduledTask.cronHelp.format') }}</div>
                  <div>{{ t('appAutomation.scheduledTask.cronHelp.minute') }}</div>
                  <div>{{ t('appAutomation.scheduledTask.cronHelp.hour') }}</div>
                  <div>{{ t('appAutomation.scheduledTask.cronHelp.day') }}</div>
                  <div>{{ t('appAutomation.scheduledTask.cronHelp.month') }}</div>
                  <div>{{ t('appAutomation.scheduledTask.cronHelp.week') }}</div>
                  <div style="margin-top: 8px;">{{ t('appAutomation.scheduledTask.cronHelp.examples') }}</div>
                  <div>{{ t('appAutomation.scheduledTask.cronHelp.everyDay') }}</div>
                  <div>{{ t('appAutomation.scheduledTask.cronHelp.everyHour') }}</div>
                  <div>{{ t('appAutomation.scheduledTask.cronHelp.everyMonday') }}</div>
                  <div>{{ t('appAutomation.scheduledTask.cronHelp.everyMonth') }}</div>
                </div>
              </template>
              <span style="cursor: pointer; color: #409EFF;">{{ t('appAutomation.scheduledTask.cronHelpLink') }}</span>
            </el-tooltip>
          </div>
        </el-form-item>

        <el-form-item v-if="form.schedule_type === 'I'" :label="t('appAutomation.scheduledTask.intervalTime')" required>
          <el-input-number v-model="form.minutes" :min="1" />
          <span class="unit">{{ t('appAutomation.scheduledTask.intervalUnit') }}</span>
        </el-form-item>

        <el-form-item v-if="form.schedule_type === 'O'" :label="t('appAutomation.scheduledTask.executeTime')" required>
          <el-date-picker
            v-model="form.next_run"
            type="datetime"
            :placeholder="t('appAutomation.scheduledTask.selectExecuteTime')"
          />
        </el-form-item>

        <!-- 每小时 -->
        <el-form-item v-if="form.schedule_type === 'H'" :label="t('appAutomation.scheduledTask.executeMinute')" required>
          <el-select v-model="form.hour_minute" :placeholder="t('appAutomation.scheduledTask.selectMinute')" style="width: 120px;">
            <el-option v-for="i in 60" :key="i-1" :label="i-1" :value="i-1" />
          </el-select>
          <span class="unit">{{ t('appAutomation.scheduledTask.unit.minute') }}</span>
        </el-form-item>

        <!-- 每天 -->
        <el-form-item v-if="form.schedule_type === 'D'" :label="t('appAutomation.scheduledTask.executeTime')" required>
          <el-time-picker v-model="form.daily_time" :placeholder="t('appAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每周 -->
        <el-form-item v-if="form.schedule_type === 'W'" :label="t('appAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="form.weekly_day" :placeholder="t('appAutomation.scheduledTask.selectWeekday')" style="width: 120px; margin-right: 10px;">
            <el-option :label="t('appAutomation.scheduledTask.weekdays.sunday')" value="0" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.monday')" value="1" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.tuesday')" value="2" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.wednesday')" value="3" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.thursday')" value="4" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.friday')" value="5" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.saturday')" value="6" />
          </el-select>
          <el-time-picker v-model="form.weekly_time" :placeholder="t('appAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 双周 -->
        <el-form-item v-if="form.schedule_type === 'BW'" :label="t('appAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="form.biweekly_day" :placeholder="t('appAutomation.scheduledTask.selectWeekday')" style="width: 120px; margin-right: 10px;">
            <el-option :label="t('appAutomation.scheduledTask.weekdays.sunday')" value="0" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.monday')" value="1" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.tuesday')" value="2" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.wednesday')" value="3" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.thursday')" value="4" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.friday')" value="5" />
            <el-option :label="t('appAutomation.scheduledTask.weekdays.saturday')" value="6" />
          </el-select>
          <el-time-picker v-model="form.biweekly_time" :placeholder="t('appAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每月 -->
        <el-form-item v-if="form.schedule_type === 'M'" :label="t('appAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="form.monthly_date" :placeholder="t('appAutomation.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="form.monthly_time" :placeholder="t('appAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 双月 -->
        <el-form-item v-if="form.schedule_type === 'BM'" :label="t('appAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="form.bimonthly_date" :placeholder="t('appAutomation.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="form.bimonthly_time" :placeholder="t('appAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每季度 -->
        <el-form-item v-if="form.schedule_type === 'Q'" :label="t('appAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="form.quarterly_month" :placeholder="t('appAutomation.scheduledTask.selectMonth')" style="width: 100px; margin-right: 10px;">
            <el-option :label="`${1}${t('appAutomation.scheduledTask.unit.month')}`" value="1" />
            <el-option :label="`${4}${t('appAutomation.scheduledTask.unit.month')}`" value="4" />
            <el-option :label="`${7}${t('appAutomation.scheduledTask.unit.month')}`" value="7" />
            <el-option :label="`${10}${t('appAutomation.scheduledTask.unit.month')}`" value="10" />
          </el-select>
          <el-select v-model="form.quarterly_date" :placeholder="t('appAutomation.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="form.quarterly_time" :placeholder="t('appAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每年 -->
        <el-form-item v-if="form.schedule_type === 'Y'" :label="t('appAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="form.yearly_month" :placeholder="t('appAutomation.scheduledTask.selectMonth')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 12" :key="i" :label="i" :value="i" />
          </el-select>
          <el-select v-model="form.yearly_date" :placeholder="t('appAutomation.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="form.yearly_time" :placeholder="t('appAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <el-form-item :label="t('appAutomation.scheduledTask.notificationSettings')">
          <el-checkbox v-model="form.notify_on_success">{{ t('appAutomation.scheduledTask.notifyOnSuccess') }}</el-checkbox>
          <el-checkbox v-model="form.notify_on_failure">{{ t('appAutomation.scheduledTask.notifyOnFailure') }}</el-checkbox>
        </el-form-item>

        <el-form-item v-if="form.notify_on_success || form.notify_on_failure" :label="t('appAutomation.scheduledTask.notificationType')">
          <el-checkbox v-model="form.notify_on_email">{{ t('appAutomation.scheduledTask.notifyOnEmail') }}</el-checkbox>
          <el-checkbox v-model="form.notify_on_webhook">{{ t('appAutomation.scheduledTask.notifyOnWebhook') }}</el-checkbox>
        </el-form-item>

        <el-form-item v-if="form.notify_on_email || form.notify_on_webhook" :label="t('appAutomation.scheduledTask.notificationConfig')">
          <el-select v-model="form.notification_config_ids" :placeholder="t('appAutomation.scheduledTask.selectNotificationConfig')" clearable multiple>
            <el-option
              v-for="config in filteredNotificationConfigs"
              :key="config.id"
              :label="config.name"
              :value="config.id"
            >
              <span>{{ config.name }}</span>
              <span style="color: #909399; font-size: 12px; margin-left: 8px;">({{ config.config_type_display }})</span>
            </el-option>
          </el-select>
          <div class="form-item-hint" v-if="!filteredNotificationConfigs.length">
            {{ t('appAutomation.scheduledTask.noMatchingNotificationConfig') }}
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showDialog = false">{{ t('appAutomation.common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">
          {{ editingTask ? t('appAutomation.common.save') : t('appAutomation.common.create') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, ArrowDown } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import {
  getSchedulerSchedules,
  createSchedulerSchedule,
  updateSchedulerSchedule,
  deleteSchedulerSchedule,
  executeSchedulerSchedule,
  toggleSchedulerSchedule,
  getTestSuiteList,
  getTestCaseList,
  getDeviceList,
  getPackageList,
  getAppProjects,
  getAppUsers,
} from '@/api/app-automation.js'
import { getUnifiedNotificationConfigs } from '@/api/core.js'

const { t } = useI18n()

const projectList = ref([])
const tasks = ref([])
const suites = ref([])
const testCases = ref([])
const devices = ref([])
const packages = ref([])
const users = ref([])
const notificationConfigs = ref([])
const loading = ref(false)
const submitting = ref(false)
const showDialog = ref(false)
const editingTask = ref(null)
const isInitializingForm = ref(false) // 标记是否正在初始化表单

const filters = reactive({ project: null, task_type: '', schedule_type: '', status: '' })
const pagination = reactive({ current: 1, size: 10, total: 0 })

const defaultForm = {
  name: '', description: '', project: null, task_type: 'APP_TEST_SUITE', schedule_type: 'C',
  cron: '0 0 * * *', minutes: 60, next_run: '',
  hour_minute: 0,
  daily_time: '',
  weekly_day: '1',
  weekly_time: '',
  biweekly_day: '1',
  biweekly_time: '',
  monthly_date: 1,
  monthly_time: '',
  bimonthly_date: 1,
  bimonthly_time: '',
  quarterly_month: 1,
  quarterly_date: 1,
  quarterly_time: '',
  yearly_month: 1,
  yearly_date: 1,
  yearly_time: '',
  device: '', app_package: '', test_suite: '', test_case: '',
  notify_on_success: false, notify_on_failure: true,
  notify_on_email: false, notify_on_webhook: false,
  notification_config_ids: [],
}
const form = reactive({ ...defaultForm })

onMounted(() => {
  getAppProjects({ page_size: 100 }).then(res => { projectList.value = res.data.results || res.data || [] }).catch(() => {})
  loadTasks()
  loadOptions()
  loadNotificationConfigs()
})

const loadTasks = async () => {
  loading.value = true
  try {
    const params = { page: pagination.current, page_size: pagination.size, module: 'APP' }
    if (filters.project) params.project_id = filters.project
    if (filters.task_type) params.task_type = filters.task_type
    if (filters.schedule_type) params.schedule_type = filters.schedule_type
    if (filters.status) params.status = filters.status
    const res = await getSchedulerSchedules(params)
    tasks.value = (res.data.results || res.data || []).map(t => ({ ...t, _running: false }))
    pagination.total = res.data.count || tasks.value.length
  } catch { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

// 获取调度类型文本
const getScheduleTypeText = (type) => {
  const typeMap = {
    'O': '单次',
    'I': '分钟间隔',
    'H': '每小时',
    'D': '每天',
    'W': '每周',
    'BW': '双周',
    'M': '每月',
    'BM': '双月',
    'Q': '每季度',
    'Y': '每年',
    'C': 'Cron'
  }
  return typeMap[type] || type
}

const getStatusType = (status) => {
  if (status === '激活' || status === 'ACTIVE') return 'success'
  if (status === '暂停' || status === 'PAUSED') return 'warning'
  if (status === '失败' || status === 'FAILED') return 'danger'
  return 'info'
}

const getNotificationTypeTag = (notificationTypeDisplay) => {
  if (!notificationTypeDisplay || notificationTypeDisplay === '未配置') {
    return 'info'
  }
  if (notificationTypeDisplay.includes('+')) {
    return 'warning'
  } else if (notificationTypeDisplay.includes('邮箱') || notificationTypeDisplay.includes('邮件')) {
    return 'success'
  } else if (notificationTypeDisplay.includes('Webhook')) {
    return 'primary'
  }
  return 'info'
}

const loadOptions = async () => {
  try {
    const [s, tc, d, p, u] = await Promise.all([
      getTestSuiteList({ page_size: 200 }),
      getTestCaseList({ page_size: 500 }),
      getDeviceList({ page_size: 100 }),
      getPackageList({ page_size: 100 }),
      getAppUsers({ page_size: 1000 }),
    ])
    suites.value = s.data.results || s.data || []
    testCases.value = tc.data.results || tc.data || []
    devices.value = d.data.results || d.data || []
    packages.value = p.data.results || p.data || []
    const usersData = u.data.results || u.data || []
    users.value = usersData.map(user => ({
      ...user,
      display_name: user.first_name ? `${user.first_name}（${user.email}）` : `${user.username}（${user.email}）`
    }))
  } catch (e) { console.error('加载选项失败', e) }
}

const loadNotificationConfigs = async () => {
  try {
    const response = await getUnifiedNotificationConfigs()
    notificationConfigs.value = response.data.results || response.data
  } catch (error) {
    console.error('加载通知配置列表失败:', error)
  }
}

const filteredNotificationConfigs = computed(() => {
  const notifyOnEmail = form.notify_on_email
  const notifyOnWebhook = form.notify_on_webhook
  
  if (!notifyOnEmail && !notifyOnWebhook) {
    return []
  }
  
  return notificationConfigs.value.filter(config => {
    if (!config.is_active) return false
    
    if (notifyOnEmail && notifyOnWebhook) {
      return true
    } else if (notifyOnEmail) {
      return config.config_type === 'email'
    } else if (notifyOnWebhook) {
      return config.config_type !== 'email'
    }
    
    return false
  })
})

const handleCreate = () => {
  editingTask.value = null
  resetForm()
  showDialog.value = true
}

const resetForm = () => Object.assign(form, { ...defaultForm })
const resetFilters = () => { Object.assign(filters, { project: null, task_type: '', schedule_type: '', status: '' }); loadTasks() }

const submitForm = async () => {
  if (!form.name) return ElMessage.warning('请输入任务名称')
  if (!form.device) return ElMessage.warning('请选择设备')

  submitting.value = true
  try {
    const submitData = {
      name: form.name,
      description: form.description,
      module: 'APP',
      task_type: form.task_type,
      schedule_type: form.schedule_type,
      project_id: form.project,
      task_config: {
        device_id: form.device,
        app_package_id: form.app_package || null
      },
      notify_on_success: form.notify_on_success,
      notify_on_failure: form.notify_on_failure,
      notify_on_email: form.notify_on_email,
      notify_on_webhook: form.notify_on_webhook,
      notification_config_ids: form.notification_config_ids
    }

    // 根据调度类型添加对应字段
    if (form.schedule_type === 'C') {
      submitData.cron = form.cron
    } else if (form.schedule_type === 'I') {
      submitData.minutes = form.minutes
    } else if (form.schedule_type === 'O') {
      submitData.next_run = form.next_run
    } else if (form.schedule_type === 'H') {
      // 每小时：指定分钟
      const minute = form.hour_minute || 0
      submitData.cron = `${minute} * * * *`
    } else if (form.schedule_type === 'D') {
      // 每天：指定时间
      if (form.daily_time) {
        const time = form.daily_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        submitData.cron = `${minute} ${hour} * * *`
      } else {
        submitData.cron = '0 0 * * *' // 默认每天0点
      }
    } else if (form.schedule_type === 'W') {
      // 每周：指定星期和时间
      if (form.weekly_time) {
        const time = form.weekly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const day = form.weekly_day || 1
        submitData.cron = `${minute} ${hour} * * ${day}`
      } else {
        submitData.cron = '0 0 * * 1' // 默认每周一0点
      }
    } else if (form.schedule_type === 'BW') {
      // 双周：使用cron表达式，实际上是每两周的指定时间
      if (form.biweekly_time) {
        const time = form.biweekly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const day = form.biweekly_day || 1
        submitData.cron = `${minute} ${hour} * * ${day}`
      } else {
        submitData.cron = '0 0 * * 1' // 默认双周周一0点
      }
    } else if (form.schedule_type === 'M') {
      // 每月：指定日期和时间
      if (form.monthly_time) {
        const time = form.monthly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const date = form.monthly_date || 1
        submitData.cron = `${minute} ${hour} ${date} * *`
      } else {
        submitData.cron = '0 0 1 * *' // 默认每月1号0点
      }
    } else if (form.schedule_type === 'BM') {
      // 双月：使用cron表达式，实际上是每两个月的指定时间
      if (form.bimonthly_time) {
        const time = form.bimonthly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const date = form.bimonthly_date || 1
        submitData.cron = `${minute} ${hour} ${date} */2 *`
      } else {
        submitData.cron = '0 0 1 */2 *' // 默认双月1号0点
      }
    } else if (form.schedule_type === 'Q') {
      // 每季度：指定月份日期和时间
      if (form.quarterly_time) {
        const time = form.quarterly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const date = form.quarterly_date || 1
        const month = form.quarterly_month || 1
        submitData.cron = `${minute} ${hour} ${date} ${month} *`
      } else {
        submitData.cron = '0 0 1 1 *' // 默认每年1月1号0点
      }
    } else if (form.schedule_type === 'Y') {
      // 每年：指定月份日期和时间
      if (form.yearly_time) {
        const time = form.yearly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const date = form.yearly_date || 1
        const month = form.yearly_month || 1
        submitData.cron = `${minute} ${hour} ${date} ${month} *`
      } else {
        submitData.cron = '0 0 1 1 *' // 默认每年1月1号0点
      }
    }

    // 根据任务类型添加对应字段
    if (form.task_type === 'APP_TEST_SUITE') {
      submitData.target_id = form.test_suite
    } else if (form.task_type === 'APP_TEST_CASE') {
      submitData.target_id = form.test_case
    }

    if (editingTask.value) {
      await updateSchedulerSchedule(editingTask.value.id, submitData)
      ElMessage.success('更新成功')
    } else {
      await createSchedulerSchedule(submitData)
      ElMessage.success('创建成功')
    }
    showDialog.value = false
    loadTasks()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.response?.data?.message || e.response?.data?.error || '操作失败')
  } finally { submitting.value = false }
}

const runNow = async (task) => {
  task._running = true
  try {
    await executeSchedulerSchedule(task.id)
    ElMessage.success('任务已开始执行')
    setTimeout(loadTasks, 2000)
  } catch (e) {
    ElMessage.error(e.response?.data?.message || e.response?.data?.error || '执行失败')
  } finally { task._running = false }
}

const handleAction = (cmd, task) => {
  switch (cmd) {
    case 'edit': editTask(task); break
    case 'pause': pauseTask(task); break
    case 'resume': resumeTask(task); break
    case 'delete': deleteTask(task); break
  }
}

const editTask = (task) => {
  editingTask.value = task
  isInitializingForm.value = true // 标记开始初始化表单
  const config = task.config || {}
  
  // 从 cron 表达式中解析时间字段
  let hour_minute = 0
  let daily_time = null
  let weekly_day = '1'
  let weekly_time = null
  let biweekly_day = '1'
  let biweekly_time = null
  let monthly_date = 1
  let monthly_time = null
  let bimonthly_date = 1
  let bimonthly_time = null
  let quarterly_month = 1
  let quarterly_date = 1
  let quarterly_time = null
  let yearly_month = 1
  let yearly_date = 1
  let yearly_time = null
  
  if (task.cron) {
    const cronParts = task.cron.split(' ')
    const minute = parseInt(cronParts[0]) || 0
    const hour = parseInt(cronParts[1]) || 0
    const dayOfMonth = parseInt(cronParts[2]) || 1
    const month = parseInt(cronParts[3]) || 1
    const dayOfWeek = parseInt(cronParts[4]) || 1
    
    hour_minute = minute
    
    if (task.schedule_type === 'D') {
      daily_time = new Date()
      daily_time.setHours(hour, minute, 0, 0)
    } else if (task.schedule_type === 'W') {
      weekly_day = dayOfWeek.toString()
      weekly_time = new Date()
      weekly_time.setHours(hour, minute, 0, 0)
    } else if (task.schedule_type === 'BW') {
      biweekly_day = dayOfWeek.toString()
      biweekly_time = new Date()
      biweekly_time.setHours(hour, minute, 0, 0)
    } else if (task.schedule_type === 'M') {
      monthly_date = dayOfMonth
      monthly_time = new Date()
      monthly_time.setHours(hour, minute, 0, 0)
    } else if (task.schedule_type === 'BM') {
      bimonthly_date = dayOfMonth
      bimonthly_time = new Date()
      bimonthly_time.setHours(hour, minute, 0, 0)
    } else if (task.schedule_type === 'Q') {
      quarterly_month = month
      quarterly_date = dayOfMonth
      quarterly_time = new Date()
      quarterly_time.setHours(hour, minute, 0, 0)
    } else if (task.schedule_type === 'Y') {
      yearly_month = month
      yearly_date = dayOfMonth
      yearly_time = new Date()
      yearly_time.setHours(hour, minute, 0, 0)
    }
  }
  
  Object.assign(form, {
    name: task.name, description: config.description || '',
    task_type: config.task_type || 'APP_TEST_SUITE', schedule_type: task.schedule_type || 'C',
    cron: task.cron || '0 0 * * *',
    minutes: task.minutes || 60,
    next_run: task.next_run || '',
    hour_minute,
    daily_time,
    weekly_day,
    weekly_time,
    biweekly_day,
    biweekly_time,
    monthly_date,
    monthly_time,
    bimonthly_date,
    bimonthly_time,
    quarterly_month,
    quarterly_date,
    quarterly_time,
    yearly_month,
    yearly_date,
    yearly_time,
    device: config.task_config?.device_id || '',
    app_package: config.task_config?.app_package_id || '',
    test_suite: config.task_type === 'APP_TEST_SUITE' ? config.target_id : '',
    test_case: config.task_type === 'APP_TEST_CASE' ? config.target_id : '',
    notify_on_success: config.notify_on_success ?? false,
    notify_on_failure: config.notify_on_failure ?? true,
    notify_on_email: config.notify_on_email ?? false,
    notify_on_webhook: config.notify_on_webhook ?? false,
    notification_config_ids: task.config?.notification_config_ids || []
  })
  
  showDialog.value = true
  
  // 等待表单初始化完成后，重置标志
  nextTick(() => {
    isInitializingForm.value = false
  })
}

// 监听通知类型变化，过滤不匹配的通知配置
watch([() => form.notify_on_email, () => form.notify_on_webhook], () => {
  // 如果正在初始化表单，跳过过滤逻辑
  if (isInitializingForm.value) {
    return
  }
  
  nextTick(() => {
    const notifyOnEmail = form.notify_on_email
    const notifyOnWebhook = form.notify_on_webhook
    
    if (!notifyOnEmail && !notifyOnWebhook) {
      form.notification_config_ids = []
      return
    }
    
    form.notification_config_ids = form.notification_config_ids.filter(id => {
      const config = notificationConfigs.value.find(c => c.id === id)
      if (!config) return false
      
      if (notifyOnEmail && notifyOnWebhook) {
        return true
      } else if (notifyOnEmail) {
        return config.config_type === 'email'
      } else if (notifyOnWebhook) {
        return config.config_type === 'webhook'
      }
      return false
    })
  })
})

const pauseTask = async (task) => {
  try { await toggleSchedulerSchedule(task.id, 'pause'); ElMessage.success('已暂停'); loadTasks() }
  catch { ElMessage.error('暂停失败') }
}
const resumeTask = async (task) => {
  try { await toggleSchedulerSchedule(task.id, 'resume'); ElMessage.success('已恢复'); loadTasks() }
  catch { ElMessage.error('恢复失败') }
}
const deleteTask = async (task) => {
  try {
    await ElMessageBox.confirm(`确认删除任务「${task.name}」？`, '删除确认', { type: 'warning' })
    await deleteSchedulerSchedule(task.id)
    ElMessage.success('已删除')
    loadTasks()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

const formatDateTime = (s) => {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).replace(/\//g, '-')
}
</script>

<style scoped>
.scheduled-tasks { padding: 20px; display: flex; flex-direction: column; height: 100%; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.filters { margin-bottom: 20px; background: #f8f9fa; padding: 20px; border-radius: 8px; }
.pagination { margin-top: 20px; display: flex; justify-content: flex-end; }
.cron-help { margin-top: 8px; font-size: 12px; }
.unit { margin-left: 8px; color: #606266; }
</style>
