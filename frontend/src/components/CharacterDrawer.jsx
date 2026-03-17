import React from "react";
import { buildApiUrl } from "../apiBase";

export default function CharacterDrawer({
  editingCharacter,
  setEditingCharacter,
  selectedNovel,
  loadNovelDetails,
  editListField,
  parseListField,
}) {
  if (!editingCharacter) return null;

  const itemUpdates = Array.isArray(editingCharacter.item_updates) ? editingCharacter.item_updates : [];

  const updateItem = (index, patch) => {
    const next = itemUpdates.map((item, idx) => (idx === index ? { ...item, ...patch } : item));
    setEditingCharacter({ ...editingCharacter, item_updates: next });
  };

  const removeItem = (index) => {
    const next = itemUpdates.filter((_, idx) => idx !== index);
    setEditingCharacter({ ...editingCharacter, item_updates: next });
  };

  const addItem = () => {
    setEditingCharacter({
      ...editingCharacter,
      item_updates: [
        ...itemUpdates,
        {
          name: "",
          type: "道具",
          description: "",
          location: "",
          related_characters: [editingCharacter.name].filter(Boolean),
        },
      ],
    });
  };

  return (
    <div className="modal">
      <div className="modal-card modal-drawer">
        <div className="drawer-header">
          <div>
            <p className="overline">人物详情</p>
            <h3>编辑人物</h3>
            <div className="hint">把人物拆成基础、性格、升华、出场范围四组，编辑时更清楚。</div>
          </div>
          <button className="ghost" onClick={() => setEditingCharacter(null)}>关闭</button>
        </div>
        <div className="drawer-section">
          <div className="drawer-section-title">基础信息</div>
          <div className="drawer-grid">
            <label>层级<select value={editingCharacter.role_tier || "support"} onChange={(e) => setEditingCharacter({ ...editingCharacter, role_tier: e.target.value })}><option value="protagonist">主角</option><option value="major_support">重要配角</option><option value="support">配角</option><option value="functional">功能角色</option></select></label>
            <label>故事职能<input value={editingCharacter.story_function || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, story_function: e.target.value })} /></label>
            <label>目标<input value={editingCharacter.target || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, target: e.target.value })} /></label>
            <label>动机<input value={editingCharacter.motive || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, motive: e.target.value })} /></label>
            <label>秘密<input value={editingCharacter.secret || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, secret: e.target.value })} /></label>
            <label>关系<input value={editingCharacter.relationship || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, relationship: e.target.value })} /></label>
            <label>口头禅<input value={editingCharacter.catchphrase || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, catchphrase: e.target.value })} /></label>
            <label>成长弧<input value={editingCharacter.growth_arc || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, growth_arc: e.target.value })} /></label>
          </div>
        </div>

        <div className="drawer-section">
          <div className="drawer-section-title">性格与状态</div>
          <div className="drawer-grid">
            <label>优点（每行一个）<textarea rows={3} value={editListField(editingCharacter.strengths)} onChange={(e) => setEditingCharacter({ ...editingCharacter, strengths: parseListField(e.target.value) })} /></label>
            <label>缺点（每行一个）<textarea rows={3} value={editListField(editingCharacter.flaws)} onChange={(e) => setEditingCharacter({ ...editingCharacter, flaws: parseListField(e.target.value) })} /></label>
            <label className="drawer-span-2">行为逻辑<textarea rows={3} value={editingCharacter.behavior_logic || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, behavior_logic: e.target.value })} /></label>
            <label className="drawer-span-2">状态<input value={editingCharacter.state || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, state: e.target.value })} /></label>
          </div>
        </div>

        <div className="drawer-section">
          <div className="drawer-section-title">升华线</div>
          <div className="drawer-grid">
            <label>
              有升华点
              <select
                value={editingCharacter.has_sublimation_point ? "1" : "0"}
                onChange={(e) =>
                  setEditingCharacter({
                    ...editingCharacter,
                    has_sublimation_point: e.target.value === "1",
                    sublimation_status: e.target.value === "1" ? editingCharacter.sublimation_status || "seeded" : "none",
                  })
                }
              >
                <option value="0">否</option><option value="1">是</option>
              </select>
            </label>
            {editingCharacter.has_sublimation_point ? (
              <>
                <label>升华进度<select value={editingCharacter.sublimation_status || "seeded"} onChange={(e) => setEditingCharacter({ ...editingCharacter, sublimation_status: e.target.value })}><option value="seeded">已埋种子</option><option value="progressing">推进中</option><option value="completed">已完成</option></select></label>
                <label>升华类型<input value={editingCharacter.sublimation_type || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, sublimation_type: e.target.value })} /></label>
                <label className="drawer-span-2">升华种子<textarea rows={2} value={editingCharacter.sublimation_seed || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, sublimation_seed: e.target.value })} /></label>
                <label className="drawer-span-2">触发条件<textarea rows={2} value={editingCharacter.sublimation_trigger || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, sublimation_trigger: e.target.value })} /></label>
                <label className="drawer-span-2">兑现方式<textarea rows={2} value={editingCharacter.sublimation_payoff || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, sublimation_payoff: e.target.value })} /></label>
              </>
            ) : (
              <div className="hint drawer-span-2">未启用升华线时，只保留基础人物信息与即时状态。</div>
            )}
          </div>
        </div>

        <div className="drawer-section">
          <div className="drawer-section-title">出场范围</div>
          <div className="drawer-grid">
            <label>关联类型<select value={editingCharacter.scope_type || "range"} onChange={(e) => setEditingCharacter({ ...editingCharacter, scope_type: e.target.value, planned_event_scope_text: e.target.value === "full" ? "全篇" : editingCharacter.planned_event_scope_text || "" })}><option value="full">全篇</option><option value="range">区间</option><option value="cameo">客串</option></select></label>
            <label>退出模式<select value={editingCharacter.exit_mode || "active"} onChange={(e) => setEditingCharacter({ ...editingCharacter, exit_mode: e.target.value })}><option value="active">active</option><option value="paused">paused</option><option value="retired">retired</option></select></label>
            <label className="drawer-span-2">计划关联范围<input value={editingCharacter.planned_event_scope_text || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, planned_event_scope_text: e.target.value })} placeholder="例如：全篇 或 1-10,12-14" /></label>
            <label className="drawer-span-2">排除出场范围<input value={editingCharacter.excluded_event_scope_text || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, excluded_event_scope_text: e.target.value })} placeholder="例如：11-12,20-21" /></label>
            <label>退场事件<input type="number" min="1" value={editingCharacter.retired_after_event_id || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, retired_after_event_id: e.target.value })} /></label>
            <label className="toggle drawer-toggle"><input type="checkbox" checked={Boolean(editingCharacter.return_required)} onChange={(e) => setEditingCharacter({ ...editingCharacter, return_required: e.target.checked })} />必须回归</label>
            <label className="drawer-span-2">回归原因<input value={editingCharacter.return_reason || ""} onChange={(e) => setEditingCharacter({ ...editingCharacter, return_reason: e.target.value })} /></label>
          </div>
        </div>

        <div className="drawer-section">
          <div className="section-heading inner-heading">
            <strong>人物设定条目 item_updates</strong>
            <div className="section-actions">
              <button type="button" className="ghost" onClick={addItem}>新增条目</button>
            </div>
          </div>
          <div className="hint">这里维护绑定该人物的物品/功法/势力/境界等初始设定。</div>
          {itemUpdates.length === 0 && <div className="table-empty">暂无人物设定条目</div>}
          <div className="item-editor-list">
            {itemUpdates.map((item, index) => (
              <div key={`item-update-${index}`} className="item-editor-card">
                <div className="drawer-grid">
                  <label>
                    名称
                    <input value={item?.name || ""} onChange={(e) => updateItem(index, { name: e.target.value })} />
                  </label>
                  <label>
                    类型
                    <input value={item?.type || ""} onChange={(e) => updateItem(index, { type: e.target.value })} />
                  </label>
                  <label className="drawer-span-2">
                    描述
                    <textarea rows={2} value={item?.description || ""} onChange={(e) => updateItem(index, { description: e.target.value })} />
                  </label>
                  <label>
                    所在/归属
                    <input value={item?.location || ""} onChange={(e) => updateItem(index, { location: e.target.value })} />
                  </label>
                  <label>
                    关联人物
                    <input
                      value={Array.isArray(item?.related_characters) ? item.related_characters.join(" / ") : ""}
                      onChange={(e) =>
                        updateItem(index, {
                          related_characters: e.target.value
                            .split(/[\/、,，;；]+/)
                            .map((part) => part.trim())
                            .filter(Boolean),
                        })
                      }
                      placeholder="默认绑定当前人物"
                    />
                  </label>
                </div>
                <div className="modal-actions compact-actions">
                  <button type="button" className="ghost danger-text" onClick={() => removeItem(index)}>删除条目</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="modal-actions drawer-actions">
          <button className="ghost" onClick={() => setEditingCharacter(null)}>取消</button>
          <button
            className="primary"
            onClick={async () => {
              await fetch(buildApiUrl(`/api/novels/${selectedNovel}/characters/${encodeURIComponent(editingCharacter.name)}`), {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(editingCharacter),
              });
              setEditingCharacter(null);
              loadNovelDetails(selectedNovel);
            }}
          >
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
