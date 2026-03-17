import React from "react";
import { buildApiUrl } from "../apiBase";

export default function ProductionPage({
  productionTab,
  selectedNovel,
  setSelectedNovel,
  novels,
  events,
  currentNovel,
  storyPhaseLabels,
  dashboard,
  selectedStoryPlan,
  genCount,
  setGenCount,
  runChapters,
  jobList,
  clearJobs,
  deleteJob,
  loadJobs,
  chapters,
  logs,
  clearLogs,
}) {
  if (productionTab === "settings") {
    return (
      <section className="grid two-column-focus equal-height-grid">
        <div className="panel fixed-panel">
          <h2>生产设置</h2>
          <label>
            选择小说
            <select value={selectedNovel || ""} onChange={(e) => setSelectedNovel(e.target.value || null)}>
              <option value="" disabled>请选择</option>
              {novels.map((novel) => (
                <option key={novel.id} value={novel.id}>{novel.title}</option>
              ))}
            </select>
          </label>
          <div className="hint">已生产事件：{events.filter((e) => e.is_written).length}</div>
          <div className="hint">当前阶段：{storyPhaseLabels[currentNovel?.current_phase] || currentNovel?.current_phase || "-"}{` / 未回收伏笔 ${currentNovel?.foreshadow_active_count || 0}`}{currentNovel?.ending_mode ? " / 结局推进中" : ""}</div>
          <div className="hint">目标字数：{((currentNovel?.target_words || 0) / 10000).toFixed(0)}万 / 目标事件：{currentNovel?.target_event_count || 0}</div>
          <div className="hint">节奏区间：开篇 1-{currentNovel?.opening_breakthrough_count || "-"} / 发展 {(currentNovel?.opening_breakthrough_count || 0) + 1}-{currentNovel?.development_end_event_id || "-"} / 结局 {currentNovel?.ending_start_event_id || "-"}-{currentNovel?.target_event_count || "-"}</div>
          <div className="hint">开放伏笔：{dashboard ? dashboard.open_foreshadows || 0 : 0}</div>
          <div className="hint">当前目标字数仅展示；如需修改，请到“小说管理 / 小说列表”中编辑。预计结局区间：{selectedStoryPlan.endingStartEventId}-{selectedStoryPlan.targetEventCount}</div>
          <label>
            生成事件数
            <input type="number" min="1" max="50" value={genCount} onChange={(e) => setGenCount(Number(e.target.value) || 1)} />
          </label>
          <button className="primary" onClick={runChapters} disabled={!selectedNovel}>开始生成章节</button>
        </div>
        <div className="panel fixed-panel">
          <h2>当前阶段摘要</h2>
          <div className="stats compact-stats">
            <div><span>当前阶段</span><strong>{storyPhaseLabels[currentNovel?.current_phase] || currentNovel?.current_phase || "-"}</strong></div>
            <div><span>已写事件</span><strong>{events.filter((e) => e.is_written).length}</strong></div>
            <div><span>总章节</span><strong>{chapters.length}</strong></div>
          </div>
          <div className="panel-table fixed-table-height fixed-panel-table">
            <div className="table-header">
              <span>事件</span><span>状态</span><span>来源</span><span>章节</span>
            </div>
            {events.slice(-12).reverse().map((event) => (
              <div key={`settings-event-${event.event_id}`} className={`table-row ${event.status === "failed" ? "row-failed" : ""}`}>
                <span>#{event.event_id}</span>
                <span>{event.status || (event.is_written ? "completed" : "planned")}</span>
                <span>{event.goal || "-"}</span>
                <span>{chapters.filter((chapter) => chapter.source_event_id === event.event_id).length}</span>
              </div>
            ))}
            {events.length === 0 && <div className="table-empty">暂无事件</div>}
          </div>
        </div>
      </section>
    );
  }

  if (productionTab === "tasks") {
    return (
      <section className="grid two-column-focus">
        <div className="panel fixed-panel">
          <div className="section-heading">
            <h2>任务列表</h2>
            <button className="ghost" onClick={clearJobs}>清空历史记录</button>
          </div>
          <div className="list fixed-list-height">
            {jobList.length === 0 && <div className="log-empty">暂无任务</div>}
            {jobList.map((job, idx) => {
              const novelName = novels.find((n) => n.id === job.novel_id)?.title || "未知小说";
              const statusLabel = job.status === "running" ? "运行中" : job.status === "failed" ? "错误" : "已完成";
              return (
                <div key={job.job_id} className="job-card">
                  <div>任务{String(idx + 1).padStart(6, "0")}</div>
                  <div>[{novelName}]</div>
                  <div>{job.step_label || "-"}</div>
                  <div>{statusLabel}</div>
                  {job.status === "running" && (
                    <button
                      className="ghost"
                      onClick={async () => {
                        await fetch(buildApiUrl(`/api/jobs/${job.job_id}/cancel`), { method: "POST" });
                        loadJobs();
                      }}
                    >
                      停止
                    </button>
                  )}
                  <button className="ghost" onClick={() => deleteJob(job.job_id)}>删除</button>
                </div>
              );
            })}
          </div>
        </div>
        <div className="panel fixed-panel">
          <div className="section-heading">
            <h2>任务日志</h2>
            <button className="ghost" onClick={clearLogs}>清空日志</button>
          </div>
          <div className="log-box fixed-log-height">
            {logs.length === 0 ? <div className="log-empty">暂无日志</div> : logs.map((line, i) => <div key={`task-log-${i}`}>{line}</div>)}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="grid two-column-focus">
      <div className="panel fixed-panel">
        <h2>生产记录</h2>
        <div className="panel-table fixed-table-height fixed-panel-table">
          <div className="table-header">
            <span>事件</span><span>状态</span><span>原因</span><span>时间</span>
          </div>
          {(dashboard?.event_runs || []).map((item) => (
            <div key={`record-${item.id}`} className={`table-row ${item.status === "failed" ? "row-failed" : ""}`}>
              <span>#{item.event_id ?? "-"}</span><span>{item.status === "failed" ? "失败" : "完成"}</span><span title={item.reason || ""}>{item.reason || "-"}</span><span>{item.created_at ? String(item.created_at).replace("T", " ").slice(0, 19) : "-"}</span>
            </div>
          ))}
          {(!dashboard?.event_runs || (dashboard.event_runs || []).length === 0) && <div className="table-empty">暂无生产记录</div>}
        </div>
      </div>
      <div className="panel fixed-panel">
        <h2>章节产出概览</h2>
        <div className="card-grid two-up uniform-card-grid fixed-grid-height">
          {chapters.slice(-6).reverse().map((chapter) => (
            <div key={`record-chapter-${chapter.chapter_num}`} className="card detail-card">
              <strong>第 {chapter.chapter_num} 章</strong>
              <div>{chapter.title || "未命名"}</div>
              <div>质量分：{chapter.quality_score || 0}</div>
              <div>来源事件：{chapter.source_event_id || "-"}</div>
            </div>
          ))}
          {chapters.length === 0 && <div className="table-empty">暂无章节产出</div>}
        </div>
      </div>
    </section>
  );
}
