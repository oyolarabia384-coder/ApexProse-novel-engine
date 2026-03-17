import React from "react";
import { buildApiUrl } from "../apiBase";

export default function EventDrawer({
  editingEvent,
  setEditingEvent,
  selectedNovel,
  loadNovelDetails,
  fetchEventCheckpoints,
  rewriteEventFromCheckpoint,
  notify,
  confirmAction,
}) {
  const [checkpointData, setCheckpointData] = React.useState(null);
  const [checkpointLoading, setCheckpointLoading] = React.useState(false);
  const [checkpointError, setCheckpointError] = React.useState("");
  const [rewriteLoading, setRewriteLoading] = React.useState(false);

  const currentEventId = editingEvent?.event_id;
  const hasCoreCheckpoints = Boolean(checkpointData?.generation_input && checkpointData?.generation_output);

  const loadCheckpoints = React.useCallback(
    async (silent = false) => {
      if (!selectedNovel || !currentEventId || !fetchEventCheckpoints) return null;
      if (!silent) {
        setCheckpointLoading(true);
      }
      setCheckpointError("");
      try {
        const data = await fetchEventCheckpoints(selectedNovel, currentEventId);
        setCheckpointData(data);
        return data;
      } catch (err) {
        const message = err?.message || "加载 checkpoint 失败";
        setCheckpointError(message);
        if (!silent && notify) {
          notify(message, "error");
        }
        return null;
      } finally {
        if (!silent) {
          setCheckpointLoading(false);
        }
      }
    },
    [selectedNovel, currentEventId, fetchEventCheckpoints, notify]
  );

  React.useEffect(() => {
    if (!editingEvent) {
      setCheckpointData(null);
      setCheckpointError("");
      return;
    }
    loadCheckpoints(true);
  }, [editingEvent?.event_id, loadCheckpoints]);

  const generationInput = checkpointData?.generation_input?.payload || null;
  const generationOutput = checkpointData?.generation_output?.payload || null;
  const postApplyState = checkpointData?.post_apply_state?.payload || null;
  const savedChapters = Array.isArray(generationOutput?.saved_chapters) ? generationOutput.saved_chapters : [];
  const artifactList = Array.isArray(checkpointData?.artifacts) ? checkpointData.artifacts : [];
  const artifactSummary = React.useMemo(() => {
    const counts = {};
    artifactList.forEach((item) => {
      const key = item?.stage || "unknown";
      counts[key] = (counts[key] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([stage, count]) => `${stage} x${count}`)
      .join(" / ");
  }, [artifactList]);

  const formatTime = (value) => (value ? String(value).replace("T", " ").slice(0, 19) : "-");
  const formatJsonBlock = (value) => {
    if (!value) return "暂无";
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  };

  const handleRewrite = async () => {
    if (!editingEvent?.event_id || !rewriteEventFromCheckpoint) return;
    const confirmed = confirmAction
      ? await confirmAction(`将按已保存 checkpoint 重写事件 ${editingEvent.event_id} 的正文，并保持回填结果与后续事件连续。是否继续？`)
      : window.confirm(`将按已保存 checkpoint 重写事件 ${editingEvent.event_id} 的正文，并保持回填结果与后续事件连续。是否继续？`);
    if (!confirmed) return;
    setRewriteLoading(true);
    try {
      const details = await rewriteEventFromCheckpoint(editingEvent.event_id);
      const refreshedEvent = Array.isArray(details?.events)
        ? details.events.find((item) => item.event_id === editingEvent.event_id)
        : null;
      if (refreshedEvent) {
        setEditingEvent((prev) => ({ ...prev, ...refreshedEvent }));
      }
      await loadCheckpoints(true);
      if (notify) {
        notify(`事件 ${editingEvent.event_id} 已按 checkpoint 重写`, "success");
      }
    } catch (err) {
      if (notify) {
        notify(`事件重写失败：${err?.message || "未知错误"}`, "error");
      }
    } finally {
      setRewriteLoading(false);
    }
  };

  if (!editingEvent) return null;

  const snapshotUpdate = editingEvent.event_world_snapshot_update || {};
  const foreshadowUpdates = Array.isArray(editingEvent.event_foreshadow_updates)
    ? editingEvent.event_foreshadow_updates
    : [];
  const growthUpdates = editingEvent.event_growth_updates || {};
  const lorebookUpdates = editingEvent.event_lorebook_updates || {};

  const updateSnapshot = (key, value) => {
    setEditingEvent({
      ...editingEvent,
      event_world_snapshot_update: { ...snapshotUpdate, [key]: value },
    });
  };

  const updateGrowth = (key, value) => {
    setEditingEvent({
      ...editingEvent,
      event_growth_updates: { ...growthUpdates, [key]: value },
    });
  };

  const updateForeshadowItem = (index, patch) => {
    const next = foreshadowUpdates.map((item, idx) => (idx === index ? { ...item, ...patch } : item));
    setEditingEvent({ ...editingEvent, event_foreshadow_updates: next });
  };

  const removeForeshadowItem = (index) => {
    setEditingEvent({
      ...editingEvent,
      event_foreshadow_updates: foreshadowUpdates.filter((_, idx) => idx !== index),
    });
  };

  const addForeshadowItem = () => {
    setEditingEvent({
      ...editingEvent,
      event_foreshadow_updates: [
        ...foreshadowUpdates,
        { description: "", status: "introduced", related_characters: [], notes: "" },
      ],
    });
  };

  const updateLorebookList = (listKey, updater) => {
    const current = Array.isArray(lorebookUpdates?.[listKey]) ? lorebookUpdates[listKey] : [];
    setEditingEvent({
      ...editingEvent,
      event_lorebook_updates: {
        ...lorebookUpdates,
        [listKey]: updater(current),
      },
    });
  };

  const renderLorebookEditor = (title, listKey) => {
    const items = Array.isArray(lorebookUpdates?.[listKey]) ? lorebookUpdates[listKey] : [];
    return (
      <div className="macro-editor-block">
        <div className="section-heading inner-heading">
          <strong>{title}</strong>
          <button
            type="button"
            className="ghost"
            onClick={() =>
              updateLorebookList(listKey, (current) => [
                ...current,
                { name: "", type: "", description: "", location: "", related_characters: [] },
              ])
            }
          >
            新增
          </button>
        </div>
        {items.length === 0 && <div className="table-empty">暂无条目</div>}
        <div className="item-editor-list">
          {items.map((item, index) => (
            <div key={`${listKey}-${index}`} className="item-editor-card">
              <div className="drawer-grid">
                <label>
                  名称
                  <input
                    value={item?.name || ""}
                    onChange={(e) =>
                      updateLorebookList(listKey, (current) =>
                        current.map((entry, idx) => (idx === index ? { ...entry, name: e.target.value } : entry))
                      )
                    }
                  />
                </label>
                <label>
                  类型
                  <input
                    value={item?.type || ""}
                    onChange={(e) =>
                      updateLorebookList(listKey, (current) =>
                        current.map((entry, idx) => (idx === index ? { ...entry, type: e.target.value } : entry))
                      )
                    }
                  />
                </label>
                <label className="drawer-span-2">
                  描述
                  <textarea
                    rows={2}
                    value={item?.description || ""}
                    onChange={(e) =>
                      updateLorebookList(listKey, (current) =>
                        current.map((entry, idx) => (idx === index ? { ...entry, description: e.target.value } : entry))
                      )
                    }
                  />
                </label>
                <label>
                  所在/归属
                  <input
                    value={item?.location || ""}
                    onChange={(e) =>
                      updateLorebookList(listKey, (current) =>
                        current.map((entry, idx) => (idx === index ? { ...entry, location: e.target.value } : entry))
                      )
                    }
                  />
                </label>
                <label>
                  关联人物
                  <input
                    value={Array.isArray(item?.related_characters) ? item.related_characters.join(" / ") : ""}
                    onChange={(e) =>
                      updateLorebookList(listKey, (current) =>
                        current.map((entry, idx) =>
                          idx === index
                            ? {
                                ...entry,
                                related_characters: e.target.value
                                  .split(/[\/、,，;；]+/)
                                  .map((part) => part.trim())
                                  .filter(Boolean),
                              }
                            : entry
                        )
                      )
                    }
                  />
                </label>
              </div>
              <div className="modal-actions compact-actions">
                <button
                  type="button"
                  className="ghost danger-text"
                  onClick={() => updateLorebookList(listKey, (current) => current.filter((_, idx) => idx !== index))}
                >
                  删除条目
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="modal">
      <div className="modal-card modal-drawer">
        <div className="drawer-header">
          <div>
            <p className="overline">事件详情</p>
            <h3>{`编辑事件 ${editingEvent.event_id}`}</h3>
            <div className="hint">先看 checkpoint 与重写状态，再校对事件规划与回填字段。</div>
          </div>
          <div className="section-actions">
            <button className="ghost" onClick={() => loadCheckpoints()} disabled={checkpointLoading || !selectedNovel}>
              {checkpointLoading ? "加载中..." : "刷新 Checkpoint"}
            </button>
            <button className="primary" onClick={handleRewrite} disabled={rewriteLoading || checkpointLoading || !hasCoreCheckpoints}>
              {rewriteLoading ? "重写中..." : "按 Checkpoint 重写正文"}
            </button>
            <button className="ghost" onClick={() => setEditingEvent(null)}>关闭</button>
          </div>
        </div>

        <div className="drawer-section">
          <div className="drawer-section-title">Checkpoint / 重写</div>
          <div className="hint">重写会复用事件生成前快照，并把既定回填结果和后续已完成事件摘要一并发给模型，避免正文与后续链条断裂。</div>
          {checkpointError && <div className="table-empty danger-text">{checkpointError}</div>}
          <div className="checkpoint-grid">
            <div className="card detail-card checkpoint-card">
              <strong>generation_input</strong>
              <div>状态：{checkpointData?.generation_input ? "已保存" : "未找到"}</div>
              <div>更新时间：{formatTime(checkpointData?.generation_input?.updated_at)}</div>
              <div>人物快照：{generationInput?.state_snapshot?.counts?.characters ?? 0}</div>
              <div>开放伏笔：{generationInput?.state_snapshot?.counts?.open_foreshadows ?? 0}</div>
            </div>
            <div className="card detail-card checkpoint-card">
              <strong>generation_output</strong>
              <div>状态：{checkpointData?.generation_output ? "已保存" : "未找到"}</div>
              <div>更新时间：{formatTime(checkpointData?.generation_output?.updated_at)}</div>
              <div>章节数：{savedChapters.length}</div>
              <div>标题：{generationOutput?.event_short_title || "-"}</div>
            </div>
            <div className="card detail-card checkpoint-card">
              <strong>post_apply_state</strong>
              <div>状态：{checkpointData?.post_apply_state ? "已保存" : "未找到"}</div>
              <div>更新时间：{formatTime(checkpointData?.post_apply_state?.updated_at)}</div>
              <div>已写事件：{postApplyState?.counts?.written_events ?? 0}</div>
              <div>设定库：{postApplyState?.counts?.lorebook ?? 0}</div>
            </div>
          </div>
          <div className="hint">生成记录：{artifactList.length} 条{artifactSummary ? `（${artifactSummary}）` : ""}</div>
          <details className="history-details">
            <summary>查看 checkpoint 明细</summary>
            <div className="item-editor-list">
              <div className="item-editor-card">
                <strong>generation_input.event_data</strong>
                <div className="reading-block checkpoint-code">{formatJsonBlock(generationInput?.event_data)}</div>
              </div>
              <div className="item-editor-card">
                <strong>generation_output.chapter_summary</strong>
                <div className="reading-block">{generationOutput?.chapter_summary || "暂无"}</div>
              </div>
              <div className="item-editor-card">
                <strong>generation_output.saved_chapters</strong>
                <div className="reading-block checkpoint-code">{formatJsonBlock(savedChapters)}</div>
              </div>
              <div className="item-editor-card">
                <strong>generation_output.event_deltas</strong>
                <div className="reading-block checkpoint-code">{formatJsonBlock(generationOutput?.event_deltas)}</div>
              </div>
              <div className="item-editor-card">
                <strong>post_apply_state.counts</strong>
                <div className="reading-block checkpoint-code">{formatJsonBlock(postApplyState?.counts)}</div>
              </div>
            </div>
          </details>
          <details className="history-details">
            <summary>查看生成阶段记录</summary>
            <div className="item-editor-list">
              {artifactList.map((item) => (
                <details key={`${item.id}-${item.stage}-${item.part_name || ""}`} className="item-editor-card checkpoint-artifact-card">
                  <summary>{`${item.stage}${item.part_name ? ` / ${item.part_name}` : ""} · ${formatTime(item.created_at)}`}</summary>
                  <div className="hint">step: {item?.meta?.step || "-"} / prompt: {item?.meta?.prompt || "-"}</div>
                  {!!item.system_prompt && (
                    <>
                      <strong>system prompt</strong>
                      <div className="reading-block checkpoint-code">{item.system_prompt}</div>
                    </>
                  )}
                  {!!item.user_prompt && (
                    <>
                      <strong>user prompt</strong>
                      <div className="reading-block checkpoint-code">{item.user_prompt}</div>
                    </>
                  )}
                  {!!item.response_text && (
                    <>
                      <strong>response</strong>
                      <div className="reading-block checkpoint-code">{item.response_text}</div>
                    </>
                  )}
                  {!!item.error_text && (
                    <>
                      <strong>error</strong>
                      <div className="reading-block checkpoint-code">{item.error_text}</div>
                    </>
                  )}
                </details>
              ))}
              {artifactList.length === 0 && <div className="table-empty">暂无生成阶段记录</div>}
            </div>
          </details>
        </div>

        <div className="drawer-section">
          <div className="drawer-section-title">基础大纲</div>
          <div className="drawer-grid">
            <label className="drawer-span-2">描述<input value={editingEvent.description || ""} onChange={(e) => setEditingEvent({ ...editingEvent, description: e.target.value })} /></label>
            <label className="drawer-span-2">原始大纲<input value={editingEvent.outline_description || ""} onChange={(e) => setEditingEvent({ ...editingEvent, outline_description: e.target.value })} /></label>
            <label>结局阶段<select value={editingEvent.ending_phase || "normal"} onChange={(e) => setEditingEvent({ ...editingEvent, ending_phase: e.target.value })}><option value="normal">normal</option><option value="pre_ending">pre_ending</option><option value="climax">climax</option><option value="resolution">resolution</option><option value="epilogue">epilogue</option></select></label>
            <label>地点<input value={editingEvent.location || ""} onChange={(e) => setEditingEvent({ ...editingEvent, location: e.target.value })} /></label>
            <label>时间跨度<input value={editingEvent.time_duration || ""} onChange={(e) => setEditingEvent({ ...editingEvent, time_duration: e.target.value })} /></label>
            <label>核心冲突<input value={editingEvent.core_conflict || ""} onChange={(e) => setEditingEvent({ ...editingEvent, core_conflict: e.target.value })} /></label>
            <label className="drawer-span-2">伏笔<input value={editingEvent.foreshadowing || ""} onChange={(e) => setEditingEvent({ ...editingEvent, foreshadowing: e.target.value })} /></label>
          </div>
        </div>

        <div className="drawer-section">
          <div className="drawer-section-title">执行目标与回报</div>
          <div className="drawer-grid">
            <label>事件目标<input value={editingEvent.goal || ""} onChange={(e) => setEditingEvent({ ...editingEvent, goal: e.target.value })} /></label>
            <label>主要障碍<input value={editingEvent.obstacle || ""} onChange={(e) => setEditingEvent({ ...editingEvent, obstacle: e.target.value })} /></label>
            <label>爽点类型<input value={editingEvent.cool_point_type || ""} onChange={(e) => setEditingEvent({ ...editingEvent, cool_point_type: e.target.value })} /></label>
            <label>爽点兑现<input value={editingEvent.payoff_type || ""} onChange={(e) => setEditingEvent({ ...editingEvent, payoff_type: e.target.value })} /></label>
            <label>成长回报<input value={editingEvent.growth_reward || ""} onChange={(e) => setEditingEvent({ ...editingEvent, growth_reward: e.target.value })} /></label>
            <label>地位回报<input value={editingEvent.status_reward || ""} onChange={(e) => setEditingEvent({ ...editingEvent, status_reward: e.target.value })} /></label>
            <label className="drawer-span-2">结尾钩子<input value={editingEvent.cliffhanger || ""} onChange={(e) => setEditingEvent({ ...editingEvent, cliffhanger: e.target.value })} /></label>
          </div>
        </div>

        <div className="drawer-section">
          <div className="drawer-section-title">出场与状态</div>
          <div className="drawer-grid">
            <label className="drawer-span-2">出场人物(JSON)<input value={editingEvent.linked_characters || ""} onChange={(e) => setEditingEvent({ ...editingEvent, linked_characters: e.target.value })} /></label>
            <label className="toggle drawer-toggle"><input type="checkbox" checked={!!editingEvent.is_written} onChange={(e) => setEditingEvent({ ...editingEvent, is_written: e.target.checked ? 1 : 0 })} />已写</label>
          </div>
        </div>

        <div className="drawer-section">
          <div className="drawer-section-title">宏观变更</div>
          <div className="hint">这里直接编辑事件完成后的世界、伏笔、成长与设定库变更。</div>

          <div className="macro-editor-block">
            <div className="section-heading inner-heading">
              <strong>世界快照变化</strong>
            </div>
            <div className="drawer-grid">
              <label className="drawer-span-2">
                世界变化
                <textarea rows={2} value={snapshotUpdate.world_state_shift || ""} onChange={(e) => updateSnapshot("world_state_shift", e.target.value)} />
              </label>
              <label>
                新冲突种子
                <textarea
                  rows={3}
                  value={Array.isArray(snapshotUpdate.new_conflict_seeds) ? snapshotUpdate.new_conflict_seeds.join("\n") : ""}
                  onChange={(e) => updateSnapshot("new_conflict_seeds", e.target.value.split(/\n+/).map((v) => v.trim()).filter(Boolean))}
                />
              </label>
              <label>
                已解决冲突种子
                <textarea
                  rows={3}
                  value={Array.isArray(snapshotUpdate.resolved_conflict_seeds) ? snapshotUpdate.resolved_conflict_seeds.join("\n") : ""}
                  onChange={(e) => updateSnapshot("resolved_conflict_seeds", e.target.value.split(/\n+/).map((v) => v.trim()).filter(Boolean))}
                />
              </label>
            </div>
          </div>

          <div className="macro-editor-block">
            <div className="section-heading inner-heading">
              <strong>伏笔变化</strong>
              <button type="button" className="ghost" onClick={addForeshadowItem}>新增伏笔变化</button>
            </div>
            {foreshadowUpdates.length === 0 && <div className="table-empty">暂无伏笔变化</div>}
            <div className="item-editor-list">
              {foreshadowUpdates.map((item, index) => (
                <div key={`foreshadow-update-${index}`} className="item-editor-card">
                  <div className="drawer-grid">
                    <label className="drawer-span-2">
                      内容
                      <input value={item?.description || ""} onChange={(e) => updateForeshadowItem(index, { description: e.target.value })} />
                    </label>
                    <label>
                      状态
                      <select value={item?.status || "introduced"} onChange={(e) => updateForeshadowItem(index, { status: e.target.value })}>
                        <option value="introduced">introduced</option>
                        <option value="progressed">progressed</option>
                        <option value="paid_off">paid_off</option>
                      </select>
                    </label>
                    <label>
                      关联人物
                      <input
                        value={Array.isArray(item?.related_characters) ? item.related_characters.join(" / ") : ""}
                        onChange={(e) =>
                          updateForeshadowItem(index, {
                            related_characters: e.target.value
                              .split(/[\/、,，;；]+/)
                              .map((part) => part.trim())
                              .filter(Boolean),
                          })
                        }
                      />
                    </label>
                    <label className="drawer-span-2">
                      备注
                      <textarea rows={2} value={item?.notes || ""} onChange={(e) => updateForeshadowItem(index, { notes: e.target.value })} />
                    </label>
                  </div>
                  <div className="modal-actions compact-actions">
                    <button type="button" className="ghost danger-text" onClick={() => removeForeshadowItem(index)}>删除条目</button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="macro-editor-block">
            <div className="section-heading inner-heading">
              <strong>成长变化</strong>
            </div>
            <div className="drawer-grid">
              <label>
                能力等级变化
                <input value={growthUpdates.power_system_level || ""} onChange={(e) => updateGrowth("power_system_level", e.target.value)} />
              </label>
              <label>
                阶段推进
                <input value={growthUpdates.stage_progress || growthUpdates.stage_summary || ""} onChange={(e) => updateGrowth("stage_progress", e.target.value)} />
              </label>
              <label>
                资源变化
                <textarea rows={2} value={growthUpdates.resource_change || ""} onChange={(e) => updateGrowth("resource_change", e.target.value)} />
              </label>
              <label>
                势力变化
                <textarea rows={2} value={growthUpdates.influence_change || ""} onChange={(e) => updateGrowth("influence_change", e.target.value)} />
              </label>
            </div>
          </div>

          <div className="macro-editor-block">
            <div className="section-heading inner-heading">
              <strong>设定库变化</strong>
            </div>
            {renderLorebookEditor("新增条目", "new_items")}
            {renderLorebookEditor("更新条目", "updated_items")}
            <div className="macro-editor-block">
              <div className="section-heading inner-heading">
                <strong>移除条目</strong>
                <button
                  type="button"
                  className="ghost"
                  onClick={() =>
                    updateLorebookList("removed_items", (current) => [
                      ...current,
                      { name: "", reason: "" },
                    ])
                  }
                >
                  新增
                </button>
              </div>
              {!(Array.isArray(lorebookUpdates?.removed_items) && lorebookUpdates.removed_items.length) && <div className="table-empty">暂无移除条目</div>}
              <div className="item-editor-list">
                {(Array.isArray(lorebookUpdates?.removed_items) ? lorebookUpdates.removed_items : []).map((item, index) => (
                  <div key={`removed-item-${index}`} className="item-editor-card">
                    <div className="drawer-grid">
                      <label>
                        名称
                        <input
                          value={item?.name || ""}
                          onChange={(e) =>
                            updateLorebookList("removed_items", (current) =>
                              current.map((entry, idx) => (idx === index ? { ...entry, name: e.target.value } : entry))
                            )
                          }
                        />
                      </label>
                      <label className="drawer-span-2">
                        移除原因
                        <textarea
                          rows={2}
                          value={item?.reason || ""}
                          onChange={(e) =>
                            updateLorebookList("removed_items", (current) =>
                              current.map((entry, idx) => (idx === index ? { ...entry, reason: e.target.value } : entry))
                            )
                          }
                        />
                      </label>
                    </div>
                    <div className="modal-actions compact-actions">
                      <button type="button" className="ghost danger-text" onClick={() => updateLorebookList("removed_items", (current) => current.filter((_, idx) => idx !== index))}>删除条目</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="modal-actions drawer-actions">
          <button className="ghost" onClick={() => setEditingEvent(null)}>取消</button>
          <button
            className="primary"
            onClick={async () => {
              try {
                const res = await fetch(buildApiUrl(`/api/novels/${selectedNovel}/events/${editingEvent.event_id}`), {
                  method: "PUT",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(editingEvent),
                });
                if (!res.ok) {
                  throw new Error("保存失败");
                }
                setEditingEvent(null);
                await loadNovelDetails(selectedNovel);
                if (notify) {
                  notify(`事件 ${editingEvent.event_id} 已保存`, "success");
                }
              } catch (err) {
                if (notify) {
                  notify(err?.message || "保存失败", "error");
                }
              }
            }}
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
