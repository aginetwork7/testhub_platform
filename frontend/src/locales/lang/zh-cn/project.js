export default {
  unifiedProject: {
    title: '项目中心',
    createProject: '创建项目',
    editProject: '编辑项目',
    searchPlaceholder: '搜索项目名称',
    statusFilter: '筛选状态',
    projectName: '项目名称',
    description: '描述',
    modules: '模块',
    owner: '负责人',
    createdAt: '创建时间',
    actions: '操作',
    basicInfo: '基本信息',
    noModules: '暂无模块',
    dashboard: {
      title: '数据看板',
      totalProjects: '项目总数',
      apiProjects: 'API项目',
      aiProjects: 'AI用例生成项目',
      aiTestProjects: 'AI智能测试项目',
      uiProjects: 'UI项目',
      appProjects: 'APP项目',
      recentProjects: '最近项目',
      viewAll: '查看全部',
      noProjects: '暂无项目',
      quickActions: '快捷操作',
      createProject: '创建项目',
      manageProjects: '管理项目',
      apiTesting: 'API测试',
      uiAutomation: 'UI自动化',
      appAutomation: 'APP自动化',
      viewReports: '查看报告',
      moduleOverview: '模块概览',
      projects: '个项目',
      apiModule: {
        title: 'API测试模块',
        description: '支持HTTP/WebSocket协议的接口测试、环境管理、自动化测试'
      },
      uiModule: {
        title: 'UI自动化模块',
        description: '基于Playwright/Selenium的Web UI自动化测试'
      },
      appModule: {
        title: 'APP自动化模块',
        description: '基于Airtest的Android APP自动化测试'
      }
    },
    messages: {
      fetchListFailed: '获取项目列表失败',
      fetchDetailFailed: '获取项目详情失败',
      createSuccess: '项目创建成功',
      createFailed: '项目创建失败',
      updateSuccess: '项目更新成功',
      updateFailed: '项目更新失败',
      deleteSuccess: '项目删除成功',
      deleteFailed: '项目删除失败',
      deleteConfirm: '确认删除该项目？此操作不可恢复。'
    },
    moduleTypes: {
      AI: 'AI用例生成',
      AI_TEST: 'AI智能测试',
      API: 'API测试',
      UI: 'UI自动化',
      APP: 'APP自动化'
    }
  },
  project: {
    // List page
    projectManagement: '项目管理',
    newProject: '新建项目',
    searchPlaceholder: '搜索项目名称',
    statusFilter: '状态筛选',
    projectName: '项目名称',
    description: '描述',
    status: '状态',
    owner: '负责人',
    createdAt: '创建时间',
    actions: '操作',

    // Status
    notStarted: '未开始',
    active: '进行中',
    paused: '已暂停',
    completed: '已完成',
    archived: '已归档',

    // Dialog
    editProject: '编辑项目',
    createProject: '新建项目',
    projectNamePlaceholder: '请输入项目名称',
    projectDescription: '项目描述',
    projectDescriptionPlaceholder: '请输入项目描述',
    selectStatus: '请选择状态',
    update: '更新',
    create: '创建',

    // Validation
    projectNameRequired: '请输入项目名称',
    projectNameLength: '项目名称长度在 2 到 200 个字符',
    projectStatusRequired: '请选择项目状态',

    // Messages
    fetchListFailed: '获取项目列表失败',
    updateSuccess: '项目更新成功',
    createSuccess: '项目创建成功',
    updateFailed: '项目更新失败',
    createFailed: '项目创建失败',
    deleteConfirm: '确定要删除这个项目吗？',
    deleteSuccess: '项目删除成功',
    deleteFailed: '项目删除失败',

    // Detail page
    projectDetail: '项目详情',
    projectInfo: '项目信息',
    noDescription: '暂无描述',
    projectMembers: '项目成员',
    addMember: '添加成员',
    username: '用户名',
    email: '邮箱',
    role: '角色',
    joinedAt: '加入时间',
    removeMember: '删除',
    environments: '环境配置',
    addEnvironment: '添加环境',
    environmentName: '环境名称',
    baseUrl: '基础URL',
    defaultEnvironment: '默认环境',
    yes: '是',
    no: '否',
    fetchDetailFailed: '获取项目详情失败',
    memberDeleteSuccess: '成员删除成功',
    memberDeleteFailed: '删除成员失败'
  },
  home: {
    // Header
    user: '用户',
    logout: '退出登录',
    logoutConfirm: '确定要退出登录吗？',
    logoutSuccess: '已退出登录',

    // Language
    language: {
      current: '中文',
      zhCN: '简体中文',
      en: 'English'
    },

    // Title
    title: 'TestHub 测试平台',
    subtitle: '一站式智能化测试解决方案',

    // Cards
    aiCaseGeneration: 'AI用例生成',
    aiCaseGenerationDesc: '智能分析需求，自动生成测试用例',
    healthCheck: '健康监控',
    healthCheckDesc: '查看服务器性能指标与 TestHub 服务状态',
    uiAutomation: 'UI自动化测试',
    uiAutomationDesc: '可视化的Web/App UI自动化测试',
    appAutomation: 'APP自动化测试',
    appAutomationDesc: '基于Airtest的Android APP自动化测试',
    performanceAutomation: '性能自动化测试',
    performanceAutomationDesc: '自动执行性能测试并分析结果',
    dataFactory: '数据工厂',
    dataFactoryDesc: '灵活的测试数据构造与管理',
    unifiedProject: '项目管理',
    unifiedProjectDesc: '统一进行项目管理',
    aiIntelligentMode: 'AI智能测试',
    aiIntelligentModeDesc: '基于自然语言的智能化测试执行',
    aiBenchmark: 'AI基准测试',
    aiBenchmarkDesc: '评估AI测试能力与执行效果',
    aiEvaluator: 'AI智能体',
    aiEvaluatorDesc: '测试领域智能体以及知识问答',
    configCenter: '配置中心',
    configCenterDesc: '系统环境、AI模型及通知配置',
    taskManagement: '任务管理',
    taskManagementDesc: '统一管理测试任务',

    // Messages
    featureInDevelopment: '功能正在开发中......'
  },
  profile: {
    // Page
    title: '个人设置',
    basicInfo: '基本信息',
    changePassword: '修改密码',

    // Basic Info
    username: '用户名',
    email: '邮箱',
    name: '姓名',
    department: '部门',
    position: '职位',

    // Password
    currentPassword: '当前密码',
    newPassword: '新密码',
    confirmPassword: '确认密码',
    changePasswordButton: '修改密码'
  }
}
