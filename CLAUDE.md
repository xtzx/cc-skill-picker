# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

`cc-skills` 是一个纯 Python 标准库（含 `curses`）实现的终端 TUI，用于搜索 Claude Code 当前可用的 skills，回车把 `/<skill-name>` 复制到剪贴板。命令名 `cc-skills`，短别名 `ccs`。仅面向交互式 TTY，剪贴板依赖 macOS 的 `pbcopy`（见 `src/cc_skills/clipboard.py`）。

## 常用命令

```bash
# 本地直接运行（无需安装，入口脚本会把 src 加到 PYTHONPATH）
./cc-skills

# 可编辑安装后使用控制台脚本
pip3 install -e .
cc-skills            # 或 ccs

# 测试
python3 -m unittest tests.test_core
# 跑单个用例
python3 -m unittest tests.test_core.CoreTests.test_load_enabled_plugins_respects_settings_precedence
```

未提交 push，按用户全局约定只做本地 commit。

## 顶层架构

三层，全部在 `src/cc_skills/`：

- `cli.py`：argparse 入口。解析 `--cwd` / `--claude-dir` / `--usage`，调 `discover_catalog` 和 `load_usage`，把结果交给 `SkillPickerApp`。非 TTY 直接退出。
- `core.py`：业务核心。扫描 skill、合并 settings、应用忽略规则、维护 usage、排序打分。所有持久化数据模型（`Skill` / `PluginInfo` / `UsageInfo` / `ScanConfig` / `SkillCatalog`）都在这里。
- `tui.py`：`curses` 界面，含搜索框、插件命令行、skill 列表、预览区。通过 `record_usage` 把本次选中的 skill 记一次。剪贴板调用 `clipboard.copy_text`。

资源文件在 `src/cc_skills/resources/`，`pyproject.toml` 用 `package-data` 打包：

- `scan_defaults.json`：内置默认 `ignoreSkillRules`
- `display_overrides.json`：列表与预览的中文 `short` / `summary` / `examples` 映射

### 扫描与优先级（`core.discover_catalog`）

skill 来源，按此顺序合并（先写入者占位，后来同名跳过，由 `seen` 去重）：

1. **全局**：`{claude_dir}/skills/*/SKILL.md`（默认 `~/.claude/skills`）
2. **项目**：从 `--cwd` 起向父目录每一层 `./.claude/skills/*/SKILL.md`
3. **插件**：读取合并后的 `enabledPlugins`，在 `{claude_dir}/plugins/cache/{marketplace}/{plugin}/**/skills/*/SKILL.md` 下查找；插件 skill 用 `plugin-name:` 作为命名空间前缀

SKILL.md frontmatter 里 `user-invocable: false` 的会被 `make_skill` 跳过。

### `settings.json` 合并顺序（`core.settings_paths`）

后者覆盖前者**同名字段**，不删除其他键：

1. `{claude_dir}/settings.json`
2. `--cwd` 向上各层的 `.claude/settings.json`
3. `--cwd` 向上各层的 `.claude/settings.local.json`

只读取合并结果中的 `cc-skills` / `ccSkills` 对象（`extract_cc_skills_config`）以及 `enabledPlugins`。

### `ignoreSkillRules` 语义（容易踩坑）

`resolve_ignore_skill_rules` 的关键规则：**只要合并后的 `cc-skills` 对象里包含 `ignoreSkillRules` 这个键**（即使是 `[]`），就**整表替换**内置 `scan_defaults.json`，不做叠加。要关闭全部过滤就写 `"ignoreSkillRules": []`。规则形状：

- `{ "type": "prefix", "value": "lark-" }`：按 skill **自身名字**（不含命名空间）前缀匹配
- `{ "type": "namespace", "value": "superpowers" }`：匹配整个 `superpowers:*` 命名空间

旧字段 `ignoreSkillPrefixes` / `ignoreSkillNamespaces` 已不再维护，不要重新引入。

### usage 路径解析（`core.normalize_usage_path`）

- `--usage` 传了就 `expanduser().resolve()`
- 没传就从 `start_dir` 开始向上找项目根（命中 `.claude` / `pyproject.toml` / `package.json` / `go.mod` / `Cargo.toml` / `.git` 任一），落到 `<项目根>/.cache/cc-skills/skills-usage.json`

持久化 JSON 结构带 `version` 与 `updated_at`，条目挂在 `skills` 下（`save_usage`）。

### 排序打分（`core.rank_for_query`）

- 空 query：按 `use_count * 20 + recency_score * 5` 降序
- 有 query：按词分别在 name / short / directory / summary / group_label / examples / scenes 七个字段里取最大得分，任一词得 0 分则整个 skill 出局；之后叠加使用频次与 recency 加权
- `recency_score` 按「距上次使用的分钟数」分段：≤60min=5，≤24h=4，≤7d=3，≤30d=2，其余 1

改排序时要同时看 `sort_skills` / `top_recent` / `top_frequent`，TUI 顶部的"最近"与"高频"两行就是后两个函数喂的。

### 展示覆盖（`DISPLAY_OVERRIDES`）

`core.DISPLAY_OVERRIDES` 在模块导入时一次性从 `display_overrides.json` 读入。`make_skill` 会用它覆盖 `summary` 与 `examples`；`build_short_label` 会优先用其中的 `short`，否则对英文 `description` 做启发式裁剪（剥离 "Use when …" 前缀、取首句/首分隔符之前）。要调整中文展示，编辑 JSON 而不是改裁剪规则。

## 编辑约定（项目相关）

- 维持"只用标准库"这条边界，不要引入第三方依赖。
- 新增 skill 字段时，`Skill` 用 `@dataclass(slots=True)`，`to_dict` / `from_dict` 要同步。
- 改 `ignoreSkillRules` 的解析逻辑请同步更新 README 中"过滤规则"一节，避免文档与代码失配。
- 可编辑安装下改 JSON 或 Python 无需重装；改了 `pyproject.toml` 的 `package-data` 或依赖才需要重装。
