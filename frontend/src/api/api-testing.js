import request from '@/utils/api'

// 仪表盘相关API
export function getDashboardStats() {
  return request({
    url: '/api-testing/dashboard/stats/',
    method: 'get'
  })
}

// ==================== 定时任务相关API ====================

// 获取定时任务列表
export function getSchedulerSchedules(params) {
  return request({
    url: '/scheduler/schedules/',
    method: 'get',
    params
  })
}

// 创建定时任务
export function createSchedulerSchedule(data) {
  return request({
    url: '/scheduler/schedules/',
    method: 'post',
    data
  })
}

// 获取定时任务详情
export function getScheduledTaskDetail(id) {
  return request({
    url: `/scheduler/schedules/${id}/`,
    method: 'get'
  })
}

// 更新定时任务
export function updateSchedulerSchedule(id, data) {
  return request({
    url: `/scheduler/schedules/${id}/`,
    method: 'patch',
    data
  })
}

// 删除定时任务
export function deleteSchedulerSchedule(id) {
  return request({
    url: `/scheduler/schedules/${id}/`,
    method: 'delete'
  })
}

export function toggleSchedulerSchedule(id, is_active) {
  const action = is_active ? 'resume' : 'pause'
  return request({
    url: `/scheduler/schedules/${id}/${action}/`,
    method: 'post'
  })
}

// 立即运行任务
export function executeSchedulerSchedule(id) {
  return request({
    url: `/scheduler/schedules/${id}/execute/`,
    method: 'post'
  })
}

// 获取测试套件列表
export function getTestSuites(params) {
  return request({
    url: '/api-testing/test-suites/',
    method: 'get',
    params
  })
}

// 获取API请求列表
export function getApiRequests(params) {
  return request({
    url: '/api-testing/requests/',
    method: 'get',
    params
  })
}

// 获取环境列表
export function getEnvironments(params) {
  return request({
    url: '/api-testing/environments/',
    method: 'get',
    params
  })
}

// 获取项目列表
export function getApiProjects(params) {
  return request({
    url: '/api-testing/projects/',
    method: 'get',
    params
  })
}

// 获取集合列表
export function getApiCollections(params) {
  return request({
    url: '/api-testing/collections/',
    method: 'get',
    params
  })
}

// 执行测试套件
export function executeTestSuite(id, data) {
  return request({
    url: `/api-testing/test-suites/${id}/execute/`,
    method: 'post',
    data
  })
}

// 执行API请求
export function executeApiRequest(id, data) {
  return request({
    url: `/api-testing/api-requests/${id}/execute/`,
    method: 'post',
    data
  })
}

// 获取执行结果
export function getExecutionResult(id) {
  return request({
    url: `/api-testing/executions/${id}/`,
    method: 'get'
  })
}

// 获取请求历史
export function getRequestHistory(params) {
  return request({
    url: '/api-testing/histories/',
    method: 'get',
    params
  })
}

// 删除请求历史
export function deleteRequestHistory(id) {
  return request({
    url: `/api-testing/histories/${id}/`,
    method: 'delete'
  })
}

// 批量删除请求历史
export function batchDeleteRequestHistory(ids) {
  return request({
    url: '/api-testing/histories/batch-delete/',
    method: 'post',
    data: { ids }
  })
}

// 获取用户列表
export function getUsers(params) {
  return request({
    url: '/api-testing/users/',
    method: 'get',
    params
  })
}
// 获取操作日志
export function getOperationLogs(params) {
  return request({
    url: '/api-testing/operation-logs/',
    method: 'get',
    params
  })
}

// 获取执行日志
export function getExecutionLogs(taskId, params = {}) {
  return request({
    url: `/scheduler/schedules/${taskId}/history/`,
    method: 'get',
    params
  })
}

// ==================== API 测试特有API ====================

export function getSchedulerHistory(id, params = {}) {
  return request({
    url: `/scheduler/schedules/${id}/history/`,
    method: 'get',
    params
  })
}

export function getSchedulerStatistics() {
  return request({
    url: '/scheduler/schedules/statistics/',
    method: 'get'
  })
}
