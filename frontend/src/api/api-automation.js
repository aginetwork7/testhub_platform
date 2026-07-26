import request from '@/utils/api'

const baseUrl = '/api-automation'

export function getAutomationProjects(params) {
  return request({ url: `${baseUrl}/projects/`, method: 'get', params })
}

export function createAutomationProject(data) {
  return request({ url: `${baseUrl}/projects/`, method: 'post', data })
}

export function getAutomationSuiteTree(projectId) {
  return request({ url: `${baseUrl}/suites/tree/`, method: 'get', params: { project_id: projectId } })
}

export function getAutomationCases(params) {
  return request({ url: `${baseUrl}/cases/`, method: 'get', params })
}

export function getAutomationEndpoints(params) {
  return request({ url: `${baseUrl}/endpoints/`, method: 'get', params })
}

export function getAutomationSchemaStatus(params) {
  return request({ url: `${baseUrl}/endpoints/schema_status/`, method: 'get', params })
}

export function regenerateAutomationSchemas(data) {
  return request({ url: `${baseUrl}/endpoints/regenerate_schemas/`, method: 'post', data })
}

export function getAutomationCoverage(params) {
  return request({ url: `${baseUrl}/coverage/stats/`, method: 'get', params })
}

export function getAutomationRuns(params) {
  return request({ url: `${baseUrl}/runs/`, method: 'get', params })
}

export function getAutomationRun(id) {
  return request({ url: `${baseUrl}/runs/${id}/`, method: 'get' })
}

export function getAutomationLogs() {
  return request({ url: `${baseUrl}/runs/logs/`, method: 'get' })
}

export function deleteAutomationRun(id) {
  return request({ url: `${baseUrl}/runs/${id}/`, method: 'delete' })
}

export function startAutomationRun(data) {
  return request({ url: `${baseUrl}/runs/start/`, method: 'post', data })
}

export function getAutomationConfigurations(params) {
  return request({ url: `${baseUrl}/configurations/`, method: 'get', params })
}

export function getAutomationConfigurationTemplate() {
  return request({ url: `${baseUrl}/configurations/template/`, method: 'get' })
}

export function initializeAutomationConfiguration(data) {
  return request({ url: `${baseUrl}/configurations/initialize/`, method: 'post', data })
}

export function createAutomationConfiguration(data) {
  return request({ url: `${baseUrl}/configurations/`, method: 'post', data })
}

export function updateAutomationConfiguration(id, data) {
  return request({ url: `${baseUrl}/configurations/${id}/`, method: 'patch', data })
}

export function deleteAutomationConfiguration(id) {
  return request({ url: `${baseUrl}/configurations/${id}/`, method: 'delete' })
}

export function setAutomationDefaultConfiguration(id) {
  return request({ url: `${baseUrl}/configurations/${id}/set_default/`, method: 'post' })
}

export function getAutomationSchedules(params) {
  return request({ url: '/scheduler/schedules/', method: 'get', params: { module: 'API_AUTOMATION', ...params } })
}

export function toggleAutomationSchedule(id, action) {
  return request({ url: `/scheduler/schedules/${id}/toggle/`, method: 'post', data: { action } })
}

export function getAutomationNotificationLogs(params) {
  return request({ url: `${baseUrl}/notification-logs/`, method: 'get', params })
}

export function createAutomationSchedule(data) {
  return request({ url: '/scheduler/schedules/', method: 'post', data })
}