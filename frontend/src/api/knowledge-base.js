import request from '@/utils/api'

// 知识库管理 API

// ==================== 知识库 ====================

/**
 * 获取知识库列表
 */
export function getKnowledgeBaseList(params) {
  return request({
    url: '/knowledge-base/',
    method: 'get',
    params
  })
}

/**
 * 获取知识库详情
 */
export function getKnowledgeBaseDetail(id) {
  return request({
    url: `/knowledge-base/${id}/`,
    method: 'get'
  })
}

/**
 * 创建知识库（支持文件上传）
 */
export function createKnowledgeBase(data) {
  // 如果是 FormData，需要设置正确的 Content-Type
  const headers = {}
  if (data instanceof FormData) {
    headers['Content-Type'] = 'multipart/form-data'
  }
  return request({
    url: '/knowledge-base/',
    method: 'post',
    data,
    headers
  })
}

/**
 * 更新知识库
 */
export function updateKnowledgeBase(id, data) {
  return request({
    url: `/knowledge-base/${id}/`,
    method: 'put',
    data
  })
}

/**
 * 删除知识库
 */
export function deleteKnowledgeBase(id) {
  return request({
    url: `/knowledge-base/${id}/`,
    method: 'delete'
  })
}

/**
 * 获取知识库统计信息
 */
export function getKnowledgeBaseStats(id) {
  return request({
    url: `/knowledge-base/${id}/stats/`,
    method: 'get'
  })
}

/**
 * 获取知识库分类树
 */
export function getKnowledgeBaseCategoriesTree(id) {
  return request({
    url: `/knowledge-base/${id}/categories_tree/`,
    method: 'get'
  })
}

// ==================== 分类 ====================

/**
 * 获取分类列表
 */
export function getCategoryList(params) {
  return request({
    url: '/knowledge-base/categories/',
    method: 'get',
    params
  })
}

/**
 * 获取分类详情
 */
export function getCategoryDetail(id) {
  return request({
    url: `/knowledge-base/categories/${id}/`,
    method: 'get'
  })
}

/**
 * 创建分类
 */
export function createCategory(data) {
  return request({
    url: '/knowledge-base/categories/',
    method: 'post',
    data
  })
}

/**
 * 更新分类
 */
export function updateCategory(id, data) {
  return request({
    url: `/knowledge-base/categories/${id}/`,
    method: 'put',
    data
  })
}

/**
 * 删除分类
 */
export function deleteCategory(id) {
  return request({
    url: `/knowledge-base/categories/${id}/`,
    method: 'delete'
  })
}

/**
 * 获取分类树形结构
 */
export function getCategoriesTree(knowledgeBaseId) {
  return request({
    url: '/knowledge-base/categories/tree/',
    method: 'get',
    params: { knowledge_base_id: knowledgeBaseId }
  })
}

// ==================== 文档 ====================

/**
 * 获取文档列表
 */
export function getDocumentList(params) {
  return request({
    url: '/knowledge-base/documents/',
    method: 'get',
    params
  })
}

/**
 * 获取文档详情（用于查看原文）
 */
export function getDocumentDetail(id) {
  return request({
    url: `/knowledge-base/documents/${id}/preview/`,
    method: 'get'
  })
}

/**
 * 上传文档
 */
export function uploadDocument(data) {
  return request({
    url: '/knowledge-base/documents/',
    method: 'post',
    data,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

/**
 * 更新文档
 */
export function updateDocument(id, data) {
  return request({
    url: `/knowledge-base/documents/${id}/`,
    method: 'put',
    data,
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

/**
 * 删除文档
 */
export function deleteDocument(id) {
  return request({
    url: `/knowledge-base/documents/${id}/`,
    method: 'delete'
  })
}

/**
 * 下载文档
 */
export function downloadDocument(id) {
  return request({
    url: `/knowledge-base/documents/${id}/download/`,
    method: 'get',
    responseType: 'blob'
  })
}

/**
 * 预览文档
 */
export function previewDocument(id) {
  return request({
    url: `/knowledge-base/documents/${id}/preview/`,
    method: 'get'
  })
}

/**
 * 获取文档版本列表
 */
export function getDocumentVersions(id) {
  return request({
    url: `/knowledge-base/documents/${id}/versions/`,
    method: 'get'
  })
}

/**
 * 恢复文档版本
 */
export function restoreDocumentVersion(id, versionNumber) {
  return request({
    url: `/knowledge-base/documents/${id}/restore_version/`,
    method: 'post',
    data: { version_number: versionNumber }
  })
}

/**
 * 搜索文档
 */
export function searchDocuments(params) {
  return request({
    url: '/knowledge-base/documents/search/',
    method: 'get',
    params
  })
}

/**
 * 语义搜索（召回检索）
 */
export function semanticSearch(knowledgeBaseId, data) {
  return request({
    url: `/knowledge-base/${knowledgeBaseId}/semantic_search/`,
    method: 'post',
    data
  })
}

/**
 * 混合检索（关键词 + 语义）
 */
export function hybridSearch(knowledgeBaseId, data) {
  return request({
    url: `/knowledge-base/${knowledgeBaseId}/hybrid_search/`,
    method: 'post',
    data
  })
}
