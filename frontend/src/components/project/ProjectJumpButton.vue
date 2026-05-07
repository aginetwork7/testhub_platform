<template>
  <el-button type="primary" link @click="handleJump">
    <el-icon><Link /></el-icon>
    跳转到 {{ moduleLabel }}
  </el-button>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Link } from '@element-plus/icons-vue'

const props = defineProps({
  moduleType: {
    type: String,
    required: true
  },
  metaProjectId: {
    type: [String, Number],
    default: null
  },
  childProjectId: {
    type: [String, Number],
    default: null
  }
})

const router = useRouter()

const moduleLabel = computed(() => {
  const labels = { AI: 'AI用例生成', AI_TEST: 'AI智能测试', API: 'API测试', UI: 'UI自动化', APP: 'APP自动化' }
  return labels[props.moduleType] || props.moduleType
})

const moduleRoutes = {
  AI: '/ai-generation/projects',
  AI_TEST: '/ai-intelligent-mode/projects',
  API: '/api-testing/projects',
  UI: '/ui-automation/projects',
  APP: '/app-automation/projects'
}

const handleJump = () => {
  const baseRoute = moduleRoutes[props.moduleType]
  if (baseRoute) {
    if (props.childProjectId) {
      router.push({
        path: baseRoute,
        query: { projectId: props.childProjectId }
      })
    } else {
      router.push(baseRoute)
    }
  }
}
</script>
