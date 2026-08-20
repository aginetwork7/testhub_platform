<template>
  <div class="requirement-analysis">
    <div class="page-header">
      <h1>{{ $t('requirementAnalysis.title') }}</h1>
      <p>{{ $t('requirementAnalysis.subtitle') }}</p>
    </div>

    <!-- 配置引导弹出窗口 -->
    <div v-if="showConfigGuide && !checkingConfig" class="modal-overlay" @click.self="showConfigGuide = false" :key="modalKey">
      <div class="guide-config-modal">
      <div class="guide-header">
        <svg class="guide-icon" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">
          <path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z" fill="#f59e0b"/>
          <path d="M464 336a48 48 0 1 0 96 0 48 48 0 1 0-96 0zm72 112h-48c-4.4 0-8 3.6-8 8v272c0 4.4 3.6 8 8 8h48c4.4 0 8-3.6 8-8V456c0-4.4-3.6-8-8-8z" fill="#f59e0b"/>
        </svg>
        <div class="guide-title">
          <h2>{{ $t('configGuide.title') }}</h2>
          <p>{{ $t('configGuide.subtitle') }}</p>
        </div>
      </div>

      <div class="config-groups">
        <!-- 模型配置行 -->
        <div class="config-group">
          <div class="group-label">{{ $t('configGuide.modelConfig') }}</div>
          <div class="config-items-row">
            <div class="config-item-inline" :class="getConfigItemClass('writer_model')">
              <span class="status-symbol" v-html="getStatusSymbol('writer_model')"></span>
              <span class="config-label">{{ $t('configGuide.caseWriter') }}</span>
              <span class="config-name" v-if="configStatus.writer_model.name">{{ configStatus.writer_model.name }}</span>
              <span class="status-text" v-if="!configStatus.writer_model.configured">{{ $t('configGuide.unconfigured') }}</span>
              <span class="status-text warning" v-else-if="!configStatus.writer_model.enabled">{{ $t('configGuide.disabled') }}</span>
            </div>

            <div class="config-item-inline" :class="getConfigItemClass('reviewer_model')">
              <span class="status-symbol" v-html="getStatusSymbol('reviewer_model')"></span>
              <span class="config-label">{{ $t('configGuide.caseReviewer') }}</span>
              <span class="config-name" v-if="configStatus.reviewer_model.name">{{ configStatus.reviewer_model.name }}</span>
              <span class="status-text" v-if="!configStatus.reviewer_model.configured">{{ $t('configGuide.unconfigured') }}</span>
              <span class="status-text warning" v-else-if="!configStatus.reviewer_model.enabled">{{ $t('configGuide.disabled') }}</span>
            </div>
          </div>
        </div>

        <!-- 提示词配置行 -->
        <div class="config-group">
          <div class="group-label">{{ $t('configGuide.promptConfig') }}</div>
          <div class="config-items-row">
            <div class="config-item-inline" :class="getConfigItemClass('writer_prompt')">
              <span class="status-symbol" v-html="getStatusSymbol('writer_prompt')"></span>
              <span class="config-label">{{ $t('configGuide.caseWriter') }}</span>
              <span class="config-name" v-if="configStatus.writer_prompt.name">{{ configStatus.writer_prompt.name }}</span>
              <span class="status-text" v-if="!configStatus.writer_prompt.configured">{{ $t('configGuide.unconfigured') }}</span>
              <span class="status-text warning" v-else-if="!configStatus.writer_prompt.enabled">{{ $t('configGuide.disabled') }}</span>
            </div>

            <div class="config-item-inline" :class="getConfigItemClass('reviewer_prompt')">
              <span class="status-symbol" v-html="getStatusSymbol('reviewer_prompt')"></span>
              <span class="config-label">{{ $t('configGuide.caseReviewer') }}</span>
              <span class="config-name" v-if="configStatus.reviewer_prompt.name">{{ configStatus.reviewer_prompt.name }}</span>
              <span class="status-text" v-if="!configStatus.reviewer_prompt.configured">{{ $t('configGuide.unconfigured') }}</span>
              <span class="status-text warning" v-else-if="!configStatus.reviewer_prompt.enabled">{{ $t('configGuide.disabled') }}</span>
            </div>
          </div>
        </div>

        <!-- 生成行为配置行 -->
        <div class="config-group">
          <div class="group-label">{{ $t('configGuide.generationConfig') }}</div>
          <div class="config-items-row">
            <div class="config-item-inline" :class="getConfigItemClass('generation_config')">
              <span class="status-symbol" v-html="getStatusSymbol('generation_config')"></span>
              <span class="config-label">{{ $t('configGuide.generationSettings') }}</span>
              <span class="config-name" v-if="configStatus.generation_config && configStatus.generation_config.name">{{ configStatus.generation_config.name }}</span>
              <span class="status-text" v-if="!configStatus.generation_config || !configStatus.generation_config.configured">{{ $t('configGuide.unconfigured') }}</span>
            </div>
          </div>
        </div>
      </div>

        <div class="guide-actions">
          <button class="generate-manual-btn" @click="goToConfig">
            {{ $t('configGuide.goToConfig') }}
          </button>
          <div class="skip-action" @click="showConfigGuide = false">
            {{ $t('configGuide.configureLater') }}
          </div>
        </div>
      </div>
    </div>

    <!-- 输出模式选择器 - 全局设置 -->
    <div class="output-mode-section" v-if="!isGenerating && !showResults">
      <div class="output-mode-card">
        <h3>{{ $t('requirementAnalysis.outputModeTitle') }}</h3>
        <p class="mode-section-desc">{{ $t('requirementAnalysis.outputModeDesc') }}</p>
        <div class="output-mode-selector">
          <label class="mode-option" :class="{ active: globalOutputMode === 'stream' }">
            <input type="radio" v-model="globalOutputMode" value="stream">
            <div class="mode-content">
              <div class="mode-title">{{ $t('requirementAnalysis.realtimeStream') }}</div>
              <div class="mode-desc">{{ $t('requirementAnalysis.realtimeStreamDesc') }}</div>
            </div>
          </label>
          <label class="mode-option" :class="{ active: globalOutputMode === 'complete' }">
            <input type="radio" v-model="globalOutputMode" value="complete">
            <div class="mode-content">
              <div class="mode-title">{{ $t('requirementAnalysis.completeOutput') }}</div>
              <div class="mode-desc">{{ $t('requirementAnalysis.completeOutputDesc') }}</div>
            </div>
          </label>
        </div>
      </div>
    </div>

    <div class="main-content">
      <!-- 面板选择器 -->
      <div class="panel-selector" v-if="!isGenerating && !showResults">
        <div class="panel-tabs">
          <div
            class="panel-tab"
            :class="{ active: activePanel === 'manual' }"
            @click="activePanel = 'manual'">
            <div class="panel-icon manual-icon">✏️</div>
            <div class="panel-content-wrapper">
              <div class="panel-label">{{ $t('requirementAnalysis.manualInputTitle') }}</div>
              <div class="panel-desc">{{ $t('requirementAnalysis.manualInputDesc') }}</div>
            </div>
          </div>
          <div
            class="panel-tab"
            :class="{ active: activePanel === 'upload' }"
            @click="activePanel = 'upload'">
            <div class="panel-icon upload-icon">📄</div>
            <div class="panel-content-wrapper">
              <div class="panel-label">{{ $t('requirementAnalysis.uploadTitle') }}</div>
              <div class="panel-desc">{{ $t('requirementAnalysis.uploadDesc') }}</div>
            </div>
          </div>
          <div
            class="panel-tab"
            :class="{ active: activePanel === 'knowledge' }"
            @click="handleKnowledgePanelClick">
            <div class="panel-icon knowledge-icon">📚</div>
            <div class="panel-content-wrapper">
              <div class="panel-label">{{ $t('requirementAnalysis.knowledgeBaseTitle') }}</div>
              <div class="panel-desc">{{ $t('requirementAnalysis.knowledgeBaseDesc') }}</div>
            </div>
          </div>
          <div
            class="panel-tab"
            :class="{ active: activePanel === 'axure' }"
            @click="handleAxurePanelClick">
            <div class="panel-icon axure-icon">🎨</div>
            <div class="panel-content-wrapper">
              <div class="panel-label">{{ $t('requirementAnalysis.axureTitle') }}</div>
              <div class="panel-desc">{{ $t('requirementAnalysis.axureDesc') }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 手动输入需求面板 -->
      <div class="panel-content manual-input-section" v-if="activePanel === 'manual' && !isGenerating && !showResults">
        <div class="panel-card">
          <h2>{{ $t('requirementAnalysis.manualInputTitle') }}</h2>
          <div class="input-form">
            <div class="form-group">
              <label>{{ $t('requirementAnalysis.requirementTitle') }} <span class="required">*</span></label>
              <input
                v-model="manualInput.title"
                type="text"
                class="form-input"
                :placeholder="$t('requirementAnalysis.titlePlaceholder')">
            </div>

            <div class="form-group">
              <label>{{ $t('requirementAnalysis.requirementDescription') }} <span class="required">*</span></label>
              <textarea
                v-model="manualInput.description"
                class="form-textarea"
                rows="8"
                :placeholder="$t('requirementAnalysis.descriptionPlaceholder')"></textarea>
              <div class="char-count">{{ manualInput.description.length }}/2000</div>
            </div>

            <div class="form-group">
              <label>{{ $t('requirementAnalysis.associatedProject') }}</label>
              <select v-model="manualInput.selectedProject" class="form-select">
                <option value="">{{ $t('requirementAnalysis.selectProject') }}</option>
                <option v-for="project in projects" :key="project.id" :value="project.id">
                  {{ project.name }}
                </option>
              </select>
            </div>

            <button
              class="generate-manual-btn"
              @click="generateFromManualInput"
              :disabled="!canGenerateManual || isGenerating">
              <span v-if="isGenerating">{{ $t('requirementAnalysis.generating') }}</span>
              <span v-else>{{ $t('requirementAnalysis.generateButton') }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 上传需求文档面板 -->
      <div class="panel-content upload-section" v-if="activePanel === 'upload' && !isGenerating && !showResults">
        <div class="panel-card">
          <h2>{{ $t('requirementAnalysis.uploadTitle') }}</h2>
          <div class="upload-area"
               @dragover.prevent
               @drop="handleDrop"
               :class="{ 'drag-over': isDragOver }"
               @dragenter="isDragOver = true"
               @dragleave="isDragOver = false">
            <div v-if="!selectedFile" class="upload-placeholder">
              <i class="upload-icon">📁</i>
              <p>{{ $t('requirementAnalysis.dragDropText') }}</p>
              <p class="upload-hint">{{ $t('requirementAnalysis.supportedFormats') }}</p>
              <input
                type="file"
                ref="fileInput"
                @change="handleFileSelect"
                accept=".pdf,.doc,.docx,.txt,.md"
                style="display: none;">
              <button class="select-file-btn" @click="$refs.fileInput.click()">
                {{ $t('requirementAnalysis.selectFile') }}
              </button>
            </div>

            <div v-else class="file-selected">
              <div class="file-info">
                <i class="file-icon">📄</i>
                <div class="file-details">
                  <p class="file-name">{{ selectedFile.name }}</p>
                  <p class="file-size">{{ formatFileSize(selectedFile.size) }}</p>
                </div>
                <button class="remove-file" @click="removeFile">❌</button>
              </div>
            </div>
          </div>

          <div v-if="selectedFile" class="document-info">
            <div class="form-group">
              <label>{{ $t('requirementAnalysis.documentTitle') }}</label>
              <input
                v-model="documentTitle"
                type="text"
                class="form-input"
                :placeholder="$t('requirementAnalysis.documentPlaceholder')">
            </div>

            <div class="form-group">
              <label>{{ $t('requirementAnalysis.associatedProject') }}</label>
              <select v-model="selectedProject" class="form-select">
                <option value="">{{ $t('requirementAnalysis.selectProject') }}</option>
                <option v-for="project in projects" :key="project.id" :value="project.id">
                  {{ project.name }}
                </option>
              </select>
            </div>

            <button
              class="generate-btn"
              @click="generateFromDocument"
              :disabled="!documentTitle || isGenerating">
              <span v-if="isGenerating">{{ $t('requirementAnalysis.generating') }}</span>
              <span v-else>{{ $t('requirementAnalysis.generateButton') }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 知识库需求面板 -->
      <div class="panel-content knowledge-section" v-if="activePanel === 'knowledge' && !isGenerating && !showResults">
        <div class="panel-card">
          <h2>{{ $t('requirementAnalysis.knowledgeBaseTitle') }}</h2>

          <div class="knowledge-search-form">
            <div class="form-row">
              <div class="form-group">
                <label>{{ $t('requirementAnalysis.selectKnowledgeBase') }}</label>
                <select v-model="selectedKnowledgeBase" class="form-select">
                  <option value="">{{ $t('requirementAnalysis.selectKnowledgeBasePlaceholder') }}</option>
                  <option v-for="kb in knowledgeBaseList" :key="kb.id" :value="kb.id">
                    {{ kb.name }}
                  </option>
                </select>
              </div>
              <div class="form-group">
                <label>{{ $t('requirementAnalysis.associatedProject') }}</label>
                <select v-model="selectedKnowledgeProject" class="form-select">
                  <option value="">{{ $t('requirementAnalysis.selectProject') }}</option>
                  <option v-for="project in projects" :key="project.id" :value="project.id">
                    {{ project.name }}
                  </option>
                </select>
              </div>
            </div>

            <!-- 检索类型选择 -->
            <div class="search-type-row">
              <label class="search-type-label">{{ $t('knowledgeBase.searchType') }}:</label>
              <div class="search-type-buttons">
                <button
                  class="search-type-btn"
                  :class="{ active: knowledgeSearchType === 'hybrid' }"
                  @click="knowledgeSearchType = 'hybrid'">
                  {{ $t('knowledgeBase.hybridSearchType') }}
                </button>
                <button
                  class="search-type-btn"
                  :class="{ active: knowledgeSearchType === 'semantic' }"
                  @click="knowledgeSearchType = 'semantic'">
                  {{ $t('knowledgeBase.semanticSearchType') }}
                </button>
                <button
                  class="search-type-btn"
                  :class="{ active: knowledgeSearchType === 'keyword' }"
                  @click="knowledgeSearchType = 'keyword'">
                  {{ $t('knowledgeBase.keywordSearchType') }}
                </button>
              </div>
            </div>

            <!-- 检索参数 -->
            <div class="search-params">
              <div class="param-item">
                <span class="param-label">{{ $t('knowledgeBase.similarityThreshold') }}:</span>
                <input
                  type="range"
                  v-model.number="knowledgeSearchParams.similarityThreshold"
                  min="0"
                  max="1"
                  step="0.05"
                  class="param-slider">
                <span class="param-value">{{ (knowledgeSearchParams.similarityThreshold * 100).toFixed(0) }}%</span>
              </div>
              <div class="param-item">
                <span class="param-label">{{ $t('knowledgeBase.topK') }}:</span>
                <select v-model.number="knowledgeSearchParams.topK" class="param-select">
                  <option v-for="i in 10" :key="i" :value="i">{{ i }}</option>
                </select>
              </div>
              <div class="param-item param-item-wide" v-if="knowledgeSearchType === 'hybrid'">
                <span class="param-label">{{ $t('knowledgeBase.keywordWeight') }}</span>
                <input
                  type="range"
                  v-model.number="knowledgeSearchParams.keywordWeight"
                  min="0"
                  max="1"
                  step="0.1"
                  class="param-slider">
                <span class="param-value">{{ (knowledgeSearchParams.keywordWeight * 100).toFixed(0) }}%</span>
              </div>
            </div>

            <!-- 检索内容输入框 -->
            <div class="form-group">
              <label>{{ $t('requirementAnalysis.searchQuery') }}</label>
              <div class="search-input-row">
                <input
                  v-model="knowledgeSearchQuery"
                  type="text"
                  class="form-input"
                  :placeholder="$t('requirementAnalysis.searchQueryPlaceholder')"
                  @keyup.enter="handleKnowledgeSearch">
                <button
                  class="search-btn"
                  @click="handleKnowledgeSearch"
                  :disabled="isKnowledgeSearching || !selectedKnowledgeBase">
                  {{ isKnowledgeSearching ? $t('requirementAnalysis.searching') : $t('knowledgeBase.search') }}
                </button>
              </div>
            </div>
          </div>

          <!-- 检索结果 -->
          <div class="search-results" v-if="knowledgeSearchResults.length > 0">
            <h3>{{ $t('requirementAnalysis.searchResults') }} ({{ knowledgeSearchResults.length }})</h3>
            <div class="result-list">
              <div v-for="(result, index) in knowledgeSearchResults" :key="index" class="result-item">
                <div class="result-header">
                  <span class="result-index">#{{ index + 1 }}</span>
                  <span class="result-score">{{ $t('knowledgeBase.similarity') }}: {{ ((result.similarity || 0) * 100).toFixed(1) }}%</span>
                </div>
                <div class="result-content">{{ result.content }}</div>
                <div class="result-meta" v-if="result.document_title">
                  <span>{{ $t('requirementAnalysis.sourceDocument') }}: {{ result.document_title }}</span>
                </div>
              </div>
            </div>
            <button
              class="generate-knowledge-btn"
              @click="generateFromKnowledge"
              :disabled="isGenerating">
              <span v-if="isGenerating">{{ $t('requirementAnalysis.generating') }}</span>
              <span v-else>{{ $t('requirementAnalysis.generateFromKnowledge') }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Axure解析需求面板 -->
      <div class="panel-content axure-section" v-if="activePanel === 'axure' && !isGenerating && !showResults">
        <div class="panel-card">
          <h2>{{ $t('requirementAnalysis.axureTitle') }}</h2>

          <div class="axure-form">
            <div class="form-group">
              <label>{{ $t('requirementAnalysis.axureOnlineLink') }}</label>
              <div class="axure-input-row">
                <input
                  v-model="axureUrl"
                  type="text"
                  class="form-input"
                  :placeholder="$t('requirementAnalysis.axureUrlPlaceholder')">
                <button
                  class="parse-btn"
                  @click="parseAxureUrl"
                  :disabled="isAxureParsing || !axureUrl">
                  {{ isAxureParsing ? $t('requirementAnalysis.parsing') : $t('requirementAnalysis.confirmParse') }}
                </button>
              </div>
            </div>

            <!-- 内容类型选择和AI结构化 -->
            <div class="form-group">
              <div class="inline-options">
                <label class="radio-label">
                  <input type="radio" v-model="axureContentType" value="full">
                  {{ $t('requirementAnalysis.fullContent') }}
                </label>
                <label class="radio-label">
                  <input type="radio" v-model="axureContentType" value="incremental">
                  {{ $t('requirementAnalysis.incrementalContent') }}
                </label>
                <label class="checkbox-label">
                  <input type="checkbox" v-model="axureUseAiRefine">
                  {{ $t('requirementAnalysis.useAiRefine') }}
                </label>
              </div>
            </div>

            <div class="form-group">
              <label>{{ $t('requirementAnalysis.associatedProject') }}</label>
              <select v-model="selectedAxureProject" class="form-select">
                <option value="">{{ $t('requirementAnalysis.selectProject') }}</option>
                <option v-for="project in projects" :key="project.id" :value="project.id">
                  {{ project.name }}
                </option>
              </select>
            </div>
          </div>

          <!-- 解析结果展示 -->
          <div class="axure-result" v-if="axureContent || axureIncrementalContent">
            <h3>{{ $t('requirementAnalysis.parseResult') }}</h3>

            <!-- 标签页切换 - 根据选择的内容类型显示对应标签 -->
            <div class="content-tabs">
              <button
                v-if="axureContentType === 'full'"
                class="content-tab active">
                {{ $t('requirementAnalysis.fullContent') }}
                <span class="content-length">({{ axureContent ? axureContent.length : 0 }} {{ $t('requirementAnalysis.characters') }})</span>
              </button>
              <button
                v-if="axureContentType === 'incremental'"
                class="content-tab active">
                {{ $t('requirementAnalysis.incrementalContent') }}
                <span class="content-length">({{ axureIncrementalContent ? axureIncrementalContent.length : 0 }} {{ $t('requirementAnalysis.characters') }})</span>
              </button>
              <button
                v-if="axureMermaidCode"
                class="content-tab"
                :class="{ active: activeTab === 'flowchart' }"
                @click="activeTab = 'flowchart'">
                {{ $t('requirementAnalysis.flowchartContent') || '流程图' }}
                <span class="content-length">(Mermaid)</span>
              </button>
            </div>

            <!-- 内容展示区域 - 可编辑的预览模式 -->
            <div class="content-display">
              <div v-if="axureContentType === 'full' && activeTab !== 'flowchart'" class="full-content">
                <div
                  v-if="axureContent"
                  class="markdown-preview editable-preview"
                  contenteditable="true"
                  @blur="onAxureContentBlur($event, 'full')"
                  v-html="formatMarkdown(axureContent)">
                </div>
                <div v-else class="no-content">
                  {{ $t('requirementAnalysis.noIncrementalContent') }}
                </div>
              </div>
              <div v-else-if="axureContentType === 'incremental' && activeTab !== 'flowchart'" class="incremental-content">
                <div
                  v-if="axureIncrementalContent"
                  class="markdown-preview editable-preview"
                  contenteditable="true"
                  @blur="onAxureContentBlur($event, 'incremental')"
                  v-html="formatMarkdown(axureIncrementalContent)">
                </div>
                <div v-else class="no-content">
                  {{ $t('requirementAnalysis.noIncrementalContent') }}
                </div>
              </div>
              <div v-if="activeTab === 'flowchart'" class="flowchart-content">
                <div v-if="axureMermaidCode" class="mermaid-container">
                  <div class="mermaid" v-html="renderedMermaid"></div>
                  <div class="mermaid-code">
                    <h4>Mermaid 代码</h4>
                    <pre>{{ axureMermaidCode }}</pre>
                  </div>
                </div>
                <div v-else class="no-content">
                  {{ $t('requirementAnalysis.noFlowchartContent') || '未检测到流程图' }}
                </div>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="axure-actions">
              <button
                class="generate-axure-btn"
                @click="generateFromAxure"
                :disabled="isGenerating || isAxureParsing">
                <span v-if="isGenerating">{{ $t('requirementAnalysis.generating') }}</span>
                <span v-else>{{ $t('requirementAnalysis.generateFromAxure') }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 生成进度和结果 -->
      <div v-if="isGenerating || showResults" class="generation-progress">
        <div class="progress-card">
          <h3>
            {{ $t('requirementAnalysis.aiGeneratingTitle') }}
            <span class="current-mode-badge">
              ({{ globalOutputMode === 'stream' ? $t('requirementAnalysis.realtimeStream') : $t('requirementAnalysis.completeOutput') }})
            </span>
          </h3>
          <div class="progress-info">
            <div class="progress-item">
              <span class="label">{{ $t('requirementAnalysis.taskId') }}</span>
              <span class="value">{{ currentTaskId || $t('requirementAnalysis.preparing') }}</span>
            </div>
            <div class="progress-item">
              <span class="label">{{ $t('requirementAnalysis.currentStatus') }}</span>
              <span class="value">{{ showResults ? $t('requirementAnalysis.generationComplete') : progressText }}</span>
            </div>
          </div>

          <!-- 流式内容实时显示区域 -->
          <div v-if="streamedContent" class="stream-content-display">
            <div class="stream-header">
              <span class="stream-title">{{ $t('requirementAnalysis.realtimeGeneratedContent') }}</span>
              <span class="stream-status">{{ $t('requirementAnalysis.characters', { count: streamedContent.length }) }}</span>
            </div>
            <div class="stream-content" v-html="formatMarkdown(streamedContent)"></div>
          </div>

          <!-- 评审内容显示区域 -->
          <div v-if="streamedReviewContent" class="stream-content-display" style="margin-top: 15px;">
            <div class="stream-header">
              <span class="stream-title">{{ $t('requirementAnalysis.aiReviewComments') }}</span>
              <span class="stream-status">{{ $t('requirementAnalysis.characters', { count: streamedReviewContent.length }) }}</span>
            </div>
            <div class="stream-content" v-html="formatMarkdown(streamedReviewContent)"></div>
          </div>

          <!-- 最终版用例显示区域 -->
          <div v-if="finalTestCases" class="stream-content-display" style="margin-top: 15px;">
            <div class="stream-header">
              <span class="stream-title">
                {{ $t('requirementAnalysis.finalVersionTestCases') }}
                <span v-if="isGenerating" class="streaming-indicator">{{ $t('requirementAnalysis.generating') }}</span>
              </span>
              <span class="stream-status">{{ $t('requirementAnalysis.characters', { count: finalTestCases.length }) }}</span>
            </div>
            <div class="stream-content final-testcases" v-html="formatMarkdown(finalTestCases)"></div>
          </div>

          <div class="progress-steps">
            <div class="step" :class="{ active: currentStep >= 1 }">
              <span class="step-number">1</span>
              <span class="step-text">{{ $t('requirementAnalysis.stepAnalysis') }}</span>
            </div>
            <div class="step" :class="{ active: currentStep >= 2 }">
              <span class="step-number">2</span>
              <span class="step-text">{{ $t('requirementAnalysis.stepWriting') }}</span>
            </div>
            <div v-if="showReviewStep" class="step" :class="{ active: currentStep >= 3 }">
              <span class="step-number">3</span>
              <span class="step-text">{{ $t('requirementAnalysis.stepReview') }}</span>
            </div>
            <div class="step" :class="{ active: currentStep >= (showReviewStep ? 4 : 3) }">
              <span class="step-number">{{ showReviewStep ? 4 : 3 }}</span>
              <span class="step-text">{{ $t('requirementAnalysis.stepComplete') }}</span>
            </div>
          </div>

          <!-- 任务完成后的操作按钮 -->
          <div v-if="showResults" class="completion-actions">
            <button class="download-btn" @click="downloadTestCases">
              <span>📥 {{ $t('requirementAnalysis.downloadExcel') }}</span>
            </button>
            <button class="save-btn" @click="saveToTestCaseRecords">
              <span>💾 {{ $t('requirementAnalysis.saveToRecords') }}</span>
            </button>
            <button class="new-generation-btn" @click="resetGeneration">
              <span>📝 {{ $t('requirementAnalysis.newGeneration') }}</span>
            </button>
          </div>
          <button v-else class="cancel-generation-btn" @click="cancelGeneration">
            {{ $t('requirementAnalysis.cancelGeneration') }}
          </button>
        </div>
      </div>

      <!-- 旧的生成结果区域已废弃，保留用于兼容 -->
      <!-- 现在使用流式显示区域 + 最终版用例区域 -->
      <div v-if="false && showResults && generationResult" class="generation-result">
        <div class="result-header">
          <h2>{{ $t('requirementAnalysis.generationComplete') }}</h2>
          <div class="result-summary">
            <span class="summary-item">
              {{ $t('requirementAnalysis.summaryTaskId', { taskId: generationResult.task_id }) }}
            </span>
            <span class="summary-item">
              {{ $t('requirementAnalysis.summaryGenerationTime', { time: formatDateTime(generationResult.completed_at) }) }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import api from '@/utils/api'
import { ElMessage } from 'element-plus'
import * as XLSX from 'xlsx'
import { useUserStore } from '@/stores/user'
import { hybridSearch, semanticSearch, getKnowledgeBaseList } from '@/api/knowledge-base'
import { marked } from 'marked'

export default {
  name: 'RequirementAnalysisView',
  data() {
    return {
      // 面板选择
      activePanel: 'manual', // manual, upload, knowledge, axure

      // 全局输出模式设置
      globalOutputMode: 'stream',  // 默认使用流式输出

      // 手动输入需求
      manualInput: {
        title: '',
        description: '',
        selectedProject: ''
      },

      // 文件上传
      selectedFile: null,
      documentTitle: '',
      selectedProject: '',
      projects: [],
      isDragOver: false,

      // 知识库需求相关
      knowledgeBaseList: [],
      selectedKnowledgeBase: '',
      knowledgeSearchQuery: '',
      knowledgeSearchResults: [],
      knowledgeSearchType: 'hybrid', // hybrid, semantic, keyword
      knowledgeSearchParams: {
        topK: 5,
        similarityThreshold: 0.5,
        keywordWeight: 0.7
      },
      isKnowledgeSearching: false,
      selectedKnowledgeProject: '',

      // Axure解析相关
      axureUrl: '',
      axureContent: '',
      axureIncrementalContent: '',
      axureMermaidCode: '',
      renderedMermaid: '',
      isAxureParsing: false,
      selectedAxureProject: '',
      axureUseAiRefine: true,
      axureContentType: 'full',  // 内容类型：'full' 或 'incremental'

      // 生成状态
      isGenerating: false,
      currentTaskId: null,
      progressText: '',
      currentStep: 0,
      pollInterval: null,
      eventSource: null,  // SSE连接
      streamedContent: '',  // 流式接收的内容
      streamedReviewContent: '',  // 流式接收的评审内容
      finalTestCases: '',  // 最终版用例
      hasShownCompletionMessage: false,  // 是否已经显示过完成消息
      showReviewStep: true,  // 是否显示评审步骤（根据生成配置决定）

      // 生成结果
      showResults: false,
      generationResult: null,

      // AI配置状态
      configStatus: {
        overall_status: 'unknown',
        message: '',
        writer_model: {
          configured: false,
          enabled: false,
          name: null,
          provider: null,
          id: null,
          required: true
        },
        writer_prompt: {
          configured: false,
          enabled: false,
          name: null,
          id: null,
          required: true
        },
        reviewer_model: {
          configured: false,
          enabled: false,
          name: null,
          id: null,
          required: true
        },
        reviewer_prompt: {
          configured: false,
          enabled: false,
          name: null,
          id: null,
          required: true
        },
        generation_config: {
          configured: false,
          enabled: false,
          name: null,
          id: null,
          required: true,
          default_output_mode: null
        }
      },
      showConfigGuide: false,
      checkingConfig: true,
      modalKey: 0  // 用于强制重新渲染弹窗
    }
  },

  computed: {
    canGenerateManual() {
      return this.manualInput.title.trim() &&
             this.manualInput.description.trim() &&
             this.manualInput.description.length <= 2000
    }
  },

  mounted() {
    this.progressText = this.$t('requirementAnalysis.preparing')
    this.loadProjects()
    this.loadKnowledgeBases()
    this.checkConfigStatus()
  },

  activated() {
    // 当从其他页面返回时，重新检查配置状态
    // 立即隐藏弹窗和遮罩层，强制重新渲染
    this.showConfigGuide = false
    this.checkingConfig = true
    this.modalKey += 1  // 改变key值，强制重新渲染弹窗

    // 延迟检查配置，确保页面完全加载后再显示弹窗
    setTimeout(async () => {
      await this.checkConfigStatus()
    }, 200)
  },

  beforeUnmount() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval)
    }
    // 停止token自动刷新定时器
    const userStore = useUserStore()
    userStore.stopAutoRefresh()
  },

  methods: {
    async checkKbConfigAndSwitchPanel(panelName) {
      try {
        const response = await api.get('/knowledge-base/check_config/')
        const config = response.data
        
        // 如果是 Axure 面板，主要依赖 Refiner 模型（如果有使用AI结构化）和配置情况
        // 这里为了统一和严格，我们在进入这两个依赖大模型的面板时都做统一的完整性校验
        if (config.has_embedding && config.has_vision && config.has_refiner) {
          this.activePanel = panelName
        } else {
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
          
          this.$confirm(
            htmlContent,
            '配置缺失提示',
            {
              confirmButtonText: '前往配置',
              cancelButtonText: '取消',
              type: 'warning',
              dangerouslyUseHTMLString: true,
              customClass: 'kb-config-warning-dialog'
            }
          ).then(() => {
            this.$router.push('/configuration/knowledge-base')
          }).catch(() => {
            // 用户点击取消，不切换面板
          })
        }
      } catch (error) {
        console.error('检查知识库配置失败:', error)
        this.activePanel = panelName // 接口失败时降级允许进入
      }
    },

    async handleKnowledgePanelClick() {
      await this.checkKbConfigAndSwitchPanel('knowledge')
    },

    async handleAxurePanelClick() {
      await this.checkKbConfigAndSwitchPanel('axure')
    },

    async loadProjects() {
      try {
        const response = await api.get('/projects/')
        this.projects = response.data.results || response.data
      } catch (error) {
        console.error(this.$t('requirementAnalysis.loadProjectsFailed'), error)
      }
    },

    async loadKnowledgeBases() {
      try {
        const response = await getKnowledgeBaseList({ status: 'active' })
        this.knowledgeBaseList = response.data.results || response.data
      } catch (error) {
        console.error('Failed to load knowledge bases:', error)
      }
    },

    async handleKnowledgeSearch() {
      if (!this.knowledgeSearchQuery.trim()) {
        ElMessage.warning(this.$t('knowledgeBase.searchQueryRequired'))
        return
      }
      if (!this.selectedKnowledgeBase) {
        ElMessage.warning(this.$t('requirementAnalysis.selectKnowledgeBase'))
        return
      }

      this.isKnowledgeSearching = true
      this.knowledgeSearchResults = []

      try {
        let response
        if (this.knowledgeSearchType === 'hybrid') {
          response = await hybridSearch(this.selectedKnowledgeBase, {
            query: this.knowledgeSearchQuery,
            top_k: this.knowledgeSearchParams.topK,
            similarity_threshold: this.knowledgeSearchParams.similarityThreshold,
            keyword_weight: this.knowledgeSearchParams.keywordWeight
          })
        } else if (this.knowledgeSearchType === 'semantic') {
          response = await semanticSearch(this.selectedKnowledgeBase, {
            query: this.knowledgeSearchQuery,
            top_k: this.knowledgeSearchParams.topK,
            similarity_threshold: this.knowledgeSearchParams.similarityThreshold
          })
        } else {
          // keyword search - use hybrid search with keyword_weight=1
          response = await hybridSearch(this.selectedKnowledgeBase, {
            query: this.knowledgeSearchQuery,
            top_k: this.knowledgeSearchParams.topK,
            similarity_threshold: this.knowledgeSearchParams.similarityThreshold,
            keyword_weight: 1.0
          })
        }
        this.knowledgeSearchResults = response.data.results || []
        if (this.knowledgeSearchResults.length === 0) {
          ElMessage.info(this.$t('knowledgeBase.noResults'))
        }
      } catch (error) {
        console.error('Knowledge search failed:', error)
        ElMessage.error(this.$t('knowledgeBase.searchFailed'))
      } finally {
        this.isKnowledgeSearching = false
      }
    },

    async generateFromKnowledge() {
      if (this.knowledgeSearchResults.length === 0) {
        ElMessage.error(this.$t('requirementAnalysis.noSearchResults'))
        return
      }

      // 合并检索结果作为需求文本
      const requirementText = this.knowledgeSearchResults.map((result, index) => {
        return `【需求片段 ${index + 1}】\n${result.content}`
      }).join('\n\n')

      const title = this.$t('requirementAnalysis.knowledgeBaseRequirement')

      await this.startGeneration(
        title,
        requirementText,
        this.selectedKnowledgeProject,
        this.globalOutputMode
      )
    },

    async parseAxureUrl() {
      if (!this.axureUrl) {
        ElMessage.warning(this.$t('requirementAnalysis.pleaseEnterAxureUrl'))
        return
      }

      this.isAxureParsing = true
      this.axureContent = ''
      this.axureMermaidCode = ''

      try {
        console.log('开始解析Axure URL:', this.axureUrl)
        // Axure 解析需要较长时间（可能超过 2 分钟），设置 5 分钟超时
        const response = await api.post('/requirement-analysis/fetch-axure-url/', {
          url: this.axureUrl,
          use_ai_refine: this.axureUseAiRefine,
          content_type: this.axureContentType
        }, {
          timeout: 300000  // 5 分钟超时
        })

        console.log('Axure解析完整响应:', JSON.stringify(response.data, null, 2))
        console.log('success状态:', response.data.success)

        if (response.data.success) {
          // 根据content_type存储对应内容
          const returnedContentType = response.data.content_type || this.axureContentType
          if (returnedContentType === 'incremental') {
            this.axureIncrementalContent = response.data.incremental_content || ''
            this.axureContent = ''  // 清空全量内容，避免显示错误
            console.log('增量内容长度:', this.axureIncrementalContent.length)
          } else {
            this.axureContent = response.data.full_content || ''
            this.axureIncrementalContent = ''  // 清空增量内容
            console.log('全量内容长度:', this.axureContent.length)
          }

          // 处理流程图 Mermaid 代码
          if (response.data.mermaid_code) {
            this.axureMermaidCode = response.data.mermaid_code
            console.log('检测到流程图，Mermaid代码长度:', this.axureMermaidCode.length)
            // 渲染 Mermaid
            this.$nextTick(() => {
              this.renderMermaid()
            })
          } else {
            this.axureMermaidCode = ''
          }
          ElMessage.success(response.data.message || this.$t('requirementAnalysis.parseSuccess'))
        } else {
          console.error('解析失败 - success为false:', response.data.error)
          ElMessage.error(response.data.error || this.$t('requirementAnalysis.parseFailed'))
        }
      } catch (error) {
        console.error('Axure解析请求异常:', error)
        console.error('错误详情:', error.response ? error.response.data : error.message)
        if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
          ElMessage.error('解析超时，Axure 原型页面加载较慢，请稍后重试')
        } else {
          ElMessage.error(this.$t('requirementAnalysis.parseFailed') + ': ' + (error.message || '未知错误'))
        }
      } finally {
        this.isAxureParsing = false
        console.log('解析结束, axureContent最终值:', this.axureContent ? this.axureContent.length + '字符' : '空')
      }
    },

    renderMermaid() {
      // 渲染 Mermaid 流程图
      if (!this.axureMermaidCode) {
        this.renderedMermaid = ''
        return
      }
      try {
        // 使用 mermaid CDN 或已安装的库
        if (window.mermaid) {
          window.mermaid.render('mermaid-flowchart', this.axureMermaidCode).then((svg) => {
            this.renderedMermaid = svg
          }).catch((err) => {
            console.error('Mermaid 渲染失败:', err)
            this.renderedMermaid = `<pre>${this.axureMermaidCode}</pre>`
          })
        } else {
          // 如果 mermaid 库未加载，直接显示代码
          this.renderedMermaid = `<pre>${this.axureMermaidCode}</pre>`
        }
      } catch (error) {
        console.error('Mermaid 渲染异常:', error)
        this.renderedMermaid = `<pre>${this.axureMermaidCode}</pre>`
      }
    },

    // 处理可编辑预览区域的内容变更
    onAxureContentBlur(event, contentType) {
      const element = event.target
      // 获取编辑后的纯文本内容（从HTML转换回markdown格式）
      const htmlContent = element.innerText

      if (contentType === 'full') {
        // 更新全量内容 - 将HTML内容转换为markdown格式的纯文本
        this.axureContent = this.htmlToMarkdown(htmlContent)
      } else if (contentType === 'incremental') {
        // 更新增量内容
        this.axureIncrementalContent = this.htmlToMarkdown(htmlContent)
      }
    },

    // 简单的HTML转Markdown（用于保存编辑后的内容）
    htmlToMarkdown(text) {
      // 由于contenteditable会保留HTML结构，这里直接使用innerText获取的纯文本
      // 表格内容会以制表符分隔的形式保存
      return text
    },

    async generateFromAxure() {
      if (!this.axureContent) {
        ElMessage.error(this.$t('requirementAnalysis.noAxureContent'))
        return
      }

      const title = this.$t('requirementAnalysis.axureRequirement')

      await this.startGeneration(
        title,
        this.axureContent,
        this.selectedAxureProject,
        this.globalOutputMode
      )
    },

    async checkConfigStatus() {
      try {
        this.checkingConfig = true
        const response = await api.get('/requirement-analysis/config/check/')
        this.configStatus = response.data

        // 判断逻辑：只有当"用例编写模型"、"用例评审模型"、"用例编写提示词"和"用例评审提示词"都配置且启用时，才不显示弹框
        const writerModelReady = response.data.writer_model &&
                                response.data.writer_model.configured &&
                                response.data.writer_model.enabled

        const reviewerModelReady = response.data.reviewer_model &&
                                  response.data.reviewer_model.configured &&
                                  response.data.reviewer_model.enabled

        const writerPromptReady = response.data.writer_prompt &&
                                 response.data.writer_prompt.configured &&
                                 response.data.writer_prompt.enabled

        const reviewerPromptReady = response.data.reviewer_prompt &&
                                   response.data.reviewer_prompt.configured &&
                                   response.data.reviewer_prompt.enabled

        // 检查生成行为配置
        const generationConfigReady = response.data.generation_config &&
                                      response.data.generation_config.configured

        // 只有五项都准备好时才不显示引导弹框
        if (writerModelReady && reviewerModelReady && writerPromptReady && reviewerPromptReady && generationConfigReady) {
          this.showConfigGuide = false

          // 如果生成配置允许用户修改，则使用配置的默认输出模式
          if (response.data.generation_config && response.data.generation_config.default_output_mode) {
            this.globalOutputMode = response.data.generation_config.default_output_mode
          }

          // 根据生成配置的enable_auto_review决定是否显示评审步骤
          if (response.data.generation_config && response.data.generation_config.enable_auto_review !== null) {
            this.showReviewStep = response.data.generation_config.enable_auto_review
          } else {
            this.showReviewStep = true  // 默认显示
          }
        } else {
          this.showConfigGuide = true
        }
      } catch (error) {
        console.error('Failed to check config status:', error)
        // 如果检查失败，默认不显示引导，避免影响正常使用
        this.showConfigGuide = false
        this.checkingConfig = false
      } finally {
        this.checkingConfig = false
      }
    },

    goToConfig() {
      // 智能判断跳转目标：优先跳转到未配置/未启用的页面
      // 优先级：必需配置 > 可选配置，提示词 > 模型

      // 0. 首先检查生成行为配置（generation_config）
      if (!this.configStatus.generation_config || !this.configStatus.generation_config.configured) {
        this.$router.push('/configuration/ai-gen/config-param')
        return
      }

      // 1. 优先检查必需的提示词配置（writer_prompt）
      if (!this.configStatus.writer_prompt.configured || !this.configStatus.writer_prompt.enabled) {
        this.$router.push('/configuration/ai-gen/config-prompt')
        return
      }

      // 2. 检查必需的模型配置（writer_model）
      if (!this.configStatus.writer_model.configured || !this.configStatus.writer_model.enabled) {
        this.$router.push('/configuration/ai-gen/config-model')
        return
      }

      // 3. 检查可选的评审提示词（reviewer_prompt）
      if (!this.configStatus.reviewer_prompt.configured || !this.configStatus.reviewer_prompt.enabled) {
        this.$router.push('/configuration/ai-gen/config-prompt')
        return
      }

      // 4. 检查可选的评审模型（reviewer_model）
      if (!this.configStatus.reviewer_model.configured || !this.configStatus.reviewer_model.enabled) {
        this.$router.push('/configuration/ai-gen/config-model')
        return
      }

      // 默认跳转到生成行为配置
      this.$router.push('/configuration/ai-gen/config-param')
    },

    goToPromptConfig() {
      this.$router.push('/configuration/ai-gen/config-prompt')
    },

    getConfigItemClass(configKey) {
      const config = this.configStatus[configKey]
      if (config.enabled) {
        return 'status-enabled'
      } else if (config.configured) {
        return 'status-disabled'
      } else {
        return 'status-unconfigured'
      }
    },

    getStatusIcon(configKey) {
      const config = this.configStatus[configKey]
      if (config.enabled) {
        // 绿色对号
        return '<path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm193.5 301.7l-210.6 292c-12.7 17.7-39 17.7-51.7 0L318.5 484.9c-3.8-5.3 0-12.7 6.5-12.7h46.9c10.2 0 19.9 4.9 25.9 13.3l71.2 98.8 157.2-218c6-8.3 15.6-13.3 25.9-13.3H699c6.5 0 10.3 7.4 6.5 12.7z" fill="#27ae60"/>'
      } else if (config.configured) {
        // 禁用图标（灰色圆圈和斜线）
        return '<path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372zm128-412c0 4.4-3.6 8-8 8H392c-4.4 0-8-3.6-8-8v-48c0-4.4 3.6-8 8-8h240c4.4 0 8 3.6 8 8v48z" fill="#95a5a6"/>'
      } else {
        // 红色叉号
        return '<path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm165.4 618.2l-66-70.7c-10.6-10.1-28.1-10.1-38.8 0l-66.7 71.5-66.7-71.5c-10.6-10.1-28.1-10.1-38.8 0l-66 70.7c-9.9 10.6-9.9 27.4 0 38l66 70.7c10.6 10.1 28.1 10.1 38.8 0l66.7-71.5 66.7 71.5c10.6 10.1 28.1 10.1 38.8 0l66-70.7c9.9-10.6 9.9-27.4 0-38z" fill="#e74c3c"/>'
      }
    },

    getStatusSymbol(configKey) {
      const config = this.configStatus[configKey]
      if (config.enabled) {
        // 绿色对勾
        return '<span style="color: #27ae60; font-size: 18px;">✓</span>'
      } else if (config.configured) {
        // 禁用图标
        return '<span style="color: #95a5a6; font-size: 18px;">○</span>'
      } else {
        // 红色叉号
        return '<span style="color: #e74c3c; font-size: 18px;">✗</span>'
      }
    },

    handleDrop(event) {
      event.preventDefault()
      this.isDragOver = false
      const files = event.dataTransfer.files
      if (files.length > 0) {
        this.handleFileSelect({ target: { files } })
      }
    },

    handleFileSelect(event) {
      const file = event.target.files[0]
      if (file) {
        const allowedTypes = [
          'application/pdf',
          'application/msword',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'text/plain',
          'text/markdown',
          'text/x-markdown'
        ]

        if (allowedTypes.includes(file.type) ||
            file.name.match(/\.(pdf|doc|docx|txt|md)$/i)) {
          this.selectedFile = file
          this.documentTitle = file.name.replace(/\.[^/.]+$/, "")
        } else {
          ElMessage.error(this.$t('requirementAnalysis.invalidFileFormatDetail'))
        }
      }
    },

    removeFile() {
      this.selectedFile = null
      this.documentTitle = ''
      this.$refs.fileInput.value = ''
    },

    formatFileSize(bytes) {
      if (bytes === 0) return '0 Bytes'
      const k = 1024
      const sizes = ['Bytes', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(k))
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
    },

    async generateFromManualInput() {
      if (!this.canGenerateManual) {
        ElMessage.error(this.$t('requirementAnalysis.fillRequiredInfo'))
        return
      }

      const requirementText = `${this.$t('requirementAnalysis.requirementTitle')}: ${this.manualInput.title}\n\n${this.$t('requirementAnalysis.requirementDescription')}:\n${this.manualInput.description}`

      await this.startGeneration(
        this.manualInput.title,
        requirementText,
        this.manualInput.selectedProject,
        this.globalOutputMode  // 使用全局输出模式
      )
    },

    async generateFromDocument() {
      if (!this.selectedFile || !this.documentTitle) {
        ElMessage.error(this.$t('requirementAnalysis.selectFileAndTitle'))
        return
      }

      try {
        // 首先上传并提取文档内容
        const formData = new FormData()
        formData.append('title', this.documentTitle)
        formData.append('file', this.selectedFile)
        if (this.selectedProject) {
          formData.append('project', this.selectedProject)
        }

        ElMessage.info(this.$t('requirementAnalysis.extractingContent'))
        const uploadResponse = await api.post('/requirement-analysis/documents/', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        })

        // 提取文档内容
        const extractResponse = await api.get(`/requirement-analysis/documents/${uploadResponse.data.id}/extract_text/`)
        const extractedText = extractResponse.data.extracted_text

        if (!extractedText || extractedText.trim().length === 0) {
          ElMessage.error(this.$t('requirementAnalysis.extractionFailed'))
          return
        }

        const requirementText = `${this.$t('requirementAnalysis.documentTitle')}: ${this.documentTitle}\n\n${this.$t('requirementAnalysis.documentContent')}:\n${extractedText}`

        await this.startGeneration(
          this.documentTitle,
          requirementText,
          this.selectedProject,
          this.globalOutputMode  // 使用全局输出模式
        )

      } catch (error) {
        console.error(this.$t('requirementAnalysis.documentProcessingFailed'), error)
        ElMessage.error(this.$t('requirementAnalysis.documentProcessingFailed') + ': ' + (error.response?.data?.error || error.message))
      }
    },

    async startGeneration(title, requirementText, projectId, outputMode = 'stream') {
      // 在开始生成前，主动刷新token确保生成过程中不会过期
      try {
        const userStore = useUserStore()
        if (userStore.isTokenExpiringSoon && userStore.refreshToken) {
          console.log('Refreshing token before generation...')
          await userStore.refreshAccessToken()
          console.log('Token refreshed successfully, safe to start generation')
        } else if (userStore.accessToken) {
          console.log('Token status is good, no refresh needed')
        }
      } catch (error) {
        console.error('Token refresh failed:', error)
        ElMessage.error(this.$t('requirementAnalysis.tokenRefreshFailed'))
        return
      }

      this.isGenerating = true
      this.currentStep = 1
      this.progressText = this.$t('requirementAnalysis.creatingTask')
      this.streamedContent = ''  // 清空流式内容
      this.finalTestCases = ''  // 清空最终版用例
      this.streamedReviewContent = ''  // 清空评审内容
      this.hasShownCompletionMessage = false  // 重置完成消息标志位
      this.showResults = false  // 隐藏上一次的结果

      try {
        // 调用新的生成API
        const requestData = {
          title: title,
          requirement_text: requirementText,
          use_writer_model: true,
          use_reviewer_model: true,
          output_mode: outputMode  // 添加输出模式参数
        }

        // 如果选择了项目，添加到请求中
        if (projectId) {
          requestData.project = projectId
        }

        const response = await api.post('/requirement-analysis/testcase-generation/generate/', requestData)

        this.currentTaskId = response.data.task_id
        this.progressText = this.$t('requirementAnalysis.taskCreated')

        ElMessage.success(this.$t('requirementAnalysis.generateSuccess'))

        // 根据输出模式选择不同的进度获取方式
        if (outputMode === 'stream') {
          this.startStreamingProgress()
        } else {
          this.startPolling()
        }

      } catch (error) {
        console.error(this.$t('requirementAnalysis.createTaskFailed'), error)
        ElMessage.error(this.$t('requirementAnalysis.createTaskFailed') + ': ' + (error.response?.data?.error || error.message))
        this.isGenerating = false
      }
    },

    startStreamingProgress() {
      // 使用SSE进行流式进度获取
      // 注意：EventSource不使用axios代理，需要直接指向后端服务器
      // 完整的URL路径: /api/requirement-analysis/testcase-generation/{task_id}/stream_progress/

      // 动态获取后端URL：使用当前页面的协议和主机名
      // 在生产环境中(如Docker部署)，通常通过Nginx反向代理访问，端口应该是80或443(与当前页面一致)
      // 而不是直接访问后端端口8000
      const currentOrigin = window.location.origin
      const apiUrl = `${currentOrigin}/api/requirement-analysis/testcase-generation/${this.currentTaskId}/stream_progress/`

      console.log('SSE连接URL:', apiUrl)

      // 创建EventSource（不支持自定义headers，使用withCredentials发送cookie）
      this.eventSource = new EventSource(apiUrl, { withCredentials: true })

      // 监听连接打开事件
      this.eventSource.onopen = (event) => {
        console.log('✅ SSE连接已打开', event)
      }

      this.eventSource.onmessage = (event) => {
        console.log('📨 收到SSE消息:', event.data)

        try {
          const data = JSON.parse(event.data)
          console.log('📦 解析后的数据:', data)

          if (data.type === 'progress') {
            // Update progress status
            if (data.status === 'generating') {
              this.currentStep = 2
              this.progressText = `${this.$t('requirementAnalysis.statusGenerating')} ${data.progress}%`
            } else if (data.status === 'reviewing') {
              this.currentStep = 3
              this.progressText = `${this.$t('requirementAnalysis.statusReviewing')} ${data.progress}%`
            } else if (data.status === 'revising') {
              this.currentStep = 3
              this.progressText = `${this.$t('requirementAnalysis.statusRevising')} ${data.progress}%`
            }
          } else if (data.type === 'content') {
            // Real-time streaming content (case generation)
            console.log('✍️ Received streaming content:', data.content.length, 'characters')
            this.streamedContent += data.content
            this.currentStep = 2
            this.progressText = this.$t('requirementAnalysis.statusGenerating')
          } else if (data.type === 'review_content') {
            // Real-time review content
            console.log('📝 Received review content:', data.content.length, 'characters', 'Total length:', this.streamedReviewContent.length + data.content.length)
            this.streamedReviewContent += data.content
            this.currentStep = 3
            this.progressText = this.$t('requirementAnalysis.statusReviewing')
          } else if (data.type === 'final_content') {
            // Real-time final test cases content
            console.log('🎯 Received final cases content:', data.content.length, 'characters', 'Total length:', this.finalTestCases.length + data.content.length)
            this.finalTestCases += data.content
            this.currentStep = 3
            this.progressText = '🎯 ' + this.$t('requirementAnalysis.statusRevising')
          } else if (data.type === 'status') {
            // Final status
            console.log('📊 Received status update:', data.status)
            if (data.status === 'completed') {
              this.progressText = this.$t('requirementAnalysis.statusCompleted')
              // Fetch final result
              this.fetchFinalResult()
            } else if (data.status === 'failed') {
              this.progressText = this.$t('requirementAnalysis.statusFailed')
              this.handleGenerationError()
            }
          } else if (data.type === 'done') {
            // 流式结束，立即关闭EventSource，获取最终结果
            console.log('✅ 流式传输完成')
            if (this.eventSource) {
              console.log('🔒 关闭SSE连接')
              this.eventSource.close()
              this.eventSource = null
            }
            this.fetchFinalResult()
          }
        } catch (e) {
          console.error('❌ 解析SSE数据失败:', e, '原始数据:', event.data)
        }
      }

      this.eventSource.onerror = (error) => {
        console.log('⚠️ SSE连接事件:', error)

        // 如果EventSource已经被关闭（在onmessage中关闭的），不做任何处理
        if (!this.eventSource) {
          console.log('ℹ️ EventSource已关闭，忽略错误事件')
          return
        }

        console.log('EventSource状态:', {
          readyState: this.eventSource.readyState,
          url: this.eventSource.url
        })

        // 如果任务已经完成或不在生成中，不要降级
        if (this.showResults || !this.isGenerating) {
          console.log('ℹ️ 任务已完成或不在生成中，不降级到轮询')
          // 清理EventSource
          if (this.eventSource) {
            this.eventSource.close()
            this.eventSource = null
          }
          return
        }

        // readyState=2表示连接已关闭，readyState=0表示连接中断
        // EventSource会自动重连（readyState=0），除非是致命错误（readyState=2）
        if (this.eventSource.readyState === 2) {
          console.error('❌ SSE连接永久关闭，降级到轮询模式')
          this.eventSource.close()
          this.eventSource = null
          ElMessage.warning(this.$t('requirementAnalysis.streamConnectionInterrupted'))
          this.startPolling()
        } else if (this.eventSource.readyState === 0) {
          // EventSource正在重连，等待一段时间后检查
          console.log('🔄 SSE正在重连...')
          setTimeout(() => {
            // 如果5秒后还是断开状态，降级到轮询
            if (this.eventSource && this.eventSource.readyState === 0) {
              console.error('❌ SSE重连失败，降级到轮询模式')
              this.eventSource.close()
              this.eventSource = null
              ElMessage.warning(this.$t('requirementAnalysis.streamConnectionInterrupted'))
              this.startPolling()
            }
          }, 5000)
        }
      }
    },

    async fetchFinalResult() {
      try {
        // 修复URL：去掉多余的/api/前缀（axios baseURL已经包含/api）
        const response = await api.get(`/requirement-analysis/testcase-generation/${this.currentTaskId}/progress/`)
        const task = response.data

        this.generationResult = task
        this.showResults = true
        this.isGenerating = false

        // 设置第4步为完成状态
        this.currentStep = 4

        // 设置最终版用例（如果还没有通过流式接收完整）
        if (task.final_test_cases) {
          console.log('📝 Getting final cases from task object')
          // 无论this.finalTestCases是否已有值，都用最新的final_test_cases覆盖
          // 这样确保完整输出模式下也能正确显示最终版用例
          this.finalTestCases = task.final_test_cases
        }

        // 如果评审内容为空，从task对象中获取
        if (!this.streamedReviewContent && task.review_feedback) {
          console.log('📝 Getting review content from task object')
          this.streamedReviewContent = task.review_feedback
        }

        // 如果生成内容为空，从task对象中获取
        if (!this.streamedContent && task.generated_test_cases) {
          console.log('✍️ Getting generated content from task object')
          this.streamedContent = task.generated_test_cases
        }

        if (this.eventSource) {
          this.eventSource.close()
          this.eventSource = null
        }

        // Only show completion message once
        if (!this.hasShownCompletionMessage) {
          ElMessage.success(this.$t('requirementAnalysis.generateCompleteSuccess'))
          this.hasShownCompletionMessage = true
        }
      } catch (error) {
        console.error('Failed to fetch final result:', error)
        ElMessage.error(this.$t('requirementAnalysis.fetchResultFailed'))
        this.isGenerating = false
      }
    },

    handleGenerationError() {
      this.isGenerating = false
      if (this.eventSource) {
        this.eventSource.close()
        this.eventSource = null
      }
      if (this.pollInterval) {
        clearInterval(this.pollInterval)
        this.pollInterval = null
      }
    },

    startPolling() {
      this.pollInterval = setInterval(async () => {
        try {
          // 修复URL：去掉多余的/api/前缀（axios baseURL已经包含/api）
          const response = await api.get(`/requirement-analysis/testcase-generation/${this.currentTaskId}/progress/`)
          const task = response.data

          console.log(`${this.$t('requirementAnalysis.taskStatus')}: ${task.status}, ${this.$t('requirementAnalysis.progress')}: ${task.progress}%`)

          // 更新进度显示
          if (task.status === 'generating') {
            this.currentStep = 2
            this.progressText = this.$t('requirementAnalysis.statusGenerating')
          } else if (task.status === 'reviewing') {
            this.currentStep = 3
            this.progressText = this.$t('requirementAnalysis.statusReviewing')
          } else if (task.status === 'completed') {
            this.currentStep = 4
            this.progressText = this.$t('requirementAnalysis.statusCompleted')

            // 任务完成，显示结果
            this.generationResult = task
            this.showResults = true
            this.isGenerating = false

            // 设置显示内容（完整输出模式下需要）
            if (task.generated_test_cases) {
              console.log('✍️ Polling mode - Setting generated content')
              this.streamedContent = task.generated_test_cases
            }
            if (task.review_feedback) {
              console.log('📝 Polling mode - Setting review content')
              this.streamedReviewContent = task.review_feedback
            }
            if (task.final_test_cases) {
              console.log('🎯 Polling mode - Setting final test cases')
              this.finalTestCases = task.final_test_cases
            }

            clearInterval(this.pollInterval)
            this.pollInterval = null

            // 只显示一次完成消息
            if (!this.hasShownCompletionMessage) {
              ElMessage.success(this.$t('requirementAnalysis.generateCompleteSuccess'))
              this.hasShownCompletionMessage = true
            }
            return
          } else if (task.status === 'failed') {
            this.progressText = this.$t('requirementAnalysis.statusFailed')
            this.isGenerating = false

            clearInterval(this.pollInterval)
            this.pollInterval = null

            ElMessage.error(this.$t('requirementAnalysis.generateFailed') + ': ' + (task.error_message || this.$t('requirementAnalysis.unknownError')))
            return
          }

        } catch (error) {
          console.error(this.$t('requirementAnalysis.checkProgressFailed'), error)
          // 继续轮询，不中断
        }
      }, 3000) // 每3秒检查一次
    },

    cancelGeneration() {
      if (this.pollInterval) {
        clearInterval(this.pollInterval)
        this.pollInterval = null
      }
      this.isGenerating = false
      this.currentTaskId = null
      ElMessage.info(this.$t('requirementAnalysis.generationCancelled'))
    },

    // 下载测试用例为xlsx文件
    async downloadTestCases() {
      try {
        // 解析最终测试用例内容
        const finalTestCases = this.generationResult.final_test_cases;
        const taskId = this.generationResult.task_id;

        // 创建工作簿
        const workbook = XLSX.utils.book_new();

        // 过滤掉总结和建议部分，只保留测试用例内容
        const filteredContent = this.filterTestCasesOnly(finalTestCases);

        // 尝试解析表格格式的测试用例（参考AutoGenTestCase的做法）
        const tableFormat = this.parseTableFormat(filteredContent);

        let worksheetData = [];

        if (tableFormat.length > 0) {
          // 如果解析到表格格式，直接使用，但要确保表头正确
          worksheetData = tableFormat;

          // 检查并修正表头
          if (worksheetData.length > 0) {
            const header = worksheetData[0];
            for (let i = 0; i < header.length; i++) {
              if (header[i] && header[i].includes('测试步骤')) {
                header[i] = header[i].replace('测试步骤', '操作步骤');
              }
              if (header[i] && header[i].includes('Test Steps')) {
                header[i] = header[i].replace('Test Steps', '操作步骤');
              }
            }
          }
        } else {
          // 否则尝试解析结构化格式
          worksheetData = this.parseStructuredFormat(filteredContent);
        }

        // 将所有单元格中的<br>标签转换为换行符
        worksheetData = worksheetData.map(row =>
          row.map(cell => this.convertBrToNewline(cell))
        );

        // 创建工作表
        const worksheet = XLSX.utils.aoa_to_sheet(worksheetData);

        // 设置列宽
        const colWidths = [
          { wch: 15 }, // 测试用例编号
          { wch: 30 }, // 测试场景
          { wch: 25 }, // 前置条件
          { wch: 40 }, // 操作步骤
          { wch: 30 }, // 预期结果
          { wch: 10 }  // 优先级
        ];
        worksheet['!cols'] = colWidths;

        // 设置表头样式（加粗）
        if (worksheetData.length > 1) {
          for (let col = 0; col < Math.min(6, worksheetData[0].length); col++) {
            const cellAddress = XLSX.utils.encode_cell({ r: 0, c: col });
            if (!worksheet[cellAddress]) continue;
            worksheet[cellAddress].s = {
              font: { bold: true },
              alignment: { horizontal: 'center', vertical: 'center', wrapText: true }
            };
          }

          // 设置自动换行
          for (let row = 1; row < worksheetData.length; row++) {
            for (let col = 0; col < Math.min(6, worksheetData[row].length); col++) {
              const cellAddress = XLSX.utils.encode_cell({ r: row, c: col });
              if (worksheet[cellAddress]) {
                worksheet[cellAddress].s = {
                  alignment: { vertical: 'top', wrapText: true }
                };
              }
            }
          }
        }

        // 将工作表添加到工作簿
        XLSX.utils.book_append_sheet(workbook, worksheet, this.$t('requirementAnalysis.testCaseSheetName'));

        // 生成文件名（包含任务ID和日期）
        const fileName = this.$t('requirementAnalysis.excelFileName', { taskId: taskId, date: new Date().toISOString().slice(0, 10) });

        // 导出文件
        XLSX.writeFile(workbook, fileName);

        ElMessage.success(this.$t('requirementAnalysis.downloadSuccess'));
      } catch (error) {
        console.error(this.$t('requirementAnalysis.downloadFailed'), error);
        ElMessage.error(this.$t('requirementAnalysis.downloadFailed') + ': ' + (error.message || this.$t('requirementAnalysis.unknownError')));
      }
    },

    // 保存到用例记录
    async saveToTestCaseRecords() {
      try {
        // 调用后端API保存到记录
        const response = await api.post(`/requirement-analysis/testcase-generation/${this.generationResult.task_id}/save_to_records/`)

        if (response.data.already_saved) {
          ElMessage.info(this.$t('requirementAnalysis.alreadySaved'))
        } else {
          const importedCount = response.data.imported_count || 0
          ElMessage.success(`测试用例已保存！已导入 ${importedCount} 条测试用例到测试用例管理系统`)
        }

        // 不跳转，留在当前页面
        // this.$router.push('/generated-testcases')
      } catch (error) {
        console.error(this.$t('requirementAnalysis.saveFailed'), error)
        ElMessage.error(this.$t('requirementAnalysis.saveFailed') + ': ' + (error.response?.data?.error || error.message))
      }
    },

    resetGeneration() {
      // 重置生成状态
      this.isGenerating = false;
      this.currentTaskId = null;
      this.progressText = this.$t('requirementAnalysis.preparing');
      this.currentStep = 0;
      this.showResults = false;
      this.generationResult = null;

      // 清空流式内容和最终版用例
      this.streamedContent = '';
      this.streamedReviewContent = '';
      this.finalTestCases = '';

      if (this.pollInterval) {
        clearInterval(this.pollInterval);
        this.pollInterval = null;
      }

      // 刷新页面以获取最新的配置
      window.location.reload();
    },

    // 格式化日期时间
    formatDateTime(dateTimeString) {
      if (!dateTimeString) return '';
      const date = new Date(dateTimeString);
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      return `${year}-${month}-${day} ${hours}:${minutes}`;
    },

    // 格式化Markdown为HTML（使用marked库）
    formatMarkdown(content) {
      if (!content) return '';
      try {
        // 配置marked选项
        marked.setOptions({
          breaks: true,  // 支持换行
          gfm: true  // 支持GitHub Flavored Markdown（表格等）
        });
        // 解析并返回HTML
        return marked.parse(content);
      } catch (error) {
        console.error('Markdown解析失败:', error);
        // 如果marked失败，回退到简单处理
        return this.simpleFormatMarkdown(content);
      }
    },

    // 简单的Markdown格式化（回退方案)
    simpleFormatMarkdown(content) {
      if (!content) return '';

      // 先去除"新增"标记
      let html = content
          .replace(/\*\*新增\*\*-/g, '')
          .replace(/新增-/g, '');

      // 转义HTML特殊字符
      html = html
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');

      // 标题
      html = html.replace(/^#{6}\s+(.+)$/gm, '<h6>$1</h6>');
      html = html.replace(/^#{5}\s+(.+)$/gm, '<h5>$1</h5>');
      html = html.replace(/^#{4}\s+(.+)$/gm, '<h4>$1</h4>');
      html = html.replace(/^#{3}\s+(.+)$/gm, '<h3>$1</h3>');
      html = html.replace(/^#{2}\s+(.+)$/gm, '<h2>$1</h2>');
      html = html.replace(/^#{1}\s+(.+)$/gm, '<h1>$1</h1>');

      // 粗体
      html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      // 斜体
      html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
      // 代码块
      html = html.replace(/```([\s\S]+?)```/g, '<pre><code>$1</code></pre>');
      // 行内代码
      html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
      // 换行符
      html = html.replace(/\n/g, '<br>');

      return html;
    },

    // 将HTML的<br>标签转换为换行符（用于Excel导出）
    convertBrToNewline(text) {
      if (!text) return '';
      return text.replace(/<br\s*\/?>/gi, '\n');
    },

    // 过滤掉总结和建议部分，只保留测试用例内容
    filterTestCasesOnly(content) {
      if (!content) return '';

      const lines = content.split('\n');
      const filteredLines = [];
      let inTestCaseTable = false;
      let tableEnded = false;
      let consecutiveNonTableLines = 0;

      for (let line of lines) {
        const trimmedLine = line.trim();

        // 如果已经检测到表格结束，停止处理
        if (tableEnded) break;

        // 检测表格开始：包含 | 且是表头行
        if (!inTestCaseTable && trimmedLine.includes('|')) {
          // 检查是否是表头行（包含"用例"、"测试"、"场景"等关键词）
          if (trimmedLine.includes('用例') ||
              trimmedLine.includes('测试') ||
              trimmedLine.includes('场景') ||
              trimmedLine.includes('Test') ||
              trimmedLine.includes('Case')) {
            inTestCaseTable = true;
            consecutiveNonTableLines = 0;
            filteredLines.push(line);
            continue;
          }
        }

        // 在表格内
        if (inTestCaseTable) {
          // 如果是表格行（包含 |）
          if (trimmedLine.includes('|')) {
            filteredLines.push(line);
            consecutiveNonTableLines = 0;
          } else {
            // 非表格行
            consecutiveNonTableLines++;

            // 连续2行非表格内容，认为表格结束
            if (consecutiveNonTableLines >= 2) {
              tableEnded = true;
            }
          }
        }
      }

      return filteredLines.join('\n');
    },

    // 解析表格格式的测试用例（参考AutoGenTestCase的做法）
    parseTableFormat(content) {
      if (!content) return [];

      const lines = content.split('\n').filter(line => line.trim());
      const worksheetData = [];

      for (let line of lines) {
        const trimmedLine = line.trim();

        // 检查是否是表格行（包含|分隔符，且不是分隔线）
        if (trimmedLine.includes('|') && !trimmedLine.includes('--------')) {
          const cells = trimmedLine.split('|').map(cell => cell.trim()).filter(cell => cell);
          if (cells.length > 1) {
            worksheetData.push(cells);
          }
        }
      }

      return worksheetData;
    },

    // 解析结构化格式的测试用例
    parseStructuredFormat(content) {
      if (!content) return [];

      const lines = content.split('\n').filter(line => line.trim());
      const worksheetData = [];

      // 添加表头
      worksheetData.push([
        this.$t('requirementAnalysis.excelTestCaseNumber'),
        this.$t('requirementAnalysis.excelTestScenario'),
        this.$t('requirementAnalysis.excelPrecondition'),
        this.$t('requirementAnalysis.excelTestSteps'),
        this.$t('requirementAnalysis.excelExpectedResult'),
        this.$t('requirementAnalysis.excelPriority')
      ]);

      let currentTestCase = {};
      let testCaseNumber = 1;
      let i = 0;

      while (i < lines.length) {
        const line = lines[i].trim();

        // 识别测试用例开始标志
        if (line.includes('测试用例') || line.includes('Test Case') ||
            line.match(/^(\d+\.|\*|\-|\d+、)/)) {

          // 如果之前有测试用例数据，先保存
          if (Object.keys(currentTestCase).length > 0) {
            worksheetData.push([
              currentTestCase.number || `TC${testCaseNumber}`,
              currentTestCase.scenario || '',
              currentTestCase.precondition || '',
              currentTestCase.steps || '',
              currentTestCase.expected || '',
              currentTestCase.priority || '中'
            ]);
            testCaseNumber++;
          }

          // 开始新的测试用例
          currentTestCase = {
            number: `TC${testCaseNumber}`,
            scenario: line.replace(/^(\d+\.|\*|\-|\d+、)\s*/, '').replace(/测试用例\d*[:：]?\s*/, ''),
            precondition: '',
            steps: '',
            expected: '',
            priority: '中'
          };
          i++;
        }
        // 识别前置条件
        else if (line.includes('前置条件') || line.includes('前提') ||
            line.includes('Precondition')) {
          let precondition = line.replace(/.*?[:：]\s*/, '');
          // 收集后续的前置条件行
          i++;
          while (i < lines.length) {
            const nextLine = lines[i].trim();
            if (nextLine.includes('测试步骤') || nextLine.includes('操作步骤') ||
                nextLine.includes('Test Steps') || nextLine.includes('步骤') ||
                nextLine.includes('预期结果') || nextLine.includes('Expected') ||
                nextLine.includes('优先级') || nextLine.includes('Priority') ||
                nextLine.includes('测试用例') || nextLine.includes('Test Case') ||
                nextLine.match(/^(\d+\.|\*|\-|\d+、)/)) {
              break;
            }
            if (nextLine) {
              precondition += '\n' + nextLine;
            }
            i++;
          }
          currentTestCase.precondition = precondition;
        }
        // 识别测试步骤
        else if (line.includes('测试步骤') || line.includes('操作步骤') ||
            line.includes('Test Steps') || line.includes('步骤')) {
          let steps = line.replace(/.*?[:：]\s*/, '');
          // 收集后续的步骤行
          i++;
          while (i < lines.length) {
            const nextLine = lines[i].trim();
            if (nextLine.includes('预期结果') || nextLine.includes('Expected') ||
                nextLine.includes('优先级') || nextLine.includes('Priority') ||
                nextLine.includes('测试用例') || nextLine.includes('Test Case') ||
                nextLine.match(/^(\d+\.|\*|\-|\d+、)/)) {
              break;
            }
            if (nextLine) {
              steps += '\n' + nextLine;
            }
            i++;
          }
          currentTestCase.steps = steps;
        }
        // 识别预期结果
        else if (line.includes('预期结果') || line.includes('Expected') ||
            line.includes('期望')) {
          let expected = line.replace(/.*?[:：]\s*/, '');
          // 收集后续的结果行
          i++;
          while (i < lines.length) {
            const nextLine = lines[i].trim();
            if (nextLine.includes('优先级') || nextLine.includes('Priority') ||
                nextLine.includes('测试用例') || nextLine.includes('Test Case') ||
                nextLine.match(/^(\d+\.|\*|\-|\d+、)/)) {
              break;
            }
            if (nextLine) {
              expected += '\n' + nextLine;
            }
            i++;
          }
          currentTestCase.expected = expected;
        }
        // 识别优先级
        else if (line.includes('优先级') || line.includes('Priority')) {
          currentTestCase.priority = line.replace(/.*?[:：]\s*/, '');
          i++;
        }
        // 如果是没有明确标识的行，可能是场景描述的延续
        else if (Object.keys(currentTestCase).length > 0 &&
            !currentTestCase.steps && !currentTestCase.expected &&
            !currentTestCase.precondition) {
          if (currentTestCase.scenario && line.length > 5) {
            currentTestCase.scenario += '\n' + line;
          }
          i++;
        } else {
          i++;
        }
      }

      // 保存最后一个测试用例
      if (Object.keys(currentTestCase).length > 0) {
        worksheetData.push([
          currentTestCase.number || `TC${testCaseNumber}`,
          currentTestCase.scenario || '',
          currentTestCase.precondition || '',
          currentTestCase.steps || '',
          currentTestCase.expected || '',
          currentTestCase.priority || '中'
        ]);
      }

      // 如果没有解析到结构化数据，则按原格式输出
      if (worksheetData.length <= 1) {
        worksheetData.length = 0; // 清空
        worksheetData.push([this.$t('requirementAnalysis.testCaseContent')]);
        content.split('\n').forEach((line, index) => {
          if (line.trim()) {
            worksheetData.push([line.trim()]);
          }
        });
      }

      return worksheetData;
    }
  }
}
</script>

<style scoped>
.requirement-analysis {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
  position: relative;
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

/* 输出模式设置区域 - 全局 */
.output-mode-section {
  margin-bottom: 30px;
}

.output-mode-card {
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  border: 1px solid rgba(226, 232, 240, 0.8);
  transition: all 0.3s ease;
}

.output-mode-card:hover {
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
}

.output-mode-card h3 {
  font-size: 1.3rem;
  color: #1a202c;
  margin: 0 0 8px 0;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.mode-section-desc {
  color: #64748b;
  font-size: 0.9rem;
  margin: 0 0 16px 0;
  line-height: 1.5;
}

/* 配置引导弹出窗口 */
.modal-overlay {
  position: fixed !important;
  top: 0 !important;
  left: 0 !important;
  right: 0 !important;
  bottom: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  background: rgba(15, 23, 42, 0.6) !important;
  backdrop-filter: blur(4px);
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  z-index: 9999 !important;
  padding: 20px;
  margin: 0 !important;
  opacity: 1 !important;
}

.guide-config-modal {
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%) !important;
  border-radius: 24px;
  padding: 36px;
  max-width: 850px;
  width: 100%;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  border: 1px solid rgba(226, 232, 240, 0.8);
  position: relative;
  flex-shrink: 0;
  margin: auto;
  opacity: 1 !important;
}

.guide-config-modal::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 5px;
  background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
  border-radius: 24px 24px 0 0;
}

.guide-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 28px;
}

.guide-icon {
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  filter: drop-shadow(0 4px 8px rgba(245, 158, 11, 0.2));
}

.guide-title h2 {
  font-size: 1.6rem;
  color: #1a202c;
  margin: 0 0 6px 0;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.guide-title p {
  color: #64748b;
  font-size: 0.95rem;
  margin: 0;
  font-weight: 400;
}

.config-groups {
  margin-bottom: 24px;
}

.config-group {
  margin-bottom: 20px;
}

.group-label {
  font-size: 0.85rem;
  color: #94a3b8;
  margin-bottom: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.config-items-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}

.config-item-inline {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-radius: 12px;
  border: 2px solid transparent;
  position: relative;
  overflow: hidden;
  font-weight: 500;
}

.config-item-inline::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-radius: 12px 0 0 12px;
}

.config-item-inline.optional {
  opacity: 0.75;
}

/* 根据状态设置背景色和样式 */
.config-item-inline.status-enabled {
  background: linear-gradient(135deg, rgba(236, 253, 245, 0.9) 0%, rgba(220, 252, 231, 0.6) 100%);
  border-color: rgba(34, 197, 94, 0.2);
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.1);
}

.config-item-inline.status-enabled::before {
  background: linear-gradient(180deg, #22c55e 0%, #16a34a 100%);
}

.config-item-inline.status-disabled {
  background: linear-gradient(135deg, rgba(254, 249, 195, 0.9) 0%, rgba(254, 240, 138, 0.6) 100%);
  border-color: rgba(234, 179, 8, 0.2);
  box-shadow: 0 4px 12px rgba(234, 179, 8, 0.1);
}

.config-item-inline.status-disabled::before {
  background: linear-gradient(180deg, #eab308 0%, #ca8a04 100%);
}

.config-item-inline.status-unconfigured {
  background: linear-gradient(135deg, rgba(254, 242, 242, 0.9) 0%, rgba(254, 226, 226, 0.6) 100%);
  border-color: rgba(239, 68, 68, 0.2);
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.1);
}

.config-item-inline.status-unconfigured::before {
  background: linear-gradient(180deg, #ef4444 0%, #dc2626 100%);
}

.status-symbol {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  font-size: 20px;
}

.config-label {
  font-size: 0.95rem;
  color: #334155;
  font-weight: 600;
  flex-shrink: 0;
}

.config-name {
  font-size: 0.85rem;
  color: #64748b;
  margin-left: 4px;
  font-weight: 500;
}

.status-text {
  margin-left: auto;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 700;
  background: #ef4444;
  color: white;
  white-space: nowrap;
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.2);
}

.status-text.warning {
  background: #eab308;
  box-shadow: 0 2px 6px rgba(234, 179, 8, 0.2);
}

.guide-actions {
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  gap: 12px;
  margin-top: 30px;
  width: 100%;
}

.guide-actions button {
  flex: none !important;
  width: 240px !important;
  height: 50px !important;
  padding: 0 24px !important;
  border-radius: 12px;
  font-size: 0.95rem;
  font-weight: 600;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  text-align: center;
  white-space: nowrap;
  opacity: 1 !important;
  cursor: pointer;
  box-sizing: border-box !important;
}

.guide-actions .generate-manual-btn {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%) !important;
  color: white !important;
  border: 2px solid transparent !important;
  box-shadow: 0 2px 10px rgba(79, 172, 254, 0.3);
}

.guide-actions .skip-action {
  font-size: 0.85rem;
  color: #94a3b8;
  cursor: pointer;
  text-decoration: none;
  padding: 4px 8px;
  transition: color 0.3s;
}

.guide-actions .skip-action:hover {
  color: #64748b;
  text-decoration: underline;
}


.manual-input-card, .upload-card {
  background: white;
  border-radius: 12px;
  padding: 30px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  border: 1px solid #e1e8ed;
  margin-bottom: 30px;
}

.manual-input-card h2, .upload-card h2 {
  color: #2c3e50;
  margin-bottom: 20px;
  font-size: 1.5rem;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: #2c3e50;
}

/* 输出模式选择器 */
.output-mode-selector {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  align-items: stretch;
}

.mode-option {
  position: relative;
  cursor: pointer;
  display: flex;
}

.mode-option input[type="radio"] {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.mode-content {
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  padding: 16px;
  transition: all 0.3s ease;
  background: white;
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: 100%;
  box-sizing: border-box;
}

.mode-option:hover .mode-content {
  border-color: #3b82f6;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.1);
}

.mode-option.active .mode-content {
  border-color: #3b82f6;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.2);
}

.mode-title {
  font-size: 1rem;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 6px;
}

.mode-desc {
  font-size: 0.85rem;
  color: #64748b;
  line-height: 1.4;
}

.mode-option.active .mode-title {
  color: #2563eb;
}

.mode-option.active .mode-desc {
  color: #475569;
}

/* 面板选择器样式 - 现代化改进 */
.panel-selector {
  margin-bottom: 32px;
}

.panel-tabs {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 20px;
  background: transparent;
  padding: 0;
  border-radius: 0;
  box-shadow: none;
  border: none;
}

.panel-tab {
  display: block;
  padding: 24px;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background: white;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
  position: relative;
  overflow: hidden;
  height: 180px; /* 增加高度以容纳多行文本 */
  box-sizing: border-box;
}

.panel-tab::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 4px;
  background: transparent;
  transition: background 0.3s ease;
}

.panel-tab:hover {
  transform: translateY(-4px);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
  border-color: #cbd5e1;
}

.panel-tab.active {
  background: white;
  border-color: #3b82f6;
  box-shadow: 0 10px 25px -5px rgba(59, 130, 246, 0.15), 0 8px 10px -6px rgba(59, 130, 246, 0.1);
}

.panel-tab.active::before {
  background: linear-gradient(90deg, #3b82f6, #60a5fa);
}

.panel-icon {
  position: absolute;
  top: 24px;
  left: 24px;
  font-size: 2.2rem;
  line-height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: #f8fafc;
  transition: all 0.3s ease;
  font-family: "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji", sans-serif;
  text-align: center;
  margin: 0;
  overflow: hidden;
  box-sizing: border-box;
}

.panel-tab.active .panel-icon {
  background: #eff6ff;
  transform: scale(1.05);
}

.panel-content-wrapper {
  position: absolute;
  top: 92px; /* icon(24+56) + 12px 间距 */
  left: 24px;
  right: 24px;
  display: block;
}

.panel-label {
  font-size: 1.1rem;
  color: #334155;
  font-weight: 600;
  text-align: left;
  line-height: 24px;
  height: 24px;
  margin: 0 0 8px 0; /* 底部间距 */
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  transition: color 0.3s ease;
}

.panel-tab.active .panel-label {
  color: #1d4ed8;
}

.panel-desc {
  font-size: 0.85rem;
  color: #64748b;
  line-height: 1.6;
  height: 3.2em; /* 1.6 * 2行 = 3.2em，保证有足够空间渲染两行 */
  text-align: left;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2; /* 限制2行 */
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 面板内容样式 */
.panel-content {
  margin-bottom: 30px;
}

.panel-card {
  background: white;
  border-radius: 12px;
  padding: 30px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  border: 1px solid #e1e8ed;
}

.panel-card h2 {
  color: #2c3e50;
  margin-bottom: 20px;
  font-size: 1.5rem;
}

/* 知识库面板样式 */
.knowledge-search-form {
  margin-bottom: 20px;
}

.form-row {
  display: flex;
  gap: 20px;
  margin-bottom: 15px;
}

.form-row .form-group {
  flex: 1;
  margin-bottom: 0;
}

.search-input-row {
  display: flex;
  gap: 10px;
}

.search-input-row .form-input {
  flex: 1;
}

.search-btn {
  padding: 12px 24px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.3s ease;
  white-space: nowrap;
}

.search-btn:hover:not(:disabled) {
  background: #2563eb;
}

.search-btn:disabled {
  background: #bdc3c7;
  cursor: not-allowed;
}

.search-params {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 30px;
  margin-top: 15px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
}

.param-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.param-item-wide{
  flex: 1;
  min-width: 250px;
}

.param-label{
  font-size: 14px;
  color: #606266;
  white-space: nowrap;
}

.param-slider{
  width: 120px;
}

.param-select{
  width: 80px;
}

.param-value{
  min-width: 40px;
  font-size: 14px;
  color: #409eff;
  font-weight: 500;
}

/* 检索类型选择样式 */
.search-type-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 15px 0;
}

.search-type-label {
  font-size: 14px;
  color: #606266;
  font-weight: 500;
}

.search-type-buttons {
  display: flex;
  gap: 8px;
}

.search-type-btn {
  padding: 8px 16px;
  border: 1px solid #dcdfe6;
  background: #f5f7fa;
  color: #606266;
  cursor: pointer;
  border-radius: 4px;
  font-size: 13px;
  transition: all 0.3s ease;
}

.search-type-btn:hover {
  border-color: #409eff;
  color: #409eff;
}

.search-type-btn.active {
  background: #409eff;
  color: white;
  border-color: #409eff;
}

.search-type-btn.active:hover {
  background: #337ecc;
}

/* 检索结果样式 */
.search-results {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e1e8ed;
}

.search-results h3 {
  color: #2c3e50;
  margin-bottom: 15px;
  font-size: 1.1rem;
}

.result-list {
  max-height: 400px;
  overflow-y: auto;
}

.result-item {
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
  margin-bottom: 12px;
  border-left: 4px solid #3b82f6;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.result-index {
  font-weight: 600;
  color: #3b82f6;
}

.result-score {
  font-size: 0.85rem;
  color: #27ae60;
  background: #e8f5e9;
  padding: 2px 8px;
  border-radius: 10px;
}

.result-content {
  font-size: 0.9rem;
  line-height: 1.6;
  color: #495057;
  white-space: pre-wrap;
}

.result-meta {
  margin-top: 8px;
  font-size: 0.8rem;
  color: #6c757d;
}

.generate-knowledge-btn {
  width: 100%;
  padding: 15px;
  background: #27ae60;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1.1rem;
  margin-top: 15px;
  transition: background 0.3s ease;
}

.generate-knowledge-btn:hover:not(:disabled) {
  background: #219a52;
}

.generate-knowledge-btn:disabled {
  background: #bdc3c7;
  cursor: not-allowed;
}

/* Axure占位符样式 */
/* Axure面板样式 */
.axure-form {
  margin-bottom: 20px;
}

.axure-input-row {
  display: flex;
  gap: 10px;
}

.axure-input-row .form-input {
  flex: 1;
}

.parse-btn {
  padding: 12px 24px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.3s ease;
  white-space: nowrap;
}

.parse-btn:hover:not(:disabled) {
  background: #2563eb;
}

.parse-btn:disabled {
  background: #bdc3c7;
  cursor: not-allowed;
}

.axure-result {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e1e8ed;
}

.axure-result h3 {
  color: #2c3e50;
  margin-bottom: 15px;
  font-size: 1.1rem;
}

.result-preview {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 15px;
  margin-bottom: 15px;
  max-height: 300px;
  overflow-y: auto;
}

.result-preview pre {
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 0.9rem;
  line-height: 1.6;
  color: #495057;
}

.generate-axure-btn {
  width: 100%;
  padding: 15px;
  background: #27ae60;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1.1rem;
  transition: background 0.3s ease;
}

.generate-axure-btn:hover:not(:disabled) {
  background: #219a52;
}

.generate-axure-btn:disabled {
  background: #bdc3c7;
  cursor: not-allowed;
}

/* Mermaid 流程图样式 */
.mermaid-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.mermaid-container .mermaid {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 20px;
  overflow-x: auto;
}

.mermaid-container .mermaid svg {
  max-width: 100%;
  height: auto;
}

.mermaid-code {
  background: #2d3748;
  border-radius: 8px;
  padding: 15px;
  margin-top: 15px;
}

.mermaid-code h4 {
  color: #a0aec0;
  margin-bottom: 10px;
  font-size: 14px;
}

.mermaid-code pre {
  color: #e2e8f0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  line-height: 1.5;
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.flowchart-content {
  padding: 15px;
}

.view-toggle {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.view-toggle-btn {
  padding: 6px 14px;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  background: #f5f5f5;
  color: #333;
  transition: all 0.2s;
}

.view-toggle-btn:hover {
  background: #e8e8e8;
}

.view-toggle-btn.active {
  background: #4CAF50;
  color: #fff;
  border-color: #4CAF50;
}

.markdown-preview {
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 15px;
  min-height: 150px;
  max-height: none;
  overflow-y: visible;
  font-size: 14px;
  line-height: 1.6;
}

.markdown-preview h1,
.markdown-preview h2,
.markdown-preview h3,
.markdown-preview h4 {
  margin-top: 15px;
  margin-bottom: 10px;
  border-bottom: 1px solid #eee;
  padding-bottom: 5px;
}

.markdown-preview h1 { font-size: 18px; }
.markdown-preview h2 { font-size: 16px; }
.markdown-preview h3 { font-size: 15px; }
.markdown-preview h4 { font-size: 14px; }

.markdown-preview p {
  margin-bottom: 10px;
}

.markdown-preview ul,
.markdown-preview ol {
  padding-left: 20px;
  margin-bottom: 10px;
}

.markdown-preview li {
  margin-bottom: 4px;
}

.markdown-preview table {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
  border: 1px solid #333;
}

.markdown-preview th,
.markdown-preview td {
  border: 1px solid #333;
  padding: 8px 12px;
  text-align: left;
}

.markdown-preview th {
  background: #e8e8e8;
  font-weight: bold;
}

/* 编辑文本框样式 */
.edit-textarea {
  width: 100%;
  min-height: 300px;
  padding: 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  line-height: 1.6;
  resize: vertical;
  background: #fafafa;
  color: #333;
}

.edit-textarea:focus {
  outline: none;
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

/* 可编辑预览样式 */
.editable-preview {
  outline: none;
  min-height: 200px;
  cursor: text;
}

.editable-preview:focus {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

.editable-preview:hover {
  border-color: #c0c4cc;
}

/* 可编辑预览样式 */
.editable-preview {
  outline: none;
  min-height: 300px;
  padding: 15px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  cursor: text;
  transition: border-color 0.3s;
}

.editable-preview:hover {
  border-color: #c0c4cc;
}

.editable-preview:focus {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

/* 可编辑预览中的表格样式 */
.editable-preview table {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
  border: 1px solid #333;
}

.editable-preview th,
.editable-preview td {
  border: 1px solid #333;
  padding: 8px 12px;
  text-align: left;
}

.editable-preview th {
  background: #e8e8e8;
  font-weight: bold;
}

.markdown-preview pre {
  background: #f5f5f5;
  padding: 10px;
  border-radius: 4px;
  overflow-x: auto;
}

.markdown-preview code {
  background: #f0f0f0;
  padding: 2px 4px;
  border-radius: 3px;
  font-family: monospace;
}

.markdown-preview pre code {
  background: none;
  padding: 0;
}

.markdown-preview blockquote {
  border-left: 4px solid #ddd;
  padding-left: 12px;
  margin: 10px 0;
  color: #666;
}

.markdown-preview a {
  color: #1a73e8;
  text-decoration: none;
}

.markdown-preview a:hover {
  text-decoration: underline;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #606266;
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.content-type-options {
  display: flex;
  gap: 20px;
  margin-top: 8px;
}

.inline-options {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #606266;
}

.radio-label input[type="radio"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

@media (max-width: 768px) {
  .panel-tabs {
    flex-direction: column;
    gap: 10px;
  }

  .form-row {
    flex-direction: column;
    gap: 15px;
  }

  .search-params {
    flex-direction: column;
    gap: 15px;
  }

  .param-item {
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
  }

  .param-slider {
    width: 100px;
  }

  .param-select {
    width: 70px;
  }
}

.form-input, .form-select, .form-textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 1rem;
  transition: border-color 0.3s ease;
}

.form-input:focus, .form-select:focus, .form-textarea:focus {
  outline: none;
  border-color: #3498db;
  box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
}

.form-textarea {
  resize: vertical;
  font-family: inherit;
}

.char-count {
  text-align: right;
  font-size: 0.85rem;
  color: #666;
  margin-top: 5px;
}

.required {
  color: #e74c3c;
}

.generate-manual-btn, .generate-btn {
  background: #27ae60;
  color: white;
  border: none;
  padding: 15px 30px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1.1rem;
  transition: background 0.3s ease;
  width: 100%;
  margin-top: 10px;
}

.generate-manual-btn:hover:not(:disabled), .generate-btn:hover:not(:disabled) {
  background: #219a52;
}

.generate-manual-btn:disabled, .generate-btn:disabled {
  background: #bdc3c7;
  cursor: not-allowed;
}

.divider {
  text-align: center;
  margin: 40px 0;
  position: relative;
}

.divider::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 1px;
  background: #ddd;
}

.divider span {
  background: white;
  padding: 0 20px;
  color: #666;
  font-size: 1rem;
}

.upload-area {
  border: 2px dashed #ddd;
  border-radius: 8px;
  padding: 40px;
  text-align: center;
  transition: border-color 0.3s ease;
  margin-bottom: 20px;
}

.upload-area.drag-over {
  border-color: #3498db;
  background: #f8f9fa;
}

.upload-placeholder {
  color: #666;
}

.upload-icon {
  font-size: 3rem;
  margin-bottom: 15px;
  display: block;
}

.upload-hint {
  color: #999;
  font-size: 0.9rem;
  margin-top: 5px;
}

.select-file-btn {
  background: #3498db;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  cursor: pointer;
  margin-top: 15px;
}

.file-selected {
  padding: 20px;
  background: #f8f9fa;
  border-radius: 6px;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 15px;
}

.file-icon {
  font-size: 2rem;
}

.file-details {
  flex: 1;
}

.file-name {
  font-weight: 600;
  margin: 0;
}

.file-size {
  color: #666;
  font-size: 0.9rem;
  margin: 5px 0 0 0;
}

.remove-file {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.2rem;
}

.generation-progress {
  margin: 40px 0;
}

.progress-card {
  background: white;
  border-radius: 12px;
  padding: 30px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  border: 1px solid #e1e8ed;
  text-align: center;
}

.progress-card h3 {
  color: #2c3e50;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}

.current-mode-badge {
  display: inline-block;
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  color: white;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.85rem;
  font-weight: 500;
  margin-left: 8px;
  box-shadow: 0 2px 8px rgba(79, 172, 254, 0.3);
}

.progress-info {
  display: flex;
  justify-content: center;
  gap: 30px;
  margin-bottom: 30px;
  flex-wrap: wrap;
}

.progress-item {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.progress-item .label {
  font-size: 0.9rem;
  color: #666;
}

.progress-item .value {
  font-weight: 600;
  color: #2c3e50;
}

/* 流式内容显示区域 */
.stream-content-display {
  margin: 20px 0;
  border: 2px solid #e1e8ed;
  border-radius: 8px;
  overflow: hidden;
  background: #f8f9fa;
}

.stream-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #e9ecef;
  border-bottom: 1px solid #dee2e6;
}

.stream-title {
  font-weight: 600;
  color: #495057;
  font-size: 0.95rem;
}

.stream-status {
  font-size: 0.85rem;
  color: #6c757d;
  background: white;
  padding: 4px 10px;
  border-radius: 12px;
  border: 1px solid #dee2e6;
}

.stream-content {
  max-height: 400px;
  overflow-y: auto;
  padding: 16px;
  text-align: left;
  background: white;
  font-size: 0.9rem;
  line-height: 1.6;
  color: #2c3e50;
  white-space: pre-wrap;
  word-wrap: break-word;
}

/* stream-content 表格样式 */
.stream-content table {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
  border: 1px solid #333;
}

.stream-content th,
.stream-content td {
  border: 1px solid #333;
  padding: 8px 12px;
  text-align: left;
}

.stream-content th {
  background: #e8e8e8;
  font-weight: bold;
}

.stream-content::-webkit-scrollbar {
  width: 8px;
}

.stream-content::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.stream-content::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.stream-content::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

/* 最终版用例特殊样式 */
.stream-content.final-testcases {
  background: #f0f7ff;
  border-left: 4px solid #2196F3;
}

.stream-content.final-testcases::before {
  content: '📋 最终版本';
  display: block;
  font-weight: 600;
  color: #2196F3;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid #e3f2fd;
}

/* 流式输出指示器 */
.streaming-indicator {
  font-size: 0.85em;
  margin-left: 8px;
  color: #4CAF50;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.stream-content h1,
.stream-content h2,
.stream-content h3,
.stream-content h4,
.stream-content h5,
.stream-content h6 {
  margin-top: 1em;
  margin-bottom: 0.5em;
  color: #2c3e50;
  font-weight: 600;
}

.stream-content code {
  background: #f1f3f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 0.85em;
}

.stream-content pre {
  background: #f1f3f5;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 10px 0;
}

.stream-content pre code {
  background: none;
  padding: 0;
}

.progress-steps {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-bottom: 30px;
  flex-wrap: wrap;
}

.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  opacity: 0.4;
  transition: opacity 0.3s ease;
}

.step.active {
  opacity: 1;
}

.step-number {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #ddd;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  color: white;
}

.step.active .step-number {
  background: #3498db;
}

.step-text {
  font-size: 0.9rem;
  color: #666;
}

.cancel-generation-btn {
  background: #e74c3c;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  cursor: pointer;
}

.completion-actions {
  display: flex;
  gap: 12px;
  margin-top: 20px;
  flex-wrap: wrap;
}

.completion-actions button {
  flex: 1;
  min-width: 150px;
  padding: 12px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.completion-actions .download-btn {
  background: #28a745;
  color: white;
  font-size: 1rem;
}

.completion-actions .download-btn:hover {
  background: #218838;
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(40, 167, 69, 0.3);
}

.completion-actions .save-btn {
  background: #007bff;
  color: white;
  font-size: 1rem;
}

.completion-actions .save-btn:hover {
  background: #0056b3;
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 123, 255, 0.3);
}

.completion-actions .new-generation-btn {
  background: #6c757d;
  color: white;
  font-size: 1rem;
}

.completion-actions .new-generation-btn:hover {
  background: #5a6268;
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(108, 117, 125, 0.3);
}

.generation-result {
  margin: 40px 0;
}

.result-header {
  background: white;
  border-radius: 12px;
  padding: 30px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  border: 1px solid #e1e8ed;
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 20px;
}

.result-header h2 {
  color: #27ae60;
  margin: 0;
}

.result-summary {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.summary-item {
  color: #666;
  font-size: 0.9rem;
}

.new-generation-btn {
  background: #3498db;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  cursor: pointer;
}

.generated-testcases-section, .review-feedback-section, .final-testcases-section {
  background: white;
  border-radius: 12px;
  padding: 30px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  border: 1px solid #e1e8ed;
  margin-bottom: 20px;
}

.generated-testcases-section h3, .review-feedback-section h3, .final-testcases-section h3 {
  color: #2c3e50;
  margin-bottom: 20px;
}

.testcase-content, .review-content {
  background: #f8f9fa;
  border-radius: 6px;
  padding: 20px;
  border-left: 4px solid #3498db;
}

.testcase-content pre, .review-content pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
  font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
  font-size: 0.9rem;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .result-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .progress-info, .result-summary {
    flex-direction: column;
    gap: 10px;
  }

  .progress-steps {
    gap: 10px;
  }
}

.actions-section {
  display: flex;
  gap: 20px;
  justify-content: center;
  margin-top: 30px;
  flex-wrap: wrap;
}

.download-btn, .save-btn {
  padding: 12px 24px;
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.3s ease;
}

.download-btn {
  background-color: #1abc9c;
  color: white;
}

.download-btn:hover {
  background-color: #16a085;
}

.save-btn {
  background-color: #3498db;
  color: white;
}

.save-btn:hover {
  background-color: #2980b9;
}

@media (max-width: 768px) {
  .actions-section {
    flex-direction: column;
    align-items: center;
  }

  .download-btn, .save-btn {
    width: 100%;
    max-width: 300px;
    justify-content: center;
  }
}
</style>

<style>
/* 全局样式：确保弹窗不受任何容器限制 */
.modal-overlay {
  position: fixed !important;
  top: 0 !important;
  left: 0 !important;
  right: 0 !important;
  bottom: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  max-width: none !important;
  max-height: none !important;
  background: rgba(15, 23, 42, 0.6) !important;
  backdrop-filter: blur(4px);
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  z-index: 9999 !important;
  padding: 20px;
  margin: 0 !important;
  opacity: 1 !important;
  box-sizing: border-box !important;
}

.guide-config-modal {
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%) !important;
  border-radius: 24px;
  padding: 36px;
  max-width: 850px !important;
  width: 100% !important;
  min-width: 300px !important;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  border: 1px solid rgba(226, 232, 240, 0.8);
  position: relative;
  flex-shrink: 0;
  margin: auto;
  opacity: 1 !important;
  box-sizing: border-box !important;
}

/* 全局按钮样式 */
.guide-actions {
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  gap: 12px;
  margin-top: 30px;
  width: 100%;
}

.guide-actions button {
  flex: none !important;
  width: 240px !important;
  height: 50px !important;
  padding: 0 24px !important;
  border-radius: 12px;
  font-size: 0.95rem;
  font-weight: 600;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  text-align: center;
  white-space: nowrap;
  opacity: 1 !important;
  box-sizing: border-box !important;
  cursor: pointer;
}

.guide-actions .generate-manual-btn {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%) !important;
  color: white !important;
  border: 2px solid transparent !important;
  box-shadow: 0 2px 10px rgba(79, 172, 254, 0.3);
}

.guide-actions .skip-action {
  font-size: 0.85rem;
  color: #94a3b8;
  cursor: pointer;
  text-decoration: none;
  padding: 4px 8px;
  transition: color 0.3s;
}

.guide-actions .skip-action:hover {
  color: #64748b;
  text-decoration: underline;
}
</style>