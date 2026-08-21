import { ref } from 'vue'
import api from '@/utils/api'

const historySessions = ref([])
const currentSession = ref(null)
const messages = ref([])
const assistantMode = ref('chat')
const alphaRuns = ref([])
const activeAlphaRun = ref(null)

const sortHistorySessions = (sessions) => [...sessions].sort((first, second) => {
  if (Boolean(first.is_pinned) !== Boolean(second.is_pinned)) {
    return Number(Boolean(second.is_pinned)) - Number(Boolean(first.is_pinned))
  }
  return new Date(second.updated_at) - new Date(first.updated_at)
})

const startNewChat = () => {
  currentSession.value = null
  messages.value = []
}

const upsertHistorySession = (session) => {
  historySessions.value = sortHistorySessions([
    session,
    ...historySessions.value.filter((item) => item.id !== session.id),
  ])
}

const loadHistory = async () => {
  const response = await api.get('/assistant/sessions/')
  const sessions = response.data.results || response.data || []
  historySessions.value = sortHistorySessions(Array.from(
    new Map(sessions.map((session) => [session.id, session])).values(),
  ))
}

const updateSession = async (sessionId, changes) => {
  const response = await api.patch(`/assistant/sessions/${sessionId}/`, changes)
  const session = response.data
  upsertHistorySession(session)

  if (currentSession.value?.id === session.id) {
    currentSession.value = { ...currentSession.value, ...session }
  }

  return session
}

const loadAlphaRuns = async () => {
  const response = await api.get('/ai-testing/alpha/runs/', { params: { page_size: 50 } })
  alphaRuns.value = response.data.results || response.data || []
}

const selectSession = async (session) => {
  if (currentSession.value?.id === session.id) return
  const response = await api.get(`/assistant/sessions/${session.id}/messages/`)
  currentSession.value = { ...session }
  messages.value = response.data
}

const removeSession = async (sessionId) => {
  await api.delete(`/assistant/sessions/${sessionId}/`)
  historySessions.value = historySessions.value.filter((session) => session.id !== sessionId)
  if (currentSession.value?.id === sessionId) startNewChat()
}

const selectAlphaRun = async (run) => {
  const response = await api.get(`/ai-testing/alpha/runs/${run.id}/`)
  activeAlphaRun.value = response.data
  assistantMode.value = 'agent'
  currentSession.value = { title: 'Alpha Agent' }
  const taskCount = response.data.active_revision?.task_nodes?.length || 0
  messages.value = [{
    role: 'assistant',
    content: `Alpha Agent：${response.data.status}${taskCount ? `，已生成 ${taskCount} 个任务` : ''}`,
    isPending: ['draft', 'planning', 'awaiting_confirmation', 'executing', 'reflecting'].includes(response.data.status),
  }]
}

const removeAlphaRun = async (runId) => {
  await api.delete(`/ai-testing/alpha/runs/${runId}/`)
  alphaRuns.value = alphaRuns.value.filter((run) => run.id !== runId)
  if (activeAlphaRun.value?.id === runId) {
    activeAlphaRun.value = null
    assistantMode.value = 'chat'
    startNewChat()
  }
}

export const assistantSessionStore = {
  historySessions,
  currentSession,
  messages,
  assistantMode,
  alphaRuns,
  activeAlphaRun,
  startNewChat,
  upsertHistorySession,
  updateSession,
  loadHistory,
  loadAlphaRuns,
  selectSession,
  selectAlphaRun,
  removeSession,
  removeAlphaRun,
}