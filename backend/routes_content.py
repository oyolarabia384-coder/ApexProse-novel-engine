from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, UploadFile

from engine import *

router = APIRouter()


@router.put("/api/novels/{novel_id}/meta")
def api_update_novel_meta(novel_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    title = str(payload.get("title", "")).strip()
    synopsis = str(payload.get("synopsis", "")).strip()
    style = str(payload.get("style", "")).strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if len(synopsis) > 200:
        raise HTTPException(status_code=400, detail="synopsis too long")
    if not style:
        raise HTTPException(status_code=400, detail="style is required")
    summary = update_novel_metadata(novel_id, title, synopsis, style)
    set_init_step_state(novel_id, "world_setting", "stale")
    mark_dependent_init_steps_stale(novel_id, "world_setting")
    return {"status": "ok", "novel": summary}


@router.get("/api/novels/{novel_id}/init-steps")
def api_init_steps(novel_id: str) -> Dict[str, Any]:
    return {"init_steps": get_init_steps(novel_id)}


@router.put("/api/novels/{novel_id}/init-steps")
def api_update_init_steps(novel_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    step_key = str(payload.get("step_key", "")).strip()
    state = str(payload.get("state", "")).strip()
    if step_key not in INIT_STEP_KEYS:
        raise HTTPException(status_code=400, detail="invalid step key")
    if state not in {"latest", "stale", "locked"}:
        raise HTTPException(status_code=400, detail="invalid state")
    set_init_step_state(novel_id, step_key, state)
    return {"status": "ok", "init_steps": get_init_steps(novel_id)}


@router.get("/api/novels/{novel_id}/seed-world-setting")
def api_seed_world_setting(novel_id: str) -> Dict[str, Any]:
    return {"content": load_init_material(novel_id, "seed_world_setting")}


@router.put("/api/novels/{novel_id}/seed-world-setting")
def api_update_seed_world_setting(novel_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    content = str(payload.get("content", ""))
    save_init_material(novel_id, "seed_world_setting", content)
    set_init_step_state(novel_id, "world_setting", "locked")
    mark_dependent_init_steps_stale(novel_id, "world_setting")
    return {"status": "ok", "content": content, "init_steps": get_init_steps(novel_id)}


@router.put("/api/novels/{novel_id}/series-blueprint")
def api_update_series_blueprint(novel_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    plan = get_story_plan(novel_id)
    blueprint_json = normalize_series_blueprint(payload, plan)
    save_series_blueprint(blueprint_json, novel_id)
    set_init_step_state(novel_id, "series_blueprint", "locked")
    mark_dependent_init_steps_stale(novel_id, "series_blueprint")
    return {"status": "ok", "series_blueprint": blueprint_json, "init_steps": get_init_steps(novel_id)}


@router.put("/api/novels/{novel_id}/growth-system")
def api_update_growth_system(novel_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    plan = get_story_plan(novel_id)
    blueprint_json = load_series_blueprint(novel_id) or normalize_series_blueprint({}, plan)
    merged_blueprint = merge_growth_plan_into_blueprint(blueprint_json, payload, plan)
    save_series_blueprint(merged_blueprint, novel_id)
    set_init_step_state(novel_id, "growth_system", "locked")
    mark_dependent_init_steps_stale(novel_id, "growth_system")
    return {"status": "ok", "growth_system": extract_growth_plan_from_blueprint(merged_blueprint), "growth_snapshot": load_growth_system_json(novel_id), "init_steps": get_init_steps(novel_id)}


@router.get("/api/novels/{novel_id}/worldview-summary")
def api_worldview_summary(novel_id: str) -> Dict[str, Any]:
    return {"content": load_init_material(novel_id, "worldview_summary")}


@router.put("/api/novels/{novel_id}/worldview-summary")
def api_update_worldview_summary(novel_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    content = str(payload.get("content", ""))
    save_init_material(novel_id, "worldview_summary", content)
    set_init_step_state(novel_id, "worldview_summary", "locked")
    mark_dependent_init_steps_stale(novel_id, "worldview_summary")
    return {"status": "ok", "content": content, "init_steps": get_init_steps(novel_id)}


@router.get("/api/novels/{novel_id}/opening-snapshot")
def api_opening_snapshot(novel_id: str) -> Dict[str, Any]:
    return {"content": load_init_material(novel_id, "world_snapshot_current")}


@router.put("/api/novels/{novel_id}/opening-snapshot")
def api_update_opening_snapshot(novel_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    content = str(payload.get("content", ""))
    save_init_material(novel_id, "world_snapshot_current", content)
    save_worldview({"world_state": format_world_snapshot_text(content)}, novel_id)
    set_init_step_state(novel_id, "opening_snapshot", "locked")
    mark_dependent_init_steps_stale(novel_id, "opening_snapshot")
    return {"status": "ok", "content": content, "init_steps": get_init_steps(novel_id)}

@router.delete("/api/novels/{novel_id}")
def api_delete_novel(novel_id: str, force: bool = False) -> Dict[str, Any]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM chapters WHERE novel_id=?", (novel_id,))
    chapter_count = cur.fetchone()[0]
    if chapter_count > 0 and not force:
        conn.close()
        return {"status": "confirm", "chapters": chapter_count}
    conn.close()
    with jobs_lock:
        for job_key in [job_key for job_key, job in jobs.items() if job.get("novel_id") == novel_id]:
            jobs.pop(job_key, None)
    delete_novel_storage(novel_id)
    delete_novel_index_item(novel_id)
    return {"status": "ok"}


@router.put("/api/novels/{novel_id}/characters/{name}")
def api_update_character(novel_id: str, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_db_conn()
    cur = conn.cursor()
    plan = get_story_plan(novel_id)
    scope_type = str(payload.get("scope_type", "range") or "range")
    planned_scope_text = str(payload.get("planned_event_scope_text", "")).strip()
    if planned_scope_text:
        planned_event_ranges = parse_event_scope_text(planned_scope_text, plan["target_event_count"])
    else:
        planned_event_ranges = normalize_event_ranges(payload.get("planned_event_ranges"), plan["target_event_count"])
    if scope_type == "full" and not planned_event_ranges:
        planned_event_ranges = [{"start_event_id": 1, "end_event_id": plan["target_event_count"]}]
    planned_scope_text = planned_scope_text or format_event_range_text(planned_event_ranges, plan["target_event_count"], scope_type)
    excluded_scope_text = str(payload.get("excluded_event_scope_text", "")).strip()
    if excluded_scope_text:
        excluded_event_ranges = parse_event_scope_text(excluded_scope_text, plan["target_event_count"])
    else:
        excluded_event_ranges = normalize_event_ranges(payload.get("excluded_event_ranges"), plan["target_event_count"])
    excluded_scope_text = excluded_scope_text or format_event_range_text(excluded_event_ranges, plan["target_event_count"], "range")
    retired_after_raw = payload.get("retired_after_event_id")
    try:
        retired_after_event_id = int(retired_after_raw) if retired_after_raw not in (None, "") else None
    except Exception:
        retired_after_event_id = None
    cur.execute(
        """
        UPDATE characters SET role_tier=?, target=?, motive=?, secret=?, relationship=?, catchphrase=?, growth_arc=?, strengths=?, flaws=?, behavior_logic=?, has_sublimation_point=?, sublimation_type=?, sublimation_seed=?, sublimation_trigger=?, sublimation_payoff=?, sublimation_status=?, state=?, scope_type=?, planned_event_scope_text=?, planned_event_ranges=?, excluded_event_scope_text=?, excluded_event_ranges=?, exit_mode=?, retired_after_event_id=?, return_required=?, return_reason=?, story_function=?, is_user_edited=1, source='user'
        WHERE novel_id=? AND name=?
        """,
        (
            payload.get("role_tier", "support"),
            payload.get("target", ""),
            payload.get("motive", ""),
            payload.get("secret", ""),
            payload.get("relationship", ""),
            payload.get("catchphrase", ""),
            payload.get("growth_arc", ""),
            dump_string_list(payload.get("strengths", [])),
            dump_string_list(payload.get("flaws", [])),
            payload.get("behavior_logic", ""),
            int(bool(payload.get("has_sublimation_point", False))),
            payload.get("sublimation_type", "") if payload.get("has_sublimation_point", False) else "",
            payload.get("sublimation_seed", "") if payload.get("has_sublimation_point", False) else "",
            payload.get("sublimation_trigger", "") if payload.get("has_sublimation_point", False) else "",
            payload.get("sublimation_payoff", "") if payload.get("has_sublimation_point", False) else "",
            payload.get("sublimation_status", "seeded" if payload.get("has_sublimation_point", False) else "none"),
            payload.get("state", ""),
            scope_type,
            planned_scope_text,
            json.dumps(planned_event_ranges, ensure_ascii=False),
            excluded_scope_text,
            json.dumps(excluded_event_ranges, ensure_ascii=False),
            payload.get("exit_mode", "active"),
            retired_after_event_id,
            int(bool(payload.get("return_required", False))),
            payload.get("return_reason", ""),
            payload.get("story_function", ""),
            novel_id,
            name,
        ),
    )
    conn.commit()
    conn.close()
    set_init_step_state(novel_id, "core_characters", "locked")
    mark_dependent_init_steps_stale(novel_id, "core_characters")
    return {"status": "ok"}


@router.post("/api/novels/{novel_id}/characters/{name}/lock")
def api_lock_character(novel_id: str, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    locked = int(bool(payload.get("locked", True)))
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE characters SET is_locked=? WHERE novel_id=? AND name=?",
        (locked, novel_id, name),
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "locked": locked}


@router.put("/api/novels/{novel_id}/events/{event_id}")
def api_update_event(novel_id: str, event_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_db_conn()
    cur = conn.cursor()
    is_written = int(payload.get("is_written", 0))
    actual_summary = payload.get("actual_summary", "") if is_written else ""
    cur.execute(
        """
        UPDATE events SET description=?, outline_description=?, actual_summary=?, goal=?, obstacle=?, cool_point_type=?, payoff_type=?, growth_reward=?, status_reward=?, cliffhanger=?, ending_phase=?, location=?, time_duration=?, core_conflict=?, foreshadowing=?, linked_characters=?, event_world_snapshot_update=?, event_foreshadow_updates=?, event_growth_updates=?, event_lorebook_updates=?, is_written=?, is_user_edited=1, source='user', status=?
        WHERE novel_id=? AND event_id=?
        """,
        (
            payload.get("description", ""),
            payload.get("outline_description") or payload.get("description", ""),
            actual_summary,
            payload.get("goal", ""),
            payload.get("obstacle", ""),
            payload.get("cool_point_type", ""),
            payload.get("payoff_type", ""),
            payload.get("growth_reward", ""),
            payload.get("status_reward", ""),
            payload.get("cliffhanger", ""),
            payload.get("ending_phase", "normal"),
            payload.get("location", ""),
            payload.get("time_duration", ""),
            payload.get("core_conflict", ""),
            payload.get("foreshadowing", ""),
            payload.get("linked_characters", "[]"),
            payload.get("event_world_snapshot_update", "{}"),
            payload.get("event_foreshadow_updates", "[]"),
            payload.get("event_growth_updates", "{}"),
            payload.get("event_lorebook_updates", "{}"),
            is_written,
            "completed" if is_written else payload.get("status", "planned"),
            novel_id,
            event_id,
        ),
    )
    conn.commit()
    conn.close()
    set_init_step_state(novel_id, "opening_world_planning", "locked")
    mark_dependent_init_steps_stale(novel_id, "opening_world_planning")
    return {"status": "ok"}


@router.post("/api/novels/{novel_id}/events/{event_id}/lock")
def api_lock_event(novel_id: str, event_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    locked = int(bool(payload.get("locked", True)))
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE events SET is_locked=?, status=CASE WHEN ?=1 AND is_written=0 THEN 'locked' WHEN is_written=1 THEN 'completed' ELSE 'planned' END WHERE novel_id=? AND event_id=?",
        (locked, locked, novel_id, event_id),
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "locked": locked}


@router.put("/api/novels/{novel_id}/chapters/{chapter_num}")
def api_update_chapter(novel_id: str, chapter_num: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE chapters SET title=?, summary=?, content=?, quality_score=?, quality_issues=?, rewrite_count=?, cool_point_type=?, hook_strength=?, cliffhanger_type=?, is_user_edited=1, source_event_id=COALESCE(source_event_id, chapter_num), status='user_edited', updated_at=? WHERE novel_id=? AND chapter_num=?",
        (
            payload.get("title", ""),
            payload.get("summary", ""),
            payload.get("content", ""),
            int(payload.get("quality_score", 0) or 0),
            payload.get("quality_issues", "[]") if isinstance(payload.get("quality_issues", "[]"), str) else json.dumps(payload.get("quality_issues", []), ensure_ascii=False),
            int(payload.get("rewrite_count", 0) or 0),
            payload.get("cool_point_type", ""),
            int(payload.get("hook_strength", 0) or 0),
            payload.get("cliffhanger_type", ""),
            datetime.utcnow().isoformat(),
            novel_id,
            chapter_num,
        ),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.delete("/api/novels/{novel_id}/chapters/{chapter_num}")
def api_delete_chapter(novel_id: str, chapter_num: int) -> Dict[str, Any]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM chapters WHERE novel_id=? AND chapter_num=?", (novel_id, chapter_num))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.delete("/api/novels/{novel_id}/chapters")
def api_clear_chapters(novel_id: str) -> Dict[str, Any]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM chapters WHERE novel_id=?", (novel_id,))
    cur.execute(
        "UPDATE events SET is_written=0, actual_summary='', status=CASE WHEN is_locked=1 THEN 'locked' ELSE 'planned' END WHERE novel_id=?",
        (novel_id,),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.post("/api/novels/{novel_id}/chapters/{chapter_num}/lock")
def api_lock_chapter(novel_id: str, chapter_num: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    locked = int(bool(payload.get("locked", True)))
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE chapters SET is_locked=?, status=CASE WHEN ?=1 THEN 'locked' WHEN is_user_edited=1 THEN 'user_edited' ELSE 'ai_final' END, updated_at=? WHERE novel_id=? AND chapter_num=?",
        (locked, locked, datetime.utcnow().isoformat(), novel_id, chapter_num),
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "locked": locked}


@router.get("/api/novels/{novel_id}/worldview")
def api_worldview(novel_id: str) -> Dict[str, Any]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT content, updated_at FROM worldview WHERE novel_id=? LIMIT 1", (novel_id,))
    row = cur.fetchone()
    conn.close()
    return {"content": row[0] if row else "", "updated_at": row[1] if row and len(row) > 1 else None}


@router.get("/api/novels/{novel_id}/series-blueprint")
def api_series_blueprint(novel_id: str) -> Dict[str, Any]:
    blueprint = load_series_blueprint(novel_id)
    return {"series_blueprint": blueprint}


@router.get("/api/novels/{novel_id}/characters")
def api_characters(novel_id: str) -> Dict[str, Any]:
    plan = get_story_plan(novel_id)
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT name, role_tier, target, motive, secret, relationship, catchphrase, growth_arc, strengths, flaws, behavior_logic, has_sublimation_point, sublimation_type, sublimation_seed, sublimation_trigger, sublimation_payoff, sublimation_status, state, scope_type, planned_event_scope_text, planned_event_ranges, excluded_event_scope_text, excluded_event_ranges, exit_mode, retired_after_event_id, return_required, return_reason, init_step, story_function, item_updates, is_locked, is_user_edited, source FROM characters WHERE novel_id=?",
        (novel_id,),
    )
    rows = cur.fetchall()
    conn.close()
    actual_map = get_character_actual_appearance_map(novel_id)
    characters = []
    for r in rows:
        scope_type = r[18] or "range"
        planned_ranges = normalize_event_ranges(parse_json_array_text(r[20]), plan["target_event_count"])
        planned_scope_text = r[19] or format_event_range_text(planned_ranges, plan["target_event_count"], scope_type)
        excluded_ranges = normalize_event_ranges(parse_json_array_text(r[22]), plan["target_event_count"])
        excluded_scope_text = r[21] or format_event_range_text(excluded_ranges, plan["target_event_count"], "range")
        characters.append(
            {
                "name": r[0],
                "role_tier": r[1],
                "target": r[2],
                "motive": r[3],
                "secret": r[4],
                "relationship": r[5],
                "catchphrase": r[6],
                "growth_arc": r[7],
                "strengths": parse_string_list(r[8]),
                "flaws": parse_string_list(r[9]),
                "behavior_logic": r[10],
                "has_sublimation_point": bool(r[11]),
                "sublimation_type": r[12],
                "sublimation_seed": r[13],
                "sublimation_trigger": r[14],
                "sublimation_payoff": r[15],
                "sublimation_status": r[16],
                "state": r[17],
                "scope_type": scope_type,
                "planned_event_scope_text": planned_scope_text,
                "planned_event_ranges": planned_ranges,
                "excluded_event_scope_text": excluded_scope_text,
                "excluded_event_ranges": excluded_ranges,
                "exit_mode": r[23] or "active",
                "retired_after_event_id": r[24],
                "return_required": bool(r[25]),
                "return_reason": r[26] or "",
                "init_step": r[27] or "",
                "story_function": r[28],
                "item_updates": json.loads(r[29]) if r[29] else [],
                "actual_event_scope_text": actual_map.get(r[0], {}).get("actual_event_scope_text", ""),
                "actual_event_ids": actual_map.get(r[0], {}).get("actual_event_ids", []),
                "is_locked": r[30],
                "is_user_edited": r[31],
                "source": r[32],
            }
        )
    return {"characters": characters}


@router.get("/api/novels/{novel_id}/growth-system")
def api_growth_system(novel_id: str) -> Dict[str, Any]:
    return {
        "growth_system": extract_growth_plan_from_blueprint(load_series_blueprint(novel_id) or {}),
        "growth_snapshot": load_growth_system_json(novel_id),
    }


@router.get("/api/novels/{novel_id}/events")
def api_events(novel_id: str) -> Dict[str, Any]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT event_id, description, outline_description, actual_summary, goal, obstacle, cool_point_type, payoff_type, growth_reward, status_reward, cliffhanger, ending_phase, location, time_duration, core_conflict, foreshadowing, linked_characters, event_world_snapshot_update, event_foreshadow_updates, event_growth_updates, event_lorebook_updates, is_written, status, is_locked, is_user_edited, source FROM events WHERE novel_id=? ORDER BY event_id ASC",
        (novel_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return {
        "events": [
            {
                "event_id": r[0],
                "description": r[1],
                "outline_description": r[2],
                "actual_summary": r[3],
                "goal": r[4],
                "obstacle": r[5],
                "cool_point_type": r[6],
                "payoff_type": r[7],
                "growth_reward": r[8],
                "status_reward": r[9],
                "cliffhanger": r[10],
                "ending_phase": r[11],
                "location": r[12],
                "time_duration": r[13],
                "core_conflict": r[14],
                "foreshadowing": r[15],
                "linked_characters": r[16],
                "event_world_snapshot_update": json.loads(r[17]) if r[17] else {},
                "event_foreshadow_updates": json.loads(r[18]) if r[18] else [],
                "event_growth_updates": json.loads(r[19]) if r[19] else {},
                "event_lorebook_updates": json.loads(r[20]) if r[20] else {},
                "is_written": r[21],
                "status": r[22],
                "is_locked": r[23],
                "is_user_edited": r[24],
                "source": r[25],
            }
            for r in rows
        ]
    }


@router.get("/api/novels/{novel_id}/chapters")
def api_chapters_list(novel_id: str) -> Dict[str, Any]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT chapter_num, title, summary, content, source_event_id, quality_score, quality_issues, rewrite_count, cool_point_type, hook_strength, cliffhanger_type, status, is_locked, is_user_edited, updated_at FROM chapters WHERE novel_id=? ORDER BY chapter_num ASC",
        (novel_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return {
        "chapters": [
            {
                "chapter_num": r[0],
                "title": r[1],
                "summary": r[2],
                "content": r[3],
                "source_event_id": r[4],
                "quality_score": r[5],
                "quality_issues": json.loads(r[6]) if r[6] else [],
                "rewrite_count": r[7],
                "cool_point_type": r[8],
                "hook_strength": r[9],
                "cliffhanger_type": r[10],
                "status": r[11],
                "is_locked": r[12],
                "is_user_edited": r[13],
                "updated_at": r[14],
            }
            for r in rows
        ]
    }


@router.get("/api/novels/{novel_id}/lorebook")
def api_lorebook(novel_id: str) -> Dict[str, Any]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT name, type, description, location, related_characters, source_event_id, last_update, is_locked, is_user_edited, source FROM lorebook WHERE novel_id=? ORDER BY name ASC",
        (novel_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return {
        "lorebook": [
            {
                "name": r[0],
                "type": r[1],
                "description": r[2],
                "location": r[3],
                "related_characters": r[4],
                "source_event_id": r[5],
                "last_update": r[6],
                "is_locked": r[7],
                "is_user_edited": r[8],
                "source": r[9],
            }
            for r in rows
        ]
    }


@router.put("/api/novels/{novel_id}/lorebook/{name}")
def api_update_lorebook_item(novel_id: str, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE lorebook SET type=?, description=?, location=?, related_characters=?, source_event_id=?, last_update=?, is_user_edited=1, source='user' WHERE novel_id=? AND name=?",
        (
            payload.get("type", "未知"),
            payload.get("description", ""),
            payload.get("location", ""),
            payload.get("related_characters", "[]"),
            payload.get("source_event_id"),
            payload.get("last_update", "人工编辑"),
            novel_id,
            name,
        ),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.post("/api/novels/{novel_id}/lorebook/{name}/lock")
def api_lock_lorebook_item(novel_id: str, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    locked = int(bool(payload.get("locked", True)))
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE lorebook SET is_locked=? WHERE novel_id=? AND name=?",
        (locked, novel_id, name),
    )
    conn.commit()
    conn.close()
    return {"status": "ok", "locked": locked}


@router.get("/api/novels/{novel_id}/foreshadows")
def api_foreshadows(novel_id: str) -> Dict[str, Any]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, description, introduced_event_id, expected_payoff_event_id, actual_payoff_event_id, status, importance_level, related_characters, notes, source, created_at, updated_at FROM foreshadows WHERE novel_id=? ORDER BY introduced_event_id ASC, id ASC",
        (novel_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return {
        "foreshadows": [
            {
                "id": r[0],
                "description": r[1],
                "introduced_event_id": r[2],
                "expected_payoff_event_id": r[3],
                "actual_payoff_event_id": r[4],
                "status": r[5],
                "importance_level": r[6],
                "related_characters": r[7],
                "notes": r[8],
                "source": r[9],
                "created_at": r[10],
                "updated_at": r[11],
            }
            for r in rows
        ]
    }


@router.post("/api/novels/{novel_id}/export/{section}")
def api_export_section(novel_id: str, section: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    export_dir = ensure_export_dir()
    safe_section = section.strip().lower()
    file_path = ""

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT title FROM novels WHERE id=? LIMIT 1", (novel_id,))
    novel_row = cur.fetchone()
    novel_title = sanitize_filename(novel_row[0] if novel_row else f"小说{novel_id}")

    if safe_section == "worldview":
        cur.execute("SELECT content FROM worldview WHERE novel_id=? LIMIT 1", (novel_id,))
        row = cur.fetchone()
        file_path = os.path.join(export_dir, f"{novel_title}-世界观.txt")
        write_txt(file_path, row[0] if row else "")
    elif safe_section == "characters":
        cur.execute("SELECT name, role_tier, target, motive, secret, relationship, catchphrase, growth_arc, strengths, flaws, behavior_logic, has_sublimation_point, sublimation_type, sublimation_seed, sublimation_trigger, sublimation_payoff, sublimation_status, state, scope_type, planned_event_scope_text, planned_event_ranges, story_function, item_updates, is_locked, is_user_edited, source FROM characters WHERE novel_id=? ORDER BY name ASC", (novel_id,))
        rows = cur.fetchall()
        file_path = os.path.join(export_dir, f"{novel_title}-人物卡.csv")
        write_csv(file_path, ["name", "role_tier", "target", "motive", "secret", "relationship", "catchphrase", "growth_arc", "strengths", "flaws", "behavior_logic", "has_sublimation_point", "sublimation_type", "sublimation_seed", "sublimation_trigger", "sublimation_payoff", "sublimation_status", "state", "scope_type", "planned_event_scope_text", "planned_event_ranges", "story_function", "item_updates", "is_locked", "is_user_edited", "source"], [
            {"name": r[0], "role_tier": r[1], "target": r[2], "motive": r[3], "secret": r[4], "relationship": r[5], "catchphrase": r[6], "growth_arc": r[7], "strengths": r[8], "flaws": r[9], "behavior_logic": r[10], "has_sublimation_point": r[11], "sublimation_type": r[12], "sublimation_seed": r[13], "sublimation_trigger": r[14], "sublimation_payoff": r[15], "sublimation_status": r[16], "state": r[17], "scope_type": r[18], "planned_event_scope_text": r[19], "planned_event_ranges": r[20], "story_function": r[21], "item_updates": r[22], "is_locked": r[23], "is_user_edited": r[24], "source": r[25]}
            for r in rows
        ])
    elif safe_section == "events":
        cur.execute("SELECT event_id, description, outline_description, actual_summary, goal, obstacle, cool_point_type, payoff_type, growth_reward, status_reward, cliffhanger, ending_phase, location, time_duration, core_conflict, foreshadowing, linked_characters, event_world_snapshot_update, event_foreshadow_updates, event_growth_updates, event_lorebook_updates, is_written, status, is_locked, is_user_edited, source FROM events WHERE novel_id=? ORDER BY event_id ASC", (novel_id,))
        rows = cur.fetchall()
        file_path = os.path.join(export_dir, f"{novel_title}-事件列表.csv")
        write_csv(file_path, ["event_id", "description", "outline_description", "actual_summary", "goal", "obstacle", "cool_point_type", "payoff_type", "growth_reward", "status_reward", "cliffhanger", "ending_phase", "location", "time_duration", "core_conflict", "foreshadowing", "linked_characters", "event_world_snapshot_update", "event_foreshadow_updates", "event_growth_updates", "event_lorebook_updates", "is_written", "status", "is_locked", "is_user_edited", "source"], [
            {"event_id": r[0], "description": r[1], "outline_description": r[2], "actual_summary": r[3], "goal": r[4], "obstacle": r[5], "cool_point_type": r[6], "payoff_type": r[7], "growth_reward": r[8], "status_reward": r[9], "cliffhanger": r[10], "ending_phase": r[11], "location": r[12], "time_duration": r[13], "core_conflict": r[14], "foreshadowing": r[15], "linked_characters": r[16], "event_world_snapshot_update": r[17], "event_foreshadow_updates": r[18], "event_growth_updates": r[19], "event_lorebook_updates": r[20], "is_written": r[21], "status": r[22], "is_locked": r[23], "is_user_edited": r[24], "source": r[25]}
            for r in rows
        ])
    elif safe_section == "lorebook":
        cur.execute("SELECT name, type, description, location, related_characters, source_event_id, last_update, is_locked, is_user_edited, source FROM lorebook WHERE novel_id=? ORDER BY name ASC", (novel_id,))
        rows = cur.fetchall()
        file_path = os.path.join(export_dir, f"{novel_title}-设定库.csv")
        write_csv(file_path, ["name", "type", "description", "location", "related_characters", "source_event_id", "last_update", "is_locked", "is_user_edited", "source"], [
            {"name": r[0], "type": r[1], "description": r[2], "location": r[3], "related_characters": r[4], "source_event_id": r[5], "last_update": r[6], "is_locked": r[7], "is_user_edited": r[8], "source": r[9]}
            for r in rows
        ])
    elif safe_section == "foreshadows":
        cur.execute("SELECT id, description, introduced_event_id, expected_payoff_event_id, actual_payoff_event_id, status, importance_level, related_characters, notes, source, created_at, updated_at FROM foreshadows WHERE novel_id=? ORDER BY introduced_event_id ASC, id ASC", (novel_id,))
        rows = cur.fetchall()
        file_path = os.path.join(export_dir, f"{novel_title}-伏笔.csv")
        write_csv(file_path, ["id", "description", "introduced_event_id", "expected_payoff_event_id", "actual_payoff_event_id", "status", "importance_level", "related_characters", "notes", "source", "created_at", "updated_at"], [
            {"id": r[0], "description": r[1], "introduced_event_id": r[2], "expected_payoff_event_id": r[3], "actual_payoff_event_id": r[4], "status": r[5], "importance_level": r[6], "related_characters": r[7], "notes": r[8], "source": r[9], "created_at": r[10], "updated_at": r[11]}
            for r in rows
        ])
    elif safe_section == "chapter_selected":
        chapter_num = payload.get("chapter_num")
        cur.execute("SELECT chapter_num, title, content FROM chapters WHERE novel_id=? AND chapter_num=? LIMIT 1", (novel_id, chapter_num))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Chapter not found")
        chapter_title = sanitize_filename(f"第 {row[0]} 章 {row[1] or ''}".strip())
        file_path = os.path.join(export_dir, f"{novel_title}-{chapter_title}.txt")
        write_txt(file_path, f"第 {row[0]} 章 {row[1] or ''}\n{row[2] or ''}")
    elif safe_section == "chapters_all":
        cur.execute("SELECT chapter_num, title, content FROM chapters WHERE novel_id=? ORDER BY chapter_num ASC", (novel_id,))
        rows = cur.fetchall()
        files = []
        for row in rows:
            title_line = f"第 {row[0]} 章 {row[1] or ''}".strip()
            chapter_title = sanitize_filename(title_line)
            one_path = os.path.join(export_dir, f"{novel_title}-{chapter_title}.txt")
            write_txt(one_path, f"{title_line}\n{row[2] or ''}")
            files.append(one_path)
        conn.close()
        return {"status": "ok", "file_paths": files, "count": len(files)}
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="Unsupported export section")

    conn.close()
    return {"status": "ok", "file_path": file_path}


@router.post("/api/novels/{novel_id}/import/{section}")
async def api_import_section(novel_id: str, section: str, file: UploadFile = File(...)) -> Dict[str, Any]:
    safe_section = section.strip().lower()
    if safe_section not in {"worldview", "characters", "events", "lorebook", "foreshadows"}:
        raise HTTPException(status_code=400, detail="Unsupported import section")

    raw = await file.read()
    text = raw.decode("utf-8-sig")

    conn = get_db_conn()
    cur = conn.cursor()
    imported = 0

    if safe_section == "worldview":
        now = datetime.utcnow().isoformat()
        cur.execute("DELETE FROM worldview WHERE novel_id=?", (novel_id,))
        cur.execute("DELETE FROM worldview_snapshots WHERE novel_id=?", (novel_id,))
        cur.execute("INSERT INTO worldview (novel_id, content, updated_at) VALUES (?, ?, ?)", (novel_id, text, now))
        cur.execute(
            "INSERT INTO worldview_snapshots (novel_id, source_event_id, content, summary, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (novel_id, None, text, "手动导入世界观", "user_import", now),
        )
        conn.commit()
        conn.close()
        return {"status": "ok", "imported": 1}

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if safe_section == "characters":
        cur.execute("DELETE FROM characters WHERE novel_id=?", (novel_id,))
        cur.execute("DELETE FROM character_state_history WHERE novel_id=?", (novel_id,))
        for row in rows:
            cur.execute(
                "INSERT INTO characters (novel_id, name, role_tier, target, motive, secret, relationship, catchphrase, growth_arc, strengths, flaws, behavior_logic, has_sublimation_point, sublimation_type, sublimation_seed, sublimation_trigger, sublimation_payoff, sublimation_status, state, scope_type, planned_event_scope_text, planned_event_ranges, story_function, item_updates, is_locked, is_user_edited, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    novel_id,
                    row.get("name", ""),
                    row.get("role_tier", "support"),
                    row.get("target", ""),
                    row.get("motive", ""),
                    row.get("secret", ""),
                    row.get("relationship", ""),
                    row.get("catchphrase", ""),
                    row.get("growth_arc", ""),
                    dump_string_list(row.get("strengths", "[]")),
                    dump_string_list(row.get("flaws", "[]")),
                    row.get("behavior_logic", ""),
                    int(row.get("has_sublimation_point", 0) or 0),
                    row.get("sublimation_type", ""),
                    row.get("sublimation_seed", ""),
                    row.get("sublimation_trigger", ""),
                    row.get("sublimation_payoff", ""),
                    row.get("sublimation_status", "seeded" if int(row.get("has_sublimation_point", 0) or 0) else "none"),
                    row.get("state", ""),
                    row.get("scope_type", "range"),
                    row.get("planned_event_scope_text", ""),
                    row.get("planned_event_ranges", "[]"),
                    row.get("story_function", ""),
                    row.get("item_updates", "[]"),
                    int(row.get("is_locked", 0) or 0),
                    1,
                    "user",
                ),
            )
            imported += 1
    elif safe_section == "events":
        cur.execute("DELETE FROM events WHERE novel_id=?", (novel_id,))
        for row in rows:
            cur.execute(
                "INSERT INTO events (novel_id, event_id, description, outline_description, actual_summary, goal, obstacle, cool_point_type, payoff_type, growth_reward, status_reward, cliffhanger, ending_phase, location, time_duration, core_conflict, foreshadowing, linked_characters, event_world_snapshot_update, event_foreshadow_updates, event_growth_updates, event_lorebook_updates, is_written, status, is_locked, is_user_edited, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (novel_id, int(row.get("event_id", 0) or 0), row.get("description", ""), row.get("outline_description", ""), row.get("actual_summary", ""), row.get("goal", ""), row.get("obstacle", ""), row.get("cool_point_type", ""), row.get("payoff_type", ""), row.get("growth_reward", ""), row.get("status_reward", ""), row.get("cliffhanger", ""), row.get("ending_phase", "normal"), row.get("location", ""), row.get("time_duration", ""), row.get("core_conflict", ""), row.get("foreshadowing", ""), row.get("linked_characters", "[]"), row.get("event_world_snapshot_update", "{}"), row.get("event_foreshadow_updates", "[]"), row.get("event_growth_updates", "{}"), row.get("event_lorebook_updates", "{}"), int(row.get("is_written", 0) or 0), row.get("status", "planned"), int(row.get("is_locked", 0) or 0), 1, "user"),
            )
            imported += 1
    elif safe_section == "lorebook":
        cur.execute("DELETE FROM lorebook WHERE novel_id=?", (novel_id,))
        for row in rows:
            cur.execute(
                "INSERT INTO lorebook (novel_id, name, type, description, location, related_characters, source_event_id, last_update, is_locked, is_user_edited, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (novel_id, row.get("name", ""), row.get("type", ""), row.get("description", ""), row.get("location", ""), row.get("related_characters", "[]"), row.get("source_event_id"), row.get("last_update", "人工导入"), int(row.get("is_locked", 0) or 0), 1, "user"),
            )
            imported += 1
    elif safe_section == "foreshadows":
        cur.execute("DELETE FROM foreshadows WHERE novel_id=?", (novel_id,))
        for row in rows:
            cur.execute(
                "INSERT INTO foreshadows (novel_id, description, introduced_event_id, expected_payoff_event_id, actual_payoff_event_id, status, importance_level, related_characters, notes, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (novel_id, row.get("description", ""), row.get("introduced_event_id"), row.get("expected_payoff_event_id"), row.get("actual_payoff_event_id"), row.get("status", "open"), row.get("importance_level", "medium"), row.get("related_characters", "[]"), row.get("notes", ""), "user", datetime.utcnow().isoformat(), datetime.utcnow().isoformat()),
            )
            imported += 1

    conn.commit()
    conn.close()
    if safe_section in {"events", "foreshadows"}:
        sync_foreshadow_active_count(novel_id)
    return {"status": "ok", "imported": imported}


