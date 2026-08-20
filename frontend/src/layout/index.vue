<template>
  <div class="layout">
    <el-container>
      <!-- 侧边栏 -->
      <el-aside width="240px" v-if="currentModule !== 'meta-projects'">
        <div class="logo" @click="router.push('/home')" style="cursor: pointer;">
          <img :src="logoImage" alt="TestHub" class="logo-img" />
        </div>
        <el-menu
          :default-active="$route.path"
          router
          background-color="#001529"
          text-color="#fff"
          active-text-color="#1890ff"
        >
          <!-- AI用例生成模块菜单 -->
          <template v-if="currentModule === 'ai-generation'">
            <el-sub-menu index="requirement">
              <template #title>
                <el-icon><MagicStick /></el-icon>
                <span>{{ $t('menu.intelligentCaseGeneration') }}</span>
              </template>
              <el-menu-item index="/ai-generation/requirement-analysis">{{ $t('menu.aiCaseGeneration') }}</el-menu-item>
              <el-menu-item index="/ai-generation/generated-testcases">{{ $t('menu.aiGeneratedTestcases') }}</el-menu-item>
            </el-sub-menu>
            <el-menu-item index="/ai-generation/knowledge-base">
              <el-icon><FolderOpened /></el-icon>
              <span>{{ $t('menu.knowledgeBase') }}</span>
            </el-menu-item>
            <el-menu-item index="/ai-generation/projects">
              <el-icon><Folder /></el-icon>
              <span>{{ $t('menu.projectManagement') }}</span>
            </el-menu-item>
            <el-menu-item index="/ai-generation/testcases">
              <el-icon><Document /></el-icon>
              <span>{{ $t('menu.testCases') }}</span>
            </el-menu-item>
            <el-menu-item index="/ai-generation/versions">
              <el-icon><Flag /></el-icon>
              <span>{{ $t('menu.versionManagement') }}</span>
            </el-menu-item>
            <el-sub-menu index="reviews">
              <template #title>
                <el-icon><Check /></el-icon>
                <span>{{ $t('menu.reviewManagement') }}</span>
              </template>
              <el-menu-item index="/ai-generation/reviews">{{ $t('menu.reviewList') }}</el-menu-item>
              <el-menu-item index="/ai-generation/review-templates">{{ $t('menu.reviewTemplates') }}</el-menu-item>
            </el-sub-menu>

            <el-menu-item index="/ai-generation/executions">
              <el-icon><VideoPlay /></el-icon>
              <span>{{ $t('menu.testPlan') }}</span>
            </el-menu-item>
            <el-menu-item index="/ai-generation/reports">
              <el-icon><DataAnalysis /></el-icon>
              <span>{{ $t('menu.testReport') }}</span>
            </el-menu-item>
          </template>

          <template v-else-if="currentModule === 'assistant'">
            <div class="assistant-session-sidebar">
              <svg class="assistant-history-gradient-definitions" aria-hidden="true">
                <defs>
                  <linearGradient id="assistant-history-icon-gradient" x1="0" y1="0" x2="1" y2="1">
                    <stop stop-color="#3b82f6" />
                    <stop offset="1" stop-color="#8b5cf6" />
                  </linearGradient>
                </defs>
              </svg>
              <el-button type="primary" class="assistant-new-session" :icon="Plus" @click="startAssistantSession">
                {{ $t('assistant.newChat') }}
              </el-button>
              <el-collapse v-model="assistantHistoryTabs" class="assistant-history">
                <el-collapse-item name="chat">
                  <template #title><span class="assistant-history-tab-title"><el-icon class="assistant-history-mode-icon assistant-history-gradient"><ChatDotSquare /></el-icon><span>Chat</span></span></template>
                  <button
                    v-for="session in assistantHistory"
                    :key="session.id"
                    type="button"
                    :class="{ active: assistantCurrentSession?.id === session.id && assistantMode === 'chat' }"
                    @click="selectAssistantSession(session)"
                  >
                    <el-icon class="assistant-history-mode-icon assistant-history-gradient"><ChatDotSquare /></el-icon>
                    <span>{{ session.title || $t('assistant.newChat') }}</span>
                    <el-icon class="assistant-history-delete" @click.stop="deleteAssistantSession(session.id)"><Delete /></el-icon>
                  </button>
                </el-collapse-item>
                <el-collapse-item name="agent">
                  <template #title><span class="assistant-history-tab-title"><el-icon class="assistant-history-mode-icon assistant-history-gradient"><Service /></el-icon><span>Agent</span></span></template>
                  <button
                    v-for="run in assistantAlphaRuns"
                    :key="run.id"
                    type="button"
                    :class="{ active: assistantActiveAlphaRun?.id === run.id && assistantMode === 'agent' }"
                    @click="selectAssistantAlphaRun(run)"
                  >
                    <el-icon class="assistant-history-mode-icon assistant-history-gradient"><Service /></el-icon>
                    <span>{{ run.original_request }}</span>
                    <el-icon class="assistant-history-delete" @click.stop="deleteAssistantAlphaRun(run.id)"><Delete /></el-icon>
                  </button>
                </el-collapse-item>
              </el-collapse>
            </div>
          </template>

          <template v-else-if="currentModule === 'data-factory'">
            <el-menu-item index="/data-factory">
              <el-icon><DataAnalysis /></el-icon>
              <span>{{ $t('home.dataFactory') }}</span>
            </el-menu-item>
            <el-menu-item index="/data-factory/warehouse">
              <el-icon><FolderOpened /></el-icon>
              <span>{{ $t('dataFactory.scenarios.warehouse') }}</span>
            </el-menu-item>
            <el-menu-item index="/data-factory/test_data">
              <el-icon><Files /></el-icon>
              <span>{{ $t('dataFactory.scenarios.test_data') }}</span>
            </el-menu-item>
            <el-menu-item index="/data-factory/business">
              <el-icon><Collection /></el-icon>
              <span>{{ $t('dataFactory.scenarios.business') }}</span>
            </el-menu-item>
            <el-menu-item index="/data-factory/json">
              <el-icon><Edit /></el-icon>
              <span>{{ $t('dataFactory.scenarios.json') }}</span>
            </el-menu-item>
            <el-menu-item index="/data-factory/string">
              <el-icon><Document /></el-icon>
              <span>{{ $t('dataFactory.scenarios.string') }}</span>
            </el-menu-item>
            <el-menu-item index="/data-factory/encoding">
              <el-icon><Connection /></el-icon>
              <span>{{ $t('dataFactory.scenarios.encoding') }}</span>
            </el-menu-item>
            <el-menu-item index="/data-factory/random">
              <el-icon><MagicStick /></el-icon>
              <span>{{ $t('dataFactory.scenarios.random') }}</span>
            </el-menu-item>
            <el-menu-item index="/data-factory/encryption">
              <el-icon><Lock /></el-icon>
              <span>{{ $t('dataFactory.scenarios.encryption') }}</span>
            </el-menu-item>
            <el-menu-item index="/data-factory/crontab">
              <el-icon><Timer /></el-icon>
              <span>{{ $t('dataFactory.scenarios.crontab') }}</span>
            </el-menu-item>
          </template>

          <!-- API自动化测试模块菜单 -->
          <template v-else-if="currentModule === 'api-automation'">
            <el-menu-item index="/api-automation/dashboard">
              <el-icon><Odometer /></el-icon>
              <span>{{ $t('menu.apiAutomationDashboard') }}</span>
            </el-menu-item>
            <el-menu-item index="/api-automation/cases">
              <el-icon><Document /></el-icon>
              <span>{{ $t('menu.apiAutomationCases') }}</span>
            </el-menu-item>
            <el-menu-item index="/api-automation/interfaces">
              <el-icon><Link /></el-icon>
              <span>{{ $t('menu.apiAutomationInterfaces') }}</span>
            </el-menu-item>
            <el-menu-item index="/api-automation/coverage">
              <el-icon><DataAnalysis /></el-icon>
              <span>{{ $t('menu.apiAutomationCoverage') }}</span>
            </el-menu-item>
            <el-menu-item index="/api-automation/runs">
              <el-icon><VideoPlay /></el-icon>
              <span>{{ $t('menu.apiAutomationRuns') }}</span>
            </el-menu-item>
            <el-menu-item index="/api-automation/reports">
              <el-icon><DataAnalysis /></el-icon>
              <span>{{ $t('menu.apiAutomationReports') }}</span>
            </el-menu-item>
            <el-menu-item index="/api-automation/scheduled-tasks">
              <el-icon><AlarmClock /></el-icon>
              <span>{{ $t('menu.apiAutomationSchedules') }}</span>
            </el-menu-item>
            <el-menu-item index="/api-automation/notification-logs">
              <el-icon><Bell /></el-icon>
              <span>{{ $t('menu.apiAutomationNotifications') }}</span>
            </el-menu-item>
            <el-menu-item index="/api-automation/logs">
              <el-icon><Monitor /></el-icon>
              <span>{{ $t('menu.apiAutomationLogs') }}</span>
            </el-menu-item>
          </template>

          <template v-else-if="currentModule === 'health-check'">
            <el-menu-item index="/health-check">
              <el-icon><Odometer /></el-icon>
              <span>{{ $t('menu.healthCheck') }}</span>
            </el-menu-item>
          </template>

          <!-- UI自动化测试模块菜单 -->
          <template v-else-if="currentModule === 'ui-automation'">
            <el-menu-item index="/ui-automation/dashboard">
              <el-icon><Odometer /></el-icon>
              <span>{{ $t('menu.dashboard') }}</span>
            </el-menu-item>
            <el-menu-item index="/ui-automation/projects">
              <el-icon><Folder /></el-icon>
              <span>{{ $t('menu.projectManagement') }}</span>
            </el-menu-item>
            <el-menu-item index="/ui-automation/elements-enhanced">
              <el-icon><Aim /></el-icon>
              <span>{{ $t('menu.elementManagement') }}</span>
            </el-menu-item>
            <el-menu-item index="/ui-automation/test-cases">
              <el-icon><Document /></el-icon>
              <span>{{ $t('menu.caseManagement') }}</span>
            </el-menu-item>
            <el-menu-item index="/ui-automation/scripts-enhanced">
              <el-icon><Edit /></el-icon>
              <span>{{ $t('menu.scriptGeneration') }}</span>
            </el-menu-item>
            <el-menu-item index="/ui-automation/scripts">
              <el-icon><DocumentCopy /></el-icon>
              <span>{{ $t('menu.scriptList') }}</span>
            </el-menu-item>
            <el-menu-item index="/ui-automation/suites">
              <el-icon><Collection /></el-icon>
              <span>{{ $t('menu.suiteManagement') }}</span>
            </el-menu-item>
            <el-menu-item index="/ui-automation/executions">
              <el-icon><VideoPlay /></el-icon>
              <span>{{ $t('menu.executionRecords') }}</span>
            </el-menu-item>
            <el-menu-item index="/ui-automation/reports">
              <el-icon><DataAnalysis /></el-icon>
              <span>{{ $t('menu.testReport') }}</span>
            </el-menu-item>
            <el-menu-item index="/ui-automation/scheduled-tasks">
              <el-icon><AlarmClock /></el-icon>
              <span>{{ $t('menu.scheduledTasks') }}</span>
            </el-menu-item>
            <el-menu-item index="/ui-automation/notification-logs">
              <el-icon><Bell /></el-icon>
              <span>{{ $t('menu.notificationList') }}</span>
            </el-menu-item>
          </template>

          <!-- APP自动化测试模块菜单 -->
          <template v-else-if="currentModule === 'app-automation'">
            <el-menu-item index="/app-automation/dashboard">
              <el-icon><Odometer /></el-icon>
              <span>{{ $t('menu.appDashboard') }}</span>
            </el-menu-item>
            <el-menu-item index="/app-automation/projects">
              <el-icon><Folder /></el-icon>
              <span>{{ $t('menu.appProjectManagement') }}</span>
            </el-menu-item>
            <el-menu-item index="/app-automation/devices">
              <el-icon><Cellphone /></el-icon>
              <span>{{ $t('menu.appDeviceManagement') }}</span>
            </el-menu-item>
            <el-menu-item index="/app-automation/packages">
              <el-icon><Collection /></el-icon>
              <span>{{ $t('menu.appPackageManagement') }}</span>
            </el-menu-item>
            <el-menu-item index="/app-automation/elements">
              <el-icon><Aim /></el-icon>
              <span>{{ $t('menu.appElementManagement') }}</span>
            </el-menu-item>
            <el-menu-item index="/app-automation/scene-builder">
              <el-icon><Connection /></el-icon>
              <span>{{ $t('menu.appSceneBuilder') }}</span>
            </el-menu-item>
            <el-menu-item index="/app-automation/test-cases">
              <el-icon><Document /></el-icon>
              <span>{{ $t('menu.appTestCases') }}</span>
            </el-menu-item>
            <el-menu-item index="/app-automation/test-suites">
              <el-icon><FolderOpened /></el-icon>
              <span>{{ $t('menu.appTestSuites') }}</span>
            </el-menu-item>
            <el-menu-item index="/app-automation/executions">
              <el-icon><VideoPlay /></el-icon>
              <span>{{ $t('menu.appExecutionRecords') }}</span>
            </el-menu-item>
            <el-menu-item index="/app-automation/reports">
              <el-icon><DataAnalysis /></el-icon>
              <span>{{ $t('menu.appTestReports') }}</span>
            </el-menu-item>
            <el-menu-item index="/app-automation/scheduled-tasks">
              <el-icon><AlarmClock /></el-icon>
              <span>{{ $t('menu.appScheduledTasks') }}</span>
            </el-menu-item>
            <el-menu-item index="/app-automation/notification-logs">
              <el-icon><Bell /></el-icon>
              <span>{{ $t('menu.appNotificationList') }}</span>
            </el-menu-item>
          </template>

          <!-- AI 智能模式模块菜单 -->
          <template v-else-if="currentModule === 'ai-intelligent-mode'">
            <el-menu-item index="/ai-intelligent-mode/projects">
              <el-icon><Folder /></el-icon>
              <span>{{ $t('menu.aiProjectManagement') }}</span>
            </el-menu-item>
            <el-menu-item index="/ai-intelligent-mode/testing">
              <el-icon><VideoPlay /></el-icon>
              <span>{{ $t('menu.aiIntelligentTesting') }}</span>
            </el-menu-item>
            <el-menu-item index="/ai-intelligent-mode/cases">
              <el-icon><Document /></el-icon>
              <span>{{ $t('menu.aiCaseManagement') }}</span>
            </el-menu-item>
            <el-menu-item index="/ai-intelligent-mode/execution-records">
              <el-icon><Timer /></el-icon>
              <span>{{ $t('menu.aiExecutionRecords') }}</span>
            </el-menu-item>
          </template>

          <!-- 项目管理模块 - 不显示侧边菜单 -->


          <!-- 配置中心模块菜单 -->
          <template v-else-if="currentModule === 'configuration'">
            <el-menu-item index="/configuration/project-center">
              <el-icon><Folder /></el-icon>
              <span>{{ $t('menu.projectManagementCenter') }}</span>
            </el-menu-item>
            <el-menu-item index="/configuration/env-setting">
              <el-icon><Connection /></el-icon>
              <span>{{ $t('menu.apiAutomationEnvironment') }}</span>
            </el-menu-item>
            <el-sub-menu index="ai-case-generation">
              <template #title>
                <el-icon><MagicStick /></el-icon>
                <span>{{ $t('menu.aiCaseGenerationConfig') }}</span>
              </template>
              <el-menu-item index="/configuration/ai-gen/config-model">
                <el-icon><Cpu /></el-icon>
                <span>{{ $t('menu.aiModelConfig') }}</span>
              </el-menu-item>
              <el-menu-item index="/configuration/ai-gen/config-prompt">
                <el-icon><Edit /></el-icon>
                <span>{{ $t('menu.promptConfigCenter') }}</span>
              </el-menu-item>
              <el-menu-item index="/configuration/ai-gen/config-param">
                <el-icon><Setting /></el-icon>
                <span>{{ $t('menu.generationConfig') }}</span>
              </el-menu-item>
            </el-sub-menu>
            <el-sub-menu index="ai-intelligent-config">
              <template #title>
                <el-icon><Cpu /></el-icon>
                <span>{{ $t('menu.aiModeConfig') }}</span>
              </template>
              <el-menu-item index="/configuration/ai-test/config-model">
                <span>{{ $t('menu.aiModeModelConfig') }}</span>
              </el-menu-item>
              <el-menu-item index="/configuration/ai-test/config-prompt">
                <span>{{ $t('menu.aiModePromptConfig') }}</span>
              </el-menu-item>
            </el-sub-menu>
            <el-sub-menu index="ai-agent-config">
              <template #title>
                <el-icon><ChatDotRound /></el-icon>
                <span>AI智能体配置</span>
              </template>
              <el-menu-item index="/configuration/ai-agent/config-model">模型配置</el-menu-item>
              <el-menu-item index="/configuration/ai-agent/config-prompt">提示词配置</el-menu-item>
            </el-sub-menu>
            <el-menu-item index="/configuration/app-setting">
              <el-icon><Cellphone /></el-icon>
              <span>{{ $t('menu.appEnvConfig') }}</span>
            </el-menu-item>
            <el-menu-item index="/configuration/ui-setting">
              <el-icon><Monitor /></el-icon>
              <span>{{ $t('menu.uiEnvConfig') }}</span>
            </el-menu-item>
            <el-menu-item index="/configuration/knowledge-base">
              <el-icon><FolderOpened /></el-icon>
              <span>{{ $t('menu.knowledgeBaseConfig') }}</span>
            </el-menu-item>
            <el-menu-item index="/configuration/notify">
              <el-icon><Timer /></el-icon>
              <span>{{ $t('menu.scheduledTaskConfig') }}</span>
            </el-menu-item>
          </template>
        </el-menu>
      </el-aside>

      <!-- 主体内容 -->
    <el-container>
      <!-- 顶部导航 -->
      <el-header height="60px" :class="{ 'header-full': currentModule === 'meta-projects' }">
        <div class="header-content">
            <div class="header-left">
              <el-breadcrumb separator="/">
                <el-breadcrumb-item :to="{ path: '/home' }">{{ $t('nav.home') }}</el-breadcrumb-item>
                <el-breadcrumb-item v-if="moduleName">{{ moduleName }}</el-breadcrumb-item>
                <el-breadcrumb-item v-if="showProjectManagement">{{ $t('menu.projectManagementCenter') }}</el-breadcrumb-item>
                <el-breadcrumb-item>{{ breadcrumbTitle }}</el-breadcrumb-item>
              </el-breadcrumb>
            </div>
            <div class="header-right">
              <!-- 语言切换 -->
              <el-dropdown @command="handleLanguageChange" class="language-dropdown">
                <span class="language-selector">
                  <span class="language-flag">{{ appStore.language === 'zh-cn' ? '🇨🇳' : '🇺🇸' }}</span>
                  <span>{{ currentLanguage }}</span>
                  <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="zh-cn" :disabled="appStore.language === 'zh-cn'">
                      <span class="dropdown-flag">🇨🇳</span> 简体中文
                    </el-dropdown-item>
                    <el-dropdown-item command="en" :disabled="appStore.language === 'en'">
                      <span class="dropdown-flag">🇺🇸</span> English
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>

              <!-- 用户信息 -->
              <el-dropdown @command="handleCommand" class="user-dropdown">
                <span class="user-info">
                  <el-avatar :size="32" :src="userStore.user?.avatar" />
                  <span class="username">{{ userStore.user?.username }}</span>
                  <el-icon><ArrowDown /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="profile">{{ $t('nav.profile') }}</el-dropdown-item>
                    <el-dropdown-item divided command="logout">{{ $t('nav.logout') }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </el-header>

        <!-- 页面内容 -->
        <el-main>
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useAppStore } from '@/stores/app'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import {
  Monitor, Folder, Document, Flag, Check, Collection, VideoPlay,
  DataAnalysis, ChatDotSquare, Service, DocumentCopy, Link, MagicStick,
  Odometer, Timer, Setting, AlarmClock, Bell, Aim, Edit, Cpu, ArrowDown, Cellphone, Connection, FolderOpened, Files, User
} from '@element-plus/icons-vue'
import logoSvg from '@/assets/images/logo.svg'
import logoHomePng from '@/assets/images/logo_home.png'
import { assistantSessionStore } from '@/stores/assistantSession'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const appStore = useAppStore()
const { t } = useI18n()
const assistantHistory = assistantSessionStore.historySessions
const assistantCurrentSession = assistantSessionStore.currentSession
const assistantAlphaRuns = assistantSessionStore.alphaRuns
const assistantActiveAlphaRun = assistantSessionStore.activeAlphaRun
const assistantMode = assistantSessionStore.assistantMode
const assistantHistoryTabs = ref(['chat', 'agent'])

const startAssistantSession = () => {
  assistantSessionStore.startNewChat()
  assistantSessionStore.assistantMode.value = 'chat'
}

const selectAssistantSession = async (session) => {
  try {
    await assistantSessionStore.selectSession(session)
    assistantSessionStore.assistantMode.value = 'chat'
  } catch (error) {
    ElMessage.error(t('assistant.messages.loadMessageFailed'))
  }
}

const selectAssistantAlphaRun = async (run) => {
  try {
    await assistantSessionStore.selectAlphaRun(run)
  } catch (error) {
    ElMessage.error('无法加载 Alpha Agent 运行')
  }
}

const deleteAssistantSession = async (sessionId) => {
  try {
    await assistantSessionStore.removeSession(sessionId)
    ElMessage.success(t('assistant.messages.sessionDeleted'))
  } catch (error) {
    ElMessage.error(t('assistant.messages.deleteSessionFailed'))
  }
}

const deleteAssistantAlphaRun = async (runId) => {
  try {
    await assistantSessionStore.removeAlphaRun(runId)
    ElMessage.success('Alpha Agent 历史已删除')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '无法删除活动中的 Alpha Agent 任务')
  }
}

const logoImage = computed(() => {
		return route.path === '/home' ? logoSvg : logoHomePng
	})
	

// 当前语言显示
const currentLanguage = computed(() => {
  return appStore.language === 'zh-cn' ? '简体中文' : 'English'
})

// 切换语言（无需刷新页面）
const handleLanguageChange = (lang) => {
  appStore.setLanguage(lang)
  ElMessage.success(lang === 'zh-cn' ? '语言已切换为中文' : 'Language switched to English')
}

const currentModule = computed(() => {
  if (route.path.startsWith('/ai-generation')) return 'ai-generation'
  if (route.path.startsWith('/assistant')) return 'assistant'
  if (route.path.startsWith('/data-factory')) return 'data-factory'
  if (route.path.startsWith('/health-check')) return 'health-check'
  if (route.path.startsWith('/api-automation')) return 'api-automation'
  if (route.path.startsWith('/ui-automation')) return 'ui-automation'
  if (route.path.startsWith('/app-automation')) return 'app-automation'
  if (route.path.startsWith('/ai-intelligent-mode')) return 'ai-intelligent-mode'
  if (route.path.startsWith('/configuration')) return 'configuration'
  if (route.path.startsWith('/meta-projects')) return 'meta-projects'
  return ''
})

watch(currentModule, async (moduleName) => {
  if (moduleName !== 'assistant') return
  try {
    await Promise.all([
      assistantSessionStore.loadHistory(),
      assistantSessionStore.loadAlphaRuns(),
    ])
  } catch (error) {
    ElMessage.error('无法加载会话历史')
  }
}, { immediate: true })

const moduleName = computed(() => {
  const map = {
    'ai-generation': t('modules.aiGeneration'),
    'assistant': t('home.aiEvaluator'),
    'data-factory': t('home.dataFactory'),
    'health-check': t('modules.healthCheck'),
    'api-automation': t('modules.apiAutomation'),
    'ui-automation': t('modules.uiAutomation'),
    'app-automation': t('modules.appAutomation'),
    'ai-intelligent-mode': t('modules.aiIntelligentMode'),
    'configuration': t('modules.configuration'),
    'meta-projects': t('modules.unifiedProject')
  }
  return map[currentModule.value] || ''
})

const breadcrumbTitle = computed(() => {
  const routeMap = {
    // AI用例生成
    '/ai-generation/requirement-analysis': t('menu.aiCaseGeneration'),
    '/ai-generation/generated-testcases': t('menu.aiGeneratedTestcases'),
    '/ai-generation/knowledge-base': t('menu.knowledgeBase'),
    '/ai-generation/projects': t('menu.projectManagement'),
    '/ai-generation/testcases': t('menu.testCases'),
    '/ai-generation/versions': t('menu.versionManagement'),
    '/ai-generation/reviews': t('menu.reviewList'),
    '/ai-generation/review-templates': t('menu.reviewTemplates'),
    '/ai-generation/testsuites': t('menu.suiteManagement'),
    '/ai-generation/executions': t('menu.executionRecords'),
    '/ai-generation/reports': t('menu.testReport'),
    '/assistant': t('assistant.title'),

    '/data-factory': t('home.dataFactory'),
    '/data-factory/warehouse': t('dataFactory.scenarios.warehouse'),

    '/health-check': t('menu.healthCheck'),

    // API自动化测试
    '/api-automation/dashboard': t('menu.apiAutomationDashboard'),
    '/api-automation/cases': t('menu.apiAutomationCases'),
    '/api-automation/interfaces': t('menu.apiAutomationInterfaces'),
    '/api-automation/coverage': t('menu.apiAutomationCoverage'),
    '/api-automation/runs': t('menu.apiAutomationRuns'),
    '/api-automation/reports': t('menu.apiAutomationReports'),
    '/api-automation/scheduled-tasks': t('menu.apiAutomationSchedules'),
    '/api-automation/notification-logs': t('menu.apiAutomationNotifications'),
    '/api-automation/logs': t('menu.apiAutomationLogs'),

    // UI自动化测试
    '/ui-automation/dashboard': t('menu.dashboard'),
    '/ui-automation/projects': t('menu.projectManagement'),
    '/ui-automation/elements-enhanced': t('menu.elementManagement'),
    '/ui-automation/test-cases': t('menu.caseManagement'),
    '/ui-automation/scripts-enhanced': t('menu.scriptGeneration'),
    '/ui-automation/scripts': t('menu.scriptList'),
    '/ui-automation/suites': t('menu.suiteManagement'),
    '/ui-automation/executions': t('menu.executionRecords'),
    '/ui-automation/reports': t('menu.testReport'),
    '/ui-automation/scheduled-tasks': t('menu.scheduledTasks'),
    '/ui-automation/notification-logs': t('menu.notificationList'),

    // APP自动化测试
    '/app-automation/dashboard': t('menu.appDashboard'),
    '/app-automation/projects': t('menu.appProjectManagement'),
    '/app-automation/devices': t('menu.appDeviceManagement'),
    '/app-automation/packages': t('menu.appPackageManagement'),
    '/app-automation/elements': t('menu.appElementManagement'),
    '/app-automation/scene-builder': t('menu.appSceneBuilder'),
    '/app-automation/test-cases': t('menu.appTestCases'),
    '/app-automation/test-suites': t('menu.appTestSuites'),
    '/app-automation/scheduled-tasks': t('menu.appScheduledTasks'),
    '/app-automation/notification-logs': t('menu.appNotificationList'),
    '/app-automation/executions': t('menu.appExecutionRecords'),
    '/app-automation/reports': t('menu.appTestReports'),

    // AI 智能模式
    '/ai-intelligent-mode/testing': t('menu.aiIntelligentTesting'),
    '/ai-intelligent-mode/projects': t('menu.aiProjectManagement'),
    '/ai-intelligent-mode/cases': t('menu.aiCaseManagement'),
    '/ai-intelligent-mode/execution-records': t('menu.aiExecutionRecords'),


    // 项目管理
    '/configuration/project-center': t('menu.projectManagementCenter'),
    '/configuration/meta-projects': t('menu.projectManagementCenter'),

    // 配置中心
    '/configuration/ai-gen/config-model': t('menu.aiModelConfig'),
    '/configuration/ai-gen/config-prompt': t('menu.promptConfigCenter'),
    '/configuration/ai-gen/config-param': t('menu.generationConfig'),
    '/configuration/knowledge-base': t('menu.knowledgeBaseConfig'),
    '/configuration/ui-setting': t('menu.uiEnvConfig'),
    '/configuration/env-setting': t('menu.apiAutomationEnvironment'),
    '/configuration/app-setting': t('menu.appEnvConfig'),
    '/configuration/ai-test/config-model': t('menu.aiModeModelConfig'),
    '/configuration/ai-test/config-prompt': t('menu.aiModePromptConfig'),
    '/configuration/ai-agent/config-model': 'AI智能体配置',
    '/configuration/notify': t('menu.scheduledTaskConfig'),

    '/profile': t('nav.profile')
  }

  const path = route.path
  if (path.match(/^\/configuration\/meta-projects\/[^/]+$/)) {
    const queryName = route.query.name
    const nameStr = Array.isArray(queryName) ? queryName[0] : queryName
    const projectName = nameStr ? decodeURIComponent(nameStr) : sessionStorage.getItem('metaProjectName')
    return projectName || t('menu.projectManagementCenter')
  }

  if (path.startsWith('/data-factory/')) {
    return t(`dataFactory.scenarios.${path.split('/')[2]}`)
  }

  return routeMap[path] || route.meta.title || ''
})

const showProjectManagement = computed(() => {
  return route.path.startsWith('/configuration/meta-projects/')
})

const handleCommand = (command) => {
  if (command === 'logout') {
    userStore.logout()
    ElMessage.success('退出登录成功')
    router.push('/login')
  } else if (command === 'profile') {
    router.push('/ai-generation/profile')
  }
}
</script>

<style lang="scss" scoped>
.layout {
  height: 100vh;
  width: 100vw;
  overflow: hidden;
}

.layout > .el-container {
  height: 100%;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #001529;
  color: white;
  border-bottom: 1px solid #1f1f1f;
  flex-shrink: 0;

		.logo-img {
			width: 100%;
			height: 100%;
			object-fit: fill;
		}
	}

.el-aside {
  background-color: #001529;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.3s ease;
  width: 240px !important;

  .el-menu {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    border-right: none;
    
    &::-webkit-scrollbar {
      width: 0;
    }
  }
}

.el-menu {
  :deep(.el-sub-menu__title),
  :deep(.el-menu-item) {
    font-size: 14px;
  }
}

.assistant-session-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px 12px;
}

.assistant-new-session {
  width: 100%;
  justify-content: flex-start;
}

.assistant-history {
  margin-top: 16px;
  border-top: 1px solid #1f3b55;
  border-bottom: 0;
  overflow: hidden;
}

.assistant-history :deep(.el-collapse-item__header) {
  height: 36px;
  border-bottom: 1px solid #1f3b55;
  background: transparent;
  color: #d6e4ff;
  font-size: 12px;
}

.assistant-history :deep(.el-collapse-item__header .el-icon) {
  margin-right: 8px;
}

.assistant-history-tab-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 100%;
}

.assistant-history-tab-title .el-icon {
  margin-right: 0 !important;
}

.assistant-history-mode-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
}

.assistant-history-gradient-definitions {
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
}

.assistant-history-gradient :deep(path) {
  fill: url(#assistant-history-icon-gradient);
}

.assistant-history :deep(.el-collapse-item__wrap),
.assistant-history :deep(.el-collapse-item__content) {
  border-bottom: 0;
  background: transparent;
}

.assistant-history :deep(.el-collapse-item__content) {
  padding-bottom: 6px;
}

.assistant-history button {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) 16px;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 36px;
  padding: 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: #d6e4ff;
  cursor: pointer;
  text-align: left;
}

.assistant-history button:hover,
.assistant-history button.active {
  background: #112a45;
}

.assistant-history button.active {
  box-shadow: inset 3px 0 0 #1890ff;
  color: #fff;
}

.assistant-history span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.assistant-history-delete {
  opacity: 0;
}

.assistant-history button:hover .assistant-history-delete {
  opacity: 1;
}

.el-menu--collapse {
  width: 64px !important;
  
  :deep(.el-sub-menu__title),
  :deep(.el-menu-item) {
    padding-left: 20px !important;
  }
  
  :deep(.el-sub-menu__title span),
  :deep(.el-menu-item span) {
    display: none;
  }
}

.el-container .el-container {
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.el-header {
  background-color: white;
  border-bottom: 1px solid #e8e8e8;
  padding: 0;
  flex-shrink: 0;
  height: 60px !important;

  &.header-full {
    .header-content {
      max-width: 100%;
    }
  }

  .header-content {
    height: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 20px;
    max-width: calc(100% - 240px);
  }

  .header-left {
    flex: 1;
    overflow: hidden;
    
    :deep(.el-breadcrumb) {
      font-size: 14px;
    }
  }

  .user-info {
    display: flex;
    align-items: center;
    cursor: pointer;
    white-space: nowrap;

    .username {
      margin: 0 8px;
      color: #303133;
      font-size: 14px;
    }
  }
}

.header-right {
    display: flex;
    align-items: center;
    gap: 20px;
  }

  .language-dropdown {
    .language-selector {
      display: flex;
      align-items: center;
      cursor: pointer;
      color: #303133;
      font-size: 14px;
      outline: none;

      &:focus {
        outline: none;
      }

      .language-flag {
        font-size: 18px;
        margin-right: 5px;
        line-height: 1;
      }

      span {
        margin: 0 4px;
      }

      &:hover {
        color: #1890ff;
      }
    }
  }

  .dropdown-flag {
    font-size: 16px;
    margin-right: 5px;
  }

  .user-dropdown {
    .user-info {
      display: flex;
      align-items: center;
      cursor: pointer;
      white-space: nowrap;

      .username {
        margin: 0 8px;
        color: #303133;
      }
    }
  }

.el-main {
  background-color: #f5f5f5;
  padding: 20px;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

@media screen and (max-width: 1920px) {
  .el-aside {
    width: 220px !important;
  }
  
  .el-main {
    padding: 18px;
  }
}

@media screen and (max-width: 1600px) {
  .el-aside {
    width: 200px !important;
  }
  
  .el-main {
    padding: 16px;
  }

  .el-menu {
    :deep(.el-sub-menu__title),
    :deep(.el-menu-item) {
      font-size: 13px;
    }
  }
}

@media screen and (max-width: 1440px) {
  .el-aside {
    width: 180px !important;
  }
  
  .el-main {
    padding: 14px;
  }

  .el-menu {
    :deep(.el-sub-menu__title),
    :deep(.el-menu-item) {
      font-size: 13px;
    }
  }
}

@media screen and (max-width: 1366px) {
  .el-aside {
    width: 180px !important;
  }
  
  .el-main {
    padding: 12px;
  }

  .el-header {
    height: 56px !important;
  }
  
  .el-menu {
    :deep(.el-sub-menu__title),
    :deep(.el-menu-item) {
      font-size: 12px;
    }
  }
}

@media screen and (max-width: 1280px) {
  .el-aside {
    width: 160px !important;
  }
  
  .el-main {
    padding: 12px;
  }

  .el-header {
    height: 56px !important;
    
    .header-content {
      padding: 0 15px;
    }
  }
  
  .el-menu {
    :deep(.el-sub-menu__title),
    :deep(.el-menu-item) {
      font-size: 12px;
      padding-left: 15px !important;
    }
  }
}

@media screen and (max-width: 1024px) {
  .el-aside {
    width: 140px !important;
  }
  
  .el-main {
    padding: 10px;
  }

  .el-header {
    height: 52px !important;
    
    .header-content {
      padding: 0 12px;
    }
  }
  
  .el-menu {
    :deep(.el-sub-menu__title),
    :deep(.el-menu-item) {
      font-size: 12px;
      padding-left: 12px !important;
    }
  }
  
  .user-info .username {
    display: none;
  }
}

@media screen and (max-width: 768px) {
  .el-aside {
    position: fixed;
    left: 0;
    top: 0;
    z-index: 1000;
    width: 240px !important;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    
    &.mobile-open {
      transform: translateX(0);
    }
  }
  
  .el-main {
    padding: 8px;
  }

  .el-header {
    height: 50px !important;
    
    .header-content {
      padding: 0 10px;
    }
    
    .header-left {
      :deep(.el-breadcrumb__item) {
        &:not(:last-child) {
          display: none;
        }
      }
    }
  }
}

@media screen and (max-width: 480px) {
  .el-aside {
    width: 220px !important;
  }
  
  .el-main {
    padding: 6px;
  }

  .el-header {
    height: 48px !important;
    
    .header-content {
      padding: 0 8px;
    }
  }
  
  .user-info {
    .el-avatar {
      width: 28px !important;
      height: 28px !important;
    }
  }
}
</style>