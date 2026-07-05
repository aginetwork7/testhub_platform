<template>
  <div class="assistant-layout">
    <!-- 左侧侧边栏 -->
    <div class="sidebar">
      <div class="new-chat-btn-wrapper">
        <el-button type="primary" class="new-chat-btn" @click="startNewChat" :icon="Plus">
          {{ $t('assistant.newChat') }}
        </el-button>
      </div>
      
      <div class="history-list">
        <div class="history-label">{{ $t('assistant.historyChat') }}</div>
        <div class="session-scroll-area">
          <div 
            v-for="session in historySessionsDescending" 
            :key="session.id"
            :class="['session-item', { active: currentSession?.id === session.id }]"
            @click="switchToSession(session)"
          >
            <div class="session-title-wrapper">
              <el-icon class="chat-icon"><ChatDotRound /></el-icon>
              <span class="session-title" :title="session.title">{{ session.title || $t('assistant.newChat') }}</span>
            </div>
            <div class="session-actions" @click.stop>
              <el-popconfirm :title="$t('assistant.deleteSessionConfirm')" @confirm="deleteSession(session.id)">
                <template #reference>
                  <el-icon class="delete-icon"><Delete /></el-icon>
                </template>
              </el-popconfirm>
            </div>
          </div>
        </div>
      </div>
      
      <div class="user-profile">
        <el-dropdown trigger="click" @command="handleCommand">
          <div class="user-info">
            <el-avatar :size="32" :icon="UserFilled" />
            <span class="username">{{ userStore.user?.username || $t('assistant.user') }}</span>
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="home">{{ $t('assistant.goHome') }}</el-dropdown-item>
              <el-dropdown-item command="logout" divided>{{ $t('assistant.logout') }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 右侧主内容区 -->
    <div class="main-content">
      <!-- 场景1：新会话（居中输入框） -->
      <div v-if="isNewChatMode" class="welcome-screen">
        <div class="welcome-content">
          <div class="logo-area">
            <div class="logo-circle">
              <el-icon><Cpu /></el-icon>
            </div>
            <h1>{{ $t('assistant.title') }}</h1>
            <p>{{ $t('assistant.subtitle') }}</p>
            <div class="welcome-mode-switch">
              <span class="label">回答模式</span>
              <el-switch
                v-model="enableThinkingMode"
                inline-prompt
                active-text="思考"
                inactive-text="直答"
                size="small"
              />
            </div>
          </div>
          
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
            <div class="input-actions">
              <el-button 
                type="primary" 
                circle 
                :icon="Promotion" 
                :disabled="!inputMessage.trim()"
                @click="sendMessage"
              />
            </div>
          </div>
          
          <div class="suggestion-chips">
            <div class="chip" @click="useSuggestion($t('assistant.suggestions.apiTestQuestion'))">{{ $t('assistant.suggestions.apiTest') }}</div>
            <div class="chip" @click="useSuggestion($t('assistant.suggestions.performancePlanQuestion'))">{{ $t('assistant.suggestions.performancePlan') }}</div>
            <div class="chip" @click="useSuggestion($t('assistant.suggestions.testTheoryQuestion'))">{{ $t('assistant.suggestions.testTheory') }}</div>
            <div class="chip" @click="useSuggestion($t('assistant.suggestions.automationDebugQuestion'))">{{ $t('assistant.suggestions.automationDebug') }}</div>
          </div>
        </div>
      </div>

      <!-- 场景2：对话界面 -->
      <div v-else class="chat-screen">
        <div class="chat-header">
          <span class="chat-title">{{ currentSession?.title || $t('assistant.newChat') }}</span>
          <div class="chat-header-actions">
            <el-switch
              v-model="enableThinkingMode"
              inline-prompt
              active-text="思考"
              inactive-text="直答"
              size="small"
            />
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
                v-if="message.role === 'assistant' && (message.tool_contract_status || message.tool_call || message.tool_contract_error)"
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
          <div class="footer-tip">{{ $t('assistant.aiDisclaimer') }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, ChatDotRound, User, Cpu, Promotion, Loading, UserFilled, ArrowDown } from '@element-plus/icons-vue'
import api from '@/utils/api'

const router = useRouter()
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
const historySessions = ref([])
const currentSession = ref(null)
const messages = ref([])
const inputMessage = ref('')
const sending = ref(false)
const messagesContainer = ref(null)
const activeStreamController = ref(null)
const enableThinkingMode = ref(getStorageFlag('assistant_enable_thinking_mode', true))
const showThinking = ref(getStorageFlag('assistant_show_thinking', true))

const handleCommand = (command) => {
  if (command === 'logout') {
    handleLogout()
  } else if (command === 'home') {
    router.push('/home')
  }
}

const handleLogout = () => {
  ElMessageBox.confirm(t('assistant.logoutConfirm'), t('assistant.logoutTitle'), {
    confirmButtonText: t('assistant.confirm'),
    cancelButtonText: t('assistant.cancel'),
    type: 'warning'
  }).then(() => {
    userStore.logout()
    router.push('/login')
    ElMessage.success(t('assistant.loggedOut'))
  }).catch(() => {})
}

// 计算属性
const historySessionsDescending = computed(() => {
  return [...historySessions.value].sort((a, b) => 
    new Date(b.updated_at) - new Date(a.updated_at)
  )
})

const isNewChatMode = computed(() => {
  // 如果没有当前会话，或者当前会话没有消息且没有ID（临时会话），则显示新会话模式
  return !currentSession.value || (!currentSession.value.id && messages.value.length === 0)
})

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
  currentSession.value = { title: t('assistant.newChat') } // 临时会话对象
  messages.value = []
  inputMessage.value = ''
}

// 切换会话
const switchToSession = async (session) => {
  if (currentSession.value?.id === session.id) return
  
  try {
    currentSession.value = { ...session }
    const response = await api.get(`/assistant/sessions/${session.id}/messages/`)
    messages.value = response.data
    scrollToBottom()
  } catch (error) {
    console.error('Load messages failed:', error)
    ElMessage.error(t('assistant.messages.loadMessageFailed'))
  }
}

// 删除会话
const deleteSession = async (sessionId) => {
  try {
    await api.delete(`/assistant/sessions/${sessionId}/`)
    historySessions.value = historySessions.value.filter(s => s.id !== sessionId)
    
    if (currentSession.value?.id === sessionId) {
      startNewChat()
    }
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
    const response = await api.get('/assistant/sessions/')
    historySessions.value = response.data.results || response.data || []
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
})
</script>

<style scoped lang="scss">
.assistant-layout {
  display: flex;
  height: 100vh;
  background: #fff;
  overflow: hidden;
}

/* 左侧侧边栏 */
.sidebar {
  width: 260px;
  background: #001529; /* 与主布局一致的深色背景 */
  border-right: 1px solid #1f1f1f;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  color: rgba(255, 255, 255, 0.65);
  
  .new-chat-btn-wrapper {
    padding: 20px;
    
    .new-chat-btn {
      width: 100%;
      height: 40px;
      border-radius: 4px; /* 稍微减小圆角以匹配整体风格 */
      font-size: 14px;
      background: #1890ff;
      border-color: #1890ff;
      color: white;
      
      &:hover {
        background: #40a9ff;
        border-color: #40a9ff;
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
      color: rgba(255, 255, 255, 0.45);
    }
    
    .session-scroll-area {
      flex: 1;
      overflow-y: auto;
      padding: 0 10px;
      
      &::-webkit-scrollbar {
        width: 4px;
      }
      &::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.2);
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
      color: rgba(255, 255, 255, 0.65);
      
      &:hover {
        background: rgba(255, 255, 255, 0.08);
        color: white;
        
        .session-actions {
          opacity: 1;
        }
      }
      
      &.active {
        background: #1890ff;
        color: white;
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
          color: rgba(255, 255, 255, 0.45);
          &:hover {
            color: #ff4d4f;
          }
        }
      }
    }
  }
  
  .user-profile {
    padding: 16px;
    border-top: 1px solid #1f1f1f;
    
    .user-info {
      display: flex;
      align-items: center;
      cursor: pointer;
      padding: 8px;
      border-radius: 4px;
      transition: all 0.2s;
      
      &:hover {
        background: rgba(255, 255, 255, 0.08);
      }
      
      .username {
        margin: 0 8px;
        font-size: 14px;
        color: rgba(255, 255, 255, 0.85);
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      
      .el-icon {
        color: rgba(255, 255, 255, 0.45);
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
    width: 100%;
    position: relative;
    margin-bottom: 30px;
    
    .center-input {
      :deep(.el-textarea__inner) {
        border-radius: 16px;
        padding: 16px 50px 16px 20px;
        font-size: 16px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
        border: 1px solid #e4e7ed;
        transition: all 0.3s;
        
        &:focus {
          box-shadow: 0 4px 20px rgba(64, 158, 255, 0.15);
          border-color: #409eff;
        }
      }
    }
    
    .input-actions {
      position: absolute;
      right: 10px;
      bottom: 10px;
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
      position: relative;
      border: 1px solid #e4e7ed;
      border-radius: 12px;
      padding: 8px;
      background: #fff;
      transition: all 0.3s;
      
      &:focus-within {
        border-color: #409eff;
        box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.1);
      }
      
      :deep(.el-textarea__inner) {
        border: none;
        box-shadow: none;
        padding: 8px 130px 8px 8px;
        background: transparent;
      }
      
      .send-btn {
        position: absolute;
        right: 8px;
        bottom: 8px;
        width: 32px;
        height: 32px;
        padding: 0;
        border-radius: 8px;
      }

      .stop-btn {
        position: absolute;
        right: 48px;
        bottom: 8px;
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

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>