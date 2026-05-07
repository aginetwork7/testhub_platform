<template>
  <div class="scheduled-tasks">
    <div class="header">
      <h3>{{ $t('uiAutomation.scheduledTask.title') }}</h3>
      <el-button type="primary" @click="handleCreateClick">
        <el-icon><Plus /></el-icon>
        {{ $t('uiAutomation.scheduledTask.newTask') }}
      </el-button>
    </div>

    <!-- 筛选条件 -->
    <div class="filters">
      <el-row :gutter="20">
        <el-col :span="6">
          <el-select v-model="filters.task_type" :placeholder="$t('uiAutomation.scheduledTask.taskType')" clearable>
            <el-option :label="$t('uiAutomation.scheduledTask.taskTypes.testSuite')" value="UI_TEST_SUITE" />
            <el-option :label="$t('uiAutomation.scheduledTask.taskTypes.testCase')" value="UI_TEST_CASE" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-select v-model="filters.schedule_type" :placeholder="$t('uiAutomation.scheduledTask.triggerType')" clearable>
            <el-option :label="$t('uiAutomation.scheduledTask.scheduleTypes.cron')" value="C" />
            <el-option :label="$t('uiAutomation.scheduledTask.scheduleTypes.once')" value="O" />
            <el-option :label="$t('uiAutomation.scheduledTask.scheduleTypes.interval')" value="I" />
            <el-option :label="$t('uiAutomation.scheduledTask.scheduleTypes.hourly')" value="H" />
            <el-option :label="$t('uiAutomation.scheduledTask.scheduleTypes.daily')" value="D" />
            <el-option :label="$t('uiAutomation.scheduledTask.scheduleTypes.weekly')" value="W" />
            <el-option :label="$t('uiAutomation.scheduledTask.scheduleTypes.biweekly')" value="BW" />
            <el-option :label="$t('uiAutomation.scheduledTask.scheduleTypes.monthly')" value="M" />
            <el-option :label="$t('uiAutomation.scheduledTask.scheduleTypes.bimonthly')" value="BM" />
            <el-option :label="$t('uiAutomation.scheduledTask.scheduleTypes.quarterly')" value="Q" />
            <el-option :label="$t('uiAutomation.scheduledTask.scheduleTypes.yearly')" value="Y" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-select v-model="filters.status" :placeholder="$t('uiAutomation.scheduledTask.status')" clearable>
            <el-option :label="$t('uiAutomation.scheduledTask.statusTypes.active')" value="ACTIVE" />
            <el-option :label="$t('uiAutomation.scheduledTask.statusTypes.paused')" value="PAUSED" />
            <el-option :label="$t('uiAutomation.scheduledTask.statusTypes.completed')" value="COMPLETED" />
            <el-option :label="$t('uiAutomation.scheduledTask.statusTypes.failed')" value="FAILED" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-button @click="resetFilters">{{ $t('uiAutomation.common.reset') }}</el-button>
          <el-button type="primary" @click="loadTasks">{{ $t('uiAutomation.common.search') }}</el-button>
        </el-col>
      </el-row>
    </div>

    <!-- 任务列表 -->
    <div class="task-list">
      <el-table :data="tasks" v-loading="loading">
        <el-table-column prop="name" :label="$t('uiAutomation.scheduledTask.taskName')" min-width="200" />
        <el-table-column prop="task_type" :label="$t('uiAutomation.scheduledTask.taskType')" width="120">
          <template #default="scope">
            <el-tag :type="scope.row.task_type === 'UI_TEST_SUITE' ? 'success' : 'primary'">
              {{ scope.row.task_type_display || scope.row.task_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="notification_type_display" :label="$t('uiAutomation.scheduledTask.notificationType')" width="120">
          <template #default="scope">
            <el-tag v-if="scope.row.notification_type_display && scope.row.notification_type_display !== '未配置'" 
                    :type="getNotificationTypeTag(scope.row.notification_type_display)"
                    size="small">
              {{ scope.row.notification_type_display }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="schedule_type_display" :label="$t('uiAutomation.scheduledTask.triggerType')" width="120">
          <template #default="scope">
            <el-tag>
              {{ scope.row.schedule_type_display || getScheduleTypeText(scope.row.schedule_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status_display" :label="$t('uiAutomation.scheduledTask.status')" width="100">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status_display)">
              {{ scope.row.status_display }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="engine" :label="$t('uiAutomation.scheduledTask.executionEngine')" width="120">
          <template #default="scope">
            <el-tag size="small" type="info">
              {{ scope.row.engine === 'playwright' ? 'Playwright' : 'Selenium' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="browser" :label="$t('uiAutomation.scheduledTask.browser')" width="100">
          <template #default="scope">
            {{ scope.row.browser || 'chrome' }}
          </template>
        </el-table-column>
        <el-table-column prop="next_run_display" :label="$t('uiAutomation.scheduledTask.nextRunTime')" width="180">
          <template #default="scope">
            {{ scope.row.next_run_display || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="last_run_display" :label="$t('uiAutomation.scheduledTask.lastRunTime')" width="180">
          <template #default="scope">
            {{ scope.row.last_run_display || '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('uiAutomation.common.operation')" width="200" fixed="right">
          <template #default="scope">
            <el-button size="small" @click="runTaskNow(scope.row)" :loading="scope.row.running">
              {{ $t('uiAutomation.scheduledTask.runNow') }}
            </el-button>
            <el-dropdown @command="(command) => handleTaskAction(command, scope.row)">
              <el-button size="small">
                {{ $t('uiAutomation.scheduledTask.more') }}<el-icon><arrow-down /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">{{ $t('uiAutomation.scheduledTask.actions.edit') }}</el-dropdown-item>
                  <el-dropdown-item command="pause" v-if="scope.row.status === 'ACTIVE'">{{ $t('uiAutomation.scheduledTask.actions.pause') }}</el-dropdown-item>
                  <el-dropdown-item command="resume" v-if="scope.row.status === 'PAUSED'">{{ $t('uiAutomation.scheduledTask.actions.resume') }}</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>{{ $t('uiAutomation.scheduledTask.actions.delete') }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页 -->
    <div class="pagination">
      <el-pagination
        v-model:current-page="pagination.current"
        v-model:page-size="pagination.size"
        :total="pagination.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="loadTasks"
        @current-change="loadTasks"
      />
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingTask ? $t('uiAutomation.scheduledTask.editTask') : $t('uiAutomation.scheduledTask.createTask')"
      width="800px"
      :close-on-click-modal="false"
      @close="resetTaskForm"
    >
      <el-form :model="taskForm" label-width="120px">
        <el-form-item :label="$t('uiAutomation.scheduledTask.taskName')" required>
          <el-input v-model="taskForm.name" :placeholder="$t('uiAutomation.scheduledTask.taskNamePlaceholder')" />
        </el-form-item>

        <el-form-item :label="$t('uiAutomation.scheduledTask.taskDesc')">
          <el-input v-model="taskForm.description" type="textarea" :placeholder="$t('uiAutomation.scheduledTask.taskDescPlaceholder')" />
        </el-form-item>

        <el-form-item :label="$t('uiAutomation.scheduledTask.relatedProject')" required>
          <el-select v-model="taskForm.project" :placeholder="$t('uiAutomation.scheduledTask.selectProject')" @change="onProjectChange">
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('uiAutomation.scheduledTask.taskType')" required>
          <el-radio-group v-model="taskForm.task_type" @change="onTaskTypeChange">
            <el-radio value="UI_TEST_SUITE">{{ $t('uiAutomation.scheduledTask.taskTypes.testSuite') }}</el-radio>
            <el-radio value="UI_TEST_CASE">{{ $t('uiAutomation.scheduledTask.taskTypes.testCase') }}</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 根据任务类型显示不同配置 - 移到任务类型下面 -->
        <el-form-item v-if="taskForm.task_type === 'UI_TEST_SUITE'" :label="$t('uiAutomation.scheduledTask.testSuite')" required>
          <el-select v-model="taskForm.test_suite" :placeholder="$t('uiAutomation.scheduledTask.selectSuite')">
            <el-option
              v-for="suite in testSuites"
              :key="suite.id"
              :label="suite.name"
              :value="suite.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-if="taskForm.task_type === 'UI_TEST_CASE'" :label="$t('uiAutomation.scheduledTask.testCase')" required>
          <el-select
            v-model="taskForm.test_cases"
            multiple
            filterable
            :placeholder="$t('uiAutomation.scheduledTask.selectTestCase')"
          >
            <el-option
              v-for="testCase in testCases"
              :key="testCase.id"
              :label="testCase.name"
              :value="testCase.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('uiAutomation.scheduledTask.triggerType')" required>
          <el-radio-group v-model="taskForm.schedule_type">
            <el-radio value="C">{{ $t('uiAutomation.scheduledTask.scheduleTypes.cron') }}</el-radio>
            <el-radio value="O">{{ $t('uiAutomation.scheduledTask.scheduleTypes.once') }}</el-radio>
            <el-radio value="I">{{ $t('uiAutomation.scheduledTask.scheduleTypes.interval') }}</el-radio>
            <el-radio value="H">{{ $t('uiAutomation.scheduledTask.scheduleTypes.hourly') }}</el-radio>
            <el-radio value="D">{{ $t('uiAutomation.scheduledTask.scheduleTypes.daily') }}</el-radio>
            <el-radio value="W">{{ $t('uiAutomation.scheduledTask.scheduleTypes.weekly') }}</el-radio>
            <el-radio value="BW">{{ $t('uiAutomation.scheduledTask.scheduleTypes.biweekly') }}</el-radio>
            <el-radio value="M">{{ $t('uiAutomation.scheduledTask.scheduleTypes.monthly') }}</el-radio>
            <el-radio value="BM">{{ $t('uiAutomation.scheduledTask.scheduleTypes.bimonthly') }}</el-radio>
            <el-radio value="Q">{{ $t('uiAutomation.scheduledTask.scheduleTypes.quarterly') }}</el-radio>
            <el-radio value="Y">{{ $t('uiAutomation.scheduledTask.scheduleTypes.yearly') }}</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 根据触发器类型显示不同配置 -->
        <el-form-item v-if="taskForm.schedule_type === 'C'" :label="$t('uiAutomation.scheduledTask.cronExpression')" required>
          <el-input v-model="taskForm.cron" :placeholder="$t('uiAutomation.scheduledTask.cronPlaceholder')" />
          <div class="cron-help">
            <el-tooltip raw-content placement="top">
              <template #content>
                <div style="line-height: 1.6; text-align: left;">
                  <div>{{ $t('uiAutomation.scheduledTask.cronHelp.format') }}</div>
                  <div>{{ $t('uiAutomation.scheduledTask.cronHelp.minute') }}</div>
                  <div>{{ $t('uiAutomation.scheduledTask.cronHelp.hour') }}</div>
                  <div>{{ $t('uiAutomation.scheduledTask.cronHelp.day') }}</div>
                  <div>{{ $t('uiAutomation.scheduledTask.cronHelp.month') }}</div>
                  <div>{{ $t('uiAutomation.scheduledTask.cronHelp.week') }}</div>
                  <div style="margin-top: 8px;">{{ $t('uiAutomation.scheduledTask.cronHelp.examples') }}</div>
                  <div>{{ $t('uiAutomation.scheduledTask.cronHelp.everyDay') }}</div>
                  <div>{{ $t('uiAutomation.scheduledTask.cronHelp.everyHour') }}</div>
                  <div>{{ $t('uiAutomation.scheduledTask.cronHelp.everyMonday') }}</div>
                  <div>{{ $t('uiAutomation.scheduledTask.cronHelp.everyMonth') }}</div>
                </div>
              </template>
              <span style="cursor: pointer; color: #409EFF;">{{ $t('uiAutomation.scheduledTask.cronHelpLink') }}</span>
            </el-tooltip>
          </div>
        </el-form-item>

        <el-form-item v-if="taskForm.schedule_type === 'I'" :label="$t('uiAutomation.scheduledTask.intervalMinutes')" required>
          <el-input-number v-model="taskForm.minutes" :min="1" />
          <span class="unit">{{ $t('uiAutomation.scheduledTask.minutes') }}</span>
        </el-form-item>

        <el-form-item v-if="taskForm.schedule_type === 'O'" :label="$t('uiAutomation.scheduledTask.executeTime')" required>
          <el-date-picker
            v-model="taskForm.next_run"
            type="datetime"
            :placeholder="$t('uiAutomation.scheduledTask.selectExecuteTime')"
          />
        </el-form-item>

        <!-- 每小时 -->
        <el-form-item v-if="taskForm.schedule_type === 'H'" :label="$t('uiAutomation.scheduledTask.executeMinute')" required>
          <el-select v-model="taskForm.hour_minute" :placeholder="$t('uiAutomation.scheduledTask.selectMinute')" style="width: 120px;">
            <el-option v-for="i in 60" :key="i-1" :label="i-1" :value="i-1" />
          </el-select>
          <span class="unit">{{ $t('uiAutomation.scheduledTask.unit.minute') }}</span>
        </el-form-item>

        <!-- 每天 -->
        <el-form-item v-if="taskForm.schedule_type === 'D'" :label="$t('uiAutomation.scheduledTask.executeTime')" required>
          <el-time-picker v-model="taskForm.daily_time" :placeholder="$t('uiAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每周 -->
        <el-form-item v-if="taskForm.schedule_type === 'W'" :label="$t('uiAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.weekly_day" :placeholder="$t('uiAutomation.scheduledTask.selectWeekday')" style="width: 120px; margin-right: 10px;">
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.sunday')" value="0" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.monday')" value="1" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.tuesday')" value="2" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.wednesday')" value="3" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.thursday')" value="4" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.friday')" value="5" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.saturday')" value="6" />
          </el-select>
          <el-time-picker v-model="taskForm.weekly_time" :placeholder="$t('uiAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 双周 -->
        <el-form-item v-if="taskForm.schedule_type === 'BW'" :label="$t('uiAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.biweekly_day" :placeholder="$t('uiAutomation.scheduledTask.selectWeekday')" style="width: 120px; margin-right: 10px;">
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.sunday')" value="0" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.monday')" value="1" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.tuesday')" value="2" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.wednesday')" value="3" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.thursday')" value="4" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.friday')" value="5" />
            <el-option :label="$t('uiAutomation.scheduledTask.weekdays.saturday')" value="6" />
          </el-select>
          <el-time-picker v-model="taskForm.biweekly_time" :placeholder="$t('uiAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每月 -->
        <el-form-item v-if="taskForm.schedule_type === 'M'" :label="$t('uiAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.monthly_date" :placeholder="$t('uiAutomation.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="taskForm.monthly_time" :placeholder="$t('uiAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 双月 -->
        <el-form-item v-if="taskForm.schedule_type === 'BM'" :label="$t('uiAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.bimonthly_date" :placeholder="$t('uiAutomation.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="taskForm.bimonthly_time" :placeholder="$t('uiAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每季度 -->
        <el-form-item v-if="taskForm.schedule_type === 'Q'" :label="$t('uiAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.quarterly_month" :placeholder="$t('uiAutomation.scheduledTask.selectMonth')" style="width: 100px; margin-right: 10px;">
            <el-option :label="`${1}${$t('uiAutomation.scheduledTask.unit.month')}`" value="1" />
            <el-option :label="`${4}${$t('uiAutomation.scheduledTask.unit.month')}`" value="4" />
            <el-option :label="`${7}${$t('uiAutomation.scheduledTask.unit.month')}`" value="7" />
            <el-option :label="`${10}${$t('uiAutomation.scheduledTask.unit.month')}`" value="10" />
          </el-select>
          <el-select v-model="taskForm.quarterly_date" :placeholder="$t('uiAutomation.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="taskForm.quarterly_time" :placeholder="$t('uiAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每年 -->
        <el-form-item v-if="taskForm.schedule_type === 'Y'" :label="$t('uiAutomation.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.yearly_month" :placeholder="$t('uiAutomation.scheduledTask.selectMonth')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 12" :key="i" :label="i" :value="i" />
          </el-select>
          <el-select v-model="taskForm.yearly_date" :placeholder="$t('uiAutomation.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="taskForm.yearly_time" :placeholder="$t('uiAutomation.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <el-form-item :label="$t('uiAutomation.scheduledTask.executionEngine')" required>
          <el-radio-group v-model="taskForm.engine">
            <el-radio value="playwright">Playwright</el-radio>
            <el-radio value="selenium">Selenium</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item :label="$t('uiAutomation.scheduledTask.browserType')" required>
          <el-select v-model="taskForm.browser" :placeholder="$t('uiAutomation.scheduledTask.selectBrowser')">
            <el-option label="Chrome" value="chrome" />
            <el-option label="Firefox" value="firefox" />
            <el-option label="Edge" value="edge" />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('uiAutomation.scheduledTask.runMode')">
          <el-checkbox v-model="taskForm.headless">{{ $t('uiAutomation.scheduledTask.headlessMode') }}</el-checkbox>
        </el-form-item>

        <el-form-item :label="$t('uiAutomation.scheduledTask.notificationSettings')">
          <el-checkbox v-model="taskForm.notify_on_success">{{ $t('uiAutomation.scheduledTask.notifyOnSuccess') }}</el-checkbox>
          <el-checkbox v-model="taskForm.notify_on_failure">{{ $t('uiAutomation.scheduledTask.notifyOnFailure') }}</el-checkbox>
        </el-form-item>

        <el-form-item v-if="taskForm.notify_on_success || taskForm.notify_on_failure" :label="$t('uiAutomation.scheduledTask.notificationType')">
          <el-checkbox v-model="taskForm.notify_on_email">{{ $t('uiAutomation.scheduledTask.notifyOnEmail') }}</el-checkbox>
          <el-checkbox v-model="taskForm.notify_on_webhook">{{ $t('uiAutomation.scheduledTask.notifyOnWebhook') }}</el-checkbox>
        </el-form-item>

        <el-form-item v-if="taskForm.notify_on_email || taskForm.notify_on_webhook" :label="$t('uiAutomation.scheduledTask.notificationConfig')">
          <el-select 
            v-model="taskForm.notification_config_ids" 
            :placeholder="$t('uiAutomation.scheduledTask.selectNotificationConfig')"
            filterable
            clearable
            multiple
            style="width: 100%"
          >
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
            {{ $t('uiAutomation.scheduledTask.noMatchingNotificationConfig') }}
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">{{ $t('uiAutomation.common.cancel') }}</el-button>
        <el-button type="primary" @click="submitTaskForm" :loading="submitting">
          {{ editingTask ? $t('uiAutomation.messages.success.update') : $t('uiAutomation.messages.success.create') }}
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
  getUiProjects,
  getTestSuites,
  getTestCases,
  getUiUsers
} from '@/api/ui_automation.js'
import { getUnifiedNotificationConfigs } from '@/api/core'

const { t, locale } = useI18n()

// 数据状态
const tasks = ref([])
const projects = ref([])
const testSuites = ref([])
const testCases = ref([])
const users = ref([])
const loading = ref(false)
const submitting = ref(false)
const showCreateDialog = ref(false)
const editingTask = ref(null)
const notificationConfigs = ref([])
const isInitializingForm = ref(false) // 标记是否正在初始化表单

const filteredNotificationConfigs = computed(() => {
  const notifyOnEmail = taskForm.notify_on_email
  const notifyOnWebhook = taskForm.notify_on_webhook
  
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

// 筛选条件
const filters = reactive({
  task_type: '',
  schedule_type: '',
  status: ''
})

// 分页配置
const pagination = reactive({
  current: 1,
  size: 10,
  total: 0
})

// 表单数据
const taskForm = reactive({
  name: '',
  description: '',
  project: '',
  task_type: 'UI_TEST_SUITE',
  schedule_type: 'C',
  cron: '0 0 * * *',
  minutes: 60,
  next_run: '',
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
  test_suite: '',
  test_cases: [],
  engine: 'playwright',
  browser: 'chrome',
  headless: false,
  notify_on_success: false,
  notify_on_failure: true,
  notify_on_email: false,
  notify_on_webhook: false,
  notification_config_ids: []
})

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

// 获取状态文本
const getStatusText = (status) => {
  const statusMap = {
    'ACTIVE': t('uiAutomation.scheduledTask.statusTypes.active'),
    'PAUSED': t('uiAutomation.scheduledTask.statusTypes.paused'),
    'COMPLETED': t('uiAutomation.scheduledTask.statusTypes.completedShort'),
    'FAILED': t('uiAutomation.scheduledTask.statusTypes.failed')
  }
  return statusMap[status] || status
}

const getStatusType = (status) => {
  if (status === '激活' || status === 'ACTIVE') return 'success'
  if (status === '暂停' || status === 'PAUSED') return 'warning'
  if (status === '失败' || status === 'FAILED') return 'danger'
  return 'info'
}

// 生命周期
onMounted(() => {
  loadTasks()
  loadProjects()
  loadUsers()
  loadNotificationConfigs()
})

const loadNotificationConfigs = async () => {
  try {
    const response = await getUnifiedNotificationConfigs()
    notificationConfigs.value = response.data.results || response.data || []
  } catch (error) {
    console.error('加载通知配置失败:', error)
  }
}

// 加载任务列表
const loadTasks = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.current,
      page_size: pagination.size,
      module: 'UI',
      ...filters
    }
    const response = await getSchedulerSchedules(params)
    tasks.value = response.data.results || response.data
    pagination.total = response.data.count || tasks.value.length
  } catch (error) {
    ElMessage.error(t('uiAutomation.scheduledTask.messages.loadFailed'))
  } finally {
    loading.value = false
  }
}

// 加载项目列表
const loadProjects = async () => {
  try {
    const response = await getUiProjects()
    projects.value = response.data.results
  } catch (error) {
    console.error('Load projects failed:', error)
  }
}

// 加载用户列表
const loadUsers = async () => {
  try {
    const response = await getUiUsers()
    // 处理分页数据结构
    const usersData = response.data.results || response.data
    users.value = usersData.map(user => ({
      ...user,
      display_name: user.first_name ? `${user.first_name}（${user.email}）` : `${user.username}（${user.email}）`
    }))
  } catch (error) {
    console.error('Load users failed:', error)
  }
}

// 项目变化时加载对应的套件和用例
const onProjectChange = async (projectId) => {
  if (!projectId) return

  try {
    // 加载测试套件
    const suitesResponse = await getTestSuites({ project: projectId })
    testSuites.value = suitesResponse.data.results

    // 加载测试用例
    const casesResponse = await getTestCases({ project: projectId })
    testCases.value = casesResponse.data.results
  } catch (error) {
    console.error('Load project data failed:', error)
  }
}

// 任务类型变化
const onTaskTypeChange = () => {
  taskForm.test_suite = ''
  taskForm.test_cases = []
}

// 新建按钮点击
const handleCreateClick = () => {
  editingTask.value = null
  resetTaskForm()
  showCreateDialog.value = true
}

// 重置表单
const resetTaskForm = () => {
  Object.assign(taskForm, {
    name: '',
    description: '',
    project: '',
    task_type: 'UI_TEST_SUITE',
    schedule_type: 'C',
    cron: '0 0 * * *',
    minutes: 60,
    next_run: '',
    test_suite: '',
    test_cases: [],
    engine: 'playwright',
    browser: 'chrome',
    headless: false,
    notify_on_email: false,
    notify_on_webhook: false,
    webhook_url: '',
    notification_config_ids: []
  })
}

// 重置筛选
const resetFilters = () => {
  Object.assign(filters, {
    task_type: '',
    schedule_type: '',
    status: ''
  })
  loadTasks()
}

// 提交任务表单
const submitTaskForm = async () => {
  // 验证必填字段
  if (!taskForm.name) {
    ElMessage.error(t('uiAutomation.scheduledTask.messages.nameRequired'))
    return
  }
  
  if (!taskForm.schedule_type) {
    ElMessage.error(t('uiAutomation.scheduledTask.messages.scheduleTypeRequired'))
    return
  }
  
  // 根据任务类型验证必填字段
  if (taskForm.task_type === 'UI_TEST_SUITE' && !taskForm.test_suite) {
    ElMessage.error(t('uiAutomation.scheduledTask.messages.testSuiteRequired'))
    return
  }
  
  if (taskForm.task_type === 'UI_TEST_CASE' && (!taskForm.test_cases || taskForm.test_cases.length === 0)) {
    ElMessage.error(t('uiAutomation.scheduledTask.messages.testCaseRequired'))
    return
  }
  
  // 验证触发器类型必填字段
  if (taskForm.schedule_type === 'C' && !taskForm.cron) {
    ElMessage.error(t('uiAutomation.scheduledTask.messages.cronRequired'))
    return
  }
  
  if (taskForm.schedule_type === 'I' && !taskForm.minutes) {
    ElMessage.error(t('uiAutomation.scheduledTask.messages.minutesRequired'))
    return
  }
  
  if (taskForm.schedule_type === 'O' && !taskForm.next_run) {
    ElMessage.error(t('uiAutomation.scheduledTask.messages.nextRunRequired'))
    return
  }

  submitting.value = true
  try {
    const submitData = {
      name: taskForm.name,
      description: taskForm.description,
      module: 'UI',
      task_type: taskForm.task_type,
      schedule_type: taskForm.schedule_type,
      project_id: taskForm.project,
      task_config: {
        engine: taskForm.engine,
        browser: taskForm.browser,
        headless: taskForm.headless
      },
      notify_on_success: taskForm.notify_on_success,
      notify_on_failure: taskForm.notify_on_failure,
      notify_on_email: taskForm.notify_on_email,
      notify_on_webhook: taskForm.notify_on_webhook,
      notification_config_ids: taskForm.notification_config_ids
    }

    // 根据触发器类型添加对应字段
    if (taskForm.schedule_type === 'C') {
      submitData.cron = taskForm.cron
    } else if (taskForm.schedule_type === 'I') {
      submitData.minutes = taskForm.minutes
    } else if (taskForm.schedule_type === 'O') {
      submitData.next_run = taskForm.next_run
    } else if (taskForm.schedule_type === 'H') {
      // 每小时：指定分钟
      const minute = taskForm.hour_minute || 0
      submitData.cron = `${minute} * * * *`
    } else if (taskForm.schedule_type === 'D') {
      // 每天：指定时间
      if (taskForm.daily_time) {
        const time = taskForm.daily_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        submitData.cron = `${minute} ${hour} * * *`
      } else {
        submitData.cron = '0 0 * * *' // 默认每天0点
      }
    } else if (taskForm.schedule_type === 'W') {
      // 每周：指定星期和时间
      if (taskForm.weekly_time) {
        const time = taskForm.weekly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const day = taskForm.weekly_day || 1
        submitData.cron = `${minute} ${hour} * * ${day}`
      } else {
        submitData.cron = '0 0 * * 1' // 默认每周一0点
      }
    } else if (taskForm.schedule_type === 'BW') {
      // 双周：使用cron表达式，实际上是每两周的指定时间
      if (taskForm.biweekly_time) {
        const time = taskForm.biweekly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const day = taskForm.biweekly_day || 1
        submitData.cron = `${minute} ${hour} * * ${day}`
      } else {
        submitData.cron = '0 0 * * 1' // 默认双周周一0点
      }
    } else if (taskForm.schedule_type === 'M') {
      // 每月：指定日期和时间
      if (taskForm.monthly_time) {
        const time = taskForm.monthly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const date = taskForm.monthly_date || 1
        submitData.cron = `${minute} ${hour} ${date} * *`
      } else {
        submitData.cron = '0 0 1 * *' // 默认每月1号0点
      }
    } else if (taskForm.schedule_type === 'BM') {
      // 双月：使用cron表达式，实际上是每两个月的指定时间
      if (taskForm.bimonthly_time) {
        const time = taskForm.bimonthly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const date = taskForm.bimonthly_date || 1
        submitData.cron = `${minute} ${hour} ${date} */2 *`
      } else {
        submitData.cron = '0 0 1 */2 *' // 默认双月1号0点
      }
    } else if (taskForm.schedule_type === 'Q') {
      // 每季度：指定月份日期和时间
      if (taskForm.quarterly_time) {
        const time = taskForm.quarterly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const date = taskForm.quarterly_date || 1
        const month = taskForm.quarterly_month || 1
        submitData.cron = `${minute} ${hour} ${date} ${month} *`
      } else {
        submitData.cron = '0 0 1 1 *' // 默认每年1月1号0点
      }
    } else if (taskForm.schedule_type === 'Y') {
      // 每年：指定月份日期和时间
      if (taskForm.yearly_time) {
        const time = taskForm.yearly_time
        const hour = time.getHours().toString().padStart(2, '0')
        const minute = time.getMinutes().toString().padStart(2, '0')
        const date = taskForm.yearly_date || 1
        const month = taskForm.yearly_month || 1
        submitData.cron = `${minute} ${hour} ${date} ${month} *`
      } else {
        submitData.cron = '0 0 1 1 *' // 默认每年1月1号0点
      }
    }

    // 根据任务类型添加对应字段
    if (taskForm.task_type === 'UI_TEST_SUITE') {
      submitData.target_id = taskForm.test_suite
    } else if (taskForm.task_type === 'UI_TEST_CASE') {
      submitData.target_id = taskForm.test_cases[0]
    }

    if (editingTask.value) {
      await updateSchedulerSchedule(editingTask.value.id, submitData)
      ElMessage.success(t('uiAutomation.scheduledTask.messages.updateSuccess'))
    } else {
      await createSchedulerSchedule(submitData)
      ElMessage.success(t('uiAutomation.scheduledTask.messages.createSuccess'))
    }
    showCreateDialog.value = false
    loadTasks()
  } catch (error) {
    console.error('Task operation failed:', error)
    ElMessage.error(error.response?.data?.error ||
                   error.response?.data?.detail ||
                   (editingTask.value ? t('uiAutomation.scheduledTask.messages.updateFailed') : t('uiAutomation.scheduledTask.messages.createFailed')))
  } finally {
    submitting.value = false
  }
}

// 立即执行任务
const runTaskNow = async (task) => {
  try {
    task.running = true
    await executeSchedulerSchedule(task.id)
    ElMessage.success(t('uiAutomation.scheduledTask.messages.runSuccess'))
    setTimeout(() => {
      loadTasks()
    }, 2000)
  } catch (error) {
    ElMessage.error(t('uiAutomation.scheduledTask.messages.runFailed'))
  } finally {
    task.running = false
  }
}

// 格式化日期时间
const formatDateTime = (dateString) => {
  if (!dateString) return '-'
  const date = new Date(dateString)
  const localeStr = locale.value === 'en' ? 'en-US' : 'zh-CN'
  return date.toLocaleString(localeStr, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }).replace(/\//g, '-')
}

// 处理任务操作
const handleTaskAction = (command, task) => {
  switch (command) {
    case 'pause':
      pauseTask(task)
      break
    case 'resume':
      resumeTask(task)
      break
    case 'edit':
      editTask(task)
      break
    case 'delete':
      deleteTask(task)
      break
  }
}

// 编辑任务
const editTask = async (task) => {
  editingTask.value = task
  isInitializingForm.value = true // 标记开始初始化表单
  
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
  
  Object.assign(taskForm, {
    name: task.name,
    description: task.description || '',
    project: task.config?.project_id || '',
    task_type: task.config?.task_type || 'UI_TEST_SUITE',
    schedule_type: task.schedule_type || 'C',
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
    test_suite: task.config?.target_id || '',
    test_cases: task.config?.target_id ? [task.config.target_id] : [],
    engine: task.engine || 'playwright',
    browser: task.browser || 'chrome',
    headless: task.config?.task_config?.headless || false,
    notification_config_ids: task.config?.notification_config_ids || [],
    notify_on_success: task.config?.notify_on_success ?? false,
    notify_on_failure: task.config?.notify_on_failure ?? true,
    notify_on_email: task.config?.notify_on_email ?? false,
    notify_on_webhook: task.config?.notify_on_webhook ?? false
  })

  // 加载项目相关数据
  if (task.config?.project_id) {
    await onProjectChange(task.config.project_id)
  }

  showCreateDialog.value = true
  
  // 等待表单初始化完成后，重置标志
  nextTick(() => {
    isInitializingForm.value = false
  })
}

// 监听通知类型变化，过滤不匹配的通知配置
watch([() => taskForm.notify_on_email, () => taskForm.notify_on_webhook], () => {
  // 如果正在初始化表单，跳过过滤逻辑
  if (isInitializingForm.value) {
    return
  }
  
  nextTick(() => {
    const notifyOnEmail = taskForm.notify_on_email
    const notifyOnWebhook = taskForm.notify_on_webhook
    
    if (!notifyOnEmail && !notifyOnWebhook) {
      taskForm.notification_config_ids = []
      return
    }
    
    taskForm.notification_config_ids = taskForm.notification_config_ids.filter(id => {
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

// 暂停任务
const pauseTask = async (task) => {
  try {
    await toggleSchedulerSchedule(task.id, 'pause')
    ElMessage.success(t('uiAutomation.scheduledTask.messages.pauseSuccess'))
    loadTasks()
  } catch (error) {
    console.error('Pause task failed:', error)
    ElMessage.error(t('uiAutomation.scheduledTask.messages.pauseFailed'))
  }
}

// 恢复任务
const resumeTask = async (task) => {
  try {
    await toggleSchedulerSchedule(task.id, 'resume')
    ElMessage.success(t('uiAutomation.scheduledTask.messages.resumeSuccess'))
    loadTasks()
  } catch (error) {
    ElMessage.error(t('uiAutomation.scheduledTask.messages.resumeFailed'))
  }
}

// 删除任务
const deleteTask = async (task) => {
  try {
    await ElMessageBox.confirm(t('uiAutomation.scheduledTask.messages.deleteConfirm'), t('uiAutomation.scheduledTask.messages.deleteConfirmTitle'), {
      confirmButtonText: t('uiAutomation.common.confirm'),
      cancelButtonText: t('uiAutomation.common.cancel'),
      type: 'warning'
    })
    await deleteSchedulerSchedule(task.id)
    ElMessage.success(t('uiAutomation.scheduledTask.messages.deleteSuccess'))
    loadTasks()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(t('uiAutomation.scheduledTask.messages.deleteFailed'))
    }
  }
}
</script>

<style scoped>
.scheduled-tasks {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.filters {
  margin-bottom: 20px;
  background: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
}

.task-list {
  flex: 1;
  overflow: hidden;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.cron-help {
  margin-top: 8px;
  font-size: 12px;
}

.unit {
  margin-left: 8px;
  color: #606266;
}
</style>
