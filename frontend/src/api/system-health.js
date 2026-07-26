import request from '@/utils/api'

export function getSystemHealth() {
  return request({ url: '/core/system-health/', method: 'get' })
}