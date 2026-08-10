<template>
  <div class="assistant-layout" :class="{ 'has-alpha-task-tree': showAlphaTaskTree }">
    <!-- 右侧主内容区 -->
    <div class="main-content">
      <!-- 场景1：新会话（居中输入框） -->
      <div v-if="isNewChatMode" class="welcome-screen">
        <div class="welcome-content">
          <div class="center-input-wrapper">
            <el-input
              v-model="inputMessage"
              type="textarea"
              :rows="3"
              :placeholder="$t('assistant.inputPlaceholder')"
              class="center-input"
              resize="none"
              @keydown.enter.exact.prevent="handleEnter"
            />
            <div class="input-toolbar">
              <div class="input-mode-tools">
                <el-dropdown trigger="click" @command="assistantMode = $event">
                  <button type="button" class="mode-icon" :aria-label="assistantMode === 'agent' ? 'Agent' : 'Chat'">
                    <span v-if="assistantMode === 'agent'" class="mode-symbol agent-symbol"><span class="robot-face"><i></i><i></i></span></span>
                    <span v-else class="mode-symbol chat-symbol"><svg viewBox="0 0 24 24" aria-hidden="true"><defs><linearGradient id="assistant-chat-stroke" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#3b82f6" /><stop offset="1" stop-color="#8b5cf6" /></linearGradient></defs><path d="M6.25 5.25h11.5a2.5 2.5 0 0 1 2.5 2.5v6.5a2.5 2.5 0 0 1-2.5 2.5H11l-4.75 3v-3H6.25a2.5 2.5 0 0 1-2.5-2.5v-6.5a2.5 2.5 0 0 1 2.5-2.5Z" fill="none" stroke="url(#assistant-chat-stroke)" stroke-linejoin="round" stroke-width="1.7"/><circle cx="9" cy="11" r=".85" fill="url(#assistant-chat-stroke)"/><circle cx="12" cy="11" r=".85" fill="url(#assistant-chat-stroke)"/><circle cx="15" cy="11" r=".85" fill="url(#assistant-chat-stroke)"/></svg></span>
                  </button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="chat"><span class="menu-mode-symbol chat-symbol"><svg viewBox="0 0 24 24" aria-hidden="true"><defs><linearGradient id="assistant-chat-menu-stroke" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#3b82f6" /><stop offset="1" stop-color="#8b5cf6" /></linearGradient></defs><path d="M6.25 5.25h11.5a2.5 2.5 0 0 1 2.5 2.5v6.5a2.5 2.5 0 0 1-2.5 2.5H11l-4.75 3v-3H6.25a2.5 2.5 0 0 1-2.5-2.5v-6.5a2.5 2.5 0 0 1 2.5-2.5Z" fill="none" stroke="url(#assistant-chat-menu-stroke)" stroke-linejoin="round" stroke-width="1.7"/><circle cx="9" cy="11" r=".85" fill="url(#assistant-chat-menu-stroke)"/><circle cx="12" cy="11" r=".85" fill="url(#assistant-chat-menu-stroke)"/><circle cx="15" cy="11" r=".85" fill="url(#assistant-chat-menu-stroke)"/></svg></span>Chat</el-dropdown-item>
                      <el-dropdown-item command="agent"><span class="menu-mode-symbol agent-symbol"><span class="robot-face"><i></i><i></i></span></span>Agent</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
                <label v-if="assistantMode === 'chat'" class="thinking-control"><span>Thinking</span><el-switch v-model="enableThinkingMode" size="small" /></label>
              </div>
              <el-button type="primary" circle :icon="Promotion" :disabled="!inputMessage.trim()" @click="sendMessage" />
            </div>
          </div>
        </div>
      </div>

      <!-- 场景2：对话界面 -->
      <div v-else class="chat-screen">
        <div class="chat-header">
          <span class="chat-title">{{ currentSession?.title || $t('assistant.newChat') }}</span>
          <div class="chat-header-actions">
            <el-switch
              v-model="showThinking"
              inline-prompt
              active-text="显"
              inactive-text="隐"
              size="small"
            />
            <span class="chat-time" v-if="currentSession">{{ formatDate(currentSession.updated_at) }}</span>
          </div>
        </div>
        
        <div class="messages-container" ref="messagesContainer">
          <div 
            v-for="(message, index) in messages" 
            :key="message.id || index"
            :class="['message-row', message.role]"
          >
            <div class="avatar">
              <el-avatar v-if="message.role === 'user'" :size="36" :icon="User" class="user-avatar" />
              <el-avatar v-else :size="36" :icon="Cpu" class="ai-avatar" />
            </div>
            <div class="message-bubble">
              <details
                v-if="showThinking && message.role === 'assistant' && message.thinking"
                class="thinking-block"
              >
                <summary>思考过程</summary>
                <div class="thinking-content">{{ message.thinking }}</div>
              </details>
              <div class="message-content" v-html="formatMessageContent(message.content)"></div>
              <div
                v-if="message.role === 'assistant' && message.usage"
                class="message-usage"
              >
                <span v-if="message.usage.total_tokens !== null && message.usage.total_tokens !== undefined">tokens: {{ message.usage.total_tokens }}</span>
                <span v-if="message.usage.prompt_tokens !== null && message.usage.prompt_tokens !== undefined"> prompt: {{ message.usage.prompt_tokens }}</span>
                <span v-if="message.usage.completion_tokens !== null && message.usage.completion_tokens !== undefined"> completion: {{ message.usage.completion_tokens }}</span>
              </div>
              <details
                v-if="message.role === 'assistant' && (message.tool_call || message.tool_result || message.tool_contract_error)"
                class="tool-debug-block"
              >
                <summary>工具契约诊断</summary>
                <div class="tool-debug-content">
                  <div v-if="message.tool_contract_status">status: {{ message.tool_contract_status }}</div>
                  <div v-if="message.tool_contract_error">
                    error: {{ message.tool_contract_error.code }} - {{ message.tool_contract_error.message }}
                  </div>
                  <div v-if="message.tool_call">tool_call: {{ formatCompactJson(message.tool_call) }}</div>
                  <div v-if="message.tool_result">tool_result: {{ formatCompactJson(message.tool_result) }}</div>
                </div>
              </details>
              <div class="message-status" v-if="message.isPending">
                <el-icon class="is-loading"><Loading /></el-icon> 生成中...
              </div>
            </div>
          </div>
          
          <!-- 底部占位，确保滚动到底部 -->
          <div style="height: 20px;"></div>
        </div>

        <div class="chat-footer">
          <div class="input-box">
            <el-input
              v-model="inputMessage"
              type="textarea"
              :rows="1"
              :autosize="{ minRows: 1, maxRows: 5 }"
              :placeholder="$t('assistant.chatInputPlaceholder')"
              resize="none"
              @keydown.enter.exact.prevent="handleEnter"
            />
            <div class="input-toolbar">
            <div class="input-mode-tools">
              <el-dropdown trigger="click" @command="assistantMode = $event">
                <button type="button" class="mode-icon" :aria-label="assistantMode === 'agent' ? 'Agent' : 'Chat'">
                  <span v-if="assistantMode === 'agent'" class="mode-symbol agent-symbol"><span class="robot-face"><i></i><i></i></span></span>
                  <span v-else class="mode-symbol chat-symbol"><svg viewBox="0 0 24 24" aria-hidden="true"><defs><linearGradient id="assistant-chat-stroke-footer" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#3b82f6" /><stop offset="1" stop-color="#8b5cf6" /></linearGradient></defs><path d="M6.25 5.25h11.5a2.5 2.5 0 0 1 2.5 2.5v6.5a2.5 2.5 0 0 1-2.5 2.5H11l-4.75 3v-3H6.25a2.5 2.5 0 0 1-2.5-2.5v-6.5a2.5 2.5 0 0 1 2.5-2.5Z" fill="none" stroke="url(#assistant-chat-stroke-footer)" stroke-linejoin="round" stroke-width="1.7"/><circle cx="9" cy="11" r=".85" fill="url(#assistant-chat-stroke-footer)"/><circle cx="12" cy="11" r=".85" fill="url(#assistant-chat-stroke-footer)"/><circle cx="15" cy="11" r=".85" fill="url(#assistant-chat-stroke-footer)"/></svg></span>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="chat"><span class="menu-mode-symbol chat-symbol"><svg viewBox="0 0 24 24" aria-hidden="true"><defs><linearGradient id="assistant-chat-menu-footer-stroke" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#3b82f6" /><stop offset="1" stop-color="#8b5cf6" /></linearGradient></defs><path d="M6.25 5.25h11.5a2.5 2.5 0 0 1 2.5 2.5v6.5a2.5 2.5 0 0 1-2.5 2.5H11l-4.75 3v-3H6.25a2.5 2.5 0 0 1-2.5-2.5v-6.5a2.5 2.5 0 0 1 2.5-2.5Z" fill="none" stroke="url(#assistant-chat-menu-footer-stroke)" stroke-linejoin="round" stroke-width="1.7"/><circle cx="9" cy="11" r=".85" fill="url(#assistant-chat-menu-footer-stroke)"/><circle cx="12" cy="11" r=".85" fill="url(#assistant-chat-menu-footer-stroke)"/><circle cx="15" cy="11" r=".85" fill="url(#assistant-chat-menu-footer-stroke)"/></svg></span>Chat</el-dropdown-item>
                    <el-dropdown-item command="agent"><span class="menu-mode-symbol agent-symbol"><span class="robot-face"><i></i><i></i></span></span>Agent</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <label v-if="assistantMode === 'chat'" class="thinking-control"><span>Thinking</span><el-switch v-model="enableThinkingMode" size="small" /></label>
            </div>
            <el-button 
              type="primary" 
              class="send-btn"
              :disabled="!inputMessage.trim() || sending"
              @click="sendMessage"
            >
              <el-icon><Promotion /></el-icon>
            </el-button>
            <el-button
              v-if="sending"
              type="danger"
              plain
              class="stop-btn"
              @click="stopStreamingReply"
            >
              停止
            </el-button>
            </div>
          </div>
          <div class="footer-tip">{{ $t('assistant.aiDisclaimer') }}</div>
        </div>
      </div>
    </div>

    <aside v-if="showAlphaTaskTree" class="alpha-task-tree">
      <div class="alpha-task-tree-header">
        <span>Task Tree</span>
        <div class="alpha-task-tree-actions">
          <el-button v-if="canStartAlphaTask" size="small" type="primary" @click="startAlphaTask">开始任务</el-button>
          <el-button v-else-if="canStopAlphaTask" size="small" type="danger" plain @click="stopAlphaTask">停止任务</el-button>
          <el-tag size="small" :type="alphaRunStatusType(activeAlphaRun.status)">{{ alphaStatusLabel(activeAlphaRun) }}</el-tag>
        </div>
      </div>
      <div v-if="!alphaTaskNodes.length" class="alpha-task-tree-empty">正在生成任务树...</div>
      <div v-for="task in alphaTaskNodes" :key="task.id" class="alpha-task-node">
        <strong>{{ task.task_key }}</strong>
        <span>{{ task.skill_name }}</span>
        <el-tag size="small" :type="alphaTaskStatusType(task.status)">{{ alphaTaskStatusLabel(task.status) }}</el-tag>
        <p v-if="task.error_message">{{ task.error_message }}</p>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'
import { User, Cpu, Promotion, Loading } from '@element-plus/icons-vue'
import api from '@/utils/api'
import { assistantSessionStore } from '@/stores/assistantSession'

const userStore = useUserStore()
const { t, locale } = useI18n()

const getStorageFlag = (key, defaultValue = true) => {
  try {
    const value = localStorage.getItem(key)
    if (value === null) {
      return defaultValue
    }
    return value !== '0'
  } catch (error) {
    console.warn('read localStorage failed:', error)
    return defaultValue
  }
}

const setStorageFlag = (key, value) => {
  try {
    localStorage.setItem(key, value ? '1' : '0')
  } catch (error) {
    console.warn('write localStorage failed:', error)
  }
}

// 状态
const historySessions = assistantSessionStore.historySessions
const currentSession = assistantSessionStore.currentSession
const messages = assistantSessionStore.messages
const inputMessage = ref('')
const sending = ref(false)
const messagesContainer = ref(null)
const activeStreamController = ref(null)
const enableThinkingMode = ref(getStorageFlag('assistant_enable_thinking_mode', true))
const showThinking = ref(getStorageFlag('assistant_show_thinking', true))
const assistantMode = assistantSessionStore.assistantMode
const activeAlphaRun = assistantSessionStore.activeAlphaRun
const alphaStatusMessage = ref(null)
let alphaPollTimer = null

// 计算属性
const isNewChatMode = computed(() => {
  // 如果没有当前会话，或者当前会话没有消息且没有ID（临时会话），则显示新会话模式
  return !currentSession.value || (!currentSession.value.id && messages.value.length === 0)
})

const showAlphaTaskTree = computed(() => assistantMode.value === 'agent' && Boolean(activeAlphaRun.value))
const alphaTaskNodes = computed(() => activeAlphaRun.value?.active_revision?.task_nodes || [])
const canStartAlphaTask = computed(() => activeAlphaRun.value?.status === 'planning' && activeAlphaRun.value?.active_revision?.status === 'draft')
const canStopAlphaTask = computed(() => ['planning', 'awaiting_confirmation', 'executing', 'reflecting'].includes(activeAlphaRun.value?.status))

const alphaTaskStatusLabel = (status) => ({
  pending: '等待中',
  awaiting_confirmation: '待确认',
  dispatched: '已派发',
  running: '执行中',
  succeeded: '成功',
  failed: '失败',
  blocked: '阻塞',
  skipped: '跳过',
  cancelled: '已取消',
}[status] || status)

const alphaTaskStatusType = (status) => ({
  succeeded: 'success',
  failed: 'danger',
  cancelled: 'info',
  awaiting_confirmation: 'warning',
  running: 'primary',
  dispatched: 'primary',
}[status] || 'info')

const alphaRunStatusType = (status) => ({
  completed: 'success',
  failed: 'danger',
  cancelled: 'info',
  planning: 'warning',
  reflecting: 'warning',
  awaiting_confirmation: 'warning',
  executing: 'primary',
}[status] || 'info')

// 方法
const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  const now = new Date()
  const localeCode = locale.value === 'zh-cn' ? 'zh-CN' : 'en-US'
  // 如果是今天，只显示时间
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString(localeCode, { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString(localeCode, { month: '2-digit', day: '2-digit' })
}

const formatMessageContent = (content) => {
  if (!content) return ''
  // 简单的 markdown 处理，实际项目中建议使用 markdown-it
  return content
    .replace(/\n/g, '<br>')
    .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
}

const formatCompactJson = (value) => {
  if (value === null || value === undefined) {
    return ''
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch (error) {
    return String(value)
  }
}

const mergeThinkingChunk = (existing, incoming) => {
  const current = String(existing || '')
  const next = String(incoming || '').trim()
  if (!next) {
    return current
  }

  if (!current) {
    return next
  }

  if (current.endsWith(next) || current.includes(`\n${next}`)) {
    return current
  }

  if (next.startsWith(current)) {
    return next
  }

  const joined = `${current}\n${next}`
  const maxLen = 12000
  if (joined.length <= maxLen) {
    return joined
  }
  return joined.slice(joined.length - maxLen)
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 开启新会话
const startNewChat = () => {
  assistantSessionStore.startNewChat()
  inputMessage.value = ''
}

// 切换会话
const switchToSession = async (session) => {
  try {
    await assistantSessionStore.selectSession(session)
    scrollToBottom()
  } catch (error) {
    console.error('Load messages failed:', error)
    ElMessage.error(t('assistant.messages.loadMessageFailed'))
  }
}

// 删除会话
const deleteSession = async (sessionId) => {
  try {
    await assistantSessionStore.removeSession(sessionId)
    ElMessage.success(t('assistant.messages.sessionDeleted'))
  } catch (error) {
    console.error('Delete session failed:', error)
    ElMessage.error(t('assistant.messages.deleteSessionFailed'))
  }
}

// 使用建议
const useSuggestion = (text) => {
  inputMessage.value = text
  sendMessage()
}

// 处理回车发送
const handleEnter = (e) => {
  if (!e.shiftKey && !sending.value) {
    sendMessage()
  }
}

const alphaStatusLabel = (run) => {
  const labels = {
    draft: '已创建',
    planning: '正在规划',
    awaiting_confirmation: '等待确认',
    executing: '正在执行',
    reflecting: '正在反思',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return labels[run.status] || run.status
}

const refreshAlphaRun = async () => {
  if (!activeAlphaRun.value) return
  try {
    const response = await api.get(`/ai-testing/alpha/runs/${activeAlphaRun.value.id}/`)
    activeAlphaRun.value = response.data
    const revision = response.data.active_revision
    const taskCount = revision?.task_nodes?.length || 0
    if (alphaStatusMessage.value) {
      alphaStatusMessage.value.content = `Alpha Agent：${alphaStatusLabel(response.data)}${taskCount ? `，已生成 ${taskCount} 个任务` : ''}`
      alphaStatusMessage.value.isPending = ['draft', 'planning', 'awaiting_confirmation', 'executing', 'reflecting'].includes(response.data.status)
    }
    if (!['draft', 'planning', 'awaiting_confirmation', 'executing', 'reflecting'].includes(response.data.status) && alphaPollTimer) {
      window.clearInterval(alphaPollTimer)
      alphaPollTimer = null
    }
  } catch (error) {
    if (alphaStatusMessage.value) {
      alphaStatusMessage.value.content = 'Alpha Agent 状态查询失败'
      alphaStatusMessage.value.isPending = false
    }
    if (alphaPollTimer) {
      window.clearInterval(alphaPollTimer)
      alphaPollTimer = null
    }
  }
}

const startAlphaTask = async () => {
  const revision = activeAlphaRun.value?.active_revision
  if (!revision) return
  try {
    await api.post(`/ai-testing/alpha/runs/${activeAlphaRun.value.id}/start/`, { revision_id: revision.id })
    await refreshAlphaRun()
    if (!alphaPollTimer) alphaPollTimer = window.setInterval(refreshAlphaRun, 3000)
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '无法开始 Alpha Agent 任务')
  }
}

const stopAlphaTask = async () => {
  try {
    await api.post(`/ai-testing/alpha/runs/${activeAlphaRun.value.id}/cancel/`)
    await refreshAlphaRun()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '无法停止 Alpha Agent 任务')
  }
}

const sendAlphaAgentMessage = async (text) => {
  if (!currentSession.value) {
    currentSession.value = { title: 'Alpha Agent' }
  }
  const userMessage = {
    role: 'user',
    content: text,
    created_at: new Date().toISOString(),
  }
  const agentMessage = {
    role: 'assistant',
    content: 'Alpha Agent：正在创建工作流',
    isPending: true,
  }
  messages.value.push(userMessage, agentMessage)
  alphaStatusMessage.value = agentMessage
  scrollToBottom()

  const created = await api.post('/ai-testing/alpha/runs/', { original_request: text })
  activeAlphaRun.value = created.data
  await api.post(`/ai-testing/alpha/runs/${created.data.id}/plan/`)
  await assistantSessionStore.loadAlphaRuns()
  await refreshAlphaRun()
  if (alphaPollTimer) window.clearInterval(alphaPollTimer)
  alphaPollTimer = window.setInterval(refreshAlphaRun, 3000)
}

const getStreamAuthToken = async () => {
  if (userStore.isTokenExpired && userStore.refreshToken) {
    await userStore.refreshAccessToken()
  } else if (userStore.isTokenExpiringSoon && userStore.refreshToken) {
    await userStore.refreshAccessToken()
  }
  return userStore.accessToken
}

const stopStreamingReply = () => {
  if (activeStreamController.value) {
    activeStreamController.value.abort()
    activeStreamController.value = null
  }
}

const parseSSEChunk = (rawChunk, onEvent) => {
  const events = rawChunk.split('\n\n')
  const remaining = events.pop() || ''

  for (const eventBlock of events) {
    const lines = eventBlock.split('\n')
    const dataLines = lines
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trim())

    if (dataLines.length === 0) {
      continue
    }

    const payloadText = dataLines.join('')
    if (!payloadText || payloadText === '[DONE]') {
      continue
    }

    let payload = null
    try {
      payload = JSON.parse(payloadText)
    } catch (error) {
      console.error('SSE payload parse failed:', payloadText, error)
      continue
    }

    onEvent(payload)
  }

  return remaining
}

const streamAssistantMessage = async ({ sessionId, message, onEvent, signal }) => {
  const token = await getStreamAuthToken()
  const response = await fetch('/api/assistant/chat/send_message_stream/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    signal,
    body: JSON.stringify({
      session_id: sessionId,
      message,
      thinking_mode: enableThinkingMode.value
    })
  })

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`
    try {
      const errorPayload = await response.json()
      errorMessage = errorPayload.error || errorPayload.detail || errorMessage
    } catch (error) {
      // ignore parse errors and fallback to HTTP status text
      errorMessage = response.statusText || errorMessage
    }
    throw new Error(errorMessage)
  }

  if (!response.body) {
    throw new Error('浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let idleTimer = null

  const resetIdleTimer = () => {
    if (idleTimer) {
      clearTimeout(idleTimer)
    }
    idleTimer = setTimeout(() => {
      reader.cancel().catch(() => {})
    }, 45000)
  }

  try {
    resetIdleTimer()
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }

      resetIdleTimer()
      buffer += decoder.decode(value, { stream: true })
      buffer = parseSSEChunk(buffer, onEvent)
    }
  } finally {
    if (idleTimer) {
      clearTimeout(idleTimer)
    }
  }

  const tail = decoder.decode()
  if (tail) {
    buffer += tail
  }
  if (buffer.trim()) {
    parseSSEChunk(`${buffer}\n\n`, onEvent)
  }
}

// 发送消息
const sendMessage = async () => {
  const text = inputMessage.value.trim()
  if (!text || sending.value) return

  if (assistantMode.value === 'agent') {
    inputMessage.value = ''
    sending.value = true
    try {
      await sendAlphaAgentMessage(text)
    } catch (error) {
      ElMessage.error(error.response?.data?.detail || 'Alpha Agent 启动失败')
      if (alphaStatusMessage.value) {
        alphaStatusMessage.value.content = error.response?.data?.detail || 'Alpha Agent 启动失败'
        alphaStatusMessage.value.isPending = false
      }
    } finally {
      sending.value = false
    }
    return
  }
  
  inputMessage.value = ''
  sending.value = true
  
  // 1. 立即上屏用户消息
  const tempUserMsg = {
    role: 'user',
    content: text,
    created_at: new Date().toISOString()
  }
  messages.value.push(tempUserMsg)
  
  // 2. 添加一个临时的"思考中"消息
  const tempAiMsg = {
    role: 'assistant',
    content: '',
    thinking: '',
    usage: null,
    tool_contract_status: null,
    tool_contract_error: null,
    tool_call: null,
    tool_result: null,
    isPending: true
  }
  messages.value.push(tempAiMsg)
  scrollToBottom()
  
  try {
    // 如果是新会话（没有ID），先创建会话
    let sessionId = currentSession.value?.id
    let isFirstMessage = false
    
    if (!sessionId) {
      isFirstMessage = true
      const newSessionId = `session_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`
      // 智能生成标题（取前10个字）
      const title = text.length > 10 ? text.substring(0, 10) + '...' : text
      
      const sessionRes = await api.post('/assistant/sessions/', {
        session_id: newSessionId,
        title: title
      })
      
      currentSession.value = sessionRes.data
      sessionId = currentSession.value.session_id // 注意：后端返回的是对象，这里需要用 session_id 字段
      
      // 立即添加到历史列表
      historySessions.value.unshift(currentSession.value)
    } else {
      // 如果是已有会话，使用 session_id 字段
      sessionId = currentSession.value.session_id
    }
    
    const controller = new AbortController()
    activeStreamController.value = controller

    let donePayload = null
    await streamAssistantMessage({
      sessionId,
      message: text,
      signal: controller.signal,
      onEvent: (event) => {
        if (event.type === 'chunk') {
          tempAiMsg.content += event.content || ''
          scrollToBottom()
          return
        }

        if (event.type === 'replace') {
          tempAiMsg.content = event.content || tempAiMsg.content
          scrollToBottom()
          return
        }

        if (event.type === 'thinking') {
          const mergedThinking = mergeThinkingChunk(tempAiMsg.thinking, event.content)
          if (mergedThinking !== tempAiMsg.thinking) {
            tempAiMsg.thinking = mergedThinking
            scrollToBottom()
          }
          return
        }

        if (event.type === 'done') {
          donePayload = event
          return
        }

        if (event.type === 'error') {
          throw new Error(event.error || t('assistant.messages.sendFailed'))
        }
      }
    })

    tempAiMsg.isPending = false

    if (donePayload?.assistant_message) {
      const serverAssistant = donePayload.assistant_message
      tempAiMsg.id = serverAssistant.id
      tempAiMsg.created_at = serverAssistant.created_at
      tempAiMsg.conversation_id = serverAssistant.conversation_id
      tempAiMsg.message_id = serverAssistant.message_id
      tempAiMsg.content = serverAssistant.content || tempAiMsg.content
      tempAiMsg.usage = donePayload.usage || null
      tempAiMsg.tool_contract_status = donePayload.tool_contract_status || null
      tempAiMsg.tool_contract_error = donePayload.tool_contract_error || null
      tempAiMsg.tool_call = donePayload.tool_call || null
      tempAiMsg.tool_result = donePayload.tool_result || null
    }

    // 更新会话的 conversation_id
    if (donePayload?.conversation_id && currentSession.value) {
      currentSession.value.conversation_id = donePayload.conversation_id
    }
    
    // 如果是第一次对话，更新历史列表中的会话信息（比如 updated_at）
    if (!isFirstMessage) {
      const index = historySessions.value.findIndex(s => s.id === currentSession.value.id)
      if (index !== -1) {
        historySessions.value[index] = { ...currentSession.value, updated_at: new Date().toISOString() }
        // 重新排序（移到最前）
        const updatedSession = historySessions.value.splice(index, 1)[0]
        historySessions.value.unshift(updatedSession)
      }
    }
    
  } catch (error) {
    console.error('Send failed:', error)
    tempAiMsg.isPending = false
    const isAbort = error?.name === 'AbortError'

    if (!tempAiMsg.content) {
      tempAiMsg.content = isAbort ? '已停止生成' : (error.message || t('assistant.messages.sendFailed'))
    }

    if (!isAbort) {
      ElMessage.error(error.message || t('assistant.messages.sendFailed'))
    }
  } finally {
    activeStreamController.value = null
    sending.value = false
    scrollToBottom()
  }
}

// 加载历史
const loadHistory = async () => {
  try {
    await assistantSessionStore.loadHistory()
  } catch (error) {
    console.error('Load history failed:', error)
  }
}

onMounted(() => {
  loadHistory()
  startNewChat()
})

watch(showThinking, (value) => {
  setStorageFlag('assistant_show_thinking', value)
})

watch(enableThinkingMode, (value) => {
  setStorageFlag('assistant_enable_thinking_mode', value)
})

onBeforeUnmount(() => {
  if (activeStreamController.value) {
    activeStreamController.value.abort()
    activeStreamController.value = null
  }
  if (alphaPollTimer) window.clearInterval(alphaPollTimer)
})
</script>

<style scoped lang="scss">
.assistant-layout {
  display: flex;
  height: calc(100vh - 60px);
  background: #fff;
  overflow: hidden;
}

.assistant-layout.has-alpha-task-tree {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
}

/* 左侧侧边栏 */
.sidebar {
  width: 260px;
  background: #f8fafc;
  border-right: 1px solid #eaecf0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  color: #475467;
  
  .new-chat-btn-wrapper {
    padding: 20px;
    
    .new-chat-btn {
      width: 100%;
      height: 40px;
      border-radius: 4px; /* 稍微减小圆角以匹配整体风格 */
      font-size: 14px;
      background: #1677ff;
      border-color: #1677ff;
      
      &:hover {
        background: #4096ff;
        border-color: #4096ff;
      }
    }
  }
  
  .history-list {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    
    .history-label {
      padding: 0 20px 10px;
      font-size: 12px;
      color: #667085;
    }
    
    .session-scroll-area {
      flex: 1;
      overflow-y: auto;
      padding: 0 10px;
      
      &::-webkit-scrollbar {
        width: 4px;
      }
      &::-webkit-scrollbar-thumb {
        background: #cbd5e1;
        border-radius: 2px;
      }
    }
    
    .session-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 12px;
      margin-bottom: 4px;
      border-radius: 4px;
      cursor: pointer;
      transition: all 0.2s;
      color: #475467;
      
      &:hover {
        background: #eef4ff;
        color: #1d4ed8;
        
        .session-actions {
          opacity: 1;
        }
      }
      
      &.active {
        background: #dbeafe;
        color: #1d4ed8;
      }
      
      .session-title-wrapper {
        display: flex;
        align-items: center;
        gap: 8px;
        flex: 1;
        overflow: hidden;
        
        .chat-icon {
          font-size: 16px;
        }
        
        .session-title {
          font-size: 14px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
      }
      
      .session-actions {
        opacity: 0;
        transition: opacity 0.2s;
        
        .delete-icon {
          font-size: 14px;
          color: #98a2b3;
          &:hover {
            color: #ff4d4f;
          }
        }
      }
    }
  }
  
}

/* 右侧主内容区 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  background: #fff;
}

.alpha-task-tree {
  overflow: hidden;
  border-left: 1px solid #eaecf0;
  background: #f8fafc;
}

.alpha-task-tree-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
  padding: 0 16px;
  border-bottom: 1px solid #eaecf0;
  background: #fff;
  color: #344054;
  font-size: 13px;
  font-weight: 600;
}

.alpha-task-tree-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.alpha-task-tree-empty {
  padding: 20px 16px;
  color: #98a2b3;
  font-size: 13px;
}

.alpha-task-node {
  display: grid;
  gap: 5px;
  padding: 14px 16px;
  border-bottom: 1px solid #eaecf0;
  background: #f8fafc;
}

.alpha-task-node strong {
  color: #344054;
  font-size: 13px;
}

.alpha-task-node span {
  color: #667085;
  font-size: 12px;
}

.alpha-task-node p {
  margin: 0;
  color: #d92d20;
  font-size: 12px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  flex-shrink: 0;
  padding: 20px 24px;
  border-bottom: 1px solid #eaecf0;
  background: #f8fafc;

  h2 {
    margin: 0;
    color: #1c2b3a;
    font-size: 22px;
    font-weight: 700;
  }

  p {
    margin: 6px 0 0;
    color: #667085;
    font-size: 14px;
  }
}

/* 场景1：欢迎页（新会话） */
.welcome-screen {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding-bottom: 100px;
  
  .welcome-content {
    width: 100%;
    max-width: 800px;
    padding: 0 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  
  .logo-area {
    text-align: center;
    margin-bottom: 40px;
    
    .logo-circle {
      width: 80px;
      height: 80px;
      background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 20px;
      box-shadow: 0 10px 20px rgba(79, 172, 254, 0.3);
      
      .el-icon {
        font-size: 40px;
        color: white;
      }
    }
    
    h1 {
      font-size: 28px;
      color: #303133;
      margin: 0 0 10px;
    }
    
    p {
      color: #909399;
      font-size: 16px;
      margin: 0;
    }

    .welcome-mode-switch {
      margin-top: 14px;
      display: inline-flex;
      align-items: center;
      gap: 8px;

      .label {
        font-size: 13px;
        color: #606266;
      }
    }
  }
  
  .center-input-wrapper {
    isolation: isolate;
    padding: 0;
    border-radius: 18px;
    overflow: hidden;
    background: #fff;
    box-shadow: 0 10px 28px rgba(91, 140, 255, 0.22), 0 8px 22px rgba(166, 108, 255, 0.16);
    width: 100%;
    margin-bottom: 30px;
    display: flex;
    flex-direction: column;
    
    .center-input {
      :deep(.el-textarea__inner) {
        border: 0;
        border-radius: 0;
        padding: 16px;
        font-size: 16px;
        box-shadow: none;
        background: transparent;
        transition: all 0.3s;
        
        &:focus {
          box-shadow: none;
        }
      }
    }
    
    .input-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 16px 14px;
    }

    .input-mode-tools {
      display: flex;
      align-items: center;
      gap: 8px;
    }
  }
  
  .suggestion-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    justify-content: center;
    
    .chip {
      padding: 8px 16px;
      background: #f5f7fa;
      border-radius: 20px;
      font-size: 14px;
      color: #606266;
      cursor: pointer;
      transition: all 0.2s;
      
      &:hover {
        background: #e6f1fc;
        color: #409eff;
      }
    }
  }
}

/* 场景2：对话页 */
.chat-screen {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  
  .chat-header {
    height: 60px;
    border-bottom: 1px solid #f0f2f5;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
    flex-shrink: 0;
    
    .chat-title {
      font-size: 16px;
      font-weight: 600;
      color: #303133;
    }
    
    .chat-time {
      font-size: 12px;
      color: #909399;
    }

    .chat-header-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }
  }
  
  .messages-container {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    background: #fff;
    
    .message-row {
      display: flex;
      gap: 16px;
      margin-bottom: 24px;
      
      &.user {
        flex-direction: row-reverse;

        .message-bubble {
          background: #409eff;
          color: #fff;
          border-radius: 12px 12px 0 12px;

          :deep(pre) {
            background: rgba(0, 0, 0, 0.1);
          }

          :deep(code) {
            background: rgba(0, 0, 0, 0.1);
            color: #fff;
          }
        }
      }
      
      &.assistant {
        .message-bubble {
          background: #f5f7fa;
          color: #303133;
          border-radius: 12px 12px 12px 0;
        }
      }
      
      .avatar {
        flex-shrink: 0;
        margin-top: 2px;
        
        .user-avatar {
          background: #c0c4cc;
        }
        
        .ai-avatar {
          background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }
      }
      
      .message-bubble {
        max-width: 70%;
        padding: 12px 16px;
        font-size: 15px;
        line-height: 1.6;
        position: relative;
        
        .message-content {
          word-wrap: break-word;
          
          :deep(p) {
            margin: 0 0 8px 0;
            &:last-child { margin: 0; }
          }
          
          :deep(pre) {
            background: #282c34;
            color: #abb2bf;
            padding: 12px;
            border-radius: 8px;
            overflow-x: auto;
            margin: 8px 0;
          }
          
          :deep(code) {
            font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
          }
        }

        .thinking-block {
          margin: 0 0 10px;
          padding: 8px 10px;
          border: 1px dashed #dcdfe6;
          border-radius: 8px;
          background: #fafafa;

          summary {
            cursor: pointer;
            font-size: 13px;
            color: #606266;
            user-select: none;
          }

          .thinking-content {
            margin-top: 8px;
            white-space: pre-wrap;
            font-size: 13px;
            color: #606266;
            line-height: 1.6;
          }
        }
        
        .message-status {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 13px;
          color: #909399;
          
          .is-loading {
            animation: rotating 2s linear infinite;
          }
        }

        .message-usage {
          margin-top: 8px;
          font-size: 12px;
          color: #909399;
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }

        .tool-debug-block {
          margin-top: 8px;
          border: 1px dashed #dcdfe6;
          border-radius: 8px;
          padding: 6px 8px;
          background: #fff;

          summary {
            cursor: pointer;
            font-size: 12px;
            color: #606266;
            user-select: none;
          }

          .tool-debug-content {
            margin-top: 6px;
            font-size: 12px;
            color: #606266;
            white-space: pre-wrap;
            line-height: 1.5;
          }
        }
      }
    }
  }
  
  .chat-footer {
    padding: 20px 24px;
    border-top: 1px solid #f0f2f5;
    background: #fff;
    
    .input-box {
      border: 1px solid #e4e7ed;
      border-radius: 12px;
      padding: 8px;
      background: #fff;
      transition: all 0.3s;
      display: flex;
      flex-direction: column;
      
      &:focus-within {
        border-color: #409eff;
        box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.1);
      }
      
      :deep(.el-textarea__inner) {
        border: none;
        box-shadow: none;
        padding: 8px;
        background: transparent;
      }

      .input-toolbar {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 8px;
        padding-top: 8px;
      }

      .input-mode-tools {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      
      .send-btn {
        margin-left: auto;
        width: 32px;
        height: 32px;
        padding: 0;
        border-radius: 8px;
      }

      .stop-btn {
        height: 32px;
        padding: 0 10px;
      }
    }
    
    .footer-tip {
      text-align: center;
      font-size: 12px;
      color: #c0c4cc;
      margin-top: 8px;
    }
  }
}

.mode-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #475467;
  cursor: pointer;
}

.mode-icon .el-icon {
  font-size: 17px;
}

.mode-icon:hover {
  color: #1570ef;
}

.mode-symbol,
.menu-mode-symbol {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
}

.mode-symbol {
  width: 24px;
  height: 24px;
}

.menu-mode-symbol {
  width: 18px;
  height: 18px;
  margin-right: 8px;
  vertical-align: middle;
}

.chat-symbol svg {
  width: 20px;
  height: 20px;
  overflow: visible;
}

.robot-face {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  width: 14px;
  height: 11px;
  padding: 1.5px;
  border: 0;
  border-radius: 3px;
  position: relative;
  isolation: isolate;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
}

.robot-face::after {
  content: '';
  position: absolute;
  inset: 1.5px;
  border-radius: 1.5px;
  background: #fff;
  z-index: 0;
}

.robot-face::before {
  content: '';
  position: absolute;
  top: -4px;
  width: 1.5px;
  height: 3px;
  background: linear-gradient(#3b82f6, #8b5cf6);
  z-index: 2;
}

.robot-face i {
  position: relative;
  z-index: 1;
  width: 2px;
  height: 2px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
}

.thinking-control {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #667085;
  font-size: 11px;
  line-height: 1;
}

.thinking-control :deep(.el-switch) {
  --el-switch-on-color: #409eff;
  --el-switch-off-color: #c0c4cc;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>