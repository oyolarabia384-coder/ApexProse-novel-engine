import json
import os
import re
import sqlite3
import threading
import time
import uuid
import csv
import io
import inspect
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")
SYSTEM_DB_FILE = os.path.join(DATA_DIR, "system.db")
LEGACY_DB_FILE = os.path.join(BASE_DIR, "novel_maker.db")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
NOVEL_INDEX_FILE = os.path.join(BASE_DIR, "novel_index.json")
PROMPT_BACKUP_DIR = os.path.join(BASE_DIR, "prompt_backups")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOG_DIR = os.path.join(ROOT_DIR, "log")
EXPORT_DIR = os.path.join(ROOT_DIR, "exports")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(PROMPT_BACKUP_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

NOVEL_ID_PATTERN = re.compile(r"^n_[a-z0-9_]+$")
SYSTEM_DB_CALLERS = {
    "init_db",
    "recover_stale_jobs",
    "create_job_record",
    "update_job_record",
    "append_job_log_record",
    "api_job",
    "api_delete_job",
    "api_clear_jobs",
    "api_jobs",
}

WORDS_PER_EVENT = 10000
ENDING_RESERVED_CHAPTERS = 1


def normalize_target_words(target_words: int) -> int:
    try:
        value = int(target_words)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid target words") from exc
    if value < WORDS_PER_EVENT:
        raise HTTPException(status_code=400, detail=f"目标字数不能低于 {WORDS_PER_EVENT}")
    return value


def build_story_plan(target_words: int, words_per_event: int = WORDS_PER_EVENT) -> Dict[str, int]:
    target_words = normalize_target_words(target_words)
    words_per_event = max(1, int(words_per_event or WORDS_PER_EVENT))
    target_event_count = max(1, (target_words + words_per_event - 1) // words_per_event)
    opening_breakthrough_count = max(1, min(3, (target_event_count * 3 + 99) // 100))
    development_end_event_id = max(opening_breakthrough_count + 1, (target_event_count * 20 + 99) // 100)
    ending_event_count = max(1, (target_event_count * 20 + 99) // 100)
    ending_start_event_id = max(1, target_event_count - ending_event_count + 1)
    stable_serial_start_event_id = development_end_event_id + 1
    stable_serial_end_event_id = max(stable_serial_start_event_id, ending_start_event_id - 1)
    return {
        "target_words": target_words,
        "words_per_event": words_per_event,
        "target_event_count": target_event_count,
        "opening_breakthrough_count": opening_breakthrough_count,
        "development_end_event_id": development_end_event_id,
        "stable_serial_start_event_id": stable_serial_start_event_id,
        "stable_serial_end_event_id": stable_serial_end_event_id,
        "ending_start_event_id": ending_start_event_id,
        "ending_event_count": ending_event_count,
    }


def phase_key_for_event(plan: Dict[str, int], event_id: int) -> str:
    if event_id <= plan["opening_breakthrough_count"]:
        return "opening_breakthrough"
    if event_id <= plan["development_end_event_id"]:
        return "development"
    if event_id < plan["ending_start_event_id"]:
        return "stable_serial"
    return "ending"


def ending_subphase_for_event_id(plan: Dict[str, int], event_id: int) -> str:
    """Return ending sub-phase for an event based on percentage distribution.

    Distribution within the ending range:
    - pre_ending: 40%
    - climax: 30%
    - resolution: 20%
    - epilogue: 10%

    For non-ending events, returns "normal".
    """
    try:
        ev_id = int(event_id)
    except Exception:
        return "normal"
    ending_start = int(plan.get("ending_start_event_id") or 0)
    target_event_count = int(plan.get("target_event_count") or 0)
    if ending_start <= 0 or target_event_count <= 0:
        return "normal"
    if ev_id < ending_start:
        return "normal"
    ending_total = max(1, (target_event_count - ending_start) + 1)
    position = (ev_id - ending_start) + 1  # 1-based
    if position < 1:
        position = 1
    if position > ending_total:
        position = ending_total
    # Compare using integers to avoid floating rounding surprises.
    if position * 100 <= ending_total * 40:
        return "pre_ending"
    if position * 100 <= ending_total * 70:
        return "climax"
    if position * 100 <= ending_total * 90:
        return "resolution"
    return "epilogue"


def phase_label(phase_key: str) -> str:
    labels = {
        "opening_breakthrough": "开篇破局期",
        "development": "发展沉淀期",
        "stable_serial": "稳定连载期",
        "ending": "结局期",
    }
    return labels.get(phase_key, phase_key)


def phase_requirements_text(phase_key: str) -> str:
    mapping = {
        "opening_breakthrough": (
            "建立日常基准，引入核心金手指或重大变故，确立第一个短期生存目标。"
            "先压主角，再完成第一次降维打击、危机反杀或标志性破局。"
        ),
        "development": (
            "拓展地图、结识初期势力、升级核心资源。"
            "必须完成开篇短期目标，并在阶段内持续出现多次成长反馈。"
            "每2-3个事件至少出现一次显著收益，每5个事件形成一次阶段推进。"
        ),
        "stable_serial": (
            "抛出深层世界观悬念，推进势力交锋与大秘境/大副本轮转。"
            "强调降维碾压、智商碾压、信息差碾压，不得长期只铺垫不兑现。"
        ),
        "ending": (
            "回收核心伏笔，所有线索向终极目标收束。"
            "推进宿命对决、终极谜底揭晓，以及对世界底层规则的重构或超越。"
        ),
    }
    return mapping.get(phase_key, "围绕主线持续推进。")


def format_upstream_error_message(detail: Any) -> str:
    raw = str(detail or "").strip()
    if not raw:
        return "上游服务返回空错误信息"
    parsed: Dict[str, Any] = {}
    try:
        candidate = json.loads(raw)
        if isinstance(candidate, dict):
            parsed = candidate
    except Exception:
        parsed = {}

    code = str(parsed.get("code", "")).strip().upper()
    message = str(parsed.get("message") or parsed.get("detail") or raw).strip()
    upper_message = message.upper()
    if code == "SUBSCRIPTION_NOT_FOUND" or "NO ACTIVE SUBSCRIPTION FOUND FOR THIS GROUP" in upper_message:
        return "当前 API 账号或分组没有可用订阅，请先更换可用的 API Key/分组；如果想先继续流程，也可以手动填写世界设定后再执行后续初始化步骤。"
    if code in {"INVALID_API_KEY", "UNAUTHORIZED"} or "INVALID API KEY" in upper_message:
        return "API Key 无效或未授权，请检查控制台中的 API 配置。"
    if code in {"INSUFFICIENT_QUOTA", "QUOTA_EXCEEDED"} or "INSUFFICIENT QUOTA" in upper_message:
        return "当前 API 额度不足，请更换有余额/配额的账号后再试。"
    if "CHATGPT ACCOUNT" in upper_message and "CODEX" in upper_message and "NOT SUPPORTED" in upper_message:
        return "当前选中的模型不支持你这类账号鉴权方式。你现在的配置仍在使用 `gpt-5.4`，但上游提示该模型不能通过 Codex/ChatGPT 账号方式调用。请到 API 配置里把当前配置的模型改成该网关实际支持的模型后再试，例如 `gpt-4.1`、`gpt-4o` 或你服务商提供的可用模型名。"
    return message or raw


def parse_json_array_text(raw_value: Any) -> List[Any]:
    if isinstance(raw_value, list):
        return raw_value
    if not isinstance(raw_value, str) or not raw_value.strip():
        return []
    try:
        parsed = json.loads(raw_value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def format_world_snapshot_text(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    if isinstance(raw_value, (dict, list)):
        return json.dumps(raw_value, ensure_ascii=False, indent=2)
    text = str(raw_value).strip()
    if not text:
        return ""
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, (dict, list)):
                return json.dumps(parsed, ensure_ascii=False, indent=2)
        except Exception:
            return text
    return text


def normalize_linked_character_names(raw_value: Any) -> List[str]:
    parsed = parse_json_array_text(raw_value)
    normalized: List[str] = []
    seen = set()
    for item in parsed:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return normalized


def normalize_event_ranges(raw_ranges: Any, target_event_count: int) -> List[Dict[str, int]]:
    normalized: List[Dict[str, int]] = []
    seen = set()
    if not isinstance(raw_ranges, list):
        return normalized
    for item in raw_ranges:
        if not isinstance(item, dict):
            continue
        start_raw: Any = item.get("start_event_id", item.get("start"))
        end_raw: Any = item.get("end_event_id", item.get("end"))
        try:
            start_id = int(start_raw)
            end_id = int(end_raw)
        except Exception:
            continue
        if start_id > end_id:
            start_id, end_id = end_id, start_id
        start_id = max(1, start_id)
        end_id = min(max(1, target_event_count), end_id)
        if start_id > end_id:
            continue
        key = (start_id, end_id)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"start_event_id": start_id, "end_event_id": end_id})
    normalized.sort(key=lambda item: (item["start_event_id"], item["end_event_id"]))
    return normalized


def format_event_range_text(ranges: List[Dict[str, int]], target_event_count: int, scope_type: str = "range") -> str:
    normalized = normalize_event_ranges(ranges, target_event_count)
    if scope_type == "full":
        return "全篇"
    if not normalized:
        return ""
    parts: List[str] = []
    for item in normalized:
        start_id = item["start_event_id"]
        end_id = item["end_event_id"]
        parts.append(str(start_id) if start_id == end_id else f"{start_id}-{end_id}")
    return ",".join(parts)


def parse_event_scope_text(scope_text: Any, target_event_count: int) -> List[Dict[str, int]]:
    if not isinstance(scope_text, str):
        return []
    text = scope_text.strip()
    if not text:
        return []
    if text in {"全篇", "全文", "全书", "full"}:
        return [{"start_event_id": 1, "end_event_id": max(1, target_event_count)}]
    ranges: List[Dict[str, int]] = []
    for chunk in re.split(r"[，,；;、\s]+", text):
        part = chunk.strip()
        if not part:
            continue
        if "-" in part:
            left, right = part.split("-", 1)
        elif "~" in part:
            left, right = part.split("~", 1)
        else:
            left, right = part, part
        try:
            start_id = int(left)
            end_id = int(right)
        except Exception:
            continue
        ranges.append({"start_event_id": start_id, "end_event_id": end_id})
    return normalize_event_ranges(ranges, target_event_count)


def event_ids_to_scope_text(event_ids: List[int]) -> str:
    if not event_ids:
        return ""
    sorted_ids = sorted({int(item) for item in event_ids})
    ranges: List[Dict[str, int]] = []
    start_id = sorted_ids[0]
    end_id = sorted_ids[0]
    for event_id in sorted_ids[1:]:
        if event_id == end_id + 1:
            end_id = event_id
        else:
            ranges.append({"start_event_id": start_id, "end_event_id": end_id})
            start_id = event_id
            end_id = event_id
    ranges.append({"start_event_id": start_id, "end_event_id": end_id})
    return format_event_range_text(ranges, max(sorted_ids), "range")


def build_stage_plan_entries(plan: Dict[str, int]) -> List[Dict[str, Any]]:
    return [
        {
            "phase": "opening_breakthrough",
            "phase_label": phase_label("opening_breakthrough"),
            "start_event_id": 1,
            "end_event_id": plan["opening_breakthrough_count"],
            "phase_goal": "建立基准、引爆变故、锁定短期生存目标。",
            "phase_requirements": ["建立日常基准", "引入核心金手指或重大变故", "完成第一次强势破局或危机反杀"],
            "progress_focus": "让主角从被动求生切到主动破局，并明确短期目标。",
            "exit_condition": "短期生存目标成立，主角获得继续扩张的资格。",
            "growth_goal": "让主角完成从普通人到可主动破局者的第一次跃迁。",
            "power_goal": "建立第一套可稳定复用的核心能力路径。",
            "resource_goal": "拿到第一批可持续使用的核心资源。",
            "influence_goal": "建立最初的可信盟友或立足身份。",
            "growth_bottleneck": "主角尚未真正理解世界规则与自身优势边界。",
            "growth_milestone": "完成第一次强势破局并证明自身价值。",
        },
        {
            "phase": "development",
            "phase_label": phase_label("development"),
            "start_event_id": plan["opening_breakthrough_count"] + 1,
            "end_event_id": plan["development_end_event_id"],
            "phase_goal": "拓图、结识势力、连续获得成长反馈，完成开篇短期目标。",
            "phase_requirements": ["每2-3个事件出现一次显著成长反馈", "推进资源、势力、人脉中的至少一项", "完成开篇短期目标"],
            "progress_focus": "让主角从局部生存转入更大盘面的竞争。",
            "exit_condition": "主角完成开篇短期目标，并进入长期主线竞争。",
            "growth_goal": "让主角完成连续成长反馈并形成阶段性优势。",
            "power_goal": "建立可持续升级的能力体系与战斗风格。",
            "resource_goal": "稳定获得资源补给、情报来源或修炼条件。",
            "influence_goal": "进入至少一层真实势力网络并拥有可调用关系。",
            "growth_bottleneck": "局部优势尚不足以支撑更大盘面的对抗。",
            "growth_milestone": "完成开篇短期目标并获得一次明显阶段跃升。",
        },
        {
            "phase": "stable_serial",
            "phase_label": phase_label("stable_serial"),
            "start_event_id": plan["development_end_event_id"] + 1,
            "end_event_id": max(plan["development_end_event_id"] + 1, plan["ending_start_event_id"] - 1),
            "phase_goal": "推进深层悬念、势力交锋和副本轮转，持续兑现高光。",
            "phase_requirements": ["持续推进世界悬念与势力交锋", "保持副本或篇章轮转", "稳定兑现高光与成长收益"],
            "progress_focus": "把主线冲突和深层世界谜题持续推高，避免空转。",
            "exit_condition": "核心伏笔开始集中回收，所有线索明显转向终极目标。",
            "growth_goal": "让主角形成足以改变大局的综合能力与布局能力。",
            "power_goal": "完成中高阶能力体系的稳定掌握与突破准备。",
            "resource_goal": "掌握能够支撑长期大战或大布局的资源池。",
            "influence_goal": "拥有可影响多方势力格局的话语权或实际控制力。",
            "growth_bottleneck": "主角缺少触及世界底层真相与终局规则的关键钥匙。",
            "growth_milestone": "核心伏笔开始回收，主角拥有冲击终局的资格。",
        },
        {
            "phase": "ending",
            "phase_label": phase_label("ending"),
            "start_event_id": plan["ending_start_event_id"],
            "end_event_id": plan["target_event_count"],
            "phase_goal": "集中回收核心伏笔，完成宿命对决和世界规则级兑现。",
            "phase_requirements": ["集中回收核心伏笔", "推进终极谜底揭晓", "完成主要人物结算"],
            "progress_focus": "让所有主线矛盾向终局收束，不再横向扩张。",
            "exit_condition": "尾声交代完成，主角达成或超越终极目标。",
            "growth_goal": "让主角完成最终能力、认知与身份上的终局兑现。",
            "power_goal": "完成终局突破或规则级超越。",
            "resource_goal": "将一切核心资源转化为终局胜势。",
            "influence_goal": "完成主要阵营关系与世界秩序的最终结算。",
            "growth_bottleneck": "终局前必须解决最后的规则限制与代价问题。",
            "growth_milestone": "完成宿命对决并达成或超越终极目标。",
        },
    ]


def ensure_json_file(path: str, default: Any) -> None:
    if os.path.exists(path):
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(default, f, ensure_ascii=False, indent=2)


def validate_novel_id(novel_id: str) -> str:
    if not isinstance(novel_id, str) or not NOVEL_ID_PATTERN.fullmatch(novel_id):
        raise HTTPException(status_code=400, detail="Invalid novel id")
    return novel_id


def generate_novel_id() -> str:
    return f"n_{datetime.utcnow().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"


def novel_db_path(novel_id: str) -> str:
    return os.path.join(DATA_DIR, f"{validate_novel_id(novel_id)}.sqlite")


def load_novel_index() -> List[Dict[str, Any]]:
    ensure_json_file(NOVEL_INDEX_FILE, [])
    try:
        with open(NOVEL_INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = []
    return data if isinstance(data, list) else []


def save_novel_index(items: List[Dict[str, Any]]) -> None:
    with open(NOVEL_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def upsert_novel_index_item(item: Dict[str, Any]) -> None:
    items = load_novel_index()
    replaced = False
    for idx, existing in enumerate(items):
        if existing.get("id") == item.get("id"):
            items[idx] = item
            replaced = True
            break
    if not replaced:
        items.append(item)
    save_novel_index(items)


def delete_novel_index_item(novel_id: str) -> None:
    items = [item for item in load_novel_index() if item.get("id") != novel_id]
    save_novel_index(items)


def get_system_db_conn() -> sqlite3.Connection:
    return sqlite3.connect(SYSTEM_DB_FILE, check_same_thread=False)


def init_novel_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS novels (
            id TEXT PRIMARY KEY,
            title TEXT UNIQUE,
            synopsis TEXT,
            style TEXT,
            target_words INTEGER DEFAULT 500000,
            words_per_event INTEGER DEFAULT 10000,
            target_event_count INTEGER DEFAULT 50,
            opening_breakthrough_count INTEGER DEFAULT 2,
            development_end_event_id INTEGER DEFAULT 10,
            foreshadow_active_count INTEGER DEFAULT 0,
            ending_mode BOOLEAN DEFAULT 0,
            ending_start_event_id INTEGER,
            ending_event_count INTEGER DEFAULT 10,
            current_phase TEXT DEFAULT 'draft',
            updated_at TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS worldview (
            id INTEGER PRIMARY KEY,
            novel_id TEXT,
            content TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS worldview_snapshots (
            id INTEGER PRIMARY KEY,
            novel_id TEXT,
            source_event_id INTEGER,
            content TEXT,
            summary TEXT,
            source TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS init_materials (
            novel_id TEXT,
            material_key TEXT,
            content TEXT,
            updated_at TEXT,
            PRIMARY KEY (novel_id, material_key)
        );
        CREATE TABLE IF NOT EXISTS init_steps (
            novel_id TEXT,
            step_key TEXT,
            state TEXT DEFAULT 'stale',
            updated_at TEXT,
            PRIMARY KEY (novel_id, step_key)
        );
        CREATE TABLE IF NOT EXISTS series_blueprint (
            id INTEGER PRIMARY KEY,
            novel_id TEXT UNIQUE,
            content TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY,
            novel_id TEXT,
            name TEXT,
            role_tier TEXT,
            target TEXT,
            motive TEXT,
            secret TEXT,
            relationship TEXT,
            catchphrase TEXT,
            growth_arc TEXT,
            strengths TEXT,
            flaws TEXT,
            behavior_logic TEXT,
            has_sublimation_point BOOLEAN DEFAULT 0,
            sublimation_type TEXT,
            sublimation_seed TEXT,
            sublimation_trigger TEXT,
            sublimation_payoff TEXT,
            sublimation_status TEXT DEFAULT 'none',
            state TEXT,
            scope_type TEXT DEFAULT 'range',
            planned_event_scope_text TEXT DEFAULT '',
            planned_event_ranges TEXT DEFAULT '[]',
            excluded_event_scope_text TEXT DEFAULT '',
            excluded_event_ranges TEXT DEFAULT '[]',
            exit_mode TEXT DEFAULT 'active',
            retired_after_event_id INTEGER,
            return_required BOOLEAN DEFAULT 0,
            return_reason TEXT DEFAULT '',
            init_step TEXT DEFAULT '',
            story_function TEXT DEFAULT '',
            item_updates TEXT DEFAULT '[]',
            is_locked BOOLEAN DEFAULT 0,
            is_user_edited BOOLEAN DEFAULT 0,
            source TEXT DEFAULT 'ai',
            UNIQUE(novel_id, name)
        );
        CREATE TABLE IF NOT EXISTS character_state_history (
            id INTEGER PRIMARY KEY,
            novel_id TEXT,
            character_name TEXT,
            source_event_id INTEGER,
            old_state TEXT,
            new_state TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS lorebook (
            id INTEGER PRIMARY KEY,
            novel_id TEXT,
            name TEXT,
            type TEXT,
            description TEXT,
            location TEXT,
            related_characters TEXT,
            source_event_id INTEGER,
            last_update TEXT,
            is_locked BOOLEAN DEFAULT 0,
            is_user_edited BOOLEAN DEFAULT 0,
            source TEXT DEFAULT 'ai',
            UNIQUE(novel_id, name)
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            novel_id TEXT,
            event_id INTEGER,
            description TEXT,
            outline_description TEXT,
            actual_summary TEXT,
            goal TEXT,
            obstacle TEXT,
            cool_point_type TEXT,
            payoff_type TEXT,
            growth_reward TEXT,
            status_reward TEXT,
            cliffhanger TEXT,
            ending_phase TEXT DEFAULT 'normal',
            location TEXT,
            time_duration TEXT,
            core_conflict TEXT,
            foreshadowing TEXT,
            linked_characters TEXT,
            event_world_snapshot_update TEXT,
            event_foreshadow_updates TEXT DEFAULT '[]',
            event_growth_updates TEXT DEFAULT '{}',
            event_lorebook_updates TEXT DEFAULT '{}',
            is_written BOOLEAN DEFAULT 0,
            status TEXT DEFAULT 'planned',
            is_locked BOOLEAN DEFAULT 0,
            is_user_edited BOOLEAN DEFAULT 0,
            source TEXT DEFAULT 'ai'
        );
        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY,
            novel_id TEXT,
            chapter_num INTEGER,
            source_event_id INTEGER,
            title TEXT,
            content TEXT,
            summary TEXT,
            quality_score INTEGER DEFAULT 0,
            quality_issues TEXT DEFAULT '[]',
            rewrite_count INTEGER DEFAULT 0,
            cool_point_type TEXT DEFAULT '',
            hook_strength INTEGER DEFAULT 0,
            cliffhanger_type TEXT DEFAULT '',
            status TEXT DEFAULT 'ai_final',
            is_locked BOOLEAN DEFAULT 0,
            is_user_edited BOOLEAN DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS foreshadows (
            id INTEGER PRIMARY KEY,
            novel_id TEXT,
            description TEXT,
            introduced_event_id INTEGER,
            expected_payoff_event_id INTEGER,
            actual_payoff_event_id INTEGER,
            status TEXT DEFAULT 'open',
            importance_level TEXT DEFAULT 'medium',
            related_characters TEXT,
            notes TEXT,
            source TEXT DEFAULT 'system',
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS protagonist_progression (
            id INTEGER PRIMARY KEY,
            novel_id TEXT UNIQUE,
            protagonist_name TEXT,
            final_goal TEXT,
            current_stage TEXT,
            stage_summary TEXT,
            power_system_level TEXT,
            power_system_notes TEXT,
            wealth_resources TEXT,
            special_resources TEXT,
            influence_assets TEXT,
            current_bottleneck TEXT,
            next_milestone TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS generation_runs (
            id INTEGER PRIMARY KEY,
            job_id TEXT UNIQUE,
            novel_id TEXT,
            run_type TEXT,
            status TEXT,
            progress INTEGER DEFAULT 0,
            step_label TEXT,
            result_json TEXT,
            error_message TEXT,
            cancelled BOOLEAN DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS generation_logs (
            id INTEGER PRIMARY KEY,
            job_id TEXT,
            level TEXT,
            step TEXT,
            message TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS event_runs (
            id INTEGER PRIMARY KEY,
            novel_id TEXT,
            event_id INTEGER,
            job_id TEXT,
            status TEXT,
            reason TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS context_cache (
            cache_key TEXT PRIMARY KEY,
            content TEXT,
            source_hash TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS event_checkpoints (
            id INTEGER PRIMARY KEY,
            novel_id TEXT,
            event_id INTEGER,
            checkpoint_type TEXT,
            payload_json TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(novel_id, event_id, checkpoint_type)
        );
        CREATE TABLE IF NOT EXISTS event_generation_artifacts (
            id INTEGER PRIMARY KEY,
            novel_id TEXT,
            event_id INTEGER,
            stage TEXT,
            part_name TEXT,
            meta_json TEXT,
            system_prompt TEXT,
            user_prompt TEXT,
            response_text TEXT,
            error_text TEXT,
            created_at TEXT
        );
        """
    )
    def ensure_column(table: str, column: str, definition: str) -> None:
        cur.execute(f"PRAGMA table_info({table})")
        names = {row[1] for row in cur.fetchall()}
        if column not in names:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    for column, definition in [
        ("target_words", "INTEGER DEFAULT 500000"),
        ("words_per_event", "INTEGER DEFAULT 10000"),
        ("target_event_count", "INTEGER DEFAULT 50"),
        ("opening_breakthrough_count", "INTEGER DEFAULT 2"),
        ("development_end_event_id", "INTEGER DEFAULT 10"),
        ("foreshadow_active_count", "INTEGER DEFAULT 0"),
        ("ending_event_count", "INTEGER DEFAULT 10"),
    ]:
        ensure_column("novels", column, definition)
    for column, definition in [
        ("role_tier", "TEXT"),
        ("strengths", "TEXT"),
        ("flaws", "TEXT"),
        ("behavior_logic", "TEXT"),
        ("has_sublimation_point", "BOOLEAN DEFAULT 0"),
        ("sublimation_type", "TEXT"),
        ("sublimation_seed", "TEXT"),
        ("sublimation_trigger", "TEXT"),
        ("sublimation_payoff", "TEXT"),
        ("sublimation_status", "TEXT DEFAULT 'none'"),
        ("scope_type", "TEXT DEFAULT 'range'"),
        ("planned_event_scope_text", "TEXT DEFAULT ''"),
        ("planned_event_ranges", "TEXT DEFAULT '[]'"),
        ("excluded_event_scope_text", "TEXT DEFAULT ''"),
        ("excluded_event_ranges", "TEXT DEFAULT '[]'"),
        ("exit_mode", "TEXT DEFAULT 'active'"),
        ("retired_after_event_id", "INTEGER"),
        ("return_required", "BOOLEAN DEFAULT 0"),
        ("return_reason", "TEXT DEFAULT ''"),
        ("init_step", "TEXT DEFAULT ''"),
        ("story_function", "TEXT DEFAULT ''"),
        ("item_updates", "TEXT DEFAULT '[]'"),
    ]:
        ensure_column("characters", column, definition)
    for column, definition in [
        ("goal", "TEXT"),
        ("obstacle", "TEXT"),
        ("cool_point_type", "TEXT"),
        ("payoff_type", "TEXT"),
        ("growth_reward", "TEXT"),
        ("status_reward", "TEXT"),
        ("cliffhanger", "TEXT"),
        ("entering_characters", "TEXT DEFAULT '[]'"),
        ("exiting_characters", "TEXT DEFAULT '[]'"),
        ("item_updates", "TEXT DEFAULT '[]'"),
        ("event_world_snapshot_update", "TEXT"),
        ("event_foreshadow_updates", "TEXT DEFAULT '[]'"),
        ("event_growth_updates", "TEXT DEFAULT '{}'"),
        ("event_lorebook_updates", "TEXT DEFAULT '{}'"),
    ]:
        ensure_column("events", column, definition)
    for column, definition in [
        ("quality_score", "INTEGER DEFAULT 0"),
        ("quality_issues", "TEXT DEFAULT '[]'"),
        ("rewrite_count", "INTEGER DEFAULT 0"),
        ("cool_point_type", "TEXT DEFAULT ''"),
        ("hook_strength", "INTEGER DEFAULT 0"),
        ("cliffhanger_type", "TEXT DEFAULT ''"),
    ]:
        ensure_column("chapters", column, definition)
    conn.commit()


def get_novel_db_conn(novel_id: str, create_if_missing: bool = False) -> sqlite3.Connection:
    validate_novel_id(novel_id)
    db_path = novel_db_path(novel_id)
    if not create_if_missing and not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Novel not found")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    init_novel_schema(conn)
    return conn


def resolve_novel_id_from_stack() -> Optional[str]:
    frame = inspect.currentframe()
    if frame is None:
        return None
    frame = frame.f_back
    while frame:
        fn_name = frame.f_code.co_name
        if fn_name in SYSTEM_DB_CALLERS:
            return None
        novel_id = frame.f_locals.get("novel_id")
        if isinstance(novel_id, str):
            return novel_id
        req = frame.f_locals.get("req")
        req_novel_id = getattr(req, "novel_id", None)
        if isinstance(req_novel_id, str):
            return req_novel_id
        frame = frame.f_back
    return None


def get_db_conn(novel_id: Optional[str] = None) -> sqlite3.Connection:
    resolved_novel_id = novel_id or resolve_novel_id_from_stack()
    if resolved_novel_id:
        return get_novel_db_conn(resolved_novel_id)
    return get_system_db_conn()


def create_novel_storage(novel_id: str, title: str, synopsis: str, style: str, target_words: int) -> None:
    created_at = datetime.utcnow().isoformat()
    plan = build_story_plan(target_words)
    conn = get_novel_db_conn(novel_id, create_if_missing=True)
    cur = conn.cursor()
    cur.execute("DELETE FROM novels")
    cur.execute(
        "INSERT INTO novels (id, title, synopsis, style, target_words, words_per_event, target_event_count, opening_breakthrough_count, development_end_event_id, foreshadow_active_count, ending_mode, ending_start_event_id, ending_event_count, current_phase, updated_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            novel_id,
            title,
            synopsis,
            style,
            plan["target_words"],
            plan["words_per_event"],
            plan["target_event_count"],
            plan["opening_breakthrough_count"],
            plan["development_end_event_id"],
            0,
            0,
            plan["ending_start_event_id"],
            plan["ending_event_count"],
            "draft",
            created_at,
            created_at,
        ),
    )
    conn.commit()
    conn.close()
    ensure_init_steps(novel_id)
    upsert_novel_index_item(
        {
            "id": novel_id,
            "db_file": os.path.basename(novel_db_path(novel_id)),
            "title": title,
            "synopsis": synopsis,
            "style": style,
            "target_words": plan["target_words"],
            "words_per_event": plan["words_per_event"],
            "target_event_count": plan["target_event_count"],
            "opening_breakthrough_count": plan["opening_breakthrough_count"],
            "development_end_event_id": plan["development_end_event_id"],
            "ending_start_event_id": plan["ending_start_event_id"],
            "ending_event_count": plan["ending_event_count"],
            "foreshadow_active_count": 0,
            "created_at": created_at,
            "updated_at": created_at,
        }
    )


def get_novel_summary(novel_id: str) -> Dict[str, Any]:
    items = {item.get("id"): item for item in load_novel_index()}
    conn = get_novel_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, synopsis, style, target_words, words_per_event, target_event_count, opening_breakthrough_count, development_end_event_id, foreshadow_active_count, ending_mode, ending_start_event_id, ending_event_count, current_phase, updated_at, created_at FROM novels LIMIT 1"
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        base = items.get(novel_id, {})
        return {
            "id": novel_id,
            "title": base.get("title", ""),
            "synopsis": base.get("synopsis", ""),
            "style": base.get("style", ""),
            "target_words": base.get("target_words", 500000),
            "words_per_event": base.get("words_per_event", WORDS_PER_EVENT),
            "target_event_count": base.get("target_event_count", 50),
            "opening_breakthrough_count": base.get("opening_breakthrough_count", 2),
            "development_end_event_id": base.get("development_end_event_id", 10),
            "foreshadow_active_count": base.get("foreshadow_active_count", 0),
            "ending_mode": base.get("ending_mode", 0),
            "ending_start_event_id": base.get("ending_start_event_id"),
            "ending_event_count": base.get("ending_event_count", 10),
            "current_phase": base.get("current_phase", "draft"),
            "updated_at": base.get("updated_at"),
            "created_at": base.get("created_at"),
        }
    return {
        "id": row[0],
        "title": row[1],
        "synopsis": row[2],
        "style": row[3],
        "target_words": row[4],
        "words_per_event": row[5],
        "target_event_count": row[6],
        "opening_breakthrough_count": row[7],
        "development_end_event_id": row[8],
        "foreshadow_active_count": row[9],
        "ending_mode": row[10],
        "ending_start_event_id": row[11],
        "ending_event_count": row[12],
        "current_phase": row[13],
        "updated_at": row[14],
        "created_at": row[15],
    }


def refresh_novel_index_item(novel_id: str) -> None:
    summary = get_novel_summary(novel_id)
    upsert_novel_index_item(
        {
            "id": summary["id"],
            "db_file": os.path.basename(novel_db_path(novel_id)),
            "title": summary.get("title", ""),
            "synopsis": summary.get("synopsis", ""),
            "style": summary.get("style", ""),
            "target_words": summary.get("target_words", 500000),
            "words_per_event": summary.get("words_per_event", WORDS_PER_EVENT),
            "target_event_count": summary.get("target_event_count", 50),
            "opening_breakthrough_count": summary.get("opening_breakthrough_count", 2),
            "development_end_event_id": summary.get("development_end_event_id", 10),
            "ending_start_event_id": summary.get("ending_start_event_id"),
            "ending_event_count": summary.get("ending_event_count", 10),
            "foreshadow_active_count": summary.get("foreshadow_active_count", 0),
            "current_phase": summary.get("current_phase", "draft"),
            "ending_mode": summary.get("ending_mode", 0),
            "created_at": summary.get("created_at"),
            "updated_at": summary.get("updated_at"),
        }
    )


def update_novel_metadata(novel_id: str, title: str, synopsis: str, style: str) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE novels SET title=?, synopsis=?, style=?, updated_at=? WHERE id=?",
            (title.strip(), synopsis.strip(), style.strip(), now, novel_id),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail="小说名已存在") from exc
    finally:
        conn.close()
    refresh_novel_index_item(novel_id)
    return get_novel_summary(novel_id)


def list_novel_summaries() -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    stale_ids: List[str] = []
    items = load_novel_index()
    for item in items:
        novel_id = item.get("id")
        if not isinstance(novel_id, str):
            continue
        if not os.path.exists(novel_db_path(novel_id)):
            stale_ids.append(novel_id)
            continue
        summaries.append(get_novel_summary(novel_id))
    if stale_ids:
        stale_set = set(stale_ids)
        save_novel_index([item for item in items if item.get("id") not in stale_set])
    summaries.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return summaries


def get_story_plan(novel_id: str) -> Dict[str, int]:
    summary = get_novel_summary(novel_id)
    plan = build_story_plan(summary.get("target_words") or 500000, summary.get("words_per_event") or WORDS_PER_EVENT)
    if (
        summary.get("target_event_count") != plan["target_event_count"]
        or summary.get("opening_breakthrough_count") != plan["opening_breakthrough_count"]
        or summary.get("development_end_event_id") != plan["development_end_event_id"]
        or summary.get("ending_start_event_id") != plan["ending_start_event_id"]
        or summary.get("ending_event_count") != plan["ending_event_count"]
    ):
        update_novel_story_plan(novel_id, plan["target_words"])
    return plan


def update_novel_story_plan(novel_id: str, target_words: int) -> Dict[str, int]:
    plan = build_story_plan(target_words)
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "UPDATE novels SET target_words=?, words_per_event=?, target_event_count=?, opening_breakthrough_count=?, development_end_event_id=?, ending_start_event_id=?, ending_event_count=?, updated_at=? WHERE id=?",
        (
            plan["target_words"],
            plan["words_per_event"],
            plan["target_event_count"],
            plan["opening_breakthrough_count"],
            plan["development_end_event_id"],
            plan["ending_start_event_id"],
            plan["ending_event_count"],
            datetime.utcnow().isoformat(),
            novel_id,
        ),
    )
    conn.commit()
    conn.close()
    refresh_novel_index_item(novel_id)
    return plan


def get_event_counts(novel_id: str) -> Dict[str, int]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM events WHERE novel_id=?", (novel_id,))
    total = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM events WHERE novel_id=? AND is_written=1", (novel_id,))
    written = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM events WHERE novel_id=? AND is_written=0 AND is_locked=0", (novel_id,))
    unwritten = int(cur.fetchone()[0] or 0)
    conn.close()
    return {"total": total, "written": written, "unwritten": unwritten}


def get_chapter_count(novel_id: str) -> int:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM chapters WHERE novel_id=?", (novel_id,))
    count = int(cur.fetchone()[0] or 0)
    conn.close()
    return count


def determine_current_story_phase(novel_id: str) -> str:
    counts = get_event_counts(novel_id)
    plan = get_story_plan(novel_id)
    next_event_id = min(counts["written"] + 1, plan["target_event_count"])
    return phase_key_for_event(plan, next_event_id)


def build_story_plan_note(novel_id: str, start_event_id: int, event_count: int) -> str:
    plan = get_story_plan(novel_id)
    end_event_id = min(plan["target_event_count"], start_event_id + max(0, event_count - 1))
    phase_key = phase_key_for_event(plan, start_event_id)
    return (
        f"【系统节奏参数】\n"
        f"目标字数：{plan['target_words']}\n"
        f"总事件数：{plan['target_event_count']}\n"
        f"当前规划事件范围：{start_event_id}-{end_event_id}\n"
        f"当前阶段：{phase_label(phase_key)}\n"
        f"阶段要求：{phase_requirements_text(phase_key)}\n"
        f"开篇破局区间：1-{plan['opening_breakthrough_count']}\n"
        f"发展沉淀区间：{plan['opening_breakthrough_count'] + 1}-{plan['development_end_event_id']}\n"
        f"稳定连载区间：{plan['development_end_event_id'] + 1}-{plan['ending_start_event_id'] - 1}\n"
        f"结局区间：{plan['ending_start_event_id']}-{plan['target_event_count']}"
    )


def get_auto_extend_count(novel_id: str) -> int:
    plan = get_story_plan(novel_id)
    counts = get_event_counts(novel_id)
    total = counts["total"]
    if total >= plan["target_event_count"]:
        return 0
    if total < plan["opening_breakthrough_count"]:
        return max(1, min(3, plan["opening_breakthrough_count"] - total))
    remaining_before_ending = (plan["ending_start_event_id"] - ENDING_RESERVED_CHAPTERS) - total
    if total < plan["ending_start_event_id"] and remaining_before_ending <= 0:
        # We are at the boundary where the next event will enter the ending phase.
        # Allow auto-extension to generate ending events instead of getting stuck.
        return min(5, plan["target_event_count"] - total)
    if total < plan["ending_start_event_id"]:
        return min(5, remaining_before_ending)
    return min(5, plan["target_event_count"] - total)


def sync_novel_phase(novel_id: str) -> str:
    phase_key = determine_current_story_phase(novel_id)
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("UPDATE novels SET current_phase=?, ending_mode=?, updated_at=? WHERE id=?", (phase_key, 1 if phase_key == "ending" else 0, datetime.utcnow().isoformat(), novel_id))
    conn.commit()
    conn.close()
    refresh_novel_index_item(novel_id)
    return phase_key


def save_init_material(novel_id: str, material_key: str, content: str, conn: Optional[sqlite3.Connection] = None) -> None:
    own_conn = conn is None
    conn = conn or get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO init_materials (novel_id, material_key, content, updated_at) VALUES (?, ?, ?, ?)",
        (novel_id, material_key, content, datetime.utcnow().isoformat()),
    )
    if own_conn:
        conn.commit()
        conn.close()


def load_init_material(novel_id: str, material_key: str) -> str:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT content FROM init_materials WHERE novel_id=? AND material_key=? LIMIT 1", (novel_id, material_key))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else ""


def delete_init_material(novel_id: str, material_key: str) -> None:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("DELETE FROM init_materials WHERE novel_id=? AND material_key=?", (novel_id, material_key))
    conn.commit()
    conn.close()


def record_event_run(novel_id: str, event_id: int, status: str, reason: str = "", job_id: str = "") -> None:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO event_runs (novel_id, event_id, job_id, status, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (novel_id, event_id, job_id, status, reason, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def fetch_latest_event_runs(novel_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, event_id, status, reason, job_id, created_at FROM event_runs WHERE novel_id=? ORDER BY id DESC LIMIT ?",
        (novel_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "event_id": row[1],
            "status": row[2],
            "reason": row[3],
            "job_id": row[4],
            "created_at": row[5],
        }
        for row in rows
    ]


def _json_load_text(raw_value: Any, fallback: Any) -> Any:
    if raw_value in (None, ""):
        return fallback
    if isinstance(raw_value, type(fallback)):
        return raw_value
    if not isinstance(raw_value, str):
        return fallback
    try:
        parsed = json.loads(raw_value)
    except Exception:
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def _select_rows_as_dicts(conn: sqlite3.Connection, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(sql, params)
    columns = [item[0] for item in (cur.description or [])]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def build_event_state_snapshot(novel_id: str, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    own_conn = conn is None
    conn = conn or get_db_conn(novel_id)
    try:
        novel_rows = _select_rows_as_dicts(
            conn,
            "SELECT id, title, synopsis, style, target_words, words_per_event, target_event_count, opening_breakthrough_count, development_end_event_id, foreshadow_active_count, ending_mode, ending_start_event_id, ending_event_count, current_phase, updated_at, created_at FROM novels LIMIT 1",
        )
        worldview_rows = _select_rows_as_dicts(
            conn,
            "SELECT content, updated_at FROM worldview WHERE novel_id=? LIMIT 1",
            (novel_id,),
        )
        init_rows = _select_rows_as_dicts(
            conn,
            "SELECT material_key, content, updated_at FROM init_materials WHERE novel_id=? AND material_key IN ('world_snapshot_current', 'worldview_summary') ORDER BY material_key ASC",
            (novel_id,),
        )
        growth_rows = _select_rows_as_dicts(
            conn,
            "SELECT protagonist_name, final_goal, current_stage, stage_summary, power_system_level, power_system_notes, wealth_resources, special_resources, influence_assets, current_bottleneck, next_milestone, updated_at FROM protagonist_progression WHERE novel_id=? LIMIT 1",
            (novel_id,),
        )
        character_rows = _select_rows_as_dicts(
            conn,
            "SELECT name, role_tier, target, motive, secret, relationship, catchphrase, growth_arc, strengths, flaws, behavior_logic, has_sublimation_point, sublimation_type, sublimation_seed, sublimation_trigger, sublimation_payoff, sublimation_status, state, scope_type, planned_event_scope_text, planned_event_ranges, excluded_event_scope_text, excluded_event_ranges, exit_mode, retired_after_event_id, return_required, return_reason, story_function, item_updates, is_locked, is_user_edited, source FROM characters WHERE novel_id=? ORDER BY name ASC",
            (novel_id,),
        )
        for item in character_rows:
            item["strengths"] = parse_string_list(item.get("strengths"))
            item["flaws"] = parse_string_list(item.get("flaws"))
            item["planned_event_ranges"] = _json_load_text(item.get("planned_event_ranges"), [])
            item["excluded_event_ranges"] = _json_load_text(item.get("excluded_event_ranges"), [])
            item["item_updates"] = _json_load_text(item.get("item_updates"), [])
        lorebook_rows = _select_rows_as_dicts(
            conn,
            "SELECT name, type, description, location, related_characters, source_event_id, last_update, is_locked, is_user_edited, source FROM lorebook WHERE novel_id=? ORDER BY name ASC",
            (novel_id,),
        )
        for item in lorebook_rows:
            item["related_characters"] = _json_load_text(item.get("related_characters"), [])
        foreshadow_rows = _select_rows_as_dicts(
            conn,
            "SELECT description, introduced_event_id, expected_payoff_event_id, actual_payoff_event_id, status, importance_level, related_characters, notes, source, created_at, updated_at FROM foreshadows WHERE novel_id=? ORDER BY introduced_event_id ASC, id ASC",
            (novel_id,),
        )
        for item in foreshadow_rows:
            item["related_characters"] = _json_load_text(item.get("related_characters"), [])
        event_rows = _select_rows_as_dicts(
            conn,
            "SELECT event_id, COALESCE(actual_summary, outline_description, description) AS summary, is_written, status FROM events WHERE novel_id=? ORDER BY event_id ASC",
            (novel_id,),
        )
        world_snapshot_current = ""
        worldview_summary = ""
        for item in init_rows:
            if item.get("material_key") == "world_snapshot_current":
                world_snapshot_current = item.get("content") or ""
            elif item.get("material_key") == "worldview_summary":
                worldview_summary = item.get("content") or ""
        written_events = [row for row in event_rows if int(row.get("is_written") or 0) == 1]
        return {
            "novel": novel_rows[0] if novel_rows else {"id": novel_id},
            "worldview": worldview_rows[0] if worldview_rows else {"content": "", "updated_at": None},
            "world_snapshot_current": world_snapshot_current,
            "worldview_summary": worldview_summary,
            "growth_system": growth_rows[0] if growth_rows else {},
            "characters": character_rows,
            "lorebook": lorebook_rows,
            "foreshadows": foreshadow_rows,
            "written_event_summaries": written_events,
            "counts": {
                "total_events": len(event_rows),
                "written_events": len(written_events),
                "open_foreshadows": sum(1 for item in foreshadow_rows if str(item.get("status") or "") != "paid_off"),
                "characters": len(character_rows),
                "lorebook": len(lorebook_rows),
            },
        }
    finally:
        if own_conn:
            conn.close()


def save_event_checkpoint(
    novel_id: str,
    event_id: int,
    checkpoint_type: str,
    payload: Any,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    own_conn = conn is None
    conn = conn or get_db_conn(novel_id)
    now = datetime.utcnow().isoformat()
    payload_text = json.dumps(payload, ensure_ascii=False, indent=2) if not isinstance(payload, str) else payload
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO event_checkpoints (novel_id, event_id, checkpoint_type, payload_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(novel_id, event_id, checkpoint_type) DO UPDATE SET
            payload_json=excluded.payload_json,
            updated_at=excluded.updated_at
        """,
        (novel_id, int(event_id), checkpoint_type, payload_text, now, now),
    )
    if own_conn:
        conn.commit()
        conn.close()


def load_event_checkpoint(novel_id: str, event_id: int, checkpoint_type: str) -> Optional[Dict[str, Any]]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT payload_json, created_at, updated_at FROM event_checkpoints WHERE novel_id=? AND event_id=? AND checkpoint_type=? LIMIT 1",
        (novel_id, int(event_id), checkpoint_type),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    payload_json = row[0] or "{}"
    try:
        payload = json.loads(payload_json)
    except Exception:
        payload = {"raw": payload_json}
    return {
        "checkpoint_type": checkpoint_type,
        "payload": payload,
        "created_at": row[1],
        "updated_at": row[2],
    }


def list_event_checkpoints(novel_id: str, event_id: int) -> List[Dict[str, Any]]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT checkpoint_type, created_at, updated_at, LENGTH(payload_json) FROM event_checkpoints WHERE novel_id=? AND event_id=? ORDER BY checkpoint_type ASC",
        (novel_id, int(event_id)),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "checkpoint_type": row[0],
            "created_at": row[1],
            "updated_at": row[2],
            "payload_length": int(row[3] or 0),
        }
        for row in rows
    ]


def save_event_generation_artifact(
    novel_id: str,
    event_id: int,
    stage: str,
    *,
    part_name: str = "",
    meta: Optional[Dict[str, Any]] = None,
    system_prompt: str = "",
    user_prompt: str = "",
    response_text: str = "",
    error_text: str = "",
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    own_conn = conn is None
    conn = conn or get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO event_generation_artifacts (novel_id, event_id, stage, part_name, meta_json, system_prompt, user_prompt, response_text, error_text, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            novel_id,
            int(event_id),
            stage,
            part_name,
            json.dumps(meta or {}, ensure_ascii=False),
            system_prompt,
            user_prompt,
            response_text,
            error_text,
            datetime.utcnow().isoformat(),
        ),
    )
    if own_conn:
        conn.commit()
        conn.close()


def fetch_event_generation_artifacts(novel_id: str, event_id: int) -> List[Dict[str, Any]]:
    conn = get_db_conn(novel_id)
    rows = _select_rows_as_dicts(
        conn,
        "SELECT id, stage, part_name, meta_json, system_prompt, user_prompt, response_text, error_text, created_at FROM event_generation_artifacts WHERE novel_id=? AND event_id=? ORDER BY id ASC",
        (novel_id, int(event_id)),
    )
    conn.close()
    for item in rows:
        item["meta"] = _json_load_text(item.pop("meta_json", "{}"), {})
    return rows


def fetch_chapters_for_event(novel_id: str, event_id: int) -> List[Dict[str, Any]]:
    conn = get_db_conn(novel_id)
    rows = _select_rows_as_dicts(
        conn,
        "SELECT chapter_num, title, summary, content, quality_score, quality_issues, rewrite_count, cool_point_type, hook_strength, cliffhanger_type, status, is_locked, is_user_edited, updated_at FROM chapters WHERE novel_id=? AND source_event_id=? ORDER BY chapter_num ASC",
        (novel_id, int(event_id)),
    )
    conn.close()
    for item in rows:
        item["quality_issues"] = _json_load_text(item.get("quality_issues"), [])
    return rows


INIT_STEP_KEYS = [
    "world_setting",
    "series_blueprint",
    "growth_system",
    "core_characters",
    "worldview_summary",
    "opening_snapshot",
    "opening_world_planning",
]

INIT_STEP_DEPENDENCIES = {
    "world_setting": ["series_blueprint", "growth_system", "core_characters", "worldview_summary", "opening_snapshot", "opening_world_planning"],
    "series_blueprint": ["growth_system", "core_characters", "worldview_summary", "opening_snapshot", "opening_world_planning"],
    "growth_system": ["core_characters", "worldview_summary", "opening_snapshot", "opening_world_planning"],
    "core_characters": ["worldview_summary", "opening_snapshot", "opening_world_planning"],
    "worldview_summary": ["opening_snapshot", "opening_world_planning"],
    "opening_snapshot": ["opening_world_planning"],
    "opening_world_planning": [],
}


def ensure_init_steps(novel_id: str) -> None:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    for step_key in INIT_STEP_KEYS:
        cur.execute(
            "INSERT OR IGNORE INTO init_steps (novel_id, step_key, state, updated_at) VALUES (?, ?, ?, ?)",
            (novel_id, step_key, "stale", now),
        )
    conn.commit()
    conn.close()


def get_init_steps(novel_id: str) -> Dict[str, str]:
    ensure_init_steps(novel_id)
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT step_key, state FROM init_steps WHERE novel_id=?", (novel_id,))
    rows = cur.fetchall()
    conn.close()
    result = {step: "stale" for step in INIT_STEP_KEYS}
    for step_key, state in rows:
        result[str(step_key)] = str(state or "stale")
    return result


def set_init_step_state(novel_id: str, step_key: str, state: str) -> None:
    ensure_init_steps(novel_id)
    now = datetime.utcnow().isoformat()
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "UPDATE init_steps SET state=?, updated_at=? WHERE novel_id=? AND step_key=?",
        (state, now, novel_id, step_key),
    )
    conn.commit()
    conn.close()


def mark_dependent_init_steps_stale(novel_id: str, step_key: str) -> None:
    ensure_init_steps(novel_id)
    downstream = INIT_STEP_DEPENDENCIES.get(step_key, [])
    if not downstream:
        return
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        f"UPDATE init_steps SET state='stale', updated_at=? WHERE novel_id=? AND step_key IN ({','.join('?' for _ in downstream)}) AND state!='locked'",
        (datetime.utcnow().isoformat(), novel_id, *downstream),
    )
    conn.commit()
    conn.close()


def normalize_story_core(raw_story_core: Any) -> Dict[str, str]:
    data = raw_story_core if isinstance(raw_story_core, dict) else {}
    return {
        "core_conflict": str(data.get("core_conflict", "")).strip(),
        "golden_finger": str(data.get("golden_finger", "")).strip(),
        "short_term_goal": str(data.get("short_term_goal", "")).strip(),
        "mid_term_goal": str(data.get("mid_term_goal", "")).strip(),
        "ultimate_goal": str(data.get("ultimate_goal", "")).strip(),
        "tone_promise": str(data.get("tone_promise", "")).strip(),
    }


def normalize_stage_plan(raw_stage_plan: Any, plan: Dict[str, int]) -> List[Dict[str, Any]]:
    defaults = build_stage_plan_entries(plan)
    raw_items = raw_stage_plan if isinstance(raw_stage_plan, list) else []
    raw_map = {str(item.get("phase")): item for item in raw_items if isinstance(item, dict) and item.get("phase")}
    normalized: List[Dict[str, Any]] = []
    for item in defaults:
        raw_item = raw_map.get(item["phase"], {})
        merged = dict(item)
        if isinstance(raw_item, dict):
            merged["phase_goal"] = str(raw_item.get("phase_goal", item["phase_goal"])).strip()
            merged["phase_requirements"] = [str(v).strip() for v in raw_item.get("phase_requirements", item["phase_requirements"]) if str(v).strip()]
            merged["progress_focus"] = str(raw_item.get("progress_focus", item["progress_focus"])).strip()
            merged["exit_condition"] = str(raw_item.get("exit_condition", item["exit_condition"])).strip()
            merged["growth_goal"] = str(raw_item.get("growth_goal", item.get("growth_goal", ""))).strip()
            merged["power_goal"] = str(raw_item.get("power_goal", item.get("power_goal", ""))).strip()
            merged["resource_goal"] = str(raw_item.get("resource_goal", item.get("resource_goal", ""))).strip()
            merged["influence_goal"] = str(raw_item.get("influence_goal", item.get("influence_goal", ""))).strip()
            merged["growth_bottleneck"] = str(raw_item.get("growth_bottleneck", item.get("growth_bottleneck", ""))).strip()
            merged["growth_milestone"] = str(raw_item.get("growth_milestone", item.get("growth_milestone", ""))).strip()
        else:
            merged["growth_goal"] = str(item.get("growth_goal", "")).strip()
            merged["power_goal"] = str(item.get("power_goal", "")).strip()
            merged["resource_goal"] = str(item.get("resource_goal", "")).strip()
            merged["influence_goal"] = str(item.get("influence_goal", "")).strip()
            merged["growth_bottleneck"] = str(item.get("growth_bottleneck", "")).strip()
            merged["growth_milestone"] = str(item.get("growth_milestone", "")).strip()
        normalized.append(merged)
    return normalized


def normalize_system_plan(raw_system_plan: Any, plan: Dict[str, int]) -> Dict[str, int]:
    _ = raw_system_plan
    return {
        "target_words": plan["target_words"],
        "words_per_event": plan["words_per_event"],
        "target_event_count": plan["target_event_count"],
        "opening_breakthrough_count": plan["opening_breakthrough_count"],
        "development_end_event_id": plan["development_end_event_id"],
        "ending_start_event_id": plan["ending_start_event_id"],
        "ending_event_count": plan["ending_event_count"],
    }


def normalize_series_blueprint(raw_blueprint: Any, plan: Dict[str, int]) -> Dict[str, Any]:
    data = raw_blueprint if isinstance(raw_blueprint, dict) else {}
    story_core = normalize_story_core(data.get("story_core"))
    if "mid_term_goal" not in story_core:
        story_core["mid_term_goal"] = ""
    story_core["mid_term_goal"] = str((data.get("story_core") or {}).get("mid_term_goal", story_core.get("mid_term_goal", ""))).strip()
    return {
        "story_core": story_core,
        "system_plan": normalize_system_plan(data.get("system_plan"), plan),
        "stage_plan": normalize_stage_plan(data.get("stage_plan"), plan),
    }


def extract_growth_plan_from_blueprint(blueprint: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = blueprint if isinstance(blueprint, dict) else {}
    return {
        "story_core_updates": {
            "short_term_goal": str((data.get("story_core") or {}).get("short_term_goal", "")).strip(),
            "mid_term_goal": str((data.get("story_core") or {}).get("mid_term_goal", "")).strip(),
            "ultimate_goal": str((data.get("story_core") or {}).get("ultimate_goal", "")).strip(),
        },
        "stage_growth_plan": [
            {
                "phase": stage.get("phase", ""),
                "phase_label": stage.get("phase_label", ""),
                "start_event_id": stage.get("start_event_id", 0),
                "end_event_id": stage.get("end_event_id", 0),
                "growth_goal": stage.get("growth_goal", ""),
                "power_goal": stage.get("power_goal", ""),
                "resource_goal": stage.get("resource_goal", ""),
                "influence_goal": stage.get("influence_goal", ""),
                "growth_bottleneck": stage.get("growth_bottleneck", ""),
                "growth_milestone": stage.get("growth_milestone", ""),
            }
            for stage in data.get("stage_plan", [])
            if isinstance(stage, dict)
        ],
    }


def merge_growth_plan_into_blueprint(blueprint: Dict[str, Any], growth_payload: Dict[str, Any], plan: Dict[str, int]) -> Dict[str, Any]:
    merged = normalize_series_blueprint(blueprint, plan)
    story_core_updates = growth_payload.get("story_core_updates") if isinstance(growth_payload, dict) else {}
    if isinstance(story_core_updates, dict):
        for key in ("short_term_goal", "mid_term_goal", "ultimate_goal"):
            value = str(story_core_updates.get(key, "")).strip()
            if value:
                merged["story_core"][key] = value
    growth_map = {}
    raw_stage_growth = growth_payload.get("stage_growth_plan") if isinstance(growth_payload, dict) else None
    if isinstance(raw_stage_growth, list):
        for item in raw_stage_growth:
            if isinstance(item, dict) and item.get("phase"):
                growth_map[str(item.get("phase"))] = item
    for stage in merged.get("stage_plan", []):
        raw = growth_map.get(str(stage.get("phase")), {})
        if not isinstance(raw, dict):
            raw = {}
        for key in ("growth_goal", "power_goal", "resource_goal", "influence_goal", "growth_bottleneck", "growth_milestone"):
            stage[key] = str(raw.get(key, stage.get(key, ""))).strip()
    return merged


def build_initial_growth_snapshot_from_blueprint(blueprint: Dict[str, Any], current_phase: Optional[str] = None) -> Dict[str, Any]:
    stages = [item for item in blueprint.get("stage_plan", []) if isinstance(item, dict)]
    if not stages:
        return {}
    target_phase = current_phase or stages[0].get("phase")
    current_stage = next((item for item in stages if item.get("phase") == target_phase), stages[0])
    story_core = blueprint.get("story_core") or {}
    return {
        "protagonist_name": "主角",
        "final_goal": story_core.get("ultimate_goal", ""),
        "current_stage": current_stage.get("phase_label", current_stage.get("phase", "")),
        "stage_summary": current_stage.get("growth_goal", current_stage.get("phase_goal", "")),
        "power_system_level": current_stage.get("power_goal", ""),
        "power_system_notes": current_stage.get("progress_focus", ""),
        "wealth_resources": current_stage.get("resource_goal", ""),
        "special_resources": current_stage.get("resource_goal", ""),
        "influence_assets": current_stage.get("influence_goal", ""),
        "current_bottleneck": current_stage.get("growth_bottleneck", ""),
        "next_milestone": current_stage.get("growth_milestone", current_stage.get("exit_condition", "")),
    }


def save_series_blueprint(blueprint_json: Dict[str, Any], novel_id: str) -> None:
    now = datetime.utcnow().isoformat()
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO series_blueprint (novel_id, content, updated_at) VALUES (?, ?, ?)",
        (novel_id, json.dumps(blueprint_json, ensure_ascii=False, indent=2), now),
    )
    conn.commit()
    conn.close()


def load_series_blueprint(novel_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT content FROM series_blueprint WHERE novel_id=? LIMIT 1", (novel_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return None
    try:
        parsed = json.loads(row[0])
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return normalize_series_blueprint(parsed, get_story_plan(novel_id))


def build_batch_slots_text(plan: Dict[str, int]) -> str:
    lines: List[str] = []
    for item in build_stage_plan_entries(plan):
        lines.append(
            f"- {item['phase_label']} | 事件 {item['start_event_id']}-{item['end_event_id']} | 阶段目标：{item['phase_goal']}"
        )
    return "\n".join(lines)


def build_blueprint_guidance_from_data(blueprint: Optional[Dict[str, Any]], start_event_id: int, end_event_id: int) -> str:
    if not blueprint:
        return ""
    story_core = blueprint.get("story_core") or {}
    system_plan = blueprint.get("system_plan") or {}
    current_stage = None
    for stage in blueprint.get("stage_plan", []):
        if not isinstance(stage, dict):
            continue
        stage_start = int(stage.get("start_event_id", 0) or 0)
        stage_end = int(stage.get("end_event_id", 0) or 0)
        if stage_start <= start_event_id <= stage_end:
            current_stage = stage
            break
    if not current_stage:
        return ""
    remaining = max(0, int(current_stage.get("end_event_id", start_event_id) or start_event_id) - end_event_id)

    sections = [
        "【阶段计划】",
        f"目标字数：{system_plan.get('target_words', '') or '未填写'}",
        f"总事件数：{system_plan.get('target_event_count', '') or '未填写'}",
        f"核心冲突：{story_core.get('core_conflict', '') or '未填写'}",
        f"核心金手指/变故：{story_core.get('golden_finger', '') or '未填写'}",
        f"当前阶段：{current_stage.get('phase_label', '') or '未填写'}",
        f"阶段区间：{current_stage.get('start_event_id', '')}-{current_stage.get('end_event_id', '')}",
        f"当前阶段目标：{current_stage.get('phase_goal', '') or '未填写'}",
        f"阶段要求：{' / '.join(current_stage.get('phase_requirements', [])) or '未填写'}",
        f"当前进度焦点：{current_stage.get('progress_focus', '') or '未填写'}",
        f"阶段退出条件：{current_stage.get('exit_condition', '') or '未填写'}",
        f"距下一阶段剩余事件：{remaining}",
        f"开篇短期目标：{story_core.get('short_term_goal', '') or '未填写'}",
        f"中期阶段目标：{story_core.get('mid_term_goal', '') or '未填写'}",
        f"终极目标：{story_core.get('ultimate_goal', '') or '未填写'}",
    ]
    return "\n".join(sections)


def build_blueprint_guidance(novel_id: str, start_event_id: int, event_count: int) -> str:
    blueprint = load_series_blueprint(novel_id)
    if not blueprint:
        return ""
    end_event_id = max(start_event_id, start_event_id + max(0, event_count - 1))
    return build_blueprint_guidance_from_data(blueprint, start_event_id, end_event_id)


def get_foreshadow_active_count(novel_id: str, conn: Optional[sqlite3.Connection] = None) -> int:
    own_conn = conn is None
    conn = conn or get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM foreshadows WHERE novel_id=? AND status != 'paid_off'", (novel_id,))
    count = int(cur.fetchone()[0] or 0)
    if own_conn:
        conn.close()
    return count


def sync_foreshadow_active_count(novel_id: str, conn: Optional[sqlite3.Connection] = None) -> int:
    own_conn = conn is None
    conn = conn or get_db_conn(novel_id)
    count = get_foreshadow_active_count(novel_id, conn)
    cur = conn.cursor()
    cur.execute("UPDATE novels SET foreshadow_active_count=?, updated_at=? WHERE id=?", (count, datetime.utcnow().isoformat(), novel_id))
    if own_conn:
        conn.commit()
        conn.close()
    return count


def foreshadow_generation_rule(active_count: int, stage: str) -> str:
    max_active = 8
    stage_limit = 6 if stage == "initial" else 3
    remaining = max(0, max_active - active_count)
    allowed_new = min(stage_limit, remaining)
    if stage == "initial":
        stage_label = "本次开篇事件批次"
    else:
        stage_label = "本次续写事件"
    if allowed_new <= 0:
        return (
            f"【伏笔数量约束】当前未回收伏笔数为 {active_count}，已达到系统上限 {max_active}。"
            f"{stage_label}禁止新增新伏笔，foreshadow_plan 必须返回空数组 []，只能推进或回收已有伏笔。"
        )
    return (
        f"【伏笔数量约束】当前未回收伏笔数为 {active_count}。"
        f"{stage_label}最多新增 {allowed_new} 条新伏笔计划；单个事件最多新增 1 条核心伏笔，必要时最多补 1 条次级伏笔。"
        "如果不需要新增，请让 foreshadow_plan 返回 []；已有伏笔应优先推进或回收。"
    )


def list_novel_ids() -> List[str]:
    return [item["id"] for item in list_novel_summaries() if isinstance(item.get("id"), str)]


def cleanup_novel_files(novel_id: str, title: str) -> None:
    safe_title = sanitize_filename(title or novel_id)
    prefixes = [f"{safe_title}_", f"{safe_title}-"]
    for base_dir in (OUTPUT_DIR, ensure_export_dir()):
        if not os.path.exists(base_dir):
            continue
        for name in os.listdir(base_dir):
            if any(name.startswith(prefix) for prefix in prefixes):
                file_path = os.path.join(base_dir, name)
                if os.path.isfile(file_path):
                    os.remove(file_path)


def locate_job_novel_id(job_id: str) -> Optional[str]:
    for novel_id in list_novel_ids():
        conn = get_novel_db_conn(novel_id)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM generation_runs WHERE job_id=? LIMIT 1", (job_id,))
        found = cur.fetchone() is not None
        conn.close()
        if found:
            return novel_id
    return None


def fetch_job_row(job_id: str) -> Optional[Dict[str, Any]]:
    novel_id = locate_job_novel_id(job_id)
    if not novel_id:
        return None
    conn = get_novel_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT job_id, status, run_type, novel_id, progress, step_label, result_json, error_message, cancelled, created_at, updated_at, finished_at FROM generation_runs WHERE job_id=?",
        (job_id,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    cur.execute("SELECT created_at, message FROM generation_logs WHERE job_id=? ORDER BY id ASC", (job_id,))
    log_rows = cur.fetchall()
    conn.close()
    return {
        "job_id": row[0],
        "status": row[1],
        "job_type": row[2],
        "novel_id": row[3],
        "progress": row[4],
        "step_label": row[5],
        "result": json.loads(row[6]) if row[6] else None,
        "error": row[7],
        "cancelled": bool(row[8]),
        "created_at": row[9],
        "updated_at": row[10],
        "finished_at": row[11],
        "logs": [{"ts": r[0], "message": r[1]} for r in log_rows],
    }


def list_all_job_rows() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for novel_id in list_novel_ids():
        conn = get_novel_db_conn(novel_id)
        cur = conn.cursor()
        cur.execute(
            "SELECT job_id, status, run_type, novel_id, progress, step_label, created_at FROM generation_runs ORDER BY created_at DESC"
        )
        rows = cur.fetchall()
        conn.close()
        items.extend(
            {
                "job_id": row[0],
                "status": row[1],
                "job_type": row[2],
                "novel_id": row[3],
                "progress": row[4],
                "step_label": row[5],
                "created_at": row[6],
            }
            for row in rows
        )
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items


def init_db() -> None:
    ensure_json_file(NOVEL_INDEX_FILE, [])
    conn = get_system_db_conn()
    cur = conn.cursor()
    conn.commit()
    conn.close()


def clear_novel(novel_id: str) -> None:
    conn = get_novel_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("DELETE FROM worldview WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM worldview_snapshots WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM init_materials WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM init_steps WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM series_blueprint WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM characters WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM character_state_history WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM lorebook WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM foreshadows WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM events WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM chapters WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM protagonist_progression WHERE novel_id=?", (novel_id,))
    cur.execute("DELETE FROM context_cache")
    cur.execute(
        "UPDATE novels SET foreshadow_active_count=0, ending_mode=0, current_phase='draft', updated_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), novel_id),
    )
    conn.commit()
    conn.close()
    ensure_init_steps(novel_id)


def delete_novel_storage(novel_id: str) -> None:
    summary = get_novel_summary(novel_id)
    cleanup_novel_files(novel_id, summary.get("title", novel_id))
    delete_novel_prompts(novel_id)
    db_path = novel_db_path(novel_id)
    if os.path.exists(db_path):
        os.remove(db_path)


def extract_json(text: str) -> Optional[Any]:
    backticks = "```"
    pattern = rf"{backticks}(?:json)?\s*([\{{\[].*?[\}}\]])\s*{backticks}"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    obj_start = text.find("{")
    array_start = text.find("[")
    start_pos = -1
    if obj_start != -1 and (array_start == -1 or obj_start < array_start):
        start_pos = obj_start
    elif array_start != -1:
        start_pos = array_start

    if start_pos != -1:
        brackets = 1
        end_pos = start_pos + 1
        while end_pos < len(text) and brackets > 0:
            if text[end_pos] in "[{":
                brackets += 1
            elif text[end_pos] in "]}":
                brackets -= 1
            end_pos += 1
        if brackets == 0:
            json_str = text[start_pos:end_pos]
            try:
                return json.loads(json_str)
            except Exception:
                pass
    return None


def parse_json_with_fix(
    client: "OpenAIClient",
    text: str,
    expect: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Any:
    def validate(obj: Any) -> Any:
        if obj is None:
            return None
        if expect == "array" and isinstance(obj, list):
            return obj
        if expect == "object" and isinstance(obj, dict):
            return obj
        return None

    data = validate(extract_json(text))
    if data is not None:
        return data

    type_hint = "JSON数组" if expect == "array" else "JSON对象"
    fix_instructions = [
        f"请将以下内容修复为严格的{type_hint}，只输出JSON，不要任何解释。",
        "如果内容中有非JSON的文字，请全部删除。",
        "如果存在单引号、中文引号、尾随逗号、未加引号的键名，请修复为标准JSON。",
        "如果输出被截断，请尽量补全为有效JSON结构。",
    ]

    for i in range(3):
        fix_prompt = "\n".join(fix_instructions) + "\n内容如下：\n" + f"```\n{text}\n```"
        fixed = client.chat(fix_prompt, meta={**(meta or {}), "step": "json_fix", "attempt": i + 1})
        data = validate(extract_json(fixed))
        if data is not None:
            return data
        text = fixed

    raise ValueError("Failed to parse JSON after fix")


def strip_trailing_json(text: str) -> str:
    if not text:
        return text
    last_brace_start = text.rfind("{")
    if last_brace_start != -1 and '"event_summary_update"' in text[last_brace_start:]:
        text = text[:last_brace_start].rstrip()
    lines = text.rstrip().splitlines()
    while lines and lines[-1].strip() in ("json", "```", "```json"):
        lines.pop()
    return "\n".join(lines).rstrip()


def extract_part_plan(sub_outline: str, part_name: str) -> str:
    if not sub_outline:
        return ""
    normalized = str(sub_outline)
    markers = [
        "上半部分",
        "中半部分",
        "下半部分",
        "第1段",
        "第2段",
        "第3段",
    ]
    idx = normalized.find(part_name)
    if idx == -1:
        return ""
    end_positions = []
    for marker in markers:
        if marker == part_name:
            continue
        marker_idx = normalized.find(marker, idx + len(part_name))
        if marker_idx != -1:
            end_positions.append(marker_idx)
    end_idx = min(end_positions) if end_positions else None
    segment = normalized[idx:end_idx].strip() if end_idx is not None else normalized[idx:].strip()
    return segment


def extract_part_names(sub_outline: str, event_id: int) -> List[str]:
    if not sub_outline:
        return ["第1段"] if event_id <= 3 else ["第1段", "第2段", "第3段"]
    if event_id <= 3:
        return ["第1段"]
    new_markers = [marker for marker in ["第1段", "第2段", "第3段"] if marker in sub_outline]
    if new_markers:
        return new_markers
    old_markers = [marker for marker in ["上半部分", "中半部分", "下半部分"] if marker in sub_outline]
    if old_markers:
        return old_markers
    return ["第1段"]


def extract_event_short_title(sub_outline: str, fallback_desc: str = "") -> str:
    if sub_outline:
        match = re.search(r"事件缩写[：:]\s*(.{2,12})", sub_outline)
        if match:
            value = match.group(1).strip()
            value = re.sub(r"[\r\n\[\]【】]", "", value)
            if 2 <= len(value) <= 10:
                return value
    cleaned = re.sub(r"\s+", "", fallback_desc or "")
    cleaned = re.sub(r"[，。、“”‘’；：,.!！?？\-—_()（）\[\]【】]", "", cleaned)
    return (cleaned[:8] or "无名事件")


def default_prompt_users() -> Dict[str, str]:
    return {
        "prompt1_world_setting": """请根据以下一句话梗概，产出可持续连载的世界设定。

【一句话梗概】
[setting]

输出要求：
1.选择一个已被熟知的世界描述差异性作为世界背景设定，逻辑要自洽，不得胡乱改编。
2. 设定必须服务后续长篇剧情推进，设计多方势力、多维度的冲突框架。
3. 必须给出可被后续事件复用的稳定规则，避免模糊表达。""",
        "prompt2_series_blueprint": """请根据以下材料，生成“阶段计划”。只需要围绕系统给出的节奏参数，为每个阶段写清楚阶段目标、阶段要求、当前进度焦点和退出条件。

【一句话梗概】
[setting]

【世界设定】
[world_setting]

【系统节奏参数】
[system_plan]

硬性要求：
1. 只规划阶段。
2. 阶段计划必须体现字数驱动节奏：开篇破局期做黄金开篇，发展沉淀期持续成长反馈，稳定连载期推进势力与悬念，结局期集中收束。
3. 必须返回严格 JSON 对象，不要解释，不要 markdown。

返回格式如下：
{
  "story_core": {
    "core_conflict": "全书核心冲突",
    "golden_finger": "核心金手指/重大变故",
    "short_term_goal": "开篇短期目标",
    "mid_term_goal": "中期阶段目标",
    "ultimate_goal": "终极目标",
    "tone_promise": "持续连载卖点承诺"
  },
  "stage_plan": [
    {
      "phase": "opening_breakthrough/development/stable_serial/ending",
      "start_event_id": 1,
      "end_event_id": 3,
      "phase_goal": "该阶段目标",
      "phase_requirements": ["该阶段必须做到的事"],
      "progress_focus": "当前阶段最该推进的方向",
      "exit_condition": "何时进入下一阶段"
    }
  ]
}""",
        "prompt3_growth_system": """请根据以下材料，补全阶段计划中的主角成长规划。

【一句话梗概】
[setting]

【世界设定】
[world_setting]

【阶段计划】
[stage_plan]

【系统节奏参数】
[system_plan]

要求：
1. 只补全阶段成长规划，不要改动阶段区间，不要重写整份阶段计划。
2. 每个阶段都必须写清楚：growth_goal、power_goal、resource_goal、influence_goal、growth_bottleneck、growth_milestone。
3. 阶段成长规划必须和阶段计划一致，能够解释开篇、发展、稳定连载、结局四段的升级路线。
4. 必须返回严格 JSON 对象，不要解释。

格式如下：
{
  "story_core_updates": {
    "short_term_goal": "开篇短期目标",
    "mid_term_goal": "中期阶段目标",
    "ultimate_goal": "终极目标"
  },
  "stage_growth_plan": [
    {
      "phase": "opening_breakthrough/development/stable_serial/ending",
      "growth_goal": "该阶段的成长目标",
      "power_goal": "该阶段的能力目标",
      "resource_goal": "该阶段的资源目标",
      "influence_goal": "该阶段的人脉/势力目标",
      "growth_bottleneck": "该阶段的成长瓶颈",
      "growth_milestone": "该阶段完成标志"
    }
  ]
}""",
        "prompt4_core_characters": """请根据世界设定、阶段计划、主角成长规划与系统节奏参数，生成核心人物卡。

【系统节奏参数】
[system_plan]

要求：
1. 需要生成开篇阶段必需角色与会长期影响主线的核心角色，特殊情况系统、金手指需要生成角色卡。不要堆砌路人。
2. 每个人物都必须服务主线推进，并和阶段计划、主角成长目标有关。
3. 必须写清楚该角色的故事职能、目标、动机、行为逻辑与计划事件范围。
4. 必须显式读取【系统节奏参数】的“当前阶段区间”，人物计划事件范围必须落在该区间内；仅主角/全篇核心人物允许跨阶段或标注全篇。
5. 每个角色必须包含 item_updates（角色初始物品/功法/势力/境界等设定），必须绑定角色，不允许 related_characters 为空。
6. 以下字段允许留空，但不要为了填满字段而臆造：secret、catchphrase、growth_arc、sublimation_type、sublimation_seed、sublimation_trigger、sublimation_payoff。
7. 如果没有明确升华线，has_sublimation_point 必须为 false，相关升华字段保持空字符串，sublimation_status 写 none。
8. 必须返回严格 JSON 数组，不要解释。

格式如下：
[{"name": "张三", "role_tier": "protagonist/major_support/support/functional", "target": "目标", "motive": "动机", "secret": "秘密", "relationship": "关系", "catchphrase": "口头禅", "growth_arc": "成长弧", "strengths": ["优点1", "优点2"], "flaws": ["缺点1", "缺点2"], "behavior_logic": "此人做选择时遵循的内在逻辑", "has_sublimation_point": false, "sublimation_type": "", "sublimation_seed": "", "sublimation_trigger": "", "sublimation_payoff": "", "sublimation_status": "none", "state": "初始状态", "scope_type": "full/range/cameo", "planned_event_scope_text": "全篇 或 1-10,12-14", "planned_event_ranges": [{"start_event_id": 1, "end_event_id": 10}], "story_function": "该角色在长线中的作用", "item_updates": [{"name": "xxx", "type": "功法/道具/势力/境界", "description": "简述设定", "location": "所在/归属", "related_characters": ["张三"]}]}]""",
        "prompt5_worldview_summary": """请根据以下材料，生成“世界观摘要”，供后续初始化和事件规划复用。

【一句话梗概】
[setting]

【世界设定】
[world_setting]

【阶段计划】
[stage_plan]

【主角成长规划】
[growth_system]

【核心人物卡】
[core_characters]

要求：
1. 只总结长线稳定不易变化的世界观骨架，不要写当前章节细节。
2. 重点写清世界秩序、关键规则、核心矛盾、主要势力、公开认知与隐藏风险。
3. 不要重复人物卡里的目标、动机、关系，也不要重复阶段计划/成长规划里的阶段目标、成长里程碑。
4. 内容要适合后续事件规划与章节阶段持续引用。
5. 必须返回严格 JSON 对象，不要解释。

格式如下：
{"worldview_summary": "400-900字的结构化摘要"}""",
        "prompt6_opening_snapshot": """请根据以下材料，生成“世界快照”，并同时给出世界级/事件级设定库。

【一句话梗概】
[setting]

【世界设定】
[world_setting]

【阶段计划】
[stage_plan]

【主角成长规划】
[growth_system]

【核心人物卡】
[core_characters]

【世界观摘要】
[worldview_summary]

要求：
1. 只写当前时点真实存在的外部世界局势，不要提前写后续事件结果。
2. 世界快照必须与人物卡、阶段计划、成长规划分工清晰：不要重复人物目标/动机/关系/个人状态，不要重复阶段目标、成长等级、成长瓶颈、下一里程碑。
3. 世界快照只负责描述“此刻世界外部现实”：表层局势、暗流、区域焦点、势力结构、规则压力、资源紧张、即将引爆的外部冲突、短期触发窗口、连续性约束。
4. `public_surface`、`hidden_undercurrent`、`regional_focus`、`power_structure`、`rule_pressure`、`resource_tension` 每项建议 60-180 字。
5. `conflict_seeds`、`continuity_constraints` 必须返回 2-5 条数组；没有变化也要保守填写，不要留空。
6. `world_state_shift` 在首次快照固定写“初始快照”，后续快照写“相对上一版的真实变化”。
7. lorebook 仅包含世界级/事件级设定，不要写人物专属物品；related_characters 允许为空。
8. 必须返回严格 JSON 对象，不要解释，不要 markdown，不要额外字段。

格式如下：
{"opening_snapshot": {"snapshot_title": "当前快照标题", "time_anchor": "当前时间锚点", "public_surface": "普通人可见的表层局势", "hidden_undercurrent": "未公开的暗流与潜在变化", "regional_focus": "当前叙事主要区域与空间焦点", "power_structure": "当前真正起作用的势力结构与控制关系", "rule_pressure": "当前正在生效的规则、限制与代价", "resource_tension": "世界层面的稀缺资源与争夺点", "conflict_seeds": ["已存在的外部冲突种子1", "已存在的外部冲突种子2"], "trigger_window": "未来短期最可能引爆事件的导火索窗口", "world_state_shift": "初始快照", "continuity_constraints": ["后续写作必须持续遵守的世界连续性约束1", "后续写作必须持续遵守的世界连续性约束2"]}, "lorebook": [{"name": "设定名", "type": "势力/规则/地点/资源", "description": "简述设定", "location": "所在/归属", "related_characters": []}]}""",
        "prompt7_opening_world_planning": """请基于以下材料，生成当前批次需要的“事件规划”。

【一句话梗概】
[setting]

【世界观摘要】
[worldview_summary]

【世界快照】
[opening_snapshot]

【世界级设定库（lorebook）】
[world_items]

【阶段计划】
[stage_plan]

【主角成长规划】
[growth_system]

【当前阶段相关人物卡】
[stage_characters]

【系统节奏参数】
[system_plan]

[opening_event_requirements]

硬性要求：
1. 必须以因果链推进。
2. 每个事件都必须推动主线，而不是重复打怪或重复冲突。
3. 人物动机必须稳定，不能为了推进剧情硬拐弯。冲突来自立场、性格和利益的碰撞，不得强行给反派降智。
4. 至少埋入部分可追踪伏笔，后续能够回收。
5. 必须严格服从当前阶段节奏：开篇破局期要做黄金开篇；发展沉淀期要持续出现成长反馈；稳定连载期要有大副本/大势力推进；结局期只允许收束，不得继续发散。
6. 必须服从阶段计划中的当前阶段要求，确保事件推进与当前阶段目标一致。
7. 必须显式读取【系统节奏参数】中的“当前阶段”和“阶段要求”，并让每个事件体现对应节奏。
8. 新人物允许出现，不要压制出场；只需说明人物作用即可。若出现新人物，必须在 linked_characters 中显式列出，供后续补卡。
9. 必须在事件对象中标注 entering_characters 与 exiting_characters，用于标记出场与下线；如果没有则返回空数组。
10. 事件变更（世界/伏笔/成长/设定库）如无变化可不返回或返回空数组/空对象。
11. 必须返回严格 JSON 数组，不要解释，不要 markdown。
12. description 控制在 80-180 字；goal、obstacle、growth_reward、status_reward、cliffhanger 各控制在 20-80 字；cool_point_type 控制在 5-20 字；payoff_type 控制在 10-40 字。
13. 宏观变动绝对主导：事件完成后的世界快照变化、伏笔变化、成长变化、Lorebook 变化必须在本阶段直接敲定；后续正文只能执行，不得擅自改写。
14. payoff_event_id 若在本批次内明确兑现，必须填数字整数；若是长线伏笔或未来未知事件，必须填 null。

每个事件对象必须包含以下字段：
- event_id: 整数，从 1 开始
- description: 该事件的原始剧情大纲，60-120 字
- location: 主要地点
- time_duration: 时间跨度
- core_conflict: 核心冲突
- foreshadowing: 本事件埋下或推进的伏笔，没有则写“无”
- linked_characters: 出场角色名数组
- entering_characters: 本事件首次出场或回归的角色名数组，没有则写 []
- exiting_characters: 本事件后应下线的角色名数组，没有则写 []
- foreshadow_plan: 结构化伏笔计划数组，没有则返回 []。每项必须包含 description, payoff_event_id, payoff_mode, importance。payoff_event_id 若不在当前批次事件内回收则填 null
- world_snapshot_update: 事件完成后的世界快照变化，直接沿用 world_snapshot_update 结构；字段可缺省，缺省表示不变
- foreshadow_updates: 本事件伏笔变更（可不返回），每项包含 description/status/related_characters/notes
- growth_updates: 本事件成长变更（可不返回），直接沿用 growth_updates 结构；字段可缺省，缺省表示不变
- lorebook_updates: 本事件设定库变更（可不返回），格式为 {new_items: [], updated_items: [], removed_items: []}

注意：foreshadow_plan 只能使用字段名 description/payoff_event_id/payoff_mode/importance，禁止输出 seed/payoff_hint/type 等旧字段。
- goal: 本事件主角或核心阵营想达成的直接目标
- obstacle: 当前最主要的阻碍
- cool_point_type: 本事件主要爽点类型，例如打脸/反杀/破局/揭秘/立威
- payoff_type: 本事件爽点如何兑现，例如当场压制/公开揭穿/意外翻盘/阶段升级
- growth_reward: 本事件带来的成长回报
- status_reward: 本事件带来的地位、人际或资源回报
- cliffhanger: 本事件结尾要留下的悬念、危机或诱因
""",
        "prompt_internal_supplement_characters": """请根据世界观摘要、世界快照、阶段计划、系统节奏参数、当前事件大纲和主角成长规划，补充人物卡。

【系统节奏参数】
[system_plan]

要求：
1. 只为当前事件中缺失的人物补卡，不要重复生成已有核心人物。
2. 每个人物都必须与当前事件存在明确关系，并能解释其为何在此时出场。
3. 人物的目标、动机、秘密之间必须彼此一致；relationship 字段请描述其与主角或关键阵营的关系。
4. state 只写当前出场时的即时状态，不要写未来结局。
5. 必须给出该角色的故事职能和计划事件范围；如果后续是否继续出场尚不确定，可以保守填写较短范围。
6. 必须显式读取【系统节奏参数】的“当前阶段区间”，人物计划事件范围必须落在该区间内；仅主角/全篇核心人物允许跨阶段或标注全篇。
7. 每个角色必须包含 item_updates（角色初始物品/功法/势力/境界等设定），必须绑定角色，不允许 related_characters 为空。
8. 以下字段允许留空，但不要为了填满字段而臆造：secret、catchphrase、growth_arc、sublimation_type、sublimation_seed、sublimation_trigger、sublimation_payoff、return_reason。
9. 升华点字段采用保守策略：如果只是埋下后续可能升华的种子，可以 only 填写 has_sublimation_point=true 与 sublimation_seed；若没有明确升华线，has_sublimation_point 必须为 false，相关字段留空，sublimation_status 写 none。
10. 如果事件规划中给出了 exiting_characters，且该人物在本事件后应下线，请使用 exit_mode=retired 与 retired_after_event_id 明确标注，并补充 excluded_event_scope_text/excluded_event_ranges；如果未来必须回归，请设置 return_required=true 并填写 return_reason。
11. planned_event_scope_text 必须使用“全篇”或“1-10,12-14”这种格式；planned_event_ranges、excluded_event_ranges 必须是结构化范围数组。
12. 必须返回严格 JSON 数组，不要解释。

格式如下：
[{"name": "张三", "role_tier": "protagonist/major_support/support/functional", "target": "目标", "motive": "动机", "secret": "", "relationship": "关系", "catchphrase": "", "growth_arc": "", "strengths": ["优点1", "优点2"], "flaws": ["缺点1", "缺点2"], "behavior_logic": "此人做选择时遵循的内在逻辑", "has_sublimation_point": false, "sublimation_type": "", "sublimation_seed": "", "sublimation_trigger": "", "sublimation_payoff": "", "sublimation_status": "none", "state": "当前出场状态", "scope_type": "full/range/cameo", "planned_event_scope_text": "1-10,12-14", "planned_event_ranges": [{"start_event_id": 1, "end_event_id": 10}], "excluded_event_scope_text": "11-11", "excluded_event_ranges": [{"start_event_id": 11, "end_event_id": 11}], "exit_mode": "active/paused/retired", "retired_after_event_id": null, "return_required": false, "return_reason": "", "story_function": "该角色在长线中的作用", "item_updates": [{"name": "xxx", "type": "功法/道具/势力/境界", "description": "简述设定", "location": "所在/归属", "related_characters": ["张三"]}]}]""",
        "prompt11_part_plan": """请只生成 [part_name] 的执行计划，不写正文。

你必须参考以下材料：
[series_note]
[full_outline_str]
[current_wv]
[lorebook_str]
[character_state_block]
[growth_system]
[goal]
[obstacle]
[cool_point_type]
[payoff_type]
[growth_reward]
[status_reward]
[cliffhanger]
[desc]
[foreshadow]

输出要求：
1. 只生成这个分段的执行计划。
2. 明确该分段的目标、情绪走向、关键镜头、冲突升级点。
3. 不得引入未说明的新主线。
4. 如需引入新角色或新设定，必须在计划中显式说明其用途。
5. 如果当前处于结局阶段，必须服从结局阶段要求，不得提前完结。
6. 必须体现爽点的铺垫、兑现和代价，并为结尾钩子留空间。
7. 重要配角的关键行为必须符合其优点、缺点与行为逻辑；只有少数具备升华点的人物可以在合适节点推进升华线，不得人人强行拔高。
8. 直接输出可供写作使用的结构化文本，不要输出 JSON。""",
        "prompt12_part_write": """请根据以下材料撰写 [part_name] 的正文。

人物状态绑定：
[character_state_block]

主角成长体系：
[growth_system]

写作材料：
[plan]

风格：
[novel_style]

注意：
1. Show, Don't Tell；避免总结、解释文字。
2. 不得私自修改已知人物核心状态。
3. 不得无理由新增角色。
4. 不得无故改变世界规则。
5. 重要配角的关键行为必须符合其优点、缺点和行为逻辑。
6. 有少数具备升华点的人物可以在合适情境中推进升华线。
7. 若处于结局阶段，必须服从该阶段职责。""",
        "prompt13_part_reflect": """请在不改变剧情事实的前提下，优化以下正文，并在末尾追加 JSON 回填。

你必须参考以下材料：
[character_state_block]

写作技法硬性规定：
1. 强画面感与五感描写：不要说“局势很紧张”，要写“刀锋贴着他的头皮掠过，斩断了一缕头发，寒意直逼后脑”。
2. 视角限制：紧紧跟随主角（或当前焦点人物）的POV，写他看到的、听到的、心里吐槽的。
3. 爽感放大器：在冲突爆发和主角展现实力时，必须加入周围人的【反应描写】（震惊、恐惧、不可置信），通过配角的反应来衬托主角的强大/神秘。
4. 绝对禁止“说明文式”写作：不要有旁边解释性描述，不要在正文里大段背诵人物状态块或世界设定。设定必须在对话和动作中自然带出。如果某个设定这一段用不到，就彻底假装它不存在！
5. 对话要求：必须为推进剧情而服务，对话要符合人物背景经历性格。
禁止新增原文没有出现的重要设定和剧情转折。
先输出优化后的正文，不要解释。
风格：[novel_style]
正文如下：
[draft]

在正文结束后，必须追加一个 JSON 代码块，格式如下：
```json
{
  "part_summary": "本段剧情精简摘要（80-120字)",
  "character_state_updates": [
    {"name": "角色名", "new_state": "更新后的状态", "sublimation_status": "none/seeded/progressing/completed"}
  ]
}
```
额外要求：
1. part_summary 必须忠于本段实际发生内容。
2. character_state_updates 只写真正发生变化的人物；如果仅更新升华状态，可不写 new_state，但必须写 sublimation_status。
3. 如果本段没有人物变化，请返回空数组："character_state_updates": []""",
        "prompt10_sub_outline": """【一句话梗概】
[setting]

【主角成长体系】
[growth_system]

【连载/结局提示】
[series_note]

【剧情上下文（含前情摘要、最近已完成事件、当前事件、未来事件预告）】
[full_outline_str]
【当前世界局势】
[current_wv]
【核心设置字典（重要物品/功法/势力）】
[lorebook_str]
【事件世界变更】
[event_world_snapshot_update]
【事件伏笔变更】
[event_foreshadow_updates]
【事件成长变更】
[event_growth_updates]
【事件设定库变更】
[event_lorebook_updates]
【本期登场人物及当前状态】
[char_details_str]

【当前撰写核心：事件 [ev_id]】
地点：[location]
时间：[time_duration]
冲突：[conflict]
剧情大纲：[desc]
必须埋下的伏笔：[foreshadow]
- 当前目标：[goal]
- 主要障碍：[obstacle]
- 爽点类型：[cool_point_type]
- 爽点兑现：[payoff_type]
- 成长回报：[growth_reward]
- 地位回报：[status_reward]
- 结尾钩子：[cliffhanger]
[ending_note]

硬性要求：
1. 必须遵守当前人物状态、世界规则、设定库与前情。
2. 必须在分段中落实【事件世界变更/伏笔变更/成长变更/设定库变更】（如有）。
3. 不得无故引入与主线无关的新角色、新设定。
4. 分段数量可根据事件内容自由选择 1-3 段，不强制三段式；但各段之间必须有明确推进关系，不能重复同一冲突。
5. 第 1、2、3 个事件必须各自只分为 1 段，避免开篇被切碎。
6. 如果处于结局阶段，分段必须符合对应阶段职责。
7. 不能在非尾声阶段提前写完全部归宿。
8. 必须围绕当前目标与障碍推进，并明确设计爽点兑现和结尾钩子。
9. 重要配角的关键行为必须符合其优点、缺点与行为逻辑；如某人物具备升华点，只能在合适节点推进，不得强行拔高或人人都有高光。

请先给当前事件生成一个【事件缩写】：
- 长度 5-10 个字
- 要适合做章节名
- 要能概括当前事件核心，不要空泛

然后再为当前【事件 [ev_id]】设计详细的“分段大纲”。
- 可按事件复杂度拆为 1 段、2 段或 3 段。
- 第 1、2、3 个事件必须只输出 1 段。
- 段名请直接写“第1段 / 第2段 / 第3段”。
请按如下格式输出：
事件缩写：xxxxxx
第1段：...
第2段：...
第3段：...
如果不足 3 段，就只输出实际需要的段数。
绝对不要直接开始写正文！""",
    }


def default_prompt_systems() -> Dict[str, str]:
    return {
        "prompt1_world_setting": "你是长篇网文项目的世界设定总策划。你只负责输出可持续连载的世界设定，不得写解释、废话。",
        "prompt2_series_blueprint": "你是长篇网文的阶段计划设计师。你必须严格遵守系统给定的节奏参数和阶段区间，只返回严格 JSON 对象；严格使用系统已经给定的阶段区间，不得擅自修改 start_event_id、end_event_id。",
        "prompt3_growth_system": "你是长篇网文的主角成长规划设计师。你必须让成长路线与阶段计划一致，只返回严格 JSON 对象；你只负责补全阶段成长规划。",
        "prompt4_core_characters": "你是长篇网文的核心人物策划。你必须让人物服务主线与阶段计划，只返回严格 JSON 数组；必须标注故事职能与计划事件范围。",
        "prompt5_worldview_summary": "你是世界观摘要整理器。你必须提炼长期稳定可复用的世界观骨架，只返回严格 JSON 对象。",
        "prompt6_opening_snapshot": "你是世界快照整理器。你必须梳理当前时点的真实局势，只返回严格 JSON 对象。",
        "prompt7_opening_world_planning": "你是长篇网文的事件规划与全局状态调度师。你必须基于当前局势生成事件因果链，并提前敲定每个事件完成后的宏观状态变动（快照、伏笔、成长、世界设定），只返回严格 JSON 数组。",
        "prompt10_sub_outline": "你是剧情执行导演。你必须基于既有设定、人物和上下文规划当前事件，只输出事件缩写与分段大纲；绝对不要直接开始写正文。",
        "prompt11_part_plan": "你是长篇网文的分段执行规划师。你只负责规划当前分段，不写正文，不输出 JSON；不得引入未说明的新主线。",
        "prompt12_part_write": "你是长篇网文的正文作者。你必须严格按计划和设定写当前分段正文，不要擅自改设定；必须遵守人物状态和世界规则。",
        "prompt13_part_reflect": "你是长篇网文的正文优化编辑。你必须在不改变剧情事实的前提下优化正文，并按要求追加 JSON 回填；不得新增原文没有的重要设定和转折。",
        "prompt_internal_supplement_characters": "你是长篇网文的补充人物策划。你只为当前事件缺失的人物补卡，只返回严格 JSON 数组；必须标注故事职能、计划事件范围与是否退场。",
    }


def make_prompt_template(system_prompt: str = "", user_prompt: str = "") -> Dict[str, str]:
    return {"system_prompt": str(system_prompt or ""), "user_prompt": str(user_prompt or "")}


def normalize_prompt_template(value: Any, default_value: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    default_entry = default_value or make_prompt_template()
    default_system = str(default_entry.get("system_prompt", ""))
    default_user = str(default_entry.get("user_prompt", ""))
    if isinstance(value, dict):
        return make_prompt_template(
            value.get("system_prompt", default_system),
            value.get("user_prompt", default_user),
        )
    if isinstance(value, str):
        return make_prompt_template(default_system, value)
    return make_prompt_template(default_system, default_user)


def normalize_prompt_map(raw_prompts: Any, defaults: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, Dict[str, str]]:
    base_defaults = defaults or default_prompts()
    merged: Dict[str, Dict[str, str]] = {key: make_prompt_template(**value) for key, value in base_defaults.items()}
    if not isinstance(raw_prompts, dict):
        return merged
    for key, default_value in base_defaults.items():
        if key in raw_prompts:
            merged[key] = normalize_prompt_template(raw_prompts.get(key), default_value)
    return merged


def default_prompts() -> Dict[str, Dict[str, str]]:
    prompt_users = default_prompt_users()
    prompt_systems = default_prompt_systems()
    return {
        key: make_prompt_template(prompt_systems.get(key, ""), prompt_users.get(key, ""))
        for key in prompt_users.keys()
    }


def get_prompt_template(prompt_set: Dict[str, Any], key: str) -> Dict[str, str]:
    defaults = default_prompts()
    return normalize_prompt_template(prompt_set.get(key), defaults.get(key))


def render_prompt_template_pair(template_value: Any, values: Dict[str, Any]) -> Dict[str, str]:
    entry = normalize_prompt_template(template_value)
    return {
        "system_prompt": render_prompt_template(entry.get("system_prompt", ""), values),
        "user_prompt": render_prompt_template(entry.get("user_prompt", ""), values),
    }


from schemas import ApiConfig

class OpenAIClient:
    def __init__(self, api: ApiConfig):
        self.base_url = api.base_url.rstrip("/")
        self.api_key = api.api_key
        self.model = api.model
        legacy_wire_api = api.wire_api or "chat_completions"
        self.main_api_path = (
            api.main_api_path or ("responses" if legacy_wire_api == "responses" else "chat/completions")
        ).strip() or "chat/completions"
        self.use_stream = bool(api.use_stream)
        self.wire_api = "responses" if self._uses_responses_api() else "chat_completions"
        self.review_model = api.review_model or api.model
        self.model_reasoning_effort = api.model_reasoning_effort or ""
        self.disable_response_storage = bool(api.disable_response_storage)

    def _build_api_url(self, path: str) -> str:
        raw = (path or "").strip()
        if re.match(r"^https?://", raw, re.IGNORECASE):
            return raw.rstrip("/")
        normalized = raw.lstrip("/") or "chat/completions"
        url = self.base_url.rstrip("/")
        if url.endswith("/v1"):
            if normalized.startswith("v1/"):
                normalized = normalized[3:]
            return f"{url}/{normalized}"
        if normalized.startswith("v1/"):
            return f"{url}/{normalized}"
        return f"{url}/v1/{normalized}"

    def _build_chat_url(self) -> str:
        return self._build_api_url("chat/completions")

    def _build_main_url(self) -> str:
        return self._build_api_url(self.main_api_path)

    def _uses_responses_api(self) -> bool:
        path = self.main_api_path.strip()
        if re.match(r"^https?://", path, re.IGNORECASE):
            lowered = path.lower().split("?", 1)[0].rstrip("/")
            return lowered.endswith("/responses")
        normalized = path.lower().lstrip("/")
        return normalized == "responses" or normalized == "v1/responses"

    def _build_request_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
        }

    def _build_chat_payload(self, user_prompt: str, system_prompt: str, temperature: float) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if self.use_stream:
            payload["stream"] = True
        if self.model_reasoning_effort:
            payload["reasoning"] = {"effort": self.model_reasoning_effort}
        return payload

    def _build_responses_url(self) -> str:
        return self._build_api_url("responses")

    def _build_models_url(self) -> str:
        url = self.base_url.rstrip("/")
        if url.endswith("/models"):
            return url
        if url.endswith("/v1"):
            return f"{url}/models"
        return f"{url}/v1/models"

    def _extract_content_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                if isinstance(item, dict):
                    text_value = item.get("text") or item.get("content")
                    if isinstance(text_value, str):
                        parts.append(text_value)
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts)
        return ""

    def _extract_stream_content(self, res: httpx.Response) -> str:
        chunks: List[str] = []
        for raw_line in res.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else raw_line
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if not data_str or data_str == "[DONE]":
                continue
            try:
                data = json.loads(data_str)
            except Exception:
                continue
            choices = data.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            delta_content = self._extract_content_text(delta.get("content"))
            if delta_content:
                chunks.append(delta_content)
                continue
            message = choices[0].get("message") or {}
            message_content = self._extract_content_text(message.get("content"))
            if message_content:
                chunks.append(message_content)
        return "".join(chunks).strip()

    def _extract_response_output(self, data: Dict[str, Any]) -> str:
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        if isinstance(output_text, list):
            combined = self._extract_content_text(output_text)
            if combined.strip():
                return combined.strip()
        output = data.get("output") or []
        parts: List[str] = []
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content") or []
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        text = block.get("text")
                        if isinstance(text, str):
                            parts.append(text)
                            continue
                        if isinstance(text, dict) and isinstance(text.get("value"), str):
                            parts.append(text["value"])
                        elif isinstance(block.get("content"), str):
                            parts.append(block["content"])
        return "".join(parts).strip()

    def _extract_sse_response_output(self, body: str) -> str:
        if not isinstance(body, str) or "event:" not in body:
            return ""

        delta_parts: List[str] = []
        best_text = ""
        event_name = ""
        data_lines: List[str] = []

        def flush_event() -> None:
            nonlocal best_text, event_name, data_lines
            if not event_name and not data_lines:
                return
            data_str = "\n".join(data_lines).strip()
            current_event = event_name
            event_name = ""
            data_lines = []
            if not data_str or data_str == "[DONE]":
                return
            try:
                payload = json.loads(data_str)
            except Exception:
                return

            if current_event == "response.output_text.delta":
                delta = payload.get("delta")
                if isinstance(delta, str):
                    delta_parts.append(delta)
                return

            if current_event == "response.output_text.done":
                text = payload.get("text")
                if isinstance(text, str) and text.strip():
                    best_text = text
                return

            if current_event == "response.content_part.done":
                part = payload.get("part") or {}
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    best_text = text
                elif isinstance(text, dict) and isinstance(text.get("value"), str):
                    best_text = text["value"]
                return

            if current_event == "response.output_item.done":
                item = payload.get("item") or {}
                text = self._extract_response_output({"output": [item]})
                if text:
                    best_text = text
                return

            if current_event == "response.completed":
                response = payload.get("response") or {}
                text = self._extract_response_output(response)
                if text:
                    best_text = text

        for raw_line in body.splitlines():
            line = raw_line.lstrip("\ufeff")
            if not line.strip():
                flush_event()
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                flush_event()
                event_name = line[6:].strip()
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())

        flush_event()
        return best_text.strip() or "".join(delta_parts).strip()

    def _extract_responses_body_output(self, body: str) -> str:
        if not isinstance(body, str) or not body.strip():
            return ""
        try:
            data = json.loads(body)
        except Exception:
            return self._extract_sse_response_output(body)
        if not isinstance(data, dict):
            return ""
        return self._extract_response_output(data)

    def _extract_chat_completions_output(self, body: str) -> str:
        if not isinstance(body, str) or not body.strip():
            return ""
        try:
            data = json.loads(body)
        except Exception:
            data = None
        if isinstance(data, dict):
            choices = data.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                content = self._extract_content_text(message.get("content"))
                if content:
                    return content

        parts: List[str] = []
        for raw_line in body.splitlines():
            line = raw_line.lstrip("\ufeff").strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if not data_str or data_str == "[DONE]":
                continue
            try:
                payload = json.loads(data_str)
            except Exception:
                continue
            choices = payload.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            delta_content = self._extract_content_text(delta.get("content"))
            if delta_content:
                parts.append(delta_content)
                continue
            message = choices[0].get("message") or {}
            message_content = self._extract_content_text(message.get("content"))
            if message_content:
                parts.append(message_content)
        return "".join(parts).strip()

    def _chat_completions(self, user_prompt: str, system_prompt: str, timeout: int, meta: Optional[Dict[str, Any]] = None) -> str:
        url = self._build_main_url()
        request_meta = {**(meta or {}), "resolved_url": url}
        headers = self._build_request_headers()
        payload = self._build_chat_payload(user_prompt, system_prompt or "You are a helpful writing assistant.", 0.8)
        log_api_event("request", json.dumps({"system_prompt": system_prompt, "user_prompt": user_prompt}, ensure_ascii=False), request_meta)
        for attempt in range(5):
            try:
                request_timeout = httpx.Timeout(connect=60.0, read=float(timeout), write=60.0, pool=60.0)
                with httpx.Client(timeout=request_timeout, follow_redirects=True) as client:
                    res = client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    body_text = res.text
                    content = self._extract_chat_completions_output(body_text)
                    if content:
                        log_api_event("response", content, request_meta)
                        return content
                    detail = body_text or "Empty content from upstream response"
                    log_api_event("error", detail, request_meta)
                    raise HTTPException(status_code=500, detail="Empty content from upstream response")
                detail = res.text
                if res.status_code in (502, 503, 504, 524) and attempt < 4:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if "<html" in detail.lower():
                    detail = f"Upstream error {res.status_code}: HTML response from gateway"
                log_api_event("error", detail, request_meta)
                raise HTTPException(status_code=500, detail=format_upstream_error_message(detail))
            except httpx.RequestError as e:
                if attempt < 4:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                log_api_event("error", str(e), request_meta)
                raise HTTPException(status_code=500, detail=str(e))
        raise HTTPException(status_code=500, detail="Upstream error: retries exhausted")

    def _chat_responses(self, user_prompt: str, system_prompt: str, timeout: int, meta: Optional[Dict[str, Any]] = None) -> str:
        url = self._build_main_url()
        request_meta = {**(meta or {}), "resolved_url": url}
        headers = self._build_request_headers()
        payload: Dict[str, Any] = {
            "model": self.model,
            "input": user_prompt,
            "store": not self.disable_response_storage,
        }
        if system_prompt:
            payload["instructions"] = system_prompt
        if self.use_stream:
            payload["stream"] = True
        if self.model_reasoning_effort:
            payload["reasoning"] = {"effort": self.model_reasoning_effort}
        log_api_event("request", json.dumps({"instructions": system_prompt, "input": user_prompt}, ensure_ascii=False), request_meta)
        for attempt in range(5):
            try:
                request_timeout = httpx.Timeout(connect=60.0, read=float(timeout), write=60.0, pool=60.0)
                with httpx.Client(timeout=request_timeout, follow_redirects=True) as client:
                    res = client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    body_text = res.text
                    content = self._extract_responses_body_output(body_text)
                    if content:
                        log_api_event("response", content, request_meta)
                        return content
                    detail = body_text or "Empty content from responses API"
                    log_api_event("error", detail, request_meta)
                    raise HTTPException(status_code=500, detail="Empty content from responses API")
                detail = res.text
                if res.status_code in (502, 503, 504, 524) and attempt < 4:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                log_api_event("error", detail, request_meta)
                raise HTTPException(status_code=500, detail=format_upstream_error_message(detail))
            except httpx.RequestError as e:
                if attempt < 4:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                log_api_event("error", str(e), request_meta)
                raise HTTPException(status_code=500, detail=str(e))
        raise HTTPException(status_code=500, detail="Upstream error: retries exhausted")

    def chat(self, user_prompt: str, system_prompt: str = "", timeout: int = 180, meta: Optional[Dict[str, Any]] = None) -> str:
        if self._uses_responses_api():
            return self._chat_responses(user_prompt, system_prompt, timeout, meta)
        return self._chat_completions(user_prompt, system_prompt, timeout, meta)

    def test_connection(self, timeout: int = 60) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        request_timeout = httpx.Timeout(connect=20.0, read=float(timeout), write=20.0, pool=20.0)
        result: Dict[str, Any] = {
            "wire_api": self.wire_api,
            "main_api_path": self.main_api_path,
            "use_stream": self.use_stream,
            "model": self.model,
            "models_url": self._build_models_url(),
        }
        with httpx.Client(timeout=request_timeout, follow_redirects=True) as client:
            models_res = client.get(result["models_url"], headers=headers)
            result["models_status"] = models_res.status_code
            result["models_ok"] = models_res.status_code == 200
            result["models_body"] = models_res.text[:800]
            if models_res.status_code != 200:
                return result

            prompt = "Reply with exactly: CONNECT_OK"
            if self._uses_responses_api():
                url = self._build_main_url()
                payload: Dict[str, Any] = {
                    "model": self.model,
                    "input": prompt,
                    "store": not self.disable_response_storage,
                }
                if self.use_stream:
                    payload["stream"] = True
                if self.model_reasoning_effort:
                    payload["reasoning"] = {"effort": self.model_reasoning_effort}
                res = client.post(url, headers=headers, json=payload)
                result["chat_url"] = url
                result["chat_status"] = res.status_code
                result["chat_ok"] = res.status_code == 200
                body_text = res.text
                result["chat_body"] = body_text[:1200]
                if res.status_code == 200:
                    result["output_text"] = self._extract_responses_body_output(body_text)
                return result

            url = self._build_main_url()
            payload = self._build_chat_payload(prompt, "You are a helpful assistant.", 0)
            res = client.post(url, headers=headers, json=payload)
            result["chat_url"] = url
            result["chat_status"] = res.status_code
            result["chat_ok"] = res.status_code == 200
            body_text = res.text
            result["chat_body"] = body_text[:1200]
            if res.status_code == 200:
                result["output_text"] = self._extract_chat_completions_output(body_text)
            return result


def log_api_event(event_type: str, content: str, meta: Optional[Dict[str, Any]] = None) -> None:
    ts = datetime.utcnow().isoformat()
    filename = os.path.join(LOG_DIR, f"api_{ts[:10]}.log")
    safe_meta = meta or {}
    entry = {
        "ts": ts,
        "event": event_type,
        "meta": safe_meta,
        "content": content,
    }
    with open(filename, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if event_type in ("response", "error"):
        print(f"[{ts}] {event_type}: {safe_meta} -> {content[:400]}")


def save_events(events_json: List[Dict[str, Any]], novel_id: str) -> int:
    plan = get_story_plan(novel_id)
    conn = get_db_conn()
    cur = conn.cursor()
    count = 0
    for ev in events_json:
        try:
            ev_event_id = int(ev.get("event_id") or 0)
        except Exception:
            ev_event_id = 0
        ending_phase_value = str(ev.get("ending_phase") or "").strip()
        if ending_phase_value not in {"normal", "pre_ending", "climax", "resolution", "epilogue"}:
            ending_phase_value = ""
        if not ending_phase_value:
            ending_phase_value = ending_subphase_for_event_id(plan, ev_event_id)
        outline_description = ev.get("outline_description") or ev.get("description") or ""
        chars = json.dumps(ev.get("linked_characters", []), ensure_ascii=False)
        event_world_snapshot_update = json.dumps(ev.get("world_snapshot_update", {}), ensure_ascii=False)
        event_foreshadow_updates = json.dumps(ev.get("foreshadow_updates", []), ensure_ascii=False)
        event_growth_updates = json.dumps(ev.get("growth_updates", {}), ensure_ascii=False)
        event_lorebook_updates = json.dumps(ev.get("lorebook_updates", {}), ensure_ascii=False)
        cur.execute(
            """
            INSERT INTO events (
                novel_id, event_id, description, outline_description, actual_summary,
                goal, obstacle, cool_point_type, payoff_type, growth_reward, status_reward, cliffhanger,
                ending_phase,
                location, time_duration, core_conflict, foreshadowing, linked_characters,
                event_world_snapshot_update, event_foreshadow_updates, event_growth_updates, event_lorebook_updates,
                entering_characters, exiting_characters,
                is_written, status, is_locked, is_user_edited, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                novel_id,
                ev.get("event_id"),
                outline_description,
                outline_description,
                "",
                ev.get("goal", ""),
                ev.get("obstacle", ""),
                ev.get("cool_point_type", ""),
                ev.get("payoff_type", ""),
                ev.get("growth_reward", ""),
                ev.get("status_reward", ""),
                ev.get("cliffhanger", ""),
                ending_phase_value,
                ev.get("location", "未知地点"),
                ev.get("time_duration", "未知时间"),
                ev.get("core_conflict", "剧情推进"),
                ev.get("foreshadowing", "无特殊伏笔"),
                chars,
                event_world_snapshot_update,
                event_foreshadow_updates,
                event_growth_updates,
                event_lorebook_updates,
                json.dumps(ev.get("entering_characters", []), ensure_ascii=False),
                json.dumps(ev.get("exiting_characters", []), ensure_ascii=False),
                0,
                ev.get("status", "planned"),
                int(bool(ev.get("is_locked", 0))),
                int(bool(ev.get("is_user_edited", 0))),
                ev.get("source", "ai"),
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def normalize_foreshadow_plan(raw_plan: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_plan, list):
        return []
    normalized: List[Dict[str, Any]] = []
    seen = set()
    for item in raw_plan:
        if not isinstance(item, dict):
            continue
        description = str(item.get("description", "")).strip()
        if not description or description in {"无", "暂无", "无特殊伏笔"}:
            continue
        payoff_event_id = item.get("payoff_event_id")
        try:
            payoff_event_id = int(payoff_event_id) if payoff_event_id not in (None, "", "null") else None
        except Exception:
            payoff_event_id = None
        payoff_mode = str(item.get("payoff_mode", "")).strip()
        importance = str(item.get("importance", "medium")).strip().lower() or "medium"
        if importance not in {"high", "medium", "low"}:
            importance = "medium"
        key = (description, payoff_event_id, payoff_mode, importance)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "description": description,
                "payoff_event_id": payoff_event_id,
                "payoff_mode": payoff_mode,
                "importance": importance,
            }
        )
    return normalized


def save_initial_foreshadows(events_json: List[Dict[str, Any]], novel_id: str, allow_text_fallback: bool = True) -> int:
    conn = get_db_conn()
    cur = conn.cursor()
    count = 0
    now = datetime.utcnow().isoformat()
    for ev in events_json:
        related_characters = json.dumps(ev.get("linked_characters", []), ensure_ascii=False)
        foreshadow_plan = normalize_foreshadow_plan(ev.get("foreshadow_plan"))
        if foreshadow_plan:
            for item in foreshadow_plan:
                note_parts = ["初始化大纲计划"]
                if item.get("payoff_mode"):
                    note_parts.append(f"预计回收方式: {item['payoff_mode']}")
                cur.execute(
                    "INSERT INTO foreshadows (novel_id, description, introduced_event_id, expected_payoff_event_id, actual_payoff_event_id, status, importance_level, related_characters, notes, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        novel_id,
                        item["description"],
                        ev.get("event_id"),
                        item.get("payoff_event_id"),
                        None,
                        "open",
                        item.get("importance", "medium"),
                        related_characters,
                        " | ".join(note_parts),
                        "outline_plan",
                        now,
                        now,
                    ),
                )
                count += 1
            continue
        if not allow_text_fallback:
            continue
        foreshadow = str(ev.get("foreshadowing", "")).strip()
        if not foreshadow or foreshadow in {"无", "无特殊伏笔", "暂无"}:
            continue
        cur.execute(
            "INSERT INTO foreshadows (novel_id, description, introduced_event_id, expected_payoff_event_id, actual_payoff_event_id, status, importance_level, related_characters, notes, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                novel_id,
                foreshadow,
                ev.get("event_id"),
                None,
                None,
                "open",
                "medium",
                related_characters,
                "初始化大纲提取（未提供 foreshadow_plan，按文本伏笔保存）",
                "outline_init",
                now,
                now,
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    sync_foreshadow_active_count(novel_id)
    return count


def build_character_seed_lookup(blueprint_json: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    if not blueprint_json:
        return lookup
    for item in blueprint_json.get("character_seed_map", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if name:
            lookup[name] = item
    return lookup


def normalize_character_card(raw_card: Dict[str, Any], plan: Dict[str, int], seed_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    name = str(raw_card.get("name", "")).strip()
    seed = seed_lookup.get(name, {})
    scope_type = str(raw_card.get("scope_type") or seed.get("scope_type") or "range").strip() or "range"
    planned_ranges = normalize_event_ranges(raw_card.get("planned_event_ranges"), plan["target_event_count"])
    planned_scope_text = str(raw_card.get("planned_event_scope_text", "")).strip()
    if not planned_ranges and planned_scope_text:
        planned_ranges = parse_event_scope_text(planned_scope_text, plan["target_event_count"])
    if not planned_ranges:
        planned_ranges = normalize_event_ranges(seed.get("planned_event_ranges"), plan["target_event_count"])
    if not planned_scope_text:
        planned_scope_text = str(seed.get("planned_event_scope_text", "")).strip()
    if scope_type == "full" and not planned_ranges:
        planned_ranges = [{"start_event_id": 1, "end_event_id": plan["target_event_count"]}]
    planned_scope_text = planned_scope_text or format_event_range_text(planned_ranges, plan["target_event_count"], scope_type)
    excluded_ranges = normalize_event_ranges(raw_card.get("excluded_event_ranges"), plan["target_event_count"])
    excluded_scope_text = str(raw_card.get("excluded_event_scope_text", "")).strip()
    if not excluded_ranges and excluded_scope_text:
        excluded_ranges = parse_event_scope_text(excluded_scope_text, plan["target_event_count"])
    excluded_scope_text = excluded_scope_text or format_event_range_text(excluded_ranges, plan["target_event_count"], "range")
    retired_after_raw = raw_card.get("retired_after_event_id")
    try:
        retired_after_event_id = int(retired_after_raw) if retired_after_raw not in (None, "") else None
    except Exception:
        retired_after_event_id = None
    return {
        **raw_card,
        "scope_type": scope_type,
        "planned_event_scope_text": planned_scope_text,
        "planned_event_ranges": planned_ranges,
        "excluded_event_scope_text": excluded_scope_text,
        "excluded_event_ranges": excluded_ranges,
        "exit_mode": str(raw_card.get("exit_mode", "active") or "active").strip(),
        "retired_after_event_id": retired_after_event_id,
        "return_required": bool(raw_card.get("return_required", False)),
        "return_reason": str(raw_card.get("return_reason", "")).strip(),
        "story_function": str(raw_card.get("story_function") or seed.get("story_function") or seed.get("function") or "").strip(),
    }


def save_characters(chars_json: List[Dict[str, Any]], novel_id: str, blueprint_json: Optional[Dict[str, Any]] = None, init_step: str = "") -> int:
    conn = get_db_conn()
    cur = conn.cursor()
    count = 0
    plan = get_story_plan(novel_id)
    seed_lookup = build_character_seed_lookup(blueprint_json)
    for raw_card in chars_json:
        if not isinstance(raw_card, dict):
            continue
        c = normalize_character_card(raw_card, plan, seed_lookup)
        if not str(c.get("name", "")).strip():
            continue
        has_sublimation_point = int(bool(c.get("has_sublimation_point", False)))
        sublimation_status = str(c.get("sublimation_status", "")).strip() or ("seeded" if has_sublimation_point else "none")
        cur.execute(
            """
            INSERT OR REPLACE INTO characters (
                novel_id, name, role_tier, target, motive, secret, relationship, catchphrase, growth_arc,
                strengths, flaws, behavior_logic, has_sublimation_point, sublimation_type,
                sublimation_seed, sublimation_trigger, sublimation_payoff, sublimation_status,
                state, scope_type, planned_event_scope_text, planned_event_ranges, excluded_event_scope_text,
                excluded_event_ranges, exit_mode, retired_after_event_id, return_required, return_reason, init_step, story_function,
                item_updates, is_locked, is_user_edited, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                novel_id,
                c.get("name"),
                c.get("role_tier", "support"),
                c.get("target"),
                c.get("motive"),
                c.get("secret"),
                str(c.get("relationship")),
                c.get("catchphrase"),
                c.get("growth_arc"),
                dump_string_list(c.get("strengths", [])),
                dump_string_list(c.get("flaws", [])),
                c.get("behavior_logic", ""),
                has_sublimation_point,
                c.get("sublimation_type", "") if has_sublimation_point else "",
                c.get("sublimation_seed", "") if has_sublimation_point else "",
                c.get("sublimation_trigger", "") if has_sublimation_point else "",
                c.get("sublimation_payoff", "") if has_sublimation_point else "",
                sublimation_status,
                c.get("state", "初始空"),
                c.get("scope_type", "range"),
                c.get("planned_event_scope_text", ""),
                json.dumps(c.get("planned_event_ranges", []), ensure_ascii=False),
                c.get("excluded_event_scope_text", ""),
                json.dumps(c.get("excluded_event_ranges", []), ensure_ascii=False),
                c.get("exit_mode", "active"),
                c.get("retired_after_event_id"),
                int(bool(c.get("return_required", False))),
                c.get("return_reason", ""),
                init_step or c.get("init_step", ""),
                c.get("story_function", ""),
                json.dumps(c.get("item_updates", []), ensure_ascii=False),
                int(bool(c.get("is_locked", 0))),
                int(bool(c.get("is_user_edited", 0))),
                c.get("source", "ai"),
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def get_character_actual_appearance_map(novel_id: str) -> Dict[str, Dict[str, Any]]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT event_id, linked_characters FROM events WHERE novel_id=? ORDER BY event_id ASC", (novel_id,))
    rows = cur.fetchall()
    conn.close()
    appearances: Dict[str, List[int]] = {}
    for event_id, linked_characters in rows:
        for name in normalize_linked_character_names(linked_characters):
            appearances.setdefault(name, []).append(int(event_id))
    return {
        name: {
            "actual_event_ids": sorted(set(event_ids)),
            "actual_event_scope_text": event_ids_to_scope_text(event_ids),
        }
        for name, event_ids in appearances.items()
    }


def event_in_ranges(event_id: int, ranges: List[Dict[str, int]]) -> bool:
    for item in ranges:
        try:
            start_id = int(item.get("start_event_id", 0) or 0)
            end_id = int(item.get("end_event_id", 0) or 0)
        except Exception:
            continue
        if start_id <= event_id <= end_id:
            return True
    return False


def save_worldview(wv_json: Dict[str, Any], novel_id: str) -> None:
    world_state = wv_json.get("world_state", "")
    if isinstance(world_state, (dict, list)):
        world_state = json.dumps(world_state, ensure_ascii=False, indent=2)
    now = datetime.utcnow().isoformat()
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM worldview WHERE novel_id=?", (novel_id,))
    cur.execute("INSERT INTO worldview (novel_id, content, updated_at) VALUES (?, ?, ?)", (novel_id, world_state, now))
    cur.execute(
        "INSERT INTO worldview_snapshots (novel_id, source_event_id, content, summary, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (novel_id, None, world_state, "初始化世界状态", "outline_init", now),
    )
    conn.commit()
    conn.close()


def load_worldview_content(novel_id: str) -> str:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT content FROM worldview WHERE novel_id=? LIMIT 1", (novel_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else ""


def fetch_world_items(novel_id: str) -> List[Dict[str, Any]]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT name, type, description, location, related_characters FROM lorebook WHERE novel_id=? ORDER BY name ASC",
        (novel_id,),
    )
    rows = cur.fetchall()
    conn.close()
    items: List[Dict[str, Any]] = []
    for name, item_type, description, location, related_chars_raw in rows:
        try:
            related = json.loads(related_chars_raw) if related_chars_raw else []
        except Exception:
            related = []
        items.append(
            {
                "name": name,
                "type": item_type,
                "description": description,
                "location": location,
                "related_characters": related,
            }
        )
    return items


def save_growth_system(growth_json: Dict[str, Any], novel_id: str, conn: Optional[sqlite3.Connection] = None) -> None:
    own_conn = conn is None
    conn = conn or get_db_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT OR REPLACE INTO protagonist_progression (novel_id, protagonist_name, final_goal, current_stage, stage_summary, power_system_level, power_system_notes, wealth_resources, special_resources, influence_assets, current_bottleneck, next_milestone, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            novel_id,
            growth_json.get("protagonist_name", ""),
            growth_json.get("final_goal", ""),
            growth_json.get("current_stage", ""),
            growth_json.get("stage_summary", ""),
            growth_json.get("power_system_level", ""),
            growth_json.get("power_system_notes", ""),
            growth_json.get("wealth_resources", ""),
            growth_json.get("special_resources", ""),
            growth_json.get("influence_assets", ""),
            growth_json.get("current_bottleneck", ""),
            growth_json.get("next_milestone", ""),
            now,
        ),
    )
    if own_conn:
        conn.commit()
        conn.close()


def load_growth_system_json(novel_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "SELECT protagonist_name, final_goal, current_stage, stage_summary, power_system_level, power_system_notes, wealth_resources, special_resources, influence_assets, current_bottleneck, next_milestone, updated_at FROM protagonist_progression WHERE novel_id=? LIMIT 1",
        (novel_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "protagonist_name": row[0],
        "final_goal": row[1],
        "current_stage": row[2],
        "stage_summary": row[3],
        "power_system_level": row[4],
        "power_system_notes": row[5],
        "wealth_resources": row[6],
        "special_resources": row[7],
        "influence_assets": row[8],
        "current_bottleneck": row[9],
        "next_milestone": row[10],
        "updated_at": row[11],
    }


def fetch_growth_system(novel_id: str) -> str:
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT protagonist_name, final_goal, current_stage, stage_summary, power_system_level, power_system_notes, wealth_resources, special_resources, influence_assets, current_bottleneck, next_milestone FROM protagonist_progression WHERE novel_id=? LIMIT 1",
        (novel_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return "（暂无成长体系）"
    return (
        f"主角: {row[0]}\n"
        f"终极目标: {row[1]}\n"
        f"当前阶段: {row[2]}\n"
        f"阶段任务: {row[3]}\n"
        f"能力等级: {row[4]}\n"
        f"能力说明: {row[5]}\n"
        f"财富资源: {row[6]}\n"
        f"特殊资源: {row[7]}\n"
        f"势力人脉: {row[8]}\n"
        f"当前瓶颈: {row[9]}\n"
        f"下一里程碑: {row[10]}"
    )


def upsert_lorebook_items(items_json: List[Dict[str, Any]], novel_id: str, conn: Optional[sqlite3.Connection] = None) -> int:
    own_conn = conn is None
    conn = conn or get_db_conn()
    cur = conn.cursor()
    count = 0
    for item in items_json:
        name = item.get("name")
        if not name:
            continue
        related_chars = json.dumps(item.get("related_characters", []), ensure_ascii=False)
        cur.execute("SELECT is_locked, is_user_edited FROM lorebook WHERE novel_id=? AND name=?", (novel_id, name))
        existing = cur.fetchone()
        if existing and (existing[0] or existing[1]):
            continue
        cur.execute(
            """
            INSERT INTO lorebook (novel_id, name, type, description, location, related_characters, source_event_id, last_update, is_locked, is_user_edited, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(novel_id, name) DO UPDATE SET
                type=excluded.type,
                description=excluded.description,
                location=excluded.location,
                related_characters=excluded.related_characters,
                source_event_id=excluded.source_event_id,
                last_update=excluded.last_update,
                source=excluded.source
            """,
            (
                novel_id,
                name,
                item.get("type", "未知"),
                item.get("description", ""),
                item.get("location", ""),
                related_chars,
                item.get("source_event_id"),
                item.get("last_update", ""),
                int(bool(item.get("is_locked", 0))),
                int(bool(item.get("is_user_edited", 0))),
                item.get("source", "system"),
            ),
        )
        count += 1
    if own_conn:
        conn.commit()
        conn.close()
    return count


def remove_lorebook_items(items_json: List[Dict[str, Any]], novel_id: str, conn: Optional[sqlite3.Connection] = None) -> int:
    own_conn = conn is None
    conn = conn or get_db_conn()
    cur = conn.cursor()
    count = 0
    for item in items_json:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name", "")).strip()
        else:
            continue
        if not name:
            continue
        cur.execute("SELECT is_locked, is_user_edited FROM lorebook WHERE novel_id=? AND name=?", (novel_id, name))
        existing = cur.fetchone()
        if not existing:
            continue
        if existing[0] or existing[1]:
            continue
        cur.execute("DELETE FROM lorebook WHERE novel_id=? AND name=?", (novel_id, name))
        if cur.rowcount > 0:
            count += 1
    if own_conn:
        conn.commit()
        conn.close()
    return count


def get_next_chapter_num(novel_id: str) -> int:
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(chapter_num), 0) FROM chapters WHERE novel_id=?", (novel_id,))
    max_num = cur.fetchone()[0] or 0
    conn.close()
    return int(max_num) + 1


def split_and_save_chapters(text: str, novel_id: str, event_id: int) -> List[str]:
    text = strip_trailing_json(text)
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chapters_to_save: List[str] = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) >= 3000 and len(current) >= 2000:
            current += p + "\n\n"
            chapters_to_save.append(current)
            current = ""
        else:
            current += p + "\n\n"

    if current.strip():
        chapters_to_save.append(current.strip())

    if len(chapters_to_save) > 1 and len(chapters_to_save[-1]) < 2000:
        chapters_to_save[-2] = (chapters_to_save[-2].rstrip() + "\n\n" + chapters_to_save[-1].lstrip()).strip()
        chapters_to_save.pop()

    novel_title = sanitize_filename(get_novel_summary(novel_id).get("title") or novel_id)
    saved_files: List[str] = []
    global_chapter_num = get_next_chapter_num(novel_id)
    for i, chapter_content in enumerate(chapters_to_save):
        suffix = f"_片段{i + 1}" if len(chapters_to_save) > 1 else ""
        filename = f"{novel_title}_第{global_chapter_num}章_事件{event_id}{suffix}.txt"
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"【 第{global_chapter_num}章 】\n")
            f.write(f"—— 事件 {event_id} ——\n\n")
            f.write(chapter_content)
        saved_files.append(filename)
        global_chapter_num += 1
    return saved_files


def split_and_save_chapters_with_titles(text: str, novel_id: str, event_id: int, event_short_title: str) -> List[Dict[str, str]]:
    text = strip_trailing_json(text)
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chapters_to_save: List[str] = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) >= 3000 and len(current) >= 2000:
            current += p + "\n\n"
            chapters_to_save.append(current.strip())
            current = ""
        else:
            current += p + "\n\n"

    if current.strip():
        chapters_to_save.append(current.strip())

    if len(chapters_to_save) > 1 and len(chapters_to_save[-1]) < 2000:
        chapters_to_save[-2] = (chapters_to_save[-2].rstrip() + "\n\n" + chapters_to_save[-1].lstrip()).strip()
        chapters_to_save.pop()

    novel_title = sanitize_filename(get_novel_summary(novel_id).get("title") or novel_id)
    saved_files: List[Dict[str, str]] = []
    global_chapter_num = get_next_chapter_num(novel_id)
    numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    for i, chapter_content in enumerate(chapters_to_save):
        seq = numerals[i] if i < len(numerals) else str(i + 1)
        chapter_title = f"{event_short_title} {seq}"
        filename = f"{novel_title}_第{global_chapter_num}章_{chapter_title}.txt"
        path = os.path.join(OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"第{global_chapter_num}章 {chapter_title}\n\n")
            f.write(chapter_content)
        saved_files.append({
            "filename": filename,
            "chapter_num": str(global_chapter_num),
            "title": chapter_title,
            "content": chapter_content,
        })
        global_chapter_num += 1
    return saved_files


jobs_lock = threading.Lock()
jobs: Dict[str, Dict[str, Any]] = {}


def create_job_record(job_id: str, job_type: str, novel_id: Optional[str]) -> None:
    if not novel_id:
        return
    now = datetime.utcnow().isoformat()
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO generation_runs (job_id, novel_id, run_type, status, progress, step_label, result_json, error_message, cancelled, created_at, updated_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, novel_id, job_type, "running", 0, "", None, None, 0, now, now, None),
    )
    conn.commit()
    conn.close()


def update_job_record(
    job_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    step_label: Optional[str] = None,
    result: Any = None,
    error: Optional[str] = None,
    cancelled: Optional[bool] = None,
    finished: bool = False,
) -> None:
    novel_id = locate_job_novel_id(job_id)
    if not novel_id:
        return
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute("SELECT status, progress, step_label, result_json, error_message, cancelled, created_at FROM generation_runs WHERE job_id=?", (job_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return
    next_status = status if status is not None else row[0]
    next_progress = progress if progress is not None else row[1]
    next_step = step_label if step_label is not None else row[2]
    next_result = json.dumps(result, ensure_ascii=False) if result is not None else row[3]
    next_error = error if error is not None else row[4]
    next_cancelled = int(cancelled) if cancelled is not None else row[5]
    now = datetime.utcnow().isoformat()
    finished_at = now if finished else None
    cur.execute(
        "UPDATE generation_runs SET status=?, progress=?, step_label=?, result_json=?, error_message=?, cancelled=?, updated_at=?, finished_at=COALESCE(?, finished_at) WHERE job_id=?",
        (next_status, next_progress, next_step, next_result, next_error, next_cancelled, now, finished_at, job_id),
    )
    conn.commit()
    conn.close()


def append_job_log_record(job_id: str, message: str, level: str = "info", step: str = "") -> None:
    novel_id = locate_job_novel_id(job_id)
    if not novel_id:
        return
    conn = get_db_conn(novel_id)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO generation_logs (job_id, level, step, message, created_at) VALUES (?, ?, ?, ?, ?)",
        (job_id, level, step, message, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def create_job(job_type: str, novel_id: Optional[str] = None) -> str:
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "status": "running",
            "logs": [],
            "result": None,
            "error": None,
            "job_type": job_type,
            "novel_id": novel_id,
            "progress": 0,
            "step_label": "",
            "cancelled": False,
            "created_at": datetime.utcnow().isoformat(),
        }
    create_job_record(job_id, job_type, novel_id)
    return job_id


def append_job_log(job_id: str, message: str) -> None:
    step_label = ""
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            append_job_log_record(job_id, message, "info", step_label)
            return
        job["logs"].append({"ts": datetime.utcnow().isoformat(), "message": message})
        step_label = job.get("step_label", "")
    append_job_log_record(job_id, message, "info", step_label)


def set_job_progress(job_id: str, progress: int) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job["progress"] = max(0, min(100, progress))
        next_progress = job["progress"]
    update_job_record(job_id, progress=next_progress)


def set_job_step(job_id: str, label: str) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        job["step_label"] = label
    update_job_record(job_id, step_label=label)


def finalize_job(job_id: str, result: Any = None, error: Optional[str] = None) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return
        if job.get("status") == "cancelled":
            return
        job["status"] = "failed" if error else "done"
        job["step_label"] = "完成" if not error else "错误"
        job["result"] = result
        job["error"] = error
        status = job["status"]
        step_label = job["step_label"]
        progress = job.get("progress", 0 if error else 100)
    update_job_record(job_id, status=status, step_label=step_label, progress=progress, result=result, error=error, finished=True)


def cancel_job(job_id: str) -> None:
    found = False
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job["cancelled"] = True
            job["status"] = "cancelled"
            job["step_label"] = "已停止"
            found = True
    update_job_record(job_id, status="cancelled", step_label="已停止", cancelled=True, finished=True)
    if not found:
        append_job_log_record(job_id, "任务已在持久化层标记为停止", "info", "cancel")


def is_job_cancelled(job_id: str) -> bool:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return True
        return bool(job.get("cancelled"))


def load_config() -> Dict[str, Any]:
    default_profiles = {
        "openai_compatible": {
            "profile_name": "OPENAI兼容配置",
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-4o-mini",
            "main_api_path": "chat/completions",
            "use_stream": False,
            "wire_api": "chat_completions",
            "review_model": "",
            "model_provider": "OpenAI",
            "provider_name": "OpenAI",
            "model_reasoning_effort": "",
            "disable_response_storage": False,
            "network_access": "enabled",
            "windows_wsl_setup_acknowledged": True,
            "model_context_window": None,
            "model_auto_compact_token_limit": None,
            "requires_openai_auth": True,
        },
        "codex_cli": {
            "profile_name": "CodexCLI配置",
            "base_url": "http://your-host:8080/v1",
            "api_key": "",
            "model": "gpt-5.4",
            "main_api_path": "chat/completions",
            "use_stream": False,
            "wire_api": "chat_completions",
            "review_model": "gpt-5.4",
            "model_provider": "OpenAI",
            "provider_name": "OpenAI",
            "model_reasoning_effort": "",
            "disable_response_storage": True,
            "network_access": "enabled",
            "windows_wsl_setup_acknowledged": True,
            "model_context_window": 1000000,
            "model_auto_compact_token_limit": 900000,
            "requires_openai_auth": True,
        },
    }
    default_config = {
        "selected_api_profile": "openai_compatible",
        "api_profiles": default_profiles,
        "api": dict(default_profiles["openai_compatible"]),
        "prompts": default_prompts(),
        "default_style": "金庸武侠风格（招式凌厉、气韵苍凉、侠骨柔情）",
        "default_target_words": 500000,
        "default_export_path": EXPORT_DIR,
    }
    if not os.path.exists(CONFIG_FILE):
        return default_config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except Exception:
        return default_config

    if not isinstance(loaded, dict):
        return default_config

    merged = dict(default_config)
    merged.update({k: v for k, v in loaded.items() if k not in {"api", "prompts", "api_profiles"}})

    raw_api_loaded = loaded.get("api")
    api_loaded: Dict[str, Any] = raw_api_loaded if isinstance(raw_api_loaded, dict) else {}
    raw_profiles_loaded = loaded.get("api_profiles")
    profiles_loaded: Dict[str, Any] = raw_profiles_loaded if isinstance(raw_profiles_loaded, dict) else {}
    raw_prompts_loaded = loaded.get("prompts")
    prompts_loaded: Dict[str, Any] = raw_prompts_loaded if isinstance(raw_prompts_loaded, dict) else {}

    merged_profiles: Dict[str, Dict[str, Any]] = {key: dict(value) for key, value in default_profiles.items()}
    for profile_key, profile_value in profiles_loaded.items():
        if not isinstance(profile_value, dict):
            continue
        base = dict(merged_profiles.get(profile_key, {}))
        base.update(profile_value)
        if not base.get("profile_name"):
            base["profile_name"] = profile_key
        merged_profiles[profile_key] = base

    if api_loaded:
        legacy_profile = dict(merged_profiles.get("openai_compatible", {}))
        legacy_profile.update(api_loaded)
        legacy_profile.setdefault("profile_name", "OPENAI兼容配置")
        legacy_profile.setdefault("main_api_path", "chat/completions")
        legacy_profile.setdefault("use_stream", False)
        legacy_profile.setdefault("wire_api", "chat_completions")
        merged_profiles["openai_compatible"] = legacy_profile

    for profile_value in merged_profiles.values():
        profile_value.setdefault(
            "main_api_path",
            "responses" if profile_value.get("wire_api") == "responses" else "chat/completions",
        )
        profile_value.setdefault("use_stream", False)
        if not profile_value.get("wire_api"):
            profile_value["wire_api"] = (
                "responses"
                if str(profile_value.get("main_api_path", "")).strip().lower().endswith("responses")
                else "chat_completions"
            )

    selected_key = str(loaded.get("selected_api_profile") or merged.get("selected_api_profile") or "openai_compatible")
    if selected_key not in merged_profiles:
        selected_key = "openai_compatible"

    merged_api = dict(merged_profiles.get(selected_key, default_profiles["openai_compatible"]))
    merged_prompts = normalize_prompt_map(prompts_loaded, default_config["prompts"])
    merged["selected_api_profile"] = selected_key
    merged["api_profiles"] = merged_profiles
    merged["api"] = merged_api
    merged["prompts"] = merged_prompts
    return merged


def save_config(data: Dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def novel_prompt_file(novel_id: str) -> str:
    return os.path.join(BASE_DIR, f"novel_{validate_novel_id(novel_id)}_prompt.json")


def load_default_prompts() -> Dict[str, Dict[str, str]]:
    data = load_config()
    return normalize_prompt_map(data.get("prompts"), default_prompts())


def get_selected_api_config(config: Dict[str, Any]) -> Dict[str, Any]:
    profiles = config.get("api_profiles") or {}
    selected_key = config.get("selected_api_profile") or "openai_compatible"
    selected = profiles.get(selected_key) or profiles.get("openai_compatible") or config.get("api") or {}
    return dict(selected)


def load_effective_prompts(novel_id: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    defaults = load_default_prompts()
    if not novel_id:
        return defaults
    prompt_file = novel_prompt_file(novel_id)
    if not os.path.exists(prompt_file):
        return defaults
    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except Exception:
        return defaults
    prompts = loaded.get("prompts") if isinstance(loaded, dict) else None
    return normalize_prompt_map(prompts, defaults)


def save_novel_prompts(novel_id: str, prompts: Dict[str, Any]) -> str:
    path = novel_prompt_file(novel_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "novel_id": novel_id,
                "created_at": datetime.utcnow().isoformat(),
                "prompts": prompts,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    return path


def delete_novel_prompts(novel_id: str) -> None:
    path = novel_prompt_file(novel_id)
    if os.path.exists(path):
        os.remove(path)


def backup_prompts(prompts: Dict[str, Any], novel_id: Optional[str] = None) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    prefix = f"prompts_{validate_novel_id(novel_id)}" if novel_id else "prompts_default"
    path = os.path.join(PROMPT_BACKUP_DIR, f"{prefix}_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"prompts": prompts, "created_at": datetime.utcnow().isoformat(), "novel_id": novel_id},
            f,
            ensure_ascii=False,
            indent=2,
        )
    return path


def list_prompt_backups(novel_id: Optional[str] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(PROMPT_BACKUP_DIR), reverse=True):
        if not name.endswith(".json"):
            continue
        path = os.path.join(PROMPT_BACKUP_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        item_novel_id = data.get("novel_id")
        if novel_id is None:
            if item_novel_id is not None:
                continue
        elif item_novel_id != novel_id:
            continue
        items.append(
            {
                "file": name,
                "path": path,
                "created_at": data.get("created_at"),
                "novel_id": item_novel_id,
                "prompt_keys": sorted(list((data.get("prompts") or {}).keys())),
            }
        )
    return items


def load_prompt_backup(file_name: str, novel_id: Optional[str] = None) -> Dict[str, Any]:
    safe_name = os.path.basename(file_name)
    path = os.path.join(PROMPT_BACKUP_DIR, safe_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Backup not found")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    backup_novel_id = data.get("novel_id")
    if backup_novel_id != novel_id:
        raise HTTPException(status_code=400, detail="Backup scope does not match current prompt set")
    prompts = data.get("prompts")
    if not isinstance(prompts, dict):
        raise HTTPException(status_code=400, detail="Invalid backup content")
    return normalize_prompt_map(prompts, load_default_prompts())


def ensure_config_file() -> None:
    data = load_config()
    save_config(data)


def ensure_export_dir() -> str:
    data = load_config()
    export_dir = data.get("default_export_path") or EXPORT_DIR
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def write_csv(path: str, fieldnames: List[str], rows: List[Dict[str, Any]]) -> str:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def write_txt(path: str, content: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "-", name or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "未命名"


def truncate_text(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def parse_string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            items = parsed if isinstance(parsed, list) else re.split(r"[\n,，、;；]+", raw)
        except Exception:
            items = re.split(r"[\n,，、;；]+", raw)
    else:
        return []

    normalized: List[str] = []
    seen = set()
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def dump_string_list(value: Any) -> str:
    return json.dumps(parse_string_list(value), ensure_ascii=False)


def render_prompt_template(template: str, values: Dict[str, Any]) -> str:
    rendered = template
    for key, value in values.items():
        token = str(key)
        replacement = str(value)
        rendered = rendered.replace(f"[{token}]", replacement)
        rendered = rendered.replace(f"【{token}】", replacement)
    return rendered


def render_prompt_messages(template_value: Any, values: Dict[str, Any]) -> Tuple[str, str]:
    rendered = render_prompt_template_pair(template_value, values)
    return rendered.get("system_prompt", ""), rendered.get("user_prompt", "")


def compose_prompt_text(template_value: Any, values: Dict[str, Any]) -> str:
    system_prompt, user_prompt = render_prompt_messages(template_value, values)
    parts = [part.strip() for part in [system_prompt, user_prompt] if str(part).strip()]
    return "\n\n".join(parts)


def recover_stale_jobs() -> None:
    now = datetime.utcnow().isoformat()
    for novel_id in list_novel_ids():
        conn = get_novel_db_conn(novel_id)
        cur = conn.cursor()
        cur.execute(
            "UPDATE generation_runs SET status='failed', step_label='服务重启中断', error_message=COALESCE(error_message, '服务重启，任务中断'), finished_at=COALESCE(finished_at, ?), updated_at=? WHERE status='running'",
            (now, now),
        )
        conn.commit()
        conn.close()


def maybe_extend_outline(
    client: OpenAIClient,
    novel_id: str,
    log_fn,
    job_id: str,
) -> None:
    def job_log(message: str) -> None:
        log_fn(job_id, message)

    counts = get_event_counts(novel_id)
    job_log(f"自动续写检查：未写事件 {counts['unwritten']}，已写事件 {counts['written']}")
    if counts["unwritten"] > 3:
        job_log("自动续写跳过：当前未写事件充足")
        return

    plan = get_story_plan(novel_id)
    extend_count = get_auto_extend_count(novel_id)
    if extend_count <= 0:
        job_log("自动续写跳过：无需追加事件")
        return

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT content FROM worldview WHERE novel_id=? LIMIT 1", (novel_id,))
    wv_row = cur.fetchone()
    current_wv = wv_row[0] if wv_row else "未知"
    growth_system_str = fetch_growth_system(novel_id)

    cur.execute("SELECT name, target, motive, state FROM characters WHERE novel_id=?", (novel_id,))
    chars = cur.fetchall()
    chars_str = "\n".join(
        [f"- {c[0]}: 目标[{c[1]}], 动机[{c[2]}], 当前状态[{c[3]}]" for c in chars]
    )
    existing_char_names = set([c[0] for c in chars])

    cur.execute(
        "SELECT name, type, description, location, related_characters, source_event_id, last_update FROM lorebook WHERE novel_id=?",
        (novel_id,),
    )
    lore_rows = cur.fetchall()
    lore_items = []
    for name, l_type, desc, loc, related_chars, source_event_id, last_update in lore_rows:
        try:
            related_list = json.loads(related_chars) if related_chars else []
        except Exception:
            related_list = []
        rel_str = "、".join(related_list) if related_list else "无"
        lore_items.append(
            f"- {name}（{l_type}）: {desc} | 位置/归属: {loc} | 相关人物: {rel_str} | 来源事件: {source_event_id} | 最近更新: {last_update}"
        )
    lorebook_str = "\n".join(lore_items) if lore_items else "（暂无）"

    cur.execute(
        "SELECT event_id, COALESCE(actual_summary, outline_description, description) FROM events WHERE novel_id=? ORDER BY event_id DESC LIMIT 15",
        (novel_id,),
    )
    recent_events = cur.fetchall()[::-1]
    past_events_str = "\n".join([f"事件 {e[0]}: {e[1]}" for e in recent_events])

    cur.execute("SELECT MAX(event_id) FROM events WHERE novel_id=?", (novel_id,))
    max_id = cur.fetchone()[0] or 0
    conn.close()

    start_event_id = max_id + 1
    end_event_id = min(plan["target_event_count"], max_id + extend_count)
    phase_key = phase_key_for_event(plan, start_event_id)
    phase_note = build_story_plan_note(novel_id, start_event_id, extend_count)
    blueprint_note = build_blueprint_guidance(novel_id, start_event_id, extend_count)
    is_ending = phase_key == "ending"
    ending_rule = (
        "这是结局阶段补事件。禁止新增长期支线与长期新伏笔，必须优先回收核心伏笔，推动终极目标收束。"
        if is_ending
        else "这是非结局阶段补事件。必须维持长线连载张力，不得提前进入大结局。"
    )

    job_log(f"触发自动续写：补充事件 {start_event_id} ~ {end_event_id}（{phase_label(phase_key)}）")

    prompt_extend = f"""【系统指令：长篇小说大纲无缝续写】
你是一个正在连载长篇网文的总策划。当前可写事件即将耗尽，请基于目前局势推演并生成接下来的 {extend_count} 个新剧情事件。

【主角成长体系】
{growth_system_str}

【当前世界局势更新】
{current_wv}

【核心设置字典（重要物品/功法/势力）】
{lorebook_str}

【主要人物当前状态】
{chars_str}

【最近发生的剧情（前情提要）】
{past_events_str}

{phase_note}

{blueprint_note}

请顺着前情提要的脉络，推演并接着生成“事件 {start_event_id}”到“事件 {end_event_id}”的剧情大纲。
要求：
1. 剧情必须连续，符合人物动机和世界观演进逻辑。矛盾要合理升级，并引出新的悬念或篇章。
2. 【极其重要】必须以 JSON 数组返回！每个事件必须包含：event_id, description, location, time_duration, core_conflict, foreshadowing, linked_characters, entering_characters, exiting_characters, foreshadow_plan。
3. 每个事件还必须包含：goal, obstacle, cool_point_type, payoff_type, growth_reward, status_reward, cliffhanger，以及 growth_updates。
4. description 控制在 80-180 字；goal、obstacle、growth_reward、status_reward、cliffhanger 各控制在 20-80 字；cool_point_type 控制在 5-20 字；payoff_type 控制在 10-40 字。
 5. foreshadow_plan 必须是数组，每项包含 description, payoff_event_id, payoff_mode, importance；若暂不准备在本次补充的事件内回收则 payoff_event_id 填 null。
 6. {foreshadow_generation_rule(get_foreshadow_active_count(novel_id), 'extend')}
 7. {ending_rule}
"""
    job_log(f"续写事件 {start_event_id} ~ {end_event_id}：准备请求模型")
    reply = client.chat(prompt_extend, timeout=120, meta={"step": "extend", "prompt": "extend_outline", "novel_id": novel_id})
    job_log(f"续写事件 {start_event_id} ~ {end_event_id}：模型返回，开始解析")
    events_json = parse_json_with_fix(client, reply, "array", meta={"prompt": "extend_outline", "novel_id": novel_id})
    job_log(f"续写事件 {start_event_id} ~ {end_event_id}：解析完成，得到 {len(events_json) if isinstance(events_json, list) else 0} 个事件")
    if events_json:
        phase_order = [phase_key_for_event(plan, start_event_id + idx) for idx in range(len(events_json))]
        if is_ending:
            for ev in events_json:
                try:
                    ev_event_id = int(ev.get("event_id") or 0)
                except Exception:
                    ev_event_id = 0
                if ev_event_id <= 0:
                    ev_event_id = start_event_id
                ev["ending_phase"] = ending_subphase_for_event_id(plan, ev_event_id)
        else:
            for idx, ev in enumerate(events_json):
                ev["ending_phase"] = "normal"
                growth_updates = ev.get("growth_updates") if isinstance(ev.get("growth_updates"), dict) else {}
                if not growth_updates.get("stage_summary"):
                    growth_updates["stage_summary"] = phase_label(phase_order[idx])
                ev["growth_updates"] = growth_updates
        job_log("自动续写：开始保存事件")
        saved = save_events(events_json, novel_id)
        job_log(f"自动续写：事件保存完成，写入 {saved} 个事件")
        saved_foreshadows = save_initial_foreshadows(events_json, novel_id, allow_text_fallback=not is_ending)
        job_log(f"续写保存成功：{saved} 个事件")
        if saved_foreshadows:
            job_log(f"续写伏笔计划保存成功：{saved_foreshadows} 条")

        new_chars = set()
        for ev in events_json:
            for c in ev.get("linked_characters", []):
                new_chars.add(c)
        missing_chars = new_chars - existing_char_names
        if missing_chars:
            job_log(f"检测到新角色：{list(missing_chars)}")
            char_prompt = f"""刚才生成的大纲中出现了新角色：{list(missing_chars)}。
请基于他们在大纲里的作用，为他们生成人物卡。
必须以JSON数组返回，格式: [{{"name": "名字", "target": "目标", "motive": "动机", "secret": "秘密", "relationship": "关系", "catchphrase": "口头禅", "growth_arc": "成长弧", "state": "初登场", "scope_type": "range", "planned_event_scope_text": "例如 21-25", "planned_event_ranges": [{{"start_event_id": {start_event_id}, "end_event_id": {end_event_id}}}], "story_function": "该角色在后续剧情中的功能"}}]"""
            job_log("自动续写：开始补充新角色人物卡")
            reply_chars = client.chat(char_prompt, timeout=90, meta={"step": "extend", "prompt": "extend_characters", "novel_id": novel_id})
            chars_json = parse_json_with_fix(client, reply_chars, "array", meta={"prompt": "extend_characters", "novel_id": novel_id})
            if chars_json:
                save_characters(chars_json, novel_id, load_series_blueprint(novel_id), init_step="supplement_characters")
                job_log("新角色人物卡保存成功")
        else:
            job_log("自动续写：无新增角色需要补卡")
    else:
        job_log("自动续写：模型未返回可保存事件")
