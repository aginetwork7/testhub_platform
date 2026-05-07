export const PROJECT_FORM_CONFIGS = {
  common: [
    {
      field: 'name',
      type: 'input',
      label: '项目名称',
      placeholder: '请输入项目名称',
      rules: [
        { required: true, message: '请输入项目名称' },
        { min: 2, max: 200, message: '长度在 2 到 200 个字符' }
      ],
      colSpan: 24
    },
    {
      field: 'description',
      type: 'textarea',
      label: '项目描述',
      placeholder: '请输入项目描述',
      rules: [],
      colSpan: 24
    },
    {
      field: 'status',
      type: 'select',
      label: '项目状态',
      options: [
        { label: '未开始', value: 'not_started' },
        { label: '进行中', value: 'active' },
        { label: '暂停', value: 'paused' },
        { label: '已完成', value: 'completed' },
        { label: '已归档', value: 'archived' }
      ],
      colSpan: 12
    }
  ],

  API: [
    {
      field: 'base_url',
      type: 'input',
      label: '基础URL',
      placeholder: 'https://api.example.com',
      rules: [
        { required: true, message: '请输入基础URL' },
        { type: 'url', message: '请输入有效的URL地址' }
      ],
      colSpan: 24
    },
    {
      field: 'timeout',
      type: 'input-number',
      label: '超时时间(ms)',
      min: 1000,
      max: 300000,
      step: 1000,
      rules: [],
      colSpan: 12
    },
    {
      field: 'retry_count',
      type: 'input-number',
      label: '重试次数',
      min: 0,
      max: 10,
      rules: [],
      colSpan: 12
    }
  ],

  UI: [
    {
      field: 'base_url',
      type: 'input',
      label: '基础URL',
      placeholder: 'https://web.example.com',
      rules: [
        { required: true, message: '请输入基础URL' }
      ],
      colSpan: 24
    },
    {
      field: 'browser',
      type: 'select',
      label: '浏览器',
      options: [
        { label: 'Chrome', value: 'chrome' },
        { label: 'Firefox', value: 'firefox' },
        { label: 'Edge', value: 'edge' },
        { label: 'Safari', value: 'safari' }
      ],
      rules: [],
      colSpan: 12
    },
    {
      field: 'headless',
      type: 'switch',
      label: '无头模式',
      rules: [],
      colSpan: 12
    },
    {
      field: 'viewport_width',
      type: 'input-number',
      label: '视口宽度',
      min: 320,
      max: 3840,
      rules: [],
      colSpan: 12
    },
    {
      field: 'viewport_height',
      type: 'input-number',
      label: '视口高度',
      min: 320,
      max: 2160,
      rules: [],
      colSpan: 12
    }
  ],

  APP: [
    {
      field: 'platform',
      type: 'select',
      label: '平台',
      options: [
        { label: 'Android', value: 'android' },
        { label: 'iOS', value: 'ios' }
      ],
      rules: [{ required: true, message: '请选择平台' }],
      colSpan: 12
    },
    {
      field: 'device_id',
      type: 'input',
      label: '设备ID',
      placeholder: 'emulator-5554',
      rules: [],
      colSpan: 12
    },
    {
      field: 'app_package',
      type: 'input',
      label: 'APP包名',
      placeholder: 'com.example.app',
      rules: [
        { required: true, message: '请输入APP包名' }
      ],
      colSpan: 12
    },
    {
      field: 'app_activity',
      type: 'input',
      label: '启动Activity',
      placeholder: 'MainActivity',
      rules: [],
      colSpan: 12
    }
  ]
}

export function getFormConfig(projectType) {
  return {
    common: PROJECT_FORM_CONFIGS.common,
    module: PROJECT_FORM_CONFIGS[projectType] || []
  }
}

export function getModuleLabel(moduleType) {
  const labels = { API: 'API测试', UI: 'UI自动化', APP: 'APP自动化' }
  return labels[moduleType] || moduleType
}
