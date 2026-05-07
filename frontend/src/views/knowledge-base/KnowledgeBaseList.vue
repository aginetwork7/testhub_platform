<template>
  <div class="knowledge-base-container">
    <!-- 页面标题和操作区 -->
    <div class="page-header">
      <div class="header-left">
        <h2>{{ $t('knowledgeBase.title') }}</h2>
        <span class="subtitle">{{ $t('knowledgeBase.subtitle') }}</span>
      </div>
      <div class="header-right">
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          {{ $t('knowledgeBase.createKnowledgeBase') }}
        </el-button>
      </div>
    </div>

    <!-- 筛选区 -->
    <div class="filter-section">
      <el-form :inline="true" :model="filterForm" class="filter-form">
        <el-form-item :label="$t('knowledgeBase.project')">
          <el-select
            v-model="filterForm.project_id"
            :placeholder="$t('knowledgeBase.selectProject')"
            clearable
            style="width: 200px;"
            @change="handleFilter"
          >
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('knowledgeBase.status')">
          <el-select
            v-model="filterForm.is_active"
            :placeholder="$t('knowledgeBase.selectStatus')"
            clearable
            style="width: 150px;"
            @change="handleFilter"
          >
            <el-option :label="$t('knowledgeBase.active')" :value="true" />
            <el-option :label="$t('knowledgeBase.inactive')" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="filterForm.search"
            :placeholder="$t('knowledgeBase.searchNamePlaceholder')"
            clearable
            @keyup.enter="handleFilter"
            @clear="handleFilter"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleFilter">
            {{ $t('common.search') }}
          </el-button>
          <el-button @click="handleReset">
            {{ $t('common.reset') }}
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 统计区 -->
    <div class="stats-section">
      <el-row :gutter="20">
        <el-col :span="8">
          <div class="stat-card">
            <div class="stat-icon" style="background-color: #409eff;">
              <el-icon><FolderOpened /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.totalKnowledgeBases }}</div>
              <div class="stat-label">{{ $t('knowledgeBase.totalKnowledgeBases') }}</div>
            </div>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="stat-card">
            <div class="stat-icon" style="background-color: #67c23a;">
              <el-icon><Document /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats.totalDocuments }}</div>
              <div class="stat-label">{{ $t('knowledgeBase.totalDocuments') }}</div>
            </div>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="stat-card">
            <div class="stat-icon" style="background-color: #e6a23c;">
              <el-icon><Files /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ formatFileSize(stats.totalSize) }}</div>
              <div class="stat-label">{{ $t('knowledgeBase.totalSize') }}</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 表格区 -->
    <div class="table-section">
      <el-table
        v-loading="loading"
        :data="tableData"
        style="width: 100%"
        border
      >
        <el-table-column type="index" width="60" :label="$t('common.index')" />
        <el-table-column prop="name" :label="$t('knowledgeBase.name')" min-width="200">
          <template #default="{ row }">
            <el-link type="primary" @click="handleDetail(row)">
              {{ row.name }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column prop="project_name" :label="$t('knowledgeBase.project')" width="150" />
        <el-table-column prop="description" :label="$t('knowledgeBase.description')" min-width="200" show-overflow-tooltip />
        <el-table-column prop="is_active" :label="$t('knowledgeBase.status')" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? $t('knowledgeBase.active') : $t('knowledgeBase.inactive') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by_name" :label="$t('knowledgeBase.createdBy')" width="120" />
        <el-table-column prop="created_at" :label="$t('knowledgeBase.createdAt')" width="180">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.actions')" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="handleDetail(row)">
              {{ $t('common.detail') }}
            </el-button>
            <el-button type="primary" link @click="handleEdit(row)">
              {{ $t('common.edit') }}
            </el-button>
            <el-button type="danger" link @click="handleDelete(row)">
              {{ $t('common.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页区 -->
    <div class="pagination-section">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :page-sizes="[10, 20, 50, 100]"
        :total="pagination.total"
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handleSizeChange"
        @current-change="handlePageChange"
      />
    </div>

    <!-- 新建/编辑知识库对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'create' ? $t('knowledgeBase.createKnowledgeBase') : $t('knowledgeBase.editKnowledgeBase')"
      width="600px"
      @close="handleDialogClose"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
      >
        <el-form-item :label="$t('knowledgeBase.name')" prop="name">
          <el-input v-model="form.name" :placeholder="$t('knowledgeBase.namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="$t('knowledgeBase.project')" prop="project">
          <el-select v-model="form.project" :placeholder="$t('knowledgeBase.selectProject')" style="width: 100%;">
            <el-option
              v-for="project in projects"
              :key="project.id"
              :label="project.name"
              :value="project.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('knowledgeBase.description')" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            :placeholder="$t('knowledgeBase.descriptionPlaceholder')"
          />
        </el-form-item>

        <!-- 向量化配置 - 仅在创建时显示 -->
        <template v-if="dialogType === 'create'">
          <el-divider content-position="left">
            {{ $t('knowledgeBase.vectorizationConfig') }}
          </el-divider>

          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item prop="chunk_size">
                <template #label>
                  {{ $t('knowledgeBase.chunkSize') }}
                  <el-tooltip :content="$t('knowledgeBase.chunkSizeTip')" placement="top">
                    <el-icon class="help-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-input-number
                  v-model="form.chunk_size"
                  :min="100"
                  :max="5000"
                  :step="100"
                  style="width: 100%;"
                />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item prop="chunk_overlap">
                <template #label>
                  {{ $t('knowledgeBase.chunkOverlap') }}
                  <el-tooltip :content="$t('knowledgeBase.chunkOverlapTip')" placement="top">
                    <el-icon class="help-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-input-number
                  v-model="form.chunk_overlap"
                  :min="0"
                  :max="1000"
                  :step="10"
                  style="width: 100%;"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item>
            <template #label>
              {{ $t('knowledgeBase.enableVectorization') }}
              <el-tooltip :content="$t('knowledgeBase.enableVectorizationTip')" placement="top">
                <el-icon class="help-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-switch
              v-model="form.enable_vectorization"
              :active-text="$t('common.yes')"
              :inactive-text="$t('common.no')"
            />
          </el-form-item>

          <el-form-item :label="$t('knowledgeBase.uploadFile')" prop="file">
            <el-upload
              ref="uploadRef"
              class="upload-area"
              :auto-upload="false"
              :limit="1"
              :on-change="handleFileChange"
              :on-remove="handleFileRemove"
              :file-list="fileList"
              accept=".pdf,.doc,.docx,.txt,.md"
              drag
            >
              <el-icon class="el-icon--upload"><upload-filled /></el-icon>
              <div class="el-upload__text">
                {{ $t('knowledgeBase.dragFileTip') }}
              </div>
              <template #tip>
                <div class="el-upload__tip">
                  {{ $t('knowledgeBase.fileTypeTip') }}
                </div>
              </template>
            </el-upload>
          </el-form-item>
        </template>

        <el-form-item :label="$t('knowledgeBase.status')" prop="is_active">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          {{ $t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, FolderOpened, Document, Files, UploadFilled, QuestionFilled } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import {
  getKnowledgeBaseList,
  createKnowledgeBase,
  updateKnowledgeBase,
  deleteKnowledgeBase
} from '@/api/knowledge-base'
import api from '@/utils/api'

const { t } = useI18n()
const router = useRouter()

// 数据
const loading = ref(false)
const submitLoading = ref(false)
const tableData = ref([])
const projects = ref([])
const dialogVisible = ref(false)
const dialogType = ref('create')
const formRef = ref(null)
const uploadRef = ref(null)
const fileList = ref([])
const currentFile = ref(null)

// 筛选表单
const filterForm = reactive({
  project_id: '',
  is_active: '',
  search: ''
})

// 分页
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

// 统计数据
const stats = reactive({
  totalKnowledgeBases: 0,
  totalDocuments: 0,
  totalSize: 0
})

// 表单
const form = reactive({
  id: '',
  name: '',
  project: '',
  description: '',
  is_active: true,
  chunk_size: 500,
  chunk_overlap: 50,
  enable_vectorization: true
})

// 表单校验规则
const rules = {
  name: [
    { required: true, message: t('knowledgeBase.nameRequired'), trigger: 'blur' }
  ],
  project: [
    { required: true, message: t('knowledgeBase.projectRequired'), trigger: 'change' }
  ]
}

// 获取列表
const fetchData = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize
    }
    // 只添加有值的筛选参数
    if (filterForm.project_id) {
      params.project_id = filterForm.project_id
    }
    if (filterForm.is_active !== '') {
      params.is_active = filterForm.is_active
    }
    if (filterForm.search) {
      params.search = filterForm.search
    }
    const response = await getKnowledgeBaseList(params)
    tableData.value = response.data.results || response.data
    pagination.total = response.data.count || response.data.length

    // 计算统计数据
    stats.totalKnowledgeBases = pagination.total
    stats.totalDocuments = tableData.value.reduce((sum, item) => sum + (item.document_count || 0), 0)
    stats.totalSize = tableData.value.reduce((sum, item) => sum + (item.total_size || 0), 0)
  } catch (error) {
    ElMessage.error(t('common.fetchFailed'))
  } finally {
    loading.value = false
  }
}

// 获取项目列表
const fetchProjects = async () => {
  try {
    const response = await api.get('/projects/', { params: { page_size: 1000 } })
    projects.value = response.data.results || response.data
  } catch (error) {
    console.error('获取项目列表失败:', error)
  }
}

// 筛选
const handleFilter = () => {
  pagination.page = 1
  fetchData()
}

// 重置
const handleReset = () => {
  filterForm.project_id = ''
  filterForm.is_active = ''
  filterForm.search = ''
  handleFilter()
}

// 分页
const handleSizeChange = (size) => {
  pagination.pageSize = size
  fetchData()
}

const handlePageChange = (page) => {
  pagination.page = page
  fetchData()
}

// 新建
const handleCreate = () => {
  dialogType.value = 'create'
  dialogVisible.value = true
  // 使用 nextTick 确保对话框渲染后再重置表单
  nextTick(() => {
    resetForm()
  })
}

// 编辑
const handleEdit = (row) => {
  dialogType.value = 'edit'
  form.id = row.id
  form.name = row.name
  form.project = row.project
  form.description = row.description
  form.is_active = row.is_active
  dialogVisible.value = true
}

// 详情
const handleDetail = (row) => {
  router.push(`/ai-generation/knowledge-base/${row.id}`)
}

// 删除
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      t('knowledgeBase.deleteConfirm'),
      t('common.warning'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    )
    await deleteKnowledgeBase(row.id)
    ElMessage.success(t('common.deleteSuccess'))
    fetchData()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(t('common.deleteFailed'))
    }
  }
}

// 提交
const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitLoading.value = true
      try {
        if (dialogType.value === 'create') {
          // 创建知识库 - 使用 FormData 支持文件上传
          const formData = new FormData()
          formData.append('name', form.name)
          formData.append('project', form.project)
          formData.append('description', form.description || '')
          formData.append('is_active', form.is_active)
          formData.append('chunk_size', form.chunk_size)
          formData.append('chunk_overlap', form.chunk_overlap)
          formData.append('enable_vectorization', form.enable_vectorization)

          // 如果有文件，添加到 FormData
          if (currentFile.value) {
            formData.append('file', currentFile.value.raw)
          }

          await createKnowledgeBase(formData)
          ElMessage.success(t('common.createSuccess'))
        } else {
          // 编辑知识库
          const data = {
            name: form.name,
            project: form.project,
            description: form.description,
            is_active: form.is_active
          }
          await updateKnowledgeBase(form.id, data)
          ElMessage.success(t('common.updateSuccess'))
        }
        dialogVisible.value = false
        fetchData()
      } catch (error) {
        ElMessage.error(dialogType.value === 'create' ? t('common.createFailed') : t('common.updateFailed'))
      } finally {
        submitLoading.value = false
      }
    }
  })
}

// 文件选择处理
const handleFileChange = (file) => {
  currentFile.value = file
}

// 文件移除处理
const handleFileRemove = () => {
  currentFile.value = null
}

// 重置表单
const resetForm = () => {
  form.id = ''
  form.name = ''
  form.project = ''
  form.description = ''
  form.is_active = true
  form.chunk_size = 500
  form.chunk_overlap = 50
  form.enable_vectorization = true
  currentFile.value = null
  fileList.value = []
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  }
  if (formRef.value) {
    formRef.value.resetFields()
  }
}

// 对话框关闭
const handleDialogClose = () => {
  resetForm()
}

// 格式化文件大小
const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 格式化日期时间
const formatDateTime = (dateStr) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

// 检查知识库配置状态
const checkConfigStatus = async () => {
  try {
    const response = await api.get('/knowledge-base/check_config/')
    const config = response.data
    if (!config.has_embedding || !config.has_vision || !config.has_refiner) {
      const buildStatusHtml = (name, isConfigured) => {
        const icon = isConfigured ? '<span style="color: #67c23a; margin-right: 8px;">✓</span>' : '<span style="color: #f56c6c; margin-right: 8px;">✗</span>'
        const color = isConfigured ? '#606266' : '#f56c6c'
        return `<div style="margin: 8px 0; display: flex; align-items: center; color: ${color}; font-size: 14px;">${icon} ${name}</div>`
      }

      const htmlContent = `
        <div style="margin-bottom: 16px; font-size: 14px; color: #606266;">您的知识库 AI 模型配置尚未完善，缺少以下必要配置：</div>
        <div style="background-color: #f8f9fa; padding: 12px 20px; border-radius: 4px; margin-bottom: 16px;">
          ${buildStatusHtml('Embedding 模型 (用于向量化检索)', config.has_embedding)}
          ${buildStatusHtml('Vision 模型 (用于图文解析)', config.has_vision)}
          ${buildStatusHtml('Refiner 模型 (用于内容结构化总结)', config.has_refiner)}
        </div>
        <div style="font-size: 13px; color: #909399;">建议您先前往设置中心完成配置，否则部分功能将无法正常使用。</div>
      `

      ElMessageBox.confirm(
        htmlContent,
        '配置缺失提示',
        {
          confirmButtonText: '前往配置',
          cancelButtonText: t('common.cancel'),
          type: 'warning',
          dangerouslyUseHTMLString: true,
          customClass: 'kb-config-warning-dialog'
        }
      ).then(() => {
        router.push('/configuration/knowledge-base')
      }).catch(() => {
        // 用户选择暂不配置，继续留在当前页面
      })
    }
  } catch (error) {
    console.error('检查知识库配置失败:', error)
  }
}

onMounted(() => {
  fetchProjects()
  fetchData()
  checkConfigStatus()
})
</script>

<style lang="scss" scoped>
.knowledge-base-container {
  padding: 20px;

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;

    .header-left {
      h2 {
        margin: 0;
        font-size: 20px;
        color: #303133;
      }

      .subtitle {
        font-size: 14px;
        color: #909399;
      }
    }
  }

  .filter-section {
    background: #fff;
    padding: 20px;
    border-radius: 4px;
    margin-bottom: 20px;

    .filter-form {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
  }

  .stats-section {
    margin-bottom: 20px;

    .stat-card {
      background: #fff;
      border-radius: 4px;
      padding: 20px;
      display: flex;
      align-items: center;
      gap: 15px;

      .stat-icon {
        width: 50px;
        height: 50px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #fff;
        font-size: 24px;
      }

      .stat-info {
        .stat-value {
          font-size: 24px;
          font-weight: 600;
          color: #303133;
        }

        .stat-label {
          font-size: 14px;
          color: #909399;
        }
      }
    }
  }

  .table-section {
    background: #fff;
    border-radius: 4px;
    padding: 20px;
    margin-bottom: 20px;
  }

  .pagination-section {
    background: #fff;
    border-radius: 4px;
    padding: 15px 20px;
    display: flex;
    justify-content: flex-end;
  }

  .form-tip {
    font-size: 12px;
    color: #909399;
    margin-top: 4px;
    line-height: 1.4;
  }

  .help-icon {
    margin-left: 5px;
    color: #909399;
    cursor: help;
    vertical-align: middle;
  }

  .upload-area {
    width: 100%;

    :deep(.el-upload) {
      width: 100%;
    }

    :deep(.el-upload-dragger) {
      width: 100%;
    }
  }
}
</style>
