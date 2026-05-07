import api from '@/utils/api'

export function getMetaProjects(params) {
  return api.get('/meta-projects/', { params })
}

export function getMetaProjectDetail(id) {
  return api.get(`/meta-projects/${id}/`)
}

export function createMetaProject(data) {
  return api.post('/meta-projects/', data)
}

export function updateMetaProject(id, data) {
  return api.patch(`/meta-projects/${id}/`, data)
}

export function deleteMetaProject(id) {
  return api.delete(`/meta-projects/${id}/`)
}

export function getProjectModules(projectId) {
  return api.get(`/meta-projects/${projectId}/modules/`)
}

export function addProjectModule(projectId, data) {
  return api.post(`/meta-projects/${projectId}/modules/`, data)
}

export function updateProjectModule(projectId, moduleType, data) {
  return api.patch(`/meta-projects/${projectId}/modules/${moduleType}/`, data)
}

export function deleteProjectModule(projectId, moduleType) {
  return api.delete(`/meta-projects/${projectId}/modules/${moduleType}/`)
}
