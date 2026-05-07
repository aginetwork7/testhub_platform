/**
 * 核心功能模块相关 API
 */
import request from '@/utils/api'

// ==================== 统一通知配置 ====================

// 获取所有通知配置
export function getUnifiedNotificationConfigs(params) {
  return request({
    url: '/core/notification-configs/',
    method: 'get',
    params
  })
}

// 获取通知配置详情
export function getUnifiedNotificationConfigDetail(id) {
  return request({
    url: `/core/notification-configs/${id}/`,
    method: 'get'
  })
}

// 创建通知配置
export function createUnifiedNotificationConfig(data) {
  return request({
    url: '/core/notification-configs/',
    method: 'post',
    data
  })
}

// 更新通知配置
export function updateUnifiedNotificationConfig(id, data) {
  return request({
    url: `/core/notification-configs/${id}/`,
    method: 'put',
    data
  })
}

// 删除通知配置
export function deleteUnifiedNotificationConfig(id) {
  return request({
    url: `/core/notification-configs/${id}/`,
    method: 'delete'
  })
}

// ==================== 通知模板 ====================

// 获取通知模板列表
export function getNotificationTemplates(params) {
  return request({
    url: '/core/notification-templates/',
    method: 'get',
    params
  })
}

// 获取通知模板详情
export function getNotificationTemplateDetail(id) {
  return request({
    url: `/core/notification-templates/${id}/`,
    method: 'get'
  })
}

// 创建通知模板
export function createNotificationTemplate(data) {
  return request({
    url: '/core/notification-templates/',
    method: 'post',
    data
  })
}

// 更新通知模板
export function updateNotificationTemplate(id, data) {
  return request({
    url: `/core/notification-templates/${id}/`,
    method: 'put',
    data
  })
}

// 删除通知模板
export function deleteNotificationTemplate(id) {
  return request({
    url: `/core/notification-templates/${id}/`,
    method: 'delete'
  })
}

// 设置为默认配置
export function setDefaultNotificationConfig(id) {
  return request({
    url: `/core/notification-configs/${id}/set_default/`,
    method: 'post'
  })
}

// 获取所有启用的配置
export function getActiveNotificationConfigs() {
  return request({
    url: '/core/notification-configs/active_configs/',
    method: 'get'
  })
}

// 测试发送通知
export function testSendNotification(id) {
  return request({
    url: `/core/notification-configs/${id}/test_send/`,
    method: 'post'
  })
}
