<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">{{ $t('testcase.title') }}</h1>
      <div class="header-actions">
        <el-button type="info" @click="showImportRecords = true">
          <el-icon><List /></el-icon>
          {{ $t('testcase.importRecords') }}
        </el-button>
        <el-button type="warning" @click="showImportDialog = true">
          <el-icon><Upload /></el-icon>
          {{ $t('testcase.importCases') }}
        </el-button>
        <el-button
          v-if="selectedTestCases.length > 0"
          type="danger"
          @click="batchDeleteTestCases"
          :disabled="isDeleting">
          <el-icon><Delete /></el-icon>
          {{ $t('testcase.batchDelete') }} ({{ selectedTestCases.length }})
        </el-button>
        <el-button type="success" @click="exportToExcel">
          <el-icon><Download /></el-icon>
          {{ $t('testcase.exportExcel') }}
        </el-button>
        <el-button type="primary" @click="$router.push('/ai-generation/testcases/create')">
          <el-icon><Plus /></el-icon>
          {{ $t('testcase.newCase') }}
        </el-button>
      </div>
    </div>
    
    <div class="card-container">
      <div class="filter-bar">
        <el-row :gutter="20">
          <el-col :span="5">
            <el-input
              v-model="searchText"
              :placeholder="$t('testcase.searchPlaceholder')"
              clearable
              @input="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </el-col>
          <el-col :span="4">
            <el-select v-model="projectFilter" :placeholder="$t('testcase.relatedProject')" clearable @change="handleFilter">
              <el-option
                v-for="project in projects"
                :key="project.id"
                :label="project.name"
                :value="project.id"
              />
            </el-select>
          </el-col>
          <el-col :span="3">
            <el-select v-model="priorityFilter" :placeholder="$t('testcase.priorityFilter')" clearable @change="handleFilter">
              <el-option :label="$t('testcase.low')" value="low" />
              <el-option :label="$t('testcase.medium')" value="medium" />
              <el-option :label="$t('testcase.high')" value="high" />
              <el-option :label="$t('testcase.critical')" value="critical" />
            </el-select>
          </el-col>
        </el-row>
      </div>
      
      <div class="table-container">
        <el-table 
          :data="testcases" 
          v-loading="loading" 
          style="width: 100%"
          height="100%"
          @selection-change="handleSelectionChange">
          <el-table-column type="selection" width="55" />
          <el-table-column type="index" :label="$t('testcase.serialNumber')" width="80" :index="getSerialNumber" />
          <el-table-column prop="title" :label="$t('testcase.caseTitle')" min-width="250">
            <template #default="{ row }">
              <el-link @click="goToTestCase(row.id)" type="primary">
                {{ row.title }}
              </el-link>
            </template>
          </el-table-column>
          <el-table-column prop="project.name" :label="$t('testcase.relatedProject')" width="150">
            <template #default="{ row }">
              {{ row.project?.name || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="versions" :label="$t('testcase.relatedVersions')" width="200">
            <template #default="{ row }">
              <div v-if="row.versions && row.versions.length > 0" class="version-tags">
                <el-tag 
                  v-for="version in row.versions.slice(0, 2)" 
                  :key="version.id" 
                  size="small" 
                  :type="version.is_baseline ? 'warning' : 'info'"
                  class="version-tag"
                >
                  {{ version.name }}
                </el-tag>
                <el-tooltip v-if="row.versions.length > 2" :content="getVersionsTooltip(row.versions)">
                  <el-tag size="small" type="info" class="version-tag">
                    +{{ row.versions.length - 2 }}
                  </el-tag>
                </el-tooltip>
              </div>
              <span v-else class="no-version">{{ $t('testcase.noVersion') }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="priority" :label="$t('testcase.priority')" width="100">
            <template #default="{ row }">
              <el-tag :class="`priority-tag ${row.priority}`">{{ getPriorityText(row.priority) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="test_type" :label="$t('testcase.testType')" width="120">
            <template #default="{ row }">
              {{ getTypeText(row.test_type) }}
            </template>
          </el-table-column>
          <el-table-column prop="author.username" :label="$t('testcase.author')" width="120" />
          <el-table-column prop="created_at" :label="$t('testcase.createdAt')" width="180">
            <template #default="{ row }">
              {{ formatDate(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column :label="$t('project.actions')" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="editTestCase(row)">{{ $t('common.edit') }}</el-button>
              <el-button size="small" type="danger" @click="deleteTestCase(row)">{{ $t('common.delete') }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[15, 25, 35, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <!-- 导入用例弹窗 -->
    <el-dialog v-model="showImportDialog" :title="$t('testcase.importDialogTitle')" width="500px">
      <div style="margin-bottom: 20px;">
        <el-alert :title="$t('testcase.importAlert')" type="info" :closable="false" show-icon />
      </div>
      <el-form label-width="100px">
        <el-form-item :label="$t('testcase.importProject')" required>
          <el-select v-model="importForm.projectId" placeholder="请选择项目" style="width: 100%;">
            <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('testcase.importFile')" required>
          <el-upload
            class="upload-demo"
            action="#"
            :auto-upload="false"
            :on-change="handleFileChange"
            :limit="1"
            accept=".xlsx,.xls"
            :file-list="importForm.fileList"
          >
            <template #trigger>
              <el-button type="primary">{{ $t('testcase.selectFile') }}</el-button>
            </template>
            <template #tip>
              <div class="el-upload__tip">{{ $t('testcase.excelOnly') }}</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="downloadImportTemplate" type="success" plain style="float: left;">{{ $t('testcase.downloadTemplate') }}</el-button>
          <el-button @click="showImportDialog = false">{{ $t('testcase.cancel') }}</el-button>
          <el-button type="primary" @click="submitImport" :loading="importing">{{ $t('testcase.startImport') }}</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 导入记录弹窗 -->
    <el-dialog v-model="showImportRecords" :title="$t('testcase.importRecordsTitle')" width="900px" @open="fetchImportRecords">
      <el-table :data="importRecords" v-loading="loadingRecords" style="width: 100%" max-height="400">
        <el-table-column prop="file_name" :label="$t('testcase.fileName')" min-width="150" show-overflow-tooltip />
        <el-table-column prop="project_name" :label="$t('testcase.importProject')" width="120" />
        <el-table-column prop="status" :label="$t('testcase.importStatus')" width="100">
          <template #default="{ row }">
            <el-tag :type="getImportStatusType(row.status)">{{ getImportStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('testcase.importProgress')" width="120">
          <template #default="{ row }">
            <el-progress :percentage="row.progress" :status="row.status === 'success' ? 'success' : (row.status === 'failed' ? 'exception' : '')" />
          </template>
        </el-table-column>
        <el-table-column :label="$t('testcase.importResultStats')" width="180">
          <template #default="{ row }">
            <span style="color: #67C23A">{{ $t('testcase.success') }}: {{ row.success_count }}</span> |
            <span style="color: #F56C6C">{{ $t('testcase.failed') }}: {{ row.failed_count }}</span> |
            <span style="color: #E6A23C">{{ $t('testcase.duplicate') }}: {{ row.duplicate_count }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" :label="$t('testcase.importTime')" width="160">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('testcase.importActions')" width="100" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.error_summary && row.error_summary.length > 0" type="primary" link @click="showErrorDetail(row)">{{ $t('testcase.viewDetail') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-container" style="margin-top: 15px;">
        <el-pagination
          v-model:current-page="recordPage"
          v-model:page-size="recordPageSize"
          :total="recordTotal"
          layout="total, prev, pager, next"
          @current-change="handleRecordPageChange"
        />
      </div>
    </el-dialog>

    <!-- 错误明细弹窗 -->
    <el-dialog v-model="showErrorDialog" :title="$t('testcase.importErrorDetail')" width="600px" append-to-body>
      <el-table :data="currentErrorDetail" style="width: 100%" max-height="300">
        <el-table-column prop="row" :label="$t('testcase.excelRow')" width="100" />
        <el-table-column prop="error" :label="$t('testcase.errorReason')" />
      </el-table>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Download, Delete, Upload, List } from '@element-plus/icons-vue'
import api from '@/utils/api'
import dayjs from 'dayjs'
import * as XLSX from 'xlsx'

const { t } = useI18n()
const router = useRouter()
const loading = ref(false)
const testcases = ref([])
const projects = ref([])
const currentPage = ref(1)
const pageSize = ref(15)
const total = ref(0)
const searchText = ref('')
const projectFilter = ref('')
const priorityFilter = ref('')
const selectedTestCases = ref([])
const isDeleting = ref(false)

const fetchTestCases = async () => {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      search: searchText.value,
      project: projectFilter.value,
      priority: priorityFilter.value
    }
    const response = await api.get('/testcases/', { params })
    testcases.value = response.data.results || []
    total.value = response.data.count || 0
  } catch (error) {
    ElMessage.error(t('testcase.fetchListFailed'))
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  currentPage.value = 1
  fetchTestCases()
}

const handleFilter = () => {
  currentPage.value = 1
  fetchTestCases()
}

const handlePageChange = () => {
  fetchTestCases()
}

const handleSizeChange = () => {
  currentPage.value = 1
  fetchTestCases()
}

const goToTestCase = (id) => {
  router.push(`/ai-generation/testcases/${id}`)
}

const editTestCase = (testcase) => {
  router.push(`/ai-generation/testcases/${testcase.id}/edit`)
}

const deleteTestCase = async (testcase) => {
  try {
    await ElMessageBox.confirm(t('testcase.deleteConfirm'), t('common.warning'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning'
    })
    
    await api.delete(`/testcases/${testcase.id}/`)
    ElMessage.success(t('testcase.deleteSuccess'))
    fetchTestCases()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(t('testcase.deleteFailed'))
    }
  }
}

// 处理选择变化
const handleSelectionChange = (selection) => {
  selectedTestCases.value = selection
}

// 获取序号
const getSerialNumber = (index) => {
  return (currentPage.value - 1) * pageSize.value + index + 1
}

// 批量删除
const batchDeleteTestCases = async () => {
  if (selectedTestCases.value.length === 0) {
    ElMessage.warning(t('testcase.selectFirst'))
    return
  }

  try {
    await ElMessageBox.confirm(
      t('testcase.batchDeleteConfirm', { count: selectedTestCases.value.length }),
      t('common.warning'),
      {
        confirmButtonText: t('common.confirm'),
        cancelButtonText: t('common.cancel'),
        type: 'warning'
      }
    )

    isDeleting.value = true
    let successCount = 0
    let failCount = 0

    // 逐个删除选中的测试用例
    for (const testcase of selectedTestCases.value) {
      try {
        await api.delete(`/testcases/${testcase.id}/`)
        successCount++
      } catch (error) {
        console.error(`Delete test case ${testcase.id} failed:`, error)
        failCount++
      }
    }

    // 显示删除结果
    if (successCount > 0) {
      if (failCount > 0) {
        ElMessage.success(t('testcase.batchDeletePartialSuccess', { successCount, failCount }))
      } else {
        ElMessage.success(t('testcase.batchDeleteSuccess', { successCount }))
      }
    } else {
      ElMessage.error(t('testcase.batchDeleteFailed'))
    }

    // 清空选择并重新加载列表
    selectedTestCases.value = []
    fetchTestCases()

  } catch (error) {
    if (error !== 'cancel') {
      console.error('Batch delete failed:', error)
      ElMessage.error(t('testcase.batchDeleteError') + ': ' + (error.message || t('common.error')))
    }
  } finally {
    isDeleting.value = false
  }
}

const getPriorityText = (priority) => {
  const textMap = {
    low: t('testcase.low'),
    medium: t('testcase.medium'),
    high: t('testcase.high'),
    critical: t('testcase.critical')
  }
  return textMap[priority] || priority
}

const getTypeText = (type) => {
  const textMap = {
    functional: t('testcase.functional'),
    integration: t('testcase.integration'),
    api: t('testcase.api'),
    ui: t('testcase.ui'),
    performance: t('testcase.performance'),
    security: t('testcase.security')
  }
  return textMap[type] || '-'
}

const formatDate = (dateString) => {
  return dayjs(dateString).format('YYYY-MM-DD HH:mm')
}

const getVersionsTooltip = (versions) => {
  return versions.map(v => v.name + (v.is_baseline ? ' (' + t('testcase.baseline') + ')' : '')).join('、')
}

// 将HTML的<br>标签转换为换行符（用于Excel导出）
const convertBrToNewline = (text) => {
  if (!text) return ''
  return text.replace(/<br\s*\/?>/gi, '\n')
}

const exportToExcel = async () => {
  try {
    loading.value = true

    // 确定要导出的数据
    let testCasesToExport = []

    if (selectedTestCases.value.length > 0) {
      // 如果有勾选，导出勾选的数据
      testCasesToExport = selectedTestCases.value
    } else {
      // 如果没有勾选，分页获取所有数据
      const pageSize = 100  // 使用后端允许的最大值
      let page = 1
      let hasMore = true
      let allData = []

      while (hasMore) {
        const response = await api.get('/testcases/', {
          params: {
            page: page,
            page_size: pageSize,
            search: searchText.value,
            project: projectFilter.value,
            priority: priorityFilter.value
          }
        })

        const results = response.data.results || []
        allData.push(...results)

        // 检查是否还有更多数据
        // 如果返回的数据少于pageSize，说明已经是最后一页
        if (results.length < pageSize) {
          hasMore = false
        } else {
          page++
        }
      }

      testCasesToExport = allData
    }

    if (testCasesToExport.length === 0) {
      ElMessage.warning(t('testcase.noDataToExport'))
      loading.value = false
      return
    }

    // 创建工作簿
    const workbook = XLSX.utils.book_new()

    // 准备Excel数据
    const worksheetData = [
      [t('testcase.excelNumber'), t('testcase.excelTitle'), t('testcase.excelProject'), t('testcase.excelVersions'), t('testcase.excelPreconditions'), t('testcase.excelSteps'), t('testcase.excelExpectedResult'), t('testcase.excelPriority'), t('testcase.excelTestType'), t('testcase.excelAuthor'), t('testcase.excelCreatedAt')]
    ]

    testCasesToExport.forEach((testcase, index) => {
      const versions = testcase.versions && testcase.versions.length > 0
        ? testcase.versions.map(v => v.name + (v.is_baseline ? '(' + t('testcase.baseline') + ')' : '')).join('、')
        : t('testcase.noVersion')

      worksheetData.push([
        `TC${String(index + 1).padStart(3, '0')}`,
        testcase.title || '',
        testcase.project?.name || '',
        versions,
        convertBrToNewline(testcase.preconditions || ''),
        convertBrToNewline(testcase.steps || ''),
        convertBrToNewline(testcase.expected_result || ''),
        getPriorityText(testcase.priority),
        getTypeText(testcase.test_type),
        testcase.author?.username || '',
        formatDate(testcase.created_at)
      ])
    })
    
    // 创建工作表
    const worksheet = XLSX.utils.aoa_to_sheet(worksheetData)
    
    // 设置列宽
    const colWidths = [
      { wch: 15 }, // Test case number
      { wch: 30 }, // Case title
      { wch: 20 }, // Related project
      { wch: 25 }, // Related versions
      { wch: 30 }, // Preconditions
      { wch: 40 }, // Steps
      { wch: 30 }, // Expected result
      { wch: 10 }, // Priority
      { wch: 15 }, // Test type
      { wch: 15 }, // Author
      { wch: 20 }  // Created at
    ]
    worksheet['!cols'] = colWidths
    
    // 设置表头样式
    for (let col = 0; col < worksheetData[0].length; col++) {
      const cellAddress = XLSX.utils.encode_cell({ r: 0, c: col })
      if (!worksheet[cellAddress]) continue
      worksheet[cellAddress].s = {
        font: { bold: true },
        alignment: { horizontal: 'center', vertical: 'center', wrapText: true }
      }
    }
    
    // 设置其他行的样式
    for (let row = 1; row < worksheetData.length; row++) {
      for (let col = 0; col < worksheetData[row].length; col++) {
        const cellAddress = XLSX.utils.encode_cell({ r: row, c: col })
        if (worksheet[cellAddress]) {
          worksheet[cellAddress].s = {
            alignment: { vertical: 'top', wrapText: true }
          }
        }
      }
    }

    // Add worksheet to workbook
    XLSX.utils.book_append_sheet(workbook, worksheet, t('testcase.excelSheetName'))

    // Generate filename
    const fileName = t('testcase.excelFileName', { date: new Date().toISOString().slice(0, 10) })

    // Export file
    XLSX.writeFile(workbook, fileName)

    ElMessage.success(t('testcase.exportSuccess'))
  } catch (error) {
    console.error('Export test cases failed:', error)
    ElMessage.error(t('testcase.exportFailed') + ': ' + (error.message || t('common.error')))
  } finally {
    loading.value = false
  }
}

const fetchProjects = async () => {
  try {
    const response = await api.get('/projects/')
    projects.value = response.data.results || response.data || []
  } catch (error) {
    ElMessage.error(t('testcase.fetchProjectsFailed'))
  }
}

// ========== 导入相关逻辑 ==========
const showImportDialog = ref(false)
const showImportRecords = ref(false)
const showErrorDialog = ref(false)
const importing = ref(false)
const loadingRecords = ref(false)
const importRecords = ref([])
const recordPage = ref(1)
const recordPageSize = ref(10)
const recordTotal = ref(0)
const currentErrorDetail = ref([])
let pollingTimer = null

const importForm = ref({
  projectId: '',
  fileList: []
})

const handleFileChange = (file, fileList) => {
  importForm.value.fileList = fileList.slice(-1)
}

const downloadImportTemplate = async () => {
  try {
    const response = await api.get('/testcases/import/template/', { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', 'testcase_import_template.xlsx')
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error('下载模板失败')
  }
}

const submitImport = async () => {
  if (!importForm.value.projectId) {
    ElMessage.warning('请选择所属项目')
    return
  }
  if (importForm.value.fileList.length === 0) {
    ElMessage.warning('请选择要导入的Excel文件')
    return
  }

  importing.value = true
  const formData = new FormData()
  formData.append('project_id', importForm.value.projectId)
  formData.append('file', importForm.value.fileList[0].raw)

  try {
    await api.post('/testcases/import/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    ElMessage.success('文件上传成功，正在后台导入')
    showImportDialog.value = false
    importForm.value.fileList = []
    fetchTestCases()
    showImportRecords.value = true
  } catch (error) {
    ElMessage.error('导入失败：' + (error.response?.data?.error || error.message))
  } finally {
    importing.value = false
  }
}

const fetchImportRecords = async () => {
  loadingRecords.value = true
  try {
    const response = await api.get('/testcases/import/records/', {
      params: {
        page: recordPage.value,
        page_size: recordPageSize.value
      }
    })
    importRecords.value = response.data.results || []
    recordTotal.value = response.data.count || 0

    // 如果有正在运行的任务，启动轮询
    const hasRunning = importRecords.value.some(r => r.status === 'pending' || r.status === 'running')
    if (hasRunning && !pollingTimer) {
      pollingTimer = setInterval(() => {
        fetchImportRecordsSilent()
      }, 3000)
    } else if (!hasRunning && pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
      fetchTestCases() // 导入完成后刷新列表
    }
  } catch (error) {
    console.error('获取导入记录失败:', error)
  } finally {
    loadingRecords.value = false
  }
}

const fetchImportRecordsSilent = async () => {
  try {
    const response = await api.get('/testcases/import/records/', {
      params: {
        page: recordPage.value,
        page_size: recordPageSize.value
      }
    })
    importRecords.value = response.data.results || []
    recordTotal.value = response.data.count || 0
    
    const hasRunning = importRecords.value.some(r => r.status === 'pending' || r.status === 'running')
    if (!hasRunning && pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = null
      fetchTestCases()
    }
  } catch (error) {
    console.error('轮询导入记录失败:', error)
  }
}

const handleRecordPageChange = () => {
  fetchImportRecords()
}

const getImportStatusType = (status) => {
  const map = {
    pending: 'info',
    running: 'warning',
    success: 'success',
    partial: 'warning',
    failed: 'danger'
  }
  return map[status] || 'info'
}

const getImportStatusText = (status) => {
  const map = {
    pending: '排队中',
    running: '导入中',
    success: '成功',
    partial: '部分成功',
    failed: '失败'
  }
  return map[status] || status
}

const showErrorDetail = (row) => {
  currentErrorDetail.value = row.error_summary || []
  showErrorDialog.value = true
}

onMounted(() => {
  fetchProjects()
  fetchTestCases()
})

</script>

<style lang="scss" scoped>
.page-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 20px;
  box-sizing: border-box;
  overflow: hidden;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-shrink: 0;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.header-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.card-container {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
  background: #fff;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.filter-bar {
  padding: 20px;
  border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
}

.table-container {
  flex: 1;
  overflow: hidden;
  padding: 0 20px;
  
  :deep(.el-table) {
    height: 100% !important;
  }
  
  :deep(.el-table__body-wrapper) {
    overflow-y: auto !important;
  }
}

.pagination-container {
  padding: 20px;
  border-top: 1px solid #ebeef5;
  display: flex;
  justify-content: center;
  flex-shrink: 0;
}

.priority-tag {
  &.low { color: #67c23a; }
  &.medium { color: #e6a23c; }
  &.high { color: #f56c6c; }
  &.critical { color: #f56c6c; font-weight: bold; }
}

.version-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  
  .version-tag {
    margin: 0;
  }
}

.no-version {
  color: #909399;
  font-size: 12px;
  font-style: italic;
}

@media (max-width: 1200px) {
  .page-container {
    height: auto;
    min-height: 100vh;
    overflow-y: auto;
  }
  
  .card-container {
    min-height: 600px;
  }
  
  .table-container {
    min-height: 400px;
  }
}

@media (max-width: 768px) {
  .page-container {
    padding: 10px;
  }
  
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 15px;
  }
  
  .header-actions {
    width: 100%;
  }
  
  .filter-bar {
    padding: 15px;
  }
  
  .pagination-container {
    padding: 15px;
  }
}

.step-content {
  min-height: 200px;
}

.preview-info {
  padding: 15px;
  background-color: #f5f7fa;
  border-radius: 4px;

  p {
    margin: 5px 0;
  }
}
</style>