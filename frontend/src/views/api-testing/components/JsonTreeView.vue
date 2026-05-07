<template>
  <div class="json-tree-view">
    <div class="json-tree-toolbar">
      <el-input
        v-model="searchKeyword"
        :placeholder="$t('apiTesting.response.searchPlaceholder')"
        size="small"
        clearable
        prefix-icon="Search"
        class="search-input"
      />
      <el-button-group>
        <el-button size="small" @click="expandAll">{{ $t('apiTesting.response.expandAll') }}</el-button>
        <el-button size="small" @click="collapseAll">{{ $t('apiTesting.response.collapseAll') }}</el-button>
      </el-button-group>
    </div>
    <div class="json-tree-content" ref="treeContainer">
      <tree-node
        :data="data"
        :path="'$'"
        :depth="0"
        :expanded-keys="expandedKeys"
        :search-keyword="searchKeyword"
        @toggle="toggleNode"
        @copy-path="copyPath"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, defineComponent, h } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  data: {
    type: [Object, Array, String, Number, Boolean],
    default: null
  }
})

const emit = defineEmits(['select-path'])

const searchKeyword = ref('')
const expandedKeys = ref(new Set())
const treeContainer = ref(null)

// 初始展开前两层
function initExpand(data, path, depth) {
  if (depth >= 2) return
  if (data && typeof data === 'object') {
    expandedKeys.value.add(path)
    if (Array.isArray(data)) {
      data.forEach((_, i) => initExpand(data[i], `${path}[${i}]`, depth + 1))
    } else {
      Object.keys(data).forEach(key => initExpand(data[key], `${path}.${key}`, depth + 1))
    }
  }
}

watch(() => props.data, (val) => {
  expandedKeys.value = new Set()
  if (val) initExpand(val, '$', 0)
}, { immediate: true })

function toggleNode(path) {
  if (expandedKeys.value.has(path)) {
    expandedKeys.value.delete(path)
  } else {
    expandedKeys.value.add(path)
  }
  expandedKeys.value = new Set(expandedKeys.value)
}

function expandAll() {
  function walk(data, path) {
    if (data && typeof data === 'object') {
      expandedKeys.value.add(path)
      if (Array.isArray(data)) {
        data.forEach((item, i) => walk(item, `${path}[${i}]`))
      } else {
        Object.keys(data).forEach(key => walk(data[key], `${path}.${key}`))
      }
    }
  }
  expandedKeys.value = new Set()
  walk(props.data, '$')
  expandedKeys.value = new Set(expandedKeys.value)
}

function collapseAll() {
  expandedKeys.value = new Set()
}

function copyPath(path) {
  navigator.clipboard.writeText(path)
  ElMessage.success(t('apiTesting.response.pathCopied'))
  emit('select-path', path)
}

// TreeNode 递归子组件
const TreeNode = defineComponent({
  name: 'TreeNode',
  props: {
    data: { default: null },
    path: { type: String, required: true },
    depth: { type: Number, default: 0 },
    keyName: { type: String, default: '' },
    expandedKeys: { type: Set, required: true },
    searchKeyword: { type: String, default: '' },
    isArrayItem: { type: Boolean, default: false },
    arrayIndex: { type: Number, default: -1 }
  },
  emits: ['toggle', 'copy-path'],
  setup(props, { emit }) {
    const isObject = computed(() => props.data !== null && typeof props.data === 'object')
    const isArray = computed(() => Array.isArray(props.data))
    const isExpanded = computed(() => props.expandedKeys.has(props.path))
    const childCount = computed(() => {
      if (!isObject.value) return 0
      return isArray.value ? props.data.length : Object.keys(props.data).length
    })

    const isMatch = computed(() => {
      if (!props.searchKeyword) return false
      const kw = props.searchKeyword.toLowerCase()
      if (props.keyName && props.keyName.toLowerCase().includes(kw)) return true
      if (!isObject.value && String(props.data).toLowerCase().includes(kw)) return true
      return false
    })

    function getValueClass(value) {
      if (value === null) return 'json-null'
      switch (typeof value) {
        case 'string': return 'json-string'
        case 'number': return 'json-number'
        case 'boolean': return 'json-boolean'
        default: return ''
      }
    }

    function formatValue(value) {
      if (value === null) return 'null'
      if (typeof value === 'string') return `"${value}"`
      return String(value)
    }

    return () => {
      const indent = { paddingLeft: `${props.depth * 18}px` }
      const children = []

      // 构建 label
      const labelParts = []

      // 展开/折叠箭头
      if (isObject.value && childCount.value > 0) {
        labelParts.push(
          h('span', {
            class: ['tree-toggle', isExpanded.value ? 'expanded' : ''],
            onClick: (e) => { e.stopPropagation(); emit('toggle', props.path) }
          }, isExpanded.value ? '▼' : '▶')
        )
      } else {
        labelParts.push(h('span', { class: 'tree-toggle-placeholder' }, ' '))
      }

      // key 名
      if (props.keyName !== '') {
        labelParts.push(
          h('span', {
            class: ['json-key', isMatch.value ? 'highlight' : '']
          }, `"${props.keyName}"`)
        )
        labelParts.push(h('span', { class: 'json-colon' }, ': '))
      } else if (props.isArrayItem) {
        labelParts.push(
          h('span', { class: 'json-index' }, `${props.arrayIndex}`)
        )
        labelParts.push(h('span', { class: 'json-colon' }, ': '))
      }

      // 值
      if (isObject.value) {
        const bracket = isArray.value ? '[' : '{'
        const closeBracket = isArray.value ? ']' : '}'
        labelParts.push(h('span', { class: 'json-bracket' }, bracket))
        if (!isExpanded.value) {
          labelParts.push(
            h('span', { class: 'json-collapsed-info' }, ` ${childCount.value} ${isArray.value ? 'items' : 'keys'} `)
          )
          labelParts.push(h('span', { class: 'json-bracket' }, closeBracket))
        }
      } else {
        labelParts.push(
          h('span', {
            class: [getValueClass(props.data), isMatch.value ? 'highlight' : '']
          }, formatValue(props.data))
        )
      }

      // 复制路径按钮
      labelParts.push(
        h('span', {
          class: 'copy-path-btn',
          title: props.path,
          onClick: (e) => { e.stopPropagation(); emit('copy-path', props.path) }
        }, '📋')
      )

      children.push(
        h('div', { class: 'tree-line', style: indent }, labelParts)
      )

      // 展开的子节点
      if (isObject.value && isExpanded.value) {
        if (isArray.value) {
          props.data.forEach((item, i) => {
            children.push(
              h(TreeNode, {
                data: item,
                path: `${props.path}[${i}]`,
                depth: props.depth + 1,
                keyName: '',
                isArrayItem: true,
                arrayIndex: i,
                expandedKeys: props.expandedKeys,
                searchKeyword: props.searchKeyword,
                onToggle: (p) => emit('toggle', p),
                onCopyPath: (p) => emit('copy-path', p)
              })
            )
          })
        } else {
          Object.keys(props.data).forEach(key => {
            children.push(
              h(TreeNode, {
                data: props.data[key],
                path: `${props.path}.${key}`,
                depth: props.depth + 1,
                keyName: key,
                expandedKeys: props.expandedKeys,
                searchKeyword: props.searchKeyword,
                onToggle: (p) => emit('toggle', p),
                onCopyPath: (p) => emit('copy-path', p)
              })
            )
          })
        }
        // 闭合括号
        children.push(
          h('div', { class: 'tree-line', style: indent },
            h('span', { class: 'json-bracket' }, isArray.value ? ']' : '}')
          )
        )
      }

      return h('div', { class: 'tree-node' }, children)
    }
  }
})
</script>

<style scoped>
.json-tree-view {
  font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.6;
}

.json-tree-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.search-input {
  width: 220px;
}

.json-tree-content {
  max-height: 500px;
  overflow: auto;
  padding: 8px;
  background: #fafafa;
  border-radius: 4px;
  border: 1px solid #ebeef5;
}

.tree-line {
  display: flex;
  align-items: center;
  white-space: nowrap;
  cursor: default;
  min-height: 22px;
}

.tree-line:hover {
  background: #f0f7ff;
  border-radius: 2px;
}

.tree-toggle {
  display: inline-block;
  width: 14px;
  cursor: pointer;
  color: #909399;
  font-size: 10px;
  user-select: none;
  flex-shrink: 0;
  text-align: center;
  margin-right: 4px;
}

.tree-toggle:hover {
  color: #409eff;
}

.tree-toggle-placeholder {
  display: inline-block;
  width: 14px;
  margin-right: 4px;
  flex-shrink: 0;
}

.json-key {
  color: #268bd2;
}

.json-index {
  color: #6c757d;
  font-size: 12px;
}

.json-colon {
  color: #333;
  margin-right: 4px;
}

.json-string {
  color: #2aa198;
}

.json-number {
  color: #d33682;
}

.json-boolean {
  color: #cb4b16;
}

.json-null {
  color: #93a1a1;
  font-style: italic;
}

.json-bracket {
  color: #586e75;
  font-weight: bold;
}

.json-collapsed-info {
  color: #93a1a1;
  font-size: 11px;
  font-style: italic;
}

.highlight {
  background: #fff3cd;
  border-radius: 2px;
  padding: 0 2px;
}

.copy-path-btn {
  margin-left: 6px;
  cursor: pointer;
  opacity: 0;
  font-size: 12px;
  transition: opacity 0.15s;
}

.tree-line:hover .copy-path-btn {
  opacity: 0.6;
}

.copy-path-btn:hover {
  opacity: 1 !important;
}
</style>
