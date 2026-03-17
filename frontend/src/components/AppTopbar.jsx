import React from "react";

export default function AppTopbar({
  novels,
  selectedNovel,
  setSelectedNovel,
  hasNovelSelection,
  redirectToCreateNovel,
  selectedApiLabel,
  currentApiModel,
  currentApiBaseUrl,
  theme,
  setTheme,
  currentNovel,
  storyPhaseLabels,
}) {
  const displayApiModel = String(currentApiModel || "").trim() || "未设置";
  const displayApiBaseUrl = String(currentApiBaseUrl || "").trim() || "未设置";
  return (
    <header className="topbar panel">
      <div className="topbar-main">
        <div className="topbar-title">
          <p className="overline">极文造物</p>
          <div className="topbar-title-line">
            <h1>极文造物 · 管理与生产台</h1>
            <div className="topbar-badge">
              <strong className="topbar-badge-title">{selectedApiLabel || "-"}</strong>
              <div className="topbar-badge-model">{displayApiModel}</div>
              <div className="topbar-badge-url" title={displayApiBaseUrl}>
                {displayApiBaseUrl}
              </div>
            </div>
          </div>
        </div>
        <div className="topbar-actions topbar-actions-stack">
          <div className="control-row">
            <span className="control-label">小说选择</span>
            <select
              className="control-input control-field"
              value={selectedNovel || ""}
              onChange={(e) => setSelectedNovel(e.target.value || null)}
            >
              <option value="">未选择</option>
              {novels.map((novel) => (
                <option key={novel.id} value={novel.id}>
                  {novel.title}
                </option>
              ))}
            </select>
            <span className="control-label">快捷操作</span>
            <button
              className="ghost action-button control-input control-field"
              onClick={redirectToCreateNovel}
            >
              前往“创建小说”
            </button>
          </div>
          <div className="control-row">
            <span className="control-label">当前小说</span>
            <div className="control-input control-field control-display">
              {currentNovel?.title || "未选择"}
            </div>
            <span className="control-label">主题</span>
            <button
              className="ghost action-button control-input control-field"
              onClick={() => setTheme((prev) => (prev === "night" ? "paper" : "night"))}
            >
              切换主题：{theme === "night" ? "Night" : "Paper"}
            </button>
          </div>
        </div>
      </div>
      {currentNovel ? (
        <div className="topbar-meta">
          <span>{storyPhaseLabels[currentNovel.current_phase] || currentNovel.current_phase || "draft"}</span>
          <span>目标 {((currentNovel.target_words || 0) / 10000).toFixed(0)} 万字</span>
          <span>未回收伏笔 {currentNovel.foreshadow_active_count || 0}</span>
        </div>
      ) : (
        <div className="topbar-meta topbar-empty">
          <span className="topbar-hint-inline">
            未选择小说请点击右上角选择，或进入
            <button className="inline-link-button" onClick={redirectToCreateNovel}>“创建小说”</button>
          </span>
        </div>
      )}
    </header>
  );
}
