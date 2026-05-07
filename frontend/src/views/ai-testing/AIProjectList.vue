<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('uiAutomation.ai.project.title') }}</h1>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        {{ $t('uiAutomation.ai.project.newProject') }}
      </el-button>
    </div>

    <div class="card-container">
      <div class="filter-bar">
        <el-row :gutter="20">
          <el-col :span="8">
            <el-input
              v-model="searchText"
              :placeholder="$t('uiAutomation.project.searchPlaceholder')"
              clearable
              @input="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </el-col>
        </el-row>
      </div>

      <el-table :data="projects" v-loading="loading" style="width: 100%">
        <el-table-column prop="name" :label="$t('uiAutomation.project.projectName')" min-width="200" />
        <el-table-column prop="description" :label="$t('uiAutomation.common.description')" min-width="300" show-overflow-tooltip />
        <el-table-column prop="created_by_name" :label="$t('uiAutomation.project.owner')" width="120" />
        <el-table-column prop="created_at" :label="$t('uiAutomation.common.createTime')" width="180" :formatter="formatDate" />
        <el-table-column :label="$t('uiAutomation.common.operation')" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="editProject(row)">
              <el-icon><Edit /></el-icon>
              {{ $t('uiAutomation.common.edit') }}
            </el-button>
            <el-button size="small" type="danger" @click="deleteProject(row.id)">
              <el-icon><Delete /></el-icon>
              {{ $t('uiAutomation.common.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.currentPage"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>

    <!-- 创建项目对话框 -->
    <el-dialog v-model="showCreateDialog" :title="$t('uiAutomation.ai.project.createProject')" width="500px" :close-on-click-modal="false">
      <el-form ref="createFormRef" :model="createForm" :rules="formRules" label-width="100px">
        <el-form-item :label="$t('uiAutomation.project.projectName')" prop="name">
          <el-input v-model="createForm.name" :placeholder="$t('uiAutomation.project.rules.nameRequired')" />
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.common.description')" prop="description">
          <el-input v-model="createForm.description" type="textarea" :placeholder="$t('uiAutomation.ai.project.descPlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showCreateDialog = false">{{ $t('uiAutomation.common.cancel') }}</el-button>
          <el-button type="primary" @click="handleCreate">{{ $t('uiAutomation.common.confirm') }}</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 编辑项目对话框 -->
    <el-dialog v-model="showEditDialog" :title="$t('uiAutomation.ai.project.editProject')" width="500px" :close-on-click-modal="false">
      <el-form ref="editFormRef" :model="editForm" :rules="formRules" label-width="100px">
        <el-form-item :label="$t('uiAutomation.project.projectName')" prop="name">
          <el-input v-model="editForm.name" :placeholder="$t('uiAutomation.project.rules.nameRequired')" />
        </el-form-item>
        <el-form-item :label="$t('uiAutomation.common.description')" prop="description">
          <el-input v-model="editForm.description" type="textarea" :placeholder="$t('uiAutomation.ai.project.descPlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showEditDialog = false">{{ $t('uiAutomation.common.cancel') }}</el-button>
          <el-button type="primary" @click="handleEdit">{{ $t('uiAutomation.common.confirm') }}</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Edit, Delete } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { getAiProjects, createAiProject, updateAiProject, deleteAiProject } from '@/api/ai-testing'

const { t } = useI18n()

const projects = ref([])
const loading = ref(false)
const total = ref(0)
const pagination = reactive({
  currentPage: 1,
  pageSize: 10
})
const searchText = ref('')

const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const createFormRef = ref(null)
const editFormRef = ref(null)
const currentEditId = ref(null)

const createForm = reactive({
  name: '',
  description: ''
})

const editForm = reactive({
  name: '',
  description: ''
})

const formRules = computed(() => ({
  name: [
    { required: true, message: t('uiAutomation.project.rules.nameRequired'), trigger: 'blur' },
    { min: 2, max: 200, message: t('uiAutomation.project.rules.nameLength'), trigger: 'blur' }
  ]
}))

const formatDate = (row, column, cellValue) => {
  if (!cellValue) return ''
  return new Date(cellValue).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const loadProjects = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.currentPage,
      page_size: pagination.pageSize
    }
    if (searchText.value) {
      params.search = searchText.value
    }
    const response = await getAiProjects(params)
    projects.value = response.data.results || response.data
    total.value = response.data.count || projects.value.length
  } catch (error) {
    ElMessage.error(t('uiAutomation.ai.project.messages.loadFailed'))
    console.error('获取项目列表失败:', error)
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  pagination.currentPage = 1
  loadProjects()
}

const handleSizeChange = (size) => {
  pagination.pageSize = size
  loadProjects()
}

const handleCurrentChange = (current) => {
  pagination.currentPage = current
  loadProjects()
}

const handleCreate = async () => {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        await createAiProject({
          name: createForm.name,
          description: createForm.description
        })
        ElMessage.success(t('uiAutomation.ai.project.messages.createSuccess'))
        showCreateDialog.value = false
        createForm.name = ''
        createForm.description = ''
        loadProjects()
      } catch (error) {
        ElMessage.error(t('uiAutomation.ai.project.messages.createFailed'))
        console.error('创建项目失败:', error)
      }
    }
  })
}

const editProject = (project) => {
  currentEditId.value = project.id
  Object.assign(editForm, {
    name: project.name,
    description: project.description || ''
  })
  showEditDialog.value = true
}

const handleEdit = async () => {
  if (!editFormRef.value) return
  await editFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        await updateAiProject(currentEditId.value, {
          name: editForm.name,
          description: editForm.description
        })
        ElMessage.success(t('uiAutomation.ai.project.messages.updateSuccess'))
        showEditDialog.value = false
        loadProjects()
      } catch (error) {
        ElMessage.error(t('uiAutomation.ai.project.messages.updateFailed'))
        console.error('更新项目失败:', error)
      }
    }
  })
}

const deleteProject = async (id) => {
  try {
    await ElMessageBox.confirm(
      t('uiAutomation.project.messages.deleteConfirm'),
      t('uiAutomation.messages.confirm.delete'),
      {
        confirmButtonText: t('uiAutomation.common.confirm'),
        cancelButtonText: t('uiAutomation.common.cancel'),
        type: 'warning'
      }
    )
    await deleteAiProject(id)
    ElMessage.success(t('uiAutomation.ai.project.messages.deleteSuccess'))
    loadProjects()
  } catch (error) {
    if (error === 'cancel') return
    ElMessage.error(t('uiAutomation.ai.project.messages.deleteFailed'))
    console.error('删除项目失败:', error)
  }
}

onMounted(() => {
  loadProjects()
})
</script>

<style scoped>
.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
  position: sticky;
  bottom: 20px;
  background: transparent;
  z-index: 10;
}
</style>
