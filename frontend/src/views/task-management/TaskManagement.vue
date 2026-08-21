<template>
  <div class="task-management-page">
    <div class="page-header">
      <div>
        <h2>测试任务管理</h2>
        <p>统一查看和维护测试任务</p>
      </div>
      <el-button type="primary" @click="dialogVisible = true">
        <el-icon><Plus /></el-icon>
        新建任务
      </el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="tasks" empty-text="暂无测试任务" style="width: 100%">
        <el-table-column label="负责人" min-width="150">
          <template #default="{ row }">
            <el-select v-model="row.owner" clearable placeholder="暂无候选人">
              <el-option v-for="candidate in candidateOptions" :key="candidate.value" :label="candidate.label" :value="candidate.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="任务名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="description" label="任务描述" min-width="240" show-overflow-tooltip />
        <el-table-column label="当前状态" min-width="130">
          <template #default="{ row }">
            <el-select v-model="row.status">
              <el-option v-for="status in statusOptions" :key="status.value" :label="status.label" :value="status.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="发布时间" min-width="130">
          <template #default="{ row }">
            <el-select v-model="row.releaseTime">
              <el-option v-for="releaseTime in releaseTimeOptions" :key="releaseTime.value" :label="releaseTime.label" :value="releaseTime.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" title="新建测试任务" width="560px" destroy-on-close>
      <el-form ref="taskFormRef" :model="taskForm" :rules="rules" label-width="90px">
        <el-form-item label="负责人">
          <el-select v-model="taskForm.owner" clearable placeholder="暂无候选人" style="width: 100%">
            <el-option v-for="candidate in candidateOptions" :key="candidate.value" :label="candidate.label" :value="candidate.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="taskForm.name" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="任务描述" prop="description">
          <el-input v-model="taskForm.description" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="当前状态" prop="status">
          <el-select v-model="taskForm.status" style="width: 100%">
            <el-option v-for="status in statusOptions" :key="status.value" :label="status.label" :value="status.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="发布时间" prop="releaseTime">
          <el-select v-model="taskForm.releaseTime" style="width: 100%">
            <el-option v-for="releaseTime in releaseTimeOptions" :key="releaseTime.value" :label="releaseTime.label" :value="releaseTime.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="taskForm.remark" type="textarea" :rows="2" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createTask">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

const candidateOptions = []
const dialogVisible = ref(false)
const taskFormRef = ref()
const tasks = ref([])
const statusOptions = [
  { label: 'To Do', value: 'TODO' },
  { label: 'Ongoing', value: 'ONGOING' },
  { label: 'Ready', value: 'READY' },
  { label: 'Released', value: 'RELEASED' }
]
const releaseTimeOptions = [
  { label: '本周', value: 'THIS_WEEK' },
  { label: '下周', value: 'NEXT_WEEK' },
  { label: '待定', value: 'TBD' }
]
const taskForm = reactive({
  owner: '',
  name: '',
  description: '',
  status: 'TODO',
  releaseTime: 'TBD',
  remark: ''
})
const rules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  description: [{ required: true, message: '请输入任务描述', trigger: 'blur' }],
  status: [{ required: true, message: '请选择当前状态', trigger: 'change' }],
  releaseTime: [{ required: true, message: '请选择发布时间', trigger: 'change' }]
}

const resetTaskForm = () => {
  Object.assign(taskForm, {
    owner: '',
    name: '',
    description: '',
    status: 'TODO',
    releaseTime: 'TBD',
    remark: ''
  })
}

const createTask = async () => {
  const isValid = await taskFormRef.value.validate().catch(() => false)
  if (!isValid) return

  tasks.value.push({ id: crypto.randomUUID(), ...taskForm })
  ElMessage.success('测试任务已创建')
  dialogVisible.value = false
  resetTaskForm()
}
</script>

<style scoped lang="scss">
.task-management-page {
  padding: 24px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;

  h2 {
    margin: 0;
    color: #303133;
    font-size: 20px;
  }

  p {
    margin: 8px 0 0;
    color: #909399;
    font-size: 14px;
  }
}

@media (max-width: 768px) {
  .task-management-page {
    padding: 16px;
  }
}
</style>