<template>
  <div class="workspace">
    <div class="workspace-header">
      <div>
        <h2>{{ title }}</h2>
        <p>{{ subtitle }}</p>
      </div>
      <div class="header-actions">
        <el-select v-model="selectedProjectId" placeholder="选择项目" clearable @change="onProjectChange">
          <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
        </el-select>
        <el-select v-if="mode === 'cases'" v-model="executionConfigurationId" placeholder="选择运行配置" clearable>
          <el-option v-for="configuration in configurations" :key="configuration.id" :label="configuration.name" :value="configuration.id" />
        </el-select>
        <el-button v-if="mode === 'cases'" type="primary" :disabled="selectedCaseIds.length === 0" :loading="starting" @click="startSelectedCases">
          <el-icon><VideoPlay /></el-icon>
          运行选中用例
        </el-button>
        <el-button v-if="mode === 'cases'" :disabled="visibleCases.length === 0" :loading="starting" @click="startVisibleCases">
          运行当前目录
        </el-button>
        <el-button v-if="mode === 'runs'" :loading="loading" @click="loadRuns">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button v-if="mode === 'configurations'" type="primary" @click="openConfigurationDialog()">
          <el-icon><Plus /></el-icon>
          新建配置
        </el-button>
      </div>
    </div>

    <el-empty v-if="!selectedProjectId && !['dashboard', 'logs'].includes(mode)" description="请先选择 API 自动化项目" />

    <template v-else-if="mode === 'dashboard'">
      <div class="stats-grid">
        <section class="stat-block cyan"><span>{{ projects.length }}</span><small>自动化项目</small></section>
        <section class="stat-block green"><span>{{ dashboard.caseCount }}</span><small>自动化用例</small></section>
        <section class="stat-block amber"><span>{{ dashboard.structuredCount }}</span><small>可结构化执行</small></section>
        <section class="stat-block red"><span>{{ dashboard.failedRuns }}</span><small>最近失败运行</small></section>
      </div>
      <section class="panel overview-panel">
        <h3>运行资产</h3>
        <p>用例由 TestHub 统一管理。选择项目后可浏览目录、创建环境配置并执行可结构化运行的用例。</p>
        <el-button type="primary" @click="goTo('cases')">查看用例</el-button>
      </section>
    </template>

    <template v-else-if="mode === 'cases'">
      <div class="case-layout">
        <section class="panel case-tree-panel">
          <div class="panel-title"><h3>用例目录</h3><el-button link :loading="loading" @click="loadCases">刷新</el-button></div>
          <el-tree :data="suiteTree" node-key="id" :props="treeProps" default-expand-all @node-click="selectSuite">
            <template #default="{ data }">
              <span class="tree-node"><el-icon><FolderOpened /></el-icon>{{ data.name }}<em v-if="suiteCaseCount(data)">{{ suiteCaseCount(data) }}</em></span>
            </template>
          </el-tree>
        </section>
        <section class="panel case-list-panel">
          <div class="panel-title"><h3>{{ selectedSuiteName || '全部用例' }}</h3><el-tag type="info">{{ visibleCases.length }} 个</el-tag></div>
          <el-table v-loading="loading" :data="visibleCases" @selection-change="onCaseSelection">
            <el-table-column type="selection" width="48" />
            <el-table-column prop="name" label="用例" min-width="240" show-overflow-tooltip />
            <el-table-column label="类型" width="110"><template #default="{ row }"><el-tag :type="caseType(row) === 'WebSocket' ? 'warning' : 'success'">{{ caseType(row) }}</el-tag></template></el-table-column>
            <el-table-column prop="priority" label="优先级" width="86"><template #default="{ row }"><el-tag :type="priorityType(row.priority)">{{ row.priority }}</el-tag></template></el-table-column>
            <el-table-column label="标记" min-width="150"><template #default="{ row }"><el-tag v-for="marker in row.markers" :key="marker" size="small" class="marker">{{ marker }}</el-tag></template></el-table-column>
            <el-table-column prop="source_path" label="来源文件" min-width="230" show-overflow-tooltip />
          </el-table>
        </section>
      </div>
    </template>

    <template v-else-if="mode === 'interfaces'">
      <section class="panel">
        <div class="panel-title interface-toolbar"><el-input v-model="endpointPath" class="path-search" clearable placeholder="按接口路径搜索" @clear="resetEndpointPage" @keyup.enter="resetEndpointPage"><template #append><el-button @click="resetEndpointPage">搜索</el-button></template></el-input><div class="schema-actions"><el-tag :type="schemaStatus.schema_count ? 'success' : 'info'">{{ pagination.interfaces.total }} 个接口</el-tag><el-button :loading="schemaLoading" @click="loadSchemaStatus"><el-icon><Refresh /></el-icon>刷新 Schema</el-button><el-button type="primary" :loading="schemaGenerating" @click="regenerateSchemas">重新生成</el-button></div></div>
        <p v-if="schemaStatus.latest_snapshot?.change_summary" class="schema-summary">最近生成：新增 {{ schemaStatus.latest_snapshot.change_summary.added?.length || 0 }}，变更 {{ schemaStatus.latest_snapshot.change_summary.changed?.length || 0 }}，删除 {{ schemaStatus.latest_snapshot.change_summary.removed?.length || 0 }}</p>
        <el-tabs v-model="endpointCategory" class="interface-category-tabs" @tab-change="changeEndpointCategory">
          <el-tab-pane label="Frontend" name="frontend" />
          <el-tab-pane label="Others" name="others" />
        </el-tabs>
        <el-table v-loading="loading" :data="endpoints">
          <el-table-column prop="path" label="路径" min-width="280" show-overflow-tooltip />
          <el-table-column label="协议" width="110"><template #default="{ row }"><el-tag :type="row.protocol === 'WebSocket' ? 'warning' : 'success'">{{ row.protocol }}</el-tag></template></el-table-column>
          <el-table-column label="方法" width="180"><template #default="{ row }"><el-tag v-for="method in row.methods" :key="method" :type="methodTagType(method)" size="small" class="marker">{{ method }}</el-tag></template></el-table-column>
          <el-table-column label="Schema" width="110"><template #default="{ row }"><el-tag :type="row.schema_status === 'GENERATED' ? 'success' : 'info'">{{ row.schema_status === 'GENERATED' ? '已生成' : '未生成' }}</el-tag></template></el-table-column>
          <el-table-column label="响应状态码" min-width="150"><template #default="{ row }"><el-tag v-for="statusCode in row.schema_status_codes" :key="statusCode" size="small" class="marker">{{ statusCode }}</el-tag><span v-if="!row.schema_status_codes?.length">-</span></template></el-table-column>
          <el-table-column label="标签" min-width="160"><template #default="{ row }"><el-tag v-for="tag in row.tags" :key="tag" size="small" class="marker">{{ tag }}</el-tag></template></el-table-column>
          <el-table-column prop="summary" label="摘要" min-width="260" show-overflow-tooltip />
          <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.deprecated ? 'danger' : 'success'">{{ row.deprecated ? '已废弃' : '可用' }}</el-tag></template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="pagination.interfaces.page" v-model:page-size="pagination.interfaces.pageSize" class="list-pagination" background layout="total, sizes, prev, pager, next" :page-sizes="pageSizeOptions" :total="pagination.interfaces.total" @current-change="loadEndpoints" @size-change="changePageSize('interfaces', loadEndpoints)" />
      </section>
    </template>

    <template v-else-if="mode === 'coverage'">
      <div class="stats-grid">
        <section class="stat-block cyan"><span>{{ coverage.total_endpoints }}</span><small>Swagger 接口总数</small></section>
        <section class="stat-block green"><span>{{ coverage.covered_endpoints }}</span><small>已覆盖接口</small></section>
        <section class="stat-block amber"><span>{{ coverage.uncovered_endpoints }}</span><small>未覆盖接口</small></section>
        <section class="stat-block red"><span>{{ coverage.coverage_rate }}%</span><small>当前覆盖率</small></section>
      </div>
      <section class="panel coverage-panel">
        <div class="panel-title"><h3>覆盖率变化趋势</h3></div>
        <v-chart v-if="coverageTrendOption" class="coverage-chart" :option="coverageTrendOption" autoresize />
        <el-empty v-else description="暂无覆盖率快照" />
      </section>
      <section class="panel coverage-panel">
        <div class="panel-title"><h3>统计快照</h3></div>
        <el-table :data="coverageSnapshots">
          <el-table-column prop="period" label="周期" width="120"><template #default="{ row }">{{ row.period === 'WEEKLY' ? '每周' : '每月' }}</template></el-table-column>
          <el-table-column prop="snapshot_date" label="快照日期" width="160" />
          <el-table-column prop="total_endpoints" label="接口总数" width="120" />
          <el-table-column prop="covered_endpoints" label="已覆盖" width="120" />
          <el-table-column prop="coverage_rate" label="覆盖率"><template #default="{ row }">{{ row.coverage_rate }}%</template></el-table-column>
        </el-table>
      </section>
      <section class="panel coverage-panel">
        <div class="panel-title"><h3>接口覆盖详情</h3><el-tag type="info">{{ coverage.endpoint_details?.length || 0 }} 个接口</el-tag></div>
        <el-table :data="coverage.endpoint_details || []" max-height="520">
          <el-table-column prop="path" label="接口" min-width="360" show-overflow-tooltip />
          <el-table-column label="是否覆盖" width="110"><template #default="{ row }"><el-tag :type="row.covered ? 'success' : 'info'">{{ row.covered ? '已覆盖' : '未覆盖' }}</el-tag></template></el-table-column>
          <el-table-column prop="case_count" label="覆盖用例数" width="120" />
          <el-table-column label="覆盖来源" min-width="260"><template #default="{ row }"><el-tag v-for="source in row.sources" :key="source" size="small" class="marker">{{ source }}</el-tag><span v-if="!row.sources?.length">-</span></template></el-table-column>
        </el-table>
      </section>
    </template>

    <template v-else-if="mode === 'runs'">
      <section class="panel">
        <el-table v-loading="loading" :data="runs">
          <el-table-column prop="id" label="运行 ID" width="90" />
          <el-table-column prop="status" label="状态" width="110"><template #default="{ row }"><el-tag :type="runStatusType(row.status)">{{ row.status }}</el-tag></template></el-table-column>
          <el-table-column prop="total_cases" label="总数" width="80" />
          <el-table-column prop="passed_cases" label="通过" width="80" />
          <el-table-column prop="schema_warning_cases" label="Schema 告警" width="110" />
          <el-table-column prop="failed_cases" label="失败" width="80" />
          <el-table-column prop="skipped_cases" label="跳过" width="80" />
          <el-table-column prop="created_at" label="创建时间" min-width="170"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
          <el-table-column label="完整报告" width="110"><template #default="{ row }"><el-link v-if="runReportUrl(row)" :href="runReportUrl(row)" target="_blank" type="primary">Allure</el-link><span v-else>-</span></template></el-table-column>
          <el-table-column label="操作" width="150"><template #default="{ row }"><el-button link type="primary" @click="showRunDetail(row)">查看</el-button><el-button link type="danger" :disabled="row.status === 'PENDING' || row.status === 'RUNNING'" @click="deleteRun(row)">删除</el-button></template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="pagination.runs.page" v-model:page-size="pagination.runs.pageSize" class="list-pagination" background layout="total, sizes, prev, pager, next" :page-sizes="pageSizeOptions" :total="pagination.runs.total" @current-change="loadRuns" @size-change="changePageSize('runs', loadRuns)" />
      </section>
    </template>

    <template v-else-if="mode === 'reports'">
      <section class="panel">
        <el-table v-loading="loading" :data="reports">
          <el-table-column prop="id" label="运行 ID" width="90" />
          <el-table-column label="报告" min-width="180"><template #default="{ row }"><el-link :href="runReportUrl(row)" target="_blank" type="primary">打开 Allure 报告</el-link></template></el-table-column>
          <el-table-column prop="status" label="执行结果" width="110"><template #default="{ row }"><el-tag :type="runStatusType(row.status)">{{ row.status }}</el-tag></template></el-table-column>
          <el-table-column prop="passed_cases" label="通过" width="80" />
          <el-table-column prop="schema_warning_cases" label="Schema 告警" width="110" />
          <el-table-column prop="failed_cases" label="失败" width="80" />
          <el-table-column prop="skipped_cases" label="跳过" width="80" />
          <el-table-column prop="ended_at" label="生成时间" min-width="180"><template #default="{ row }">{{ formatDate(row.ended_at) }}</template></el-table-column>
          <el-table-column label="操作" width="80"><template #default="{ row }"><el-button link type="primary" @click="showRunDetail(row)">详情</el-button></template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="pagination.reports.page" v-model:page-size="pagination.reports.pageSize" class="list-pagination" background layout="total, sizes, prev, pager, next" :page-sizes="pageSizeOptions" :total="pagination.reports.total" @current-change="loadReports" @size-change="changePageSize('reports', loadReports)" />
      </section>
    </template>

    <template v-else-if="mode === 'configurations'">
      <section class="panel">
        <div class="panel-title"><h3>真实测试环境</h3><div class="environment-table-actions"><el-button v-if="configurations.length === 0" type="primary" :loading="initializingConfiguration" @click="initializeConfiguration">创建默认测试环境</el-button><el-button v-else type="primary" :icon="Check" :disabled="!selectedConfiguration || selectedConfiguration.is_default" @click="setDefaultConfiguration(selectedConfiguration)">设为默认环境</el-button></div></div>
        <el-table v-loading="loading" :data="configurations" row-key="id" :row-class-name="environmentRowClass" @selection-change="onConfigurationSelection">
          <el-table-column type="selection" width="48" />
          <el-table-column label="配置名称" min-width="180"><template #default="{ row }"><span class="environment-name">{{ row.name }}</span></template></el-table-column>
          <el-table-column prop="environment" label="运行环境" width="120"><template #default="{ row }"><el-tag type="info">{{ row.environment }}</el-tag></template></el-table-column>
          <el-table-column prop="base_url" label="HTTP 基础地址" min-width="250" />
          <el-table-column prop="timeout_seconds" label="超时" width="90"><template #default="{ row }">{{ row.timeout_seconds }}s</template></el-table-column>
          <el-table-column label="操作" width="90" fixed="right"><template #default="{ row }"><div class="environment-actions"><el-tooltip content="编辑环境" placement="top"><el-button class="environment-action edit" :icon="Edit" circle @click="openConfigurationDialog(row)" /></el-tooltip><el-tooltip content="删除环境" placement="top"><el-button class="environment-action delete" :icon="Delete" circle @click="removeConfiguration(row)" /></el-tooltip></div></template></el-table-column>
        </el-table>
      </section>
    </template>

    <template v-else-if="mode === 'schedules'">
      <section class="panel">
        <div class="panel-title"><h3>定时任务</h3><el-button type="primary" @click="scheduleDialogVisible = true"><el-icon><Plus /></el-icon>新建任务</el-button></div>
        <el-table v-loading="loading" :data="schedules">
          <el-table-column prop="name" label="任务名称" min-width="200" />
          <el-table-column prop="schedule_type_display" label="计划" width="120" />
          <el-table-column label="运行范围" min-width="150"><template #default="{ row }">{{ scheduleScopeLabel(row.config?.task_config?.selection?.source_path_prefix || 'test_api') }}</template></el-table-column>
          <el-table-column prop="next_run_display" label="下次执行" min-width="180" />
          <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.config?.status === 'PAUSED' ? 'info' : 'success'">{{ row.config?.status_display || row.status_display }}</el-tag></template></el-table-column>
          <el-table-column prop="success_count" label="成功" width="80"><template #default="{ row }">{{ row.config?.success_count || 0 }}</template></el-table-column>
          <el-table-column prop="failure_count" label="失败" width="80"><template #default="{ row }">{{ row.config?.failure_count || 0 }}</template></el-table-column>
          <el-table-column label="操作" width="110"><template #default="{ row }"><el-button v-if="row.config?.status === 'PAUSED'" link type="success" @click="resumeSchedule(row)">恢复</el-button><el-button v-else link type="warning" @click="pauseSchedule(row)">暂停</el-button></template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="pagination.schedules.page" v-model:page-size="pagination.schedules.pageSize" class="list-pagination" background layout="total, sizes, prev, pager, next" :page-sizes="pageSizeOptions" :total="pagination.schedules.total" @current-change="loadSchedules" @size-change="changePageSize('schedules', loadSchedules)" />
      </section>
    </template>

    <template v-else-if="mode === 'notifications'">
      <section class="panel">
        <div class="panel-title"><h3>通知派发记录</h3><el-button :loading="loading" @click="loadNotifications"><el-icon><Refresh /></el-icon>刷新</el-button></div>
        <el-table v-loading="loading" :data="notifications">
          <el-table-column prop="schedule_name" label="计划任务" min-width="180" show-overflow-tooltip />
          <el-table-column label="运行" width="90"><template #default="{ row }">{{ row.run || '-' }}</template></el-table-column>
          <el-table-column label="运行结果" width="110"><template #default="{ row }"><el-tag :type="runStatusType(row.execution_status)">{{ row.execution_status }}</el-tag></template></el-table-column>
          <el-table-column label="渠道" width="120"><template #default="{ row }"><el-tag type="info">{{ row.channel_display }}</el-tag></template></el-table-column>
          <el-table-column label="派发状态" width="110"><template #default="{ row }"><el-tag :type="row.status === 'DISPATCHED' ? 'success' : 'info'">{{ row.status_display }}</el-tag></template></el-table-column>
          <el-table-column label="通知目标" min-width="180"><template #default="{ row }"><el-tag v-for="target in row.targets" :key="`${target.type}-${target.name}`" size="small" class="marker">{{ target.name }}</el-tag><span v-if="!row.targets?.length">-</span></template></el-table-column>
          <el-table-column prop="message" label="内容" min-width="280" show-overflow-tooltip />
          <el-table-column prop="created_at" label="派发时间" width="180"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="pagination.notifications.page" v-model:page-size="pagination.notifications.pageSize" class="list-pagination" background layout="total, sizes, prev, pager, next" :page-sizes="pageSizeOptions" :total="pagination.notifications.total" @current-change="loadNotifications" @size-change="changePageSize('notifications', loadNotifications)" />
      </section>
    </template>

    <template v-else-if="mode === 'logs'">
      <section class="panel log-monitor-panel">
        <div class="panel-title">
          <div><h3>API 运行日志</h3><p class="log-meta">每 2 秒自动刷新，单个日志文件最大 10MB，超过后自动轮转。</p></div>
          <div class="log-actions"><el-tag type="info">{{ formatBytes(logMonitor.file_size) }} / {{ formatBytes(logMonitor.max_file_size) }}</el-tag><el-tag type="warning">{{ logMonitor.rotated_files.length }} 个轮转文件</el-tag><el-button :loading="logLoading" @click="loadLogs"><el-icon><Refresh /></el-icon>刷新</el-button></div>
        </div>
        <pre ref="automationLog" v-loading="logLoading" class="automation-log">{{ logMonitor.content || '暂无 API 自动化运行日志。' }}</pre>
        <p class="log-updated">最后更新：{{ formatDate(logMonitor.updated_at) }}</p>
      </section>
    </template>

    <template v-else>
      <section class="panel"><el-empty :description="`${title}将复用 API 自动化运行记录与平台统一调度/通知服务。`" /></section>
    </template>

    <el-dialog v-model="configurationDialogVisible" :title="editingConfiguration ? '编辑环境配置' : '新建环境配置'" width="860px" align-center class="environment-config-dialog">
      <el-tabs v-model="configurationDialogTab" class="config-tabs">
        <el-tab-pane label="基础连接" name="connection">
          <el-form class="config-form" label-position="top">
            <div class="config-grid">
              <el-form-item label="配置名称"><el-input v-model="configurationForm.name" placeholder="例如：test 环境" /></el-form-item>
              <el-form-item label="环境标识"><el-input v-model="configurationForm.environment" placeholder="例如：test" /></el-form-item>
              <el-form-item label="请求超时（秒）"><el-input-number v-model="configurationForm.timeout_seconds" :min="1" :max="300" controls-position="right" /></el-form-item>
              <el-form-item class="full-row" label="HTTP 基础地址"><el-input v-model="configurationForm.base_url" placeholder="https://api.example.com" /></el-form-item>
              <el-form-item class="full-row" label="WebSocket 地址"><el-input v-model="configurationForm.websocket_url" placeholder="wss://api.example.com/ws" /></el-form-item>
            </div>
            <div class="config-switches">
              <div><strong>默认环境</strong><span>新建运行时优先选用此环境</span><el-switch v-model="configurationForm.is_default" /></div>
              <div class="schema-validation-setting"><strong>HTTP Schema 校验</strong><span>按 Swagger 契约校验 HTTP 响应</span><el-switch v-model="configurationForm.http_schema_enabled" /><div v-if="configurationForm.http_schema_enabled" class="schema-failure-mode"><label>Schema 不一致处理</label><el-select v-model="configurationForm.http_schema_failure_mode" size="small" aria-label="Schema 不一致处理模式"><el-option label="严格失败" value="strict" /><el-option label="告警通过" value="warning" /></el-select></div></div>
            </div>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="认证与变量" name="authentication">
          <el-form class="config-form" label-position="top">
            <div class="form-section-header"><div><h3>认证角色</h3><span>每个角色在当前环境独立保存。</span></div><el-button :icon="Plus" plain @click="addAuthenticationProfile">添加角色</el-button></div>
            <div class="credential-grid"><section v-for="(profile, role) in authenticationProfiles" :key="role" :class="['credential-card', { 'is-default-role': profile.is_default_role }]"><div class="credential-card-head"><div><strong>{{ role }}</strong><el-tag v-if="profile.is_default_role" type="success" size="small">默认角色</el-tag></div><div class="credential-actions"><el-button size="small" :disabled="profile.is_default_role" @click="setDefaultAuthenticationProfile(role)">设为默认角色</el-button><el-button :icon="Delete" circle plain type="danger" @click="removeAuthenticationProfile(role)" /></div></div><el-form-item label="用户名"><el-input v-model="profile.username" autocomplete="off" /></el-form-item><el-form-item label="密码"><el-input v-model="profile.password" type="password" show-password autocomplete="new-password" /></el-form-item><div class="credential-meta"><el-form-item label="角色标识"><el-input v-model="profile.role" /></el-form-item><el-form-item label="密码模式"><el-select v-model="profile.password_mode"><el-option label="网络 Argon2" value="argon2_network" /><el-option label="明文" value="plain" /></el-select></el-form-item></div></section></div>
            <div class="form-section-header variable-heading"><div><h3>环境变量</h3><span>用于替换用例中的 <code v-pre>{{ VARIABLE_NAME }}</code> 引用。</span></div><el-button :icon="Plus" plain @click="addConfigurationVariable">添加变量</el-button></div>
            <div class="variable-editor"><div v-for="variable in primitiveConfigurationVariables" :key="variable.key" class="variable-row"><el-input v-model="variable.key" disabled /><el-input v-model="configurationVariables[variable.key]" autocomplete="off" /><el-button :icon="Delete" circle plain type="danger" @click="removeConfigurationVariable(variable.key)" /></div><div v-for="variable in structuredConfigurationVariables" :key="variable" class="structured-variable"><span>{{ variable }}</span><el-tag type="info">保留结构化值</el-tag></div></div>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="服务集成" name="services">
          <el-form class="config-form" label-position="top">
            <div class="form-section-header"><div><h3>支付服务</h3><span>仅用于支付类自动化场景。</span></div></div>
            <div class="service-grid"><el-form-item label="Mock 服务地址"><el-input v-model="paymentConfiguration.mock_base_url" placeholder="https://mock.example.com" /></el-form-item><el-form-item label="Webhook 模式"><el-select v-model="paymentConfiguration.webhook_mode"><el-option label="Stripe CLI" value="stripe_cli" /><el-option label="无" value="none" /></el-select></el-form-item><el-form-item label="Stripe API Key"><el-input v-model="paymentConfiguration.stripe_api_key" type="password" show-password autocomplete="new-password" /></el-form-item><el-form-item label="管理员令牌"><el-input v-model="paymentConfiguration.headers['X-Admin-Token']" type="password" show-password autocomplete="new-password" /></el-form-item></div>
            <div class="form-section-header model-heading"><div><h3>模型服务</h3><span>模型配置按服务名称独立保存。</span></div></div>
            <div class="model-grid"><section v-for="(profile, name) in modelProfiles" :key="name" class="model-card"><strong>{{ name }}</strong><el-form-item label="服务地址"><el-input v-model="profile.url" placeholder="https://api.example.com/v1" /></el-form-item><el-form-item label="模型名称"><el-input v-model="profile.model" /></el-form-item></section></div>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="运行设置" name="runtime">
          <el-form class="config-form" label-position="top">
            <div class="runtime-panels">
              <section class="runtime-panel execution-panel"><div class="runtime-panel-head"><span>执行节奏</span></div><div class="runtime-strategy-grid"><el-form-item label="重试次数"><el-input-number v-model="runtimeSettings.api.retry" :min="0" :max="10" controls-position="right" /></el-form-item><el-form-item label="重试间隔（秒）"><el-input-number v-model="runtimeSettings.api.retry_interval" :min="0" :max="60" controls-position="right" /></el-form-item><el-form-item label="最大并发数"><el-input-number v-model="runtimeSettings.test.max_workers" :min="1" :max="100" controls-position="right" /></el-form-item><el-form-item label="并行执行"><el-switch v-model="runtimeSettings.test.parallel" /></el-form-item></div></section>
              <section class="runtime-panel filter-panel"><div class="runtime-panel-head"><span>执行范围</span></div><div class="runtime-filter-grid"><el-form-item label="用例标记"><el-select v-model="selectedTestMarkers" multiple filterable allow-create default-first-option placeholder="选择或输入标记"><el-option v-for="marker in testMarkerOptions" :key="marker" :label="marker" :value="marker" /></el-select></el-form-item><el-form-item label="测试套件"><el-input v-model="runtimeSettings.test.suite" placeholder="可选路径" /></el-form-item><el-form-item label="忽略项"><el-select v-model="runtimeSettings.test.ignore_list" multiple filterable allow-create default-first-option placeholder="选择或输入需忽略的项"><el-option v-for="item in runtimeSettings.test.ignore_list" :key="item" :label="item" :value="item" /><template #footer><el-button :icon="Plus" text type="primary" @click.stop="addIgnoreItem">追加忽略项</el-button></template></el-select></el-form-item></div></section>
              <section class="runtime-panel lifecycle-panel"><div class="runtime-panel-head"><span>超时与清理</span></div><div class="timeout-grid"><el-form-item label="用例超时（秒）"><el-input-number v-model="runtimeSettings.test.timeout.case" :min="1" :max="3600" controls-position="right" /></el-form-item><el-form-item label="函数超时（秒）"><el-input-number v-model="runtimeSettings.test.timeout.function" :min="1" :max="3600" controls-position="right" /></el-form-item><el-form-item label="前置超时（秒）"><el-input-number v-model="runtimeSettings.test.timeout.setup" :min="1" :max="3600" controls-position="right" /></el-form-item><el-form-item label="后置超时（秒）"><el-input-number v-model="runtimeSettings.test.timeout.teardown" :min="1" :max="3600" controls-position="right" /></el-form-item></div><div class="cleanup-options"><el-checkbox v-model="runtimeSettings.test.cleanup.enabled">启用自动清理</el-checkbox><el-checkbox v-model="runtimeSettings.test.cleanup.after_test">每个用例后清理</el-checkbox><el-checkbox v-model="runtimeSettings.test.cleanup.after_suite">每个套件后清理</el-checkbox><el-checkbox v-model="runtimeSettings.test.cleanup.after_session">会话结束后清理</el-checkbox></div></section>
            </div>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="设备信息" name="event-reporting">
          <el-form class="config-form" label-position="top">
            <div class="salt-row"><span>SALT</span><el-input v-model="configurationForm.salt" type="password" show-password autocomplete="new-password" placeholder="用于网络密码转换的固定 SALT" /></div>
            <el-alert type="info" :closable="false" show-icon title="事件构造会使用当前环境保存的设备私钥进行真实上报。已配置的密钥不会回显；留空保存可保持原值。" />
            <el-form-item label="主设备私钥（Base64 PEM）"><el-input v-model="configurationForm.main_device_key" class="config-code-input" type="textarea" :rows="5" autocomplete="off" placeholder="粘贴主设备私钥" /><el-tag v-if="configurationForm.has_main_device_key" type="success" size="small">已配置</el-tag></el-form-item>
            <el-form-item label="备用设备私钥（Base64 PEM）"><el-input v-model="configurationForm.backup_device_key" class="config-code-input" type="textarea" :rows="5" autocomplete="off" placeholder="粘贴备用设备私钥" /><el-tag v-if="configurationForm.has_backup_device_key" type="success" size="small">已配置</el-tag></el-form-item>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="设备 CLI" name="device-cli">
          <el-form class="config-form" label-position="top">
            <div class="device-cli-switch"><div><strong>启用设备 CLI Skill</strong><span>仅需传入设备 ID 即可使用当前环境的固定认证与 SSH 连接模式。</span></div><el-switch v-model="deviceCliEnabled" /></div>
            <el-form-item label="命令黑名单（正则表达式）">
              <div class="blacklist-editor">
                <div v-for="(_, index) in deviceCliBlacklist" :key="index" class="blacklist-row"><el-input v-model="deviceCliBlacklist[index]" placeholder="输入禁止执行的命令正则" /><el-button :icon="Delete" circle plain type="danger" @click="removeDeviceCliBlacklist(index)" /></div>
                <el-button plain :icon="Plus" @click="addDeviceCliBlacklist">添加黑名单规则</el-button>
              </div>
            </el-form-item>
            <el-alert type="warning" :closable="false" show-icon title="默认允许执行命令；命中任一黑名单正则即被拒绝。黑名单规则由当前环境独立维护。" />
          </el-form>
        </el-tab-pane>
      </el-tabs>
      <template #footer><div class="config-dialog-footer"><div><el-button :loading="loadingTemplate" @click="loadConfigurationTemplate">加载模板</el-button><el-button v-if="!editingConfiguration" @click="copyConfigurationDialogVisible = true">复制环境</el-button></div><div><el-button @click="configurationDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveConfiguration">保存环境配置</el-button></div></div></template>
    </el-dialog>

    <el-dialog v-model="copyConfigurationDialogVisible" title="复制环境" width="440px" append-to-body>
      <el-form label-position="top">
        <el-form-item label="来源环境">
          <el-select v-model="copySourceConfigurationId" placeholder="选择已有环境" style="width: 100%">
            <el-option v-for="configuration in configurations" :key="configuration.id" :label="`${configuration.name} (${configuration.environment})`" :value="configuration.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="copyConfigurationDialogVisible = false">取消</el-button><el-button type="primary" :disabled="!copySourceConfigurationId" @click="copyConfiguration">复制</el-button></template>
    </el-dialog>

    <el-dialog v-model="runDetailVisible" title="运行详情" width="820px">
      <template v-if="selectedRun">
        <el-descriptions :column="5" border><el-descriptions-item label="状态">{{ selectedRun.status }}</el-descriptions-item><el-descriptions-item label="通过">{{ selectedRun.passed_cases }}</el-descriptions-item><el-descriptions-item label="Schema 告警">{{ selectedRun.schema_warning_cases }}</el-descriptions-item><el-descriptions-item label="失败">{{ selectedRun.failed_cases }}</el-descriptions-item><el-descriptions-item label="跳过">{{ selectedRun.skipped_cases }}</el-descriptions-item></el-descriptions>
        <div class="run-progress"><div class="run-progress-head"><span>执行进度</span><span>{{ completedTestCount }} / {{ selectedRun.total_cases || 0 }}</span></div><el-progress :percentage="runProgressPercentage" :status="selectedRun.status === 'FAILED' ? 'exception' : selectedRun.status === 'COMPLETED' ? 'success' : undefined" /><p v-if="selectedRun.current_case_name && ['PENDING', 'RUNNING'].includes(selectedRun.status)" class="current-case">当前正在运行：{{ selectedRun.current_case_name }}</p></div>
      </template>
      <el-tabs v-if="selectedRun" class="report-tabs">
        <el-tab-pane label="用例结果">
          <el-table :data="selectedRun.case_results" class="result-table"><el-table-column prop="case.name" label="用例" min-width="260" /><el-table-column prop="status" label="状态" width="150" /><el-table-column label="Schema" width="120"><template #default="{ row }"><el-tag v-if="row.status === 'SCHEMA_WARNING'" type="warning">告警</el-tag><el-tag v-else-if="row.details?.schema_validation" type="danger">失败</el-tag><span v-else>-</span></template></el-table-column><el-table-column prop="duration_ms" label="耗时(ms)" width="120" /><el-table-column label="Schema 明细" min-width="260" show-overflow-tooltip><template #default="{ row }"><span v-if="row.details?.schema_warnings?.length">{{ row.details.schema_warnings.map(item => `${item.operation} ${item.status_code} · ${item.json_path}: ${item.message}`).join('；') }}</span><span v-else-if="row.details?.schema_validation">{{ `${row.details.schema_validation.method} ${row.details.schema_validation.path} ${row.details.schema_validation.status} · ${row.details.schema_validation.field}: ${row.details.schema_validation.message}` }}</span><span v-else>-</span></template></el-table-column><el-table-column prop="error_message" label="错误信息" min-width="220" show-overflow-tooltip /></el-table>
        </el-tab-pane>
        <el-tab-pane label="Runner 日志">
          <el-collapse>
            <el-collapse-item v-for="result in selectedRun.case_results" :key="result.id" :name="result.id" :title="`${result.case.name} - ${result.status}`">
              <pre class="runner-log">{{ result.details?.stdout || result.details?.stderr || result.error_message || '暂无 Runner 日志' }}</pre>
            </el-collapse-item>
          </el-collapse>
        </el-tab-pane>
      </el-tabs>
    </el-dialog>

    <el-dialog v-model="scheduleDialogVisible" title="新建 API 自动化定时任务" width="620px">
      <el-form label-width="120px">
        <el-form-item label="任务名称"><el-input v-model="scheduleForm.name" /></el-form-item>
        <el-form-item label="计划类型"><el-select v-model="scheduleForm.schedule_type"><el-option label="分钟间隔" value="I" /><el-option label="每天" value="D" /><el-option label="Cron" value="C" /></el-select></el-form-item>
        <el-form-item v-if="scheduleForm.schedule_type === 'I'" label="间隔分钟"><el-input-number v-model="scheduleForm.minutes" :min="1" /></el-form-item>
        <el-form-item v-if="scheduleForm.schedule_type === 'C'" label="Cron 表达式"><el-input v-model="scheduleForm.cron" placeholder="0 9 * * 1-5" /></el-form-item>
        <el-form-item label="运行配置"><el-select v-model="scheduleForm.configuration_id" clearable><el-option v-for="configuration in configurations" :key="configuration.id" :label="configuration.name" :value="configuration.id" /></el-select></el-form-item>
        <el-form-item label="运行范围"><el-select v-model="scheduleForm.source_path_prefix"><el-option label="API 接口用例（test_api）" value="test_api" /><el-option label="WebSocket 用例（test_websocket）" value="test_websocket" /><el-option label="模型用例（test_model）" value="test_model" /><el-option label="支付用例（test_pay）" value="test_pay" /><el-option label="场景用例（test_scenario）" value="test_scenario" /><el-option label="全部用例" value="all" /></el-select></el-form-item>
        <el-form-item label="成功通知"><el-switch v-model="scheduleForm.notify_on_success" /></el-form-item>
        <el-form-item label="失败通知"><el-switch v-model="scheduleForm.notify_on_failure" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="scheduleDialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveSchedule">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, toRaw, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Delete, Edit, FolderOpened, Plus, Refresh, VideoPlay } from '@element-plus/icons-vue'
import VChart from 'vue-echarts'
import {
  createAutomationConfiguration,
  deleteAutomationConfiguration,
  deleteAutomationRun,
  getAutomationCases,
  getAutomationConfigurations,
  getAutomationConfigurationTemplate,
  initializeAutomationConfiguration,
  getAutomationCoverage,
  getAutomationEndpoints,
  getAutomationSchemaStatus,
  getAutomationNotificationLogs,
  getAutomationLogs,
  getAutomationProjects,
  getAutomationRun,
  getAutomationSchedules,
  getAutomationRuns,
  getAutomationSuiteTree,
  regenerateAutomationSchemas,
  setAutomationDefaultConfiguration,
  toggleAutomationSchedule,
  startAutomationRun,
  createAutomationSchedule,
  updateAutomationConfiguration
} from '@/api/api-automation'

const props = defineProps({ mode: { type: String, required: true } })
const router = useRouter()
const projects = ref([])
const selectedProjectId = ref(null)
const loading = ref(false)
const starting = ref(false)
const saving = ref(false)
const suiteTree = ref([])
const cases = ref([])
const selectedSuiteId = ref(null)
const selectedSuiteName = ref('')
const selectedCaseIds = ref([])
const runs = ref([])
const configurations = ref([])
const selectedConfiguration = ref(null)
const executionConfigurationId = ref(null)
const endpoints = ref([])
const endpointPath = ref('')
const endpointCategory = ref('frontend')
const schemaStatus = ref({ schema_count: 0, latest_snapshot: null })
const schemaLoading = ref(false)
const schemaGenerating = ref(false)
const coverage = ref({ total_endpoints: 0, covered_endpoints: 0, uncovered_endpoints: 0, coverage_rate: 0 })
const schedules = ref([])
const notifications = ref([])
const reports = ref([])
const pageSizeOptions = [20, 50, 100]
const pagination = reactive({
  interfaces: { page: 1, pageSize: 20, total: 0 },
  runs: { page: 1, pageSize: 20, total: 0 },
  reports: { page: 1, pageSize: 20, total: 0 },
  schedules: { page: 1, pageSize: 20, total: 0 },
  notifications: { page: 1, pageSize: 20, total: 0 },
})
const logMonitor = ref({ content: '', file_size: 0, max_file_size: 10 * 1024 * 1024, rotated_files: [], updated_at: null })
const logLoading = ref(false)
const automationLog = ref(null)
const selectedRun = ref(null)
const runDetailVisible = ref(false)
const configurationDialogVisible = ref(false)
const configurationDialogTab = ref('connection')
const editingConfiguration = ref(null)
const copyConfigurationDialogVisible = ref(false)
const copySourceConfigurationId = ref(null)
const configurationVariables = ref({})
const authenticationProfiles = ref({})
const paymentConfiguration = ref({})
const modelProfiles = ref({})
const runtimeSettings = ref({})
const selectedTestMarkers = ref([])
const deviceCliEnabled = ref(false)
const deviceCliBlacklist = ref([])
const loadingTemplate = ref(false)
const initializingConfiguration = ref(false)
const configurationForm = ref({ name: '', environment: 'custom', salt: '', base_url: '', websocket_url: '', timeout_seconds: 30, is_default: false, http_schema_enabled: false, http_schema_failure_mode: 'strict', main_device_key: '', backup_device_key: '', has_main_device_key: false, has_backup_device_key: false })
const defaultDeviceCliBlacklist = [
  '(^|\\s)(sudo\\s+)?rm\\s+(-[A-Za-z]*r[A-Za-z]*f?|--recursive)(\\s|$)',
  '(^|\\s)(sudo\\s+)?(mkfs(\\.|\\s|$)|wipefs(\\s|$)|fdisk(\\s|$)|parted(\\s|$))',
  '(^|\\s)(sudo\\s+)?dd\\s+.*\\bof=/dev/',
  '(^|\\s)(sudo\\s+)?(reboot|poweroff|shutdown|halt|init\\s+[06])(\\s|$)',
  '(^|\\s)(sudo\\s+)?(passwd|useradd|userdel|usermod|chpasswd|visudo)(\\s|$)',
  '(^|\\s)(sudo\\s+)?(iptables|nft|ufw|firewall-cmd)(\\s|$)',
  '(^|\\s)(sudo\\s+)?(chmod\\s+(-R\\s+)?777|chown\\s+-R\\s+/)(\\s|$)',
  '(^|\\s)(curl|wget)\\s+.*\\|\\s*(ba)?sh(\\s|$)',
  '(^|/)authorized_keys(\\s|$)|(^|/)sshd_config(\\s|$)',
]
const authenticationVariableBindings = {
  admin: ['ADMIN_NAME', 'ADMIN_PASSWORD'], distributors: ['DISTRIBUTORS_NAME', 'DISTRIBUTORS_PASSWORD'], dealer: ['DEALER_NAME', 'DEALER_PASSWORD'], customer: ['CUSTOMER_NAME', 'CUSTOMER_PASSWORD'], dealer_admin: ['DEALER_ADMIN_NAME', 'DEALER_ADMIN_PASSWORD'], dealer_rep: ['DEALER_REP_NAME', 'DEALER_REP_PASSWORD'], technician: ['TECHNICIAN_NAME', 'TECHNICIAN_PASSWORD'], scheduler: ['SCHEDULER_NAME', 'SCHEDULER_PASSWORD'], dispatcher: ['DISPATCHER_NAME', 'DISPATCHER_PASSWORD'], inspector: ['INSPECTOR_NAME', 'INSPECTOR_PASSWORD'], operator: ['OPERATOR_NAME', 'OPERATOR_PASSWORD'], org_admin: ['ORG_ADMIN_NAME', 'ORG_ADMIN_PASSWORD'], site_manager: ['SITE_MANAGER_NAME', 'SITE_MANAGER_PASSWORD'], dealerdingkang: ['DEALERDINGKANG_NAME', 'DEALERDINGKANG_PASSWORD'], customerdingkang: ['CUSTOMERDINGKANG_NAME', 'CUSTOMERDINGKANG_PASSWORD'],
}
const hiddenConfigurationVariableKeys = computed(() => new Set(['MAIN_KEY', 'BACKUP_KEY', 'SALT', 'ENV', 'MARKERS', 'IGNORE_LIST', 'default_role', ...Object.values(authenticationVariableBindings).flat()]))
const primitiveConfigurationVariables = computed(() => Object.entries(configurationVariables.value).filter(([key, value]) => !hiddenConfigurationVariableKeys.value.has(key) && (value === null || ['string', 'number', 'boolean'].includes(typeof value))).map(([key]) => ({ key })))
const structuredConfigurationVariables = computed(() => Object.entries(configurationVariables.value).filter(([key, value]) => !hiddenConfigurationVariableKeys.value.has(key) && value !== null && typeof value === 'object').map(([key]) => key))
const testMarkerOptions = ['smoke', 'P0', 'P1', 'P2']
const scheduleDialogVisible = ref(false)
const scheduleForm = ref({ name: '', schedule_type: 'I', minutes: 60, cron: '', configuration_id: null, source_path_prefix: 'test_api', notify_on_success: false, notify_on_failure: true })
const treeProps = { children: 'children', label: 'name' }
let runProgressTimer = null
let logRefreshTimer = null

const definitions = {
  dashboard: ['API 自动化测试', '用例与运行状态总览'],
  cases: ['用例管理', '按测试目录、文件和测试类管理自动化用例'],
  interfaces: ['接口管理', '展示 Swagger 契约中的接口目录与操作元数据'],
  coverage: ['覆盖统计', '分析自动化用例对 Swagger 接口的覆盖情况与趋势'],
  runs: ['执行记录', '查看 TestHub API 自动化执行结果'],
  reports: ['报告管理', '查看用例级执行结果与失败信息'],
  configurations: ['环境配置', '统一管理 API 自动化项目的运行环境与变量'],
  schedules: ['定时任务', '管理 API 自动化测试计划'],
  notifications: ['通知列表', '查看 API 自动化测试通知'],
  logs: ['日志监控', '实时查看 API 自动化测试运行日志'],
}
const title = computed(() => definitions[props.mode][0])
const subtitle = computed(() => definitions[props.mode][1])
const visibleCases = computed(() => {
  if (!selectedSuiteId.value) return cases.value
  const selectedSuite = findSuite(suiteTree.value, selectedSuiteId.value)
  if (!selectedSuite) return []
  const descendantSuiteIds = new Set()
  collectSuiteIds(selectedSuite, descendantSuiteIds)
  return cases.value.filter(caseItem => descendantSuiteIds.has(caseItem.suite))
})
const coverageSnapshots = computed(() => [
  ...(coverage.value.weekly_trend || []),
  ...(coverage.value.monthly_trend || []),
].sort((left, right) => right.snapshot_date.localeCompare(left.snapshot_date)))
const coverageTrendOption = computed(() => {
  const weekly = coverage.value.weekly_trend || []
  const monthly = coverage.value.monthly_trend || []
  if (!weekly.length && !monthly.length) return null
  const dates = [...new Set([...weekly, ...monthly].map(item => item.snapshot_date))].sort()
  const pointMap = snapshots => Object.fromEntries(snapshots.map(item => [item.snapshot_date, item.coverage_rate]))
  const weeklyMap = pointMap(weekly)
  const monthlyMap = pointMap(monthly)
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['每周覆盖率', '每月覆盖率'] },
    grid: { left: 48, right: 24, top: 48, bottom: 32 },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { formatter: '{value}%' } },
    series: [
      { name: '每周覆盖率', type: 'line', smooth: true, data: dates.map(date => weeklyMap[date] ?? null) },
      { name: '每月覆盖率', type: 'line', smooth: true, data: dates.map(date => monthlyMap[date] ?? null) },
    ],
  }
})
const dashboard = computed(() => ({
  caseCount: cases.value.length,
  structuredCount: cases.value.filter(caseItem => caseItem.execution_mode === 'STRUCTURED').length,
  failedRuns: runs.value.filter(run => run.status === 'FAILED').length,
}))
const completedTestCount = computed(() => {
  if (!selectedRun.value) return 0
  return selectedRun.value.passed_cases + selectedRun.value.failed_cases + selectedRun.value.skipped_cases
})
const runProgressPercentage = computed(() => {
  const total = selectedRun.value?.total_cases || 0
  return total ? Math.min(100, Math.round(completedTestCount.value / total * 100)) : 0
})

const unwrap = response => response.data.results || response.data
const setPaginatedItems = (response, items, page) => {
  items.value = response.data.results || []
  page.total = response.data.count || 0
}
const formatDate = value => value ? new Date(value).toLocaleString() : '-'
const formatBytes = value => {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / 1024 ** exponent).toFixed(exponent ? 1 : 0)} ${units[exponent]}`
}
const priorityType = priority => ({ P0: 'danger', P1: 'warning', P2: 'info' }[priority] || 'info')
const caseType = caseItem => caseItem.source_path.startsWith('test_websocket/') ? 'WebSocket' : 'API'
const scheduleScopeLabel = scope => ({ test_api: 'API 接口用例', test_websocket: 'WebSocket 用例', test_model: '模型用例', test_pay: '支付用例', test_scenario: '场景用例', all: '全部用例' }[scope] || scope)
const runStatusType = status => ({ COMPLETED: 'success', FAILED: 'danger', RUNNING: 'warning', PENDING: 'info', CANCELLED: 'info' }[status] || 'info')
const methodTagType = method => ({ GET: 'success', POST: 'warning', PUT: 'primary', PATCH: 'info', DELETE: 'danger' }[method] || 'info')

async function loadProjects() {
  projects.value = unwrap(await getAutomationProjects())
  if (!selectedProjectId.value && projects.value.length) selectedProjectId.value = projects.value[0].id
}

async function loadCases() {
  if (!selectedProjectId.value) return
  loading.value = true
  try {
    const [treeResponse, caseResponse] = await Promise.all([
      getAutomationSuiteTree(selectedProjectId.value),
      getAutomationCases({ project: selectedProjectId.value }),
    ])
    suiteTree.value = unwrap(treeResponse)
    cases.value = unwrap(caseResponse)
  } catch (error) {
    ElMessage.error('加载自动化用例失败')
  } finally {
    loading.value = false
  }
}

async function loadRuns() {
  if (!selectedProjectId.value) return
  loading.value = true
  try { setPaginatedItems(await getAutomationRuns({ project: selectedProjectId.value, page: pagination.runs.page, page_size: pagination.runs.pageSize }), runs, pagination.runs) } catch (error) { ElMessage.error('加载执行记录失败') } finally { loading.value = false }
}

async function loadReports() {
  if (!selectedProjectId.value) return
  loading.value = true
  try { setPaginatedItems(await getAutomationRuns({ project: selectedProjectId.value, has_report: true, page: pagination.reports.page, page_size: pagination.reports.pageSize }), reports, pagination.reports) } catch (error) { ElMessage.error('加载报告管理失败') } finally { loading.value = false }
}

async function loadConfigurations() {
  if (!selectedProjectId.value) return
  loading.value = true
  try { configurations.value = unwrap(await getAutomationConfigurations({ project: selectedProjectId.value })) } catch (error) { ElMessage.error('加载配置失败') } finally { loading.value = false }
}

async function loadEndpoints() {
  if (!selectedProjectId.value) return
  loading.value = true
  try { setPaginatedItems(await getAutomationEndpoints({ project: selectedProjectId.value, path: endpointPath.value, category: endpointCategory.value, page: pagination.interfaces.page, page_size: pagination.interfaces.pageSize }), endpoints, pagination.interfaces) } catch (error) { ElMessage.error('加载接口失败') } finally { loading.value = false }
}

function changeEndpointCategory() {
  pagination.interfaces.page = 1
  loadEndpoints()
}

function resetEndpointPage() {
  pagination.interfaces.page = 1
  loadEndpoints()
}

async function loadSchemaStatus() {
  if (!selectedProjectId.value) return
  schemaLoading.value = true
  try { schemaStatus.value = (await getAutomationSchemaStatus({ project: selectedProjectId.value })).data } catch (error) { ElMessage.error('加载 Schema 状态失败') } finally { schemaLoading.value = false }
}

async function regenerateSchemas() {
  if (!selectedProjectId.value) return
  schemaGenerating.value = true
  try {
    const result = (await regenerateAutomationSchemas({ project: selectedProjectId.value })).data
    const catalogMessage = result.catalog
      ? `，接口目录：新增 ${result.catalog.created}，更新 ${result.catalog.updated}，删除 ${result.catalog.deleted}`
      : ''
    ElMessage.success(`已生成 ${result.schema_count} 条 Schema${catalogMessage}`)
    pagination.interfaces.page = 1
    await Promise.all([loadEndpoints(), loadSchemaStatus()])
  } catch (error) { ElMessage.error(error.response?.data?.error || '重新生成 Schema 失败') } finally { schemaGenerating.value = false }
}

async function loadCoverage() {
  if (!selectedProjectId.value) return
  loading.value = true
  try { coverage.value = (await getAutomationCoverage({ project: selectedProjectId.value })).data } catch (error) { ElMessage.error('加载覆盖统计失败') } finally { loading.value = false }
}

async function loadPage() {
  stopLogRefresh()
  selectedSuiteId.value = null
  selectedSuiteName.value = ''
  if (props.mode === 'cases' || props.mode === 'dashboard') await loadCases()
  if (props.mode === 'cases') await loadConfigurations()
  if (props.mode === 'interfaces') await Promise.all([loadEndpoints(), loadSchemaStatus()])
  if (props.mode === 'coverage') await loadCoverage()
  if (props.mode === 'runs' || props.mode === 'dashboard') await loadRuns()
  if (props.mode === 'reports') await loadReports()
  if (props.mode === 'configurations') await loadConfigurations()
  if (props.mode === 'schedules') {
    await Promise.all([loadSchedules(), loadConfigurations()])
  }
  if (props.mode === 'notifications') await loadNotifications()
  if (props.mode === 'logs') {
    await loadLogs()
    logRefreshTimer = setInterval(loadLogs, 2000)
  }
}

function onProjectChange() {
  for (const page of Object.values(pagination)) page.page = 1
  loadPage()
}

function selectSuite(suite) { selectedSuiteId.value = suite.id; selectedSuiteName.value = suite.source_path }
function onCaseSelection(selectedCases) { selectedCaseIds.value = selectedCases.map(caseItem => caseItem.id) }
function goTo(name) { router.push(`/api-automation/${name}`) }

function findSuite(suites, suiteId) {
  for (const suite of suites) {
    if (suite.id === suiteId) return suite
    const childSuite = findSuite(suite.children || [], suiteId)
    if (childSuite) return childSuite
  }
  return null
}

function collectSuiteIds(suite, suiteIds) {
  suiteIds.add(suite.id)
  for (const childSuite of suite.children || []) collectSuiteIds(childSuite, suiteIds)
}

function suiteCaseCount(suite) {
  return (suite.cases || []).length + (suite.children || []).reduce(
    (total, childSuite) => total + suiteCaseCount(childSuite),
    0,
  )
}

async function startSelectedCases() {
  if (!executionConfigurationId.value) {
    ElMessage.warning('请选择运行配置')
    return
  }
  starting.value = true
  try {
    await startAutomationRun({
      project_id: selectedProjectId.value,
      configuration_id: executionConfigurationId.value,
      selection: { case_ids: selectedCaseIds.value },
    })
    ElMessage.success('执行任务已提交')
    selectedCaseIds.value = []
  } catch (error) {
    ElMessage.error('提交执行任务失败，请先创建运行配置')
  } finally { starting.value = false }
}

async function startVisibleCases() {
  selectedCaseIds.value = visibleCases.value.map(caseItem => caseItem.id)
  await startSelectedCases()
}

const cloneConfigurationValue = value => value && typeof value === 'object' ? structuredClone(toRaw(value)) : {}

function normalizeAuthenticationProfiles(value) {
  const profiles = cloneConfigurationValue(value)
  Object.entries(profiles).forEach(([role, profile]) => {
    profiles[role] = {
      ...(profile && typeof profile === 'object' ? profile : {}),
      username: profile?.username || '',
      password: profile?.password || '',
      role: profile?.role || role.toUpperCase(),
      password_mode: profile?.password_mode || 'argon2_network',
      is_default_role: Boolean(profile?.is_default_role),
    }
  })
  return profiles
}

function normalizePaymentConfiguration(value) {
  const payment = cloneConfigurationValue(value)
  payment.headers = payment.headers && typeof payment.headers === 'object' ? payment.headers : {}
  payment.mock_base_url = payment.mock_base_url || ''
  payment.stripe_api_key = payment.stripe_api_key || ''
  payment.webhook_mode = payment.webhook_mode || 'stripe_cli'
  return payment
}

function normalizeModelProfiles(value) {
  const profiles = cloneConfigurationValue(value)
  Object.entries(profiles).forEach(([name, profile]) => {
    profiles[name] = {
      ...(profile && typeof profile === 'object' ? profile : {}),
      url: profile?.url || '',
      model: profile?.model || '',
    }
  })
  return profiles
}

function normalizeRuntimeSettings(value) {
  const runtime = cloneConfigurationValue(value)
  runtime.api = runtime.api && typeof runtime.api === 'object' ? runtime.api : {}
  runtime.test = runtime.test && typeof runtime.test === 'object' ? runtime.test : {}
  runtime.api.retry = Number.isFinite(runtime.api.retry) ? runtime.api.retry : 1
  runtime.api.retry_interval = Number.isFinite(runtime.api.retry_interval) ? runtime.api.retry_interval : 1
  runtime.test.markers = runtime.test.markers || ''
  runtime.test.suite = runtime.test.suite || ''
  runtime.test.max_workers = Number.isFinite(runtime.test.max_workers) ? runtime.test.max_workers : 1
  runtime.test.parallel = Boolean(runtime.test.parallel)
  runtime.test.ignore_list = normalizeIgnoreList(runtime.test.ignore_list)
  runtime.test.timeout = runtime.test.timeout && typeof runtime.test.timeout === 'object' ? runtime.test.timeout : {}
  runtime.test.timeout.case = Number.isFinite(runtime.test.timeout.case) ? runtime.test.timeout.case : 300
  runtime.test.timeout.function = Number.isFinite(runtime.test.timeout.function) ? runtime.test.timeout.function : 60
  runtime.test.timeout.setup = Number.isFinite(runtime.test.timeout.setup) ? runtime.test.timeout.setup : 180
  runtime.test.timeout.teardown = Number.isFinite(runtime.test.timeout.teardown) ? runtime.test.timeout.teardown : 180
  runtime.test.cleanup = runtime.test.cleanup && typeof runtime.test.cleanup === 'object' ? runtime.test.cleanup : {}
  runtime.test.cleanup.enabled = runtime.test.cleanup.enabled !== false
  runtime.test.cleanup.after_test = runtime.test.cleanup.after_test !== false
  runtime.test.cleanup.after_suite = runtime.test.cleanup.after_suite !== false
  runtime.test.cleanup.after_session = runtime.test.cleanup.after_session !== false
  return runtime
}

function parseTestMarkers(value) {
  return String(value || '').split(/\s+or\s+|,/i).map(marker => marker.trim()).filter(Boolean)
}

function normalizeIgnoreList(value) {
  if (Array.isArray(value)) return value.flatMap(item => normalizeIgnoreList(item))
  const raw = String(value || '').trim().replace(/^[-*]\s*/, '')
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed.flatMap(item => normalizeIgnoreList(item))
  } catch (error) {
    // Plain globs and comma-separated legacy values are handled below.
  }
  return raw.split(/[\n,]/).map(item => item.trim().replace(/^['"]|['"]$/g, '')).filter(Boolean)
}

function setDefaultAuthenticationProfile(role) {
  Object.entries(authenticationProfiles.value).forEach(([name, profile]) => {
    profile.is_default_role = name === role
  })
}

function applyLegacyDefaultRole(profiles, legacyRole) {
  if (Object.values(profiles).some(profile => profile.is_default_role) || !profiles[legacyRole]) return
  profiles[legacyRole].is_default_role = true
}

function synchronizeLegacyVariables(variables, profiles, runtime, environment, salt) {
  delete variables.MAIN_KEY
  delete variables.BACKUP_KEY
  delete variables.default_role
  variables.ENV = environment
  variables.SALT = salt || ''
  variables.MARKERS = runtime.test.markers || ''
  variables.IGNORE_LIST = JSON.stringify(runtime.test.ignore_list)
  Object.entries(authenticationVariableBindings).forEach(([role, [usernameKey, passwordKey]]) => {
    const profile = profiles[role]
    if (!profile) return
    variables[usernameKey] = profile.username || ''
    variables[passwordKey] = profile.password || ''
  })
}

async function addAuthenticationProfile() {
  try {
    const { value } = await ElMessageBox.prompt('输入角色名称，例如 qa_admin。', '添加认证角色', { inputPattern: /^[A-Za-z][A-Za-z0-9_]{1,49}$/, inputErrorMessage: '角色名称只能包含字母、数字和下划线。' })
    const role = value.trim().toLowerCase()
    if (authenticationProfiles.value[role]) {
      ElMessage.warning('该认证角色已存在')
      return
    }
    authenticationProfiles.value[role] = { username: '', password: '', role: role.toUpperCase(), password_mode: 'argon2_network' }
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('添加认证角色失败')
  }
}

function removeAuthenticationProfile(role) {
  delete authenticationProfiles.value[role]
}

async function addConfigurationVariable() {
  try {
    const { value } = await ElMessageBox.prompt('输入变量名称，例如 API_TOKEN。', '添加环境变量', { inputPattern: /^[A-Za-z_][A-Za-z0-9_]{0,99}$/, inputErrorMessage: '变量名称只能包含字母、数字和下划线。' })
    const key = value.trim()
    if (Object.prototype.hasOwnProperty.call(configurationVariables.value, key)) {
      ElMessage.warning('该环境变量已存在')
      return
    }
    configurationVariables.value[key] = ''
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('添加环境变量失败')
  }
}

function removeConfigurationVariable(key) {
  delete configurationVariables.value[key]
}

async function addIgnoreItem() {
  try {
    const { value } = await ElMessageBox.prompt('输入测试文件、目录或匹配模式，例如 tests/*_example.py。', '追加忽略项', { inputPattern: /\S+/, inputErrorMessage: '忽略项不能为空。' })
    const items = normalizeIgnoreList(value)
    runtimeSettings.value.test.ignore_list = [...new Set([...runtimeSettings.value.test.ignore_list, ...items])]
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('追加忽略项失败')
  }
}

function openConfigurationDialog(configuration = null) {
  editingConfiguration.value = configuration
  configurationDialogTab.value = 'connection'
  configurationForm.value = configuration ? { ...configuration, salt: configuration.variables?.SALT || '', http_schema_enabled: Boolean(configuration.runtime_settings?.test?.validation?.http_schema_enabled), http_schema_failure_mode: configuration.runtime_settings?.test?.validation?.http_schema_failure_mode || 'strict', main_device_key: '', backup_device_key: '' } : { name: '', environment: 'custom', salt: '', base_url: '', websocket_url: '', timeout_seconds: 30, is_default: false, http_schema_enabled: false, http_schema_failure_mode: 'strict', main_device_key: '', backup_device_key: '', has_main_device_key: false, has_backup_device_key: false }
  configurationVariables.value = cloneConfigurationValue(configuration?.variables)
  authenticationProfiles.value = normalizeAuthenticationProfiles(configuration?.auth_profiles)
  paymentConfiguration.value = normalizePaymentConfiguration(configuration?.payment_config)
  modelProfiles.value = normalizeModelProfiles(configuration?.model_profiles)
  runtimeSettings.value = normalizeRuntimeSettings(configuration?.runtime_settings)
  selectedTestMarkers.value = parseTestMarkers(runtimeSettings.value.test.markers || configurationVariables.value.MARKERS)
  if (!runtimeSettings.value.test.ignore_list.length) runtimeSettings.value.test.ignore_list = normalizeIgnoreList(configurationVariables.value.IGNORE_LIST)
  applyLegacyDefaultRole(authenticationProfiles.value, configurationVariables.value.default_role)
  const deviceCliSettings = configuration?.runtime_settings?.device_cli || {}
  deviceCliEnabled.value = Boolean(deviceCliSettings.enabled)
  deviceCliBlacklist.value = Array.isArray(deviceCliSettings.command_blacklist) ? [...deviceCliSettings.command_blacklist] : [...defaultDeviceCliBlacklist]
  configurationDialogVisible.value = true
}

function copyConfiguration() {
  const sourceConfiguration = configurations.value.find(configuration => configuration.id === copySourceConfigurationId.value)
  if (!sourceConfiguration) return
  const { id, project, variables, auth_profiles, payment_config, model_profiles, runtime_settings, ...formValues } = sourceConfiguration
  editingConfiguration.value = null
  configurationForm.value = {
    ...formValues,
    name: `${sourceConfiguration.name} 副本`,
    environment: `${sourceConfiguration.environment}-copy`,
    salt: sourceConfiguration.variables?.SALT || '',
    is_default: false,
    http_schema_enabled: Boolean(sourceConfiguration.runtime_settings?.test?.validation?.http_schema_enabled),
    http_schema_failure_mode: sourceConfiguration.runtime_settings?.test?.validation?.http_schema_failure_mode || 'strict',
    main_device_key: '',
    backup_device_key: '',
    has_main_device_key: false,
    has_backup_device_key: false,
  }
  configurationVariables.value = cloneConfigurationValue(sourceConfiguration.variables)
  authenticationProfiles.value = normalizeAuthenticationProfiles(sourceConfiguration.auth_profiles)
  paymentConfiguration.value = normalizePaymentConfiguration(sourceConfiguration.payment_config)
  modelProfiles.value = normalizeModelProfiles(sourceConfiguration.model_profiles)
  runtimeSettings.value = normalizeRuntimeSettings(sourceConfiguration.runtime_settings)
  selectedTestMarkers.value = parseTestMarkers(runtimeSettings.value.test.markers || configurationVariables.value.MARKERS)
  if (!runtimeSettings.value.test.ignore_list.length) runtimeSettings.value.test.ignore_list = normalizeIgnoreList(configurationVariables.value.IGNORE_LIST)
  applyLegacyDefaultRole(authenticationProfiles.value, configurationVariables.value.default_role)
  const deviceCliSettings = sourceConfiguration.runtime_settings?.device_cli || {}
  deviceCliEnabled.value = Boolean(deviceCliSettings.enabled)
  deviceCliBlacklist.value = Array.isArray(deviceCliSettings.command_blacklist) ? [...deviceCliSettings.command_blacklist] : [...defaultDeviceCliBlacklist]
  copyConfigurationDialogVisible.value = false
  copySourceConfigurationId.value = null
  configurationDialogTab.value = 'connection'
  ElMessage.success('已复制环境配置，请修改后保存')
}

async function saveConfiguration() {
  const variables = cloneConfigurationValue(configurationVariables.value)
  const authProfiles = normalizeAuthenticationProfiles(authenticationProfiles.value)
  const paymentConfig = normalizePaymentConfiguration(paymentConfiguration.value)
  const configuredModelProfiles = normalizeModelProfiles(modelProfiles.value)
  const configuredRuntimeSettings = normalizeRuntimeSettings(runtimeSettings.value)
  saving.value = true
  try {
    configuredRuntimeSettings.test = configuredRuntimeSettings.test || {}
    configuredRuntimeSettings.test.validation = configuredRuntimeSettings.test.validation || {}
    configuredRuntimeSettings.test.validation.http_schema_enabled = configurationForm.value.http_schema_enabled
    configuredRuntimeSettings.test.validation.http_schema_failure_mode = configurationForm.value.http_schema_failure_mode
    configuredRuntimeSettings.test.markers = selectedTestMarkers.value.join(' or ')
    configuredRuntimeSettings.device_cli = {
      ...(configuredRuntimeSettings.device_cli || {}),
      enabled: deviceCliEnabled.value,
      command_blacklist: deviceCliBlacklist.value.map(item => item.trim()).filter(Boolean),
    }
    synchronizeLegacyVariables(variables, authProfiles, configuredRuntimeSettings, configurationForm.value.environment, configurationForm.value.salt)
    const { http_schema_enabled, http_schema_failure_mode, salt, main_device_key, backup_device_key, has_main_device_key, has_backup_device_key, ...configurationValues } = configurationForm.value
    const payload = {
      ...configurationValues,
      project: selectedProjectId.value,
      variables,
      auth_profiles: authProfiles,
      payment_config: paymentConfig,
      model_profiles: configuredModelProfiles,
      runtime_settings: configuredRuntimeSettings,
    }
    if (main_device_key.trim()) payload.main_device_key = main_device_key.trim()
    if (backup_device_key.trim()) payload.backup_device_key = backup_device_key.trim()
    if (editingConfiguration.value) await updateAutomationConfiguration(editingConfiguration.value.id, payload)
    else await createAutomationConfiguration(payload)
    configurationDialogVisible.value = false
    await loadConfigurations()
    ElMessage.success('配置已保存')
  } catch (error) {
    const responseData = error.response?.data
    const message = responseData?.websocket_url?.[0] || responseData?.base_url?.[0] || responseData?.detail || '保存配置失败'
    ElMessage.error(message)
  } finally { saving.value = false }
}

async function loadConfigurationTemplate() {
  loadingTemplate.value = true
  try {
    const template = (await getAutomationConfigurationTemplate()).data
    configurationForm.value.base_url = template.api?.base_url || ''
    configurationForm.value.websocket_url = template.websocket?.url || ''
    configurationForm.value.timeout_seconds = template.api?.timeout || 30
    configurationForm.value.environment = template.env || 'custom'
    configurationForm.value.salt = ''
    configurationForm.value.http_schema_enabled = Boolean(template.test?.validation?.http_schema_enabled)
    configurationForm.value.http_schema_failure_mode = template.test?.validation?.http_schema_failure_mode || 'strict'
    configurationVariables.value = {
      data_endpoints: {},
      model_images: {},
    }
    authenticationProfiles.value = normalizeAuthenticationProfiles(template.auth?.users)
    applyLegacyDefaultRole(authenticationProfiles.value, String(template.api?.roles?.default_role || 'dealer').toLowerCase())
    paymentConfiguration.value = normalizePaymentConfiguration(template.payment)
    modelProfiles.value = normalizeModelProfiles(template.models)
    runtimeSettings.value = normalizeRuntimeSettings(template)
    selectedTestMarkers.value = parseTestMarkers(runtimeSettings.value.test.markers)
    deviceCliEnabled.value = false
    deviceCliBlacklist.value = [...defaultDeviceCliBlacklist]
    ElMessage.success('已加载测试配置模板，请补充变量引用后保存')
  } catch (error) { ElMessage.error('加载测试配置模板失败') } finally { loadingTemplate.value = false }
}

function addDeviceCliBlacklist() {
  deviceCliBlacklist.value.push('')
}

function removeDeviceCliBlacklist(index) {
  deviceCliBlacklist.value.splice(index, 1)
}

async function initializeConfiguration() {
  if (!selectedProjectId.value) return
  initializingConfiguration.value = true
  try {
    const configuration = (await initializeAutomationConfiguration({ project: selectedProjectId.value })).data
    await loadConfigurations()
    executionConfigurationId.value = configuration.id
    ElMessage.success('默认测试环境已创建，请补充变量引用后保存')
  } catch (error) { ElMessage.error('创建默认测试环境失败') } finally { initializingConfiguration.value = false }
}

async function removeConfiguration(configuration) {
  try {
    await ElMessageBox.confirm(`确定删除配置“${configuration.name}”吗？`, '删除配置', { type: 'warning' })
    await deleteAutomationConfiguration(configuration.id)
    await loadConfigurations()
    ElMessage.success('配置已删除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('删除配置失败')
  }
}

async function setDefaultConfiguration(configuration) {
  try {
    await ElMessageBox.confirm(`确定将“${configuration.name}”设为默认环境吗？后续新建运行会优先使用该环境。`, '设置默认环境', { type: 'warning' })
    await setAutomationDefaultConfiguration(configuration.id)
    await loadConfigurations()
    selectedConfiguration.value = null
    ElMessage.success(`已将“${configuration.name}”设为默认环境`)
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.response?.data?.error || '设置默认环境失败')
  }
}

function onConfigurationSelection(selectedConfigurations) {
  selectedConfiguration.value = selectedConfigurations.length === 1 ? selectedConfigurations[0] : null
}

const environmentRowClass = ({ row }) => row.is_default ? 'default-environment-row' : ''

async function deleteRun(run) {
  try {
    await ElMessageBox.confirm(`确定删除运行记录 #${run.id} 吗？相关用例结果和报告链接将一并删除。`, '删除执行记录', { type: 'warning' })
    await deleteAutomationRun(run.id)
    await loadRuns()
    ElMessage.success('执行记录已删除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.response?.data?.error || '删除执行记录失败')
  }
}

async function loadSchedules() {
  loading.value = true
  try { setPaginatedItems(await getAutomationSchedules({ page: pagination.schedules.page, page_size: pagination.schedules.pageSize }), schedules, pagination.schedules) } catch (error) { ElMessage.error('加载定时任务失败') } finally { loading.value = false }
}

async function pauseSchedule(schedule) {
  try {
    await toggleAutomationSchedule(schedule.id, 'pause')
    await loadSchedules()
    ElMessage.success('定时任务已暂停')
  } catch (error) {
    ElMessage.error('暂停定时任务失败')
  }
}

async function resumeSchedule(schedule) {
  try {
    await toggleAutomationSchedule(schedule.id, 'resume')
    await loadSchedules()
    ElMessage.success('定时任务已恢复')
  } catch (error) {
    ElMessage.error('恢复定时任务失败')
  }
}

async function loadNotifications() {
  if (!selectedProjectId.value) return
  loading.value = true
  try { setPaginatedItems(await getAutomationNotificationLogs({ project: selectedProjectId.value, page: pagination.notifications.page, page_size: pagination.notifications.pageSize }), notifications, pagination.notifications) } catch (error) { ElMessage.error('加载通知记录失败') } finally { loading.value = false }
}

function changePageSize(listName, load) {
  pagination[listName].page = 1
  load()
}

async function loadLogs() {
  logLoading.value = true
  try {
    logMonitor.value = (await getAutomationLogs()).data
    await nextTick()
    if (automationLog.value) automationLog.value.scrollTop = automationLog.value.scrollHeight
  } catch (error) {
    ElMessage.error('加载 API 自动化运行日志失败')
  } finally {
    logLoading.value = false
  }
}

async function saveSchedule() {
  if (!scheduleForm.value.name.trim()) { ElMessage.warning('请输入任务名称'); return }
  saving.value = true
  try {
    await createAutomationSchedule({
      name: scheduleForm.value.name,
      module: 'API_AUTOMATION',
      task_type: 'API_AUTOMATION_SUITE',
      schedule_type: scheduleForm.value.schedule_type,
      project_id: selectedProjectId.value,
      task_config: {
        configuration_id: scheduleForm.value.configuration_id,
        selection: scheduleForm.value.source_path_prefix === 'all' ? {} : { source_path_prefix: scheduleForm.value.source_path_prefix },
      },
      minutes: scheduleForm.value.schedule_type === 'I' ? scheduleForm.value.minutes : null,
      cron: scheduleForm.value.schedule_type === 'C' ? scheduleForm.value.cron : '',
      notify_on_success: scheduleForm.value.notify_on_success,
      notify_on_failure: scheduleForm.value.notify_on_failure,
    })
    scheduleDialogVisible.value = false
    scheduleForm.value = { name: '', schedule_type: 'I', minutes: 60, cron: '', configuration_id: null, source_path_prefix: 'test_api', notify_on_success: false, notify_on_failure: true }
    await loadSchedules()
    ElMessage.success('定时任务已创建')
  } catch (error) { ElMessage.error('创建定时任务失败') } finally { saving.value = false }
}

async function refreshSelectedRun() {
  if (!selectedRun.value) return
  try {
    const run = (await getAutomationRun(selectedRun.value.id)).data
    selectedRun.value = run
    const index = runs.value.findIndex(item => item.id === run.id)
    if (index >= 0) runs.value.splice(index, 1, run)
    if (!['PENDING', 'RUNNING'].includes(run.status)) stopRunProgressRefresh()
  } catch (error) {
    stopRunProgressRefresh()
  }
}

function stopRunProgressRefresh() {
  if (runProgressTimer) clearInterval(runProgressTimer)
  runProgressTimer = null
}

function stopLogRefresh() {
  if (logRefreshTimer) clearInterval(logRefreshTimer)
  logRefreshTimer = null
}

function showRunDetail(run) {
  selectedRun.value = run
  runDetailVisible.value = true
  refreshSelectedRun()
  stopRunProgressRefresh()
  if (['PENDING', 'RUNNING'].includes(run.status)) runProgressTimer = setInterval(refreshSelectedRun, 2000)
}

function runReportUrl(run) {
  return run.report_path ? `/media/api-automation/${run.report_path}` : ''
}

onMounted(async () => { await loadProjects(); await loadPage() })

watch(
  () => props.mode,
  async () => {
    await loadPage()
  },
)

watch(runDetailVisible, visible => {
  if (!visible) stopRunProgressRefresh()
})

onBeforeUnmount(() => {
  stopRunProgressRefresh()
  stopLogRefresh()
})
</script>

<style scoped>
.workspace { padding: 24px; min-height: 100%; background: #f4f7fb; }
.config-dialog-intro { margin: -4px 0 16px; padding: 10px 12px; border-left: 3px solid #1677ff; background: #f0f7ff; color: #526170; font-size: 13px; line-height: 1.6; }.config-tabs :deep(.el-tabs__header) { margin-bottom: 18px; }.config-form { padding: 0 2px; }.config-grid { display: grid; grid-template-columns: minmax(0, 1fr) 190px; gap: 0 16px; }.config-grid .full-row { grid-column: 1 / -1; }.config-form :deep(.el-form-item__label) { padding-bottom: 6px; color: #344054; font-size: 13px; font-weight: 600; }.config-form :deep(.el-input-number) { width: 100%; }.config-switches { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 8px; }.config-switches > div { display: grid; grid-template-columns: 1fr auto; align-items: center; gap: 4px 12px; padding: 14px; border: 1px solid #e4e7ec; border-radius: 6px; background: #f8fafc; }.config-switches strong { color: #344054; font-size: 13px; }.config-switches span { color: #667085; font-size: 12px; }.config-switches :deep(.el-switch) { grid-column: 2; grid-row: 1 / span 2; }.schema-failure-mode { grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 8px; padding-top: 10px; border-top: 1px solid #e4e7ec; }.schema-failure-mode label { color: #475467; font-size: 12px; font-weight: 600; }.schema-failure-mode :deep(.el-select) { width: 140px; }.config-code-input :deep(.el-textarea__inner) { min-height: 160px; border-color: #d0d5dd; background: #101828; color: #d0d5dd; font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: 12px; line-height: 1.6; }.runtime-code-input :deep(.el-textarea__inner) { min-height: 420px; }.config-dialog-footer { display: flex; align-items: center; justify-content: space-between; width: 100%; }.config-dialog-footer > div { display: flex; gap: 8px; }
.environment-config-dialog :deep(.el-dialog__body) { max-height: min(72vh, 720px); overflow: auto; }.config-tabs :deep(.el-tabs__header) { padding-bottom: 8px; border-bottom: 1px solid #e4e7ec; }.config-tabs :deep(.el-tabs__item) { height: 40px; padding: 0 14px; color: #667085; font-weight: 600; }.config-tabs :deep(.el-tabs__item.is-active) { color: #1677ff; }.config-grid { grid-template-columns: minmax(0, 1fr) 180px 150px; }.form-section-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 2px 0 16px; padding-bottom: 12px; border-bottom: 1px solid #eaecf0; }.form-section-header h3 { margin: 0; color: #1d2939; font-size: 15px; }.form-section-header span { display: block; margin-top: 4px; color: #667085; font-size: 12px; }.form-section-header code { color: #0f766e; font-family: "SFMono-Regular", Consolas, monospace; }.variable-heading, .model-heading { margin-top: 24px; }.credential-grid, .model-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }.credential-card, .model-card { padding: 14px; border: 1px solid #dbe6f0; border-radius: 6px; background: #fbfdff; }.credential-card.is-default-role { border-color: #8ad5b0; background: #effaf3; }.credential-card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; color: #175cd3; }.credential-card-head > div:first-child { display: flex; align-items: center; gap: 8px; }.credential-actions { display: flex; align-items: center; gap: 6px; }.credential-card-head strong, .model-card > strong { font-size: 13px; }.credential-card :deep(.el-form-item), .model-card :deep(.el-form-item) { margin-bottom: 10px; }.credential-card :deep(.el-form-item:last-child), .model-card :deep(.el-form-item:last-child) { margin-bottom: 0; }.credential-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 12px; }.service-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 300px)); gap: 0 16px; justify-content: start; }.runtime-strategy-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 150px)); gap: 0 14px; justify-content: start; }.runtime-filter-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 210px)); gap: 0 14px; justify-content: start; }.timeout-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 150px)); gap: 0 14px; justify-content: start; }.runtime-strategy-grid :deep(.el-input-number), .runtime-filter-grid :deep(.el-select), .runtime-filter-grid :deep(.el-input), .timeout-grid :deep(.el-input-number) { width: 100%; }.global-salt-field { max-width: 460px; }.variable-editor { display: grid; gap: 8px; }.variable-row { display: grid; grid-template-columns: minmax(130px, .45fr) minmax(0, 1fr) auto; gap: 8px; align-items: center; }.structured-variable { display: flex; align-items: center; justify-content: space-between; padding: 9px 10px; border: 1px dashed #d0d5dd; border-radius: 4px; color: #667085; font-size: 12px; }.service-grid :deep(.el-select), .timeout-grid :deep(.el-input-number) { width: 100%; }.cleanup-options { display: flex; flex-wrap: wrap; gap: 12px 20px; padding: 12px; border: 1px solid #dbe6f0; border-radius: 6px; background: #f6fbff; }.config-dialog-footer { position: static; margin: 0; padding: 0; border: 0; background: transparent; }
.runtime-panels { display: grid; gap: 20px; padding-top: 8px; }.runtime-panel { position: relative; padding: 22px 16px 14px; border: 1px solid #dbe6f0; border-radius: 6px; }.runtime-panel-title { position: absolute; top: -12px; left: 50%; padding: 0 12px; color: #1d2939; font-size: 14px; font-weight: 700; line-height: 24px; transform: translateX(-50%); }.execution-panel { border-left: 3px solid #3b82f6; background: #fbfdff; }.execution-panel .runtime-panel-title { background: #fbfdff; }.filter-panel { border-left: 3px solid #0f9f8b; background: #f7fdfa; }.filter-panel .runtime-panel-title { background: #f7fdfa; }.lifecycle-panel { border-left: 3px solid #e6a23c; background: #fffdf8; }.lifecycle-panel .runtime-panel-title { background: #fffdf8; }.runtime-panel :deep(.el-form-item) { margin-bottom: 0; }.runtime-strategy-grid, .runtime-filter-grid, .timeout-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0 12px; }.runtime-filter-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }.runtime-panel :deep(.el-input-number), .runtime-panel :deep(.el-select), .runtime-panel :deep(.el-input) { width: 100%; }.cleanup-options { margin-top: 12px; background: #fff; }.salt-row { display: grid; grid-template-columns: 72px minmax(0, 420px); align-items: center; gap: 12px; margin: 0 0 14px; padding: 10px 12px; border: 1px solid #dbe6f0; border-radius: 6px; background: #f8fafc; }.salt-row > span { color: #344054; font-size: 13px; font-weight: 700; }.device-cli-switch { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; padding: 14px; border: 1px solid #d0d5dd; border-radius: 6px; background: #f8fafc; }.device-cli-switch strong { display: block; color: #344054; font-size: 13px; }.device-cli-switch span { display: block; max-width: 580px; margin-top: 4px; color: #667085; font-size: 12px; line-height: 1.5; }.blacklist-editor { display: grid; gap: 8px; width: 100%; }.blacklist-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; }
.runtime-panels { gap: 14px; padding-top: 0; }.runtime-panel { position: static; padding: 16px; }.runtime-panel-title { display: none; }.runtime-panel-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid #dbe6f0; }.runtime-panel-head span { color: #1d2939; font-size: 18px; font-weight: 800; }.execution-panel .runtime-panel-head span { color: #1d4ed8; }.filter-panel .runtime-panel-head span { color: #0f766e; }.lifecycle-panel .runtime-panel-head span { color: #b45309; }.runtime-panel :deep(.el-form-item__label) { color: #526170; font-size: 12px; font-weight: 600; }
.run-progress { margin-top: 16px; }
.run-progress-head { display: flex; justify-content: space-between; margin-bottom: 8px; color: #475467; font-size: 13px; }
.current-case { margin: 8px 0 0; color: #475467; font-size: 13px; }
.list-pagination { display: flex; justify-content: flex-end; margin-top: 16px; }
.path-search { max-width: 440px; }.interface-toolbar { gap: 12px; }.schema-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 8px; }.schema-summary { margin: -4px 0 14px; color: #667085; font-size: 13px; }
.log-monitor-panel { min-height: 620px; }
.log-actions { display: flex; align-items: center; gap: 8px; }
.log-meta, .log-updated { margin: 4px 0 0; color: #667085; font-size: 13px; }
.automation-log { box-sizing: border-box; min-height: 500px; max-height: calc(100vh - 280px); width: 100%; margin: 16px 0 0; padding: 16px; overflow: auto; border: 1px solid #d0d5dd; background: #101828; color: #d0d5dd; font: 12px/1.6 "SFMono-Regular", Consolas, "Liberation Mono", monospace; white-space: pre-wrap; }
.environment-name { color: #1d2939; font-weight: 600; }.environment-table-actions { display: flex; align-items: center; gap: 8px; }
.environment-actions { display: flex; justify-content: center; gap: 8px; }
.environment-action { width: 30px; height: 30px; margin: 0; border-radius: 6px; }
.environment-action.default { border-color: #abefc6; color: #039855; background: #ecfdf3; }
.environment-action.default:hover { border-color: #039855; color: #fff; background: #039855; }
.environment-action.edit { border-color: #b2ddff; color: #1570ef; background: #f0f7ff; }
.environment-action.edit:hover { border-color: #1570ef; color: #fff; background: #1570ef; }
.environment-action.delete { border-color: #fecdca; color: #d92d20; background: #fff5f4; }
.environment-action.delete:hover { border-color: #d92d20; color: #fff; background: #d92d20; }
.workspace :deep(.default-environment-row > td.el-table__cell) { background: #eff8ff !important; }
.workspace :deep(.default-environment-row .environment-name) { color: #175cd3; }
.workspace-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 20px; }
.workspace-header h2 { margin: 0; color: #1c2b3a; font-size: 22px; font-weight: 700; }
.workspace-header p { margin: 6px 0 0; color: #667085; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.header-actions .el-select { width: 230px; }
.panel { background: #fff; border: 1px solid #e4eaf1; padding: 18px; }
.panel-title { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.panel-title h3 { margin: 0; font-size: 16px; color: #22313f; }
.stats-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.stat-block { min-height: 108px; padding: 18px; border-left: 5px solid; background: #fff; display: flex; flex-direction: column; justify-content: center; }
.stat-block span { font-size: 30px; font-weight: 700; color: #1b2a39; }
.stat-block small { margin-top: 6px; color: #667085; font-size: 13px; }
.cyan { border-color: #0ea5a8; }.green { border-color: #22a06b; }.amber { border-color: #dc8d19; }.red { border-color: #d14343; }
.overview-panel { margin-top: 18px; }.overview-panel h3 { margin-top: 0; }.overview-panel p { max-width: 760px; color: #526170; line-height: 1.7; }
.case-layout { display: grid; grid-template-columns: minmax(250px, 28%) 1fr; gap: 16px; }.case-tree-panel { min-height: 560px; }.tree-node { display: inline-flex; align-items: center; gap: 7px; }.tree-node em { color: #8896a5; font-size: 12px; font-style: normal; }
.marker { margin-right: 4px; }.result-table { margin-top: 18px; }
.coverage-panel { margin-top: 18px; }.coverage-chart { width: 100%; height: 340px; }
.report-tabs { margin-top: 18px; }.runner-log { max-height: 300px; overflow: auto; white-space: pre-wrap; margin: 0; padding: 12px; background: #f6f8fa; color: #253342; }
@media (max-width: 900px) { .workspace-header { flex-direction: column; }.stats-grid { grid-template-columns: repeat(2, 1fr); }.case-layout { grid-template-columns: 1fr; } }
</style>