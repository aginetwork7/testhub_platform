<template>
  <div class="notification-config-container">
    <div class="left-panel">
      <div class="panel-header">
        <h3>{{ $t('uiAutomation.notification.configs.title') }}</h3>
        <el-button type="primary" size="small" @click="handleAdd">
          <el-icon><Plus /></el-icon>
          {{ $t('common.add') }}
        </el-button>
      </div>
      
      <div class="filter-section">
        <el-select v-model="filterType" :placeholder="$t('uiAutomation.notification.configs.selectPlatform')" clearable style="width: 100%">
          <el-option
            v-for="item in configTypeOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </div>
      
      <div class="bot-list">
        <div
          v-for="bot in filteredBots"
          :key="bot.id"
          class="bot-item"
          :class="{ active: selectedBotId === bot.id, 'is-new': bot._isNew }"
          @click="selectBot(bot)"
        >
          <div class="bot-icon" :style="{ background: getBotColor(bot.config_type) }">
            <el-icon :size="24" color="#fff">
              <component :is="getBotIcon(bot.config_type)" />
            </el-icon>
          </div>
          <div class="bot-info">
            <div class="bot-name">{{ bot.name || $t('uiAutomation.notification.configs.newBot') }}</div>
            <div class="bot-type">{{ getConfigTypeLabel(bot.config_type) }}</div>
          </div>
          <div class="bot-status" v-if="!bot._isNew">
            <el-tag :type="bot.is_active ? 'success' : 'info'" size="small">
              {{ bot.is_active ? $t('common.enabled') : $t('common.disabled') }}
            </el-tag>
          </div>
        </div>
        
        <el-empty v-if="filteredBots.length === 0" :description="$t('common.noData')" />
      </div>
    </div>
    
    <div class="right-panel">
      <template v-if="showForm">
        <div class="panel-header">
          <h3>{{ isNewBot ? $t('uiAutomation.notification.configs.addNewBot') : (formData.name || $t('uiAutomation.notification.configs.editBot')) }}</h3>
          <div class="header-actions">
            <el-button v-if="!isNewBot" type="success" @click="handleTestSend" :loading="testing">
              {{ $t('uiAutomation.notification.configs.testSend') }}
            </el-button>
            <el-button type="primary" @click="handleSave" :loading="saving">
              {{ $t('common.save') }}
            </el-button>
            <el-button v-if="!isNewBot" type="danger" @click="handleDelete">
              {{ $t('common.delete') }}
            </el-button>
            <el-button v-else @click="handleCancel">
              {{ $t('common.cancel') }}
            </el-button>
          </div>
        </div>
        
        <el-form
          ref="formRef"
          :model="formData"
          :rules="formRules"
          label-position="top"
          class="config-form"
        >
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item 
                :label="formData.config_type === 'email' ? $t('uiAutomation.notification.configs.emailName') : $t('uiAutomation.notification.configs.botName')" 
                prop="name"
              >
                <el-input v-model="formData.name" :placeholder="$t('common.pleaseInput')" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="$t('uiAutomation.notification.configs.platform')" prop="config_type">
                <el-select v-model="formData.config_type" style="width: 100%" :disabled="!isNewBot">
                  <el-option
                    v-for="item in configTypeOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
                <div class="form-item-hint" v-if="!isNewBot">
                  {{ $t('uiAutomation.notification.configs.platformNotEditable') }}
                </div>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="$t('uiAutomation.notification.configs.status')">
                <el-switch v-model="formData.is_active" :active-text="$t('common.enabled')" :inactive-text="$t('common.disabled')" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item :label="$t('uiAutomation.notification.configs.isDefault')">
                <el-switch v-model="formData.is_default" />
              </el-form-item>
            </el-col>
            <el-col :span="24">
              <el-form-item :label="$t('uiAutomation.notification.configs.webhookUrl')" prop="webhook_url" v-if="showWebhookUrl">
                <el-input v-model="formData.webhook_url" :placeholder="$t('uiAutomation.notification.configs.webhookPlaceholder')" />
              </el-form-item>
            </el-col>
            
            <el-col :span="24" v-if="formData.config_type === 'webhook_dingtalk'">
              <el-form-item :label="$t('uiAutomation.notification.configs.signatureSecret')">
                <el-input v-model="formData.secret" :placeholder="$t('uiAutomation.notification.configs.signatureSecretPlaceholder')" />
                <div class="form-item-hint">
                  {{ $t('uiAutomation.notification.configs.signatureSecretHint') }}
                </div>
              </el-form-item>
            </el-col>
            
            <el-col :span="24" v-if="formData.config_type === 'email'">
              <el-form-item :label="$t('uiAutomation.notification.configs.emailRecipients')">
                <div class="email-recipients-container">
                  <div class="recipients-list" v-if="emailRecipientsList.length > 0">
                    <el-tag
                      v-for="(recipient, index) in emailRecipientsList"
                      :key="index"
                      closable
                      @close="removeEmailRecipient(index)"
                      :type="recipient.type === 'user' ? 'primary' : 'success'"
                      class="recipient-tag"
                    >
                      <span class="recipient-content">
                        <el-icon class="recipient-icon"><User v-if="recipient.type === 'user'" /><Message v-else /></el-icon>
                        <span class="recipient-text">{{ recipient.display || recipient.email }}</span>
                      </span>
                    </el-tag>
                  </div>
                  <div class="add-recipient-row">
                    <el-select
                      v-model="newRecipientType"
                      style="width: 120px"
                      :placeholder="$t('uiAutomation.notification.configs.recipientType')"
                    >
                      <el-option value="user" :label="$t('uiAutomation.notification.configs.platformUser')" />
                      <el-option value="email" :label="$t('uiAutomation.notification.configs.customEmail')" />
                    </el-select>
                    <el-select
                      v-if="newRecipientType === 'user'"
                      v-model="selectedUserId"
                      filterable
                      :placeholder="$t('uiAutomation.notification.configs.selectUser')"
                      style="flex: 1"
                    >
                      <el-option
                        v-for="user in platformUsers"
                        :key="user.id"
                        :label="user.username + (user.email ? ` (${user.email})` : '')"
                        :value="user.id"
                      />
                    </el-select>
                    <el-input
                      v-else
                      v-model="newEmailAddress"
                      :placeholder="$t('uiAutomation.notification.configs.emailPlaceholder')"
                      style="flex: 1"
                    />
                    <el-button type="primary" @click="addEmailRecipient">
                      {{ $t('common.add') }}
                    </el-button>
                  </div>
                </div>
              </el-form-item>
            </el-col>
            
            <el-col :span="24" v-if="formData.config_type === 'email'">
              <el-form-item :label="$t('uiAutomation.notification.configs.emailAttachReport')">
                <el-switch
                  v-model="formData.email_attach_report"
                  :active-text="$t('common.yes')"
                  :inactive-text="$t('common.no')"
                />
                <div class="form-item-hint">
                  {{ $t('uiAutomation.notification.configs.emailAttachReportHint') }}
                </div>
              </el-form-item>
            </el-col>
            
            <el-col :span="24">
              <el-form-item :label="$t('uiAutomation.notification.configs.messageTemplate')" prop="notification_template">
                <el-select
                  v-model="formData.notification_template"
                  :placeholder="$t('uiAutomation.notification.configs.selectTemplate')"
                  filterable
                  style="width: 100%"
                >
                  <el-option
                    v-for="template in notificationTemplates"
                    :key="template.id"
                    :label="template.name"
                    :value="template.id"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            
            <el-col :span="24">
              <el-form-item :label="$t('uiAutomation.notification.configs.businessType')">
                <el-checkbox-group v-model="businessTypes">
                  <el-checkbox value="ui_automation">{{ $t('uiAutomation.notification.configs.uiAutomationTest') }}</el-checkbox>
                  <el-checkbox value="api_testing">{{ $t('uiAutomation.notification.configs.apiTest') }}</el-checkbox>
                  <el-checkbox value="app_automation">{{ $t('uiAutomation.notification.configs.appAutomationTest') }}</el-checkbox>
                </el-checkbox-group>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </template>
      
      <template v-else>
        <div class="empty-state">
          <el-empty :description="$t('uiAutomation.notification.configs.emptyHint')">
            <el-button type="primary" @click="handleAdd">
              <el-icon><Plus /></el-icon>
              {{ $t('uiAutomation.notification.configs.addNewBot') }}
            </el-button>
          </el-empty>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, ChatDotRound, Message, PhoneFilled, Link, User } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import {
  getUnifiedNotificationConfigs,
  createUnifiedNotificationConfig,
  updateUnifiedNotificationConfig,
  deleteUnifiedNotificationConfig,
  getNotificationTemplates,
  testSendNotification
} from '@/api/core'
import { getUiUsers } from '@/api/ui_automation'

const { t } = useI18n()

const formRef = ref(null)
const botList = ref([])
const notificationTemplates = ref([])
const selectedBotId = ref(null)
const filterType = ref('')
const saving = ref(false)
const testing = ref(false)

const platformUsers = ref([])
const emailRecipientsList = ref([])
const newRecipientType = ref('email')
const selectedUserId = ref(null)
const newEmailAddress = ref('')

const configTypeOptions = [
  { value: 'webhook_feishu', label: t('uiAutomation.notification.configs.feishuBot') },
  { value: 'webhook_wechat', label: t('uiAutomation.notification.configs.wechatBot') },
  { value: 'webhook_dingtalk', label: t('uiAutomation.notification.configs.dingtalkBot') },
  { value: 'webhook_generic', label: t('uiAutomation.notification.configs.genericWebhook') },
  { value: 'email', label: t('uiAutomation.notification.configs.emailNotification') },
]

const showWebhookUrl = computed(() => {
  return ['webhook_feishu', 'webhook_wechat', 'webhook_dingtalk', 'webhook_generic'].includes(formData.config_type)
})

const defaultFormData = {
  name: '',
  config_type: 'webhook_feishu',
  webhook_url: '',
  secret: '',
  email_recipients: [],
  email_attach_report: false,
  notification_template: null,
  enable_ui_automation: true,
  enable_api_testing: true,
  enable_app_automation: true,
  is_active: true,
  is_default: false
}

const formData = reactive({ ...defaultFormData })

const businessTypes = computed({
  get: () => {
    const types = []
    if (formData.enable_ui_automation) types.push('ui_automation')
    if (formData.enable_api_testing) types.push('api_testing')
    if (formData.enable_app_automation) types.push('app_automation')
    return types
  },
  set: (val) => {
    formData.enable_ui_automation = val.includes('ui_automation')
    formData.enable_api_testing = val.includes('api_testing')
    formData.enable_app_automation = val.includes('app_automation')
  }
})

const formRules = computed(() => {
  return {
    name: [{ required: true, message: t('common.required'), trigger: 'blur' }],
    config_type: [{ required: true, message: t('common.required'), trigger: 'change' }],
    webhook_url: [{ required: true, message: t('common.required'), trigger: 'blur' }],
    notification_template: [{ required: true, message: t('common.required'), trigger: 'change' }]
  }
})

const filteredBots = computed(() => {
  if (!filterType.value) return botList.value
  return botList.value.filter(bot => bot.config_type === filterType.value)
})

const isNewBot = computed(() => {
  return selectedBotId.value === 'new'
})

const showForm = computed(() => {
  return selectedBotId.value !== null
})

const selectedBot = computed(() => {
  if (isNewBot.value) return null
  return botList.value.find(bot => bot.id === selectedBotId.value)
})

const getConfigTypeLabel = (configType) => {
  const option = configTypeOptions.find(opt => opt.value === configType)
  return option ? option.label : configType
}

const getBotIcon = (configType) => {
  const iconMap = {
    'webhook_feishu': ChatDotRound,
    'webhook_wechat': Message,
    'webhook_dingtalk': PhoneFilled,
    'webhook_generic': Link,
    'email': Message
  }
  return iconMap[configType] || Link
}

const getBotColor = (configType) => {
  const colorMap = {
    'webhook_feishu': '#3370ff',
    'webhook_wechat': '#07c160',
    'webhook_dingtalk': '#0089ff',
    'webhook_generic': '#909399',
    'email': '#e6a23c'
  }
  return colorMap[configType] || '#909399'
}

const fetchBotList = async () => {
  try {
    const response = await getUnifiedNotificationConfigs()
    if (response.data.results) {
      botList.value = response.data.results
    } else if (Array.isArray(response.data)) {
      botList.value = response.data
    }
  } catch (error) {
    console.error('获取机器人列表失败:', error)
    ElMessage.error(t('common.fetchFailed'))
  }
}

const fetchTemplates = async () => {
  try {
    const response = await getNotificationTemplates()
    if (response.data.results) {
      notificationTemplates.value = response.data.results
    } else if (Array.isArray(response.data)) {
      notificationTemplates.value = response.data
    }
  } catch (error) {
    console.error('获取模板列表失败:', error)
  }
}

const selectBot = (bot) => {
  if (bot._isNew) return
  
  selectedBotId.value = bot.id
  Object.assign(formData, {
    name: bot.name,
    config_type: bot.config_type,
    webhook_url: bot.webhook_url,
    secret: bot.secret || '',
    email_recipients: bot.email_recipients || [],
    email_attach_report: bot.email_attach_report || false,
    notification_template: bot.notification_template,
    enable_ui_automation: bot.enable_ui_automation,
    enable_api_testing: bot.enable_api_testing,
    enable_app_automation: bot.enable_app_automation,
    is_active: bot.is_active,
    is_default: bot.is_default
  })
  
  emailRecipientsList.value = parseEmailRecipients(bot.email_recipients || [])
}

const handleAdd = () => {
  selectedBotId.value = 'new'
  Object.assign(formData, {
    ...defaultFormData,
    config_type: filterType.value || 'webhook_feishu'
  })
  emailRecipientsList.value = []
}

const handleCancel = () => {
  selectedBotId.value = null
  Object.assign(formData, defaultFormData)
  emailRecipientsList.value = []
}

const parseEmailRecipients = (recipients) => {
  const result = []
  for (const item of recipients) {
    if (typeof item === 'string' && item.includes('@')) {
      result.push({
        type: 'email',
        email: item,
        display: item
      })
    } else if (typeof item === 'object') {
      if (item.type === 'user') {
        const user = platformUsers.value.find(u => u.id === item.id)
        result.push({
          type: 'user',
          id: item.id,
          display: user ? `${user.username} (${user.email})` : `用户ID: ${item.id}`
        })
      } else if (item.type === 'email') {
        result.push({
          type: 'email',
          email: item.email,
          display: item.email
        })
      }
    }
  }
  return result
}

const addEmailRecipient = () => {
  if (newRecipientType.value === 'user') {
    if (!selectedUserId.value) {
      ElMessage.warning(t('uiAutomation.notification.configs.selectUser'))
      return
    }
    const user = platformUsers.value.find(u => u.id === selectedUserId.value)
    if (!user) return
    
    const exists = emailRecipientsList.value.some(r => r.type === 'user' && r.id === user.id)
    if (exists) {
      ElMessage.warning(t('uiAutomation.notification.configs.recipientExists'))
      return
    }
    
    emailRecipientsList.value.push({
      type: 'user',
      id: user.id,
      display: `${user.username} (${user.email})`
    })
    selectedUserId.value = null
  } else {
    if (!newEmailAddress.value) {
      ElMessage.warning(t('uiAutomation.notification.configs.emailRequired'))
      return
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(newEmailAddress.value)) {
      ElMessage.warning(t('uiAutomation.notification.configs.emailInvalid'))
      return
    }
    
    const exists = emailRecipientsList.value.some(r => r.email === newEmailAddress.value)
    if (exists) {
      ElMessage.warning(t('uiAutomation.notification.configs.recipientExists'))
      return
    }
    
    emailRecipientsList.value.push({
      type: 'email',
      email: newEmailAddress.value,
      display: newEmailAddress.value
    })
    newEmailAddress.value = ''
  }
}

const removeEmailRecipient = (index) => {
  emailRecipientsList.value.splice(index, 1)
}

const fetchUsers = async () => {
  try {
    const response = await getUiUsers()
    if (response.data.results) {
      platformUsers.value = response.data.results
    } else if (Array.isArray(response.data)) {
      platformUsers.value = response.data
    }
  } catch (error) {
    console.error('获取用户列表失败:', error)
  }
}

const handleSave = async () => {
  if (!formRef.value) return
  
  try {
    await formRef.value.validate()
  } catch (validateError) {
    console.error('表单验证失败:', validateError)
    ElMessage.error(t('common.saveFailed') + ': 请检查表单必填项')
    return
  }
  
  try {
    saving.value = true
    
    const data = { ...formData }
    
    data.email_recipients = emailRecipientsList.value.map(r => {
      if (r.type === 'user') {
        return { type: 'user', id: r.id }
      } else {
        return { type: 'email', email: r.email }
      }
    })
    
    console.log('Saving data:', JSON.stringify(data, null, 2))
    
    if (isNewBot.value) {
      const response = await createUnifiedNotificationConfig(data)
      console.log('Create response:', response)
      selectedBotId.value = response.data.id
      ElMessage.success(t('common.createSuccess'))
    } else {
      const response = await updateUnifiedNotificationConfig(selectedBotId.value, data)
      console.log('Update response:', response)
      ElMessage.success(t('common.updateSuccess'))
    }
    
    await fetchBotList()
  } catch (error) {
    console.error('保存失败 - 完整错误:', error)
    console.error('错误响应:', error.response)
    let errorMsg = t('common.saveFailed')
    if (error.response) {
      const respData = error.response.data
      console.error('响应数据:', respData)
      if (respData.detail) {
        errorMsg += ': ' + respData.detail
      } else if (respData.message) {
        errorMsg += ': ' + respData.message
      } else if (typeof respData === 'object') {
        const errors = []
        for (const key in respData) {
          if (Array.isArray(respData[key])) {
            errors.push(`${key}: ${respData[key].join(', ')}`)
          } else {
            errors.push(`${key}: ${respData[key]}`)
          }
        }
        if (errors.length > 0) {
          errorMsg += ': ' + errors.join('; ')
        }
      }
    } else if (error.message) {
      errorMsg += ': ' + error.message
    }
    ElMessage.error(errorMsg)
  } finally {
    saving.value = false
  }
}

const handleTestSend = async () => {
  if (!selectedBotId.value || isNewBot.value) return
  
  try {
    testing.value = true
    const response = await testSendNotification(selectedBotId.value)
    
    if (response.data.success) {
      ElMessage.success(response.data.message || t('uiAutomation.notification.configs.testSendSuccess'))
    } else {
      ElMessage.error(response.data.message || t('uiAutomation.notification.configs.testSendFailed'))
    }
  } catch (error) {
    console.error('测试发送失败:', error)
    const errorMsg = error.response?.data?.message || error.message || t('uiAutomation.notification.configs.testSendFailed')
    ElMessage.error(errorMsg)
  } finally {
    testing.value = false
  }
}

const handleDelete = async () => {
  if (!selectedBotId.value || isNewBot.value) return
  
  try {
    await ElMessageBox.confirm(t('common.deleteConfirm'), t('common.warning'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning'
    })
    
    await deleteUnifiedNotificationConfig(selectedBotId.value)
    ElMessage.success(t('common.deleteSuccess'))
    selectedBotId.value = null
    await fetchBotList()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
      ElMessage.error(t('common.deleteFailed'))
    }
  }
}

onMounted(() => {
  fetchBotList()
  fetchTemplates()
  fetchUsers()
})
</script>

<style scoped>
.notification-config-container {
  display: flex;
  height: calc(100vh - 120px);
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.left-panel {
  width: 320px;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
}

.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.filter-section {
  padding: 12px 16px;
  border-bottom: 1px solid #e4e7ed;
}

.bot-list {
  flex: 1;
  overflow-y: auto;
}

.bot-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
  transition: background-color 0.2s;
}

.bot-item:hover {
  background-color: #f5f7fa;
}

.bot-item.active {
  background-color: #ecf5ff;
  border-left: 3px solid #409eff;
}

.bot-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 12px;
  flex-shrink: 0;
}

.bot-info {
  flex: 1;
  overflow: hidden;
}

.bot-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bot-type {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.bot-status {
  margin-left: 8px;
  flex-shrink: 0;
}

.config-form {
  padding: 20px;
  flex: 1;
  overflow-y: auto;
}

.form-item-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  margin-left: 12px;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.email-recipients-container {
  width: 100%;
}

.recipients-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  min-height: 32px;
}

.recipient-tag {
  display: inline-flex;
  align-items: center;
}

.recipient-content {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.recipient-icon {
  flex-shrink: 0;
}

.recipient-text {
  white-space: nowrap;
}

.add-recipient-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
