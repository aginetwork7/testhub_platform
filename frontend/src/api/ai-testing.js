import request from '@/utils/api'

// ================= AI用例生成相关 =================

// 获取AI测试项目列表
export function getAiProjects(params) {
  return request({
    url: '/ai-testing/projects/',
    method: 'get',
    params
  })
}

// 创建AI测试项目
export function createAiProject(data) {
  return request({
    url: '/ai-testing/projects/',
    method: 'post',
    data
  })
}

// 更新AI测试项目
export function updateAiProject(id, data) {
  return request({
    url: `/ai-testing/projects/${id}/`,
    method: 'put',
    data
  })
}

// 删除AI测试项目
export function deleteAiProject(id) {
  return request({
    url: `/ai-testing/projects/${id}/`,
    method: 'delete'
  })
}

// 获取AI用例列表
export function getAICases(params) {
  return request({
    url: '/ai-testing/ai-cases/',
    method: 'get',
    params
  })
}

// 创建AI用例
export function createAICase(data) {
  return request({
    url: '/ai-testing/ai-cases/',
    method: 'post',
    data
  })
}

// 更新AI用例
export function updateAICase(id, data) {
  return request({
    url: `/ai-testing/ai-cases/${id}/`,
    method: 'put',
    data
  })
}

// 删除AI用例
export function deleteAICase(id) {
  return request({
    url: `/ai-testing/ai-cases/${id}/`,
    method: 'delete'
  })
}

// 执行AI用例
export function executeAICase(id, data) {
  return request({
    url: `/ai-testing/ai-cases/${id}/run/`,
    method: 'post',
    data
  })
}

// 批量执行 AI 用例
export function batchExecuteAICases(data) {
  return request({
    url: '/ai-testing/ai-cases/batch_run/',
    method: 'post',
    data
  })
}

// 执行临时AI任务
export function runAdhocAICase(data) {
  return request({
    url: '/ai-testing/ai-execution-records/run_adhoc/',
    method: 'post',
    data
  })
}

// ================= AI执行记录相关 =================

// 获取执行记录列表
export function getAIExecutionRecords(params) {
  return request({
    url: '/ai-testing/ai-execution-records/',
    method: 'get',
    params
  })
}

// 获取单条执行记录详情
export function getAIExecutionRecord(id) {
  return request({
    url: `/ai-testing/ai-execution-records/${id}/`,
    method: 'get'
  })
}

// 获取执行记录的日志
export function getAIExecutionLogs(id) {
  return request({
    url: `/ai-testing/ai-execution-records/${id}/logs/`,
    method: 'get'
  })
}

// 获取执行记录的步骤截图
export function getAIExecutionScreenshots(id) {
  return request({
    url: `/ai-testing/ai-execution-records/${id}/screenshots/`,
    method: 'get'
  })
}

// 停止AI执行记录
export function stopAIExecution(id) {
  return request({
    url: `/ai-testing/ai-execution-records/${id}/stop/`,
    method: 'post'
  })
}

// 批量删除执行记录
export function batchDeleteAIExecutionRecords(ids) {
  return request({
    url: '/ai-testing/ai-execution-records/batch_delete/',
    method: 'post',
    data: { ids }
  })
}

// ================= 报告相关 =================
// 获取执行报告
export function getAIExecutionReport(id, params = {}) {
  return request({
    url: `/ai-testing/ai-execution-records/${id}/report/`,
    method: 'get',
    params
  })
}

// 导出PDF报告
export function exportAIExecutionReportPDF(id, params = {}) {
  return request({
    url: `/ai-testing/ai-execution-records/${id}/export_pdf/`,
    method: 'get',
    params,
    responseType: 'blob'
  })
}
