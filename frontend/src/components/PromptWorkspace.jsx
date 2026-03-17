import React from "react";

export default function PromptWorkspace({
  visiblePromptKeys,
  promptMenu,
  setPromptMenu,
  promptLabels,
  selectedNovel,
  promptScope,
  currentPromptMeta,
  promptValue,
  prompts,
  setPrompts,
  promptBackups,
  restorePromptBackup,
  savePrompts,
  resetCurrentPrompt,
  resetPrompts,
}) {
  return (
    <section className="grid prompt-grid">
      <div className="panel prompt-sidebar">
        <h2>提示词列表</h2>
        <div className="list">
          {visiblePromptKeys.map((key) => (
            <button key={key} className={promptMenu === key ? "list-item active" : "list-item"} onClick={() => setPromptMenu(key)}>
              {promptLabels[key] || key}
            </button>
          ))}
        </div>
      </div>
      <div className="panel prompt-editor-panel">
        <h2>提示词编辑</h2>
        <div className="hint">当前编辑：{promptLabels[promptMenu] || promptMenu}</div>
        <div className="hint">
          当前作用域：{selectedNovel ? `小说 ${selectedNovel}` : "默认提示词"}
          {selectedNovel ? ` / ${promptScope === "novel" ? "已使用小说独立提示词" : "当前仍继承默认提示词"}` : ""}
        </div>
        <div className="hint">变量通常放在 user_prompt 中，请用【XXX】标记，例如：[setting]。保存和恢复前都会自动备份。</div>
        <div className="hint">System Prompt：放稳定角色、硬规则、输出格式、禁止事项。</div>
        <textarea
          className="prompt-editor"
          rows={8}
          value={promptValue.system_prompt}
          onChange={(e) =>
            setPrompts({
              ...prompts,
              [promptMenu]: {
                ...promptValue,
                system_prompt: e.target.value,
              },
            })
          }
        />
        <div className="hint">User Prompt：放本次任务输入、上下文材料、变量占位符。</div>
        <textarea
          className="prompt-editor"
          rows={14}
          value={promptValue.user_prompt}
          onChange={(e) =>
            setPrompts({
              ...prompts,
              [promptMenu]: {
                ...promptValue,
                user_prompt: e.target.value,
              },
            })
          }
        />
        <button className="primary" onClick={savePrompts}>保存提示词</button>
        <button className="ghost" onClick={resetCurrentPrompt}>恢复当前项默认</button>
        <button className="ghost" onClick={resetPrompts}>恢复所有提示词默认</button>
        <div className="hint">提示词备份记录（点击即可回滚）</div>
        <div className="list prompt-backup-list">
          {promptBackups.length === 0 && <div className="log-empty">暂无备份</div>}
          {promptBackups.slice(0, 8).map((item) => (
            <button key={item.file} className="list-item" onClick={() => restorePromptBackup(item.file)}>
              <div>{item.file}</div>
              <small>{item.created_at || "未知时间"}</small>
            </button>
          ))}
        </div>
      </div>
      <div className="panel prompt-meta-panel">
        <h2>变量与说明</h2>
        <div className="card detail-card">
          <strong>所属业务阶段</strong>
          <div>{currentPromptMeta.stage}</div>
        </div>
        <div className="card detail-card">
          <strong>期望输出</strong>
          <div>{currentPromptMeta.output}</div>
        </div>
        <div className="card detail-card scroll-card">
          <strong>变量说明</strong>
          {currentPromptMeta.variables.length > 0 ? (
            currentPromptMeta.variables.map((item) => <div key={`meta-var-${item}`} className="var-chip">{item}</div>)
          ) : (
            <div>当前提示词无需固定变量。</div>
          )}
        </div>
      </div>
    </section>
  );
}
