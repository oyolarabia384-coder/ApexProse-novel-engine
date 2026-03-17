from typing import Dict, Optional

from pydantic import BaseModel, Field


class ApiConfig(BaseModel):
    profile_name: Optional[str] = None
    base_url: str
    api_key: str
    model: str
    main_api_path: str = "chat/completions"
    use_stream: bool = False
    wire_api: str = "chat_completions"
    review_model: Optional[str] = None
    model_provider: Optional[str] = None
    provider_name: Optional[str] = None
    model_reasoning_effort: Optional[str] = None
    disable_response_storage: bool = False
    network_access: Optional[str] = None
    windows_wsl_setup_acknowledged: bool = False
    model_context_window: Optional[int] = None
    model_auto_compact_token_limit: Optional[int] = None
    requires_openai_auth: bool = True


class AppConfig(BaseModel):
    api: Optional[ApiConfig] = None
    api_profiles: Optional[Dict[str, ApiConfig]] = None
    selected_api_profile: Optional[str] = None
    default_style: Optional[str] = None
    default_export_path: Optional[str] = None
    default_target_words: Optional[int] = None


class PromptTemplate(BaseModel):
    system_prompt: str = ""
    user_prompt: str = ""


class PromptConfig(BaseModel):
    prompt1_world_setting: PromptTemplate
    prompt2_series_blueprint: PromptTemplate
    prompt3_growth_system: PromptTemplate
    prompt4_core_characters: PromptTemplate
    prompt5_worldview_summary: PromptTemplate
    prompt6_opening_snapshot: PromptTemplate
    prompt7_opening_world_planning: PromptTemplate
    prompt10_sub_outline: PromptTemplate
    prompt11_part_plan: PromptTemplate
    prompt12_part_write: PromptTemplate
    prompt13_part_reflect: PromptTemplate
    prompt_internal_supplement_characters: PromptTemplate


class OutlineRequest(BaseModel):
    api: ApiConfig
    setting: str = Field(max_length=200)
    novel_id: str
    prompt1_world_setting: PromptTemplate
    prompt2_series_blueprint: PromptTemplate
    prompt3_growth_system: PromptTemplate
    prompt4_core_characters: PromptTemplate
    prompt5_worldview_summary: PromptTemplate
    prompt6_opening_snapshot: PromptTemplate
    prompt7_opening_world_planning: PromptTemplate
    prompt_internal_supplement_characters: PromptTemplate


class InitStepRequest(BaseModel):
    api: ApiConfig
    prompt1_world_setting: PromptTemplate
    prompt2_series_blueprint: PromptTemplate
    prompt3_growth_system: PromptTemplate
    prompt4_core_characters: PromptTemplate
    prompt5_worldview_summary: PromptTemplate
    prompt6_opening_snapshot: PromptTemplate
    prompt7_opening_world_planning: PromptTemplate
    prompt_internal_supplement_characters: PromptTemplate


class NovelMetaUpdateRequest(BaseModel):
    title: str
    synopsis: str = Field(max_length=200)
    style: str


class ChapterRequest(BaseModel):
    api: ApiConfig
    novel_id: str
    limit_count: int = 1
    target_words: Optional[int] = None
    novel_style: str = "金庸武侠风格（招式凌厉、气韵苍凉、侠骨柔情）"
    prompt3_growth_system: PromptTemplate
    prompt10_sub_outline: PromptTemplate
    prompt11_part_plan: PromptTemplate
    prompt12_part_write: PromptTemplate
    prompt13_part_reflect: PromptTemplate
    prompt_internal_supplement_characters: PromptTemplate


class EventRewriteRequest(BaseModel):
    api: ApiConfig
    novel_style: str = "金庸武侠风格（招式凌厉、气韵苍凉、侠骨柔情）"
    preserve_chapter_count: bool = True


class NovelCreateRequest(BaseModel):
    title: str
    synopsis: str = Field(max_length=200)
    style: str
    target_words: int = Field(ge=10000)

