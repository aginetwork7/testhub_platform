<template>
  <el-form
    ref="formRef"
    :model="formData"
    :rules="mergedRules"
    :label-width="labelWidth"
    :validate-on-rule-change="false"
  >
    <el-row :gutter="20">
      <el-col
        v-for="field in commonFields"
        :key="field.field"
        :span="field.colSpan || 24"
      >
        <el-form-item :label="field.label" :prop="field.field">
          <component
            :is="getFieldComponent(field.type)"
            v-model="formData[field.field]"
            v-bind="getFieldProps(field)"
            :placeholder="field.placeholder"
          />
        </el-form-item>
      </el-col>
    </el-row>

    <el-divider v-if="moduleFields.length">
      <el-icon><Folder /></el-icon>
      {{ moduleLabel }} 配置
    </el-divider>

    <el-row :gutter="20">
      <el-col
        v-for="field in moduleFields"
        :key="field.field"
        :span="field.colSpan || 24"
      >
        <el-form-item :label="field.label" :prop="`module_config.${field.field}`">
          <component
            :is="getFieldComponent(field.type)"
            v-model="formData.module_config[field.field]"
            v-bind="getFieldProps(field)"
            :placeholder="field.placeholder"
          />
        </el-form-item>
      </el-col>
    </el-row>
  </el-form>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { PROJECT_FORM_CONFIGS, getModuleLabel } from '@/utils/project-form-config'
import { Folder } from '@element-plus/icons-vue'

const props = defineProps({
  projectType: {
    type: String,
    required: true,
    validator: (v) => typeof v === 'string' && ['API', 'UI', 'APP'].includes(v)
  },
  modelValue: {
    type: Object,
    default: () => ({})
  },
  labelWidth: {
    type: String,
    default: '120px'
  }
})

const emit = defineEmits(['update:modelValue'])

const formRef = ref(null)

const commonFields = computed(() => PROJECT_FORM_CONFIGS.common || [])

const moduleFields = computed(() => PROJECT_FORM_CONFIGS[props.projectType] || [])

const moduleLabel = computed(() => getModuleLabel(props.projectType))

const formData = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

watch(() => props.modelValue, (newVal) => {
  if (!newVal.module_config) {
    emit('update:modelValue', { ...newVal, module_config: {} })
  }
}, { immediate: true })

const mergedRules = computed(() => {
  const rules = {}

  commonFields.value.forEach(field => {
    if (field.rules && field.rules.length) {
      rules[field.field] = field.rules
    }
  })

  moduleFields.value.forEach(field => {
    if (field.rules && field.rules.length) {
      rules[`module_config.${field.field}`] = field.rules
    }
  })

  return rules
})

const getFieldComponent = (type) => {
  const componentMap = {
    'input': 'el-input',
    'textarea': 'el-input',
    'select': 'el-select',
    'switch': 'el-switch',
    'input-number': 'el-input-number',
    'date-picker': 'el-date-picker'
  }
  return componentMap[type] || 'el-input'
}

const getFieldProps = (field) => {
  const props = {}

  if (field.type === 'textarea') {
    props.type = 'textarea'
    props.rows = 3
  }

  if (field.type === 'select') {
    props.placeholder = '请选择'
    if (field.options) {
      props.options = field.options.map(opt => ({
        label: opt.label,
        value: opt.value
      }))
    }
  }

  if (field.type === 'input-number') {
    if (field.min !== undefined) props.min = field.min
    if (field.max !== undefined) props.max = field.max
    if (field.step) props.step = field.step
  }

  if (field.type === 'switch') {
    props['active-text'] = '是'
    props['inactive-text'] = '否'
  }

  return props
}

const validate = () => {
  return formRef.value?.validate()
}

const clearValidate = () => {
  formRef.value?.clearValidate()
}

defineExpose({
  validate,
  clearValidate
})
</script>
