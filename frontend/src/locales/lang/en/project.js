export default {
  unifiedProject: {
    title: 'Unified Project Management',
    createProject: 'Create Project',
    editProject: 'Edit Project',
    searchPlaceholder: 'Search project name',
    statusFilter: 'Filter by status',
    projectName: 'Project Name',
    description: 'Description',
    modules: 'Modules',
    owner: 'Owner',
    createdAt: 'Created At',
    actions: 'Actions',
    basicInfo: 'Basic Information',
    noModules: 'No modules yet',
    status: {
      notStarted: 'Not Started',
      active: 'Active',
      paused: 'Paused',
      completed: 'Completed',
      archived: 'Archived'
    },
    dashboard: {
      title: 'Dashboard',
      totalProjects: 'Total Projects',
      apiProjects: 'API Projects',
      aiProjects: 'AI Case Gen Projects',
      aiTestProjects: 'AI Smart Test Projects',
      uiProjects: 'UI Projects',
      appProjects: 'APP Projects',
      recentProjects: 'Recent Projects',
      viewAll: 'View All',
      noProjects: 'No projects yet',
      quickActions: 'Quick Actions',
      createProject: 'Create Project',
      manageProjects: 'Manage Projects',
      apiTesting: 'API Testing',
      uiAutomation: 'UI Automation',
      appAutomation: 'APP Automation',
      viewReports: 'View Reports',
      moduleOverview: 'Module Overview',
      projects: 'projects',
      apiModule: {
        title: 'API Testing Module',
        description: 'HTTP/WebSocket API testing, environment management, automated testing'
      },
      uiModule: {
        title: 'UI Automation Module',
        description: 'Web UI automation testing based on Playwright/Selenium'
      },
      appModule: {
        title: 'APP Automation Module',
        description: 'Android APP automation testing based on Airtest'
      }
    },
    messages: {
      fetchListFailed: 'Failed to fetch project list',
      fetchDetailFailed: 'Failed to fetch project details',
      createSuccess: 'Project created successfully',
      createFailed: 'Failed to create project',
      updateSuccess: 'Project updated successfully',
      updateFailed: 'Failed to update project',
      deleteSuccess: 'Project deleted successfully',
      deleteFailed: 'Failed to delete project',
      deleteConfirm: 'Are you sure to delete this project? This action cannot be undone.'
    },
    moduleTypes: {
      AI: 'AI Case Generation',
      AI_TEST: 'AI Smart Testing',
      API: 'API Testing',
      UI: 'UI Automation',
      APP: 'APP Automation'
    }
  },
  project: {
    // List page
    projectManagement: 'Project Management',
    newProject: 'New Project',
    searchPlaceholder: 'Search project name',
    statusFilter: 'Status Filter',
    projectName: 'Project Name',
    description: 'Description',
    status: 'Status',
    owner: 'Owner',
    createdAt: 'Created At',
    actions: 'Actions',

    // Status
    notStarted: 'Not Started',
    active: 'Active',
    paused: 'Paused',
    completed: 'Completed',
    archived: 'Archived',

    // Dialog
    editProject: 'Edit Project',
    createProject: 'New Project',
    projectNamePlaceholder: 'Enter project name',
    projectDescription: 'Project Description',
    projectDescriptionPlaceholder: 'Enter project description',
    selectStatus: 'Select status',
    update: 'Update',
    create: 'Create',

    // Validation
    projectNameRequired: 'Please enter project name',
    projectNameLength: 'Project name length must be between 2 and 200 characters',
    projectStatusRequired: 'Please select project status',

    // Messages
    fetchListFailed: 'Failed to fetch project list',
    updateSuccess: 'Project updated successfully',
    createSuccess: 'Project created successfully',
    updateFailed: 'Failed to update project',
    createFailed: 'Failed to create project',
    deleteConfirm: 'Are you sure to delete this project?',
    deleteSuccess: 'Project deleted successfully',
    deleteFailed: 'Failed to delete project',

    // Detail page
    projectDetail: 'Project Details',
    projectInfo: 'Project Info',
    noDescription: 'No description',
    projectMembers: 'Project Members',
    addMember: 'Add Member',
    username: 'Username',
    email: 'Email',
    role: 'Role',
    joinedAt: 'Joined At',
    removeMember: 'Remove',
    environments: 'Environments',
    addEnvironment: 'Add Environment',
    environmentName: 'Environment Name',
    baseUrl: 'Base URL',
    defaultEnvironment: 'Default Environment',
    yes: 'Yes',
    no: 'No',
    fetchDetailFailed: 'Failed to fetch project details',
    memberDeleteSuccess: 'Member deleted successfully',
    memberDeleteFailed: 'Failed to delete member'
  },
  home: {
    // Header
    user: 'User',
    logout: 'Logout',
    logoutConfirm: 'Are you sure to logout?',
    logoutSuccess: 'Logged out successfully',

    // Language
    language: {
      current: 'English',
      zhCN: '简体中文',
      en: 'English'
    },

    // Title
    title: 'TestHub Testing Platform',
    subtitle: 'All-in-One Intelligent Testing Solution',

    // Cards
    aiCaseGeneration: 'AI Case Generation',
    aiCaseGenerationDesc: 'Intelligently analyze requirements, auto-generate test cases',
    apiTesting: 'API Testing',
    apiTestingDesc: 'Efficient API automation testing and management',
    uiAutomation: 'UI Automation Testing',
    uiAutomationDesc: 'Visual Web/App UI automation testing',
    appAutomation: 'APP Automation Testing',
    appAutomationDesc: 'Android APP automation testing based on Airtest',
    dataFactory: 'Data Factory',
    dataFactoryDesc: 'Flexible test data construction and management',
    unifiedProject: 'Unified Project Management',
    unifiedProjectDesc: 'Cross-module unified project management platform',
    aiIntelligentMode: 'AI Intelligent Mode',
    aiIntelligentModeDesc: 'Natural language-based intelligent test execution',
    aiEvaluator: 'AI Evaluator',
    aiEvaluatorDesc: 'Professional software testing Q&A based on evaluator knowledge base',
    configCenter: 'Configuration Center',
    configCenterDesc: 'System environment, AI model and notification configuration',

    // Messages
    featureInDevelopment: 'Feature is under development......'
  },
  profile: {
    // Page
    title: 'Profile Settings',
    basicInfo: 'Basic Information',
    changePassword: 'Change Password',

    // Basic Info
    username: 'Username',
    email: 'Email',
    name: 'Name',
    department: 'Department',
    position: 'Position',

    // Password
    currentPassword: 'Current Password',
    newPassword: 'New Password',
    confirmPassword: 'Confirm Password',
    changePasswordButton: 'Change Password'
  }
}
