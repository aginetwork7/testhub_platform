<template>
  <div class="ai-mode-prompt-config">
    <div class="page-header">
      <h1>{{ $t('configuration.aiModePrompt.title') }}</h1>
      <p>{{ $t('configuration.aiModePrompt.description') }}</p>
    </div>

    <div class="main-content">
      <div class="configs-section">
        <div class="section-header">
          <h2>{{ $t('configuration.aiModePrompt.configList') }}</h2>
          <div class="header-actions">
            <button class="load-defaults-btn" @click="loadDefaultPrompts">
              {{ $t('configuration.aiModePrompt.loadDefaults') }}
            </button>
            <button class="add-config-btn" @click="openAddModal">
              {{ $t('configuration.aiModePrompt.addConfig') }}
            </button>
          </div>
        </div>

        <div class="configs-grid">
          <div v-for="config in configs" :key="config.id" class="config-card">
            <div class="config-header">
              <div class="config-title">
                <h3>{{ config.name }}</h3>
                <div class="config-badges">
                  <span class="type-badge" :class="config.prompt_type">
                    {{ getTypeLabel(config.prompt_type) }}
                  </span>
                  <span class="status-badge" :class="{ active: config.is_active }">
                    {{ config.is_active ? $t('configuration.common.enabled') : $t('configuration.common.disabled') }}
                  </span>
                </div>
              </div>
              <div class="config-actions">
                <button class="preview-btn" @click="previewPrompt(config)">{{ $t('configuration.aiModePrompt.preview') }}</button>
                <button class="edit-btn" @click="editConfig(config)">{{ $t('configuration.common.edit') }}</button>
                <button class="delete-btn" @click="deleteConfig(config.id)">{{ $t('configuration.common.delete') }}</button>
              </div>
            </div>

            <div class="config-details">
              <div class="prompt-preview">
                <label>{{ $t('configuration.aiModePrompt.contentPreview') }}</label>
                <div class="content-preview">{{ truncateContent(config.content, 200) }}</div>
              </div>
              <div class="config-meta">
                <div class="meta-item">
                  <label>{{ $t('configuration.common.createdAt') }}</label>
                  <span>{{ formatDateTime(config.created_at) }}</span>
                </div>
                <div class="meta-item">
                  <label>{{ $t('configuration.common.updatedAt') }}</label>
                  <span>{{ formatDateTime(config.updated_at) }}</span>
                </div>
                <div class="meta-item">
                  <label>{{ $t('configuration.aiModePrompt.createdBy') }}</label>
                  <span>{{ config.created_by_name || '-' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="configs.length === 0" class="empty-state">
          <div class="empty-icon">📝</div>
          <h3>{{ $t('configuration.aiModePrompt.emptyTitle') }}</h3>
          <p>{{ $t('configuration.aiModePrompt.emptyDescription') }}</p>
          <div class="empty-actions">
            <button class="add-first-config-btn" @click="openAddModal">
              {{ $t('configuration.aiModePrompt.addConfig') }}
            </button>
            <button class="load-defaults-first-btn" @click="loadDefaultPrompts">
              {{ $t('configuration.aiModePrompt.loadDefaults') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 添加/编辑弹窗 -->
    <div v-if="showAddModal || showEditModal" class="config-modal">
      <div class="modal-content large" @click.stop>
        <div class="modal-header">
          <h3>{{ isEditing ? $t('configuration.aiModePrompt.editConfig') : $t('configuration.aiModePrompt.addConfig') }}</h3>
          <button class="close-btn" @click="closeModals">×</button>
        </div>
        <div class="modal-body">
          <form @submit.prevent="saveConfig">
            <div class="form-group">
              <label>{{ $t('configuration.aiModePrompt.configName') }} <span class="required">*</span></label>
              <input v-model="configForm.name" type="text" class="form-input"
                :placeholder="$t('configuration.aiModePrompt.configNamePlaceholder')" required>
            </div>

            <div class="form-group">
              <label>{{ $t('configuration.aiModePrompt.promptType') }} <span class="required">*</span></label>
              <select v-model="configForm.prompt_type" class="form-select" required :disabled="isEditing">
                <option value="">{{ $t('configuration.aiModePrompt.selectPromptType') }}</option>
                <option value="planner_text">Planner - {{ $t('configuration.aiModePrompt.textPrompt') }}</option>
                <option value="planner_vision">Planner - {{ $t('configuration.aiModePrompt.visionPrompt') }}</option>
                <option value="executor_text">Executor - {{ $t('configuration.aiModePrompt.textPrompt') }}</option>
                <option value="executor_vision">Executor - {{ $t('configuration.aiModePrompt.visionPrompt') }}</option>
                <option value="hermes_agent">{{ $t('configuration.aiModePrompt.hermesPrompt') }}</option>
              </select>
            </div>

            <div class="form-group">
              <label>{{ $t('configuration.aiModePrompt.promptContent') }} <span class="required">*</span></label>
              <div class="textarea-container">
                <textarea v-model="configForm.content" class="form-textarea large" rows="20"
                  :placeholder="$t('configuration.aiModePrompt.contentPlaceholder')" required></textarea>
                <div class="char-count">{{ configForm.content.length }} {{ $t('configuration.aiModePrompt.chars') }}</div>
              </div>
            </div>

            <div class="form-group">
              <label class="checkbox-label">
                <input v-model="configForm.is_active" type="checkbox">
                {{ $t('configuration.aiModePrompt.enableConfig') }}
              </label>
              <div class="checkbox-hint">{{ $t('configuration.aiModePrompt.enableHint') }}</div>
            </div>

            <div class="modal-actions">
              <button type="button" class="cancel-btn" @click="closeModals">{{ $t('configuration.common.cancel') }}</button>
              <button type="submit" class="confirm-btn" :disabled="isSaving">
                {{ isSaving ? $t('configuration.aiModePrompt.saving') : $t('configuration.common.save') }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <!-- 预览弹窗 -->
    <div v-if="showPreviewModal" class="preview-modal" @click="closePreview">
      <div class="modal-content large" @click.stop>
        <div class="modal-header">
          <h3>{{ previewConfig.name }}</h3>
          <button class="close-btn" @click="closePreview">×</button>
        </div>
        <div class="modal-body">
          <div class="preview-meta">
            <span class="type-badge" :class="previewConfig.prompt_type">{{ getTypeLabel(previewConfig.prompt_type) }}</span>
            <span class="status-badge" :class="{ active: previewConfig.is_active }">
              {{ previewConfig.is_active ? $t('configuration.common.enabled') : $t('configuration.common.disabled') }}
            </span>
          </div>
          <div class="content-display">{{ previewConfig.content }}</div>
        </div>
      </div>
    </div>

    <!-- 加载默认提示词弹窗 -->
    <div v-if="showDefaultsModal" class="defaults-modal" @click="closeDefaultsModal">
      <div class="modal-content large" @click.stop>
        <div class="modal-header">
          <h3>{{ $t('configuration.aiModePrompt.defaultsPreview') }}</h3>
          <button class="close-btn" @click="closeDefaultsModal">×</button>
        </div>
        <div class="modal-body">
          <div class="tabs">
            <button class="tab-btn" :class="{ active: activeTab === 'planner_text' }"
              @click="activeTab = 'planner_text'">Planner - {{ $t('configuration.aiModePrompt.textPrompt') }}</button>
            <button class="tab-btn" :class="{ active: activeTab === 'planner_vision' }"
              @click="activeTab = 'planner_vision'">Planner - {{ $t('configuration.aiModePrompt.visionPrompt') }}</button>
            <button class="tab-btn" :class="{ active: activeTab === 'executor_text' }"
              @click="activeTab = 'executor_text'">Executor - {{ $t('configuration.aiModePrompt.textPrompt') }}</button>
            <button class="tab-btn" :class="{ active: activeTab === 'executor_vision' }"
              @click="activeTab = 'executor_vision'">Executor - {{ $t('configuration.aiModePrompt.visionPrompt') }}</button>
            <button class="tab-btn" :class="{ active: activeTab === 'hermes_agent' }"
              @click="activeTab = 'hermes_agent'">{{ $t('configuration.aiModePrompt.hermesPrompt') }}</button>
          </div>
          <div class="content-display">{{ defaultPrompts[activeTab] || $t('configuration.aiModePrompt.noContent') }}</div>
          <div class="modal-actions">
            <button class="cancel-btn" @click="closeDefaultsModal">{{ $t('configuration.common.cancel') }}</button>
            <button class="confirm-btn" @click="confirmLoadDefaults" :disabled="isLoadingDefaults">
              {{ isLoadingDefaults ? $t('configuration.aiModePrompt.loading') : $t('configuration.aiModePrompt.confirmLoad') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import api from '@/utils/api'
import { ElMessage } from 'element-plus'

const API_BASE = '/ai-test/prompts'

export default {
  name: 'AIModePromptConfig',
  data() {
    return {
      configs: [],
      showAddModal: false,
      showEditModal: false,
      showPreviewModal: false,
      showDefaultsModal: false,
      isEditing: false,
      isSaving: false,
      isLoadingDefaults: false,
      editingConfigId: null,
      previewConfig: {},
      defaultPrompts: { planner_text: '', planner_vision: '', executor_text: '', executor_vision: '', hermes_agent: '' },
      activeTab: 'planner_text',
      configForm: {
        name: '',
        prompt_type: '',
        content: '',
        is_active: true
      }
    }
  },
  mounted() {
    this.loadConfigs()
  },
  methods: {
    getTypeLabel(type) {
      const map = {
        planner_text: `Planner - ${this.$t('configuration.aiModePrompt.textPrompt')}`,
        planner_vision: `Planner - ${this.$t('configuration.aiModePrompt.visionPrompt')}`,
        executor_text: `Executor - ${this.$t('configuration.aiModePrompt.textPrompt')}`,
        executor_vision: `Executor - ${this.$t('configuration.aiModePrompt.visionPrompt')}`,
        hermes_agent: this.$t('configuration.aiModePrompt.hermesPrompt')
      }
      return map[type] || type
    },
    async loadConfigs() {
      try {
        const response = await api.get(`${API_BASE}/`)
        this.configs = Array.isArray(response.data) ? response.data : (response.data.results || [])
      } catch (error) {
        ElMessage.error(this.$t('configuration.aiModePrompt.messages.loadFailed'))
      }
    },
    openAddModal() {
      this.resetForm()
      this.isEditing = false
      this.showAddModal = true
    },
    editConfig(config) {
      this.isEditing = true
      this.editingConfigId = config.id
      this.configForm = {
        name: config.name,
        prompt_type: config.prompt_type,
        content: config.content,
        is_active: config.is_active
      }
      this.showEditModal = true
    },
    async saveConfig() {
      this.isSaving = true
      try {
        if (this.isEditing) {
          await api.put(`${API_BASE}/${this.editingConfigId}/`, this.configForm)
          ElMessage.success(this.$t('configuration.aiModePrompt.messages.updateSuccess'))
        } else {
          await api.post(`${API_BASE}/`, this.configForm)
          ElMessage.success(this.$t('configuration.aiModePrompt.messages.saveSuccess'))
        }
        this.closeModals()
        this.loadConfigs()
      } catch (error) {
        ElMessage.error(this.$t('configuration.aiModePrompt.messages.saveFailed') + ': ' + (error.response?.data?.error || error.message))
      } finally {
        this.isSaving = false
      }
    },
    async deleteConfig(id) {
      if (!confirm(this.$t('configuration.aiModePrompt.messages.deleteConfirm'))) return
      try {
        await api.delete(`${API_BASE}/${id}/`)
        ElMessage.success(this.$t('configuration.aiModePrompt.messages.deleteSuccess'))
        this.loadConfigs()
      } catch (error) {
        ElMessage.error(this.$t('configuration.aiModePrompt.messages.deleteFailed'))
      }
    },
    previewPrompt(config) {
      this.previewConfig = config
      this.showPreviewModal = true
    },
    async loadDefaultPrompts() {
      try {
        const response = await api.get(`${API_BASE}/load_defaults/`)
        this.defaultPrompts = response.data.defaults
        this.showDefaultsModal = true
      } catch (error) {
        ElMessage.error(this.$t('configuration.aiModePrompt.messages.loadDefaultsFailed'))
      }
    },
    async confirmLoadDefaults() {
      this.isLoadingDefaults = true
      try {
        for (const [type, content] of Object.entries(this.defaultPrompts)) {
          if (content) {
            const label = type === 'browser_use_text'
              ? this.$t('configuration.aiModePrompt.defaultTextName')
              : type === 'browser_use_vision'
                ? this.$t('configuration.aiModePrompt.defaultVisionName')
                : this.$t('configuration.aiModePrompt.defaultHermesName')
            await api.post(`${API_BASE}/`, {
              name: label,
              prompt_type: type,
              content: content,
              is_active: true
            })
          }
        }
        ElMessage.success(this.$t('configuration.aiModePrompt.messages.defaultsLoaded'))
        this.closeDefaultsModal()
        this.loadConfigs()
      } catch (error) {
        ElMessage.error(this.$t('configuration.aiModePrompt.messages.loadDefaultsFailed'))
      } finally {
        this.isLoadingDefaults = false
      }
    },
    closeModals() {
      this.showAddModal = false
      this.showEditModal = false
      this.isEditing = false
      this.editingConfigId = null
      this.resetForm()
    },
    closePreview() {
      this.showPreviewModal = false
      this.previewConfig = {}
    },
    closeDefaultsModal() {
      this.showDefaultsModal = false
    },
    resetForm() {
      this.configForm = { name: '', prompt_type: '', content: '', is_active: true }
    },
    truncateContent(content, max) {
      if (!content) return ''
      return content.length <= max ? content : content.substring(0, max) + '...'
    },
    formatDateTime(str) {
      if (!str) return ''
      return new Date(str).toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
      })
    }
  }
}
</script>

<style scoped>
.ai-mode-prompt-config {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}
.page-header {
  text-align: center;
  margin-bottom: 40px;
}
.page-header h1 {
  font-size: 2.5rem;
  color: #2c3e50;
  margin-bottom: 10px;
}
.page-header p {
  color: #666;
  font-size: 1.1rem;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 30px;
  flex-wrap: wrap;
  gap: 15px;
}
.section-header h2 {
  color: #2c3e50;
  margin: 0;
}
.header-actions {
  display: flex;
  gap: 10px;
}
.load-defaults-btn {
  background: #9b59b6;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1rem;
}
.load-defaults-btn:hover { background: #8e44ad; }
.add-config-btn {
  background: #27ae60;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1rem;
}
.add-config-btn:hover { background: #219a52; }
.configs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(600px, 1fr));
  gap: 20px;
}
.config-card {
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 4px 6px rgba(0,0,0,0.1);
  border: 1px solid #e1e8ed;
  transition: transform 0.2s, box-shadow 0.2s;
}
.config-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 15px rgba(0,0,0,0.15);
}
.config-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.config-title h3 {
  color: #2c3e50;
  margin: 0 0 10px 0;
  font-size: 1.3rem;
}
.config-badges {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.type-badge, .status-badge {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 600;
}
.type-badge.browser_use_text {
  background: #e3f2fd;
  color: #1565c0;
}
.type-badge.browser_use_vision {
  background: #fce4ec;
  color: #c62828;
}
.type-badge.hermes_agent {
  background: #e8f5e9;
  color: #1b5e20;
}
.status-badge {
  background: #ffebee;
  color: #d32f2f;
}
.status-badge.active {
  background: #e8f5e8;
  color: #388e3c;
}
.config-actions {
  display: flex;
  gap: 8px;
}
.preview-btn, .edit-btn, .delete-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
}
.preview-btn { background: #3498db; color: white; }
.preview-btn:hover { background: #2980b9; }
.edit-btn { background: #f39c12; color: white; }
.edit-btn:hover { background: #e67e22; }
.delete-btn { background: #e74c3c; color: white; }
.delete-btn:hover { background: #c0392b; }
.prompt-preview {
  margin-bottom: 15px;
}
.prompt-preview label {
  font-size: 0.85rem;
  color: #666;
  font-weight: 600;
  display: block;
  margin-bottom: 8px;
}
.content-preview {
  background: #f8f9fa;
  padding: 12px;
  border-radius: 6px;
  color: #2c3e50;
  font-size: 0.9rem;
  line-height: 1.5;
  border-left: 4px solid #3498db;
  white-space: pre-wrap;
  word-break: break-all;
}
.config-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}
.meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.meta-item label {
  font-size: 0.85rem;
  color: #666;
  font-weight: 600;
}
.meta-item span {
  color: #2c3e50;
  font-size: 0.9rem;
}
.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: #666;
}
.empty-icon {
  font-size: 4rem;
  margin-bottom: 20px;
}
.empty-actions {
  display: flex;
  gap: 15px;
  justify-content: center;
  margin-top: 20px;
}
.add-first-config-btn, .load-defaults-first-btn {
  background: #3498db;
  color: white;
  border: none;
  padding: 15px 30px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1.1rem;
}
.load-defaults-first-btn {
  background: #9b59b6;
}
.config-modal, .preview-modal, .defaults-modal {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-content {
  background: white;
  border-radius: 12px;
  max-width: 600px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
}
.modal-content.large {
  max-width: 900px;
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 30px;
  border-bottom: 1px solid #eee;
}
.modal-header h3 {
  margin: 0;
  color: #2c3e50;
}
.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: #666;
}
.modal-body {
  padding: 30px;
}
.form-group {
  margin-bottom: 20px;
}
.form-group label {
  display: block;
  margin-bottom: 8px;
  color: #2c3e50;
  font-weight: 600;
}
.required { color: #e74c3c; }
.form-input, .form-select {
  width: 100%;
  padding: 12px;
  border: 2px solid #e1e8ed;
  border-radius: 8px;
  font-size: 1rem;
  box-sizing: border-box;
}
.form-input:focus, .form-select:focus {
  border-color: #3498db;
  outline: none;
}
.textarea-container {
  position: relative;
}
.form-textarea {
  width: 100%;
  padding: 12px;
  border: 2px solid #e1e8ed;
  border-radius: 8px;
  font-size: 0.95rem;
  font-family: monospace;
  resize: vertical;
  box-sizing: border-box;
}
.form-textarea.large {
  min-height: 400px;
}
.char-count {
  text-align: right;
  font-size: 0.8rem;
  color: #999;
  margin-top: 4px;
}
.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.checkbox-hint {
  margin-top: 4px;
  font-size: 0.85rem;
  color: #999;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}
.cancel-btn {
  background: #eee;
  color: #333;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1rem;
}
.confirm-btn {
  background: #3498db;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1rem;
}
.confirm-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.preview-meta {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}
.content-display {
  background: #f8f9fa;
  padding: 20px;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 0.9rem;
  line-height: 1.6;
  max-height: 500px;
  overflow-y: auto;
}
.tabs {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}
.tab-btn {
  padding: 10px 20px;
  border: 2px solid #e1e8ed;
  border-radius: 8px;
  background: white;
  cursor: pointer;
  font-size: 0.95rem;
}
.tab-btn.active {
  border-color: #3498db;
  background: #e3f2fd;
  color: #1565c0;
}
</style>
