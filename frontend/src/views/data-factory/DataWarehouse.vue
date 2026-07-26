<template>
  <main class="warehouse-page">
    <header class="page-header">
      <div><h2>{{ $t('dataFactory.scenarios.warehouse') }}</h2><p>集中管理数据工厂的固有素材与可复用事件资产</p></div>
    </header>
    <section class="upload-panel">
      <div class="upload-panel-title">上传事件素材</div>
      <div class="upload-controls">
        <el-select v-model="uploadCategory" class="category-select" placeholder="选择存放路径">
          <el-option v-for="category in categories" :key="category.key" :label="category.label" :value="category.key" />
          <el-option label="自定义路径" value="__custom__" />
        </el-select>
        <el-input v-if="uploadCategory === '__custom__'" v-model="customCategory" class="category-select" placeholder="输入自定义目录名" />
        <el-upload ref="uploadRef" :auto-upload="false" multiple :limit="3" :on-change="selectFiles" :on-remove="selectFiles" :show-file-list="false" accept=".jpeg,.jpg,.mp4">
          <el-button class="select-media-button">选择事件素材</el-button>
        </el-upload>
        <el-button type="primary" class="upload-button" :disabled="!uploadFiles.length" :loading="uploading" @click="uploadMedia">上传{{ uploadFiles.length ? ` (${uploadFiles.length})` : '' }}</el-button>
      </div>
      <div v-if="uploadFiles.length" class="selected-files"><el-tag v-for="file in uploadFiles" :key="file.uid" closable @close="uploadRef?.handleRemove(file)">{{ file.name }}</el-tag></div>
    </section>
    <section v-loading="loading" class="warehouse-content">
      <section v-for="category in categories" :key="category.key" class="asset-section">
        <div class="section-title"><h3>{{ category.label }}</h3><div class="section-actions"><el-tag type="info">{{ category.group_count }} 组事件</el-tag><el-tooltip v-if="!['person', 'vehicle'].includes(category.key)" content="删除自定义目录" placement="top"><el-button class="delete-group-button" :icon="Delete" circle @click="deleteDirectory(category.key)" /></el-tooltip></div></div>
        <el-table :data="category.groups" empty-text="暂无素材">
          <el-table-column label="主素材" min-width="320" show-overflow-tooltip><template #default="{ row }"><el-button link type="primary" @click="previewMedia(category.key, row.path)">{{ row.path }}</el-button></template></el-table-column>
          <el-table-column label="关联图片" min-width="220" show-overflow-tooltip><template #default="{ row }"><el-button v-if="row.image_1" link type="primary" @click="previewMedia(category.key, `${category.key}/${row.image_1}`)">{{ row.image_1 }}</el-button><span v-else>-</span></template></el-table-column>
          <el-table-column label="关联视频" min-width="220" show-overflow-tooltip><template #default="{ row }"><el-button v-if="row.video_0" link type="primary" @click="previewMedia(category.key, `${category.key}/${row.video_0}`)">{{ row.video_0 }}</el-button><span v-else>-</span></template></el-table-column>
          <el-table-column label="操作" width="80" fixed="right"><template #default="{ row }"><el-tooltip content="删除整组" placement="top"><el-button class="delete-group-button" :icon="Delete" circle @click="deleteGroup(category.key, row)" /></el-tooltip></template></el-table-column>
        </el-table>
      </section>
      <el-empty v-if="!loading && !categories.length" description="数据仓库暂无固有资产" />
    </section>
    <el-dialog v-model="previewVisible" :title="previewName" width="760px" align-center @closed="clearPreview">
      <div v-loading="previewLoading" class="media-preview"><video v-if="previewIsVideo && previewUrl" :src="previewUrl" controls autoplay></video><el-image v-else-if="previewUrl" :src="previewUrl" fit="contain" /></div>
    </el-dialog>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import api from '@/utils/api'

const loading = ref(false)
const categories = ref([])
const uploadCategory = ref('person')
const customCategory = ref('')
const uploadRef = ref(null)
const uploadFiles = ref([])
const uploading = ref(false)
const previewVisible = ref(false)
const previewPath = ref('')
const previewCategory = ref('')
const previewUrl = ref('')
const previewLoading = ref(false)
const previewName = computed(() => previewPath.value.split('/').pop() || '')
const previewIsVideo = computed(() => previewPath.value.endsWith('.mp4'))

const loadWarehouse = async () => {
  loading.value = true
  try {
    categories.value = (await api.get('/data-factory/warehouse/')).data.categories || []
    if (!categories.value.some(category => category.key === uploadCategory.value)) uploadCategory.value = categories.value[0]?.key || 'person'
  } catch (error) {
    ElMessage.error('加载数据仓库失败')
  } finally {
    loading.value = false
  }
}

const selectFiles = (file, fileList) => { uploadFiles.value = fileList }

const uploadMedia = async () => {
  if (!uploadFiles.value.length) return
  const category = uploadCategory.value === '__custom__' ? customCategory.value.trim() : uploadCategory.value
  if (!category) {
    ElMessage.warning('请选择或输入存放路径')
    return
  }
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('category', category)
    uploadFiles.value.forEach(file => formData.append('files', file.raw))
    await api.post('/data-factory/warehouse_upload/', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
    uploadFiles.value = []
    uploadRef.value?.clearFiles()
    ElMessage.success('素材上传成功')
    await loadWarehouse()
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '素材上传失败')
  } finally {
    uploading.value = false
  }
}

const deleteGroup = async (category, group) => {
  try {
    await ElMessageBox.confirm(`确定删除事件组“${group.path}”及其关联图片、视频吗？`, '删除事件素材', { type: 'warning' })
    await api.delete('/data-factory/warehouse_group/', { params: { category, path: group.path } })
    ElMessage.success('事件素材组已删除')
    await loadWarehouse()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.response?.data?.error || '删除事件素材失败')
  }
}

const deleteDirectory = async category => {
  try {
    await ElMessageBox.confirm(`确定删除自定义目录“${category}”及其中全部事件素材吗？`, '删除自定义素材目录', { type: 'warning' })
    await api.delete('/data-factory/warehouse_directory/', { params: { category } })
    ElMessage.success('自定义素材目录已删除')
    await loadWarehouse()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.response?.data?.error || '删除自定义素材目录失败')
  }
}

const previewMedia = async (category, path) => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewCategory.value = category
  previewPath.value = path
  previewVisible.value = true
  previewLoading.value = true
  try {
    const response = await api.get('/data-factory/warehouse_media/', { params: { category, path }, responseType: 'blob' })
    previewUrl.value = URL.createObjectURL(response.data)
  } catch (error) {
    ElMessage.error('加载素材预览失败')
    previewVisible.value = false
  } finally {
    previewLoading.value = false
  }
}

const clearPreview = () => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  previewPath.value = ''
  previewCategory.value = ''
}

onMounted(loadWarehouse)
onBeforeUnmount(clearPreview)
</script>

<style scoped>
.warehouse-page { min-height: calc(100vh - 60px); padding: 24px; background: #f4f7fb; }
.page-header { margin-bottom: 16px; }.page-header h2 { margin: 0; color: #1c2b3a; font-size: 22px; }.page-header p { margin: 6px 0 0; color: #667085; }.upload-panel { display: flex; flex-wrap: wrap; align-items: center; gap: 14px 18px; margin-bottom: 16px; padding: 16px 18px; border: 1px solid #cfe0f5; border-radius: 6px; background: #f7fbff; }.upload-panel-title { color: #1d4ed8; font-size: 14px; font-weight: 600; white-space: nowrap; }.upload-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }.category-select { width: 180px; }.select-media-button { border-color: #a9c6eb; color: #175cd3; background: #fff; }.upload-button { min-width: 88px; }.selected-files { display: flex; flex-basis: 100%; flex-wrap: wrap; gap: 8px; padding-top: 2px; }.selected-files :deep(.el-tag) { max-width: 280px; }
.warehouse-content { display: grid; gap: 16px; }.asset-section { padding: 18px; border: 1px solid #e4e7ec; border-radius: 6px; background: #fff; }.section-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }.section-title h3 { margin: 0; color: #1d2939; font-size: 16px; }.section-actions { display: flex; align-items: center; gap: 8px; }.delete-group-button { margin: 0; border-color: #fecdca; color: #d92d20; background: #fff5f4; }.delete-group-button:hover { border-color: #d92d20; color: #fff; background: #d92d20; }.media-preview { display: flex; justify-content: center; min-height: 320px; background: #f8fafc; }.media-preview video { width: 100%; max-height: 520px; }.media-preview :deep(.el-image) { max-height: 520px; }
</style>