from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from schemas import AppConfig, PromptConfig
from engine import *

router = APIRouter()

@router.get("/api/config")
def api_get_config() -> Dict[str, Any]:
    return load_config()


@router.post("/api/config")
def api_save_config(payload: AppConfig) -> Dict[str, Any]:
    data = load_config()
    current_profiles = data.get("api_profiles") or {}
    if payload.api_profiles:
        data["api_profiles"] = {key: value.model_dump() for key, value in payload.api_profiles.items()}
    elif payload.api:
        merged_profiles = dict(current_profiles)
        merged_profiles["openai_compatible"] = payload.api.model_dump()
        data["api_profiles"] = merged_profiles
    if payload.selected_api_profile:
        data["selected_api_profile"] = payload.selected_api_profile
    elif not data.get("selected_api_profile"):
        data["selected_api_profile"] = "openai_compatible"
    data["api"] = get_selected_api_config(data)
    if payload.default_style:
        data["default_style"] = payload.default_style
    if payload.default_target_words is not None:
        data["default_target_words"] = normalize_target_words(payload.default_target_words)
    if payload.default_export_path:
        data["default_export_path"] = payload.default_export_path
    save_config(data)
    return {"status": "ok"}


@router.post("/api/config/test")
def api_test_config(payload: ApiConfig) -> Dict[str, Any]:
    if not payload.api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    client = OpenAIClient(payload)
    result = client.test_connection()
    result["ok"] = bool(result.get("models_ok") and result.get("chat_ok") and result.get("output_text"))
    return result


@router.get("/api/prompts")
def api_get_prompts(novel_id: Optional[str] = None) -> Dict[str, Any]:
    effective = load_effective_prompts(novel_id)
    return {
        "prompts": effective,
        "scope": "novel" if novel_id and os.path.exists(novel_prompt_file(novel_id)) else "default",
        "novel_id": novel_id,
    }


@router.get("/api/prompts/backups")
def api_prompt_backups(novel_id: Optional[str] = None) -> Dict[str, Any]:
    return {"backups": list_prompt_backups(novel_id), "novel_id": novel_id}


@router.post("/api/prompts")
def api_save_prompts(payload: PromptConfig, novel_id: Optional[str] = None) -> Dict[str, Any]:
    prompt_data = payload.model_dump()
    if novel_id:
        backup_path = backup_prompts(load_effective_prompts(novel_id), novel_id)
        save_novel_prompts(novel_id, prompt_data)
        return {"status": "ok", "backup_path": backup_path, "scope": "novel", "novel_id": novel_id}
    data = load_config()
    backup_path = backup_prompts(data.get("prompts", default_prompts()))
    data["prompts"] = prompt_data
    save_config(data)
    return {"status": "ok", "backup_path": backup_path, "scope": "default"}


@router.post("/api/prompts/reset")
def api_reset_prompts(novel_id: Optional[str] = None) -> Dict[str, Any]:
    if novel_id:
        backup_path = backup_prompts(load_effective_prompts(novel_id), novel_id)
        delete_novel_prompts(novel_id)
        return {
            "status": "ok",
            "prompts": load_default_prompts(),
            "backup_path": backup_path,
            "scope": "novel",
            "novel_id": novel_id,
        }
    data = load_config()
    backup_path = backup_prompts(data.get("prompts", default_prompts()))
    data["prompts"] = default_prompts()
    save_config(data)
    return {"status": "ok", "prompts": data["prompts"], "backup_path": backup_path, "scope": "default"}


@router.post("/api/prompts/reset/{prompt_key}")
def api_reset_single_prompt(prompt_key: str, novel_id: Optional[str] = None) -> Dict[str, Any]:
    defaults = load_default_prompts()
    if prompt_key not in defaults:
        raise HTTPException(status_code=404, detail="Prompt key not found")
    if novel_id:
        current_prompts = load_effective_prompts(novel_id)
        backup_path = backup_prompts(current_prompts, novel_id)
        current_prompts[prompt_key] = defaults[prompt_key]
        if all(current_prompts.get(key, "") == defaults.get(key, "") for key in defaults):
            delete_novel_prompts(novel_id)
        else:
            save_novel_prompts(novel_id, current_prompts)
        return {
            "status": "ok",
            "prompt_key": prompt_key,
            "value": defaults[prompt_key],
            "backup_path": backup_path,
            "scope": "novel",
            "novel_id": novel_id,
        }
    data = load_config()
    current_prompts = data.get("prompts", default_prompts())
    backup_path = backup_prompts(current_prompts)
    current_prompts[prompt_key] = defaults[prompt_key]
    data["prompts"] = current_prompts
    save_config(data)
    return {"status": "ok", "prompt_key": prompt_key, "value": defaults[prompt_key], "backup_path": backup_path, "scope": "default"}


@router.post("/api/prompts/restore")
def api_restore_prompt_backup(payload: Dict[str, Any], novel_id: Optional[str] = None) -> Dict[str, Any]:
    file_name = payload.get("file")
    if not file_name:
        raise HTTPException(status_code=400, detail="Backup file is required")
    restored = load_prompt_backup(str(file_name), novel_id)
    if novel_id:
        backup_path = backup_prompts(load_effective_prompts(novel_id), novel_id)
        save_novel_prompts(novel_id, restored)
        return {"status": "ok", "prompts": restored, "backup_path": backup_path, "scope": "novel", "novel_id": novel_id}
    data = load_config()
    backup_path = backup_prompts(data.get("prompts", default_prompts()))
    data["prompts"] = restored
    save_config(data)
    return {"status": "ok", "prompts": restored, "backup_path": backup_path, "scope": "default"}
