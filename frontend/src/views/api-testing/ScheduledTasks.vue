<template>
  <div class="scheduled-tasks">
    <div class="header">
      <h3>{{ $t('apiTesting.scheduledTask.title') }}</h3>
      <el-button type="primary" @click="handleCreateClick">
        <el-icon><Plus /></el-icon>
        {{ $t('apiTesting.scheduledTask.createTask') }}
      </el-button>
    </div>

    <!-- 筛选条件 -->
    <div class="filters">
      <el-row :gutter="20">
        <el-col :span="6">
          <el-select v-model="filters.task_type" :placeholder="$t('apiTesting.scheduledTask.taskType')" clearable>
            <el-option :label="$t('apiTesting.scheduledTask.taskTypes.testSuite')" value="API_TEST_SUITE" />
            <el-option :label="$t('apiTesting.scheduledTask.taskTypes.apiRequest')" value="API_REQUEST" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-select v-model="filters.schedule_type" :placeholder="$t('apiTesting.scheduledTask.triggerType')" clearable>
            <el-option :label="$t('apiTesting.scheduledTask.scheduleTypes.cron')" value="C" />
            <el-option :label="$t('apiTesting.scheduledTask.scheduleTypes.once')" value="O" />
            <el-option :label="$t('apiTesting.scheduledTask.scheduleTypes.interval')" value="I" />
            <el-option :label="$t('apiTesting.scheduledTask.scheduleTypes.hourly')" value="H" />
            <el-option :label="$t('apiTesting.scheduledTask.scheduleTypes.daily')" value="D" />
            <el-option :label="$t('apiTesting.scheduledTask.scheduleTypes.weekly')" value="W" />
            <el-option :label="$t('apiTesting.scheduledTask.scheduleTypes.biweekly')" value="BW" />
            <el-option :label="$t('apiTesting.scheduledTask.scheduleTypes.monthly')" value="M" />
            <el-option :label="$t('apiTesting.scheduledTask.scheduleTypes.bimonthly')" value="BM" />
            <el-option :label="$t('apiTesting.scheduledTask.scheduleTypes.quarterly')" value="Q" />
            <el-option :label="$t('apiTesting.scheduledTask.scheduleTypes.yearly')" value="Y" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-select v-model="filters.status" :placeholder="$t('apiTesting.scheduledTask.taskStatus')" clearable>
            <el-option :label="$t('apiTesting.scheduledTask.status.active')" value="ACTIVE" />
            <el-option :label="$t('apiTesting.scheduledTask.status.paused')" value="PAUSED" />
            <el-option :label="$t('apiTesting.scheduledTask.status.completed')" value="COMPLETED" />
            <el-option :label="$t('apiTesting.scheduledTask.status.failed')" value="FAILED" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-button @click="resetFilters">{{ $t('apiTesting.common.reset') }}</el-button>
          <el-button type="primary" @click="loadTasks">{{ $t('apiTesting.common.search') }}</el-button>
        </el-col>
      </el-row>
    </div>

    <!-- 任务列表 -->
    <div class="task-list">
      <el-table :data="tasks" v-loading="loading">
        <el-table-column prop="name" :label="$t('apiTesting.scheduledTask.taskName')" min-width="180" />
        <el-table-column prop="task_type_display" :label="$t('apiTesting.scheduledTask.taskType')" width="150">
          <template #default="scope">
            <el-tag :type="scope.row.task_type === 'API_TEST_SUITE' ? 'success' : 'primary'">
              {{ scope.row.task_type_display || scope.row.task_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="schedule_type_display" :label="$t('apiTesting.scheduledTask.triggerType')" width="120">
          <template #default="scope">
            <el-tag>
              {{ scope.row.schedule_type_display || getScheduleTypeText(scope.row.schedule_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status_display" :label="$t('apiTesting.common.status')" width="100">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status_display)">
              {{ scope.row.status_display || getStatusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="notification_type_display" :label="$t('apiTesting.scheduledTask.notificationType')" width="150">
          <template #default="scope">
            <el-tag
              v-if="scope.row.notification_type_display && scope.row.notification_type_display !== '未配置'"
              :type="getNotificationTypeTag(scope.row.notification_type_display)"
              size="small"
            >
              {{ scope.row.notification_type_display }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="next_run_display" :label="$t('apiTesting.scheduledTask.nextRunTime')" width="180">
          <template #default="scope">
            {{ scope.row.next_run_display || formatDateTime(scope.row.next_run) }}
          </template>
        </el-table-column>
        <el-table-column prop="last_run_display" :label="$t('apiTesting.scheduledTask.lastRunTime')" width="180">
          <template #default="scope">
            {{ scope.row.last_run_display || '-' }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('apiTesting.common.operation')" width="200" fixed="right">
          <template #default="scope">
            <el-button size="small" @click="runTaskNow(scope.row)" :loading="scope.row.running">
              {{ $t('apiTesting.scheduledTask.runNow') }}
            </el-button>
            <el-dropdown @command="(command) => handleTaskAction(command, scope.row)">
              <el-button size="small">
                {{ $t('apiTesting.common.more') }}<el-icon><arrow-down /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">{{ $t('apiTesting.common.edit') }}</el-dropdown-item>
                  <el-dropdown-item command="pause" v-if="scope.row.status === 'ACTIVE'">{{ $t('apiTesting.scheduledTask.pause') }}</el-dropdown-item>
                  <el-dropdown-item command="activate" v-if="scope.row.status === 'PAUSED'">{{ $t('apiTesting.scheduledTask.activate') }}</el-dropdown-item>
                  <el-dropdown-item command="logs">{{ $t('apiTesting.scheduledTask.executionLogs') }}</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>{{ $t('apiTesting.common.delete') }}</el-dropdown-item>
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
      :title="editingTask ? $t('apiTesting.scheduledTask.editTask') : $t('apiTesting.scheduledTask.createTask')"
      width="800px"
      :close-on-click-modal="false"
      @close="resetTaskForm"
    >
      <el-form :model="taskForm" label-width="120px">
        <el-form-item :label="$t('apiTesting.scheduledTask.taskName')" required>
          <el-input v-model="taskForm.name" :placeholder="$t('apiTesting.scheduledTask.inputTaskName')" />
        </el-form-item>

        <el-form-item :label="$t('apiTesting.scheduledTask.taskDescription')">
          <el-input v-model="taskForm.description" type="textarea" :placeholder="$t('apiTesting.scheduledTask.inputTaskDesc')" />
        </el-form-item>

        <el-form-item :label="$t('apiTesting.scheduledTask.taskType')" required>
          <el-radio-group v-model="taskForm.task_type">
            <el-radio value="API_TEST_SUITE">{{ $t('apiTesting.scheduledTask.taskTypes.testSuite') }}</el-radio>
            <el-radio value="API_REQUEST">{{ $t('apiTesting.scheduledTask.taskTypes.apiRequest') }}</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item :label="$t('apiTesting.scheduledTask.triggerType')" required>
          <el-radio-group v-model="taskForm.schedule_type">
            <el-radio value="C">{{ $t('apiTesting.scheduledTask.scheduleTypes.cron') }}</el-radio>
            <el-radio value="O">{{ $t('apiTesting.scheduledTask.scheduleTypes.once') }}</el-radio>
            <el-radio value="I">{{ $t('apiTesting.scheduledTask.scheduleTypes.interval') }}</el-radio>
            <el-radio value="H">{{ $t('apiTesting.scheduledTask.scheduleTypes.hourly') }}</el-radio>
            <el-radio value="D">{{ $t('apiTesting.scheduledTask.scheduleTypes.daily') }}</el-radio>
            <el-radio value="W">{{ $t('apiTesting.scheduledTask.scheduleTypes.weekly') }}</el-radio>
            <el-radio value="BW">{{ $t('apiTesting.scheduledTask.scheduleTypes.biweekly') }}</el-radio>
            <el-radio value="M">{{ $t('apiTesting.scheduledTask.scheduleTypes.monthly') }}</el-radio>
            <el-radio value="BM">{{ $t('apiTesting.scheduledTask.scheduleTypes.bimonthly') }}</el-radio>
            <el-radio value="Q">{{ $t('apiTesting.scheduledTask.scheduleTypes.quarterly') }}</el-radio>
             <el-radio value="Y">{{ $t('apiTesting.scheduledTask.scheduleTypes.yearly') }}</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 根据触发器类型显示不同配置 -->
        <el-form-item v-if="taskForm.schedule_type === 'C'" :label="$t('apiTesting.scheduledTask.cronExpression')" required>
          <el-input v-model="taskForm.cron" placeholder="0 0 * * *" />
          <div class="cron-help">
            <el-tooltip
              raw-content
              placement="top"
            >
              <template #content>
                <div style="line-height: 1.6; text-align: left;">
                  <div>{{ $t('apiTesting.scheduledTask.cronHelp.format') }}</div>
                  <div>• {{ $t('apiTesting.scheduledTask.cronHelp.minute') }}</div>
                  <div>• {{ $t('apiTesting.scheduledTask.cronHelp.hour') }}</div>
                  <div>• {{ $t('apiTesting.scheduledTask.cronHelp.day') }}</div>
                  <div>• {{ $t('apiTesting.scheduledTask.cronHelp.month') }}</div>
                  <div>• {{ $t('apiTesting.scheduledTask.cronHelp.week') }}</div>
                  <div style="margin-top: 8px;">{{ $t('apiTesting.scheduledTask.cronHelp.examples') }}</div>
                  <div>• {{ $t('apiTesting.scheduledTask.cronHelp.daily') }}</div>
                  <div>• {{ $t('apiTesting.scheduledTask.cronHelp.hourly') }}</div>
                  <div>• {{ $t('apiTesting.scheduledTask.cronHelp.weekly') }}</div>
                  <div>• {{ $t('apiTesting.scheduledTask.cronHelp.monthly') }}</div>
                </div>
              </template>
              <span style="cursor: pointer; color: #409EFF;">{{ $t('apiTesting.scheduledTask.cronHelpLink') }}</span>
            </el-tooltip>
          </div>
        </el-form-item>

        <el-form-item v-if="taskForm.schedule_type === 'I'" :label="$t('apiTesting.scheduledTask.intervalMinutes')" required>
          <el-input-number v-model="taskForm.minutes" :min="1" />
          <span class="unit">{{ $t('apiTesting.scheduledTask.minutes') }}</span>
        </el-form-item>

        <el-form-item v-if="taskForm.schedule_type === 'O'" :label="$t('apiTesting.scheduledTask.executeTime')" required>
          <el-date-picker
            v-model="taskForm.next_run"
            type="datetime"
            :placeholder="$t('apiTesting.scheduledTask.selectExecuteTime')"
          />
        </el-form-item>

        <!-- 每小时 -->
        <el-form-item v-if="taskForm.schedule_type === 'H'" :label="$t('apiTesting.scheduledTask.executeMinute')" required>
          <el-select v-model="taskForm.hour_minute" :placeholder="$t('apiTesting.scheduledTask.selectMinute')" style="width: 120px;">
            <el-option v-for="i in 60" :key="i-1" :label="i-1" :value="i-1" />
          </el-select>
          <span class="unit">{{ $t('apiTesting.scheduledTask.unit.minute') }}</span>
        </el-form-item>

        <!-- 每天 -->
        <el-form-item v-if="taskForm.schedule_type === 'D'" :label="$t('apiTesting.scheduledTask.executeTime')" required>
          <el-time-picker v-model="taskForm.daily_time" :placeholder="$t('apiTesting.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每周 -->
        <el-form-item v-if="taskForm.schedule_type === 'W'" :label="$t('apiTesting.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.weekly_day" :placeholder="$t('apiTesting.scheduledTask.selectWeekday')" style="width: 120px; margin-right: 10px;">
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.sunday')" value="0" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.monday')" value="1" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.tuesday')" value="2" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.wednesday')" value="3" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.thursday')" value="4" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.friday')" value="5" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.saturday')" value="6" />
          </el-select>
          <el-time-picker v-model="taskForm.weekly_time" :placeholder="$t('apiTesting.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 双周 -->
        <el-form-item v-if="taskForm.schedule_type === 'BW'" :label="$t('apiTesting.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.biweekly_day" :placeholder="$t('apiTesting.scheduledTask.selectWeekday')" style="width: 120px; margin-right: 10px;">
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.sunday')" value="0" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.monday')" value="1" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.tuesday')" value="2" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.wednesday')" value="3" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.thursday')" value="4" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.friday')" value="5" />
            <el-option :label="$t('apiTesting.scheduledTask.weekdays.saturday')" value="6" />
          </el-select>
          <el-time-picker v-model="taskForm.biweekly_time" :placeholder="$t('apiTesting.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每月 -->
        <el-form-item v-if="taskForm.schedule_type === 'M'" :label="$t('apiTesting.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.monthly_date" :placeholder="$t('apiTesting.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="taskForm.monthly_time" :placeholder="$t('apiTesting.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 双月 -->
        <el-form-item v-if="taskForm.schedule_type === 'BM'" :label="$t('apiTesting.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.bimonthly_date" :placeholder="$t('apiTesting.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="taskForm.bimonthly_time" :placeholder="$t('apiTesting.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每季度 -->
        <el-form-item v-if="taskForm.schedule_type === 'Q'" :label="$t('apiTesting.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.quarterly_month" :placeholder="$t('apiTesting.scheduledTask.selectMonth')" style="width: 100px; margin-right: 10px;">
            <el-option :label="`${1}${$t('apiTesting.scheduledTask.unit.month')}`" value="1" />
            <el-option :label="`${4}${$t('apiTesting.scheduledTask.unit.month')}`" value="4" />
            <el-option :label="`${7}${$t('apiTesting.scheduledTask.unit.month')}`" value="7" />
            <el-option :label="`${10}${$t('apiTesting.scheduledTask.unit.month')}`" value="10" />
          </el-select>
          <el-select v-model="taskForm.quarterly_date" :placeholder="$t('apiTesting.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="taskForm.quarterly_time" :placeholder="$t('apiTesting.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 每年 -->
        <el-form-item v-if="taskForm.schedule_type === 'Y'" :label="$t('apiTesting.scheduledTask.executeTime')" required>
          <el-select v-model="taskForm.yearly_month" :placeholder="$t('apiTesting.scheduledTask.selectMonth')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 12" :key="i" :label="i" :value="i" />
          </el-select>
          <el-select v-model="taskForm.yearly_date" :placeholder="$t('apiTesting.scheduledTask.selectDate')" style="width: 100px; margin-right: 10px;">
            <el-option v-for="i in 31" :key="i" :label="i" :value="i" />
          </el-select>
          <el-time-picker v-model="taskForm.yearly_time" :placeholder="$t('apiTesting.scheduledTask.selectExecuteTime')" />
        </el-form-item>

        <!-- 根据任务类型显示不同配置 -->
        <el-form-item v-if="taskForm.task_type === 'API_TEST_SUITE'" :label="$t('apiTesting.automation.testSuite')" required>
          <el-select v-model="taskForm.test_suite" :placeholder="$t('apiTesting.scheduledTask.selectTestSuite')">
            <el-option
              v-for="suite in testSuites"
              :key="suite.id"
              :label="suite.name"
              :value="suite.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-if="taskForm.task_type === 'API_REQUEST'" :label="$t('apiTesting.scheduledTask.apiRequest')" required>
          <el-select v-model="taskForm.api_request" :placeholder="$t('apiTesting.scheduledTask.selectApiRequest')">
            <el-option
              v-for="request in apiRequests"
              :key="request.id"
              :label="request.name"
              :value="request.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('apiTesting.scheduledTask.executeEnvironment')">
          <el-select v-model="taskForm.environment" :placeholder="$t('apiTesting.scheduledTask.selectEnvironment')">
            <el-option
              v-for="env in environments"
              :key="env.id"
              :label="env.name"
              :value="env.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('apiTesting.scheduledTask.notificationSettings')">
          <el-checkbox v-model="taskForm.notify_on_success">{{ $t('apiTesting.scheduledTask.notifyOnSuccess') }}</el-checkbox>
          <el-checkbox v-model="taskForm.notify_on_failure">{{ $t('apiTesting.scheduledTask.notifyOnFailure') }}</el-checkbox>
        </el-form-item>

        <el-form-item v-if="taskForm.notify_on_success || taskForm.notify_on_failure" :label="$t('apiTesting.scheduledTask.notificationType')">
          <el-checkbox v-model="taskForm.notify_on_email">{{ $t('apiTesting.scheduledTask.notifyOnEmail') }}</el-checkbox>
          <el-checkbox v-model="taskForm.notify_on_webhook">{{ $t('apiTesting.scheduledTask.notifyOnWebhook') }}</el-checkbox>
        </el-form-item>

        <el-form-item v-if="taskForm.notify_on_email || taskForm.notify_on_webhook" :label="$t('apiTesting.scheduledTask.notificationConfig')">
          <el-select v-model="taskForm.notification_config_ids" :placeholder="$t('apiTesting.scheduledTask.selectNotificationConfig')" clearable multiple>
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
            {{ $t('apiTesting.scheduledTask.noMatchingNotificationConfig') }}
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">{{ $t('apiTesting.common.cancel') }}</el-button>
        <el-button type="primary" @click="submitTaskForm" :loading="submitting">
          {{ editingTask ? $t('apiTesting.common.update') : $t('apiTesting.common.create') }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 执行日志对话框 -->
    <el-dialog v-model="showLogsDialog" :title="$t('apiTesting.scheduledTask.executionLogs')" width="1000px">
      <el-table :data="executionLogs" v-loading="logsLoading">
        <el-table-column prop="started" :label="$t('apiTesting.scheduledTask.startTime')" width="180">
          <template #default="scope">
            <div class="time-cell">{{ formatDateTime(scope.row.started) }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="stopped" :label="$t('apiTesting.scheduledTask.endTime')" width="180">
          <template #default="scope">
            <div class="time-cell">{{ formatDateTime(scope.row.stopped) }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="type" :label="$t('apiTesting.common.status')" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.type === 'success' ? 'success' : 'danger'">
              {{ scope.row.type === 'success' ? $t('apiTesting.common.success') : $t('apiTesting.common.failed') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="result" :label="$t('apiTesting.scheduledTask.errorMessage')" width="300" show-overflow-tooltip>
          <template #default="scope">
            {{ scope.row.result || '-' }}
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { Plus, ArrowDown } from '@element-plus/icons-vue'
import api from '@/utils/api'
import {
  getSchedulerSchedules,
  createSchedulerSchedule,
  updateSchedulerSchedule,
  deleteSchedulerSchedule,
  executeSchedulerSchedule,
  toggleSchedulerSchedule,
  getSchedulerHistory,
  getExecutionLogs,
  getTestSuites,
  getApiRequests,
  getEnvironments,
  getUsers
} from '@/api/api-testing.js'
import { getUnifiedNotificationConfigs } from '@/api/core.js'

const { t } = useI18n()

// 获取状态文本
const getStatusText = (status) => {
  const statusKey = {
    'ACTIVE': 'active',
    'PAUSED': 'paused',
    'COMPLETED': 'completed',
    'FAILED': 'failed'
  }[status]
  return statusKey ? t(`apiTesting.scheduledTask.status.${statusKey}`) : status
}

// 获取触发器类型文本
const getTriggerTypeText = (type) => {
  const typeKey = {
    'CRON': 'cron',
    'INTERVAL': 'interval',
    'ONCE': 'once'
  }[type]
  return typeKey ? t(`apiTesting.scheduledTask.triggerTypes.${typeKey}`) : type
}

// 获取调度类型文本
const getScheduleTypeText = (type) => {
  const typeMap = {
    'O': t('apiTesting.scheduledTask.scheduleTypes.once'),
    'I': t('apiTesting.scheduledTask.scheduleTypes.interval'),
    'H': t('apiTesting.scheduledTask.scheduleTypes.hourly'),
    'D': t('apiTesting.scheduledTask.scheduleTypes.daily'),
    'W': t('apiTesting.scheduledTask.scheduleTypes.weekly'),
    'BW': t('apiTesting.scheduledTask.scheduleTypes.biweekly'),
    'M': t('apiTesting.scheduledTask.scheduleTypes.monthly'),
    'BM': t('apiTesting.scheduledTask.scheduleTypes.bimonthly'),
    'Q': t('apiTesting.scheduledTask.scheduleTypes.quarterly'),
    'Y': t('apiTesting.scheduledTask.scheduleTypes.yearly'),
    'C': t('apiTesting.scheduledTask.scheduleTypes.cron')
  }
  return typeMap[type] || type
}

// 数据状态
const tasks = ref([])
const executionLogs = ref([])
const testSuites = ref([])
const apiRequests = ref([])
const environments = ref([])
const users = ref([]) // 添加用户列表
const notificationConfigs = ref([]) // 添加通知配置列表
const loading = ref(false)
const logsLoading = ref(false)
const submitting = ref(false)
const showCreateDialog = ref(false)
const showLogsDialog = ref(false)
const editingTask = ref(null)
const isInitializingForm = ref(false) // 标记是否正在初始化表单

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
  task_type: 'API_TEST_SUITE',
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
  api_request: '',
  environment: '',
  notify_on_success: false,
  notify_on_failure: true,
  notify_on_email: false,
  notify_on_webhook: false,
  notification_config_ids: []
})

// 生命周期
onMounted(() => {
  loadTasks()
  loadTestSuites()
  loadApiRequests()
  loadEnvironments()
  loadUsers() // 加载用户列表
  loadNotificationConfigs() // 加载通知配置列表
})

// 加载任务列表
const loadTasks = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.current,
      page_size: pagination.size,
      module: 'API'
    }
    
    // 只添加非空的筛选条件
    if (filters.task_type) {
      params.task_type = filters.task_type
    }
    if (filters.schedule_type) {
      params.schedule_type = filters.schedule_type
    }
    if (filters.status) {
      params.status = filters.status
    }
    
    const response = await getSchedulerSchedules(params)
    const taskList = response.data.results || response.data
    tasks.value = taskList.map(task => ({
      ...task,
      task_type_display: getTaskTypeDisplay(task.config?.task_type),
      schedule_type_display: getScheduleTypeDisplay(task.schedule_type)
    }))
    pagination.total = response.data.count || tasks.value.length
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.loadTasksFailed'))
  } finally {
    loading.value = false
  }
}

// 加载测试套件
const loadTestSuites = async () => {
  try {
    const response = await getTestSuites()
    testSuites.value = response.data.results
  } catch (error) {
    console.error('加载测试套件失败:', error)
  }
}

// 加载API请求
const loadApiRequests = async () => {
  try {
    const response = await getApiRequests()
    apiRequests.value = response.data.results
  } catch (error) {
    console.error('加载API请求失败:', error)
  }
}

// 加载环境
const loadEnvironments = async () => {
  try {
    const response = await getEnvironments()
    environments.value = response.data.results
  } catch (error) {
    console.error('加载环境失败:', error)
  }
}

// 加载用户列表
const loadUsers = async () => {
  try {
    const response = await getUsers()
    // 处理分页数据结构
    const usersData = response.data.results || response.data
    users.value = usersData.map(user => ({
      ...user,
      display_name: user.first_name ? `${user.first_name}（${user.email}）` : `${user.username}（${user.email}）`
    }))
  } catch (error) {
    console.error('加载用户列表失败:', error)
  }
}

// 加载通知配置列表
const loadNotificationConfigs = async () => {
  try {
    const response = await getUnifiedNotificationConfigs()
    notificationConfigs.value = response.data.results || response.data
  } catch (error) {
    console.error('加载通知配置列表失败:', error)
  }
}

// 过滤通知配置列表
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

// 新建按钮点击
const handleCreateClick = () => {
  console.log('新建按钮点击')
  editingTask.value = null
  resetTaskForm()
  showCreateDialog.value = true
}

// 重置表单
const resetTaskForm = () => {
  Object.assign(taskForm, {
    name: '',
    description: '',
    task_type: 'API_TEST_SUITE',
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
    api_request: '',
    environment: '',
    notify_on_success: false,
    notify_on_failure: false,
    notify_emails: []
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
  submitting.value = true
  try {
    const submitData = {
      name: taskForm.name,
      description: taskForm.description,
      module: 'API',
      task_type: taskForm.task_type,
      schedule_type: taskForm.schedule_type,
      notify_on_success: taskForm.notify_on_success,
      notify_on_failure: taskForm.notify_on_failure,
      notify_on_email: taskForm.notify_on_email,
      notify_on_webhook: taskForm.notify_on_webhook,
      notification_config_ids: taskForm.notification_config_ids,
      environment_id: taskForm.environment
    }

    // 根据触发器类型添加对应字段
    if (taskForm.schedule_type === 'C') {
      submitData.cron = taskForm.cron
    } else if (taskForm.schedule_type === 'I') {
      submitData.minutes = taskForm.minutes
    } else if (taskForm.schedule_type === 'O') {
      submitData.next_run = taskForm.next_run
      submitData.repeats = 1  // 单次执行，执行一次后停止
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
    if (taskForm.task_type === 'API_TEST_SUITE') {
      submitData.target_id = taskForm.test_suite
    } else if (taskForm.task_type === 'API_REQUEST') {
      submitData.target_id = taskForm.api_request
    }

    if (editingTask.value) {
      await updateSchedulerSchedule(editingTask.value.id, submitData)
      ElMessage.success(t('apiTesting.messages.success.taskUpdated'))
    } else {
      await createSchedulerSchedule(submitData)
      ElMessage.success(t('apiTesting.messages.success.taskCreated'))
    }
    showCreateDialog.value = false
    loadTasks()
  } catch (error) {
    console.error('Task operation failed:', error)
    ElMessage.error(error.response?.data?.error ||
                   error.response?.data?.detail ||
                   (editingTask.value ? t('apiTesting.messages.error.updateTaskFailed') : t('apiTesting.messages.error.createTaskFailed')))
  } finally {
    submitting.value = false
  }
}

// 立即执行任务
const runTaskNow = async (task) => {
  try {
    task.running = true
    await executeSchedulerSchedule(task.id)
    ElMessage.success(t('apiTesting.messages.success.taskStarted'))
    
    // 无感轮询：在后台静默检查任务执行状态
    let retryCount = 0
    const maxRetries = 15  // 最多轮询15次
    const checkInterval = 2000  // 每2秒检查一次
    
    const checkExecution = async () => {
      try {
        // 静默刷新列表，不显示加载状态
        const response = await getSchedulerSchedules({
          page: pagination.current,
          page_size: pagination.size,
          task_type: filters.task_type,
          schedule_type: filters.schedule_type,
          status: filters.status
        })
        
        const updatedTask = response.data.results.find(t => t.id === task.id)
        if (updatedTask && updatedTask.last_run_display && updatedTask.last_run_display !== '-') {
          // 有执行记录了，更新当前任务数据
          const taskIndex = tasks.value.findIndex(t => t.id === task.id)
          if (taskIndex !== -1) {
            tasks.value[taskIndex] = updatedTask
          }
          return
        }
        
        retryCount++
        if (retryCount < maxRetries) {
          setTimeout(checkExecution, checkInterval)
        }
      } catch (error) {
        console.error('检查执行状态失败:', error)
      }
    }
    
    // 开始无感轮询
    setTimeout(checkExecution, checkInterval)
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.executeTaskFailed'))
  } finally {
    task.running = false
  }
}

// 格式化日期时间
const formatDateTime = (dateString) => {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }).replace(/\//g, '-')
}

const getTaskTypeDisplay = (taskType) => {
  const typeMap = {
    'API_TEST_SUITE': t('apiTesting.scheduledTask.taskTypes.testSuite'),
    'API_REQUEST': t('apiTesting.scheduledTask.taskTypes.apiRequest'),
    'TEST_SUITE': t('apiTesting.scheduledTask.taskTypes.testSuite')
  }
  return typeMap[taskType] || taskType
}

const getScheduleTypeDisplay = (scheduleType) => {
  const typeMap = {
    'C': t('apiTesting.scheduledTask.scheduleTypes.cron'),
    'O': t('apiTesting.scheduledTask.scheduleTypes.once'),
    'I': t('apiTesting.scheduledTask.scheduleTypes.interval'),
    'H': t('apiTesting.scheduledTask.scheduleTypes.hourly'),
    'D': t('apiTesting.scheduledTask.scheduleTypes.daily'),
    'W': t('apiTesting.scheduledTask.scheduleTypes.weekly'),
    'BW': t('apiTesting.scheduledTask.scheduleTypes.biweekly'),
    'M': t('apiTesting.scheduledTask.scheduleTypes.monthly'),
    'BM': t('apiTesting.scheduledTask.scheduleTypes.bimonthly'),
    'Q': t('apiTesting.scheduledTask.scheduleTypes.quarterly'),
    'Y': t('apiTesting.scheduledTask.scheduleTypes.yearly')
  }
  return typeMap[scheduleType] || scheduleType
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
  } else if (notificationTypeDisplay.includes('邮箱')) {
    return 'success'
  } else if (notificationTypeDisplay.includes('Webhook')) {
    return 'primary'
  }
  return 'info'
}

// 查看执行日志
const viewTaskLogs = async (task) => {
  logsLoading.value = true
  try {
    const response = await getExecutionLogs(task.id)
    const data = response.data
    executionLogs.value = [
      ...(data.success || []).map(item => ({ ...item, type: 'success' })),
      ...(data.failure || []).map(item => ({ ...item, type: 'failure' }))
    ].sort((a, b) => new Date(b.started) - new Date(a.started))
    showLogsDialog.value = true
  } catch (error) {
    console.error('Load execution logs failed:', error)
    ElMessage.error(t('apiTesting.messages.error.loadLogsFailed'))
  } finally {
    logsLoading.value = false
  }
}

// 处理任务操作
const handleTaskAction = (command, task) => {
  switch (command) {
    case 'pause':
      pauseTask(task)
      break
    case 'activate':
      activateTask(task)
      break
    case 'edit':
      editTask(task)
      break
    case 'logs':
      viewTaskLogs(task)
      break
    case 'delete':
      deleteTask(task)
      break
  }
}

// 编辑任务
const editTask = (task) => {
  editingTask.value = task
  isInitializingForm.value = true // 标记开始初始化表单
  const config = task.config || {}
  
  // 从 cron 表达式中解析时间字段
  let hour_minute = 0
  let daily_time = null
  let weekly_day = 1
  let weekly_time = null
  let biweekly_day = 1
  let biweekly_time = null
  let monthly_day = 1
  let monthly_time = null
  let bimonthly_day = 1
  let bimonthly_time = null
  let quarterly_month = 1
  let quarterly_day = 1
  let quarterly_time = null
  let yearly_month = 1
  let yearly_day = 1
  let yearly_time = null
  
  if (task.cron) {
    const cronParts = task.cron.split(' ')
    const minute = parseInt(cronParts[0]) || 0
    const hour = parseInt(cronParts[1]) || 0
    const dayOfMonth = parseInt(cronParts[2]) || 1
    const month = parseInt(cronParts[3]) || 1
    const dayOfWeek = parseInt(cronParts[4]) || 1
    
    switch (task.schedule_type) {
      case 'H':
        hour_minute = minute
        break
      case 'D':
        daily_time = new Date()
        daily_time.setHours(hour, minute, 0, 0)
        break
      case 'W':
        weekly_day = dayOfWeek
        weekly_time = new Date()
        weekly_time.setHours(hour, minute, 0, 0)
        break
      case 'BW':
        biweekly_day = dayOfWeek
        biweekly_time = new Date()
        biweekly_time.setHours(hour, minute, 0, 0)
        break
      case 'M':
        monthly_day = dayOfMonth
        monthly_time = new Date()
        monthly_time.setHours(hour, minute, 0, 0)
        break
      case 'BM':
        bimonthly_day = dayOfMonth
        bimonthly_time = new Date()
        bimonthly_time.setHours(hour, minute, 0, 0)
        break
      case 'Q':
        quarterly_month = month
        quarterly_day = dayOfMonth
        quarterly_time = new Date()
        quarterly_time.setHours(hour, minute, 0, 0)
        break
      case 'Y':
        yearly_month = month
        yearly_day = dayOfMonth
        yearly_time = new Date()
        yearly_time.setHours(hour, minute, 0, 0)
        break
    }
  }
  
  Object.assign(taskForm, {
    name: task.name,
    description: config.description || '',
    task_type: config.task_type || 'API_TEST_SUITE',
    schedule_type: task.schedule_type || 'C',
    cron: task.cron || '0 0 * * *',
    minutes: task.minutes || 60,
    next_run: task.next_run || '',
    hour_minute: hour_minute,
    daily_time: daily_time,
    weekly_day: weekly_day,
    weekly_time: weekly_time,
    biweekly_day: biweekly_day,
    biweekly_time: biweekly_time,
    monthly_day: monthly_day,
    monthly_time: monthly_time,
    bimonthly_day: bimonthly_day,
    bimonthly_time: bimonthly_time,
    quarterly_month: quarterly_month,
    quarterly_day: quarterly_day,
    quarterly_time: quarterly_time,
    yearly_month: yearly_month,
    yearly_day: yearly_day,
    yearly_time: yearly_time,
    test_suite: config.task_type === 'API_TEST_SUITE' ? config.target_id : null,
    api_request: config.task_type === 'API_REQUEST' ? config.target_id : null,
    environment: config.environment_id || null,
    notification_config_ids: task.config?.notification_config_ids || [],
    notify_on_success: config.notify_on_success ?? false,
    notify_on_failure: config.notify_on_failure ?? true,
    notify_on_email: config.notify_on_email ?? false,
    notify_on_webhook: config.notify_on_webhook ?? false
  })
  
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
    ElMessage.success(t('apiTesting.messages.success.taskPaused'))
    loadTasks()
  } catch (error) {
    console.error('Pause task failed:', error)
    ElMessage.error(t('apiTesting.messages.error.pauseTaskFailed'))
  }
}

// 激活任务
const activateTask = async (task) => {
  try {
    await toggleSchedulerSchedule(task.id, 'resume')
    ElMessage.success(t('apiTesting.messages.success.taskActivated'))
    loadTasks()
  } catch (error) {
    ElMessage.error(t('apiTesting.messages.error.activateTaskFailed'))
  }
}

// 删除任务
const deleteTask = async (task) => {
  try {
    await ElMessageBox.confirm(
      t('apiTesting.scheduledTask.confirmDeleteTask'),
      t('apiTesting.common.tip'),
      {
        confirmButtonText: t('apiTesting.common.confirm'),
        cancelButtonText: t('apiTesting.common.cancel'),
        type: 'warning'
      }
    )
    await deleteSchedulerSchedule(task.id)
    ElMessage.success(t('apiTesting.messages.success.taskDeleted'))
    loadTasks()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(t('apiTesting.messages.error.deleteTaskFailed'))
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
  margin-bottom: px;
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