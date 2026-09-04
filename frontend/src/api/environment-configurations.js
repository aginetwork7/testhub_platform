import request from '@/utils/api'

const baseUrl = '/core/environment-configurations'

export function getEnvironmentConfigurations(params) {
  return request({ url: `${baseUrl}/`, method: 'get', params })
}

export function getEnvironmentConfigurationTemplate() {
  return request({ url: `${baseUrl}/template/`, method: 'get' })
}

export function initializeEnvironmentConfiguration(data) {
  return request({ url: `${baseUrl}/initialize/`, method: 'post', data })
}

export function createEnvironmentConfiguration(data) {
  return request({ url: `${baseUrl}/`, method: 'post', data })
}

export function updateEnvironmentConfiguration(id, data) {
  return request({ url: `${baseUrl}/${id}/`, method: 'patch', data })
}

export function deleteEnvironmentConfiguration(id) {
  return request({ url: `${baseUrl}/${id}/`, method: 'delete' })
}

export function setDefaultEnvironmentConfiguration(id) {
  return request({ url: `${baseUrl}/${id}/set_default/`, method: 'post' })
}