from typing import Any, Dict
import json
import time

from fastapi import APIRouter

from schemas import ChapterRequest, EventRewriteRequest, InitStepRequest, NovelCreateRequest, OutlineRequest
from engine import *

router = APIRouter()

@router.post("/api/novels")
def api_create_novel(req: NovelCreateRequest) -> Dict[str, Any]:
    novel_id = generate_novel_id()
    create_novel_storage(novel_id, req.title, req.synopsis, req.style, req.target_words)
    data = load_config()
    data["default_style"] = req.style
    save_config(data)
    return {"status": "ok", "novel_id": novel_id}


@router.get("/api/novels")
def api_list_novels() -> Dict[str, Any]:
    return {"novels": list_novel_summaries()}


@router.get("/api/novels/{novel_id}/dashboard")
def api_novel_dashboard(novel_id: str) -> Dict[str, Any]:
    plan = get_story_plan(novel_id)
    counts = get_event_counts(novel_id)
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM characters WHERE novel_id=?", (novel_id,))
    characters = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM events WHERE novel_id=?", (novel_id,))
    events = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chapters WHERE novel_id=?", (novel_id,))
    chapters = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM lorebook WHERE novel_id=?", (novel_id,))
    lorebook = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM foreshadows WHERE novel_id=? AND status != 'paid_off'", (novel_id,))
    open_foreshadows = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM events WHERE novel_id=? AND is_user_edited=1", (novel_id,))
    user_edited_events = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM chapters WHERE novel_id=? AND is_user_edited=1", (novel_id,))
    user_edited_chapters = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM characters WHERE novel_id=? AND is_user_edited=1", (novel_id,))
    user_edited_characters = cur.fetchone()[0]
    conn.close()
    return {
        "novels": len(load_novel_index()),
        "target_words": plan["target_words"],
        "target_event_count": plan["target_event_count"],
        "opening_breakthrough_count": plan["opening_breakthrough_count"],
        "development_end_event_id": plan["development_end_event_id"],
        "ending_start_event_id": plan["ending_start_event_id"],
        "ending_event_count": plan["ending_event_count"],
        "written_events": counts["written"],
        "unwritten_events": counts["unwritten"],
        "story_phase": determine_current_story_phase(novel_id),
        "characters": characters,
        "events": events,
        "chapters": chapters,
        "lorebook": lorebook,
        "open_foreshadows": open_foreshadows,
        "user_edited_events": user_edited_events,
        "user_edited_chapters": user_edited_chapters,
        "user_edited_characters": user_edited_characters,
        "running_jobs": sum(1 for job in jobs.values() if job.get("status") == "running"),
        "event_runs": fetch_latest_event_runs(novel_id, 10),
    }


@router.put("/api/novels/{novel_id}/plan")
def api_update_novel_plan(novel_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    target_words_raw = payload.get("target_words", 0)
    if target_words_raw in (None, ""):
        raise HTTPException(status_code=400, detail="target_words is required")
    plan = update_novel_story_plan(novel_id, int(target_words_raw))
    phase_key = sync_novel_phase(novel_id)
    return {"status": "ok", "story_plan": plan, "story_phase": phase_key}


def build_init_prompt_set(req: InitStepRequest) -> Dict[str, Dict[str, str]]:
    return {
        "prompt1_world_setting": req.prompt1_world_setting.model_dump(),
        "prompt2_series_blueprint": req.prompt2_series_blueprint.model_dump(),
        "prompt3_growth_system": req.prompt3_growth_system.model_dump(),
        "prompt4_core_characters": req.prompt4_core_characters.model_dump(),
        "prompt5_worldview_summary": req.prompt5_worldview_summary.model_dump(),
        "prompt6_opening_snapshot": req.prompt6_opening_snapshot.model_dump(),
        "prompt7_opening_world_planning": req.prompt7_opening_world_planning.model_dump(),
        "prompt_internal_supplement_characters": req.prompt_internal_supplement_characters.model_dump(),
    }


def ensure_can_regenerate_init_outputs(novel_id: str, step_name: str) -> None:
    if step_name not in {"core_characters", "worldview_summary", "opening_snapshot", "opening_world_planning"}:
        return
    chapter_count = get_chapter_count(novel_id)
    counts = get_event_counts(novel_id)
    if chapter_count > 0 or counts["written"] > 0:
        raise HTTPException(status_code=400, detail="当前小说已开始写正文，请改用手动编辑，不要重生成初始化内容")


def clear_opening_events(novel_id: str) -> None:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("DELETE FROM foreshadows WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM events WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM chapters WHERE novel_id=?", (novel_id,))
    conn.commit()
    conn.close()
    sync_foreshadow_active_count(novel_id)


def clear_initial_characters(novel_id: str) -> None:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("DELETE FROM character_state_history WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM characters WHERE novel_id=?", (novel_id,))
    conn.commit()
    conn.close()


def build_core_character_stage_summary(blueprint_json: Dict[str, Any], growth_json: Dict[str, Any]) -> str:
    story_core = blueprint_json.get("story_core") or {}
    opening_stage = None
    for item in blueprint_json.get("stage_plan", []):
        if isinstance(item, dict) and item.get("phase") == "opening_breakthrough":
            opening_stage = item
            break
    opening_stage = opening_stage or {}
    growth_items = growth_json.get("stage_growth_plan") if isinstance(growth_json, dict) else []
    growth_opening = None
    if isinstance(growth_items, list):
        for item in growth_items:
            if isinstance(item, dict) and item.get("phase") == "opening_breakthrough":
                growth_opening = item
                break
    growth_opening = growth_opening or {}
    payload = {
        "story_core": {
            "core_conflict": story_core.get("core_conflict", ""),
            "golden_finger": story_core.get("golden_finger", ""),
            "short_term_goal": story_core.get("short_term_goal", ""),
            "ultimate_goal": story_core.get("ultimate_goal", ""),
        },
        "opening_breakthrough": {
            "range": f"{opening_stage.get('start_event_id', '')}-{opening_stage.get('end_event_id', '')}",
            "phase_goal": opening_stage.get("phase_goal", ""),
            "phase_requirements": opening_stage.get("phase_requirements", []),
            "progress_focus": opening_stage.get("progress_focus", ""),
            "exit_condition": opening_stage.get("exit_condition", ""),
        },
        "later_stages": [
            {
                "phase": item.get("phase", ""),
                "goal": item.get("phase_goal", ""),
            }
            for item in blueprint_json.get("stage_plan", [])
            if isinstance(item, dict) and item.get("phase") != "opening_breakthrough"
        ],
        "opening_growth": {
            "growth_goal": growth_opening.get("growth_goal", ""),
            "power_goal": growth_opening.get("power_goal", ""),
            "resource_goal": growth_opening.get("resource_goal", ""),
            "influence_goal": growth_opening.get("influence_goal", ""),
            "growth_bottleneck": growth_opening.get("growth_bottleneck", ""),
            "growth_milestone": growth_opening.get("growth_milestone", ""),
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def load_character_cards_for_prompt(novel_id: str) -> list[Dict[str, Any]]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT name, role_tier, target, motive, secret, relationship, catchphrase, growth_arc, strengths, flaws, behavior_logic, has_sublimation_point, sublimation_type, sublimation_seed, sublimation_trigger, sublimation_payoff, sublimation_status, state, scope_type, planned_event_scope_text, planned_event_ranges, excluded_event_scope_text, excluded_event_ranges, exit_mode, retired_after_event_id, return_required, return_reason, story_function FROM characters WHERE novel_id=? ORDER BY name ASC",
        (novel_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "name": row[0],
            "role_tier": row[1],
            "target": row[2],
            "motive": row[3],
            "secret": row[4],
            "relationship": row[5],
            "catchphrase": row[6],
            "growth_arc": row[7],
            "strengths": parse_string_list(row[8]),
            "flaws": parse_string_list(row[9]),
            "behavior_logic": row[10],
            "has_sublimation_point": bool(row[11]),
            "sublimation_type": row[12],
            "sublimation_seed": row[13],
            "sublimation_trigger": row[14],
            "sublimation_payoff": row[15],
            "sublimation_status": row[16],
            "state": row[17],
            "scope_type": row[18],
            "planned_event_scope_text": row[19],
            "planned_event_ranges": parse_json_array_text(row[20]),
            "excluded_event_scope_text": row[21],
            "excluded_event_ranges": parse_json_array_text(row[22]),
            "exit_mode": row[23],
            "retired_after_event_id": row[24],
            "return_required": bool(row[25]),
            "return_reason": row[26],
            "story_function": row[27],
        }
        for row in rows
    ]


def apply_character_exit_plan(events_json: List[Dict[str, Any]], novel_id: str) -> int:
    if not events_json:
        return 0
    plan = get_story_plan(novel_id)
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    updated = 0
    for ev in events_json:
        event_id = ev.get("event_id")
        if event_id is None:
            continue
        try:
            event_id_int = int(event_id)
        except Exception:
            continue
        exits = ev.get("exiting_characters") or []
        if not isinstance(exits, list) or not exits:
            continue
        for name in exits:
            if not name:
                continue
            cur.execute("SELECT is_locked FROM characters WHERE novel_id=? AND name=?", (novel_id, name))
            row = cur.fetchone()
            if not row:
                continue
            if row[0]:
                continue
            cur.execute(
                "UPDATE characters SET exit_mode='retired', retired_after_event_id=? WHERE novel_id=? AND name=?",
                (event_id_int, novel_id, name),
            )
            updated += 1
    if updated:
        conn.commit()
    conn.close()
    return updated


def extract_opening_snapshot_payload(payload: Any) -> Tuple[str, List[Dict[str, Any]]]:
    if not isinstance(payload, dict):
        return "", []
    value = payload.get("opening_snapshot")
    if isinstance(value, (dict, list)):
        snapshot_text = json.dumps(value, ensure_ascii=False, indent=2).strip()
    else:
        snapshot_text = str(value or "").strip()
    lorebook = payload.get("lorebook", [])
    if not isinstance(lorebook, list):
        lorebook = []
    return snapshot_text, lorebook


@router.post("/api/novels/{novel_id}/initialize/{step_name}")
def api_initialize_step(novel_id: str, step_name: str, req: InitStepRequest) -> Dict[str, Any]:
    summary = get_novel_summary(novel_id)
    synopsis = summary.get("synopsis", "")
    if not synopsis:
        raise HTTPException(status_code=400, detail="请先填写小说梗概")
    prompt_set = build_init_prompt_set(req)
    client = OpenAIClient(req.api)
    plan = get_story_plan(novel_id)
    initial_event_count = plan["opening_breakthrough_count"]

    if step_name == "world_setting":
        system_prompt, user_prompt = render_prompt_messages(prompt_set["prompt1_world_setting"], {"setting": synopsis})
        world_setting = client.chat(user_prompt, system_prompt=system_prompt, meta={"step": "init", "prompt": "prompt1_world_setting", "novel_id": novel_id})
        save_init_material(novel_id, "seed_world_setting", world_setting)
        set_init_step_state(novel_id, "world_setting", "latest")
        return {"status": "ok", "step": step_name, "content": world_setting}

    world_setting = load_init_material(novel_id, "seed_world_setting")
    if not world_setting:
        raise HTTPException(status_code=400, detail="请先生成世界设定")

    if step_name == "series_blueprint":
        story_plan_note = build_story_plan_note(novel_id, 1, plan["target_event_count"])
        blueprint_system_prompt, blueprint_prompt = render_prompt_messages(
            prompt_set["prompt2_series_blueprint"],
            {"setting": synopsis, "world_setting": world_setting, "system_plan": story_plan_note},
        )
        blueprint_reply = client.chat(
            blueprint_prompt,
            system_prompt=blueprint_system_prompt,
            meta={"step": "init", "prompt": "prompt2_series_blueprint", "novel_id": novel_id},
        )
        blueprint_raw = parse_json_with_fix(
            client,
            blueprint_reply,
            "object",
            meta={"prompt": "prompt2_series_blueprint", "novel_id": novel_id},
        )
        blueprint_json = normalize_series_blueprint(blueprint_raw, plan)
        save_series_blueprint(blueprint_json, novel_id)
        set_init_step_state(novel_id, "series_blueprint", "latest")
        return {"status": "ok", "step": step_name, "series_blueprint": blueprint_json}

    blueprint_json = load_series_blueprint(novel_id)
    if not blueprint_json:
        raise HTTPException(status_code=400, detail="请先生成阶段计划")

    if step_name == "growth_system":
        growth_system_prompt, growth_prompt = render_prompt_messages(
            prompt_set["prompt3_growth_system"],
            {
                "setting": synopsis,
                "world_setting": world_setting,
                "stage_plan": json.dumps(blueprint_json.get("stage_plan", []), ensure_ascii=False),
                "system_plan": json.dumps(blueprint_json.get("system_plan", {}), ensure_ascii=False),
            },
        )
        growth_reply = client.chat(
            growth_prompt,
            system_prompt=growth_system_prompt,
            meta={"step": "init", "prompt": "prompt3_growth_system", "novel_id": novel_id},
        )
        growth_json = parse_json_with_fix(
            client,
            growth_reply,
            "object",
            meta={"prompt": "prompt3_growth_system", "novel_id": novel_id},
        )
        merged_blueprint = merge_growth_plan_into_blueprint(blueprint_json, growth_json, plan)
        save_series_blueprint(merged_blueprint, novel_id)
        set_init_step_state(novel_id, "growth_system", "latest")
        return {"status": "ok", "step": step_name, "growth_system": extract_growth_plan_from_blueprint(merged_blueprint)}

    growth_json = extract_growth_plan_from_blueprint(blueprint_json)
    if not growth_json.get("stage_growth_plan"):
        raise HTTPException(status_code=400, detail="请先生成主角成长规划")

    if step_name == "core_characters":
        ensure_can_regenerate_init_outputs(novel_id, "core_characters")
        clear_initial_characters(novel_id)
        core_stage_summary = build_core_character_stage_summary(blueprint_json, growth_json)
        system_plan_note = build_story_plan_note(novel_id, 1, plan["target_event_count"])
        prompt3_system_prompt, prompt3_user_template = render_prompt_messages(
            prompt_set["prompt4_core_characters"],
            {"system_plan": system_plan_note},
        )
        prompt3_full = (
            f"【世界观设定】\n{world_setting}\n\n"
            f"【阶段计划摘要】\n{core_stage_summary}\n\n"
            "【当前事件列表】\n当前尚未生成开篇事件，请只生成开篇必需角色与会长期影响主线的核心角色。\n\n"
            f"{prompt3_user_template}"
        )
        chars_reply = client.chat(prompt3_full, system_prompt=prompt3_system_prompt, meta={"step": "init", "prompt": "prompt4_core_characters", "novel_id": novel_id})
        chars_json = parse_json_with_fix(client, chars_reply, "array", meta={"prompt": "prompt4_core_characters", "novel_id": novel_id})
        save_characters(chars_json, novel_id, blueprint_json, init_step="core_characters")
        set_init_step_state(novel_id, "core_characters", "latest")
        return {"status": "ok", "step": step_name, "characters_saved": len(chars_json)}

    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM characters WHERE novel_id=?", (novel_id,))
    character_count = int(cur.fetchone()[0] or 0)
    conn.close()
    if character_count == 0:
        raise HTTPException(status_code=400, detail="请先生成核心人物卡")

    if step_name == "worldview_summary":
        ensure_can_regenerate_init_outputs(novel_id, step_name)
        conn = get_db_conn(novel_id)
        cur = conn.cursor()
        cur.execute(
            "SELECT name, role_tier, target, motive, secret, relationship, catchphrase, growth_arc, strengths, flaws, behavior_logic, has_sublimation_point, sublimation_type, sublimation_seed, sublimation_trigger, sublimation_payoff, sublimation_status, state, scope_type, planned_event_scope_text, planned_event_ranges, story_function FROM characters WHERE novel_id=? ORDER BY name ASC",
            (novel_id,),
        )
        char_rows = cur.fetchall()
        conn.close()
        chars_json = [
            {
                "name": row[0],
                "role_tier": row[1],
                "target": row[2],
                "motive": row[3],
                "secret": row[4],
                "relationship": row[5],
                "catchphrase": row[6],
                "growth_arc": row[7],
                "strengths": parse_string_list(row[8]),
                "flaws": parse_string_list(row[9]),
                "behavior_logic": row[10],
                "has_sublimation_point": bool(row[11]),
                "sublimation_type": row[12],
                "sublimation_seed": row[13],
                "sublimation_trigger": row[14],
                "sublimation_payoff": row[15],
                "sublimation_status": row[16],
                "state": row[17],
                "scope_type": row[18],
                "planned_event_scope_text": row[19],
                "planned_event_ranges": parse_json_array_text(row[20]),
                "story_function": row[21],
            }
            for row in char_rows
        ]
        prompt5_system_prompt, prompt5_user_template = render_prompt_messages(prompt_set["prompt5_worldview_summary"], {})
        prompt5_full = (
            f"【世界设定】\n{world_setting}\n\n"
            f"【一句话梗概】\n{synopsis}\n\n"
            f"【阶段计划】\n{json.dumps(blueprint_json, ensure_ascii=False)}\n\n"
            f"【主角成长规划】\n{json.dumps(growth_json, ensure_ascii=False)}\n\n"
            f"【核心人物卡】\n{json.dumps(chars_json, ensure_ascii=False)}\n\n"
            f"{prompt5_user_template}"
        )
        summary_reply = client.chat(prompt5_full, system_prompt=prompt5_system_prompt, meta={"step": "init", "prompt": "prompt5_worldview_summary", "novel_id": novel_id})
        summary_json = parse_json_with_fix(client, summary_reply, "object", meta={"prompt": "prompt5_worldview_summary", "novel_id": novel_id})
        save_init_material(novel_id, "worldview_summary", summary_json.get("worldview_summary", ""))
        set_init_step_state(novel_id, "worldview_summary", "latest")
        return {"status": "ok", "step": step_name, "content": load_init_material(novel_id, "worldview_summary")}

    worldview_summary = load_init_material(novel_id, "worldview_summary")
    if not worldview_summary:
        raise HTTPException(status_code=400, detail="请先生成世界观摘要")

    if step_name == "opening_snapshot":
        ensure_can_regenerate_init_outputs(novel_id, step_name)
        snapshot_chars_json = load_character_cards_for_prompt(novel_id)
        prompt6_system_prompt, prompt6_user_template = render_prompt_messages(prompt_set["prompt6_opening_snapshot"], {})
        prompt6_full = (
            f"【世界设定】\n{world_setting}\n\n"
            f"【一句话梗概】\n{synopsis}\n\n"
            f"【阶段计划】\n{json.dumps(blueprint_json, ensure_ascii=False)}\n\n"
            f"【主角成长规划】\n{json.dumps(growth_json, ensure_ascii=False)}\n\n"
            f"【核心人物卡】\n{json.dumps(snapshot_chars_json, ensure_ascii=False)}\n\n"
            f"【世界观摘要】\n{worldview_summary}\n\n"
            f"{prompt6_user_template}"
        )
        snapshot_reply = client.chat(prompt6_full, system_prompt=prompt6_system_prompt, meta={"step": "init", "prompt": "prompt6_opening_snapshot", "novel_id": novel_id})
        snapshot_json = parse_json_with_fix(client, snapshot_reply, "object", meta={"prompt": "prompt6_opening_snapshot", "novel_id": novel_id})
        snapshot_text, lorebook_items = extract_opening_snapshot_payload(snapshot_json)
        if not snapshot_text:
            raise HTTPException(status_code=500, detail="世界快照生成成功但返回字段缺失，需返回 opening_snapshot")
        save_init_material(novel_id, "world_snapshot_current", snapshot_text)
        if lorebook_items:
            for item in lorebook_items:
                if isinstance(item, dict):
                    item.setdefault("source_event_id", None)
                    item.setdefault("last_update", "世界快照初始化")
                    item.setdefault("source", "world_snapshot")
            upsert_lorebook_items(lorebook_items, novel_id)
        save_worldview({"world_state": format_world_snapshot_text(snapshot_text)}, novel_id)
        set_init_step_state(novel_id, "opening_snapshot", "latest")
        return {"status": "ok", "step": step_name, "content": load_init_material(novel_id, "world_snapshot_current")}

    opening_snapshot = load_init_material(novel_id, "world_snapshot_current")
    if not opening_snapshot:
        raise HTTPException(status_code=400, detail="请先生成世界快照")

    if step_name == "opening_world_planning":
        ensure_can_regenerate_init_outputs(novel_id, step_name)
        clear_opening_events(novel_id)
        conn = get_db_conn(novel_id)
        cur = conn.cursor()
        cur.execute(
            "SELECT name, role_tier, target, motive, secret, relationship, catchphrase, growth_arc, strengths, flaws, behavior_logic, has_sublimation_point, sublimation_type, sublimation_seed, sublimation_trigger, sublimation_payoff, sublimation_status, state, scope_type, planned_event_scope_text, planned_event_ranges, excluded_event_scope_text, excluded_event_ranges, exit_mode, retired_after_event_id, return_required, return_reason, story_function FROM characters WHERE novel_id=? ORDER BY name ASC",
            (novel_id,),
        )
        char_rows = cur.fetchall()
        conn.close()
        core_chars_json = [
            {
                "name": row[0],
                "role_tier": row[1],
                "target": row[2],
                "motive": row[3],
                "secret": row[4],
                "relationship": row[5],
                "catchphrase": row[6],
                "growth_arc": row[7],
                "strengths": parse_string_list(row[8]),
                "flaws": parse_string_list(row[9]),
                "behavior_logic": row[10],
                "has_sublimation_point": bool(row[11]),
                "sublimation_type": row[12],
                "sublimation_seed": row[13],
                "sublimation_trigger": row[14],
                "sublimation_payoff": row[15],
                "sublimation_status": row[16],
                "state": row[17],
                "scope_type": row[18],
                "planned_event_scope_text": row[19],
                "planned_event_ranges": parse_json_array_text(row[20]),
                "excluded_event_scope_text": row[21],
                "excluded_event_ranges": parse_json_array_text(row[22]),
                "exit_mode": row[23],
                "retired_after_event_id": row[24],
                "return_required": bool(row[25]),
                "return_reason": row[26],
                "story_function": row[27],
            }
            for row in char_rows
        ]
        opening_stage = next((item for item in blueprint_json.get("stage_plan", []) if item.get("phase") == "opening_breakthrough"), {})
        stage_start = int(opening_stage.get("start_event_id", 1) or 1)
        stage_end = int(opening_stage.get("end_event_id", initial_event_count) or initial_event_count)
        stage_chars_json = [
            item for item in core_chars_json
            if item.get("scope_type") == "full" or event_in_ranges(stage_start, normalize_event_ranges(item.get("planned_event_ranges"), plan["target_event_count"])) or event_in_ranges(stage_end, normalize_event_ranges(item.get("planned_event_ranges"), plan["target_event_count"]))
        ] or core_chars_json
        prompt2_rule = foreshadow_generation_rule(get_foreshadow_active_count(novel_id), "initial")
        story_plan_note = build_story_plan_note(novel_id, 1, initial_event_count)
        opening_blueprint_note = build_blueprint_guidance_from_data(blueprint_json, 1, initial_event_count)
        world_items = fetch_world_items(novel_id)
        opening_event_requirements = build_opening_event_requirements()
        prompt2_system_prompt, prompt2_user_template = render_prompt_messages(
            prompt_set["prompt7_opening_world_planning"],
            {"opening_event_requirements": opening_event_requirements},
        )
        prompt2_full = (
            f"【一句话梗概】\n{synopsis}\n\n"
            f"【世界观摘要】\n{worldview_summary}\n\n"
            f"【世界快照】\n{opening_snapshot}\n\n"
            f"【世界级设定库（lorebook）】\n{json.dumps(world_items, ensure_ascii=False)}\n\n"
            f"【阶段计划】\n{json.dumps(blueprint_json, ensure_ascii=False)}\n\n"
            f"【主角成长规划】\n{json.dumps(growth_json, ensure_ascii=False)}\n\n"
            f"【当前阶段相关人物卡】\n{json.dumps(stage_chars_json, ensure_ascii=False)}\n\n"
            f"{story_plan_note}\n"
            f"{opening_blueprint_note}\n"
            f"【本次生成任务】\n只生成开篇破局期事件，共 {initial_event_count} 个，事件号从 1 到 {initial_event_count}。"
            "必须做好黄金开篇，建立日常基准，引入核心金手指或变故，确立第一个短期生存目标。"
            "必须体现欲扬先抑：先展示主角困境，再完成第一次降维打击、反杀或强势破局。\n\n"
            f"{prompt2_rule}\n\n{prompt2_user_template}"
        )
        events_reply = client.chat(prompt2_full, system_prompt=prompt2_system_prompt, meta={"step": "init", "prompt": "prompt7_opening_world_planning", "novel_id": novel_id})
        events_json = parse_json_with_fix(client, events_reply, "array", meta={"prompt": "prompt7_opening_world_planning", "novel_id": novel_id})
        save_events(events_json, novel_id)
        apply_character_exit_plan(events_json, novel_id)
        save_initial_foreshadows(events_json, novel_id)
        sync_novel_phase(novel_id)
        set_init_step_state(novel_id, "opening_world_planning", "latest")
        return {"status": "ok", "step": step_name, "events_saved": len(events_json)}

    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT event_id, description, outline_description, goal, obstacle, cool_point_type, payoff_type, growth_reward, status_reward, cliffhanger, linked_characters FROM events WHERE novel_id=? ORDER BY event_id ASC", (novel_id,))
    event_rows = cur.fetchall()
    conn.close()
    if not event_rows:
        raise HTTPException(status_code=400, detail="请先生成开篇事件")
    events_json = [
        {
            "event_id": row[0],
            "description": row[1],
            "outline_description": row[2],
            "goal": row[3],
            "obstacle": row[4],
            "cool_point_type": row[5],
            "payoff_type": row[6],
            "growth_reward": row[7],
            "status_reward": row[8],
            "cliffhanger": row[9],
            "linked_characters": parse_json_array_text(row[10]),
        }
        for row in event_rows
    ]

    raise HTTPException(status_code=404, detail="unknown step")


@router.post("/api/outline")
def api_outline(req: OutlineRequest) -> Dict[str, Any]:
    job_id = create_job("outline", req.novel_id)

    def run() -> None:
        try:
            append_job_log(job_id, "开始生成世界设定、阶段计划与人物卡")
            client = OpenAIClient(req.api)
            prompt_set = {
                "prompt1_world_setting": req.prompt1_world_setting.model_dump(),
                "prompt2_series_blueprint": req.prompt2_series_blueprint.model_dump(),
                "prompt3_growth_system": req.prompt3_growth_system.model_dump(),
                "prompt4_core_characters": req.prompt4_core_characters.model_dump(),
                "prompt5_worldview_summary": req.prompt5_worldview_summary.model_dump(),
                "prompt6_opening_snapshot": req.prompt6_opening_snapshot.model_dump(),
                "prompt7_opening_world_planning": req.prompt7_opening_world_planning.model_dump(),
                "prompt_internal_supplement_characters": req.prompt_internal_supplement_characters.model_dump(),
            }
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute(
                "UPDATE novels SET current_phase='outlining', updated_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), req.novel_id),
            )
            conn.commit()
            cur.execute("SELECT COUNT(*) FROM events WHERE novel_id=? AND is_user_edited=1", (req.novel_id,))
            user_edited_events = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM characters WHERE novel_id=? AND is_user_edited=1", (req.novel_id,))
            user_edited_chars = cur.fetchone()[0]
            conn.close()
            if user_edited_events or user_edited_chars:
                raise ValueError("当前小说存在人工修改的人物或事件，请先清理或新增保留人工修改的重生成功能")
            clear_novel(req.novel_id)
            plan = get_story_plan(req.novel_id)
            initial_event_count = plan["opening_breakthrough_count"]
            append_job_log(job_id, "已清空旧数据")

            p1_system_prompt, p1_user_prompt = render_prompt_messages(prompt_set["prompt1_world_setting"], {"setting": req.setting})
            append_job_log(job_id, "发送提示词1：故事设定")
            if is_job_cancelled(job_id):
                finalize_job(job_id, error="cancelled")
                return
            wv_text = client.chat(p1_user_prompt, system_prompt=p1_system_prompt, meta={"step": "outline", "prompt": "prompt1_world_setting", "novel_id": req.novel_id})
            save_init_material(req.novel_id, "seed_world_setting", wv_text)
            set_job_progress(job_id, 18)

            append_job_log(job_id, "发送提示词2：阶段计划")
            story_plan_note = build_story_plan_note(req.novel_id, 1, plan["target_event_count"])
            batch_slots_text = build_batch_slots_text(plan)
            blueprint_system_prompt, blueprint_prompt = render_prompt_messages(
                prompt_set["prompt2_series_blueprint"],
                {"setting": req.setting, "world_setting": wv_text, "system_plan": story_plan_note},
            )
            if is_job_cancelled(job_id):
                finalize_job(job_id, error="cancelled")
                return
            blueprint_reply = client.chat(
                blueprint_prompt,
                system_prompt=blueprint_system_prompt,
                meta={"step": "outline", "prompt": "prompt2_series_blueprint", "novel_id": req.novel_id},
            )
            blueprint_raw = parse_json_with_fix(
                client,
                blueprint_reply,
                "object",
                meta={"prompt": "prompt2_series_blueprint", "novel_id": req.novel_id},
            )
            blueprint_json = normalize_series_blueprint(blueprint_raw, plan)
            save_series_blueprint(blueprint_json, req.novel_id)
            append_job_log(job_id, "阶段计划保存成功")
            set_job_progress(job_id, 36)

            append_job_log(job_id, "发送提示词3：主角成长规划")
            growth_system_prompt, growth_prompt = render_prompt_messages(
                prompt_set["prompt3_growth_system"],
                {
                    "setting": req.setting,
                    "world_setting": wv_text,
                    "stage_plan": json.dumps(blueprint_json.get("stage_plan", []), ensure_ascii=False),
                    "system_plan": json.dumps(blueprint_json.get("system_plan", {}), ensure_ascii=False),
                },
            )
            res_growth = client.chat(
                growth_prompt,
                system_prompt=growth_system_prompt,
                meta={"step": "outline", "prompt": "prompt3_growth_system", "novel_id": req.novel_id},
            )
            growth_json = parse_json_with_fix(
                client,
                res_growth,
                "object",
                meta={"prompt": "prompt3_growth_system", "novel_id": req.novel_id},
            )
            blueprint_json = merge_growth_plan_into_blueprint(blueprint_json, growth_json, plan)
            save_series_blueprint(blueprint_json, req.novel_id)
            append_job_log(job_id, "主角成长规划保存成功")
            set_job_progress(job_id, 52)
            growth_plan_json = extract_growth_plan_from_blueprint(blueprint_json)

            append_job_log(job_id, "发送提示词4：核心人物卡")
            core_stage_summary = build_core_character_stage_summary(blueprint_json, growth_plan_json)
            system_plan_note = build_story_plan_note(req.novel_id, 1, plan["target_event_count"])
            prompt3_core_system_prompt, prompt3_core_user_template = render_prompt_messages(
                prompt_set["prompt4_core_characters"],
                {"system_plan": system_plan_note},
            )
            prompt3_core_full = (
                f"【世界观设定】\n{wv_text}\n\n"
                f"【阶段计划摘要】\n{core_stage_summary}\n\n"
                "【当前事件大纲】\n当前尚未生成开篇事件，请只生成开篇必需角色与会长期影响主线的核心角色。\n\n"
                f"{prompt3_core_user_template}"
            )
            res3_core = client.chat(prompt3_core_full, system_prompt=prompt3_core_system_prompt, meta={"step": "outline", "prompt": "prompt4_core_characters", "novel_id": req.novel_id})
            core_chars_json = parse_json_with_fix(client, res3_core, "array", meta={"prompt": "prompt4_core_characters", "novel_id": req.novel_id})
            saved_core_chars = save_characters(core_chars_json, req.novel_id, blueprint_json, init_step="core_characters")
            append_job_log(job_id, f"核心人物卡保存成功：{saved_core_chars}")
            set_job_progress(job_id, 60)

            append_job_log(job_id, "发送提示词5：世界观摘要")
            prompt5_system_prompt, prompt5_user_template = render_prompt_messages(prompt_set["prompt5_worldview_summary"], {})
            prompt5_full = (
                f"【世界设定】\n{wv_text}\n\n"
                f"【一句话梗概】\n{req.setting}\n\n"
                f"【阶段计划】\n{json.dumps(blueprint_json, ensure_ascii=False)}\n\n"
                f"【主角成长规划】\n{json.dumps(growth_plan_json, ensure_ascii=False)}\n\n"
                f"【核心人物卡】\n{json.dumps(core_chars_json, ensure_ascii=False)}\n\n"
                f"{prompt5_user_template}"
            )
            worldview_summary_reply = client.chat(prompt5_full, system_prompt=prompt5_system_prompt, meta={"step": "outline", "prompt": "prompt5_worldview_summary", "novel_id": req.novel_id})
            worldview_summary_json = parse_json_with_fix(client, worldview_summary_reply, "object", meta={"prompt": "prompt5_worldview_summary", "novel_id": req.novel_id})
            worldview_summary = worldview_summary_json.get("worldview_summary", "")
            save_init_material(req.novel_id, "worldview_summary", worldview_summary)
            set_job_progress(job_id, 68)

            append_job_log(job_id, "发送提示词6：世界快照")
            prompt6_system_prompt, prompt6_user_template = render_prompt_messages(prompt_set["prompt6_opening_snapshot"], {})
            prompt6_full = (
                f"【世界设定】\n{wv_text}\n\n"
                f"【一句话梗概】\n{req.setting}\n\n"
                f"【阶段计划】\n{json.dumps(blueprint_json, ensure_ascii=False)}\n\n"
                f"【主角成长规划】\n{json.dumps(growth_plan_json, ensure_ascii=False)}\n\n"
                f"【核心人物卡】\n{json.dumps(core_chars_json, ensure_ascii=False)}\n\n"
                f"【世界观摘要】\n{worldview_summary}\n\n"
                f"{prompt6_user_template}"
            )
            opening_snapshot_reply = client.chat(prompt6_full, system_prompt=prompt6_system_prompt, meta={"step": "outline", "prompt": "prompt6_opening_snapshot", "novel_id": req.novel_id})
            opening_snapshot_json = parse_json_with_fix(client, opening_snapshot_reply, "object", meta={"prompt": "prompt6_opening_snapshot", "novel_id": req.novel_id})
            opening_snapshot, lorebook_items = extract_opening_snapshot_payload(opening_snapshot_json)
            if not opening_snapshot:
                raise ValueError("世界快照生成成功但返回字段缺失，需返回 opening_snapshot")
            save_init_material(req.novel_id, "world_snapshot_current", opening_snapshot)
            if lorebook_items:
                for item in lorebook_items:
                    if isinstance(item, dict):
                        item.setdefault("source_event_id", None)
                        item.setdefault("last_update", "世界快照初始化")
                        item.setdefault("source", "world_snapshot")
                upsert_lorebook_items(lorebook_items, req.novel_id)
            set_job_progress(job_id, 74)

            append_job_log(job_id, "发送提示词7：事件规划")
            prompt2_rule = foreshadow_generation_rule(get_foreshadow_active_count(req.novel_id), "initial")
            opening_blueprint_note = build_blueprint_guidance_from_data(blueprint_json, 1, initial_event_count)
            opening_stage = next((item for item in blueprint_json.get("stage_plan", []) if item.get("phase") == "opening_breakthrough"), {})
            stage_start = int(opening_stage.get("start_event_id", 1) or 1)
            stage_end = int(opening_stage.get("end_event_id", initial_event_count) or initial_event_count)
            stage_chars_json = [
                item for item in core_chars_json
                if item.get("scope_type") == "full" or event_in_ranges(stage_start, normalize_event_ranges(item.get("planned_event_ranges"), plan["target_event_count"])) or event_in_ranges(stage_end, normalize_event_ranges(item.get("planned_event_ranges"), plan["target_event_count"]))
            ] or core_chars_json
            world_items = fetch_world_items(req.novel_id)
            opening_event_requirements = build_opening_event_requirements()
            prompt2_system_prompt, prompt2_user_template = render_prompt_messages(
                prompt_set["prompt7_opening_world_planning"],
                {"opening_event_requirements": opening_event_requirements},
            )
            prompt2_full = (
                f"【一句话梗概】\n{req.setting}\n\n"
                f"【世界观摘要】\n{worldview_summary}\n\n"
                f"【世界快照】\n{opening_snapshot}\n\n"
                f"【世界级设定库（lorebook）】\n{json.dumps(world_items, ensure_ascii=False)}\n\n"
                f"【阶段计划】\n{json.dumps(blueprint_json, ensure_ascii=False)}\n\n"
                f"【主角成长规划】\n{json.dumps(growth_plan_json, ensure_ascii=False)}\n\n"
                f"【当前阶段相关人物卡】\n{json.dumps(stage_chars_json, ensure_ascii=False)}\n\n"
                f"{story_plan_note}\n"
                f"{opening_blueprint_note}\n"
                f"【本次生成任务】\n只生成开篇破局期事件，共 {initial_event_count} 个，事件号从 1 到 {initial_event_count}。"
                "必须做好黄金开篇，建立日常基准，引入核心金手指或变故，确立第一个短期生存目标。"
                "必须体现欲扬先抑：先展示主角困境，再完成第一次降维打击、反杀或强势破局。\n\n"
                f"{prompt2_rule}\n\n{prompt2_user_template}"
            )
            if is_job_cancelled(job_id):
                finalize_job(job_id, error="cancelled")
                return
            res2 = client.chat(prompt2_full, system_prompt=prompt2_system_prompt, meta={"step": "outline", "prompt": "prompt7_opening_world_planning", "novel_id": req.novel_id})
            events_json = parse_json_with_fix(client, res2, "array", meta={"prompt": "prompt7_opening_world_planning", "novel_id": req.novel_id})
            saved_events = save_events(events_json, req.novel_id)
            saved_foreshadows = save_initial_foreshadows(events_json, req.novel_id)
            append_job_log(job_id, f"事件保存成功：{saved_events}")
            append_job_log(job_id, f"初始伏笔提取成功：{saved_foreshadows}")
            set_job_progress(job_id, 84)

            append_job_log(job_id, "检测并补充事件新增人物")
            core_names = {item.get("name") for item in core_chars_json if isinstance(item, dict)}
            missing_names = sorted({name for ev in events_json for name in ev.get("linked_characters", []) if name and name not in core_names})
            system_plan_note = build_story_plan_note(req.novel_id, stage_start, stage_end)
            prompt3_sup_system_prompt, prompt3_sup_user_template = render_prompt_messages(
                prompt_set["prompt_internal_supplement_characters"],
                {"system_plan": system_plan_note},
            )
            prompt3_sup_full = (
                f"【世界观摘要】\n{worldview_summary}\n\n"
                f"【世界快照】\n{opening_snapshot}\n\n"
                f"【阶段计划】\n{json.dumps(blueprint_json, ensure_ascii=False)}\n\n"
                f"【主角成长规划】\n{json.dumps(growth_plan_json, ensure_ascii=False)}\n\n"
                f"【当前事件列表】\n{json.dumps(events_json, ensure_ascii=False)}\n\n"
                f"【仅补充以下缺失角色】\n{json.dumps(missing_names, ensure_ascii=False)}\n\n"
                f"{prompt3_sup_user_template}"
            )
            if is_job_cancelled(job_id):
                finalize_job(job_id, error="cancelled")
                return
            supplement_chars_json = []
            saved_chars = 0
            if missing_names:
                res3 = client.chat(prompt3_sup_full, system_prompt=prompt3_sup_system_prompt, meta={"step": "outline", "prompt": "prompt_internal_supplement_characters", "novel_id": req.novel_id})
                supplement_chars_json = parse_json_with_fix(client, res3, "array", meta={"prompt": "prompt_internal_supplement_characters", "novel_id": req.novel_id})
                saved_chars = save_characters(supplement_chars_json, req.novel_id, blueprint_json, init_step="supplement_characters")
            chars_json = core_chars_json + supplement_chars_json
            append_job_log(job_id, f"补充人物卡保存成功：{saved_chars}")
            exit_updates = apply_character_exit_plan(events_json, req.novel_id)
            if exit_updates:
                append_job_log(job_id, f"事件规划下线人物同步：{exit_updates} 人")
            set_job_progress(job_id, 92)

            save_worldview({"world_state": format_world_snapshot_text(opening_snapshot or worldview_summary or wv_text)}, req.novel_id)
            append_job_log(job_id, "已用世界快照初始化当前世界状态")
            set_job_progress(job_id, 100)

            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute(
                "UPDATE novels SET current_phase=?, updated_at=? WHERE id=?",
                (sync_novel_phase(req.novel_id), datetime.utcnow().isoformat(), req.novel_id),
            )
            conn.commit()
            conn.close()

            finalize_job(
                job_id,
                result={"events_saved": saved_events, "characters_saved": saved_chars, "foreshadows_saved": saved_foreshadows, "series_blueprint_saved": True},
            )
        except Exception as e:
            conn = get_db_conn()
            cur = conn.cursor()
            cur.execute(
                "UPDATE novels SET current_phase=CASE WHEN current_phase='outlining' THEN 'draft' ELSE current_phase END, updated_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), req.novel_id),
            )
            conn.commit()
            conn.close()
            finalize_job(job_id, error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return {"status": "accepted", "job_id": job_id}


def fetch_worldview(novel_id: str) -> str:
    snapshot_text = load_init_material(novel_id, "world_snapshot_current")
    if snapshot_text:
        return format_world_snapshot_text(snapshot_text)
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT content FROM worldview WHERE novel_id=? LIMIT 1", (novel_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else "未知世界观"


def fetch_lorebook(
    novel_id: str,
    character_names: Optional[List[str]] = None,
    location: str = "",
    foreshadow: str = "",
    description: str = "",
    conflict: str = "",
) -> str:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT name, type, description, location, related_characters, source_event_id, last_update, is_locked FROM lorebook WHERE novel_id=?",
        (novel_id,),
    )
    rows = cur.fetchall()
    conn.close()

    character_names = character_names or []
    text_blob = " ".join([location or "", foreshadow or "", description or "", conflict or ""])
    scored_rows: List[tuple] = []

    for name, l_type, desc, loc, related_chars, source_event_id, last_update, is_locked in rows:
        try:
            related_list = json.loads(related_chars) if related_chars else []
        except Exception:
            related_list = []

        score = 0
        if any(name_item in related_list for name_item in character_names):
            score += 5
        if location and loc and (location in loc or loc in location):
            score += 4
        if foreshadow and foreshadow != "无" and name and name in foreshadow:
            score += 3
        if text_blob and name and name in text_blob:
            score += 2
        if last_update:
            score += 1
        if is_locked:
            score += 2

        scored_rows.append((score, source_event_id or 0, last_update or "", name, l_type, desc, loc, related_list))

    scored_rows.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    chosen_rows = [item for item in scored_rows if item[0] > 0][:6]
    if not chosen_rows:
        chosen_rows = scored_rows[:4]

    lore_items = []
    for score, source_event_id, last_update, name, l_type, desc, loc, related_list in chosen_rows:
        rel_str = "、".join(related_list) if related_list else "无"
        lore_items.append(
            f"- {name}（{l_type}）: {truncate_text(desc, 120)} | 位置/归属: {truncate_text(loc, 24)} | 相关人物: {truncate_text(rel_str, 24)} | 来源事件: {source_event_id} | 最近更新: {truncate_text(last_update, 18)}"
        )
    return "\n".join(lore_items) if lore_items else "（暂无）"


def fetch_events(novel_id: str, limit_count: int) -> List[tuple]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, event_id, outline_description, ending_phase, location, time_duration, core_conflict, foreshadowing, linked_characters, event_world_snapshot_update, event_foreshadow_updates, event_growth_updates, event_lorebook_updates, entering_characters, exiting_characters, goal, obstacle, cool_point_type, payoff_type, growth_reward, status_reward, cliffhanger FROM events WHERE novel_id=? AND is_written=0 AND is_locked=0 ORDER BY event_id ASC LIMIT ?",
        (novel_id, limit_count),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def fetch_all_events(novel_id: str) -> List[tuple]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT event_id, COALESCE(actual_summary, outline_description, description), is_written, ending_phase FROM events WHERE novel_id=? ORDER BY event_id ASC",
        (novel_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def load_context_cache(novel_id: str, cache_key: str) -> Optional[Dict[str, str]]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT content, source_hash, updated_at FROM context_cache WHERE cache_key=? LIMIT 1", (cache_key,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"content": row[0], "source_hash": row[1], "updated_at": row[2]}


def save_context_cache(novel_id: str, cache_key: str, content: str, source_hash: str) -> None:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO context_cache (cache_key, content, source_hash, updated_at) VALUES (?, ?, ?, ?)",
        (cache_key, content, source_hash, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def build_completed_events_summary(client: OpenAIClient, novel_id: str, completed_events: List[Dict[str, Any]]) -> str:
    if len(completed_events) <= 10:
        return ""
    older_events = completed_events[:-3]
    if not older_events:
        return ""
    source_payload = json.dumps(older_events, ensure_ascii=False, sort_keys=True)
    source_hash = hashlib.sha1(source_payload.encode("utf-8")).hexdigest()
    cached = load_context_cache(novel_id, "completed_events_summary")
    if cached and cached.get("source_hash") == source_hash and cached.get("content"):
        return cached["content"]

    raw_lines = [f"事件 {item['event_id']}: {item['summary']}" for item in older_events]
    prompt = (
        "请把以下已经完成的剧情事件压缩成一段前情摘要。\n"
        "要求：\n"
        "1. 控制在 400-800 字。\n"
        "2. 只保留主线推进、关键人物状态变化、敌我格局变化、尚未解决的核心矛盾、仍然有效的长期悬念。\n"
        "3. 不要新增事实，不要使用空话套话，不要写散文化修辞。\n"
        "4. 直接输出摘要正文，不要 JSON。\n\n"
        "【已完成事件列表】\n"
        + "\n".join(raw_lines)
    )
    summary = client.chat(prompt, meta={"step": "compress", "prompt": "completed_events_summary", "novel_id": novel_id}).strip()
    save_context_cache(novel_id, "completed_events_summary", summary, source_hash)
    return summary


def build_full_outline_context(client: OpenAIClient, novel_id: str, current_event_id: int, open_foreshadows: str = "（暂无）") -> str:
    rows = fetch_all_events(novel_id)
    completed = [
        {"event_id": row[0], "summary": row[1], "ending_phase": row[3]}
        for row in rows
        if row[2]
    ]
    current = next((row for row in rows if row[0] == current_event_id), None)
    future = [row for row in rows if row[0] > current_event_id][:3]

    sections: List[str] = []
    completed_summary = build_completed_events_summary(client, novel_id, completed)
    if completed_summary:
        sections.append(f"【已完成事件摘要】\n{completed_summary}")

    visible_completed = completed if len(completed) <= 10 else completed[-3:]
    if visible_completed:
        lines = []
        for item in visible_completed:
            phase_note = f" [结局阶段:{item['ending_phase']}]" if item.get("ending_phase") and item.get("ending_phase") != "normal" else ""
            lines.append(f"事件 {item['event_id']}{phase_note}: {item['summary']}")
        sections.append("【最近已完成事件】\n" + "\n".join(lines))

    if current:
        phase_note = f" [结局阶段:{current[3]}]" if current[3] and current[3] != "normal" else ""
        sections.append(f"【当前事件】\n事件 {current[0]}{phase_note}: {current[1]}")

    if open_foreshadows and open_foreshadows != "（暂无）":
        sections.append(f"【开放伏笔（优先处理）】\n{open_foreshadows}")

    if future:
        future_lines = []
        for event_id, summary, _, ending_phase in future:
            phase_note = f" [结局阶段:{ending_phase}]" if ending_phase and ending_phase != "normal" else ""
            future_lines.append(f"事件 {event_id}{phase_note}: {summary}")
        sections.append("【未来3个事件预告】\n" + "\n".join(future_lines))

    return "\n\n".join(sections).strip()


def build_opening_event_requirements() -> str:
    return (
        "【开篇事件特别要求（仅初始化时生效）】\n"
        "事件1：必须抛出悬念或困境，自然引入金手指卖点并交代前因；必须出现一个小高潮（爽点），留下钩子，并展现主角的性格特点。\n"
        "事件2：必须承接事件1的钩子，主角开始行动；引入新的转机或变数，凸显核心金手指的能力，并留下新的钩子。\n"
        "事件3：必须让读者清晰看到未来蓝图；既要展现时代背景，又要避免枯燥，可通过主角与时代的错位感制造趣味。"
    )


def build_future_completed_events_context(novel_id: str, current_event_id: int, limit: int = 3) -> str:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT event_id, COALESCE(actual_summary, outline_description, description) FROM events WHERE novel_id=? AND event_id>? AND is_written=1 ORDER BY event_id ASC LIMIT ?",
        (novel_id, int(current_event_id), int(limit)),
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return ""
    return "\n".join([f"事件 {row[0]}: {row[1]}" for row in rows if row and row[1]])


def format_rewrite_constraints_text(
    event_id: int,
    output_checkpoint_payload: Dict[str, Any],
    future_context: str = "",
) -> str:
    lines = [
        "【重写约束】",
        f"本次任务是重写已完成的事件 {event_id} 正文。",
        "只能重写表达和细节，不得改动既定回填结果，不得与后续已完成事件冲突。",
    ]
    chapter_summary = str(output_checkpoint_payload.get("chapter_summary") or "").strip()
    if chapter_summary:
        lines.extend(["【必须保持的事件结果】", chapter_summary])
    sub_outline = str(output_checkpoint_payload.get("sub_outline") or "").strip()
    if sub_outline:
        lines.extend(["【原始通过版分段大纲】", sub_outline])
    output_json = output_checkpoint_payload.get("json_data") or {}
    if isinstance(output_json, dict) and output_json.get("character_state_updates"):
        lines.append("【必须保持的人物状态变化】")
        for item in output_json.get("character_state_updates", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            new_state = str(item.get("new_state", "")).strip()
            sublimation_status = str(item.get("sublimation_status", "")).strip()
            detail = new_state or sublimation_status
            if detail:
                lines.append(f"- {name}: {detail}")
    event_deltas = output_checkpoint_payload.get("event_deltas") or {}
    if isinstance(event_deltas, dict):
        for label, key in [
            ("世界快照更新", "world_snapshot_update"),
            ("伏笔更新", "foreshadow_updates"),
            ("成长更新", "growth_updates"),
            ("设定库更新", "lorebook_updates"),
        ]:
            value = event_deltas.get(key)
            if value:
                lines.extend([f"【必须保持的{label}】", json.dumps(value, ensure_ascii=False, indent=2)])
    if future_context:
        lines.extend(["【后续已完成事件（重写时必须兼容）】", future_context])
    return "\n".join(lines).strip()


def chat_with_event_artifact(
    client: OpenAIClient,
    novel_id: str,
    event_id: int,
    stage: str,
    user_prompt: str,
    *,
    system_prompt: str = "",
    meta: Optional[Dict[str, Any]] = None,
    part_name: str = "",
) -> str:
    try:
        response = client.chat(user_prompt, system_prompt=system_prompt, meta=meta)
        save_event_generation_artifact(
            novel_id,
            event_id,
            stage,
            part_name=part_name,
            meta=meta,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=response,
        )
        return response
    except Exception as exc:
        save_event_generation_artifact(
            novel_id,
            event_id,
            stage,
            part_name=part_name,
            meta=meta,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            error_text=str(exc),
        )
        raise


def parse_part_final_output(part_final: str, is_last_part: bool) -> Dict[str, Any]:
    part_text = part_final
    part_json = None
    backticks = "```"
    pattern = rf"{backticks}(?:json)?\s*([\{{\[].*?[\}}\]])\s*{backticks}"
    json_match = re.search(pattern, part_final, re.DOTALL | re.IGNORECASE)
    if json_match:
        part_text = part_final[: json_match.start()].strip()
        try:
            part_json = json.loads(json_match.group(1))
        except Exception:
            part_json = None
    else:
        last_brace_start = part_final.rfind("{")
        if last_brace_start != -1 and '"part_summary"' in part_final[last_brace_start:]:
            part_text = part_final[:last_brace_start].strip()
            try:
                part_json = json.loads(part_final[last_brace_start:])
            except Exception:
                part_json = None
    chapter_summary = ""
    char_updates: List[Dict[str, Any]] = []
    if isinstance(part_json, dict):
        raw_updates = part_json.get("character_state_updates")
        if isinstance(raw_updates, list):
            char_updates = raw_updates
        if is_last_part:
            chapter_summary = str(part_json.get("part_summary", "") or "")
    return {
        "part_text": part_text,
        "part_json": part_json if isinstance(part_json, dict) else None,
        "chapter_summary": chapter_summary,
        "character_state_updates": char_updates,
    }


def generate_event_text_bundle(
    client: OpenAIClient,
    prompt_set: Dict[str, Dict[str, str]],
    novel_id: str,
    event_id: int,
    novel_style: str,
    context: Dict[str, Any],
    *,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    def job_log(message: str) -> None:
        if job_id:
            append_job_log(job_id, message)

    def job_step(message: str) -> None:
        if job_id:
            set_job_step(job_id, message)

    base_progress = int(context.get("base_progress", 0) or 0)
    rewrite_constraints_text = str(context.get("rewrite_constraints_text") or "").strip()
    series_note_value = str(context.get("series_note") or "")
    if rewrite_constraints_text:
        series_note_value = f"{series_note_value}\n\n{rewrite_constraints_text}".strip()

    prompt_sub_outline_system, prompt_sub_outline_user = render_prompt_messages(
        prompt_set["prompt10_sub_outline"],
        {
            "setting": context.get("novel_synopsis", ""),
            "growth_system": context.get("growth_system_str", ""),
            "series_note": series_note_value,
            "full_outline_str": context.get("full_outline_str", ""),
            "current_wv": context.get("current_wv", ""),
            "lorebook_str": context.get("lorebook_str", ""),
            "event_world_snapshot_update": context.get("event_world_snapshot_update_input", "{}"),
            "event_foreshadow_updates": context.get("event_foreshadow_updates_input", "[]"),
            "event_growth_updates": context.get("event_growth_updates_input", "{}"),
            "event_lorebook_updates": context.get("event_lorebook_updates_input", "{}"),
            "char_details_str": context.get("char_details_str", ""),
            "ev_id": str(event_id),
            "location": context.get("location", ""),
            "time_duration": context.get("time_duration", ""),
            "conflict": context.get("conflict", ""),
            "desc": context.get("desc", ""),
            "foreshadow": context.get("foreshadow", ""),
            "goal": context.get("goal", ""),
            "obstacle": context.get("obstacle", ""),
            "cool_point_type": context.get("cool_point_type", ""),
            "payoff_type": context.get("payoff_type", ""),
            "growth_reward": context.get("growth_reward", ""),
            "status_reward": context.get("status_reward", ""),
            "cliffhanger": context.get("cliffhanger", ""),
            "ending_note": context.get("ending_note", ""),
        },
    )

    job_step(f"正在生成事件{event_id}分段大纲")
    job_log(f"事件 {event_id}：生成分段大纲")
    sub_outline = chat_with_event_artifact(
        client,
        novel_id,
        event_id,
        "sub_outline",
        prompt_sub_outline_user,
        system_prompt=prompt_sub_outline_system,
        meta={"step": "sub_outline", "prompt": "prompt10_sub_outline", "novel_id": novel_id, "event_id": event_id, "rewrite": bool(rewrite_constraints_text)},
    )
    event_short_title = extract_event_short_title(sub_outline, context.get("desc", ""))
    job_log(f"事件 {event_id} 缩写：{event_short_title}")
    if job_id:
        set_job_progress(job_id, base_progress + 10)

    parts = extract_part_names(sub_outline, int(event_id))
    full_event_content = ""
    chapter_summary = ""
    char_update_buffer: List[Dict[str, Any]] = []
    part_records: List[Dict[str, Any]] = []
    total_parts = len(parts)

    for idx_part, part_name in enumerate(parts, start=1):
        job_step(f"事件{event_id}-{part_name} 规划")
        job_log(f"事件 {event_id}：{part_name} 分段大纲+关键镜头")
        part_plan = extract_part_plan(sub_outline, part_name)
        if not part_plan:
            prompt_part_plan_system, prompt_part_plan_user = render_prompt_messages(
                prompt_set.get("prompt11_part_plan", "") or "",
                {
                    "part_name": part_name,
                    "series_note": series_note_value,
                    "full_outline_str": context.get("full_outline_str", ""),
                    "current_wv": context.get("current_wv", ""),
                    "lorebook_str": context.get("lorebook_str", ""),
                    "character_state_block": context.get("char_details_str", ""),
                    "growth_system": context.get("growth_system_str", ""),
                    "goal": context.get("goal", ""),
                    "obstacle": context.get("obstacle", ""),
                    "cool_point_type": context.get("cool_point_type", ""),
                    "payoff_type": context.get("payoff_type", ""),
                    "growth_reward": context.get("growth_reward", ""),
                    "status_reward": context.get("status_reward", ""),
                    "cliffhanger": context.get("cliffhanger", ""),
                    "desc": context.get("desc", ""),
                    "foreshadow": context.get("foreshadow", ""),
                },
            )
            part_plan = chat_with_event_artifact(
                client,
                novel_id,
                event_id,
                "part_plan",
                prompt_part_plan_user,
                system_prompt=prompt_part_plan_system,
                meta={"step": "part_plan", "prompt": "prompt11_part_plan", "novel_id": novel_id, "event_id": event_id, "part": part_name, "rewrite": bool(rewrite_constraints_text)},
                part_name=part_name,
            )
        if job_id:
            set_job_progress(job_id, base_progress + 10 + idx_part * 10)

        part_write_plan = part_plan.strip()
        if rewrite_constraints_text:
            part_write_plan = f"{part_write_plan}\n\n{rewrite_constraints_text}".strip()
        job_step(f"事件{event_id}-{part_name} 正文")
        job_log(f"事件 {event_id}：{part_name} 正文")
        prompt_part_write_system, prompt_part_write_user = render_prompt_messages(
            prompt_set["prompt12_part_write"],
            {
                "part_name": part_name,
                "character_state_block": context.get("char_details_str", ""),
                "growth_system": context.get("growth_system_str", ""),
                "plan": part_write_plan,
                "novel_style": novel_style,
                "ev_id": str(event_id),
            },
        )
        part_draft = chat_with_event_artifact(
            client,
            novel_id,
            event_id,
            "part_write",
            prompt_part_write_user,
            system_prompt=prompt_part_write_system,
            meta={"step": "part_write", "prompt": "prompt12_part_write", "novel_id": novel_id, "event_id": event_id, "part": part_name, "rewrite": bool(rewrite_constraints_text)},
            part_name=part_name,
        )

        reflect_character_block = context.get("char_details_str", "")
        if rewrite_constraints_text:
            reflect_character_block = f"{reflect_character_block}\n\n{rewrite_constraints_text}".strip()
        job_step(f"事件{event_id}-{part_name} 反思优化")
        job_log(f"事件 {event_id}：{part_name} 反思优化")
        prompt_part_reflect_system, prompt_part_reflect_user = render_prompt_messages(
            prompt_set["prompt13_part_reflect"],
            {
                "draft": part_draft,
                "novel_style": novel_style,
                "ev_id": str(event_id),
                "character_state_block": reflect_character_block,
            },
        )
        part_final = chat_with_event_artifact(
            client,
            novel_id,
            event_id,
            "part_reflect",
            prompt_part_reflect_user,
            system_prompt=prompt_part_reflect_system,
            meta={"step": "part_reflect", "prompt": "prompt13_part_reflect", "novel_id": novel_id, "event_id": event_id, "part": part_name, "rewrite": bool(rewrite_constraints_text)},
            part_name=part_name,
        )
        if job_id:
            set_job_progress(job_id, base_progress + 40 + idx_part * 15)

        parsed = parse_part_final_output(part_final, idx_part == total_parts)
        if parsed["character_state_updates"]:
            char_update_buffer.extend(parsed["character_state_updates"])
        if idx_part == total_parts:
            chapter_summary = parsed["chapter_summary"] or "摘要提取失败。"
        full_event_content += parsed["part_text"] + "\n\n"
        part_records.append(
            {
                "part_name": part_name,
                "part_plan": part_plan,
                "part_summary": parsed["chapter_summary"] if idx_part == total_parts else "",
                "character_state_updates": parsed["character_state_updates"],
            }
        )

    def normalize_char_updates(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            new_state = item.get("new_state")
            sublimation_status = item.get("sublimation_status")
            if not name or (not new_state and not sublimation_status):
                continue
            entry = {"name": str(name)}
            if new_state:
                entry["new_state"] = str(new_state)
            if sublimation_status:
                entry["sublimation_status"] = str(sublimation_status)
            normalized.append(entry)
        return normalized

    json_data = {
        "event_summary_update": chapter_summary or "摘要提取失败。",
        "character_state_updates": normalize_char_updates(char_update_buffer),
    }
    return {
        "event_short_title": event_short_title,
        "sub_outline": sub_outline,
        "parts": part_records,
        "full_event_content": full_event_content.strip(),
        "chapter_summary": chapter_summary or "摘要提取失败。",
        "json_data": json_data,
    }


def split_text_into_fixed_chapter_payloads(full_text: str, event_short_title: str, chapter_numbers: List[int]) -> List[Dict[str, Any]]:
    clean_text = strip_trailing_json(full_text).strip()
    chapter_numbers = [int(item) for item in chapter_numbers]
    if not chapter_numbers:
        return []
    if len(chapter_numbers) == 1:
        return [{"chapter_num": chapter_numbers[0], "title": f"{event_short_title} 一", "content": clean_text}]

    paragraphs = [item.strip() for item in clean_text.split("\n") if item.strip()]
    if not paragraphs:
        paragraphs = [clean_text]
    total_length = max(sum(len(item) for item in paragraphs), 1)
    target_length = max(total_length // len(chapter_numbers), 1)
    chunks: List[str] = []
    current_parts: List[str] = []
    current_length = 0

    for idx, paragraph in enumerate(paragraphs):
        remaining_paragraphs = len(paragraphs) - idx
        remaining_slots = len(chapter_numbers) - len(chunks)
        if current_parts and ((current_length >= target_length and remaining_slots > 1) or remaining_paragraphs == remaining_slots):
            chunks.append("\n\n".join(current_parts).strip())
            current_parts = [paragraph]
            current_length = len(paragraph)
            continue
        current_parts.append(paragraph)
        current_length += len(paragraph)
    if current_parts:
        chunks.append("\n\n".join(current_parts).strip())

    while len(chunks) < len(chapter_numbers):
        longest_idx = max(range(len(chunks)), key=lambda item: len(chunks[item]))
        longest = chunks.pop(longest_idx)
        midpoint = max(len(longest) // 2, 1)
        split_pos = longest.rfind("\n\n", 0, midpoint)
        if split_pos == -1:
            split_pos = midpoint
        left = longest[:split_pos].strip()
        right = longest[split_pos:].strip()
        if not left or not right:
            left = longest[:midpoint].strip()
            right = longest[midpoint:].strip()
        chunks.insert(longest_idx, left or longest)
        chunks.insert(longest_idx + 1, right or longest)

    if len(chunks) > len(chapter_numbers):
        chunks = chunks[: len(chapter_numbers) - 1] + ["\n\n".join(chunks[len(chapter_numbers) - 1 :]).strip()]

    numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    payloads: List[Dict[str, Any]] = []
    for idx, chapter_num in enumerate(chapter_numbers):
        seq = numerals[idx] if idx < len(numerals) else str(idx + 1)
        payloads.append(
            {
                "chapter_num": chapter_num,
                "title": f"{event_short_title} {seq}",
                "content": (chunks[idx] if idx < len(chunks) else "").strip(),
            }
        )
    return payloads


def overwrite_event_chapters(
    novel_id: str,
    event_id: int,
    chapter_payloads: List[Dict[str, Any]],
    final_summary: str,
) -> List[Dict[str, Any]]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    applied: List[Dict[str, Any]] = []
    for idx, payload in enumerate(chapter_payloads):
        chapter_num_raw = payload.get("chapter_num")
        if chapter_num_raw in (None, ""):
            continue
        chapter_num = int(str(chapter_num_raw))
        title = str(payload.get("title") or "")
        content = str(payload.get("content") or "").strip()
        summary = final_summary if idx == len(chapter_payloads) - 1 else ""
        cur.execute(
            "SELECT id, COALESCE(rewrite_count, 0) FROM chapters WHERE novel_id=? AND chapter_num=? LIMIT 1",
            (novel_id, chapter_num),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE chapters SET source_event_id=?, title=?, content=?, summary=?, rewrite_count=?, status='ai_final', is_user_edited=0, updated_at=? WHERE id=?",
                (event_id, title, content, summary, int(row[1] or 0) + 1, now, row[0]),
            )
        else:
            cur.execute(
                "INSERT INTO chapters (novel_id, chapter_num, source_event_id, title, content, summary, quality_score, quality_issues, rewrite_count, cool_point_type, hook_strength, cliffhanger_type, status, is_locked, is_user_edited, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (novel_id, chapter_num, event_id, title, content, summary, 0, "[]", 1, "", 0, "", "ai_final", 0, 0, now, now),
            )
        applied.append({"chapter_num": chapter_num, "title": title, "content_length": len(content)})
    conn.commit()
    conn.close()
    return applied


def assign_ending_phases(novel_id: str) -> Dict[int, str]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT event_id FROM events WHERE novel_id=? AND is_written=0 ORDER BY event_id ASC",
        (novel_id,),
    )
    remaining = [row[0] for row in cur.fetchall()]
    phase_map: Dict[int, str] = {}
    total = len(remaining)
    if total == 0:
        conn.close()
        return phase_map

    for event_id in remaining:
        phase_map[event_id] = "normal"

    if total >= 5:
        phase_map[remaining[-5]] = "pre_ending"
        phase_map[remaining[-4]] = "pre_ending"
        phase_map[remaining[-3]] = "climax"
        phase_map[remaining[-2]] = "resolution"
        phase_map[remaining[-1]] = "epilogue"
    elif total == 4:
        phase_map[remaining[-4]] = "pre_ending"
        phase_map[remaining[-3]] = "climax"
        phase_map[remaining[-2]] = "resolution"
        phase_map[remaining[-1]] = "epilogue"
    elif total == 3:
        phase_map[remaining[-3]] = "pre_ending"
        phase_map[remaining[-2]] = "resolution"
        phase_map[remaining[-1]] = "epilogue"
    elif total == 2:
        phase_map[remaining[-2]] = "resolution"
        phase_map[remaining[-1]] = "epilogue"
    else:
        phase_map[remaining[-1]] = "epilogue"

    cur.execute("UPDATE events SET ending_phase='normal' WHERE novel_id=? AND is_written=0", (novel_id,))
    for event_id, phase in phase_map.items():
        cur.execute(
            "UPDATE events SET ending_phase=? WHERE novel_id=? AND event_id=?",
            (phase, novel_id, event_id),
        )
    conn.commit()
    conn.close()
    return phase_map


def prepare_fixed_ending_events(client: OpenAIClient, novel_id: str, log_fn, job_id: str) -> Dict[int, str]:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT ending_mode FROM novels WHERE id=? LIMIT 1", (novel_id,))
    row = cur.fetchone()
    if row and row[0]:
        cur.execute(
            "SELECT event_id, ending_phase FROM events WHERE novel_id=? AND is_written=0 AND ending_phase IN ('pre_ending', 'climax', 'resolution', 'epilogue') ORDER BY event_id ASC",
            (novel_id,),
        )
        existing = cur.fetchall()
        conn.close()
        return {event_id: phase for event_id, phase in existing}

    cur.execute("SELECT content FROM worldview WHERE novel_id=? LIMIT 1", (novel_id,))
    wv_row = cur.fetchone()
    current_wv = wv_row[0] if wv_row else "未知"
    cur.execute("SELECT synopsis FROM novels WHERE id=? LIMIT 1", (novel_id,))
    synopsis_row = cur.fetchone()
    synopsis = synopsis_row[0] if synopsis_row and synopsis_row[0] else ""
    growth_system_str = fetch_growth_system(novel_id)
    cur.execute("SELECT name, target, motive, state FROM characters WHERE novel_id=?", (novel_id,))
    chars = cur.fetchall()
    chars_str = "\n".join([f"- {c[0]}: 目标[{c[1]}], 动机[{c[2]}], 当前状态[{c[3]}]" for c in chars])
    cur.execute(
        "SELECT event_id, COALESCE(actual_summary, outline_description, description) FROM events WHERE novel_id=? ORDER BY event_id DESC LIMIT 15",
        (novel_id,),
    )
    recent_events = cur.fetchall()[::-1]
    past_events_str = "\n".join([f"事件 {e[0]}: {e[1]}" for e in recent_events])
    cur.execute("SELECT MAX(event_id) FROM events WHERE novel_id=?", (novel_id,))
    max_id = cur.fetchone()[0] or 0
    conn.close()

    prompt = f"""【系统指令：固定五步结局事件生成】
你现在要为这本小说生成固定 5 个步入结局的事件，作为最终结局链。

【一句话梗概】
{synopsis}

【主角成长体系】
{growth_system_str}

【当前世界局势】
{current_wv}

【主要人物状态】
{chars_str}

【最近剧情前情】
{past_events_str}

要求：
1. 固定只生成 5 个事件，事件号从 {max_id + 1} 到 {max_id + 5}。
2. 五个事件的 ending_phase 必须依次为：pre_ending、pre_ending、climax、resolution、epilogue。
3. 这是最终结局链，后续不再生成普通新事件。
4. 必须返回严格 JSON 数组，不要解释。
5. 每个事件对象必须包含：event_id, description, location, time_duration, core_conflict, foreshadowing, linked_characters, foreshadow_plan, ending_phase。
6. 每个事件还必须包含：goal, obstacle, cool_point_type, payoff_type, growth_reward, status_reward, cliffhanger，以及 growth_updates。
7. description 控制在 80-180 字；goal、obstacle、growth_reward、status_reward、cliffhanger 各控制在 20-80 字；cool_point_type 控制在 5-20 字；payoff_type 控制在 10-40 字。
8. 结局链禁止新增新伏笔。foreshadow_plan 必须始终返回空数组 []，foreshadowing 只能描述对已有伏笔的推进或回收，不得引入新的长期悬念。
"""
    log_fn(job_id, "结局模式已开启：正在固定生成 5 个结局事件...")
    reply = client.chat(prompt, meta={"step": "ending_outline", "prompt": "fixed_ending_outline", "novel_id": novel_id})
    events_json = parse_json_with_fix(client, reply, "array", meta={"prompt": "fixed_ending_outline", "novel_id": novel_id})
    if not events_json or len(events_json) != 5:
        raise ValueError("结局事件生成失败：未返回固定 5 个事件")

    phase_order = ["pre_ending", "pre_ending", "climax", "resolution", "epilogue"]
    for idx, ev in enumerate(events_json):
        ev["ending_phase"] = phase_order[idx]
        ev["status"] = "planned"
        growth_updates = ev.get("growth_updates") if isinstance(ev.get("growth_updates"), dict) else {}
        if not growth_updates.get("stage_summary"):
            growth_updates["stage_summary"] = phase_label(phase_order[idx])
        ev["growth_updates"] = growth_updates
    save_events(events_json, novel_id)
    save_initial_foreshadows(events_json, novel_id, allow_text_fallback=False)

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE novels SET ending_mode=1, ending_start_event_id=?, current_phase='ending', updated_at=? WHERE id=?",
        (max_id + 1, datetime.utcnow().isoformat(), novel_id),
    )
    conn.commit()
    conn.close()
    log_fn(job_id, f"结局事件已固定写入：事件 {max_id + 1} ~ {max_id + 5}")
    return {ev.get("event_id"): ev.get("ending_phase", "normal") for ev in events_json}


def fetch_character_details(novel_id: str, names: List[str]) -> str:
    conn = get_db_conn()
    cur = conn.cursor()
    details: List[str] = []
    for name in names:
        cur.execute(
            "SELECT name, role_tier, target, motive, secret, relationship, catchphrase, strengths, flaws, behavior_logic, has_sublimation_point, sublimation_type, sublimation_seed, sublimation_trigger, sublimation_payoff, sublimation_status, state, scope_type, planned_event_scope_text, story_function, item_updates FROM characters WHERE novel_id=? AND name=?",
            (novel_id, name),
        )
        res = cur.fetchone()
        if res:
            strengths = " / ".join(parse_string_list(res[7])) or "无"
            flaws = " / ".join(parse_string_list(res[8])) or "无"
            info = (
                f"- [{res[0]}]\n  层级: {res[1] or 'support'} | 目标: {res[2]} | 动机: {res[3]}\n  优点: {strengths}\n  缺点: {flaws}\n  行为逻辑: {res[9] or '未设定'}\n  秘密: {res[4]} | 关系: {res[5]} | 口头禅: {res[6] or '无'}\n  当前状态: {res[16]}\n  故事职能: {res[19] or '未设定'} | 计划关联: {res[18] or ('全篇' if res[17] == 'full' else '未标注')}"
            )
            if res[10]:
                info += (
                    f"\n  升华点: {res[11] or '未命名'} | 种子: {res[12] or '无'}"
                    f"\n  触发条件: {res[13] or '无'} | 兑现方式: {res[14] or '无'} | 当前进度: {res[15] or 'seeded'}"
                )
            try:
                item_updates = json.loads(res[20]) if res[20] else []
            except Exception:
                item_updates = []
            if item_updates:
                item_names = [str(item.get("name", "")).strip() for item in item_updates if isinstance(item, dict)]
                item_names = [name for name in item_names if name]
                if item_names:
                    info += f"\n  设定条目: {' / '.join(item_names)}"
            details.append(info)
    conn.close()
    return "\n".join(details)


def select_relevant_character_names(novel_id: str, current_event_id: int, linked_names: List[str], limit: int = 8) -> List[str]:
    plan = get_story_plan(novel_id)
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT name, role_tier, scope_type, planned_event_ranges, excluded_event_ranges, exit_mode, retired_after_event_id FROM characters WHERE novel_id=?",
        (novel_id,),
    )
    rows = cur.fetchall()
    conn.close()
    linked_set = {name for name in linked_names if name}
    scored = []
    for name, role_tier, scope_type, planned_ranges_raw, excluded_ranges_raw, exit_mode, retired_after_event_id in rows:
        if not name:
            continue
        planned_ranges = normalize_event_ranges(parse_json_array_text(planned_ranges_raw), plan["target_event_count"])
        excluded_ranges = normalize_event_ranges(parse_json_array_text(excluded_ranges_raw), plan["target_event_count"])
        if event_in_ranges(current_event_id, excluded_ranges):
            continue
        if str(exit_mode or "active") == "retired" and retired_after_event_id not in (None, ""):
            try:
                if current_event_id > int(retired_after_event_id):
                    continue
            except Exception:
                pass
        score = 0
        if name in linked_set:
            score += 100
        if event_in_ranges(current_event_id, planned_ranges):
            score += 80
        if str(scope_type or "") == "full":
            score += 60
        if str(role_tier or "") in {"protagonist", "major_support"}:
            score += 20
        if score > 0:
            scored.append((score, name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    ordered = [name for _, name in scored]
    for name in linked_names:
        if name and name not in ordered:
            ordered.insert(0, name)
    result = []
    seen = set()
    for name in ordered:
        if name in seen:
            continue
        seen.add(name)
        result.append(name)
        if len(result) >= limit:
            break
    return result


def normalize_linked_character_names(raw_value: str) -> List[str]:
    try:
        parsed = json.loads(raw_value) if raw_value else []
    except Exception:
        return []
    normalized: List[str] = []
    seen = set()
    if not isinstance(parsed, list):
        return []
    for item in parsed:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return normalized


def ensure_event_characters_ready(
    client: OpenAIClient,
    novel_id: str,
    blueprint_json: Dict[str, Any],
    growth_json_str: str,
    event_payload: Dict[str, Any],
    prompt_set: Dict[str, Dict[str, str]],
) -> int:
    linked_names = [name for name in event_payload.get("linked_characters", []) if name]
    if not linked_names:
        return 0
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT name FROM characters WHERE novel_id=?", (novel_id,))
    existing_names = {str(row[0]) for row in cur.fetchall() if row and row[0]}
    conn.close()
    missing_names = sorted({name for name in linked_names if name not in existing_names})
    if not missing_names:
        return 0
    worldview_summary = load_init_material(novel_id, "worldview_summary")
    opening_snapshot = load_init_material(novel_id, "world_snapshot_current")
    system_plan_note = build_story_plan_note(novel_id, event_payload.get("event_id") or 1, 1)
    prompt_system, prompt_user_template = render_prompt_messages(
        prompt_set["prompt_internal_supplement_characters"],
        {"system_plan": system_plan_note},
    )
    prompt_full = (
        f"【世界观摘要】\n{worldview_summary}\n\n"
        f"【世界快照】\n{opening_snapshot}\n\n"
        f"【阶段计划】\n{json.dumps(blueprint_json, ensure_ascii=False)}\n\n"
        f"【主角成长规划】\n{growth_json_str}\n\n"
        f"【当前事件列表】\n{json.dumps([event_payload], ensure_ascii=False)}\n\n"
        f"【仅补充以下缺失角色】\n{json.dumps(missing_names, ensure_ascii=False)}\n\n"
        f"{prompt_user_template}"
    )
    reply = client.chat(prompt_full, system_prompt=prompt_system, meta={"step": "event_prepare", "prompt": "prompt_internal_supplement_characters", "novel_id": novel_id, "event_id": event_payload.get("event_id")})
    chars_json = parse_json_with_fix(client, reply, "array", meta={"prompt": "prompt_internal_supplement_characters", "novel_id": novel_id, "event_id": event_payload.get("event_id")})
    if not chars_json:
        return 0
    return save_characters(chars_json, novel_id, blueprint_json, init_step="supplement_characters")


def fetch_open_foreshadows(
    novel_id: str,
    character_names: Optional[List[str]] = None,
    location: str = "",
    foreshadow: str = "",
    description: str = "",
    conflict: str = "",
    current_event_id: Optional[int] = None,
    limit_core: int = 3,
    limit_recent: int = 3,
) -> str:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, description, status, related_characters, introduced_event_id, expected_payoff_event_id, importance_level, notes, updated_at FROM foreshadows WHERE novel_id=? AND status != 'paid_off' ORDER BY introduced_event_id ASC, id ASC",
        (novel_id,),
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return "（暂无）"

    character_names = character_names or []
    text_blob = " ".join([location or "", foreshadow or "", description or "", conflict or ""])
    normalized_rows = []
    for row_id, description, status, related_characters, introduced_event_id, expected_payoff_event_id, importance_level, notes, updated_at in rows:
        try:
            related_list = json.loads(related_characters) if related_characters else []
        except Exception:
            related_list = []
        normalized_rows.append(
            {
                "id": row_id,
                "description": description,
                "status": status,
                "related_list": related_list,
                "introduced_event_id": introduced_event_id or 0,
                "expected_payoff_event_id": expected_payoff_event_id,
                "importance_level": importance_level or "medium",
                "notes": notes or "",
                "updated_at": updated_at or "",
            }
        )

    due_rows = []
    if current_event_id is not None:
        due_rows = [
            item for item in normalized_rows
            if item["expected_payoff_event_id"] is not None and int(item["expected_payoff_event_id"]) <= int(current_event_id)
        ]

    core_rows = normalized_rows[:limit_core]
    related_rows = []
    for item in normalized_rows:
        matched = False
        if any(name in item["related_list"] for name in character_names):
            matched = True
        elif text_blob and item["description"] and item["description"] in text_blob:
            matched = True
        elif foreshadow and foreshadow != "无" and item["description"] and item["description"] in foreshadow:
            matched = True
        if matched:
            related_rows.append(item)

    recent_rows = sorted(normalized_rows, key=lambda x: (x["updated_at"], x["introduced_event_id"]), reverse=True)[:limit_recent]

    merged = []
    seen = set()
    for group in [due_rows, core_rows, related_rows, recent_rows]:
        for item in group:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            merged.append(item)

    items = []
    for item in merged:
        rel_str = "、".join(item["related_list"]) if item["related_list"] else "无"
        payoff_str = item["expected_payoff_event_id"] if item["expected_payoff_event_id"] is not None else "待定"
        note_str = f" | 备注: {item['notes']}" if item["notes"] else ""
        items.append(
            f"- {item['description']} | 状态: {item['status']} | 引入事件: {item['introduced_event_id']} | 预计回收: 事件 {payoff_str} | 优先级: {item['importance_level']} | 相关人物: {rel_str}{note_str}"
        )
    return "\n".join(items)


def build_live_event_generation_context(
    client: OpenAIClient,
    novel_id: str,
    prompt_set: Dict[str, Dict[str, str]],
    event_data: Dict[str, Any],
) -> Dict[str, Any]:
    ev_id = int(event_data.get("event_id") or 0)
    plan = get_story_plan(novel_id)
    phase_key = phase_key_for_event(plan, ev_id)
    raw_ending_phase = str(event_data.get("ending_phase") or "").strip()
    if raw_ending_phase in {"pre_ending", "climax", "resolution", "epilogue"}:
        ending_phase = raw_ending_phase
    else:
        ending_phase = ending_subphase_for_event_id(plan, ev_id) if phase_key == "ending" else "normal"
    current_wv = fetch_worldview(novel_id)
    growth_system_str = fetch_growth_system(novel_id)
    summary = get_novel_summary(novel_id)
    novel_synopsis = summary.get("synopsis", "")

    linked_names = normalize_linked_character_names(str(event_data.get("linked_characters") or ""))
    entering_names = normalize_linked_character_names(str(event_data.get("entering_characters") or ""))
    if entering_names:
        linked_names = list(dict.fromkeys(entering_names + linked_names))
    blueprint_json = load_series_blueprint(novel_id) or {}
    prepared_count = ensure_event_characters_ready(
        client,
        novel_id,
        blueprint_json,
        growth_system_str,
        {
            "event_id": ev_id,
            "description": event_data.get("desc", ""),
            "goal": event_data.get("goal", ""),
            "obstacle": event_data.get("obstacle", ""),
            "cool_point_type": event_data.get("cool_point_type", ""),
            "payoff_type": event_data.get("payoff_type", ""),
            "growth_reward": event_data.get("growth_reward", ""),
            "status_reward": event_data.get("status_reward", ""),
            "cliffhanger": event_data.get("cliffhanger", ""),
            "linked_characters": linked_names,
        },
        prompt_set,
    )
    char_names = select_relevant_character_names(novel_id, ev_id, linked_names)
    char_details_str = fetch_character_details(novel_id, char_names)
    lorebook_str = fetch_lorebook(
        novel_id,
        character_names=char_names,
        location=event_data.get("location", ""),
        foreshadow=event_data.get("foreshadow", ""),
        description=event_data.get("desc", ""),
        conflict=event_data.get("conflict", ""),
    )
    open_foreshadows = fetch_open_foreshadows(
        novel_id,
        character_names=char_names,
        location=event_data.get("location", ""),
        foreshadow=event_data.get("foreshadow", ""),
        description=event_data.get("desc", ""),
        conflict=event_data.get("conflict", ""),
        current_event_id=ev_id,
    )
    full_outline_str = build_full_outline_context(client, novel_id, ev_id, open_foreshadows)
    phase_plan_note = build_story_plan_note(novel_id, ev_id, 1)
    blueprint_note = build_blueprint_guidance(novel_id, ev_id, 1)
    if ending_phase != "normal":
        ending_guide = {
            "pre_ending": "当前处于终局前夜阶段：收拢支线、强化对立、不得直接完结。",
            "climax": "当前处于终局高潮阶段：主冲突必须全面爆发，但不要把尾声提前写完。",
            "resolution": "当前处于高潮收束阶段：必须处理结果、代价与主要伏笔回收。",
            "epilogue": "当前处于尾声阶段：交代归宿与余韵，不再开启新的主线冲突。",
            "normal": "当前仍按普通连载逻辑推进。",
        }
        ending_note = f"\n【结局模式】已自动开启\n【当前结局阶段】{ending_phase}\n【阶段要求】{ending_guide.get(ending_phase, '')}"
        series_note = f"{phase_plan_note}\n{blueprint_note}\n当前事件结局阶段：{ending_phase}。请按阶段自然收束，不要骤然大结局。"
    else:
        ending_note = ""
        series_note = f"{phase_plan_note}\n{blueprint_note}"

    return {
        **event_data,
        "phase_key": phase_key,
        "ending_phase": ending_phase,
        "current_wv": current_wv,
        "growth_system_str": growth_system_str,
        "novel_synopsis": novel_synopsis,
        "linked_names": linked_names,
        "char_names": char_names,
        "char_details_str": char_details_str,
        "lorebook_str": lorebook_str,
        "open_foreshadows": open_foreshadows,
        "full_outline_str": full_outline_str,
        "series_note": series_note,
        "ending_note": ending_note,
        "prepared_character_count": prepared_count,
        "state_snapshot": build_event_state_snapshot(novel_id),
    }


def build_generation_input_checkpoint_payload(context: Dict[str, Any]) -> Dict[str, Any]:
    event_data = {
        key: context.get(key)
        for key in [
            "db_id",
            "event_id",
            "desc",
            "location",
            "time_duration",
            "conflict",
            "foreshadow",
            "goal",
            "obstacle",
            "cool_point_type",
            "payoff_type",
            "growth_reward",
            "status_reward",
            "cliffhanger",
            "ending_phase",
            "linked_characters",
            "entering_characters",
            "exiting_characters",
        ]
    }
    prompt_context = {
        key: context.get(key)
        for key in [
            "phase_key",
            "novel_synopsis",
            "current_wv",
            "growth_system_str",
            "linked_names",
            "char_names",
            "char_details_str",
            "lorebook_str",
            "open_foreshadows",
            "full_outline_str",
            "series_note",
            "ending_note",
            "event_world_snapshot_update_input",
            "event_foreshadow_updates_input",
            "event_growth_updates_input",
            "event_lorebook_updates_input",
        ]
    }
    return {
        "event_id": context.get("event_id"),
        "prepared_character_count": context.get("prepared_character_count", 0),
        "event_data": event_data,
        "prompt_context": prompt_context,
        "state_snapshot": context.get("state_snapshot") or {},
        "captured_at": datetime.utcnow().isoformat(),
    }


def snapshot_worldview(
    conn: sqlite3.Connection,
    novel_id: str,
    content: str,
    summary: str,
    source: str,
    source_event_id: Optional[int] = None,
) -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO worldview_snapshots (novel_id, source_event_id, content, summary, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (novel_id, source_event_id, content, summary, source, datetime.utcnow().isoformat()),
    )


def mark_event_user_edited(novel_id: str, event_id: int) -> None:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE events SET is_user_edited=1, source='user', status=CASE WHEN is_written=1 THEN 'completed' ELSE 'planned' END WHERE novel_id=? AND event_id=?",
        (novel_id, event_id),
    )
    conn.commit()
    conn.close()


def update_chapter(
    novel_id: str,
    db_id: int,
    ev_id: int,
    content: str,
    summary: str,
    title: str = "",
    chapter_num: Optional[int] = None,
    *,
    conn: Optional[sqlite3.Connection] = None,
    mark_event_complete: bool = True,
) -> None:
    own_conn = conn is None
    conn = conn or get_db_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    final_chapter_num = chapter_num if chapter_num is not None else ev_id
    cur.execute("SELECT cool_point_type, cliffhanger FROM events WHERE id=? LIMIT 1", (db_id,))
    event_row = cur.fetchone()
    chapter_cool_point_type = event_row[0] if event_row else ""
    chapter_cliffhanger = event_row[1] if event_row else ""
    cur.execute(
        "INSERT INTO chapters (novel_id, chapter_num, source_event_id, title, content, summary, quality_score, quality_issues, rewrite_count, cool_point_type, hook_strength, cliffhanger_type, status, is_locked, is_user_edited, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (novel_id, final_chapter_num, ev_id, title, content.strip(), summary, 0, "[]", 0, chapter_cool_point_type, 0, chapter_cliffhanger, "ai_final", 0, 0, now, now),
    )
    if mark_event_complete:
        if summary and summary != "摘要提取失败。":
            cur.execute(
                "UPDATE events SET is_written=1, actual_summary=?, status='completed' WHERE id=?",
                (summary, db_id),
            )
        else:
            cur.execute("UPDATE events SET is_written=1, status='completed' WHERE id=?", (db_id,))
    if own_conn:
        conn.commit()
        conn.close()


def update_world_and_chars(
    novel_id: str,
    json_data: Dict[str, Any],
    ev_id: int,
    event_deltas: Optional[Dict[str, Any]] = None,
    log_fn=None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, int]:
    own_conn = conn is None
    conn = conn or get_db_conn()
    cur = conn.cursor()
    deferred_logs: List[str] = []

    def log(message: str) -> None:
        if log_fn:
            deferred_logs.append(message)

    def parse_snapshot(text: str) -> Dict[str, Any]:
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def merge_snapshot(base: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for key, value in delta.items():
            if value is None:
                continue
            merged[key] = value
        return merged

    log(f"事件 {ev_id}：开始回填人物/世界/伏笔/成长")

    char_updates = json_data.get("character_state_updates", [])
    character_updates_count = 0
    for cu in char_updates:
        c_name = cu.get("name")
        c_new_state = cu.get("new_state")
        c_sublimation_status = cu.get("sublimation_status")
        if c_name and (c_new_state or c_sublimation_status):
            cur.execute("SELECT state, is_locked FROM characters WHERE novel_id=? AND name=?", (novel_id, c_name))
            row = cur.fetchone()
            if not row:
                continue
            old_state, is_locked = row
            if is_locked:
                continue
            if c_new_state:
                cur.execute(
                    "UPDATE characters SET state = ?, source='system' WHERE novel_id=? AND name = ?",
                    (c_new_state, novel_id, c_name),
                )
                cur.execute(
                    "INSERT INTO character_state_history (novel_id, character_name, source_event_id, old_state, new_state, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (novel_id, c_name, ev_id, old_state, c_new_state, datetime.utcnow().isoformat()),
                )
                character_updates_count += 1
            if c_sublimation_status:
                cur.execute(
                    "UPDATE characters SET sublimation_status = ?, source='system' WHERE novel_id=? AND name = ?",
                    (str(c_sublimation_status), novel_id, c_name),
                )
                character_updates_count += 1

    log(f"事件 {ev_id}：人物状态回填完成，更新 {character_updates_count} 项")

    lorebook_updates_count = 0
    foreshadow_count = 0
    growth_updated = 0

    if event_deltas:
        snapshot_update = event_deltas.get("world_snapshot_update")
        if isinstance(snapshot_update, dict) and snapshot_update:
            log(f"事件 {ev_id}：开始回填世界快照")
            current_snapshot = load_init_material(novel_id, "world_snapshot_current")
            base_snapshot = parse_snapshot(current_snapshot)
            merged_snapshot = merge_snapshot(base_snapshot, snapshot_update)
            snapshot_text = format_world_snapshot_text(merged_snapshot)
            save_init_material(novel_id, "world_snapshot_current", snapshot_text, conn=conn)
            cur.execute(
                "UPDATE worldview SET content = ?, updated_at = ? WHERE novel_id=?",
                (snapshot_text, datetime.utcnow().isoformat(), novel_id),
            )
            log(f"事件 {ev_id}：世界快照回填完成")

        lorebook_updates = event_deltas.get("lorebook_updates") or {}
        if isinstance(lorebook_updates, dict):
            log(f"事件 {ev_id}：开始回填设定库")
            new_items = lorebook_updates.get("new_items", [])
            updated_items = lorebook_updates.get("updated_items", [])
            removed_items = lorebook_updates.get("removed_items", [])
            if isinstance(new_items, list) and new_items:
                for item in new_items:
                    if isinstance(item, dict):
                        if not item.get("source_event_id"):
                            item["source_event_id"] = ev_id
                        if not item.get("last_update"):
                            item["last_update"] = f"事件 {ev_id}"
                lorebook_updates_count += upsert_lorebook_items(new_items, novel_id, conn=conn)
            if isinstance(updated_items, list) and updated_items:
                for item in updated_items:
                    if isinstance(item, dict):
                        if not item.get("source_event_id"):
                            item["source_event_id"] = ev_id
                        if not item.get("last_update"):
                            item["last_update"] = f"事件 {ev_id}"
                lorebook_updates_count += upsert_lorebook_items(updated_items, novel_id, conn=conn)
            if isinstance(removed_items, list) and removed_items:
                lorebook_updates_count += remove_lorebook_items(removed_items, novel_id, conn=conn)
            log(f"事件 {ev_id}：设定库回填完成，变更 {lorebook_updates_count} 条")

        foreshadow_updates = event_deltas.get("foreshadow_updates", [])
        if isinstance(foreshadow_updates, list):
            log(f"事件 {ev_id}：开始回填伏笔")
            now = datetime.utcnow().isoformat()
            for item in foreshadow_updates:
                if not isinstance(item, dict):
                    continue
                description = str(item.get("description", "")).strip()
                status = str(item.get("status", "introduced")).strip() or "introduced"
                if not description:
                    continue
                related_characters = json.dumps(item.get("related_characters", []), ensure_ascii=False)
                notes = str(item.get("notes", "")).strip()
                cur.execute(
                    "SELECT id, status FROM foreshadows WHERE novel_id=? AND description=? ORDER BY id DESC LIMIT 1",
                    (novel_id, description),
                )
                existing = cur.fetchone()
                if status == "introduced" or not existing:
                    cur.execute(
                        "INSERT INTO foreshadows (novel_id, description, introduced_event_id, expected_payoff_event_id, actual_payoff_event_id, status, importance_level, related_characters, notes, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            novel_id,
                            description,
                            ev_id,
                            None,
                            ev_id if status == "paid_off" else None,
                            "paid_off" if status == "paid_off" else "open",
                            "medium",
                            related_characters,
                            notes,
                            "chapter_update",
                            now,
                            now,
                        ),
                    )
                else:
                    foreshadow_id = existing[0]
                    db_status = "paid_off" if status == "paid_off" else "recurring"
                    cur.execute(
                        "UPDATE foreshadows SET status=?, actual_payoff_event_id=CASE WHEN ?='paid_off' THEN ? ELSE actual_payoff_event_id END, related_characters=?, notes=?, updated_at=? WHERE id=?",
                        (db_status, status, ev_id, related_characters, notes, now, foreshadow_id),
                    )
                foreshadow_count += 1
            log(f"事件 {ev_id}：伏笔回填完成，更新 {foreshadow_count} 条")

        growth_updates = event_deltas.get("growth_updates") or {}
        if isinstance(growth_updates, dict) and any(str(v).strip() for v in growth_updates.values() if v is not None):
            log(f"事件 {ev_id}：开始回填成长")
            cur.execute(
                "SELECT protagonist_name, final_goal, current_stage, stage_summary, power_system_level, power_system_notes, wealth_resources, special_resources, influence_assets, current_bottleneck, next_milestone FROM protagonist_progression WHERE novel_id=? LIMIT 1",
                (novel_id,),
            )
            existing = cur.fetchone()
            if existing:
                merged = {
                    "protagonist_name": existing[0],
                    "final_goal": existing[1],
                    "current_stage": growth_updates.get("current_stage") or existing[2],
                    "stage_summary": growth_updates.get("stage_summary") or existing[3],
                    "power_system_level": growth_updates.get("power_system_level") or existing[4],
                    "power_system_notes": growth_updates.get("power_system_notes") or existing[5],
                    "wealth_resources": growth_updates.get("wealth_resources") or existing[6],
                    "special_resources": growth_updates.get("special_resources") or existing[7],
                    "influence_assets": growth_updates.get("influence_assets") or existing[8],
                    "current_bottleneck": growth_updates.get("current_bottleneck") or existing[9],
                    "next_milestone": growth_updates.get("next_milestone") or existing[10],
                }
                growth_updated = 1
                save_growth_system(merged, novel_id, conn=conn)
                log(f"事件 {ev_id}：成长回填完成")

    sync_foreshadow_active_count(novel_id, conn=conn)
    if own_conn:
        conn.commit()
        conn.close()

    log(f"事件 {ev_id}：回填流程全部完成")
    if log_fn:
        for message in deferred_logs:
            log_fn(message)
    return {
        "lorebook_updates": lorebook_updates_count,
        "foreshadow_updates": foreshadow_count,
        "growth_updates": growth_updated,
    }


@router.post("/api/chapters")
def api_chapters(req: ChapterRequest) -> Dict[str, Any]:
    job_id = create_job("chapters", req.novel_id)

    def run() -> None:
        try:
            if req.target_words is not None:
                update_novel_story_plan(req.novel_id, req.target_words)
            sync_novel_phase(req.novel_id)
            client = OpenAIClient(req.api)
            prompt_set = load_effective_prompts(req.novel_id)
            target_events = max(1, int(req.limit_count or 1))
            results: List[Dict[str, Any]] = []
            processed_count = 0
            failed_events = 0
            backoff_schedule = [10, 30, 60, 100, 200]

            while processed_count < target_events:
                events_to_write = fetch_events(req.novel_id, target_events - processed_count)
                append_job_log(job_id, f"当前循环：processed_count={processed_count}, target_events={target_events}, 获取到 {len(events_to_write)} 个待写事件")
                
                if not events_to_write:
                    append_job_log(job_id, "当前可写事件已耗尽，尝试自动续写后继续生成...")
                    maybe_extend_outline(client, req.novel_id, append_job_log, job_id)
                    events_to_write = fetch_events(req.novel_id, target_events - processed_count)
                    append_job_log(job_id, f"自动续写后获取到 {len(events_to_write)} 个待写事件")
                    if not events_to_write:
                        if processed_count == 0:
                            finalize_job(job_id, result={"status": "empty"})
                            return
                        append_job_log(job_id, f"没有更多待写事件，结束任务。processed_count={processed_count}")
                        break

                for ev in events_to_write:
                    event_success = False
                    event_fail_reason = ""
                    ev_id = "未知"
                    db_id = 0
                    attempt = 0
                    while attempt < len(backoff_schedule):
                        try:
                            idx = processed_count + 1
                            if is_job_cancelled(job_id):
                                finalize_job(job_id, error="cancelled")
                                return
                            (
                                db_id,
                                ev_id,
                                desc,
                                ending_phase,
                                location,
                                time_duration,
                                conflict,
                                foreshadow,
                                linked_chars_str,
                                event_world_snapshot_update_str,
                                event_foreshadow_updates_str,
                                event_growth_updates_str,
                                event_lorebook_updates_str,
                                entering_chars_str,
                                exiting_chars_str,
                                goal,
                                obstacle,
                                cool_point_type,
                                payoff_type,
                                growth_reward,
                                status_reward,
                                cliffhanger,
                            ) = ev
                            append_job_log(job_id, f"=== 开始处理事件 {ev_id} (db_id={db_id}) ===")
                            base_progress = int(((idx - 1) / max(target_events, 1)) * 100)
                            set_job_progress(job_id, base_progress)
                            phase_key = phase_key_for_event(get_story_plan(req.novel_id), ev_id)
                            ending_phase = ending_phase or ("epilogue" if phase_key == "ending" else "normal")
                            if ending_phase != "normal":
                                append_job_log(job_id, f"事件 {ev_id} 结局阶段：{ending_phase}")

                            event_data = {
                                "db_id": db_id,
                                "event_id": ev_id,
                                "desc": desc,
                                "ending_phase": ending_phase,
                                "location": location,
                                "time_duration": time_duration,
                                "conflict": conflict,
                                "foreshadow": foreshadow,
                                "linked_characters": linked_chars_str,
                                "event_world_snapshot_update_input": event_world_snapshot_update_str or "{}",
                                "event_foreshadow_updates_input": event_foreshadow_updates_str or "[]",
                                "event_growth_updates_input": event_growth_updates_str or "{}",
                                "event_lorebook_updates_input": event_lorebook_updates_str or "{}",
                                "entering_characters": entering_chars_str,
                                "exiting_characters": exiting_chars_str,
                                "goal": goal or "",
                                "obstacle": obstacle or "",
                                "cool_point_type": cool_point_type or "",
                                "payoff_type": payoff_type or "",
                                "growth_reward": growth_reward or "",
                                "status_reward": status_reward or "",
                                "cliffhanger": cliffhanger or "",
                                "base_progress": base_progress,
                            }
                            context = build_live_event_generation_context(client, req.novel_id, prompt_set, event_data)
                            if context.get("prepared_character_count"):
                                append_job_log(job_id, f"事件 {ev_id} 分段前补充人物卡：{context['prepared_character_count']} 张")
                            save_event_checkpoint(
                                req.novel_id,
                                int(ev_id),
                                "generation_input",
                                build_generation_input_checkpoint_payload(context),
                            )

                            generation_bundle = generate_event_text_bundle(
                                client,
                                prompt_set,
                                req.novel_id,
                                int(ev_id),
                                req.novel_style,
                                context,
                                job_id=job_id,
                            )
                            chapter_summary = generation_bundle.get("chapter_summary") or "摘要提取失败。"
                            json_data = generation_bundle.get("json_data") or {"event_summary_update": chapter_summary, "character_state_updates": []}
                            saved_files = split_and_save_chapters_with_titles(
                                generation_bundle.get("full_event_content", "").strip(),
                                req.novel_id,
                                ev_id,
                                generation_bundle.get("event_short_title", "事件"),
                            )
                            append_job_log(job_id, f"事件 {ev_id} 写入完成：{', '.join([item.get('filename', '') for item in saved_files])}")
                            set_job_progress(job_id, base_progress + 90)

                            def parse_delta(raw, fallback):
                                if not raw:
                                    return fallback
                                try:
                                    parsed = json.loads(raw)
                                    return parsed if isinstance(parsed, type(fallback)) else fallback
                                except Exception:
                                    return fallback

                            event_deltas = {
                                "world_snapshot_update": parse_delta(event_world_snapshot_update_str, {}),
                                "foreshadow_updates": parse_delta(event_foreshadow_updates_str, []),
                                "growth_updates": parse_delta(event_growth_updates_str, {}),
                                "lorebook_updates": parse_delta(event_lorebook_updates_str, {}),
                            }

                            lore_updates = 0
                            foreshadow_updates_count = 0
                            growth_updates_count = 0
                            update_result = {"lorebook_updates": 0, "foreshadow_updates": 0, "growth_updates": 0}
                            apply_conn = get_db_conn(req.novel_id)
                            try:
                                for idx_file, item in enumerate(saved_files):
                                    file_title: str = str(item.get("title") or generation_bundle.get("event_short_title", "事件") or "事件")
                                    file_content: str = str(item.get("content", "") or "")
                                    chapter_num_value = item.get("chapter_num")
                                    chapter_num = int(chapter_num_value) if chapter_num_value is not None else None
                                    summary_value = chapter_summary if idx_file == len(saved_files) - 1 else ""
                                    update_chapter(
                                        req.novel_id,
                                        db_id,
                                        ev_id,
                                        file_content,
                                        summary_value,
                                        file_title,
                                        chapter_num,
                                        conn=apply_conn,
                                        mark_event_complete=False,
                                    )
                                update_result = update_world_and_chars(
                                    req.novel_id,
                                    json_data,
                                    ev_id,
                                    event_deltas,
                                    log_fn=lambda message: append_job_log(job_id, message),
                                    conn=apply_conn,
                                )
                                if chapter_summary and chapter_summary != "摘要提取失败。":
                                    apply_conn.cursor().execute(
                                        "UPDATE events SET is_written=1, actual_summary=?, status='completed' WHERE id=?",
                                        (chapter_summary, db_id),
                                    )
                                else:
                                    apply_conn.cursor().execute(
                                        "UPDATE events SET is_written=1, status='completed' WHERE id=?",
                                        (db_id,),
                                    )
                                output_checkpoint_payload = {
                                    "event_id": ev_id,
                                    "event_short_title": generation_bundle.get("event_short_title", "事件"),
                                    "sub_outline": generation_bundle.get("sub_outline", ""),
                                    "parts": generation_bundle.get("parts", []),
                                    "chapter_summary": chapter_summary,
                                    "json_data": json_data,
                                    "event_deltas": event_deltas,
                                    "saved_chapters": [
                                        {
                                            "filename": item.get("filename", ""),
                                            "chapter_num": int(item.get("chapter_num") or 0),
                                            "title": item.get("title", ""),
                                            "content_length": len(item.get("content", "") or ""),
                                        }
                                        for item in saved_files
                                    ],
                                    "update_result": update_result,
                                    "saved_at": datetime.utcnow().isoformat(),
                                }
                                save_event_checkpoint(req.novel_id, int(ev_id), "generation_output", output_checkpoint_payload, conn=apply_conn)
                                save_event_checkpoint(
                                    req.novel_id,
                                    int(ev_id),
                                    "post_apply_state",
                                    build_event_state_snapshot(req.novel_id, conn=apply_conn),
                                    conn=apply_conn,
                                )
                                apply_conn.commit()
                            except Exception:
                                apply_conn.rollback()
                                raise
                            finally:
                                apply_conn.close()

                            lore_updates = update_result.get("lorebook_updates", 0)
                            foreshadow_updates_count = update_result.get("foreshadow_updates", 0)
                            growth_updates_count = update_result.get("growth_updates", 0)
                            if lore_updates:
                                append_job_log(job_id, f"核心设定更新：{lore_updates} 条")
                            if foreshadow_updates_count:
                                append_job_log(job_id, f"伏笔更新：{foreshadow_updates_count} 条")
                            if growth_updates_count:
                                append_job_log(job_id, f"成长系统更新：{growth_updates_count} 条")

                            results.append(
                                {
                                    "event_id": ev_id,
                                    "saved_files": [item.get("filename") for item in saved_files],
                                    "event_short_title": generation_bundle.get("event_short_title", "事件"),
                                    "lorebook_updates": lore_updates,
                                    "foreshadow_updates": foreshadow_updates_count,
                                    "growth_updates": growth_updates_count,
                                }
                            )
                            processed_count += 1
                            event_success = True
                            append_job_log(job_id, f"=== 事件 {ev_id} 处理完成，processed_count={processed_count} ===")
                            record_event_run(req.novel_id, int(ev_id), "completed", "", job_id)
                            break

                        except Exception as ev_err:
                            attempt += 1
                            event_fail_reason = str(ev_err)
                            append_job_log(job_id, f"❌ 事件 {ev_id} 处理失败（第 {attempt} 次）：{event_fail_reason}")
                            import traceback
                            append_job_log(job_id, f"错误详情：{traceback.format_exc()}")
                            if attempt >= len(backoff_schedule):
                                break
                            wait_seconds = backoff_schedule[attempt - 1]
                            append_job_log(job_id, f"事件 {ev_id} 等待 {wait_seconds}s 后重试")
                            time.sleep(wait_seconds)

                    if event_success:
                        continue

                    failed_events += 1
                    try:
                        event_id_int = int(ev_id)
                    except Exception:
                        event_id_int = 0
                    record_event_run(req.novel_id, event_id_int, "failed", event_fail_reason, job_id)
                    conn = get_db_conn(req.novel_id)
                    cur = conn.cursor()
                    if event_id_int:
                        cur.execute(
                            "UPDATE events SET status='failed' WHERE novel_id=? AND event_id=?",
                            (req.novel_id, event_id_int),
                        )
                    conn.commit()
                    conn.close()
                    append_job_log(job_id, f"事件 {ev_id} 已标记为 failed，等待下次生产补回。当前失败计数 {failed_events}/5")
                    finalize_job(job_id, error=f"事件 {ev_id} 生成失败，任务已停止，避免跳过章节顺序。")
                    return

            append_job_log(job_id, f"所有事件处理完成，最终 processed_count={processed_count}")
            set_job_progress(job_id, 100)
            sync_novel_phase(req.novel_id)
            finalize_job(job_id, result={"status": "ok", "results": results, "processed_events": processed_count, "target_events": target_events})
        except Exception as e:
            finalize_job(job_id, error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return {"status": "accepted", "job_id": job_id}


@router.get("/api/novels/{novel_id}/events/{event_id}/checkpoints")
def api_event_checkpoints(novel_id: str, event_id: int) -> Dict[str, Any]:
    return {
        "checkpoints": list_event_checkpoints(novel_id, event_id),
        "generation_input": load_event_checkpoint(novel_id, event_id, "generation_input"),
        "generation_output": load_event_checkpoint(novel_id, event_id, "generation_output"),
        "post_apply_state": load_event_checkpoint(novel_id, event_id, "post_apply_state"),
        "artifacts": fetch_event_generation_artifacts(novel_id, event_id),
    }


@router.post("/api/novels/{novel_id}/events/{event_id}/rewrite")
def api_rewrite_event(novel_id: str, event_id: int, req: EventRewriteRequest) -> Dict[str, Any]:
    job_id = create_job("rewrite_event", novel_id)

    def run() -> None:
        try:
            if not req.preserve_chapter_count:
                finalize_job(job_id, error="当前版本仅支持保留原章节数重写")
                return
            input_checkpoint = load_event_checkpoint(novel_id, event_id, "generation_input")
            output_checkpoint = load_event_checkpoint(novel_id, event_id, "generation_output")
            if not input_checkpoint or not output_checkpoint:
                finalize_job(job_id, error="缺少事件 checkpoint，无法按原状态重写")
                return

            input_payload = input_checkpoint.get("payload") or {}
            output_payload = output_checkpoint.get("payload") or {}
            prompt_context = input_payload.get("prompt_context") or {}
            event_data = input_payload.get("event_data") or {}
            current_chapters = fetch_chapters_for_event(novel_id, event_id)
            chapter_numbers = [int(item.get("chapter_num") or 0) for item in current_chapters if int(item.get("chapter_num") or 0) > 0]
            if not chapter_numbers:
                chapter_numbers = [
                    int(item.get("chapter_num") or 0)
                    for item in (output_payload.get("saved_chapters") or [])
                    if int(item.get("chapter_num") or 0) > 0
                ]
            if not chapter_numbers:
                finalize_job(job_id, error="找不到可重写的章节编号")
                return

            append_job_log(job_id, f"开始重写事件 {event_id}，保留章节号：{chapter_numbers}")
            future_context = build_future_completed_events_context(novel_id, event_id)
            rewrite_constraints_text = format_rewrite_constraints_text(event_id, output_payload, future_context)
            context = {
                **event_data,
                **prompt_context,
                "base_progress": 0,
                "rewrite_constraints_text": rewrite_constraints_text,
                "state_snapshot": input_payload.get("state_snapshot") or {},
            }

            client = OpenAIClient(req.api)
            prompt_set = load_effective_prompts(novel_id)
            generation_bundle = generate_event_text_bundle(
                client,
                prompt_set,
                novel_id,
                event_id,
                req.novel_style,
                context,
                job_id=job_id,
            )

            preserved_summary = ""
            conn = get_db_conn(novel_id)
            cur = conn.cursor()
            cur.execute("SELECT actual_summary FROM events WHERE novel_id=? AND event_id=? LIMIT 1", (novel_id, event_id))
            row = cur.fetchone()
            conn.close()
            if row and row[0]:
                preserved_summary = str(row[0])
            elif output_payload.get("chapter_summary"):
                preserved_summary = str(output_payload.get("chapter_summary"))

            event_short_title = str(output_payload.get("event_short_title") or generation_bundle.get("event_short_title") or f"事件{event_id}")
            chapter_payloads = split_text_into_fixed_chapter_payloads(
                generation_bundle.get("full_event_content", ""),
                event_short_title,
                chapter_numbers,
            )
            applied_chapters = overwrite_event_chapters(novel_id, event_id, chapter_payloads, preserved_summary)
            save_event_checkpoint(
                novel_id,
                event_id,
                "last_rewrite_context",
                {
                    "future_context": future_context,
                    "rewrite_constraints_text": rewrite_constraints_text,
                    "chapter_numbers": chapter_numbers,
                    "used_generation_input_updated_at": input_checkpoint.get("updated_at"),
                    "used_generation_output_updated_at": output_checkpoint.get("updated_at"),
                    "created_at": datetime.utcnow().isoformat(),
                },
            )
            save_event_checkpoint(
                novel_id,
                event_id,
                "last_rewrite_result",
                {
                    "event_short_title": event_short_title,
                    "chapter_summary": preserved_summary,
                    "chapters": applied_chapters,
                    "rewritten_at": datetime.utcnow().isoformat(),
                },
            )
            record_event_run(novel_id, event_id, "rewritten", "checkpoint rewrite applied", job_id)
            finalize_job(
                job_id,
                result={
                    "status": "ok",
                    "event_id": event_id,
                    "chapter_numbers": chapter_numbers,
                    "chapters": applied_chapters,
                    "preserved_summary": preserved_summary,
                },
            )
        except Exception as e:
            finalize_job(job_id, error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return {"status": "accepted", "job_id": job_id}


@router.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> Dict[str, Any]:
    persisted = fetch_job_row(job_id)
    if persisted:
        return persisted
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job


@router.post("/api/jobs/{job_id}/cancel")
def api_cancel_job(job_id: str) -> Dict[str, Any]:
    cancel_job(job_id)
    return {"status": "ok"}


@router.delete("/api/jobs/{job_id}")
def api_delete_job(job_id: str) -> Dict[str, Any]:
    with jobs_lock:
        jobs.pop(job_id, None)
    novel_id = locate_job_novel_id(job_id)
    if novel_id:
        conn = get_db_conn(novel_id)
        cur = conn.cursor()
        cur.execute("DELETE FROM generation_logs WHERE job_id=?", (job_id,))
        cur.execute("DELETE FROM generation_runs WHERE job_id=?", (job_id,))
        conn.commit()
        conn.close()
    return {"status": "ok"}


@router.delete("/api/jobs")
def api_clear_jobs() -> Dict[str, Any]:
    with jobs_lock:
        jobs.clear()
    for novel_id in list_novel_ids():
        conn = get_db_conn(novel_id)
        cur = conn.cursor()
        cur.execute("DELETE FROM generation_logs")
        cur.execute("DELETE FROM generation_runs")
        conn.commit()
        conn.close()
    return {"status": "ok"}


@router.get("/api/jobs")
def api_jobs() -> Dict[str, Any]:
    rows = list_all_job_rows()
    if rows:
        return {"jobs": rows}
    with jobs_lock:
        items = []
        for job_id, job in jobs.items():
            items.append({
                "job_id": job_id,
                "status": job.get("status"),
                "job_type": job.get("job_type"),
                "novel_id": job.get("novel_id"),
                "progress": job.get("progress", 0),
                "step_label": job.get("step_label", ""),
                "created_at": job.get("created_at"),
            })
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"jobs": items}


