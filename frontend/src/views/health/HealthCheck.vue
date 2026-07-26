<template>
  <main class="health-page">
    <header class="health-header">
      <div><h2>健康检测</h2><p>服务器关键性能指标与 TestHub 核心服务状态</p></div>
      <div class="health-actions"><span>最后更新：{{ formatDate(health.checked_at) }}</span><el-button :loading="loading" @click="loadHealth"><el-icon><Refresh /></el-icon>刷新</el-button></div>
    </header>

    <section class="metrics-grid">
      <article class="metric"><span>CPU 使用率</span><strong>{{ percent(health.host.cpu_percent) }}</strong><el-progress :percentage="health.host.cpu_percent || 0" :status="progressStatus(health.host.cpu_percent)" :show-text="false" /></article>
      <article class="metric"><span>内存使用率</span><strong>{{ percent(health.host.memory_percent) }}</strong><el-progress :percentage="health.host.memory_percent || 0" :status="progressStatus(health.host.memory_percent)" :show-text="false" /><small>{{ formatBytes(health.host.memory_used) }} / {{ formatBytes(health.host.memory_total) }}</small></article>
      <article class="metric"><span>磁盘使用率</span><strong>{{ percent(health.host.disk_percent) }}</strong><el-progress :percentage="health.host.disk_percent || 0" :status="progressStatus(health.host.disk_percent)" :show-text="false" /><small>{{ formatBytes(health.host.disk_used) }} / {{ formatBytes(health.host.disk_total) }}</small></article>
      <article class="metric"><span>系统运行时间</span><strong>{{ formatDuration(health.host.uptime_seconds) }}</strong><small>负载：{{ formatLoad(health.host.load_average) }}</small></article>
    </section>

    <section class="content-grid">
      <section class="panel"><div class="panel-title"><h3>TestHub 服务</h3><el-tag :type="hasServiceFailure ? 'danger' : 'success'">{{ hasServiceFailure ? '存在异常' : '运行正常' }}</el-tag></div><el-table v-loading="loading" :data="health.services"><el-table-column prop="name" label="服务" min-width="220" /><el-table-column label="状态" width="120"><template #default="{ row }"><el-tag :type="row.status === 'UP' ? 'success' : 'danger'">{{ row.status === 'UP' ? '正常' : '异常' }}</el-tag></template></el-table-column><el-table-column prop="latency_ms" label="探测耗时" width="130"><template #default="{ row }">{{ row.latency_ms }} ms</template></el-table-column><el-table-column prop="message" label="详情" min-width="260" show-overflow-tooltip /></el-table></section>
      <aside class="panel host-panel"><h3>运行节点</h3><dl><div><dt>主机名</dt><dd>{{ health.host.hostname || '-' }}</dd></div><div><dt>系统</dt><dd>{{ health.host.platform || '-' }}</dd></div><div><dt>CPU 逻辑核心</dt><dd>{{ health.host.cpu_count || '-' }}</dd></div><div><dt>网络发送</dt><dd>{{ formatBytes(health.host.network_sent) }}</dd></div><div><dt>网络接收</dt><dd>{{ formatBytes(health.host.network_received) }}</dd></div></dl></aside>
    </section>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { getSystemHealth } from '@/api/system-health'

const loading = ref(false)
const health = ref({ host: {}, services: [], checked_at: null })
let refreshTimer = null

const hasServiceFailure = computed(() => health.value.services.some(service => service.status !== 'UP'))
const formatDate = timestamp => timestamp ? new Date(timestamp * 1000).toLocaleString() : '-'
const percent = value => `${Number(value || 0).toFixed(1)}%`
const formatLoad = value => Array.isArray(value) ? value.map(item => Number(item).toFixed(2)).join(' / ') : '-'
const formatBytes = value => {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** exponent).toFixed(exponent ? 1 : 0)} ${units[exponent]}`
}
const formatDuration = value => {
  const total = Number(value || 0)
  const days = Math.floor(total / 86400)
  const hours = Math.floor(total % 86400 / 3600)
  return `${days} 天 ${hours} 小时`
}
const progressStatus = value => value >= 90 ? 'exception' : value >= 75 ? 'warning' : 'success'

async function loadHealth() {
  loading.value = true
  try { health.value = (await getSystemHealth()).data } catch (error) { ElMessage.error('加载系统健康状态失败') } finally { loading.value = false }
}

onMounted(async () => { await loadHealth(); refreshTimer = setInterval(loadHealth, 10000) })
onBeforeUnmount(() => { if (refreshTimer) clearInterval(refreshTimer) })
</script>

<style scoped>
.health-page { min-height: 100%; padding: 24px; background: #f4f7fb; }
.health-header, .panel-title, .health-actions { display: flex; align-items: center; }
.health-header { justify-content: space-between; gap: 20px; margin-bottom: 20px; }
.health-header h2, .panel h3 { margin: 0; color: #1c2b3a; }
.health-header p, .health-actions, .metric small { color: #667085; font-size: 13px; }
.health-header p { margin: 6px 0 0; }
.health-actions { gap: 12px; }
.metrics-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.metric, .panel { border: 1px solid #e4e7ec; border-radius: 6px; background: #fff; box-shadow: 0 1px 2px rgb(16 24 40 / 5%); }
.metric { display: grid; gap: 10px; padding: 18px; color: #475467; }
.metric strong { color: #101828; font-size: 28px; }
.content-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr); gap: 16px; }
.panel { padding: 18px; }
.panel-title { justify-content: space-between; margin-bottom: 14px; }
.host-panel dl { margin: 16px 0 0; }
.host-panel dl div { display: grid; grid-template-columns: 100px minmax(0, 1fr); gap: 12px; padding: 12px 0; border-bottom: 1px solid #eaecf0; }
.host-panel dt { color: #667085; }.host-panel dd { margin: 0; overflow-wrap: anywhere; color: #1d2939; }
@media (max-width: 1100px) { .metrics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.content-grid { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .health-page { padding: 16px; }.health-header { align-items: flex-start; flex-direction: column; }.metrics-grid { grid-template-columns: 1fr; } }
</style>