<template>
  <el-dialog
    v-model="dialogVisible"
    :title="isEdit ? '编辑项目' : '创建项目'"
    width="900px"
    :close-on-click-modal="false"
    @close="handleClose"
    class="project-dialog"
  >
    <div class="form-container">
      <el-form
        ref="formRef"
        :model="formData"
        :rules="formRules"
        label-width="110px"
        label-position="left"
        size="default"
      >
        <div class="form-section basic-info">
          <div class="section-header">
            <el-icon><Document /></el-icon>
            <span>基本信息</span>
          </div>

          <el-form-item label="项目名称" prop="name">
            <el-input
              v-model="formData.name"
              placeholder="请输入项目名称"
              clearable
              :prefix-icon="FolderOpened"
            />
          </el-form-item>

          <el-form-item label="项目描述" prop="description">
            <el-input
              v-model="formData.description"
              type="textarea"
              :rows="3"
              placeholder="请输入项目描述"
              clearable
            />
          </el-form-item>

          <el-form-item label="项目状态" prop="status">
            <el-select v-model="formData.status" style="width: 100%">
              <el-option label="未开始" value="not_started">
                <span class="status-option">
                  <span class="status-dot not-started"></span>
                  未开始
                </span>
              </el-option>
              <el-option label="进行中" value="active">
                <span class="status-option">
                  <span class="status-dot active"></span>
                  进行中
                </span>
              </el-option>
              <el-option label="暂停" value="paused">
                <span class="status-option">
                  <span class="status-dot paused"></span>
                  暂停
                </span>
              </el-option>
              <el-option label="已完成" value="completed">
                <span class="status-option">
                  <span class="status-dot completed"></span>
                  已完成
                </span>
              </el-option>
              <el-option label="已归档" value="archived">
                <span class="status-option">
                  <span class="status-dot archived"></span>
                  已归档
                </span>
              </el-option>
            </el-select>
          </el-form-item>
        </div>

        <div class="form-section module-selection">
          <div class="section-header">
            <el-icon><Connection /></el-icon>
            <span>项目类型</span>
            <span class="section-hint">可多选，创建后将自动在各模块中创建项目</span>
          </div>

          <el-form-item prop="types" label-width="0" style="margin-bottom: 0;">
            <div class="module-cards-wrapper">
              <div
                v-for="type in moduleTypes"
                :key="type.value"
                class="module-card"
                :class="{ selected: selectedTypes.includes(type.value) }"
                @click="toggleType(type.value)"
              >
                <div class="module-icon-wrap">
                  <div class="module-icon" :style="{ background: type.color }">
                    <el-icon :size="32"><component :is="type.icon" /></el-icon>
                  </div>
                </div>
                <div class="module-name">{{ type.label }}</div>
                <div class="module-check">
                  <el-check-tag
                    :checked="selectedTypes.includes(type.value)"
                  >
                    {{ selectedTypes.includes(type.value) ? '已选择' : '选择' }}
                  </el-check-tag>
                </div>
              </div>
            </div>
          </el-form-item>
        </div>

        <template v-if="selectedTypes.length > 0">
          <div class="form-section module-configs">
            <div class="section-header">
              <el-icon><Setting /></el-icon>
              <span>模块配置</span>
            </div>

            <div class="configs-wrapper">
              <el-collapse v-model="activeConfigs" accordion>
                <el-collapse-item
                  v-for="type in selectedTypes"
                  :key="type"
                  :name="type"
                  class="config-collapse-item"
                >
                  <template #title>
                    <div class="collapse-header">
                      <el-icon :size="20" :style="{ color: getModuleColor(type) }">
                        <component :is="getModuleIcon(type)" />
                      </el-icon>
                      <span class="collapse-title">{{ getModuleLabel(type) }}</span>
                    </div>
                  </template>

                  <div class="config-form">
                    <template v-if="type === 'AI'">
                      <el-form-item label="负责人" :prop="`module_configs.AI.owner`">
                        <el-select v-model="formData.module_configs.AI.owner" placeholder="请选择负责人" filterable style="width: 100%">
                          <el-option
                            v-for="user in users"
                            :key="user.id"
                            :label="user.username"
                            :value="user.id"
                          />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="团队成员" :prop="`module_configs.AI.member_ids`">
                        <el-select v-model="formData.module_configs.AI.member_ids" multiple placeholder="请选择团队成员" filterable style="width: 100%">
                          <el-option
                            v-for="user in users"
                            :key="user.id"
                            :label="user.username"
                            :value="user.id"
                          />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="开始日期" :prop="`module_configs.AI.start_date`">
                        <el-date-picker v-model="formData.module_configs.AI.start_date" type="date" placeholder="选择开始日期" value-format="YYYY-MM-DD" style="width: 100%" />
                      </el-form-item>
                      <el-form-item label="结束日期" :prop="`module_configs.AI.end_date`">
                        <el-date-picker v-model="formData.module_configs.AI.end_date" type="date" placeholder="选择结束日期" value-format="YYYY-MM-DD" style="width: 100%" />
                      </el-form-item>
                    </template>

                    <template v-else-if="type === 'AI_TEST'">
                      <el-form-item label="负责人" :prop="`module_configs.AI_TEST.owner`">
                        <el-select v-model="formData.module_configs.AI_TEST.owner" placeholder="请选择负责人" filterable style="width: 100%">
                          <el-option
                            v-for="user in users"
                            :key="user.id"
                            :label="user.username"
                            :value="user.id"
                          />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="团队成员" :prop="`module_configs.AI_TEST.member_ids`">
                        <el-select v-model="formData.module_configs.AI_TEST.member_ids" multiple placeholder="请选择团队成员" filterable style="width: 100%">
                          <el-option
                            v-for="user in users"
                            :key="user.id"
                            :label="user.username"
                            :value="user.id"
                          />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="开始日期" :prop="`module_configs.AI_TEST.start_date`">
                        <el-date-picker v-model="formData.module_configs.AI_TEST.start_date" type="date" placeholder="选择开始日期" value-format="YYYY-MM-DD" style="width: 100%" />
                      </el-form-item>
                      <el-form-item label="结束日期" :prop="`module_configs.AI_TEST.end_date`">
                        <el-date-picker v-model="formData.module_configs.AI_TEST.end_date" type="date" placeholder="选择结束日期" value-format="YYYY-MM-DD" style="width: 100%" />
                      </el-form-item>
                    </template>

                    <template v-else-if="type === 'API'">
                      <el-form-item label="项目类型" :prop="`module_configs.API.project_type`">
                        <el-radio-group v-model="formData.module_configs.API.project_type">
                          <el-radio value="HTTP">HTTP</el-radio>
                          <el-radio value="WEBSOCKET">WebSocket</el-radio>
                        </el-radio-group>
                      </el-form-item>
                      <el-form-item label="负责人" :prop="`module_configs.API.owner`">
                        <el-select v-model="formData.module_configs.API.owner" placeholder="请选择负责人" filterable style="width: 100%">
                          <el-option
                            v-for="user in users"
                            :key="user.id"
                            :label="user.username"
                            :value="user.id"
                          />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="团队成员" :prop="`module_configs.API.member_ids`">
                        <el-select v-model="formData.module_configs.API.member_ids" multiple placeholder="请选择团队成员" filterable style="width: 100%">
                          <el-option
                            v-for="user in users"
                            :key="user.id"
                            :label="user.username"
                            :value="user.id"
                          />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="开始日期" :prop="`module_configs.API.start_date`">
                        <el-date-picker v-model="formData.module_configs.API.start_date" type="date" placeholder="选择开始日期" value-format="YYYY-MM-DD" style="width: 100%" />
                      </el-form-item>
                      <el-form-item label="结束日期" :prop="`module_configs.API.end_date`">
                        <el-date-picker v-model="formData.module_configs.API.end_date" type="date" placeholder="选择结束日期" value-format="YYYY-MM-DD" style="width: 100%" />
                      </el-form-item>
                    </template>

                    <template v-else-if="type === 'UI'">
                      <el-form-item label="基础URL" :prop="`module_configs.UI.base_url`">
                        <el-input v-model="formData.module_configs.UI.base_url" placeholder="https://web.example.com" clearable />
                      </el-form-item>
                      <el-form-item label="浏览器" :prop="`module_configs.UI.browser`">
                        <el-select v-model="formData.module_configs.UI.browser" placeholder="请选择浏览器" style="width: 100%">
                          <el-option label="Chrome" value="chrome" />
                          <el-option label="Firefox" value="firefox" />
                          <el-option label="Edge" value="edge" />
                          <el-option label="Safari" value="safari" />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="无头模式" :prop="`module_configs.UI.headless`">
                        <el-switch v-model="formData.module_configs.UI.headless" />
                      </el-form-item>
                      <el-form-item label="视口宽度" :prop="`module_configs.UI.viewport_width`">
                        <el-input-number v-model="formData.module_configs.UI.viewport_width" :min="320" :max="3840" style="width: 100%" />
                      </el-form-item>
                      <el-form-item label="视口高度" :prop="`module_configs.UI.viewport_height`">
                        <el-input-number v-model="formData.module_configs.UI.viewport_height" :min="320" :max="2160" style="width: 100%" />
                      </el-form-item>
                      <el-form-item label="开始日期" :prop="`module_configs.UI.start_date`">
                        <el-date-picker v-model="formData.module_configs.UI.start_date" type="date" placeholder="选择开始日期" value-format="YYYY-MM-DD" style="width: 100%" />
                      </el-form-item>
                      <el-form-item label="结束日期" :prop="`module_configs.UI.end_date`">
                        <el-date-picker v-model="formData.module_configs.UI.end_date" type="date" placeholder="选择结束日期" value-format="YYYY-MM-DD" style="width: 100%" />
                      </el-form-item>
                    </template>

                    <template v-else-if="type === 'APP'">
                      <el-form-item label="平台" :prop="`module_configs.APP.platform`">
                        <el-select v-model="formData.module_configs.APP.platform" placeholder="请选择平台" style="width: 100%">
                          <el-option label="Android" value="android" />
                          <el-option label="iOS" value="ios" />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="设备ID" :prop="`module_configs.APP.device_id`">
                        <el-input v-model="formData.module_configs.APP.device_id" placeholder="emulator-5554" clearable />
                      </el-form-item>
                      <el-form-item label="APP包名" :prop="`module_configs.APP.app_package`">
                        <el-input v-model="formData.module_configs.APP.app_package" placeholder="com.example.app" clearable />
                      </el-form-item>
                      <el-form-item label="启动Activity" :prop="`module_configs.APP.app_activity`">
                        <el-input v-model="formData.module_configs.APP.app_activity" placeholder="MainActivity" clearable />
                      </el-form-item>
                      <el-form-item label="开始日期" :prop="`module_configs.APP.start_date`">
                        <el-date-picker v-model="formData.module_configs.APP.start_date" type="date" placeholder="选择开始日期" value-format="YYYY-MM-DD" style="width: 100%" />
                      </el-form-item>
                      <el-form-item label="结束日期" :prop="`module_configs.APP.end_date`">
                        <el-date-picker v-model="formData.module_configs.APP.end_date" type="date" placeholder="选择结束日期" value-format="YYYY-MM-DD" style="width: 100%" />
                      </el-form-item>
                    </template>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>
          </div>
        </template>
      </el-form>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">
          <el-icon v-if="!submitting"><Check /></el-icon>
          {{ isEdit ? '保存修改' : '创建项目' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { createMetaProject, updateMetaProject } from '@/api/unified-projects'
import { ElMessage } from 'element-plus'
import api from '@/utils/api'
import {
  Document,
  FolderOpened,
  Connection,
  Setting,
  Check,
  Link,
  Monitor,
  Iphone,
  Tickets,
  MagicStick
} from '@element-plus/icons-vue'

const { t } = useI18n()

const props = defineProps({
  visible: Boolean,
  isEdit: Boolean,
  projectData: Object,
  defaultType: {
    type: String,
    default: 'API'
  }
})

const emit = defineEmits(['update:visible', 'success'])

const moduleTypes = computed(() => [
  {
    value: 'AI',
    label: t('unifiedProject.moduleTypes.AI'),
    icon: Tickets,
    color: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
  },
  {
    value: 'AI_TEST',
    label: t('unifiedProject.moduleTypes.AI_TEST'),
    icon: MagicStick,
    color: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)'
  },
  {
    value: 'API',
    label: t('unifiedProject.moduleTypes.API'),
    icon: Tickets,
    color: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
  },
  {
    value: 'UI',
    label: t('unifiedProject.moduleTypes.UI'),
    icon: Monitor,
    color: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)'
  },
  {
    value: 'APP',
    label: t('unifiedProject.moduleTypes.APP'),
    icon: Iphone,
    color: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)'
  }
])

const moduleIcons = { AI: Link, AI_TEST: MagicStick, API: Tickets, UI: Monitor, APP: Iphone }
const moduleColors = {
  AI: '#667eea',
  AI_TEST: '#f5576c',
  API: '#667eea',
  UI: '#f5576c',
  APP: '#00f2fe'
}

const getModuleIcon = (type) => moduleIcons[type] || Link
const getModuleColor = (type) => moduleColors[type] || '#409EFF'
const getModuleLabel = (type) => {
  const keyMap = { AI: 'AI', AI_TEST: 'AI_TEST', API: 'API', UI: 'UI', APP: 'APP' }
  const key = keyMap[type]
  return key ? t(`unifiedProject.moduleTypes.${key}`) : type
}

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
})

const formRef = ref(null)
const submitting = ref(false)
const selectedTypes = ref([])
const activeConfigs = ref('')
const users = ref([])

const getDefaultModuleConfig = (type) => {
  if (type === 'AI' || type === 'AI_TEST') {
    return {
      owner: null,
      member_ids: [],
      start_date: null,
      end_date: null
    }
  } else if (type === 'API') {
    return {
      project_type: 'HTTP',
      owner: null,
      member_ids: [],
      start_date: null,
      end_date: null
    }
  } else if (type === 'UI') {
    return {
      base_url: '',
      browser: 'chrome',
      headless: false,
      viewport_width: 1920,
      viewport_height: 1080,
      start_date: null,
      end_date: null
    }
  } else if (type === 'APP') {
    return {
      platform: 'android',
      device_id: '',
      app_package: '',
      app_activity: '',
      start_date: null,
      end_date: null
    }
  }
  return {}
}

const formData = ref({
  name: '',
  description: '',
  status: 'not_started',
  module_configs: {
    AI: getDefaultModuleConfig('AI'),
    AI_TEST: getDefaultModuleConfig('AI_TEST'),
    API: getDefaultModuleConfig('API'),
    UI: getDefaultModuleConfig('UI'),
    APP: getDefaultModuleConfig('APP')
  }
})

const formRules = {
  name: [
    { required: true, message: '请输入项目名称', trigger: 'blur' },
    { min: 2, max: 200, message: '长度在 2 到 200 个字符', trigger: 'blur' }
  ]
}

const loadUsers = async () => {
  try {
    const response = await api.get('/api-testing/users/')
    users.value = response.data.results || response.data || []
  } catch (error) {
    console.error('加载用户列表失败:', error)
  }
}

watch(() => props.projectData, async (newVal) => {
  if (newVal && props.isEdit) {
    await loadUsers()

    formData.value = {
      name: newVal.name,
      description: newVal.description || '',
      status: newVal.status,
      module_configs: {
        AI: getDefaultModuleConfig('AI'),
        AI_TEST: getDefaultModuleConfig('AI_TEST'),
        API: getDefaultModuleConfig('API'),
        UI: getDefaultModuleConfig('UI'),
        APP: getDefaultModuleConfig('APP')
      }
    }

    if (newVal.modules && newVal.modules.length > 0) {
      selectedTypes.value = newVal.modules.map(m => m.module_type)
      activeConfigs.value = newVal.modules[0]?.module_type || ''

      newVal.modules.forEach(m => {
        if (formData.value.module_configs[m.module_type]) {
          const config = m.config || {}
          const moduleConfig = formData.value.module_configs[m.module_type]

          if (m.module_type === 'AI' || m.module_type === 'AI_TEST') {
            moduleConfig.owner = config.owner
            moduleConfig.member_ids = config.member_ids || []
            moduleConfig.start_date = config.start_date || null
            moduleConfig.end_date = config.end_date || null
          } else if (m.module_type === 'API') {
            moduleConfig.project_type = config.project_type || 'HTTP'
            moduleConfig.owner = config.owner
            moduleConfig.member_ids = config.member_ids || []
            moduleConfig.start_date = config.start_date || null
            moduleConfig.end_date = config.end_date || null
          } else if (m.module_type === 'UI') {
            moduleConfig.base_url = config.base_url || ''
            moduleConfig.browser = config.browser || 'chrome'
            moduleConfig.headless = config.headless || false
            moduleConfig.viewport_width = config.viewport_width || 1920
            moduleConfig.viewport_height = config.viewport_height || 1080
            moduleConfig.start_date = config.start_date || null
            moduleConfig.end_date = config.end_date || null
          } else if (m.module_type === 'APP') {
            moduleConfig.platform = config.platform || 'android'
            moduleConfig.device_id = config.device_id || ''
            moduleConfig.app_package = config.app_package || ''
            moduleConfig.app_activity = config.app_activity || ''
            moduleConfig.start_date = config.start_date || null
            moduleConfig.end_date = config.end_date || null
          }
        }
      })
    }
  }
}, { immediate: true })

watch(() => props.visible, async (newVal) => {
  if (newVal && props.isEdit && props.projectData) {
    await loadUsers()

    formData.value = {
      name: props.projectData.name,
      description: props.projectData.description || '',
      status: props.projectData.status,
      module_configs: {
        AI: getDefaultModuleConfig('AI'),
        AI_TEST: getDefaultModuleConfig('AI_TEST'),
        API: getDefaultModuleConfig('API'),
        UI: getDefaultModuleConfig('UI'),
        APP: getDefaultModuleConfig('APP')
      }
    }

    selectedTypes.value = props.projectData.modules?.map(m => m.module_type) || []
    if (selectedTypes.value.length > 0) {
      activeConfigs.value = selectedTypes.value[0]
    } else {
      activeConfigs.value = ''
    }

    if (props.projectData.modules && props.projectData.modules.length > 0) {
      props.projectData.modules.forEach(m => {
        if (formData.value.module_configs[m.module_type]) {
          const config = m.config || {}
          const moduleConfig = formData.value.module_configs[m.module_type]

          if (m.module_type === 'AI' || m.module_type === 'AI_TEST') {
            moduleConfig.owner = config.owner
            moduleConfig.member_ids = config.member_ids || []
            moduleConfig.start_date = config.start_date || null
            moduleConfig.end_date = config.end_date || null
          } else if (m.module_type === 'API') {
            moduleConfig.project_type = config.project_type || 'HTTP'
            moduleConfig.owner = config.owner
            moduleConfig.member_ids = config.member_ids || []
            moduleConfig.start_date = config.start_date || null
            moduleConfig.end_date = config.end_date || null
          } else if (m.module_type === 'UI') {
            moduleConfig.base_url = config.base_url || ''
            moduleConfig.browser = config.browser || 'chrome'
            moduleConfig.headless = config.headless || false
            moduleConfig.viewport_width = config.viewport_width || 1920
            moduleConfig.viewport_height = config.viewport_height || 1080
            moduleConfig.start_date = config.start_date || null
            moduleConfig.end_date = config.end_date || null
          } else if (m.module_type === 'APP') {
            moduleConfig.platform = config.platform || 'android'
            moduleConfig.device_id = config.device_id || ''
            moduleConfig.app_package = config.app_package || ''
            moduleConfig.app_activity = config.app_activity || ''
            moduleConfig.start_date = config.start_date || null
            moduleConfig.end_date = config.end_date || null
          }
        }
      })
    }
  } else if (!newVal) {
    selectedTypes.value = []
    activeConfigs.value = ''
  }
})

const toggleType = (type) => {
  const index = selectedTypes.value.indexOf(type)
  if (index === -1) {
    selectedTypes.value.push(type)
    activeConfigs.value = type
  } else {
    selectedTypes.value.splice(index, 1)
    if (activeConfigs.value === type) {
      activeConfigs.value = selectedTypes.value[0] || ''
    }
  }
  handleTypesChange()
}

const handleTypesChange = () => {
  Object.keys(formData.value.module_configs).forEach(type => {
    if (!selectedTypes.value.includes(type)) {
      formData.value.module_configs[type] = getDefaultModuleConfig(type)
    }
  })
  if (selectedTypes.value.length > 0 && !activeConfigs.value) {
    activeConfigs.value = selectedTypes.value[0]
  }
}

const handleSubmit = async () => {
  if (!formData.value.name) {
    ElMessage.error('请输入项目名称')
    return
  }

  try {
    submitting.value = true

    const formatDate = (date) => {
      if (!date) return null
      if (typeof date === 'string') return date
      const d = new Date(date)
      return d.toISOString().split('T')[0]
    }

    const modules = selectedTypes.value.map(type => {
      const config = { ...formData.value.module_configs[type] }
      if (config.start_date) config.start_date = formatDate(config.start_date)
      if (config.end_date) config.end_date = formatDate(config.end_date)
      return {
        module_type: type,
        config
      }
    })

    const data = {
      name: formData.value.name,
      description: formData.value.description,
      status: formData.value.status,
      modules
    }

    if (props.isEdit) {
      await updateMetaProject(props.projectData.id, data)
      ElMessage.success('项目更新成功')
    } else {
      await createMetaProject(data)
      ElMessage.success('项目创建成功')
    }

    emit('success')
    dialogVisible.value = false
  } catch (error) {
    console.error('提交失败:', error)
    ElMessage.error(props.isEdit ? '更新失败' : '创建失败')
  } finally {
    submitting.value = false
  }
}

const handleClose = () => {
  formData.value = {
    name: '',
    description: '',
    status: 'not_started',
    module_configs: {
      AI: getDefaultModuleConfig('AI'),
      AI_TEST: getDefaultModuleConfig('AI_TEST'),
      API: getDefaultModuleConfig('API'),
      UI: getDefaultModuleConfig('UI'),
      APP: getDefaultModuleConfig('APP')
    }
  }
  selectedTypes.value = []
  activeConfigs.value = ''
  emit('update:visible', false)
}

onMounted(() => {
  loadUsers()
})
</script>

<style scoped>
.form-container {
  padding: 0 8px;
}

.form-section {
  margin-bottom: 24px;
  padding: 20px;
  background: #fafbfc;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e8e8e8;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.section-header .el-icon {
  color: #409eff;
}

.section-hint {
  font-size: 12px;
  font-weight: 400;
  color: #909399;
  margin-left: 8px;
}

.basic-info {
  background: linear-gradient(135deg, #fefefe 0%, #f5f7fa 100%);
}

.module-selection {
  background: linear-gradient(135deg, #f0f9ff 0%, #e8f4fd 100%);
  text-align: center;
}

.module-cards-wrapper {
  display: flex;
  gap: 16px;
  justify-content: space-between;
  flex-wrap: wrap;
  width: 100%;
}

.module-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 16px 12px;
  background: #ffffff;
  border: 2px solid #ebeef5;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  min-height: 110px;
  max-width: 300px;
}

.module-card:hover {
  border-color: #c0c4cc;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.module-card.selected {
  border-color: #409eff;
  background: linear-gradient(180deg, #ecf5ff 0%, #f0f9ff 100%);
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.15);
}

.module-icon-wrap {
  position: relative;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.module-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  color: #ffffff;
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.12);
  transition: transform 0.3s ease;
}

.module-card:hover .module-icon {
  transform: scale(1.05);
}

.module-card.selected .module-icon {
  box-shadow: 0 4px 10px rgba(64, 158, 255, 0.25);
}

.module-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  text-align: center;
}

.module-check {
  margin-top: 4px;
}

.module-configs {
  background: linear-gradient(135deg, #fff9f0 0%, #fff5e6 100%);
}

.configs-wrapper {
  margin-top: 8px;
}

.config-form {
  padding: 16px 8px;
}

.config-collapse-item {
  margin-bottom: 8px;
  border-radius: 8px;
  overflow: hidden;
}

.config-collapse-item :deep(.el-collapse-item__header) {
  background: #ffffff;
  border-radius: 8px;
  padding: 12px 16px;
  height: auto;
  line-height: 1.5;
}

.config-collapse-item :deep(.el-collapse-item__wrap) {
  border: none;
  background: #fafafa;
}

.config-collapse-item :deep(.el-collapse-item__content) {
  padding: 0;
}

.collapse-header {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.collapse-title {
  font-weight: 600;
  color: #303133;
}

.status-option {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot.not-started {
  background: #909399;
}

.status-dot.active {
  background: #67c23a;
}

.status-dot.paused {
  background: #e6a23c;
}

.status-dot.completed {
  background: #409eff;
}

.status-dot.archived {
  background: #c0c4cc;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

:deep(.el-dialog__header) {
  padding: 20px 24px 16px;
  border-bottom: 1px solid #f0f0f0;
}

:deep(.el-dialog__title) {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

:deep(.el-dialog__body) {
  padding: 24px;
}

:deep(.el-form-item__label) {
  font-weight: 500;
  color: #606266;
}

:deep(.el-check-tag) {
  padding: 6px 14px;
  border-radius: 16px;
  font-size: 13px;
  border: 1px solid #dcdfe6;
  transition: all 0.2s;
}

:deep(.el-check-tag:hover) {
  border-color: #409eff;
}

:deep(.el-check-tag.is-checked) {
  background-color: #409eff;
  border-color: #409eff;
  color: #ffffff;
}
</style>
