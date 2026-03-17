import React, { useMemo, useState } from "react";
import AppSidebar from "./components/AppSidebar";
import ConsolePage from "./components/ConsolePage";
import AppTopbar from "./components/AppTopbar";
import NovelDetailPage from "./components/NovelDetailPage";
import PromptWorkspace from "./components/PromptWorkspace";
import ProductionPage from "./components/ProductionPage";
import CharacterDrawer from "./components/CharacterDrawer";
import EventDrawer from "./components/EventDrawer";
import ChapterDrawer from "./components/ChapterDrawer";

const UI_LOG_STORAGE_KEY = "novel-ui-logs";

const primaryMenuMeta = {
  console: { label: "控制台", children: ["dashboard", "api", "logs"] },
  novels: { label: "小说管理", children: ["create", "detail"] },
  production: { label: "生产管理", children: ["settings", "tasks", "records"] },
  prompts: { label: "提示词", children: ["overview"] },
};

const secondaryMenuLabels = {
  dashboard: "数据看板",
  api: "API 设置",
  logs: "日志记录",
  create: "创建小说（初始化）",
  detail: "小说详情",
  settings: "生产设置",
  tasks: "任务列表",
  records: "生产记录",
  overview: "提示词编辑",
};

const novelDetailTabs = ["world", "characters", "planning", "chapters"];
const novelDetailTabLabels = {
  world: "世界背景",
  characters: "人物",
  planning: "规划与状态",
  chapters: "章节",
};

const promptOrder = [
  "prompt1_world_setting",
  "prompt2_series_blueprint",
  "prompt3_growth_system",
  "prompt4_core_characters",
  "prompt5_worldview_summary",
  "prompt6_opening_snapshot",
  "prompt7_opening_world_planning",
  "prompt_internal_supplement_characters",
  "prompt10_sub_outline",
  "prompt11_part_plan",
  "prompt12_part_write",
  "prompt13_part_reflect",
];

const hiddenPromptKeys = [];
const allPromptKeys = [...promptOrder, ...hiddenPromptKeys];

const promptLabels = {
  prompt1_world_setting: "1. 世界设定",
  prompt2_series_blueprint: "2. 阶段计划",
  prompt3_growth_system: "3. 主角成长规划",
  prompt4_core_characters: "4. 核心人物卡",
  prompt5_worldview_summary: "5. 世界观摘要",
  prompt6_opening_snapshot: "6. 世界快照",
  prompt7_opening_world_planning: "7. 事件规划",
  prompt_internal_supplement_characters: "8. 事件前补卡",
  prompt10_sub_outline: "9. 事件分段大纲",
  prompt11_part_plan: "10. 单段执行计划",
  prompt12_part_write: "11. 单段正文写作",
  prompt13_part_reflect: "12. 正文优化与回填",
};

const promptMeta = {
  prompt1_world_setting: {
    stage: "初始化阶段 / 世界搭建",
    output: "纯文本世界设定稿，约 3000 字",
    variables: ["[setting]"],
  },
  prompt2_series_blueprint: {
    stage: "初始化阶段 / 阶段计划",
    output: "JSON 对象：story_core + stage_plan",
    variables: ["[setting]", "[world_setting]", "[system_plan]"],
  },
  prompt3_growth_system: {
    stage: "初始化阶段 / 主角成长规划",
    output: "JSON 对象：阶段成长规划",
    variables: ["[setting]", "[world_setting]", "[stage_plan]", "[system_plan]"],
  },
  prompt4_core_characters: {
    stage: "初始化阶段 / 核心人物卡",
    output: "JSON 数组：开篇核心人物卡",
    variables: ["[world_setting]", "[stage_plan]", "[growth_system]", "[system_plan]"],
  },
  prompt5_worldview_summary: {
    stage: "初始化阶段 / 世界观摘要",
    output: "JSON 对象：worldview_summary（长期稳定世界骨架，不含人物目标与阶段目标）",
    variables: ["[setting]", "[world_setting]", "[stage_plan]", "[growth_system]", "[core_characters]"],
  },
  prompt6_opening_snapshot: {
    stage: "初始化阶段 / 世界快照",
    output: "JSON 对象：opening_snapshot（12字段：表层局势/暗流/规则压力/资源紧张/触发窗口等）",
    variables: ["[setting]", "[world_setting]", "[stage_plan]", "[growth_system]", "[core_characters]", "[worldview_summary]"],
  },
  prompt7_opening_world_planning: {
    stage: "初始化阶段 / 事件规划",
    output: "JSON 数组：事件对象需包含 entering_characters / exiting_characters",
    variables: [
      "[setting]",
      "[worldview_summary]",
      "[opening_snapshot]",
      "[world_items]",
      "[stage_plan]",
      "[growth_system]",
      "[stage_characters]",
      "[system_plan]",
      "[opening_event_requirements]",
    ],
  },
  prompt_internal_supplement_characters: {
    stage: "章节阶段 / 事件前补卡",
    output: "JSON 数组：补充事件缺失人物卡",
    variables: ["[worldview_summary]", "[world_snapshot]", "[stage_plan]", "[growth_system]", "[system_plan]", "[event_outline]", "[missing_names]"],
  },
  prompt10_sub_outline: {
    stage: "章节阶段 / 事件级规划",
    output: "事件缩写 + 1-3段分段大纲",
    variables: [
      "[series_note]",
      "[full_outline_str]",
      "[current_wv]",
      "[lorebook_str]",
      "[event_world_snapshot_update]",
      "[event_foreshadow_updates]",
      "[event_growth_updates]",
      "[event_lorebook_updates]",
      "[char_details_str]",
      "[ev_id]",
      "[location]",
      "[time_duration]",
      "[conflict]",
      "[desc]",
      "[foreshadow]",
      "[goal]",
      "[obstacle]",
      "[cool_point_type]",
      "[payoff_type]",
      "[growth_reward]",
      "[status_reward]",
      "[cliffhanger]",
      "[ending_note]",
    ],
  },
  prompt11_part_plan: {
    stage: "章节阶段 / 单段执行计划",
    output: "纯文本执行计划",
    variables: [
      "[part_name]",
      "[series_note]",
      "[full_outline_str]",
      "[current_wv]",
      "[lorebook_str]",
      "[character_state_block]",
      "[growth_system]",
      "[goal]",
      "[obstacle]",
      "[cool_point_type]",
      "[payoff_type]",
      "[growth_reward]",
      "[status_reward]",
      "[cliffhanger]",
      "[desc]",
      "[foreshadow]",
    ],
  },
  prompt12_part_write: {
    stage: "章节阶段 / 单段正文写作",
    output: "只返回正文文本",
    variables: ["[part_name]", "[character_state_block]", "[plan]", "[novel_style]"],
  },
  prompt13_part_reflect: {
    stage: "章节阶段 / 正文优化与回填",
    output: "优化后的正文 + JSON 回填（人物状态）",
    variables: ["[draft]", "[novel_style]", "[ev_id]", "[character_state_block]"],
  },
};

const makeEmptyPromptTemplate = () => ({ system_prompt: "", user_prompt: "" });

const normalizePromptTemplate = (value) => {
  if (value && typeof value === "object") {
    return {
      system_prompt: String(value.system_prompt || ""),
      user_prompt: String(value.user_prompt || ""),
    };
  }
  if (typeof value === "string") {
    return { system_prompt: "", user_prompt: value };
  }
  return makeEmptyPromptTemplate();
};

const defaultPrompts = Object.fromEntries(allPromptKeys.map((key) => [key, makeEmptyPromptTemplate()]));

const formatListField = (value) => (Array.isArray(value) ? value.join(" / ") : value || "");
const editListField = (value) => (Array.isArray(value) ? value.join("\n") : value || "");
const parseListField = (value) =>
  String(value || "")
    .split(/[\n,，、;；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
const normalizeJsonArray = (value) => {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const formatJsonEditor = (value) => {
  if (!value) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
};

const normalizeMainApiPath = (value) => {
  const raw = String(value || "chat/completions").trim();
  if (!raw) return "chat/completions";
  const withoutLeadingSlash = raw.replace(/^\/+/, "");
  if (withoutLeadingSlash.toLowerCase().startsWith("v1/")) {
    return withoutLeadingSlash.slice(3) || "chat/completions";
  }
  return withoutLeadingSlash;
};

const mainApiPathOptions = [
  {
    value: "chat/completions",
    label: "/v1/chat/completions",
    description: "请求结构使用 messages；返回结构读取 choices[0].message.content。兼容性最高，最适合小说初始化、章节批量生成和大多数 API 中转站。",
    recommendation: "推荐默认使用这个路径；如果你是在 API 中转站或 OPENAI 兼容站上跑长篇生成，优先选它。",
  },
  {
    value: "responses",
    label: "/v1/responses",
    description: "请求结构使用 input；返回结构读取 output_text 或 output.content.text，并兼容 Responses 的流式事件。",
    recommendation: "只有在上游明确支持 Responses API 时再切换；如果报 404、403 或返回解析异常，改回 /v1/chat/completions。",
  },
];

const serializeApiConfig = (value) => {
  const effort = value.model_reasoning_effort === "default" ? "" : value.model_reasoning_effort || "";
  return {
    profile_name: value.profile_name || "",
    base_url: String(value.base_url || "").trim(),
    api_key: value.api_key || "",
    model: value.model || "",
    main_api_path: normalizeMainApiPath(value.main_api_path),
    use_stream: Boolean(value.use_stream),
    model_reasoning_effort: effort,
  };
};

const normalizeApiProfileName = (key, name) => {
  const raw = String(name || "").trim();
  if (raw === "OPENAI兼容配置") return "OPENAI标准配置";
  if (raw === "CodexCLI配置" || raw === "自定义配置") return "OPENAI自定义配置";
  if (!raw) {
    if (key === "openai_compatible") return "OPENAI标准配置";
    if (key === "codex_cli") return "OPENAI自定义配置";
  }
  return raw;
};

const normalizeApiProfile = (key, value) => ({
  ...value,
  profile_name: normalizeApiProfileName(key, value?.profile_name),
});

const defaultApi = {
  profile_name: "OPENAI标准配置",
  base_url: "https://api.openai.com/v1",
  api_key: "",
  model: "gpt-4o-mini",
  main_api_path: "chat/completions",
  use_stream: false,
  model_reasoning_effort: "",
};

const defaultApiProfiles = {
  openai_compatible: { ...defaultApi },
  codex_cli: {
    profile_name: "OPENAI自定义配置",
    base_url: "http://your-host:8080/v1",
    api_key: "",
    model: "gpt-5.4",
    main_api_path: "chat/completions",
    use_stream: false,
    model_reasoning_effort: "",
  },
};

const reasoningEffortOptions = [
  { value: "default", label: "默认" },
  { value: "none", label: "none" },
  { value: "low", label: "low" },
  { value: "medium", label: "medium" },
  { value: "high", label: "high" },
  { value: "xhigh", label: "xhigh" },
];

const endingPhaseLabels = {
  normal: "普通推进",
  pre_ending: "终局前夜",
  climax: "终局高潮",
  resolution: "高潮收束",
  epilogue: "尾声",
};

const storyPhaseLabels = {
  draft: "草稿",
  outlining: "初始化中",
  outlined: "已初始化",
  opening_breakthrough: "开篇破局期",
  development: "发展沉淀期",
  stable_serial: "稳定连载期",
  ending: "结局期",
};

const initStepLabels = {
  world_setting: "世界设定",
  series_blueprint: "阶段计划",
  growth_system: "成长规划",
  core_characters: "核心人物卡",
  worldview_summary: "世界观摘要",
  opening_snapshot: "世界快照",
  opening_world_planning: "事件规划",
};

const initStepStateLabels = {
  latest: "最新",
  stale: "过期",
  locked: "锁定",
};

const styleOptions = [
  "金庸武侠风格（招式凌厉、气韵苍凉、侠骨柔情）",
  "冷峻悬疑风格（克制、短句、环境压抑、草蛇灰线）",
  "磅礴仙侠风格（大道无情、天地缥缈、斗法宏大）",
  "细腻言情风格（情感拉扯、侧面烘托、日常物件隐喻）",
  "赛博朋克风格（霓虹迷幻、机械冰冷、阶级压迫感）",
  "自然写实风格（Show, Don't Tell，细节入微，不生硬陈述）",
];

const targetWordOptions = [500000, 1000000, 1500000];

const buildStoryPlan = (targetWords) => {
  const totalWords = Math.max(10000, Number(targetWords) || 500000);
  const targetEventCount = Math.max(1, Math.ceil(totalWords / 10000));
  const openingBreakthroughCount = Math.max(1, Math.min(3, Math.ceil(targetEventCount * 0.03)));
  const developmentEndEventId = Math.max(openingBreakthroughCount + 1, Math.ceil(targetEventCount * 0.2));
  const endingEventCount = Math.max(1, Math.ceil(targetEventCount * 0.2));
  const endingStartEventId = Math.max(1, targetEventCount - endingEventCount + 1);
  return {
    targetWords: totalWords,
    targetEventCount,
    openingBreakthroughCount,
    developmentEndEventId,
    endingStartEventId,
    endingEventCount,
  };
};

function App() {
  const [api, setApi] = useState(defaultApi);
  const [apiProfiles, setApiProfiles] = useState(defaultApiProfiles);
  const [selectedApiProfile, setSelectedApiProfile] = useState("openai_compatible");
  const [testingApi, setTestingApi] = useState(false);
  const [setting, setSetting] = useState("");
  const [novels, setNovels] = useState([]);
  const [selectedNovel, setSelectedNovel] = useState(null);
  const [newTitle, setNewTitle] = useState("");
  const [newSynopsis, setNewSynopsis] = useState("");
  const [newStyle, setNewStyle] = useState(styleOptions[0]);
  const [newNovelTargetWords, setNewNovelTargetWords] = useState(500000);
  const [defaultTargetWords, setDefaultTargetWords] = useState(500000);
  const [novelPlanDrafts, setNovelPlanDrafts] = useState({});
  const [savingNovelPlanId, setSavingNovelPlanId] = useState(null);
  const [style, setStyle] = useState(styleOptions[0]);
  const [genCount, setGenCount] = useState(1);
  const [menu, setMenu] = useState("console");
  const [consoleTab, setConsoleTab] = useState("dashboard");
  const [novelManagerTab, setNovelManagerTab] = useState("create");
  const [novelDetailTab, setNovelDetailTab] = useState("world");
  const [productionTab, setProductionTab] = useState("settings");
  const [promptTab, setPromptTab] = useState("overview");
  const [theme, setTheme] = useState(() => window.localStorage.getItem("novel-theme") || "night");
  const [characterQuery, setCharacterQuery] = useState("");
  const [characterTierFilter, setCharacterTierFilter] = useState("all");
  const [eventQuery, setEventQuery] = useState("");
  const [eventStatusFilter, setEventStatusFilter] = useState("all");
  const [chapterQuery, setChapterQuery] = useState("");
  const [showProgress, setShowProgress] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStep, setProgressStep] = useState("");
  const [progressReady, setProgressReady] = useState(false);
  const [selectedChapter, setSelectedChapter] = useState(null);
  const [jobList, setJobList] = useState([]);
  const [editingCharacter, setEditingCharacter] = useState(null);
  const [editingEvent, setEditingEvent] = useState(null);
  const [editingChapter, setEditingChapter] = useState(null);
  const [prompts, setPrompts] = useState(defaultPrompts);
  const [promptMenu, setPromptMenu] = useState("prompt1_world_setting");
  const [promptBackups, setPromptBackups] = useState([]);
  const [promptScope, setPromptScope] = useState("default");
  const [dashboard, setDashboard] = useState(null);
  const [lastFailureId, setLastFailureId] = useState(0);
  const [seedWorldSetting, setSeedWorldSetting] = useState("");
  const [worldviewSummary, setWorldviewSummary] = useState("");
  const [worldview, setWorldview] = useState("");
  const [openingSnapshot, setOpeningSnapshot] = useState("");
  const [seriesBlueprint, setSeriesBlueprint] = useState(null);
  const [characters, setCharacters] = useState([]);
  const [events, setEvents] = useState([]);
  const [chapters, setChapters] = useState([]);
  const [lorebook, setLorebook] = useState([]);
  const [foreshadows, setForeshadows] = useState([]);
  const [growthSystem, setGrowthSystem] = useState(null);
  const [growthSnapshot, setGrowthSnapshot] = useState(null);
  const [initStepStates, setInitStepStates] = useState({});
  const [logs, setLogs] = useState(() => {
    try {
      const raw = window.localStorage.getItem(UI_LOG_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  });
  const [jobId, setJobId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [runningJobIds, setRunningJobIds] = useState([]);
  const [defaultExportPath, setDefaultExportPath] = useState("");
  const [pendingImportSection, setPendingImportSection] = useState(null);
  const [pendingImportFile, setPendingImportFile] = useState(null);
  const [toast, setToast] = useState(null);
  const [confirmState, setConfirmState] = useState(null);
  const [initRunningStep, setInitRunningStep] = useState("");
  const [worldSettingDraft, setWorldSettingDraft] = useState("");
  const [blueprintDraft, setBlueprintDraft] = useState("");
  const [growthDraft, setGrowthDraft] = useState("");
  const [worldviewSummaryDraft, setWorldviewSummaryDraft] = useState("");
  const [openingSnapshotDraft, setOpeningSnapshotDraft] = useState("");
  const [worldviewDraft, setWorldviewDraft] = useState("");
  const [editingNovelMeta, setEditingNovelMeta] = useState({ title: "", synopsis: "", style: "" });

  const visiblePromptKeys = useMemo(
    () => promptOrder.filter((key) => Object.prototype.hasOwnProperty.call(prompts, key)),
    [prompts]
  );
  const currentNovel = useMemo(
    () => novels.find((novel) => novel.id === selectedNovel) || null,
    [novels, selectedNovel]
  );
  const currentChapter = useMemo(
    () => chapters.find((chapter) => chapter.chapter_num === selectedChapter) || null,
    [chapters, selectedChapter]
  );
  const createTargetWords = Math.max(10000, Number(newNovelTargetWords) || Number(defaultTargetWords) || 500000);
  const createStoryPlan = useMemo(() => buildStoryPlan(createTargetWords), [createTargetWords]);
  const selectedStoryPlan = useMemo(
    () => buildStoryPlan(currentNovel?.target_words || 500000),
    [currentNovel]
  );
  const openingEvents = useMemo(
    () => events.filter((event) => event.event_id <= selectedStoryPlan.openingBreakthroughCount),
    [events, selectedStoryPlan]
  );
  const lorebookMap = useMemo(() => {
    const map = new Map();
    lorebook.forEach((item) => {
      if (!item?.name) return;
      map.set(item.name, {
        ...item,
        related_characters: normalizeJsonArray(item.related_characters),
      });
    });
    return map;
  }, [lorebook]);
  const worldItemRows = useMemo(
    () =>
      lorebook.map((item, index) => ({
        key: `world-item-${item?.name || index}`,
        name: item?.name || "-",
        type: item?.type || "-",
        description: item?.description || "-",
        related_characters: normalizeJsonArray(item?.related_characters),
        location: item?.location || "-",
      })),
    [lorebook]
  );
  const eventLorebookUpdateRows = useMemo(() => {
    const rows = [];
    events.forEach((event) => {
      const updates = event?.event_lorebook_updates || {};
      const newItems = normalizeJsonArray(updates?.new_items);
      const updatedItems = normalizeJsonArray(updates?.updated_items);
      const removedItems = normalizeJsonArray(updates?.removed_items);
      newItems.forEach((item, index) => {
        rows.push({
          key: `event-lorebook-new-${event.event_id}-${index}`,
          event_id: event.event_id,
          action: "新增",
          name: item?.name || "-",
          type: item?.type || "-",
          description: item?.description || "-",
        });
      });
      updatedItems.forEach((item, index) => {
        rows.push({
          key: `event-lorebook-update-${event.event_id}-${index}`,
          event_id: event.event_id,
          action: "更新",
          name: item?.name || "-",
          type: item?.type || "-",
          description: item?.description || "-",
        });
      });
      removedItems.forEach((item, index) => {
        rows.push({
          key: `event-lorebook-remove-${event.event_id}-${index}`,
          event_id: event.event_id,
          action: "移除",
          name: item?.name || "-",
          type: "-",
          description: item?.reason || "-",
        });
      });
    });
    return rows;
  }, [events]);
  const initStepStatus = useMemo(
    () => ({
      world_setting: initStepStates.world_setting || "stale",
      series_blueprint: initStepStates.series_blueprint || "stale",
      growth_system: initStepStates.growth_system || "stale",
      core_characters: initStepStates.core_characters || "stale",
      worldview_summary: initStepStates.worldview_summary || "stale",
      opening_snapshot: initStepStates.opening_snapshot || "stale",
      opening_world_planning: initStepStates.opening_world_planning || "stale",
    }),
    [initStepStates]
  );
  const currentMainApiPath = normalizeMainApiPath(api.main_api_path);
  const currentMainApiOption =
    mainApiPathOptions.find((item) => item.value === currentMainApiPath) || mainApiPathOptions[0];
  const hasNovelSelection = Boolean(selectedNovel);
  const activeErrorJobs = useMemo(
    () => jobList.filter((job) => job.status === "failed"),
    [jobList]
  );
  const sortedCharacters = useMemo(() => {
    const tierOrder = { protagonist: 0, major_support: 1, support: 2, functional: 3 };
    return [...characters].sort((a, b) => {
      const tierDiff = (tierOrder[a.role_tier] ?? 9) - (tierOrder[b.role_tier] ?? 9);
      if (tierDiff !== 0) return tierDiff;
      return String(a.name || "").localeCompare(String(b.name || ""), "zh-Hans-CN");
    });
  }, [characters]);
  const filteredCharacters = useMemo(() => {
    const query = characterQuery.trim().toLowerCase();
    return sortedCharacters.filter((item) => {
      const matchesTier = characterTierFilter === "all" || item.role_tier === characterTierFilter;
      const haystack = [item.name, item.story_function, item.state, item.target, item.motive]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      const matchesQuery = !query || haystack.includes(query);
      return matchesTier && matchesQuery;
    });
  }, [sortedCharacters, characterQuery, characterTierFilter]);
  const filteredEvents = useMemo(() => {
    const query = eventQuery.trim().toLowerCase();
    return events.filter((item) => {
      const status = item.status || (item.is_written ? "completed" : "planned");
      const matchesStatus = eventStatusFilter === "all" || status === eventStatusFilter;
      const haystack = [item.event_id, item.outline_description, item.description, item.goal, item.cliffhanger]
        .filter((part) => part !== undefined && part !== null)
        .join(" ")
        .toLowerCase();
      const matchesQuery = !query || haystack.includes(query);
      return matchesStatus && matchesQuery;
    });
  }, [events, eventQuery, eventStatusFilter]);
  const filteredChapters = useMemo(() => {
    const query = chapterQuery.trim().toLowerCase();
    return chapters.filter((item) => {
      const haystack = [item.chapter_num, item.title, item.summary, item.source_event_id]
        .filter((part) => part !== undefined && part !== null)
        .join(" ")
        .toLowerCase();
      return !query || haystack.includes(query);
    });
  }, [chapters, chapterQuery]);

  const promptValue = normalizePromptTemplate(prompts[promptMenu]);
  const currentPromptMeta = promptMeta[promptMenu] || { stage: "-", output: "-", variables: [] };
  const coreCharacters = useMemo(
    () => characters.filter((item) => item.init_step === "core_characters" || item.scope_type === "full"),
    [characters]
  );
  const supplementCharacters = useMemo(
    () => characters.filter((item) => item.init_step === "supplement_characters"),
    [characters]
  );
  const selectedApiLabel = selectedApiProfile === "openai_compatible"
    ? "OPENAI标准配置"
    : "OPENAI自定义配置";
  const updateSelectedApi = (patch) => {
    setApiProfiles((prev) => {
      const next = {
        ...prev,
        [selectedApiProfile]: {
          ...(prev[selectedApiProfile] || defaultApi),
          ...patch,
        },
      };
      setApi(next[selectedApiProfile]);
      return next;
    });
  };
  const buildPromptApiPath = (path) => {
    if (!selectedNovel) return path;
    const separator = path.includes("?") ? "&" : "?";
    return `${path}${separator}novel_id=${encodeURIComponent(selectedNovel)}`;
  };

  const appendLog = (line) => {
    setLogs((prev) => [...prev, `[${new Date().toLocaleTimeString()}] ${line}`].slice(-500));
  };

  const clearLogs = () => {
    setLogs([]);
    window.localStorage.removeItem(UI_LOG_STORAGE_KEY);
    notify("界面日志已清空", "success");
  };

  const notify = (message, type = "info") => {
    setToast({ message, type, id: Date.now() });
  };

  const confirmAction = (message) =>
    new Promise((resolve) => {
      setConfirmState({
        message,
        onConfirm: () => {
          setConfirmState(null);
          resolve(true);
        },
        onCancel: () => {
          setConfirmState(null);
          resolve(false);
        },
      });
    });

  const extractErrorMessage = (rawText) => {
    const normalizeUpstreamMessage = (message) => {
      const text = String(message || "");
      const upper = text.toUpperCase();
      if (upper.includes("SUBSCRIPTION_NOT_FOUND") || upper.includes("NO ACTIVE SUBSCRIPTION FOUND FOR THIS GROUP")) {
        return "当前 API 账号或分组没有可用订阅，请先到控制台更换可用的 API Key/分组；如果想先继续，也可以手动填写世界设定后再执行后续初始化步骤。";
      }
      if (upper.includes("INSUFFICIENT_QUOTA") || upper.includes("QUOTA_EXCEEDED")) {
        return "当前 API 额度不足，请更换有余额/配额的账号后再试。";
      }
      if (upper.includes("INVALID_API_KEY") || upper.includes("INVALID API KEY")) {
        return "API Key 无效或未授权，请检查控制台中的 API 配置。";
      }
      return text;
    };
    try {
      const parsed = JSON.parse(rawText);
      if (parsed?.detail) {
        if (typeof parsed.detail === "string") {
          try {
            const nested = JSON.parse(parsed.detail);
            return normalizeUpstreamMessage(nested?.message || nested?.detail || parsed.detail);
          } catch {
            return normalizeUpstreamMessage(parsed.detail);
          }
        }
        return normalizeUpstreamMessage(parsed.detail.message || parsed.detail.detail || rawText);
      }
    } catch {
      return normalizeUpstreamMessage(rawText);
    }
    return normalizeUpstreamMessage(rawText);
  };

  const callApi = async (path, body) => {
    const res = await fetch(`http://localhost:8000${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(extractErrorMessage(text));
    }
    return res.json();
  };

  const fetchConfig = async () => {
    const res = await fetch("http://localhost:8000/api/config");
    if (!res.ok) return;
    const data = await res.json();
    const rawProfiles = data.api_profiles || defaultApiProfiles;
    const nextProfiles = Object.fromEntries(
      Object.entries(rawProfiles).map(([key, value]) => [key, normalizeApiProfile(key, value)])
    );
    if (!nextProfiles.openai_compatible) {
      nextProfiles.openai_compatible = normalizeApiProfile("openai_compatible", defaultApiProfiles.openai_compatible);
    }
    if (!nextProfiles.codex_cli) {
      nextProfiles.codex_cli = normalizeApiProfile("codex_cli", defaultApiProfiles.codex_cli);
    }
    const nextSelected = data.selected_api_profile || "openai_compatible";
    setApiProfiles(nextProfiles);
    setSelectedApiProfile(nextSelected);
    if (nextProfiles[nextSelected]) {
      setApi(nextProfiles[nextSelected]);
    } else if (data.api) {
      setApi(normalizeApiProfile(nextSelected, data.api));
    }
    if (data.default_style) {
      setStyle(data.default_style);
      setNewStyle(data.default_style);
    }
    const resolvedTargetWords = Number(data.default_target_words) || 500000;
    setDefaultTargetWords(resolvedTargetWords);
    setNewNovelTargetWords(resolvedTargetWords);
    setDefaultExportPath(data.default_export_path || "F:/项目/小说gpt版/exports");
  };

  const saveConfig = async () => {
    const normalizeProfileForSave = (key, value) => {
      const base = serializeApiConfig(value);
      if (key === "openai_compatible") {
        return {
          ...base,
          main_api_path: "chat/completions",
          use_stream: false,
          model_reasoning_effort: "",
        };
      }
      return base;
    };
    const serializedProfiles = Object.fromEntries(
      Object.entries(apiProfiles).map(([key, value]) => [key, normalizeProfileForSave(key, value)])
    );
    await callApi("/api/config", {
      api: normalizeProfileForSave(selectedApiProfile, api),
      api_profiles: serializedProfiles,
      selected_api_profile: selectedApiProfile,
      default_style: style,
      default_target_words: Number(defaultTargetWords) || 500000,
      default_export_path: defaultExportPath,
    });
    appendLog("配置已保存");
  };

  const testCurrentApiConfig = async () => {
    setTestingApi(true);
    try {
      const res = await fetch("http://localhost:8000/api/config/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(serializeApiConfig(api)),
      });
      const text = await res.text();
      if (!res.ok) {
        throw new Error(text);
      }
      const data = JSON.parse(text);
      if (data.ok) {
        notify(`连接成功：${selectedApiLabel}`, "success");
        appendLog(
          `API 测试成功：${selectedApiLabel} / ${data.main_api_path || "chat/completions"} / ${data.use_stream ? "stream" : "non-stream"} / 输出=${data.output_text || "(无返回文本)"}`
        );
      } else {
        notify(`连接失败：${selectedApiLabel}`, "error");
        appendLog(
          `API 测试失败：${selectedApiLabel} / models=${data.models_status || "?"} / request=${data.chat_status || "?"}`
        );
      }
    } catch (err) {
      notify(`连接失败：${err.message}`, "error");
      appendLog(`API 测试异常：${err.message}`);
    } finally {
      setTestingApi(false);
    }
  };

  const triggerImport = (section) => {
    setPendingImportSection(section);
    setPendingImportFile(null);
  };

  const redirectToCreateNovel = () => {
    setMenu("novels");
    setNovelManagerTab("create");
    notify("当前没有选中的小说，已跳转到创建小说。", "info");
  };

  const handlePickExportDirectory = async () => {
    if (!window.showDirectoryPicker) {
      notify("当前浏览器不支持目录选择，请直接手动填写完整导出路径", "error");
      appendLog("当前浏览器不支持 showDirectoryPicker，请手动输入导出路径");
      return;
    }
    try {
      const handle = await window.showDirectoryPicker();
      if (handle?.name) {
        setDefaultExportPath((prev) => {
          if (prev && /[\\/]/.test(prev)) {
            const normalized = prev.replace(/\\/g, "/");
            const parts = normalized.split("/").filter(Boolean);
            if (parts.length > 0) {
              parts[parts.length - 1] = handle.name;
              return prev.includes("\\") ? parts.join("\\") : parts.join("/");
            }
          }
          return handle.name;
        });
        appendLog(`已选择目录：${handle.name}。如需完整路径，请继续手动补全。`);
      }
    } catch (error) {
      if (error?.name === "AbortError") {
        return;
      }
      notify("目录选择失败，请手动填写导出路径", "error");
      appendLog(`目录选择失败：${error.message || error}`);
    }
  };

  const exportSection = async (section, body = {}) => {
    if (!selectedNovel) return;
    const res = await fetch(`http://localhost:8000/api/novels/${selectedNovel}/export/${section}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      appendLog(`导出失败：${text}`);
      notify(`导出失败：${text}`, "error");
      return;
    }
    const data = await res.json();
    if (Array.isArray(data.file_paths)) {
      notify(`导出完成，共导出 ${data.count || data.file_paths.length} 个文件`, "success");
      return;
    }
    notify(`导出完成：${data.file_path || section}`, "success");
  };

  const importSection = async (section, file) => {
    if (!selectedNovel || !file) return;
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`http://localhost:8000/api/novels/${selectedNovel}/import/${section}`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const text = await res.text();
      appendLog(`导入失败：${text}`);
      notify(`导入失败：${text}`, "error");
      return;
    }
    const data = await res.json();
    appendLog(`导入完成：${section}，共 ${data.imported || 0} 条`);
    notify(`导入完成：${section}，共 ${data.imported || 0} 条`, "success");
    setPendingImportSection(null);
    setPendingImportFile(null);
    loadNovelDetails(selectedNovel);
  };

  const loadNovels = async () => {
    const res = await fetch("http://localhost:8000/api/novels");
    if (!res.ok) return;
    const data = await res.json();
    const nextNovels = data.novels || [];
    setNovels(nextNovels);
    setNovelPlanDrafts((prev) => {
      const next = {};
      nextNovels.forEach((novel) => {
        next[novel.id] = prev[novel.id] ?? novel.target_words ?? 500000;
      });
      return next;
    });
  };

  const saveNovelTargetWords = async (novelId) => {
    const targetWords = Math.max(10000, Number(novelPlanDrafts[novelId]) || 500000);
    setSavingNovelPlanId(novelId);
    try {
      const res = await fetch(`http://localhost:8000/api/novels/${novelId}/plan`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_words: targetWords }),
      });
      if (!res.ok) {
        throw new Error(extractErrorMessage(await res.text()));
      }
      await loadNovels();
      if (selectedNovel === novelId) {
        await loadNovelDetails(novelId);
      }
      appendLog(`已更新小说目标字数：${novelId} -> ${targetWords}`);
      notify("目标字数已更新", "success");
    } catch (err) {
      notify(`更新失败：${err.message}`, "error");
      appendLog(`更新小说目标字数失败：${err.message}`);
    } finally {
      setSavingNovelPlanId(null);
    }
  };

  const updateInitStepState = async (stepKey, state) => {
    if (!selectedNovel) return;
    try {
      const res = await fetch(`http://localhost:8000/api/novels/${selectedNovel}/init-steps`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step_key: stepKey, state }),
      });
      if (!res.ok) throw new Error(extractErrorMessage(await res.text()));
      const data = await res.json();
      setInitStepStates(data.init_steps || {});
      notify(`${initStepLabels[stepKey] || stepKey} 标记已更新`, "success");
    } catch (err) {
      notify(`更新标记失败：${err.message}`, "error");
    }
  };

  const deleteNovelById = async (novelId) => {
    const first = await confirmAction("确定删除该小说吗？");
    if (!first) return;
    const res = await fetch(`http://localhost:8000/api/novels/${novelId}`, { method: "DELETE" });
    if (!res.ok) return;
    const data = await res.json();
    if (data.status === "confirm") {
      const second = await confirmAction(`该小说已有 ${data.chapters} 章内容，确认彻底删除？`);
      if (!second) return;
      await fetch(`http://localhost:8000/api/novels/${novelId}?force=true`, { method: "DELETE" });
    }
    if (selectedNovel === novelId) {
      setSelectedNovel(null);
    }
    await loadNovels();
  };

  const clearChaptersByNovel = async (novelId) => {
    const confirmed = await confirmAction("确定清空当前小说的所有章节，并将全部事件重置为 planned 吗？");
    if (!confirmed) return;
    const res = await fetch(`http://localhost:8000/api/novels/${novelId}/chapters`, { method: "DELETE" });
    if (!res.ok) {
      notify(`清空章节失败：${extractErrorMessage(await res.text())}`, "error");
      return;
    }
    notify("已清空章节并重置事件状态。", "success");
    await loadNovelDetails(novelId);
  };

  const deleteSingleChapter = async (novelId, chapterNum) => {
    const confirmed = await confirmAction(`确定删除第 ${chapterNum} 章吗？`);
    if (!confirmed) return;
    const res = await fetch(`http://localhost:8000/api/novels/${novelId}/chapters/${chapterNum}`, { method: "DELETE" });
    if (!res.ok) {
      notify(`删除章节失败：${extractErrorMessage(await res.text())}`, "error");
      return;
    }
    notify(`第 ${chapterNum} 章已删除。`, "success");
    if (selectedChapter === chapterNum) setSelectedChapter(null);
    await loadNovelDetails(novelId);
  };

  const loadJobs = async () => {
    const res = await fetch("http://localhost:8000/api/jobs");
    if (!res.ok) return;
    const data = await res.json();
    const jobs = data.jobs || [];
    setJobList(jobs);
    setRunningJobIds(jobs.filter((j) => j.status === "running").map((j) => j.job_id));
  };

  const loadPrompts = async () => {
    const res = await fetch(`http://localhost:8000${buildPromptApiPath("/api/prompts")}`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.prompts) {
      const nextPrompts = {};
      allPromptKeys.forEach((key) => {
        nextPrompts[key] = normalizePromptTemplate(data.prompts[key]);
      });
      setPrompts(nextPrompts);
      if (!nextPrompts[promptMenu]) {
        setPromptMenu(promptOrder[0]);
      }
      setPromptScope(data.scope || "default");
    }
  };

  const loadPromptBackups = async () => {
    const res = await fetch(`http://localhost:8000${buildPromptApiPath("/api/prompts/backups")}`);
    if (!res.ok) return;
    const data = await res.json();
    setPromptBackups(data.backups || []);
  };

    const savePrompts = async () => {
    const required = currentPromptMeta.variables || [];
    const combinedPromptValue = `${promptValue.system_prompt || ""}\n${promptValue.user_prompt || ""}`;
    const missing = required.filter((token) => !combinedPromptValue.includes(token));
    if (missing.length > 0) {
      const action = await confirmAction(
        `提示词校验失败，缺少变量：${missing.join(", ")}\n\n点击“确定”恢复默认，点击“取消”继续修改。`
      );
      if (action) {
        setPrompts({ ...prompts, [promptMenu]: normalizePromptTemplate(defaultPrompts[promptMenu]) });
        appendLog(`已恢复默认提示词：${promptLabels[promptMenu] || promptMenu}`);
      }
      return;
    }
    await callApi(buildPromptApiPath("/api/prompts"), prompts);
    appendLog(selectedNovel ? `小说提示词已保存：${selectedNovel}` : "默认提示词已保存");
    await loadPromptBackups();
    await loadPrompts();
  };

  const resetPrompts = async () => {
    const ok = await confirmAction("确定恢复全部系统默认提示词吗？当前提示词会先自动备份。");
    if (!ok) return;
    const res = await fetch(`http://localhost:8000${buildPromptApiPath("/api/prompts/reset")}`, {
      method: "POST",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text);
    }
    const data = await res.json();
    if (data.prompts) {
      const nextPrompts = {};
      allPromptKeys.forEach((key) => {
        nextPrompts[key] = normalizePromptTemplate(data.prompts[key]);
      });
      setPrompts(nextPrompts);
    }
    await loadPromptBackups();
    appendLog(`${selectedNovel ? `已恢复小说 ${selectedNovel} 为默认提示词` : "已恢复系统默认提示词"}${data.backup_path ? `，已备份到 ${data.backup_path}` : ""}`);
    await loadPrompts();
  };

  const resetCurrentPrompt = async () => {
    const ok = await confirmAction(`确定将 ${promptLabels[promptMenu] || promptMenu} 恢复为系统默认吗？当前版本会先自动备份。`);
    if (!ok) return;
    const res = await fetch(`http://localhost:8000${buildPromptApiPath(`/api/prompts/reset/${promptMenu}`)}`, {
      method: "POST",
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text);
    }
    const data = await res.json();
    if (data.prompt_key) {
      setPrompts((prev) => ({ ...prev, [data.prompt_key]: normalizePromptTemplate(data.value) }));
    }
    await loadPromptBackups();
    await loadPrompts();
    appendLog(`已恢复当前提示词默认值：${promptLabels[promptMenu] || promptMenu}`);
  };

  const restorePromptBackup = async (file) => {
    const ok = await confirmAction(`确定回滚到备份 ${file} 吗？当前提示词会先再次备份。`);
    if (!ok) return;
    const res = await fetch(`http://localhost:8000${buildPromptApiPath("/api/prompts/restore")}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file }),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text);
    }
    const data = await res.json();
    if (data.prompts) {
      setPrompts(data.prompts);
    }
    await loadPromptBackups();
    await loadPrompts();
    appendLog(`已回滚提示词备份：${file}`);
  };

  const deleteJob = async (jobId) => {
    const ok = await confirmAction("确定删除这条任务记录吗？");
    if (!ok) return;
    await fetch(`http://localhost:8000/api/jobs/${jobId}`, {
      method: "DELETE",
    });
    appendLog(`已删除任务记录：${jobId}`);
    loadJobs();
  };

  const clearJobs = async () => {
    const ok = await confirmAction("确定清空全部任务历史吗？该操作不可恢复。");
    if (!ok) return;
    await fetch("http://localhost:8000/api/jobs", {
      method: "DELETE",
    });
    appendLog("已清空全部任务历史");
    loadJobs();
  };

  const pollJobStatus = async (newJobId) => {
    while (true) {
      const res = await fetch(`http://localhost:8000/api/jobs/${newJobId}`);
      if (!res.ok) throw new Error("任务状态获取失败");
      const data = await res.json();
      if (data.status === "done") return data;
      if (data.status === "failed") throw new Error(data.error || "任务失败");
      await new Promise((r) => setTimeout(r, 1200));
    }
  };

  const createNovel = async (autoInitialize = false) => {
    if (!newTitle.trim()) {
      appendLog("请输入小说标题");
      return;
    }
    if (!newSynopsis.trim()) {
      appendLog("请输入一句话梗概");
      return;
    }
    if (!createTargetWords) {
      appendLog("请输入目标字数");
      return;
    }
    setShowProgress(true);
    setProgressReady(false);
    setProgress(0);
    setProgressStep(autoInitialize ? "正在创建并初始化小说..." : "正在创建小说...");
    try {
      const result = await callApi("/api/novels", {
        title: newTitle.trim(),
        synopsis: newSynopsis.trim(),
        style: newStyle,
        target_words: createTargetWords,
      });
      setSelectedNovel(result.novel_id);
      await loadNovels();
      await loadNovelDetails(result.novel_id);
      if (autoInitialize) {
        const steps = [
          ["world_setting", "正在生成世界设定..."],
          ["series_blueprint", "正在生成阶段计划..."],
          ["growth_system", "正在生成成长规划..."],
          ["core_characters", "正在生成核心人物卡..."],
          ["worldview_summary", "正在生成世界观摘要..."],
          ["opening_snapshot", "正在生成世界快照..."],
          ["opening_world_planning", "正在生成事件规划..."],
        ];
        for (let i = 0; i < steps.length; i += 1) {
          const [stepName, label] = steps[i];
          setProgressStep(label);
          setProgress(Math.round((i / steps.length) * 100));
          const resultMessage = await runInitStep(stepName, result.novel_id);
          if (resultMessage !== true) {
            throw new Error(`初始化步骤失败：${stepName} / ${resultMessage}`);
          }
        }
      }

      setNewTitle("");
      setNewSynopsis("");
      setNewStyle(styleOptions[0]);
      setNewNovelTargetWords(Number(defaultTargetWords) || 500000);
      setProgressStep(autoInitialize ? "全部初始化完成" : "小说创建完成");
      setProgress(100);
      setProgressReady(true);
      notify(autoInitialize ? "小说初始化完成" : "小说创建完成", "success");
    } catch (err) {
      setProgressStep(`生成失败：${err.message}`);
      setProgressReady(true);
      notify(`生成失败：${err.message}`, "error");
    }
  };

  const loadNovelDetails = async (novelId) => {
    if (!novelId) return;
    const loaded = {};
    const [dashRes, initRes, seedRes, summaryRes, snapshotRes, wvRes, sbRes, chRes, evRes, cpRes, lbRes, fsRes, gsRes] = await Promise.all([
      fetch(`http://localhost:8000/api/novels/${novelId}/dashboard`),
      fetch(`http://localhost:8000/api/novels/${novelId}/init-steps`),
      fetch(`http://localhost:8000/api/novels/${novelId}/seed-world-setting`),
      fetch(`http://localhost:8000/api/novels/${novelId}/worldview-summary`),
      fetch(`http://localhost:8000/api/novels/${novelId}/opening-snapshot`),
      fetch(`http://localhost:8000/api/novels/${novelId}/worldview`),
      fetch(`http://localhost:8000/api/novels/${novelId}/series-blueprint`),
      fetch(`http://localhost:8000/api/novels/${novelId}/characters`),
      fetch(`http://localhost:8000/api/novels/${novelId}/events`),
      fetch(`http://localhost:8000/api/novels/${novelId}/chapters`),
      fetch(`http://localhost:8000/api/novels/${novelId}/lorebook`),
      fetch(`http://localhost:8000/api/novels/${novelId}/foreshadows`),
      fetch(`http://localhost:8000/api/novels/${novelId}/growth-system`),
    ]);
    if (dashRes.ok) {
      const data = await dashRes.json();
      loaded.dashboard = data;
      setDashboard(data);
      const runs = Array.isArray(data.event_runs) ? data.event_runs : [];
      const latestFailure = runs.find((item) => item.status === "failed");
      if (latestFailure && latestFailure.id && latestFailure.id !== lastFailureId) {
        setLastFailureId(latestFailure.id);
        notify(`事件 ${latestFailure.event_id || "未知"} 生产失败：${latestFailure.reason || "无"}`, "error");
      }
    }
    if (initRes.ok) {
      const data = await initRes.json();
      loaded.init_steps = data.init_steps || {};
      setInitStepStates(data.init_steps || {});
    } else {
      setInitStepStates({});
    }
    if (seedRes.ok) {
      const data = await seedRes.json();
      const content = data.content || "";
      loaded.seed_world_setting = content;
      setSeedWorldSetting(content);
      setWorldSettingDraft(content);
    } else {
      setSeedWorldSetting("");
      setWorldSettingDraft("");
    }
    if (summaryRes.ok) {
      const data = await summaryRes.json();
      loaded.worldview_summary = data.content || "";
      setWorldviewSummary(data.content || "");
      setWorldviewSummaryDraft(data.content || "");
    } else {
      setWorldviewSummary("");
      setWorldviewSummaryDraft("");
    }
    if (snapshotRes.ok) {
      const data = await snapshotRes.json();
      loaded.opening_snapshot = data.content || "";
      setOpeningSnapshot(data.content || "");
      setOpeningSnapshotDraft(data.content || "");
    } else {
      setOpeningSnapshot("");
      setOpeningSnapshotDraft("");
    }
    if (wvRes.ok) {
      const data = await wvRes.json();
      loaded.worldview = data.content || "";
      setWorldview(data.content || "");
      setWorldviewDraft(data.content || "");
    } else {
      setWorldview("");
      setWorldviewDraft("");
    }
    if (sbRes.ok) {
      const data = await sbRes.json();
      loaded.series_blueprint = data.series_blueprint || null;
      setSeriesBlueprint(data.series_blueprint || null);
      setBlueprintDraft(formatJsonEditor(data.series_blueprint));
    } else {
      setSeriesBlueprint(null);
      setBlueprintDraft("");
    }
    if (chRes.ok) {
      const data = await chRes.json();
      loaded.characters = data.characters || [];
      setCharacters(data.characters || []);
    }
    if (evRes.ok) {
      const data = await evRes.json();
      loaded.events = data.events || [];
      setEvents(data.events || []);
    }
    if (cpRes.ok) {
      const data = await cpRes.json();
      const nextChapters = data.chapters || [];
      loaded.chapters = nextChapters;
      setChapters(nextChapters);
      if (selectedChapter && !nextChapters.some((chapter) => chapter.chapter_num === selectedChapter)) {
        setSelectedChapter(null);
      }
    }
    if (lbRes.ok) {
      const data = await lbRes.json();
      loaded.lorebook = data.lorebook || [];
      setLorebook(data.lorebook || []);
    }
    if (fsRes.ok) {
      const data = await fsRes.json();
      loaded.foreshadows = data.foreshadows || [];
      setForeshadows(data.foreshadows || []);
    }
    if (gsRes.ok) {
      const data = await gsRes.json();
      loaded.growth_system = data.growth_system || null;
      loaded.growth_snapshot = data.growth_snapshot || null;
      setGrowthSystem(data.growth_system || null);
      setGrowthSnapshot(data.growth_snapshot || null);
      setGrowthDraft(formatJsonEditor(data.growth_system));
    } else {
      setGrowthSystem(null);
      setGrowthSnapshot(null);
      setGrowthDraft("");
    }
    return loaded;
  };

  const fetchEventCheckpoints = async (novelId, eventId) => {
    const res = await fetch(`http://localhost:8000/api/novels/${novelId}/events/${eventId}/checkpoints`);
    if (!res.ok) {
      throw new Error(extractErrorMessage(await res.text()));
    }
    return res.json();
  };

  const rewriteEventFromCheckpoint = async (eventId) => {
    if (!selectedNovel) {
      throw new Error("请先选择小说");
    }
    appendLog(`开始提交事件 ${eventId} 的 checkpoint 重写任务...`);
    const result = await callApi(`/api/novels/${selectedNovel}/events/${eventId}/rewrite`, {
      api,
      novel_style: currentNovel?.style || style,
      preserve_chapter_count: true,
    });
    if (result.job_id) {
      await pollJob(result.job_id);
      return loadNovelDetails(selectedNovel);
    }
    return result;
  };

  const saveNovelMeta = async () => {
    if (!selectedNovel) return;
    setBusy(true);
    try {
      const res = await fetch(`http://localhost:8000/api/novels/${selectedNovel}/meta`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editingNovelMeta),
      });
      if (!res.ok) {
        throw new Error(extractErrorMessage(await res.text()));
      }
      await loadNovels();
      await loadNovelDetails(selectedNovel);
      appendLog(`已更新小说信息：${selectedNovel}`);
      notify("小说信息已保存", "success");
    } catch (err) {
      notify(`保存失败：${err.message}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const saveSeedWorldSetting = async () => {
    if (!selectedNovel) return;
    setBusy(true);
    try {
      const res = await fetch(`http://localhost:8000/api/novels/${selectedNovel}/seed-world-setting`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: worldSettingDraft }),
      });
      if (!res.ok) throw new Error(extractErrorMessage(await res.text()));
      setSeedWorldSetting(worldSettingDraft);
      const data = await res.json();
      setInitStepStates(data.init_steps || {});
      appendLog(`世界设定已保存：${selectedNovel}`);
      notify("世界设定已保存", "success");
    } catch (err) {
      notify(`保存失败：${err.message}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const saveSeriesBlueprintDraft = async () => {
    if (!selectedNovel) return;
    setBusy(true);
    try {
      const parsed = JSON.parse(blueprintDraft || "{}");
      const res = await fetch(`http://localhost:8000/api/novels/${selectedNovel}/series-blueprint`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
      });
      if (!res.ok) throw new Error(extractErrorMessage(await res.text()));
      const data = await res.json();
      setSeriesBlueprint(data.series_blueprint || null);
      setBlueprintDraft(formatJsonEditor(data.series_blueprint));
      setInitStepStates(data.init_steps || {});
      appendLog(`阶段计划已保存：${selectedNovel}`);
      notify("阶段计划已保存", "success");
    } catch (err) {
      notify(`保存失败：${err.message}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const saveGrowthSystemDraft = async () => {
    if (!selectedNovel) return;
    setBusy(true);
    try {
      const parsed = JSON.parse(growthDraft || "{}");
      const res = await fetch(`http://localhost:8000/api/novels/${selectedNovel}/growth-system`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
      });
      if (!res.ok) throw new Error(extractErrorMessage(await res.text()));
      const data = await res.json();
      setGrowthSystem(data.growth_system || null);
      setGrowthSnapshot(data.growth_snapshot || null);
      setGrowthDraft(formatJsonEditor(data.growth_system));
      setInitStepStates(data.init_steps || {});
      appendLog(`成长规划已保存：${selectedNovel}`);
      notify("成长规划已保存", "success");
    } catch (err) {
      notify(`保存失败：${err.message}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const saveWorldviewSummaryDraft = async () => {
    if (!selectedNovel) return;
    setBusy(true);
    try {
      const res = await fetch(`http://localhost:8000/api/novels/${selectedNovel}/worldview-summary`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: worldviewSummaryDraft }),
      });
      if (!res.ok) throw new Error(extractErrorMessage(await res.text()));
      const data = await res.json();
      setWorldviewSummary(data.content || "");
      setWorldviewSummaryDraft(data.content || "");
      setInitStepStates(data.init_steps || {});
      appendLog(`世界观摘要已保存：${selectedNovel}`);
      notify("世界观摘要已保存", "success");
    } catch (err) {
      notify(`保存失败：${err.message}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const saveOpeningSnapshotDraft = async () => {
    if (!selectedNovel) return;
    setBusy(true);
    try {
      const res = await fetch(`http://localhost:8000/api/novels/${selectedNovel}/opening-snapshot`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: openingSnapshotDraft }),
      });
      if (!res.ok) throw new Error(extractErrorMessage(await res.text()));
      const data = await res.json();
      setOpeningSnapshot(data.content || "");
      setOpeningSnapshotDraft(data.content || "");
      setInitStepStates(data.init_steps || {});
      appendLog(`世界快照已保存：${selectedNovel}`);
      notify("世界快照已保存", "success");
    } catch (err) {
      notify(`保存失败：${err.message}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const saveWorldviewDraft = async () => {
    if (!selectedNovel) return;
    setBusy(true);
    try {
      const res = await fetch(`http://localhost:8000/api/novels/${selectedNovel}/worldview`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: worldviewDraft }),
      });
      if (!res.ok) throw new Error(extractErrorMessage(await res.text()));
      const data = await res.json();
      setWorldview(data.content || "");
      setWorldviewDraft(data.content || "");
      setInitStepStates(data.init_steps || {});
      appendLog(`世界状态已保存：${selectedNovel}`);
      notify("世界状态已保存", "success");
    } catch (err) {
      notify(`保存失败：${err.message}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const runInitStep = async (stepName, novelId = selectedNovel) => {
    if (!novelId) return;
    setBusy(true);
    setInitRunningStep(stepName);
    try {
      const res = await fetch(`http://localhost:8000/api/novels/${novelId}/initialize/${stepName}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api,
          prompt1_world_setting: prompts.prompt1_world_setting,
          prompt2_series_blueprint: prompts.prompt2_series_blueprint,
          prompt3_growth_system: prompts.prompt3_growth_system,
          prompt4_core_characters: prompts.prompt4_core_characters,
          prompt5_worldview_summary: prompts.prompt5_worldview_summary,
          prompt6_opening_snapshot: prompts.prompt6_opening_snapshot,
          prompt7_opening_world_planning: prompts.prompt7_opening_world_planning,
          prompt_internal_supplement_characters: prompts.prompt_internal_supplement_characters,
        }),
      });
      if (!res.ok) throw new Error(extractErrorMessage(await res.text()));
      await loadNovels();
      await loadNovelDetails(novelId);
      appendLog(`初始化步骤完成：${stepName}`);
      notify(`初始化步骤完成：${stepName}`, "success");
      return true;
    } catch (err) {
      notify(`初始化失败：${err.message}`, "error");
      appendLog(`初始化步骤失败 ${stepName}: ${err.message}`);
      return err.message || String(err);
    } finally {
      setInitRunningStep("");
      setBusy(false);
    }
  };

  const runInitAll = async (novelId = selectedNovel) => {
    const steps = [
      "world_setting",
      "series_blueprint",
      "growth_system",
      "core_characters",
      "worldview_summary",
      "opening_snapshot",
      "opening_world_planning",
    ];
    for (const stepName of steps) {
      const result = await runInitStep(stepName, novelId);
      if (result !== true) return result;
    }
    return true;
  };

  const toggleLock = async (type, id, locked) => {
    if (!selectedNovel) return;
    let url = "";
    if (type === "character") {
      url = `http://localhost:8000/api/novels/${selectedNovel}/characters/${encodeURIComponent(id)}/lock`;
    } else if (type === "event") {
      url = `http://localhost:8000/api/novels/${selectedNovel}/events/${id}/lock`;
    } else if (type === "chapter") {
      url = `http://localhost:8000/api/novels/${selectedNovel}/chapters/${id}/lock`;
    } else if (type === "lorebook") {
      url = `http://localhost:8000/api/novels/${selectedNovel}/lorebook/${encodeURIComponent(id)}/lock`;
    }
    if (!url) return;
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locked }),
    });
    appendLog(`${type} ${locked ? "已锁定" : "已解锁"}: ${id}`);
    loadNovelDetails(selectedNovel);
  };

  const pollJob = async (newJobId) => {
    setJobId(newJobId);
    appendLog(`任务已提交：${newJobId}`);
    let lastCount = 0;
    while (true) {
      const res = await fetch(`http://localhost:8000/api/jobs/${newJobId}`);
      if (!res.ok) {
        appendLog("获取任务状态失败");
        break;
      }
      const data = await res.json();
      if (data.logs && data.logs.length > lastCount) {
        data.logs.slice(lastCount).forEach((line) => appendLog(line.message));
        lastCount = data.logs.length;
      }
      if (data.status === "done") {
        appendLog("任务完成");
        break;
      }
      if (data.status === "failed") {
        appendLog(`任务失败：${data.error || "未知错误"}`);
        break;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
  };

  const runOutline = async () => {
    if (!selectedNovel) {
      appendLog("请先选择小说");
      return;
    }
    setBusy(true);
    appendLog("开始生成大纲与人物卡...");
    try {
      const result = await callApi("/api/outline", {
        api,
        setting,
        novel_id: selectedNovel,
        prompt1_world_setting: prompts.prompt1_world_setting,
        prompt2_series_blueprint: prompts.prompt2_series_blueprint,
        prompt3_growth_system: prompts.prompt3_growth_system,
        prompt4_core_characters: prompts.prompt4_core_characters,
        prompt5_worldview_summary: prompts.prompt5_worldview_summary,
        prompt6_opening_snapshot: prompts.prompt6_opening_snapshot,
        prompt7_opening_world_planning: prompts.prompt7_opening_world_planning,
        prompt_internal_supplement_characters: prompts.prompt_internal_supplement_characters,
      });
      if (result.job_id) {
        await pollJob(result.job_id);
        await loadNovelDetails(selectedNovel);
      }
    } catch (err) {
      appendLog(`失败：${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  const runChapters = async () => {
    if (!selectedNovel) {
      appendLog("请先选择小说");
      return;
    }
    setBusy(true);
    appendLog(`开始生成章节，数量 ${genCount}...`);
    try {
      const writtenEvents = events.filter((event) => event.is_written).length;
      if (
        writtenEvents < selectedStoryPlan.endingStartEventId &&
        writtenEvents + Number(genCount) >= selectedStoryPlan.endingStartEventId
      ) {
        const shouldContinue = await confirmAction(
          `按当前目标字数规划，本次生成会进入结局期（从事件 ${selectedStoryPlan.endingStartEventId} 开始）。如果你还想继续长期连载，请先修改目标字数。是否继续按当前规划生成？`
        );
        if (!shouldContinue) {
          setBusy(false);
          return;
        }
      }
      const result = await callApi("/api/chapters", {
        api,
        novel_id: selectedNovel,
        limit_count: Number(genCount),
        novel_style: currentNovel?.style || style,
        prompt3_growth_system: prompts.prompt3_growth_system,
        prompt10_sub_outline: prompts.prompt10_sub_outline,
        prompt11_part_plan: prompts.prompt11_part_plan,
        prompt12_part_write: prompts.prompt12_part_write,
        prompt13_part_reflect: prompts.prompt13_part_reflect,
        prompt_internal_supplement_characters: prompts.prompt_internal_supplement_characters,
      });
      if (result.job_id) {
        await pollJob(result.job_id);
        await loadNovelDetails(selectedNovel);
      }
    } catch (err) {
      appendLog(`失败：${err.message}`);
    } finally {
      setBusy(false);
    }
  };

  React.useEffect(() => {
    fetchConfig();
    loadNovels();
    loadJobs();
    loadPrompts();
    loadPromptBackups();
  }, []);

  React.useEffect(() => {
    if (selectedNovel) {
      setSelectedChapter(null);
      setEditingCharacter(null);
      setEditingEvent(null);
      setEditingChapter(null);
      loadNovelDetails(selectedNovel);
    } else {
      setSeedWorldSetting("");
      setWorldSettingDraft("");
      setSeriesBlueprint(null);
      setBlueprintDraft("");
      setGrowthSystem(null);
      setGrowthSnapshot(null);
      setGrowthDraft("");
      setWorldview("");
      setWorldviewDraft("");
      setCharacters([]);
      setEvents([]);
      setChapters([]);
      setInitStepStates({});
    }
    loadPrompts();
    loadPromptBackups();
  }, [selectedNovel]);

  React.useEffect(() => {
    if (currentNovel?.style) {
      setStyle(currentNovel.style);
    }
  }, [currentNovel]);

  React.useEffect(() => {
    if (!newTitle && !newSynopsis) {
      setNewNovelTargetWords(Number(defaultTargetWords) || 500000);
    }
  }, [defaultTargetWords, newTitle, newSynopsis]);

  React.useEffect(() => {
    setEditingNovelMeta({
      title: currentNovel?.title || "",
      synopsis: currentNovel?.synopsis || "",
      style: currentNovel?.style || styleOptions[0],
    });
  }, [currentNovel?.id, currentNovel?.title, currentNovel?.synopsis, currentNovel?.style]);

  React.useEffect(() => {
    if (apiProfiles[selectedApiProfile]) {
      setApi(apiProfiles[selectedApiProfile]);
    }
  }, [apiProfiles, selectedApiProfile]);

  React.useEffect(() => {
    const t = setInterval(() => {
      loadJobs();
    }, 2000);
    return () => clearInterval(t);
  }, []);

  React.useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  React.useEffect(() => {
    try {
      window.localStorage.setItem(UI_LOG_STORAGE_KEY, JSON.stringify(logs.slice(-500)));
    } catch {
      // ignore storage errors
    }
  }, [logs]);

  React.useEffect(() => {
    if (selectedChapter && !filteredChapters.some((item) => item.chapter_num === selectedChapter)) {
      setSelectedChapter(null);
    }
  }, [filteredChapters, selectedChapter]);

  React.useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("novel-theme", theme);
  }, [theme]);

  return (
    <div className="layout">
      <AppSidebar
        menu={menu}
        setMenu={setMenu}
        consoleTab={consoleTab}
        setConsoleTab={setConsoleTab}
        novelManagerTab={novelManagerTab}
        setNovelManagerTab={setNovelManagerTab}
        productionTab={productionTab}
        setProductionTab={setProductionTab}
        promptTab={promptTab}
        setPromptTab={setPromptTab}
        primaryMenuMeta={primaryMenuMeta}
        secondaryMenuLabels={secondaryMenuLabels}
      />

      <main className="content">
      <AppTopbar
        novels={novels}
        selectedNovel={selectedNovel}
        setSelectedNovel={setSelectedNovel}
        hasNovelSelection={hasNovelSelection}
        redirectToCreateNovel={redirectToCreateNovel}
        selectedApiLabel={selectedApiLabel}
        currentApiModel={api.model}
        currentApiBaseUrl={api.base_url}
        theme={theme}
        setTheme={setTheme}
        currentNovel={currentNovel}
        storyPhaseLabels={storyPhaseLabels}
      />

        {menu === "console" && (
          <ConsolePage
            consoleTab={consoleTab}
            dashboard={dashboard}
            currentNovel={currentNovel}
            jobList={jobList}
            novels={novels}
            activeErrorJobs={activeErrorJobs}
            selectedApiProfile={selectedApiProfile}
            setSelectedApiProfile={setSelectedApiProfile}
            selectedApiLabel={selectedApiLabel}
            api={api}
            updateSelectedApi={updateSelectedApi}
            currentMainApiPath={currentMainApiPath}
            normalizeMainApiPath={normalizeMainApiPath}
            mainApiPathOptions={mainApiPathOptions}
            currentMainApiOption={currentMainApiOption}
            reasoningEffortOptions={reasoningEffortOptions}
            defaultExportPath={defaultExportPath}
            setDefaultExportPath={setDefaultExportPath}
            handlePickExportDirectory={handlePickExportDirectory}
            targetWordOptions={targetWordOptions}
            defaultTargetWords={defaultTargetWords}
            setDefaultTargetWords={setDefaultTargetWords}
            createStoryPlan={createStoryPlan}
            testingApi={testingApi}
            busy={busy}
            testCurrentApiConfig={testCurrentApiConfig}
            saveConfig={saveConfig}
            logs={logs}
            clearLogs={clearLogs}
          />
        )}

        {menu === "novels" && novelManagerTab === "create" && (
          <section className="grid">
            <div className="panel full">
              <div className="section-heading">
                <div>
                  <p className="overline">小说管理</p>
                  <h2>创建小说（初始化）</h2>
                </div>
                <button className="ghost" onClick={() => setNovelManagerTab("detail")}>
                  前往小说详情
                </button>
              </div>
              <div className="row">
                <label>
                  小说名
                  <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="例如：霜河旧梦" />
                </label>
                <label>
                  一句话梗概
                  <input maxLength={200} value={newSynopsis} onChange={(e) => setNewSynopsis(e.target.value.slice(0, 200))} placeholder="一句话概括设定" />
                  <div className="hint">{newSynopsis.length}/200</div>
                </label>
                <label>
                  文风
                  <input value={newStyle} onChange={(e) => setNewStyle(e.target.value)} placeholder="可自由修改文风内容" />
                </label>
                <label>
                  目标字数
                  <input type="number" min="10000" step="10000" value={newNovelTargetWords || 500000} onChange={(e) => setNewNovelTargetWords(Number(e.target.value) || 500000)} />
                </label>
              </div>
              <div className="inline-chip-row">
                {styleOptions.map((opt) => (
                  <button key={opt} type="button" className="ghost chip" onClick={() => setNewStyle(opt)}>
                    {opt}
                  </button>
                ))}
              </div>
              <div className="inline-chip-row">
                {targetWordOptions.map((value) => (
                  <button key={`create-target-${value}`} type="button" className="ghost chip" onClick={() => setNewNovelTargetWords(value)}>
                    {value / 10000}万
                  </button>
                ))}
              </div>
              <div className="hint">预计总事件 {createStoryPlan.targetEventCount} / 开篇 {createStoryPlan.openingBreakthroughCount} / 发展 {createStoryPlan.openingBreakthroughCount + 1}-{createStoryPlan.developmentEndEventId} / 结局 {createStoryPlan.endingStartEventId}-{createStoryPlan.targetEventCount}</div>
              <div className="modal-actions">
                <button className="ghost" onClick={() => createNovel(false)} disabled={busy}>仅创建小说</button>
                <button className="primary" onClick={() => createNovel(true)} disabled={busy}>创建并一键初始化</button>
              </div>
            </div>

            <div className="panel full">
              <div className="section-heading">
                <div>
                  <p className="overline">初始化工作台</p>
                  <h2>初始化步骤</h2>
                </div>
                {selectedNovel && <div className="section-actions"><button className="primary" onClick={() => runInitAll()} disabled={busy || !!initRunningStep}>{initRunningStep ? `执行中：${initRunningStep}` : "一键自动初始化"}</button></div>}
              </div>
              {selectedNovel ? (
                <>
                  <div className="stats compact-stats">
                    {Object.entries(initStepLabels).map(([stepKey, label]) => (
                      <div key={`init-state-${stepKey}`}>
                        <span>{label}</span>
                        <strong>{initStepStateLabels[initStepStatus[stepKey]] || "过期"}</strong>
                      </div>
                    ))}
                  </div>
                  <div className="inline-chip-row">
                    <button className="ghost chip" onClick={() => runInitStep("world_setting")} disabled={busy}>1. 世界设定</button>
                    <button className="ghost chip" onClick={() => runInitStep("series_blueprint")} disabled={busy || initStepStatus.world_setting === "stale"}>2. 阶段计划</button>
                    <button className="ghost chip" onClick={() => runInitStep("growth_system")} disabled={busy || initStepStatus.series_blueprint === "stale"}>3. 成长规划</button>
                    <button className="ghost chip" onClick={() => runInitStep("core_characters")} disabled={busy || initStepStatus.growth_system === "stale"}>4. 核心人物卡</button>
                    <button className="ghost chip" onClick={() => runInitStep("worldview_summary")} disabled={busy || initStepStatus.core_characters === "stale"}>5. 世界摘要</button>
                    <button className="ghost chip" onClick={() => runInitStep("opening_snapshot")} disabled={busy || initStepStatus.worldview_summary === "stale"}>6. 世界快照</button>
                    <button className="ghost chip" onClick={() => runInitStep("opening_world_planning")} disabled={busy || initStepStatus.opening_snapshot === "stale"}>7. 事件规划</button>
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  <strong>先选择小说再初始化</strong>
                  <p>左上角选择已有小说，或先创建一个新小说。</p>
                </div>
              )}
            </div>
          </section>
        )}

        {menu === "novels" && novelManagerTab === "detail" && (
          <NovelDetailPage
            hasNovelSelection={hasNovelSelection}
            redirectToCreateNovel={redirectToCreateNovel}
            currentNovel={currentNovel}
            novelDetailTabs={novelDetailTabs}
            novelDetailTab={novelDetailTab}
            setNovelDetailTab={setNovelDetailTab}
            novelDetailTabLabels={novelDetailTabLabels}
            storyPhaseLabels={storyPhaseLabels}
            exportSection={exportSection}
            worldviewSummary={worldviewSummary}
            openingSnapshot={openingSnapshot}
            worldview={worldview}
            worldItemRows={worldItemRows}
            triggerImport={triggerImport}
            eventLorebookUpdateRows={eventLorebookUpdateRows}
            characterQuery={characterQuery}
            setCharacterQuery={setCharacterQuery}
            characterTierFilter={characterTierFilter}
            setCharacterTierFilter={setCharacterTierFilter}
            filteredCharacters={filteredCharacters}
            sortedCharacters={sortedCharacters}
            setEditingCharacter={setEditingCharacter}
            toggleLock={toggleLock}
            seriesBlueprint={seriesBlueprint}
            growthSystem={growthSystem}
            growthSnapshot={growthSnapshot}
            eventQuery={eventQuery}
            setEventQuery={setEventQuery}
            eventStatusFilter={eventStatusFilter}
            setEventStatusFilter={setEventStatusFilter}
            filteredEvents={filteredEvents}
            events={events}
            setEditingEvent={setEditingEvent}
            foreshadows={foreshadows}
            chapters={chapters}
            chapterQuery={chapterQuery}
            setChapterQuery={setChapterQuery}
            selectedChapter={selectedChapter}
            setSelectedChapter={setSelectedChapter}
            filteredChapters={filteredChapters}
            currentChapter={currentChapter}
            setEditingChapter={setEditingChapter}
            deleteNovelById={deleteNovelById}
            clearChaptersByNovel={clearChaptersByNovel}
            deleteSingleChapter={deleteSingleChapter}
          />
        )}

        {menu === "production" && (
          <ProductionPage
            productionTab={productionTab}
            selectedNovel={selectedNovel}
            setSelectedNovel={setSelectedNovel}
            novels={novels}
            events={events}
            currentNovel={currentNovel}
            storyPhaseLabels={storyPhaseLabels}
            dashboard={dashboard}
            selectedStoryPlan={selectedStoryPlan}
            genCount={genCount}
            setGenCount={setGenCount}
            runChapters={runChapters}
            jobList={jobList}
            clearJobs={clearJobs}
            deleteJob={deleteJob}
            loadJobs={loadJobs}
            chapters={chapters}
            logs={logs}
            clearLogs={clearLogs}
          />
        )}

        {menu === "prompts" && (
          <PromptWorkspace
            visiblePromptKeys={visiblePromptKeys}
            promptMenu={promptMenu}
            setPromptMenu={setPromptMenu}
            promptLabels={promptLabels}
            selectedNovel={selectedNovel}
            promptScope={promptScope}
            currentPromptMeta={currentPromptMeta}
            promptValue={promptValue}
            prompts={prompts}
            setPrompts={setPrompts}
            promptBackups={promptBackups}
            restorePromptBackup={restorePromptBackup}
            savePrompts={savePrompts}
            resetCurrentPrompt={resetCurrentPrompt}
            resetPrompts={resetPrompts}
          />
        )}
      </main>

      {showProgress && (
        <div className="modal">
          <div className="modal-card">
            <h3>初始化小说</h3>
            <p>{progressStep}</p>
            <div className="progress">
              <div className="progress-bar" style={{ width: `${progress}%` }} />
            </div>
            <div className="progress-text">{progress}%</div>
            {progressReady && (
              <button className="primary" onClick={() => setShowProgress(false)}>
                确认
              </button>
            )}
          </div>
        </div>
      )}

      <CharacterDrawer
        editingCharacter={editingCharacter}
        setEditingCharacter={setEditingCharacter}
        selectedNovel={selectedNovel}
        loadNovelDetails={loadNovelDetails}
        editListField={editListField}
        parseListField={parseListField}
      />

      <EventDrawer
        editingEvent={editingEvent}
        setEditingEvent={setEditingEvent}
        selectedNovel={selectedNovel}
        loadNovelDetails={loadNovelDetails}
        fetchEventCheckpoints={fetchEventCheckpoints}
        rewriteEventFromCheckpoint={rewriteEventFromCheckpoint}
        notify={notify}
        confirmAction={confirmAction}
      />

      <ChapterDrawer
        editingChapter={editingChapter}
        setEditingChapter={setEditingChapter}
        selectedNovel={selectedNovel}
        loadNovelDetails={loadNovelDetails}
      />

      {pendingImportSection && (
        <div className="modal">
          <div className="modal-card">
            <h3>导入数据</h3>
            <div className="hint">当前导入目标：{pendingImportSection}</div>
            <input
              type="file"
              accept={pendingImportSection === "worldview" ? ".txt" : ".csv"}
              onChange={(e) => setPendingImportFile(e.target.files?.[0] || null)}
            />
            <div className="modal-actions">
              <button
                className="ghost"
                onClick={() => {
                  setPendingImportSection(null);
                  setPendingImportFile(null);
                }}
              >
                取消
              </button>
              <button
                className="primary"
                disabled={!pendingImportFile}
                onClick={() => importSection(pendingImportSection, pendingImportFile)}
              >
                确认导入
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmState && (
        <div className="modal">
          <div className="modal-card">
            <h3>请确认</h3>
            <div className="hint confirm-text">{confirmState.message}</div>
            <div className="modal-actions">
              <button className="ghost" onClick={confirmState.onCancel}>
                取消
              </button>
              <button className="primary" onClick={confirmState.onConfirm}>
                确认
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className={`toast toast-${toast.type || "info"}`}>
          {toast.message}
        </div>
      )}
    </div>
  );
}

export default App;
