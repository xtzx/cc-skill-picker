# cc-skills

在终端里快速搜索 Claude 当前可用的 **skills**，回车复制 `/<skill-name>`；已启用的 **插件** 单独展示为 **`/插件名`** 命令（不混入 skill 列表）。

依赖极少：仅用 Python 标准库（含 `curses`），无第三方包。

---

## 功能概览

- 命令：`cc-skills`，短别名：`ccs`
- 扫描 Claude 侧真实存在的 `SKILL.md` 技能条目
- 列表优先使用内置中文短说明与完整说明；未配置映射时回退英文
- 默认过滤规则来自 `src/cc_skills/resources/scan_defaults.json` 的 **`ignoreSkillRules`**
- 使用频次与最近使用参与排序；usage 默认落在项目目录下
- 已启用插件在 TUI 顶部以 **插件命令** 形式展示（如 `/ralph-loop`）；无 `SKILL.md` 的插件不会出现在可搜索 skill 列表中

---

## 项目结构

```
cc-skill-picker/
├── README.md
├── LICENSE
├── pyproject.toml
├── cc-skills                 # 本地入口脚本（设置 PYTHONPATH 后调 cli）
├── .gitignore
├── src/cc_skills/
│   ├── cli.py                # 命令行入口
│   ├── core.py               # 扫描、过滤、usage、排序
│   ├── tui.py                # curses 界面
│   ├── clipboard.py          # 剪贴板
│   └── resources/
│       ├── scan_defaults.json      # 内置 ignoreSkillRules
│       └── display_overrides.json  # 内置中文展示映射
└── tests/
    └── test_core.py
```

安装可编辑包后可能生成 `src/cc_skills.egg-info/`（已在 `.gitignore` 中忽略）；可随时删掉后执行 `pip install -e .` 重建。

---

## 运行与安装

> 平台支持：仅 macOS（剪贴板依赖系统自带的 `pbcopy`）。Linux / Windows 暂未适配。

直接从 Git 装（推荐，不用克隆）：

```bash
pip3 install "git+https://github.com/bjhl/cc-skill-picker.git"
# 或用 pipx / uv 独立环境
pipx install "git+https://github.com/bjhl/cc-skill-picker.git"
uv tool install "git+https://github.com/bjhl/cc-skill-picker.git"
```

克隆后本地运行（开发用）：

```bash
git clone https://github.com/bjhl/cc-skill-picker.git
cd cc-skill-picker
./cc-skills           # 不装也能用，入口脚本会把 src 加到 PYTHONPATH
```

可编辑安装到当前 Python 环境：

```bash
pip3 install -e .
cc-skills
# 或
ccs
```

查看参数：

```bash
cc-skills --help
```

---

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--cwd` | 扫描起始目录，默认当前工作目录；会向上查找 `.claude/skills` 与合并 `settings` |
| `--claude-dir` | Claude 配置根目录，默认 `~/.claude` |
| `--usage` | 使用记录 JSON 路径；不传则默认 `<项目根>/.cache/cc-skills/skills-usage.json` |

---

## 扫描范围

1. **全局**：`{claude_dir}/skills/*/SKILL.md`
2. **项目**：自 `--cwd` 起向父目录，每层 `.claude/skills/*/SKILL.md`
3. **插件**：读取合并后的 `enabledPlugins`，在 `{claude_dir}/plugins/cache/{marketplace}/{plugin}/**/skills/*/SKILL.md` 中查找

`settings` 合并顺序（后者覆盖同名字段，**不会删除**前者已写入的其它键）：

1. `~/.claude/settings.json`
2. 自 `--cwd` 向上各层的 `.claude/settings.json`
3. 自 `--cwd` 向上各层的 `.claude/settings.local.json`

---

## 过滤规则：`ignoreSkillRules`

内置默认在 **`src/cc_skills/resources/scan_defaults.json`**，每条规则：

- `{ "type": "prefix", "value": "lark-" }`：skill **自身名字**（不含命名空间）以该前缀开头则忽略
- `{ "type": "namespace", "value": "superpowers" }`：忽略形如 `superpowers:*` 的插件命名空间下全部 skill

在 Claude 的 `settings*.json` 里配置 **`cc-skills.ignoreSkillRules`** 时，会对「合并后的 `cc-skills` 对象」生效：若最终配置里**包含该键**，则**整表替换**内置规则（**不再**与 `scan_defaults.json` 叠加）。要关闭全部 skill 级别过滤，设为 `[]` 即可。

示例：

```json
{
  "cc-skills": {
    "ignoreSkillRules": [
      { "type": "prefix", "value": "lark-" },
      { "type": "prefix", "value": "document-" },
      { "type": "namespace", "value": "document-skills" },
      { "type": "namespace", "value": "superpowers" }
    ]
  }
}
```

当前版本**只支持** `ignoreSkillRules`。旧的 `ignoreSkillPrefixes` / `ignoreSkillNamespaces` 不再作为正式配置接口维护，也不会在 README 中继续说明。

---

## 使用记录（usage）

默认路径：

`<项目根>/.cache/cc-skills/skills-usage.json`

**项目根**定义为：从 `--cwd` 起向父目录查找，命中以下**任一**标记的最近一层目录：

- `.claude/`
- `pyproject.toml`
- `package.json`
- `go.mod`
- `Cargo.toml`
- `.git/`

自定义路径：

```bash
cc-skills --usage /your/path/skills-usage.json
```

> 说明：早期版本曾使用 `~/.cc-switch/skills/skills-usage.json`，当前已不再读取；若你已无其它工具依赖，可删除遗留文件。

---

## 内置数据文件（可随版本维护）

| 文件 | 作用 |
|------|------|
| `src/cc_skills/resources/scan_defaults.json` | 默认 `ignoreSkillRules` |
| `src/cc_skills/resources/display_overrides.json` | 列表/预览区中文 `short` / `summary` / `examples` |

安装包时由 `pyproject.toml` 的 `package-data` 一并打包；本地 `./cc-skills` 直接读源码旁文件即可。

---

## 键位（TUI）

- `Enter`：复制当前 skill 的 `/<name>` 并退出  
- `↑` / `↓` 或 `j` / `k`：移动选中  
- `Backspace`：删搜索字符  
- `Esc` / `q`：退出  

终端过小会提示放大；建议高度 **不少于约 9 行** 以便同时看到搜索区、插件命令行与列表。

---

## 中文展示映射

新增 skill **不必**立刻写中文映射；写了则列表与预览区优先用中文。

编辑 **`src/cc_skills/resources/display_overrides.json`**，在 `entries` 下按 skill 全名写键：

- 全局 / 项目 skill：如 `pdf`
- 插件 skill：如 `plugin-name:skill-name`（若该条目被默认过滤规则排除，则不会出现在列表里，映射仍可保留以备将来调整规则后生效）

### 维护规则

`display_overrides.json` 的数据不需要手写硬翻译，建议按下面的流程维护：

1. 先读取对应 skill 的 `SKILL.md`
2. 优先参考 frontmatter 的 `name`、`description`、`when_to_use`
3. 若 frontmatter 信息不足，再参考正文开头几段，提炼这个 skill 的典型用途
4. 可以用 LLM 辅助批量生成初稿，但建议人工统一润色，保证风格一致

字段建议：

- `short`：列表里的短描述，尽量 10-20 个字，偏动作导向
- `summary`：一句完整中文说明，重点写“这个 skill 适合拿来做什么”
- `examples`：2-4 个典型触发场景或用途关键词，便于搜索和理解

质量要求：

- 不要逐字翻译英文原文
- 不要写过空、过泛的描述
- 尽量保持整份文件语气和粒度一致
- 若某条 skill 当前被默认过滤，映射仍然可以保留，供后续调整规则时直接复用

示例（全局 skill）：

```json
{
  "entries": {
    "pdf": {
      "short": "读取拆分合并 OCR PDF",
      "summary": "读取、拆分、合并、OCR、提取表格、填表或加工 PDF 文档。",
      "examples": "读 PDF、合并文件、OCR 扫描件、提取表格"
    }
  }
}
```

可编辑安装（`pip install -e .`）下，改完 JSON 或 Python 后一般**无需重装**，重新运行 `ccs` / `cc-skills` 即可。

---

## 开发与测试

```bash
cd /path/to/cc-skills
python3 -m unittest tests.test_core
```

---

## 说明

- 本工具只面向 **交互式终端**（需 `stdin`/`stdout` 为 TTY）。  
- 插件命令（如 `/ralph-loop`）当前仅用于顶部展示与辨认，**选中复制**的仍是 skill 列表中的 `/<skill-name>`。
