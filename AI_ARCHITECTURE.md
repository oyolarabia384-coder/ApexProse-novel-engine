# AI_ARCHITECTURE

This document is a quick map for future maintenance. It explains how the system is wired, where the critical logic lives, and how to modify it safely.

## 0) Mandatory maintenance rules

Every change must follow this exact sequence:

1. **Read `AI_ARCHITECTURE.md` first** to understand current structure and constraints.
2. **Modify the project** (code, config, docs, assets).
3. **Maintain `AI_ARCHITECTURE.md`** by updating it with any new rules, changed behavior, or new files/entrypoints.

If a change affects architecture, data flow, or key settings, record it here immediately after the change.

## 1) Repository layout

- `backend/` FastAPI service + core logic
- `frontend/` React UI
- `start.py` one-click launcher (creates venv + installs deps + runs both services)
- `log/` API request/response logs (JSONL)
- `exports/` exported data

## 2) Runtime entrypoints

- Backend: `backend/app.py` (FastAPI startup, includes routers)
- Frontend: `frontend/src/main.jsx` -> `frontend/src/App.jsx`
- One-click: `start.py` starts uvicorn on `:8000` and Vite on `:5173`

## 3) Storage model

### 3.1 SQLite databases

- Per novel DB: `backend/data/<novel_id>.sqlite`
- System DB: `backend/data/system.db`

Core tables are created in `backend/engine.py:init_db()`.

Key tables:

- `novels`, `events`, `chapters`, `characters`, `lorebook`, `foreshadows`
- `worldview`, `worldview_snapshots`, `init_materials`, `init_steps`
- `protagonist_progression`
- `generation_runs`, `generation_logs`, `event_runs`
- `event_checkpoints`, `event_generation_artifacts` (added for checkpointed rewrite)

### 3.2 Files

- `backend/novel_index.json`: index of novels
- `backend/config.json`: API profiles + default prompts (contains API keys; do not commit real keys)
- `backend/prompt_backups/`: prompt backups
- `backend/output/`: exported chapter text files

API profile keys in `backend/config.json` are stable:

- `openai_compatible` and `codex_cli` are the canonical keys
- UI display names are:
  - `OPENAI标准配置` (standard)
  - `OPENAI自定义配置` (custom)
- Legacy names are migrated on load in `frontend/src/App.jsx`:
  - `OPENAI兼容配置` -> `OPENAI标准配置`
  - `CodexCLI配置` / `自定义配置` -> `OPENAI自定义配置`

## 4) Backend architecture

### 4.1 Core module: `backend/engine.py`

This file is the heart of the system. Major responsibilities:

- **Config & prompts**
  - `load_config()`, `save_config()`
  - `default_prompts()` / `load_effective_prompts()`
  - prompt backups: `backup_prompts()`

- **Story plan math**
  - `build_story_plan()`: target words -> event counts
  - `phase_key_for_event()` / `phase_label()`
  - **Ending sub-phase distribution**: `ending_subphase_for_event_id()`
    - pre_ending 40%, climax 30%, resolution 20%, epilogue 10%

- **DB helpers**
  - `get_db_conn()`, `get_novel_db_conn()`
  - `save_events()`, `save_characters()`, `save_worldview()`

- **OpenAI-compatible client**
  - `OpenAIClient`: builds `chat/completions` or `responses` payloads
  - `main_api_path` is honored via `_build_main_url()`

- **Jobs** (in-memory + persisted)
  - `jobs` + `jobs_lock`
  - persisted to `generation_runs` + `generation_logs`
  - `recover_stale_jobs()` marks running jobs failed on startup

- **Auto-extend**
  - `maybe_extend_outline()`
  - `get_auto_extend_count()` controls when to add new events

- **Checkpoint system**
  - `event_checkpoints`: generation input/output + post-apply snapshot
  - `event_generation_artifacts`: prompt+response archive
  - `build_event_state_snapshot()`: used to freeze state before generation
  - `save_event_checkpoint()`, `load_event_checkpoint()`

### 4.2 Routes

- **`backend/routes_config.py`**
  - `/api/config`, `/api/config/test`
  - `/api/prompts` CRUD + backups

- **`backend/routes_content.py`**
  - metadata + initialization state
  - manual edits for characters/events
  - import/export endpoints

- **`backend/routes_generation.py`**
  - novel creation
  - initialization steps (`/initialize/{step_name}`)
  - chapter generation (`/api/chapters`)
  - job polling (`/api/jobs`)
  - checkpoint & rewrite:
    - `GET /api/novels/{novel_id}/events/{event_id}/checkpoints`
    - `POST /api/novels/{novel_id}/events/{event_id}/rewrite`

## 5) Initialization pipeline

Sequence (all in `routes_generation.py`):

1. `world_setting`
2. `series_blueprint`
3. `growth_system`
4. `core_characters`
5. `worldview_summary`
6. `opening_snapshot`
7. `opening_world_planning`

Each step is guarded by init-step state and writes to `init_materials`.

Regeneration guards:

- `ensure_can_regenerate_init_outputs()` blocks re-init once chapters exist.

## 6) Chapter generation pipeline

Entry: `POST /api/chapters` -> `routes_generation.py` background thread.

High-level flow per event:

1. `fetch_events()` -> if none, call `maybe_extend_outline()`
2. Build live context with:
   - worldview, lorebook, growth, open foreshadows
   - character cards and event metadata
3. Save **generation_input** checkpoint
4. Generate:
   - `sub_outline` (event short title + part plan)
   - For each part: `part_plan` -> `part_write` -> `part_reflect`
5. Build bundle (full text + character updates + summary)
6. **Apply in one transaction**
   - write chapters
   - apply world/character/foreshadow/growth deltas
   - mark event completed
7. Save **generation_output** and **post_apply_state** checkpoints

If any apply step fails, the transaction is rolled back and the event stays incomplete.

## 7) Event rewrite (checkpoint-based)

Endpoint: `POST /api/novels/{novel_id}/events/{event_id}/rewrite`

Key rules:

- Uses `generation_input` to reconstruct the original input state
- Uses `generation_output` to **lock the event outcome**
- Injects “future completed events” summary to prevent contradictions
- Only rewrites prose and reuses existing chapter numbers
- Does **not** re-run world/character/foreshadow state updates

When you change rewrite behavior:

- `routes_generation.py:api_rewrite_event`
- `generate_event_text_bundle()`
- `split_text_into_fixed_chapter_payloads()`

## 8) Auto-extend behavior

Auto-extend kicks in when no writable events are found.

- `get_auto_extend_count()` decides how many events to add
- `maybe_extend_outline()` writes new events + foreshadows + missing characters
- Ending sub-phases are assigned by `ending_subphase_for_event_id()`

## 9) Frontend architecture

### 9.1 App shell

- `frontend/src/App.jsx` is the single source of state:
  - API config, novel selection, prompt editing, job polling
  - event/character/chapter drawers
  - UI logs (persisted in `localStorage`)
- API profile normalization and migration:
  - `normalizeApiProfileName()` / `normalizeApiProfile()` enforce display names
  - legacy profile names are upgraded on `fetchConfig()`
- OpenAI standard profile enforcement:
  - `saveConfig()` forces `main_api_path=chat/completions`, `use_stream=false`,
    `model_reasoning_effort=""` for `openai_compatible`

### 9.2 Pages

- `ConsolePage.jsx`: dashboard + API config + UI logs
- `ProductionPage.jsx`: generation settings, tasks, records
- `NovelDetailPage.jsx`: world/characters/planning/chapters tabs
- `PromptWorkspace.jsx`: prompt editor & backups

API config UI rules (ConsolePage):

- OpenAI standard mode (`openai_compatible`) disables (not hides) advanced controls
  - Reasoning Effort select, main API path select, stream toggle
  - Disabled wrapper class: `.disabled-setting-item`
  - Hint text: `当前模式下系统自动处理`
- Reasoning Effort options (App state) are:
  - `default`, `none`, `low`, `medium`, `high`, `xhigh`

### 9.3 Drawers

- `EventDrawer.jsx`: event edit + checkpoint view + rewrite trigger
- `CharacterDrawer.jsx`: character edit
- `ChapterDrawer.jsx`: chapter view/edit

### 9.4 Styling

- `frontend/src/styles.css` contains layout rules and fixed-height card patterns
- API config and topbar styles:
  - `.disabled-setting-item` dims and blocks interaction
  - `.topbar-badge-url` truncates long Base URL with ellipsis

## 10) Logging & observability

- `generation_logs`: persisted job logs
- `log/api_YYYY-MM-DD.log`: upstream request/response payloads (JSONL)
- UI logs are local-only in browser storage

## 11) Common change points

### 11.1 Change story rhythm or event math

- `backend/engine.py`:
  - `build_story_plan()`
  - `ending_subphase_for_event_id()`

### 11.2 Change generation prompts or rules

- Prompt templates:
  - `backend/engine.py:default_prompts()`
  - `backend/config.json` (default + per-novel overrides)

### 11.3 Modify chapter generation pipeline

- `backend/routes_generation.py`:
  - `generate_event_text_bundle()`
  - `update_chapter()`
  - `update_world_and_chars()`
  - event apply transaction block in `api_chapters()`

### 11.4 Modify auto-extend

- `backend/engine.py:maybe_extend_outline()`
- `backend/engine.py:get_auto_extend_count()`

### 11.5 Modify event rewrite behavior

- `backend/routes_generation.py:api_rewrite_event()`
- `generate_event_text_bundle()`
- `split_text_into_fixed_chapter_payloads()`

### 11.6 Modify frontend layout

- `frontend/src/styles.css`
- `ConsolePage.jsx`, `ProductionPage.jsx`, `NovelDetailPage.jsx`
- `AppTopbar.jsx` (current API card layout: name/model/base URL)

## 12) Troubleshooting quick guide

- **“生成任务秒结束 / 无事件可写”**
  - Check `events` count vs `target_event_count` and `ending_start_event_id`.
  - Auto-extend is handled in `engine.py:maybe_extend_outline()`.

- **“事件未完成却写后续”**
  - The pipeline now stops on event failure; check logs in `generation_logs`.

- **“重启后任务丢失”**
  - In-memory jobs reset; persisted runs are still in `generation_runs`.
  - `recover_stale_jobs()` marks running jobs as failed on startup.

- **“重写事件逻辑不连续”**
  - Ensure checkpoints exist: `GET /api/novels/{id}/events/{event_id}/checkpoints`.

## 13) Git repository status

This directory currently **has no `.git` folder**, so it is not a git repo. If you need version control here, initialize one at the project root.
