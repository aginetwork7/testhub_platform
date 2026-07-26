import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

// 静态导入常用组件来避免动态导入问题
import Login from '@/views/auth/Login.vue'
import Register from '@/views/auth/Register.vue'
import Layout from '@/layout/index.vue'
import ProjectList from '@/views/projects/ProjectList.vue'
import Home from '@/views/Home.vue'
import DataFactory from '@/views/data-factory/DataFactory.vue'
import DataWarehouse from '@/views/data-factory/DataWarehouse.vue'
import HealthCheck from '@/views/health/HealthCheck.vue'
import ApiAutomationWorkspace from '@/views/api-automation/Workspace.vue'
import UiDashboard from '@/views/ui-automation/dashboard/Dashboard.vue'
import UiProjectList from '@/views/ui-automation/projects/ProjectList.vue'
import UiElementManagerEnhanced from '@/views/ui-automation/elements/ElementManagerEnhanced.vue'
import UiTestCaseManager from '@/views/ui-automation/test-cases/TestCaseManager.vue'
import UiScriptEditorEnhanced from '@/views/ui-automation/scripts/ScriptEditorEnhanced.vue'
import UiScriptList from '@/views/ui-automation/scripts/ScriptList.vue'
import UiSuiteList from '@/views/ui-automation/suites/SuiteList.vue'
import UiExecutionList from '@/views/ui-automation/executions/ExecutionList.vue'
import UiReportList from '@/views/ui-automation/reports/ReportList.vue'
import UiScheduledTasks from '@/views/ui-automation/scheduled-tasks/ScheduledTasks.vue'
import UiNotificationLogs from '@/views/ui-automation/notification/NotificationLogs.vue'
import UiAITesting from '@/views/ai-testing/AITesting.vue'
import UiAICaseList from '@/views/ai-testing/AICaseList.vue'
import UiAIExecutionRecords from '@/views/ai-testing/AIExecutionRecords.vue'
import UiAIProjectList from '@/views/ai-testing/AIProjectList.vue'

/** @type {import('vue-router').RouteRecordRaw[]} */
const routes = [
  {
    path: '/',
    redirect: '/home'
  },
  {
    path: '/home',
    name: 'Home',
    component: Home,
    meta: { requiresAuth: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { requiresGuest: true }
  },
  {
    path: '/register',
    name: 'Register',
    component: Register,
    meta: { requiresGuest: true }
  },
  {
    path: '/reports',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'list'
      },
      {
        path: 'list',
        name: 'ReportList',
        component: () => import('@/views/reports/ReportList.vue')
      },
      {
        path: 'schedule/:id',
        name: 'ScheduleReport',
        component: () => import('@/views/reports/ReportList.vue')
      }
    ]
  },
  {
    path: '/ai-generation',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'requirement-analysis'
      },
      {
        path: 'requirement-analysis',
        name: 'RequirementAnalysis',
        component: () => import('@/views/requirement-analysis/RequirementAnalysisView.vue')
      },
      {
        path: 'projects',
        name: 'Projects',
        component: ProjectList
      },
      {
        path: 'projects/:id',
        name: 'ProjectDetail',
        component: () => import('@/views/projects/ProjectDetail.vue')
      },
      {
        path: 'testcases',
        name: 'TestCases',
        component: () => import('@/views/testcases/TestCaseList.vue')
      },
      {
        path: 'testcases/create',
        name: 'CreateTestCase',
        component: () => import('@/views/testcases/TestCaseForm.vue')
      },
      {
        path: 'testcases/:id',
        name: 'TestCaseDetail',
        component: () => import('@/views/testcases/TestCaseDetail.vue')
      },
      {
        path: 'testcases/:id/edit',
        name: 'EditTestCase',
        component: () => import('@/views/testcases/TestCaseEdit.vue')
      },
      {
        path: 'versions',
        name: 'Versions',
        component: () => import('@/views/versions/VersionList.vue')
      },
      {
        path: 'reviews',
        name: 'Reviews',
        component: () => import('@/views/reviews/ReviewList.vue')
      },
      {
        path: 'reviews/create',
        name: 'CreateReview',
        component: () => import('@/views/reviews/ReviewForm.vue')
      },
      {
        path: 'reviews/:id',
        name: 'ReviewDetail',
        component: () => import('@/views/reviews/ReviewDetail.vue')
      },
      {
        path: 'reviews/:id/edit',
        name: 'EditReview',
        component: () => import('@/views/reviews/ReviewForm.vue')
      },
      {
        path: 'review-templates',
        name: 'ReviewTemplates',
        component: () => import('@/views/reviews/ReviewTemplateList.vue')
      },
      {
        path: 'testsuites',
        name: 'TestSuites',
        component: () => import('@/views/testsuites/TestSuiteList.vue')
      },
      {
        path: 'executions',
        name: 'Executions',
        component: () => import('@/views/executions/ExecutionListView.vue')
      },
      {
        path: 'executions/:id',
        name: 'ExecutionDetail',
        component: () => import('@/views/executions/ExecutionDetailView.vue')
      },
      {
        path: 'reports',
        name: 'AiTestReport',
        component: () => import('@/views/reports/AiTestReport.vue')
      },
      {
        path: 'generated-testcases',
        name: 'GeneratedTestCases',
        component: () => import('@/views/requirement-analysis/GeneratedTestCaseList.vue')
      },
      {
        path: 'knowledge-base',
        name: 'KnowledgeBase',
        component: () => import('@/views/knowledge-base/KnowledgeBaseList.vue')
      },
      {
        path: 'knowledge-base/:id',
        name: 'KnowledgeBaseDetail',
        component: () => import('@/views/knowledge-base/KnowledgeBaseDetail.vue')
      },
      {
        path: 'task-detail/:taskId',
        name: 'TaskDetail',
        component: () => import('@/views/requirement-analysis/TaskDetail.vue')
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/profile/UserProfile.vue')
      },
    ]
  },
  {
    path: '/assistant',
    component: Layout,
    meta: { requiresAuth: true },
    children: [{ path: '', name: 'Assistant', component: () => import('@/views/assistant/AssistantView.vue') }]
  },
  {
    path: '/health-check',
    component: Layout,
    meta: { requiresAuth: true },
    children: [{ path: '', name: 'HealthCheck', component: HealthCheck }]
  },
  {
    path: '/api-automation',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'dashboard'
      },
      {
        path: 'dashboard',
        name: 'ApiAutomationDashboard',
        component: ApiAutomationWorkspace,
        props: { mode: 'dashboard' }
      },
      {
        path: 'cases',
        name: 'ApiAutomationCases',
        component: ApiAutomationWorkspace,
        props: { mode: 'cases' }
      },
      {
        path: 'interfaces',
        name: 'ApiAutomationInterfaces',
        component: ApiAutomationWorkspace,
        props: { mode: 'interfaces' }
      },
      {
        path: 'coverage',
        name: 'ApiAutomationCoverage',
        component: ApiAutomationWorkspace,
        props: { mode: 'coverage' }
      },
      {
        path: 'runs',
        name: 'ApiAutomationRuns',
        component: ApiAutomationWorkspace,
        props: { mode: 'runs' }
      },
      {
        path: 'reports',
        name: 'ApiAutomationReports',
        component: ApiAutomationWorkspace,
        props: { mode: 'reports' }
      },
      {
        path: 'configurations',
        redirect: '/configuration/api-environment'
      },
      {
        path: 'scheduled-tasks',
        name: 'ApiAutomationScheduledTasks',
        component: ApiAutomationWorkspace,
        props: { mode: 'schedules' }
      },
      {
        path: 'notification-logs',
        name: 'ApiAutomationNotificationLogs',
        component: ApiAutomationWorkspace,
        props: { mode: 'notifications' }
      },
      {
        path: 'logs',
        name: 'ApiAutomationLogs',
        component: ApiAutomationWorkspace,
        props: { mode: 'logs' }
      }
    ]
  },
  {
    path: '/ui-automation',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'dashboard'
      },
      {
        path: 'dashboard',
        name: 'UiDashboard',
        component: UiDashboard
      },
      {
        path: 'projects',
        name: 'UiProjects',
        component: UiProjectList
      },
      {
        path: 'elements-enhanced',
        name: 'UiElementsEnhanced',
        component: UiElementManagerEnhanced
      },
      {
        path: 'test-cases',
        name: 'UiTestCases',
        component: UiTestCaseManager
      },
      {
        path: 'scripts-enhanced',
        name: 'UiScriptsEnhanced',
        component: UiScriptEditorEnhanced
      },
      {
        path: 'scripts/editor',
        name: 'UiScriptEditor',
        component: UiScriptEditorEnhanced
      },
      {
        path: 'scripts',
        name: 'UiScripts',
        component: UiScriptList
      },
      {
        path: 'suites',
        name: 'UiSuites',
        component: UiSuiteList
      },
      {
        path: 'executions',
        name: 'UiExecutions',
        component: UiExecutionList
      },
      {
        path: 'reports',
        name: 'UiReports',
        component: UiReportList
      },
      {
        path: 'scheduled-tasks',
        name: 'UiScheduledTasks',
        component: UiScheduledTasks
      },
      {
        path: 'notification-logs',
        name: 'UiNotificationLogs',
        component: UiNotificationLogs
      }
    ]
  },
  {
    path: '/ai-intelligent-mode',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'testing'
      },
      {
        path: 'testing',
        name: 'AITesting',
        component: UiAITesting,
        meta: {
          title: 'route.uiAITesting',
          icon: 'MagicStick',
          requiresAuth: true
        }
      },
      {
        path: 'projects',
        name: 'AIProjectList',
        component: UiAIProjectList,
        meta: {
          title: 'route.uiAIProjectList',
          icon: 'Folder',
          requiresAuth: true
        }
      },
      {
        path: 'cases',
        name: 'AICaseList',
        component: UiAICaseList,
        meta: {
          title: 'route.uiAICaseList',
          icon: 'Files',
          requiresAuth: true
        }
      },
      {
        path: 'execution-records',
        name: 'AIExecutionRecords',
        component: UiAIExecutionRecords,
        meta: {
          title: 'route.uiAIExecutionRecords',
          icon: 'Document',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/data-factory',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'DataFactory', component: DataFactory },
      { path: 'warehouse', name: 'DataWarehouse', component: DataWarehouse },
      { path: ':category', name: 'DataFactoryCategory', component: DataFactory }
    ]
  },
  {
    path: '/configuration',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        component: () => import('@/views/configuration/ConfigurationCenter.vue'),
        children: [
          {
            path: '',
            redirect: 'project-center'
          },
          {
            path: 'project-center',
            name: 'ConfigProjectCenter',
            component: () => import('@/views/unified-projects/Dashboard.vue')
          },
          {
            path: 'meta-projects/:id',
            name: 'ConfigMetaProjectDetail',
            component: () => import('@/views/unified-projects/UnifiedProjectDetail.vue')
          },
          {
            path: 'ai-model',
            name: 'ConfigAIModel',
            component: () => import('@/views/requirement-analysis/AIModelConfig.vue')
          },
          {
            path: 'prompt-config',
            name: 'ConfigPromptConfig',
            component: () => import('@/views/requirement-analysis/PromptConfig.vue')
          },
          {
            path: 'generation-config',
            name: 'ConfigGenerationConfig',
            component: () => import('@/views/requirement-analysis/GenerationConfigView.vue')
          },
          {
            path: 'knowledge-base',
            name: 'ConfigKnowledgeBase',
            component: () => import('@/views/configuration/KnowledgeBaseConfig.vue')
          },
          {
            path: 'ui-env',
            name: 'ConfigUIEnv',
            component: () => import('@/views/configuration/UIEnvironmentConfig.vue')
          },
          {
            path: 'api-environment',
            name: 'ConfigApiAutomationEnvironment',
            component: ApiAutomationWorkspace,
            props: { mode: 'configurations' }
          },
          {
            path: 'app-env',
            name: 'ConfigAppEnv',
            component: () => import('@/views/app-automation/settings/AppSettings.vue')
          },
          {
            path: 'ai-mode',
            name: 'ConfigAIMode',
            component: () => import('@/views/configuration/AIIntelligentModeConfig.vue')
          },
          {
            path: 'ai-mode-prompt',
            name: 'ConfigAIModePrompt',
            component: () => import('@/views/configuration/AIModePromptConfig.vue')
          },
          {
            path: 'scheduled-task',
            name: 'ConfigScheduledTask',
            component: () => import('@/views/ui-automation/notification/NotificationConfigs.vue')
          },
          {
            path: 'dify',
            name: 'DifyConfig',
            component: () => import('@/views/configuration/DifyConfig.vue')
          }
        ]
      }
    ]
  },
  // APP自动化测试路由
  {
    path: '/app-automation',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'dashboard'
      },
      {
        path: 'dashboard',
        name: 'AppAutomationDashboard',
        component: () => import('@/views/app-automation/dashboard/Dashboard.vue')
      },
      {
        path: 'projects',
        name: 'AppProjectList',
        component: () => import('@/views/app-automation/projects/ProjectList.vue')
      },
      {
        path: 'devices',
        name: 'AppDeviceList',
        component: () => import('@/views/app-automation/devices/DeviceList.vue')
      },
      {
        path: 'packages',
        name: 'AppPackageList',
        component: () => import('@/views/app-automation/packages/PackageList.vue')
      },
      {
        path: 'elements',
        name: 'AppElementList',
        component: () => import('@/views/app-automation/elements/ElementList.vue')
      },
      {
        path: 'scene-builder',
        name: 'AppSceneBuilder',
        component: () => import('@/views/app-automation/test-cases/SceneBuilder.vue'),
        meta: { title: '用例编排' }
      },
      {
        path: 'test-cases',
        name: 'AppTestCaseList',
        component: () => import('@/views/app-automation/test-cases/TestCaseList.vue')
      },
      {
        path: 'test-suites',
        name: 'AppTestSuiteList',
        component: () => import('@/views/app-automation/suites/SuiteList.vue')
      },
      {
        path: 'scheduled-tasks',
        name: 'AppScheduledTasks',
        component: () => import('@/views/app-automation/scheduled-tasks/ScheduledTasks.vue')
      },
      {
        path: 'notification-logs',
        name: 'AppNotificationLogs',
        component: () => import('@/views/app-automation/notification/NotificationLogs.vue')
      },
      {
        path: 'executions',
        name: 'AppExecutionList',
        component: () => import('@/views/app-automation/executions/ExecutionList.vue')
      },
      {
        path: 'reports',
        name: 'AppReportList',
        component: () => import('@/views/app-automation/reports/ReportList.vue')
      }
    ]
  },
  {
    path: '/meta-projects',
    component: Layout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: 'dashboard'
      },
      {
        path: 'dashboard',
        name: 'UnifiedProjectDashboard',
        component: () => import('@/views/unified-projects/Dashboard.vue')
      },
      {
        path: 'list',
        redirect: 'dashboard'
      },
      {
        path: ':id',
        name: 'UnifiedProjectDetail',
        component: () => import('@/views/unified-projects/UnifiedProjectDetail.vue')
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  const userStore = useUserStore()

  console.log('路由守卫:', {
    to: to.path,
    from: from.path,
    hasToken: !!userStore.accessToken,
    hasUser: !!userStore.user,
    isAuthenticated: userStore.isAuthenticated
  })

  // 只在应用初始化或从登录页面导航时初始化认证
  if (!userStore.user && userStore.accessToken) {
    try {
      console.log('初始化认证...')
      await userStore.initAuth()
      console.log('认证初始化完成:', {
        hasUser: !!userStore.user,
        isAuthenticated: userStore.isAuthenticated
      })
    } catch (error) {
      console.error('认证初始化失败:', error)
    }
  }

  if (to.meta.requiresAuth && !userStore.isAuthenticated) {
    console.log('需要认证但未认证，跳转到登录页')
    next('/login')
  } else if (to.meta.requiresGuest && userStore.isAuthenticated) {
    console.log('访客页面但已认证，跳转到项目页')
    next('/home')
  } else {
    console.log('路由守卫通过，继续导航')
    next()
  }
})

router.afterEach((to, from) => {
  console.log(`Navigated from ${from.path} to ${to.path}`)
})

export default router