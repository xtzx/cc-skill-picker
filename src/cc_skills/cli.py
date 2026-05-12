from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cc_skills.core import (
    DEFAULT_CLAUDE_DIR,
    discover_catalog,
    load_usage,
    normalize_usage_path,
)
from cc_skills.tui import SkillPickerApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="终端内 skills 搜索与复制工具")
    parser.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="扫描项目 skills 的起始目录，默认当前目录",
    )
    parser.add_argument(
        "--claude-dir",
        type=Path,
        default=DEFAULT_CLAUDE_DIR,
        help="Claude 配置目录，默认 ~/.claude，用于 settings、插件缓存与兼容 skills 源",
    )
    parser.add_argument(
        "--usage",
        type=Path,
        default=None,
        help="usage 记录路径，默认 <项目根>/.cache/cc-skills/skills-usage.json",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    usage_path = normalize_usage_path(args.usage, args.cwd)

    try:
        catalog = discover_catalog(args.cwd, args.claude_dir)
        usage = load_usage(usage_path)
    except Exception as exc:
        print(f"[cc-skills] 初始化失败: {exc}", file=sys.stderr)
        return 1

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("[cc-skills] 需要在交互式终端中运行", file=sys.stderr)
        return 1

    try:
        result = SkillPickerApp(catalog.skills, usage, catalog.plugins, usage_path=usage_path).run()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"[cc-skills] 运行失败: {exc}", file=sys.stderr)
        return 1

    if result.copied_command:
        print(f"已复制 {result.copied_command}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
