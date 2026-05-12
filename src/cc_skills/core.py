from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_CLAUDE_DIR = Path.home() / ".claude"
DEFAULT_AGENTS_SKILLS_DIR = Path.home() / ".agents" / "skills"
DEFAULT_USAGE_RELATIVE_PATH = Path(".cache") / "cc-skills" / "skills-usage.json"
RECENT_LIMIT = 5
FREQUENT_LIMIT = 5
RESOURCE_DIR = Path(__file__).with_name("resources")
SCAN_DEFAULTS_PATH = RESOURCE_DIR / "scan_defaults.json"
DISPLAY_OVERRIDES_PATH = RESOURCE_DIR / "display_overrides.json"
PROJECT_ROOT_MARKERS = (
    ".claude",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    ".git",
)

def load_display_overrides(path: Path = DISPLAY_OVERRIDES_PATH) -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    raw_entries = payload.get("entries", payload)
    if not isinstance(raw_entries, dict):
        return {}

    overrides: dict[str, dict[str, str]] = {}
    for name, raw_data in raw_entries.items():
        if not isinstance(raw_data, dict):
            continue
        entry: dict[str, str] = {}
        for field in ("short", "summary", "examples"):
            if field in raw_data and raw_data[field] is not None:
                entry[field] = str(raw_data[field])
        if entry:
            overrides[str(name)] = entry
    return overrides


DISPLAY_OVERRIDES = load_display_overrides()


@dataclass(slots=True)
class Skill:
    directory: str
    name: str
    short: str
    summary: str
    examples: str
    scenes: str
    group: str
    group_label: str
    order: int

    @property
    def command(self) -> str:
        return f"/{self.name}"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Skill":
        return cls(
            directory=str(data["directory"]),
            name=str(data["name"]),
            short=str(data["short"]),
            summary=str(data["summary"]),
            examples=str(data["examples"]),
            scenes=str(data["scenes"]),
            group=str(data["group"]),
            group_label=str(data["group_label"]),
            order=int(data["order"]),
        )


@dataclass(slots=True)
class PluginInfo:
    name: str
    marketplace: str
    has_skills: bool
    skill_count: int

    @property
    def command(self) -> str:
        return f"/{self.name}"

    @property
    def summary(self) -> str:
        if self.has_skills:
            return f"{self.command}({self.skill_count})"
        return f"{self.command}(无 skill)"


@dataclass(slots=True)
class ScanConfig:
    ignore_skill_rules: tuple[tuple[str, str], ...] = ()


@dataclass(slots=True)
class SkillCatalog:
    skills: list[Skill]
    plugins: list[PluginInfo]
    scan_config: ScanConfig


@dataclass(slots=True)
class UsageInfo:
    use_count: int = 0
    last_used_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "use_count": self.use_count,
            "last_used_at": self.last_used_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "UsageInfo":
        return cls(
            use_count=int(data.get("use_count", 0)),
            last_used_at=str(data["last_used_at"]) if data.get("last_used_at") else None,
        )

    def touch(self) -> None:
        self.use_count += 1
        self.last_used_at = datetime.now().isoformat(timespec="seconds")


def build_short_label(name: str, summary: str) -> str:
    override = DISPLAY_OVERRIDES.get(name)
    if override and override.get("short"):
        return override["short"]

    text = summary.strip().strip('"').strip("'")
    if not text:
        return name

    prefixes = [
        "Use when you have ",
        "Use when you're ",
        "Use when you are ",
        "Use when starting ",
        "Use when encountering ",
        "Use when implementing ",
        "Use when creating ",
        "Use when receiving ",
        "Use when completing ",
        "Use when about to ",
        "Use when ",
        "Use this skill to ",
        "You MUST use this before ",
    ]

    lowered = text.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix.lower()):
            text = text[len(prefix) :].strip()
            break

    for separator in [" - ", " — ", ". ", "。", ";", "；", ",", "，", ": ", "："]:
        if separator in text:
            text = text.split(separator, 1)[0].strip()
            break

    text = re.sub(r"^(to |for |before )", "", text, flags=re.IGNORECASE).strip()
    return text[:28] or name


def _ignore_rules_from_list(raw: list[object]) -> tuple[tuple[str, str], ...]:
    rules: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type", "")).strip().lower()
        value = str(item.get("value", "")).strip()
        if kind in {"prefix", "namespace"} and value:
            rules.append((kind, value))
    return tuple(rules)


def load_builtin_ignore_skill_rules(path: Path = SCAN_DEFAULTS_PATH) -> tuple[tuple[str, str], ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return ()

    raw = payload.get("ignoreSkillRules", [])
    if not isinstance(raw, list):
        return ()

    return _ignore_rules_from_list(raw)


def parse_ignore_skill_rules(raw: object) -> tuple[tuple[str, str], ...] | None:
    if not isinstance(raw, list):
        return None

    return _ignore_rules_from_list(raw)


def resolve_ignore_skill_rules(merged: dict[str, object]) -> tuple[tuple[str, str], ...]:
    if "ignoreSkillRules" in merged:
        parsed = parse_ignore_skill_rules(merged["ignoreSkillRules"])
        if parsed is not None:
            return parsed
    return load_builtin_ignore_skill_rules()


def should_ignore_skill(
    raw_name: str,
    namespace: str | None,
    ignore_rules: tuple[tuple[str, str], ...],
) -> bool:
    lowered = raw_name.lower()
    for kind, value in ignore_rules:
        if kind == "prefix" and lowered.startswith(value.lower()):
            return True
        if kind == "namespace" and namespace is not None and namespace.lower() == value.lower():
            return True
    return False


def load_json_file(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def normalize_frontmatter_value(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    return " ".join(text.split())


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    frontmatter: dict[str, str] = {}
    current_key: str | None = None
    body_start = 0

    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == "---":
            body_start = index + 1
            break

        if not line.strip():
            continue

        matched = re.match(r"^([A-Za-z0-9_-]+):(.*)$", line)
        if matched:
            current_key = matched.group(1)
            frontmatter[current_key] = normalize_frontmatter_value(matched.group(2))
            continue

        if current_key and (line.startswith(" ") or line.startswith("\t")):
            frontmatter[current_key] = (
                frontmatter[current_key] + " " + normalize_frontmatter_value(line)
            ).strip()
        else:
            current_key = None
    else:
        return {}, text

    body = "\n".join(lines[body_start:])
    return frontmatter, body


def body_summary(markdown: str) -> str:
    chunks: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            if chunks:
                break
            continue

        if line.startswith("#") or (line.startswith("<") and line.endswith(">")):
            continue

        chunks.append(line.replace("`", ""))

    return " ".join(chunks).strip()


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    lowered = value.strip().lower()
    if lowered in {"true", "yes", "1"}:
        return True
    if lowered in {"false", "no", "0"}:
        return False
    return default


def make_skill(
    skill_file: Path,
    *,
    namespace: str | None,
    source_type: str,
    source_label: str,
    ignore_rules: tuple[tuple[str, str], ...] = (),
) -> Skill | None:
    text = skill_file.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(text)

    if not parse_bool(frontmatter.get("user-invocable"), True):
        return None

    raw_name = frontmatter.get("name") or skill_file.parent.name
    name = f"{namespace}:{raw_name}" if namespace else raw_name
    if should_ignore_skill(raw_name, namespace, ignore_rules):
        return None

    summary = frontmatter.get("description") or body_summary(body) or name
    when_to_use = frontmatter.get("when_to_use", "")
    override = DISPLAY_OVERRIDES.get(name)
    if override:
        summary = override.get("summary", summary)
        when_to_use = override.get("examples", when_to_use)

    return Skill(
        directory=skill_file.parent.name,
        name=name,
        short=build_short_label(name, summary),
        summary=summary,
        examples=when_to_use,
        scenes=str(skill_file),
        group=source_type,
        group_label=source_label,
        order=0,
    )


def settings_paths(start_dir: Path, claude_dir: Path) -> list[Path]:
    start_dir = start_dir.resolve()
    ancestors = list(reversed([start_dir, *start_dir.parents]))
    paths: list[Path] = []

    user_settings = claude_dir / "settings.json"
    if user_settings.exists():
        paths.append(user_settings)

    for base in ancestors:
        project_settings = base / ".claude" / "settings.json"
        if project_settings.exists() and project_settings not in paths:
            paths.append(project_settings)

    for base in ancestors:
        local_settings = base / ".claude" / "settings.local.json"
        if local_settings.exists() and local_settings not in paths:
            paths.append(local_settings)

    return paths


def extract_cc_skills_config(payload: dict[str, object]) -> dict[str, object]:
    config: dict[str, object] = {}
    for key in ("cc-skills", "ccSkills"):
        raw = payload.get(key)
        if isinstance(raw, dict):
            config.update(raw)
    return config


def load_scan_config(start_dir: Path, claude_dir: Path = DEFAULT_CLAUDE_DIR) -> ScanConfig:
    merged: dict[str, object] = {}
    for path in settings_paths(start_dir, claude_dir):
        payload = load_json_file(path)
        merged.update(extract_cc_skills_config(payload))

    return ScanConfig(ignore_skill_rules=resolve_ignore_skill_rules(merged))


def load_enabled_plugins(start_dir: Path, claude_dir: Path = DEFAULT_CLAUDE_DIR) -> set[str]:
    enabled: dict[str, bool] = {}
    for path in settings_paths(start_dir, claude_dir):
        payload = load_json_file(path)
        for plugin_key, value in dict(payload.get("enabledPlugins", {})).items():
            enabled[str(plugin_key)] = bool(value)

    return {plugin_key for plugin_key, is_enabled in enabled.items() if is_enabled}


def iter_skill_files(skill_dir: Path) -> list[Path]:
    if not skill_dir.is_dir():
        return []
    return sorted(skill_dir.glob("*/SKILL.md"), key=lambda path: path.parent.name.lower())


def resolve_project_root(start_dir: Path) -> Path:
    start_dir = start_dir.resolve()
    for base in [start_dir, *start_dir.parents]:
        if any((base / marker).exists() for marker in PROJECT_ROOT_MARKERS):
            return base
    return start_dir


def resolve_default_usage_path(start_dir: Path) -> Path:
    return resolve_project_root(start_dir) / DEFAULT_USAGE_RELATIVE_PATH


def normalize_usage_path(path: Path | None, start_dir: Path | None = None) -> Path:
    if path is not None:
        return path.expanduser().resolve()
    base_dir = Path.cwd() if start_dir is None else start_dir
    return resolve_default_usage_path(base_dir)


def discover_catalog(
    start_dir: Path,
    claude_dir: Path = DEFAULT_CLAUDE_DIR,
    *,
    agents_skills_dir: Path = DEFAULT_AGENTS_SKILLS_DIR,
) -> SkillCatalog:
    start_dir = start_dir.resolve()
    claude_dir = claude_dir.expanduser().resolve()
    agents_skills_dir = agents_skills_dir.expanduser().resolve()
    scan_config = load_scan_config(start_dir, claude_dir)
    ignore_rules = scan_config.ignore_skill_rules

    skills: list[Skill] = []
    plugins: list[PluginInfo] = []
    seen: set[str] = set()

    def append(skill: Skill | None) -> None:
        if skill is None or skill.name in seen:
            return
        skill.order = len(skills)
        skills.append(skill)
        seen.add(skill.name)

    for skill_file in iter_skill_files(agents_skills_dir):
        append(
            make_skill(
                skill_file,
                namespace=None,
                source_type="global",
                source_label="全局 / agents",
                ignore_rules=ignore_rules,
            )
        )

    for skill_file in iter_skill_files(claude_dir / "skills"):
        append(
            make_skill(
                skill_file,
                namespace=None,
                source_type="global",
                source_label="全局 / claude",
                ignore_rules=ignore_rules,
            )
        )

    for base in [start_dir, *start_dir.parents]:
        for skill_file in iter_skill_files(base / ".claude" / "skills"):
            append(
                make_skill(
                    skill_file,
                    namespace=None,
                    source_type="project",
                    source_label="项目",
                    ignore_rules=ignore_rules,
                )
            )

    enabled_plugins = load_enabled_plugins(start_dir, claude_dir)
    cache_dir = claude_dir / "plugins" / "cache"
    for plugin_key in sorted(enabled_plugins):
        plugin_name, _, marketplace_name = plugin_key.partition("@")
        plugin_root = cache_dir / marketplace_name / plugin_name
        plugin_seen: set[str] = set()
        skill_files: list[Path] = []
        if plugin_root.exists():
            skill_files = sorted(
                plugin_root.glob("**/skills/*/SKILL.md"),
                key=lambda path: (path.stat().st_mtime, str(path)),
                reverse=True,
            )
        for skill_file in skill_files:
            skill = make_skill(
                skill_file,
                namespace=plugin_name,
                source_type="plugin",
                source_label=f"插件 / {plugin_name}",
                ignore_rules=ignore_rules,
            )
            if skill is None or skill.name in plugin_seen:
                continue
            plugin_seen.add(skill.name)
            append(skill)

        plugins.append(
            PluginInfo(
                name=plugin_name,
                marketplace=marketplace_name,
                has_skills=bool(plugin_seen),
                skill_count=len(plugin_seen),
            )
        )

    return SkillCatalog(skills=skills, plugins=plugins, scan_config=scan_config)


def discover_skills(
    start_dir: Path,
    claude_dir: Path = DEFAULT_CLAUDE_DIR,
    *,
    agents_skills_dir: Path = DEFAULT_AGENTS_SKILLS_DIR,
) -> list[Skill]:
    return discover_catalog(start_dir, claude_dir, agents_skills_dir=agents_skills_dir).skills


def load_usage(path: Path | None = None) -> dict[str, UsageInfo]:
    path = normalize_usage_path(path)
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    skills = payload.get("skills", {})
    usage: dict[str, UsageInfo] = {}
    for name, data in skills.items():
        usage[str(name)] = UsageInfo.from_dict(data)
    return usage


def save_usage(usage: dict[str, UsageInfo], path: Path | None = None) -> None:
    path = normalize_usage_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "skills": {name: info.to_dict() for name, info in usage.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def record_usage(skill_name: str, path: Path | None = None) -> dict[str, UsageInfo]:
    path = normalize_usage_path(path)
    usage = load_usage(path)
    info = usage.setdefault(skill_name, UsageInfo())
    info.touch()
    save_usage(usage, path)
    return usage


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def recency_score(info: UsageInfo | None) -> int:
    if not info or not info.last_used_at:
        return 0

    last_used = parse_datetime(info.last_used_at)
    if not last_used:
        return 0

    delta = datetime.now() - last_used
    minutes = delta.total_seconds() / 60
    if minutes <= 60:
        return 5
    if minutes <= 1440:
        return 4
    if minutes <= 10080:
        return 3
    if minutes <= 43200:
        return 2
    return 1


def text_score(text: str, query: str, weight: int) -> int:
    if not query or not text:
        return 0

    if text == query:
        return weight + 90
    if text.startswith(query):
        return weight + 50
    if query in text:
        return weight
    return 0


def rank_for_query(skill: Skill, usage: UsageInfo | None, query: str) -> tuple[int, int, str] | None:
    query = query.strip().lower()
    if not query:
        score = (usage.use_count if usage else 0) * 20 + recency_score(usage) * 5
        return (-score, skill.order, skill.name)

    fields = (
        (skill.name.lower(), 120),
        (skill.short.lower(), 110),
        (skill.directory.lower(), 95),
        (skill.summary.lower(), 80),
        (skill.group_label.lower(), 30),
        (skill.examples.lower(), 25),
        (skill.scenes.lower(), 20),
    )

    total = 0
    for term in [part for part in query.split() if part]:
        term_best = 0
        for text, weight in fields:
            term_best = max(term_best, text_score(text, term, weight))
        if term_best == 0:
            return None
        total += term_best

    total += min(usage.use_count if usage else 0, 20) * 5
    total += recency_score(usage) * 3
    return (-total, skill.order, skill.name)


def sort_skills(skills: list[Skill], usage_map: dict[str, UsageInfo], query: str) -> list[Skill]:
    ranked: list[tuple[tuple[int, int, str], Skill]] = []
    for skill in skills:
        usage = usage_map.get(skill.name)
        rank = rank_for_query(skill, usage, query)
        if rank is None:
            continue
        ranked.append((rank, skill))

    ranked.sort(key=lambda item: item[0])
    return [skill for _, skill in ranked]


def top_recent(skills: list[Skill], usage_map: dict[str, UsageInfo], limit: int = RECENT_LIMIT) -> list[Skill]:
    skill_map = {skill.name: skill for skill in skills}
    items: list[tuple[datetime, Skill]] = []
    for name, info in usage_map.items():
        dt = parse_datetime(info.last_used_at)
        skill = skill_map.get(name)
        if dt and skill:
            items.append((dt, skill))

    items.sort(key=lambda item: item[0], reverse=True)
    return [skill for _, skill in items[:limit]]


def top_frequent(skills: list[Skill], usage_map: dict[str, UsageInfo], limit: int = FREQUENT_LIMIT) -> list[Skill]:
    skill_map = {skill.name: skill for skill in skills}
    items: list[tuple[int, datetime, Skill]] = []
    for name, info in usage_map.items():
        skill = skill_map.get(name)
        if not skill or info.use_count <= 0:
            continue
        last_used = parse_datetime(info.last_used_at) or datetime.min
        items.append((info.use_count, last_used, skill))

    items.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [skill for _, _, skill in items[:limit]]


def format_usage(info: UsageInfo | None) -> str:
    if not info or info.use_count <= 0:
        return "0 次"

    if info.last_used_at:
        return f"{info.use_count} 次 · 最近 {info.last_used_at.replace('T', ' ')}"
    return f"{info.use_count} 次"
