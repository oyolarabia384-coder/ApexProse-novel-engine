import React from "react";

export default function ChapterDrawer({ editingChapter, setEditingChapter, selectedNovel, loadNovelDetails }) {
  if (!editingChapter) return null;

  return (
    <div className="modal">
      <div className="modal-card modal-drawer">
        <div className="drawer-header">
          <div>
            <p className="overline">章节详情</p>
            <h3>编辑章节</h3>
            <div className="hint">把正文、质量和钩子分开编辑，适合快速定位问题。</div>
          </div>
          <button className="ghost" onClick={() => setEditingChapter(null)}>关闭</button>
        </div>
        <div className="drawer-section">
          <div className="drawer-section-title">章节内容</div>
          <div className="drawer-grid">
            <label>标题<input value={editingChapter.title || ""} onChange={(e) => setEditingChapter({ ...editingChapter, title: e.target.value })} /></label>
            <label>摘要<input value={editingChapter.summary || ""} onChange={(e) => setEditingChapter({ ...editingChapter, summary: e.target.value })} /></label>
            <label className="drawer-span-2">正文<textarea rows={12} value={editingChapter.content || ""} onChange={(e) => setEditingChapter({ ...editingChapter, content: e.target.value })} /></label>
          </div>
        </div>

        <div className="drawer-section">
          <div className="drawer-section-title">质量与钩子</div>
          <div className="drawer-grid">
            <label>质量分<input type="number" value={editingChapter.quality_score || 0} onChange={(e) => setEditingChapter({ ...editingChapter, quality_score: Number(e.target.value) || 0 })} /></label>
            <label>重写次数<input type="number" value={editingChapter.rewrite_count || 0} onChange={(e) => setEditingChapter({ ...editingChapter, rewrite_count: Number(e.target.value) || 0 })} /></label>
            <label>爽点类型<input value={editingChapter.cool_point_type || ""} onChange={(e) => setEditingChapter({ ...editingChapter, cool_point_type: e.target.value })} /></label>
            <label>钩子类型<input value={editingChapter.cliffhanger_type || ""} onChange={(e) => setEditingChapter({ ...editingChapter, cliffhanger_type: e.target.value })} /></label>
            <label>钩子强度<input type="number" value={editingChapter.hook_strength || 0} onChange={(e) => setEditingChapter({ ...editingChapter, hook_strength: Number(e.target.value) || 0 })} /></label>
            <label className="drawer-span-2">
              质量问题(JSON数组或文本)
              <textarea
                rows={4}
                value={Array.isArray(editingChapter.quality_issues) ? JSON.stringify(editingChapter.quality_issues, null, 2) : editingChapter.quality_issues || "[]"}
                onChange={(e) => {
                  const raw = e.target.value;
                  let next = raw;
                  try {
                    const parsed = JSON.parse(raw);
                    next = Array.isArray(parsed) ? parsed : raw;
                  } catch {
                    next = raw;
                  }
                  setEditingChapter({ ...editingChapter, quality_issues: next });
                }}
              />
            </label>
          </div>
        </div>

        <div className="modal-actions drawer-actions">
          <button className="ghost" onClick={() => setEditingChapter(null)}>取消</button>
          <button
            className="primary"
            onClick={async () => {
              await fetch(`http://localhost:8000/api/novels/${selectedNovel}/chapters/${editingChapter.chapter_num}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(editingChapter),
              });
              setEditingChapter(null);
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
