import React from "react";

export default function ConsolePage({
  consoleTab,
  dashboard,
  currentNovel,
  jobList,
  novels,
  activeErrorJobs,
  selectedApiProfile,
  setSelectedApiProfile,
  selectedApiLabel,
  api,
  updateSelectedApi,
  currentMainApiPath,
  normalizeMainApiPath,
  mainApiPathOptions,
  currentMainApiOption,
  reasoningEffortOptions,
  defaultExportPath,
  setDefaultExportPath,
  handlePickExportDirectory,
  targetWordOptions,
  defaultTargetWords,
  setDefaultTargetWords,
  createStoryPlan,
  testingApi,
  busy,
  testCurrentApiConfig,
  saveConfig,
  logs,
  clearLogs,
}) {
  if (consoleTab === "dashboard") {
    return (
      <section className="dashboard-columns">
        <div className="dashboard-column">
          <div className="panel dashboard-panel dashboard-top-panel">
            <h2>数据看板</h2>
            <div className="stats dashboard-stats">
              <div><span>小说</span><strong>{dashboard ? dashboard.novels : 0}</strong></div>
              <div><span>事件</span><strong>{dashboard ? dashboard.events : 0}</strong></div>
              <div><span>章节</span><strong>{dashboard ? dashboard.chapters : 0}</strong></div>
              <div><span>进行中任务</span><strong>{dashboard ? dashboard.running_jobs : 0}</strong></div>
            </div>
          </div>
          <div className="panel dashboard-panel dashboard-bottom-panel">
            <h2>错误记录</h2>
            <div className="panel-table fixed-table-height fixed-panel-table">
              <div className="table-header five-col">
                <span>任务</span><span>小说</span><span>阶段</span><span>错误</span><span>时间</span>
              </div>
              {activeErrorJobs.slice(0, 20).map((job) => (
                <div key={`dash-error-${job.job_id}`} className="table-row five-col row-failed">
                  <span>{job.job_id.slice(0, 6)}</span>
                  <span>{novels.find((n) => n.id === job.novel_id)?.title || "-"}</span>
                  <span>{job.step_label || "-"}</span>
                  <span title={job.error || job.message || ""}>{job.error || job.message || "未记录错误"}</span>
                  <span>{job.updated_at ? String(job.updated_at).replace("T", " ").slice(0, 16) : "-"}</span>
                </div>
              ))}
              {activeErrorJobs.length === 0 && <div className="table-empty">暂无错误记录</div>}
            </div>
          </div>
        </div>
        <div className="dashboard-column">
          <div className="panel dashboard-panel dashboard-top-panel dashboard-summary-panel">
            <h2>概览摘要</h2>
            <div className="stats compact-stats dashboard-stats">
              <div><span>当前小说</span><strong>{currentNovel?.title || "未选择"}</strong></div>
              <div><span>最近任务</span><strong>{jobList[0]?.step_label || "暂无"}</strong></div>
              <div><span>最近失败</span><strong>{activeErrorJobs.length}</strong></div>
            </div>
          </div>
          <div className="panel dashboard-panel dashboard-bottom-panel">
            <h2>最近任务</h2>
            <div className="panel-table fixed-table-height fixed-panel-table">
              <div className="table-header five-col">
                <span>任务</span><span>小说</span><span>阶段</span><span>状态</span><span>时间</span>
              </div>
              {jobList.slice(0, 20).map((job) => (
                <div key={`dash-job-${job.job_id}`} className="table-row five-col">
                  <span>{job.job_id.slice(0, 6)}</span>
                  <span>{novels.find((n) => n.id === job.novel_id)?.title || "-"}</span>
                  <span>{job.step_label || "-"}</span>
                  <span>{job.status || "-"}</span>
                  <span>{job.updated_at ? String(job.updated_at).replace("T", " ").slice(0, 16) : "-"}</span>
                </div>
              ))}
              {jobList.length === 0 && <div className="table-empty">暂无任务</div>}
            </div>
          </div>
        </div>
      </section>
    );
  }

  if (consoleTab === "api") {
    const isOpenAiCompatible = selectedApiProfile === "openai_compatible";
    const effectiveReasoningEffort = isOpenAiCompatible
      ? "default"
      : api.model_reasoning_effort || "default";
    const effectiveMainApiPath = isOpenAiCompatible ? "chat/completions" : currentMainApiPath;
    const effectiveMainApiOption =
      mainApiPathOptions.find((item) => item.value === effectiveMainApiPath) || currentMainApiOption;
    return (
      <section className="grid two-column-focus api-grid">
        <div className="panel">
          <h2>API 设置</h2>
          <div className="hint">当前正在编辑：{selectedApiLabel}</div>
          <div className="drawer-grid api-form-grid">
            <label>
              当前配置
              <select value={selectedApiProfile} onChange={(e) => setSelectedApiProfile(e.target.value)}>
                <option value="openai_compatible">OPENAI标准配置</option>
                <option value="codex_cli">OPENAI自定义配置</option>
              </select>
            </label>
            <label className={isOpenAiCompatible ? "disabled-setting-item" : ""}>
              Reasoning Effort
              <select
                value={effectiveReasoningEffort}
                onChange={(e) => updateSelectedApi({ model_reasoning_effort: e.target.value })}
                disabled={isOpenAiCompatible}
              >
                {reasoningEffortOptions.map((option) => <option key={option.label} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label className="drawer-span-2">Base URL<input value={api.base_url} onChange={(e) => updateSelectedApi({ base_url: e.target.value })} placeholder="https://api.openai.com/v1" /></label>
            <label className="drawer-span-2">API Key<input value={api.api_key} onChange={(e) => updateSelectedApi({ api_key: e.target.value })} placeholder="sk-..." type="password" /></label>
            <label>模型名<input value={api.model} onChange={(e) => updateSelectedApi({ model: e.target.value })} placeholder="gpt-4o-mini" /></label>
            <label className={`toggle drawer-toggle ${isOpenAiCompatible ? "disabled-setting-item" : ""}`}>
              <input
                type="checkbox"
                checked={isOpenAiCompatible ? false : Boolean(api.use_stream)}
                onChange={(e) => updateSelectedApi({ use_stream: e.target.checked })}
                disabled={isOpenAiCompatible}
              />
              启用流式
            </label>
            <label className={`drawer-span-2 ${isOpenAiCompatible ? "disabled-setting-item" : ""}`}>
              主调用路径
              <select
                value={effectiveMainApiPath}
                onChange={(e) => updateSelectedApi({ main_api_path: normalizeMainApiPath(e.target.value) })}
                disabled={isOpenAiCompatible}
              >
                {mainApiPathOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
              <div className="hint">{effectiveMainApiOption.description}</div>
              <div className="hint">{effectiveMainApiOption.recommendation}</div>
            </label>
            <label className="drawer-span-2">
              默认导出路径
              <div className="inline-input-row">
                <input value={defaultExportPath} onChange={(e) => setDefaultExportPath(e.target.value)} placeholder="例如：F:\导出目录" />
                <button type="button" className="ghost" onClick={handlePickExportDirectory}>选择目录</button>
              </div>
            </label>
            <label className="drawer-span-2">
              默认新建小说目标字数
              <select value={targetWordOptions.includes(Number(defaultTargetWords) || 0) ? String(defaultTargetWords) : "custom"} onChange={(e) => {
                if (e.target.value === "custom") return;
                setDefaultTargetWords(Number(e.target.value) || 500000);
              }}>
                <option value="500000">50万</option>
                <option value="1000000">100万</option>
                <option value="1500000">150万</option>
                <option value="custom">自定义</option>
              </select>
              {!targetWordOptions.includes(Number(defaultTargetWords) || 0) && (
                <input type="number" min="10000" step="10000" value={defaultTargetWords || 500000} onChange={(e) => setDefaultTargetWords(Number(e.target.value) || 500000)} placeholder="请输入默认目标字数" />
              )}
              <div className="hint">新建小说统一使用这里的字数设置。预计总事件 {createStoryPlan.targetEventCount} / 开篇 {createStoryPlan.openingBreakthroughCount} / 发展 {createStoryPlan.openingBreakthroughCount + 1}-{createStoryPlan.developmentEndEventId} / 结局 {createStoryPlan.endingStartEventId}-{createStoryPlan.targetEventCount}</div>
            </label>
          </div>
          <div className="modal-actions">
            <button className="ghost" onClick={testCurrentApiConfig} disabled={testingApi || busy}>{testingApi ? "测试中..." : "测试当前配置"}</button>
            <button className="primary" onClick={saveConfig} disabled={busy || testingApi}>保存配置</button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="panel log-panel standalone-log-panel">
      <div className="section-heading">
        <div>
          <h2>日志记录</h2>
          <div className="hint">界面日志将保存在本地浏览器，重启服务后仍会保留，直到你主动清空。</div>
        </div>
        <div className="section-actions">
          <button className="ghost" onClick={clearLogs}>清空日志</button>
        </div>
      </div>
      <div className="log-box fixed-log-height">
        {logs.length === 0 ? <div className="log-empty">等待操作...</div> : logs.map((line, i) => <div key={i}>{line}</div>)}
      </div>
    </section>
  );
}
