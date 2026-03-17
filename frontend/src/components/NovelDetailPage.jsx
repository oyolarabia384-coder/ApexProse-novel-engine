import React from "react";

export default function NovelDetailPage({
  hasNovelSelection,
  redirectToCreateNovel,
  currentNovel,
  novelDetailTabs,
  novelDetailTab,
  setNovelDetailTab,
  novelDetailTabLabels,
  storyPhaseLabels,
  exportSection,
  worldviewSummary,
  openingSnapshot,
  worldview,
  worldItemRows,
  triggerImport,
  eventLorebookUpdateRows,
  characterQuery,
  setCharacterQuery,
  characterTierFilter,
  setCharacterTierFilter,
  filteredCharacters,
  sortedCharacters,
  setEditingCharacter,
  toggleLock,
  seriesBlueprint,
  growthSystem,
  growthSnapshot,
  eventQuery,
  setEventQuery,
  eventStatusFilter,
  setEventStatusFilter,
  filteredEvents,
  events,
  setEditingEvent,
  foreshadows,
  chapters,
  chapterQuery,
  setChapterQuery,
  selectedChapter,
  setSelectedChapter,
  filteredChapters,
  currentChapter,
  setEditingChapter,
  deleteNovelById,
  clearChaptersByNovel,
  deleteSingleChapter,
}) {
  return (
    <section className="grid">
      {!hasNovelSelection ? (
        <div className="panel full empty-state-panel">
          <div className="empty-state">
            <strong>当前没有选中的小说</strong>
            <p>点击确认后自动跳转到创建小说页面。</p>
            <button className="primary" onClick={redirectToCreateNovel}>确定</button>
          </div>
        </div>
      ) : (
        <>
          <div className="panel full sticky-subtabs">
            <div className="section-heading">
              <div>
                <p className="overline">小说详情</p>
                <h2>{currentNovel?.title || "当前小说"}</h2>
              </div>
                  <div className="section-actions">
                    <button className="ghost" onClick={() => exportSection("meta")}>导出小说信息</button>
                    <button className="danger" onClick={() => currentNovel?.id && deleteNovelById(currentNovel.id)}>删除小说</button>
                  </div>
                </div>
            <div className="detail-tabs">
              {novelDetailTabs.map((tab) => (
                <button key={tab} className={novelDetailTab === tab ? "subnav active" : "subnav"} onClick={() => setNovelDetailTab(tab)}>
                  {novelDetailTabLabels[tab]}
                </button>
              ))}
            </div>
            <div className="topbar-meta">
              <span>{storyPhaseLabels[currentNovel?.current_phase] || currentNovel?.current_phase || "draft"}</span>
              <span>目标 {((currentNovel?.target_words || 0) / 10000).toFixed(0)} 万字</span>
              <span>事件 {events.length}</span>
              <span>章节 {chapters.length}</span>
            </div>
          </div>

          {novelDetailTab === "world" && (
            <div className="panel full">
              <div className="section-heading">
                <div>
                  <p className="overline">从大到小</p>
                  <h2>世界背景</h2>
                </div>
                <div className="section-actions">
                  <button className="ghost" onClick={() => exportSection("worldview_summary")}>导出世界摘要</button>
                  <button className="ghost" onClick={() => exportSection("opening_snapshot")}>导出世界快照</button>
                </div>
              </div>
              <div className="row detail-layout-two">
                <div className="mini">
                  <div className="card detail-card">
                    <strong>世界摘要</strong>
                    <div className="reading-block clamp-block">{worldviewSummary || "暂无"}</div>
                    <details>
                      <summary>查看详情正文</summary>
                      <div className="reading-block">{worldviewSummary || "暂无"}</div>
                    </details>
                  </div>
                  <div className="card detail-card">
                    <strong>当前世界快照</strong>
                    <div className="reading-block">{openingSnapshot || worldview || "暂无"}</div>
                  </div>
                </div>
                <div className="mini">
                  <div className="section-heading inner-heading">
                    <strong>世界级设定库</strong>
                    <div className="section-actions">
                      <button className="ghost" onClick={() => exportSection("lorebook")}>导出</button>
                      <button className="ghost" onClick={() => triggerImport("lorebook")}>导入</button>
                    </div>
                  </div>
                  <div className="panel-table fixed-table-height">
                    <div className="table-header world-library-header">
                      <span>名称</span>
                      <span>类型</span>
                      <span>位置</span>
                      <span>说明</span>
                    </div>
                    {worldItemRows.slice(0, 10).map((item) => (
                      <div key={item.key} className="table-row world-library-row">
                        <span>{item.name}</span>
                        <span>{item.type}</span>
                        <span>{item.location}</span>
                        <span title={item.description}>{item.description}</span>
                      </div>
                    ))}
                    {worldItemRows.length === 0 && <div className="table-empty">暂无设定库</div>}
                  </div>
                  <div className="section-heading inner-heading">
                    <strong>设定库历史变更</strong>
                  </div>
                  <div className="panel-table fixed-table-height short-table">
                    <div className="table-header five-col">
                      <span>事件</span>
                      <span>动作</span>
                      <span>名称</span>
                      <span>类型</span>
                      <span>说明</span>
                    </div>
                    {eventLorebookUpdateRows.map((item) => (
                      <div key={item.key} className="table-row five-col">
                        <span>#{item.event_id}</span>
                        <span>{item.action}</span>
                        <span>{item.name}</span>
                        <span>{item.type}</span>
                        <span title={item.description}>{item.description}</span>
                      </div>
                    ))}
                    {eventLorebookUpdateRows.length === 0 && <div className="table-empty">暂无事件级变更</div>}
                  </div>
                </div>
              </div>
            </div>
          )}

          {novelDetailTab === "characters" && (
            <div className="panel full">
              <div className="section-heading">
                <div>
                  <p className="overline">人物</p>
                  <h2>按层级排序，主角优先</h2>
                </div>
                <div className="section-actions">
                  <button className="ghost" onClick={() => exportSection("characters")}>导出</button>
                  <button className="ghost" onClick={() => triggerImport("characters")}>导入</button>
                </div>
              </div>
              <div className="row filter-row">
                <label>
                  搜索人物
                  <input value={characterQuery} onChange={(e) => setCharacterQuery(e.target.value)} placeholder="按姓名、职能、目标筛选" />
                </label>
                <label>
                  层级筛选
                  <select value={characterTierFilter} onChange={(e) => setCharacterTierFilter(e.target.value)}>
                    <option value="all">全部层级</option>
                    <option value="protagonist">主角</option>
                    <option value="major_support">重要配角</option>
                    <option value="support">配角</option>
                    <option value="functional">功能角色</option>
                  </select>
                </label>
              </div>
              <div className="hint">当前结果 {filteredCharacters.length} / 总人物 {sortedCharacters.length}</div>
              <div className="card-grid three-up uniform-card-grid fixed-grid-height">
                {filteredCharacters.map((c) => (
                  <div key={`detail-char-${c.name}`} className="card detail-card">
                    <strong>{c.name}</strong>
                    <div>层级：{c.role_tier || "support"}</div>
                    <div>故事职能：{c.story_function || "-"}</div>
                    <div>当前状态：{c.state || "-"}</div>
                    <div>秘密：{c.secret || "-"}</div>
                    <div>口头禅：{c.catchphrase || "-"}</div>
                    <div>计划关联：{c.planned_event_scope_text || (c.scope_type === "full" ? "全篇" : "-")}</div>
                    <div>item_updates：{Array.isArray(c.item_updates) ? c.item_updates.map((item) => item?.name).filter(Boolean).join(" / ") || "-" : "-"}</div>
                    <div className="modal-actions compact-actions">
                      <button className="ghost" onClick={() => setEditingCharacter({ ...c })}>查看详情 / 编辑</button>
                      <button className="ghost" onClick={() => toggleLock("character", c.name, !c.is_locked)}>{c.is_locked ? "解锁" : "锁定"}</button>
                    </div>
                  </div>
                ))}
              </div>
              {filteredCharacters.length === 0 && <div className="table-empty">没有匹配的人物</div>}
            </div>
          )}

          {novelDetailTab === "planning" && (
            <>
              <div className="panel full">
                <div className="section-heading">
                  <div>
                    <p className="overline">规划与状态</p>
                    <h2>默认显示当前内容，并保留历史记录可查</h2>
                  </div>
                  <div className="section-actions">
                    <button className="ghost" onClick={() => exportSection("series_blueprint")}>导出阶段计划</button>
                    <button className="ghost" onClick={() => exportSection("growth_system")}>导出成长规划</button>
                    <button className="ghost" onClick={() => exportSection("events")}>导出事件列表</button>
                  </div>
                </div>
                <div className="row detail-layout-three">
                  <div className="mini">
                    <div className="card detail-card">
                      <strong>当前世界状态</strong>
                      <div className="reading-block clamp-block">{worldview || openingSnapshot || "暂无"}</div>
                    </div>
                  </div>
                  <div className="mini">
                    <div className="card detail-card scroll-card">
                      <strong>阶段计划</strong>
                      {!seriesBlueprint && <div>暂无</div>}
                      {(seriesBlueprint?.stage_plan || []).map((stage) => (
                        <div key={stage.phase} className="subcard">
                          <div>{stage.phase_label || stage.phase}</div>
                          <div>事件 {stage.start_event_id}-{stage.end_event_id}</div>
                          <div>{stage.phase_goal || "-"}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="mini">
                    <div className="card detail-card scroll-card">
                      <strong>成长计划</strong>
                      {!growthSystem && <div>暂无</div>}
                      {(growthSystem?.stage_growth_plan || []).map((stage) => (
                        <div key={`growth-${stage.phase}`} className="subcard">
                          <div>{stage.phase_label || stage.phase}</div>
                          <div>{stage.growth_goal || "-"}</div>
                        </div>
                      ))}
                      <div className="subcard accent-subcard">
                        <div>当前成长快照</div>
                        <div>阶段：{growthSnapshot?.current_stage || "-"}</div>
                        <div>任务：{growthSnapshot?.stage_summary || "-"}</div>
                        <div>等级：{growthSnapshot?.power_system_level || "-"}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="panel full">
                <div className="section-heading">
                  <strong>事件列表</strong>
                  <div className="section-actions">
                    <button className="ghost" onClick={() => triggerImport("events")}>导入事件</button>
                  </div>
                </div>
                <div className="row filter-row">
                  <label>
                    搜索事件
                    <input value={eventQuery} onChange={(e) => setEventQuery(e.target.value)} placeholder="按事件号、大纲、目标筛选" />
                  </label>
                  <label>
                    状态筛选
                    <select value={eventStatusFilter} onChange={(e) => setEventStatusFilter(e.target.value)}>
                      <option value="all">全部状态</option>
                      <option value="planned">planned</option>
                      <option value="completed">completed</option>
                      <option value="failed">failed</option>
                    </select>
                  </label>
                </div>
                <div className="hint">当前结果 {filteredEvents.length} / 总事件 {events.length}</div>
                <div className="card-grid three-up uniform-card-grid fixed-grid-height">
                  {filteredEvents.map((e) => (
                    <div key={`detail-event-${e.event_id}`} className={e.ending_phase && e.ending_phase !== "normal" ? "card detail-card ending-card" : "card detail-card"}>
                      <strong>事件 {e.event_id}</strong>
                      <div>{e.outline_description || e.description}</div>
                      <div>状态：{e.status || (e.is_written ? "completed" : "planned")}</div>
                      <div>目标：{e.goal || "-"}</div>
                      <div>钩子：{e.cliffhanger || "-"}</div>
                      <div className="modal-actions compact-actions">
                        <button className="ghost" onClick={() => setEditingEvent({ ...e })}>查看详情 / Checkpoint</button>
                        <button className="ghost" onClick={() => toggleLock("event", e.event_id, !e.is_locked)}>{e.is_locked ? "解锁" : "锁定"}</button>
                      </div>
                    </div>
                  ))}
                </div>
                {filteredEvents.length === 0 && <div className="table-empty">没有匹配的事件</div>}
                <details className="history-details">
                  <summary>查看历史记录</summary>
                  <div className="row detail-layout-two">
                    <div className="panel-table fixed-table-height">
                      <div className="table-title">伏笔历史</div>
                      <div className="table-header five-col">
                        <span>ID</span>
                        <span>状态</span>
                        <span>内容</span>
                        <span>重要度</span>
                        <span>最近更新</span>
                      </div>
                      {foreshadows.map((item) => (
                        <div key={`history-foreshadow-${item.id}`} className="table-row five-col">
                          <span>{item.id}</span>
                          <span>{item.status || "-"}</span>
                          <span title={item.description || ""}>{item.description || "-"}</span>
                          <span>{item.importance_level || "-"}</span>
                          <span>{item.updated_at ? String(item.updated_at).replace("T", " ").slice(0, 16) : "-"}</span>
                        </div>
                      ))}
                      {foreshadows.length === 0 && <div className="table-empty">暂无伏笔历史</div>}
                    </div>
                    <div className="panel-table fixed-table-height">
                      <div className="table-title">已完成章节记录</div>
                      <div className="table-header five-col">
                        <span>章节</span>
                        <span>事件</span>
                        <span>标题</span>
                        <span>质量</span>
                        <span>更新时间</span>
                      </div>
                      {chapters.map((chapter) => (
                        <div key={`history-chapter-${chapter.chapter_num}`} className="table-row five-col">
                          <span>{chapter.chapter_num}</span>
                          <span>{chapter.source_event_id || "-"}</span>
                          <span>{chapter.title || "-"}</span>
                          <span>{chapter.quality_score || 0}</span>
                          <span>{chapter.updated_at ? String(chapter.updated_at).replace("T", " ").slice(0, 16) : "-"}</span>
                        </div>
                      ))}
                      {chapters.length === 0 && <div className="table-empty">暂无章节历史</div>}
                    </div>
                  </div>
                </details>
              </div>
            </>
          )}

          {novelDetailTab === "chapters" && (
            <div className="panel full">
              <div className="section-heading">
                <div>
                  <p className="overline">章节</p>
                  <h2>查看正文，按需深入编辑</h2>
                </div>
                <div className="section-actions">
                  <button className="ghost" onClick={() => currentNovel?.id && clearChaptersByNovel(currentNovel.id)}>清空章节</button>
                  <button className="ghost" onClick={() => selectedChapter && exportSection("chapter_selected", { chapter_num: selectedChapter })}>导出选中章节</button>
                  <button className="ghost" onClick={() => exportSection("chapters_all")}>导出全部章节</button>
                </div>
              </div>
              <div className="row detail-layout-two">
                <div className="mini">
                  <label>
                    搜索章节
                    <input value={chapterQuery} onChange={(e) => setChapterQuery(e.target.value)} placeholder="按章节号、标题、事件筛选" />
                  </label>
                  <label>
                    选择章节
                    <select value={selectedChapter || ""} onChange={(e) => setSelectedChapter(e.target.value ? Number(e.target.value) : null)}>
                      <option value="">请选择章节</option>
                      {filteredChapters.map((c) => (
                        <option key={c.chapter_num} value={c.chapter_num}>第 {c.chapter_num} 章 {c.title || ""}</option>
                      ))}
                    </select>
                  </label>
                  <div className="hint">当前结果 {filteredChapters.length} / 总章节 {chapters.length}</div>
                  <div className="scroll-box fixed-list-height">
                    {filteredChapters.map((c) => (
                      <button key={`chapter-list-${c.chapter_num}`} className={selectedChapter === c.chapter_num ? "list-item active" : "list-item"} onClick={() => setSelectedChapter(c.chapter_num)}>
                        <div>第 {c.chapter_num} 章</div>
                        <small>{c.title || "未命名"}</small>
                      </button>
                    ))}
                    {filteredChapters.length === 0 && <div className="table-empty">没有匹配的章节</div>}
                  </div>
                </div>
                <div className="mini">
                  <div className="chapter-area chapter-area-large">
                    {currentChapter ? (
                      <div className="chapter-body chapter-scroll-body">
                        <h3>{`第 ${selectedChapter} 章 ${currentChapter.title || ""}`}</h3>
                        <div className="topbar-meta chapter-meta">
                          <span>质量分 {currentChapter.quality_score || 0}</span>
                          <span>重写 {currentChapter.rewrite_count || 0}</span>
                          <span>钩子 {currentChapter.cliffhanger_type || "-"}</span>
                        </div>
                        {currentChapter.content || ""}
                        <div className="modal-actions compact-actions">
                          <button className="ghost" onClick={() => currentChapter && setEditingChapter({ ...currentChapter })}>查看详情 / 编辑</button>
                          <button className="ghost" onClick={() => toggleLock("chapter", selectedChapter, !currentChapter?.is_locked)}>{currentChapter?.is_locked ? "解锁" : "锁定"}</button>
                          <button className="danger" onClick={() => currentNovel?.id && selectedChapter && deleteSingleChapter(currentNovel.id, selectedChapter)}>删除</button>
                        </div>
                      </div>
                    ) : (
                      <div className="placeholder">选择章节后显示正文</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
