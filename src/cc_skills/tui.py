from __future__ import annotations

import curses
import unicodedata
from dataclasses import dataclass

from cc_skills.clipboard import copy_text
from cc_skills.core import (
    PluginInfo,
    Skill,
    UsageInfo,
    format_usage,
    record_usage,
    sort_skills,
    top_frequent,
    top_recent,
)


def char_width(char: str) -> int:
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def display_width(text: str) -> int:
    return sum(char_width(char) for char in text)


def trim_to_width(text: str, width: int) -> str:
    if width <= 0:
        return ""

    result = []
    current = 0
    for char in text:
        next_width = current + char_width(char)
        if next_width > width:
            break
        result.append(char)
        current = next_width

    trimmed = "".join(result)
    if trimmed == text:
        return trimmed

    ellipsis = "…"
    while display_width(trimmed + ellipsis) > width and trimmed:
        trimmed = trimmed[:-1]
    return trimmed + ellipsis if trimmed else ellipsis


def clip_plain(text: str, width: int) -> str:
    if width <= 0:
        return ""

    result = []
    current = 0
    for char in text:
        next_width = current + char_width(char)
        if next_width > width:
            break
        result.append(char)
        current = next_width
    return "".join(result)


def pad_to_width(text: str, width: int) -> str:
    text = trim_to_width(text, width)
    return text + " " * max(0, width - display_width(text))


def crop_line(text: str, width: int) -> str:
    return trim_to_width(text, width)


def safe_addstr(
    stdscr: curses.window,
    row: int,
    col: int,
    text: str,
    attr: int = curses.A_NORMAL,
) -> None:
    height, width = stdscr.getmaxyx()
    if row < 0 or row >= height or col >= width:
        return

    writable = max(0, width - col - 1)
    if writable <= 0:
        return

    try:
        stdscr.addstr(row, col, clip_plain(text, writable), attr)
    except curses.error:
        pass


def safe_hline(stdscr: curses.window, row: int, col: int, width: int) -> None:
    height, max_width = stdscr.getmaxyx()
    if row < 0 or row >= height or col >= max_width:
        return

    writable = max(0, min(width, max_width - col - 1))
    if writable <= 0:
        return

    try:
        stdscr.hline(row, col, "-", writable)
    except curses.error:
        pass


def wrap_text(prefix: str, text: str, width: int, max_lines: int) -> list[str]:
    if width <= 0 or max_lines <= 0:
        return []

    available = max(1, width - display_width(prefix))
    chunks: list[str] = []
    raw = text.replace("`", "").strip()

    while raw:
        part = trim_to_width(raw, available)
        if not part:
            break
        clean = part[:-1] if part.endswith("…") else part
        chunks.append(clean)
        raw = raw[len(clean) :].lstrip()
        if len(chunks) >= max_lines:
            break

    if not chunks:
        return [crop_line(prefix, width)]

    lines = [crop_line(prefix + chunks[0], width)]
    continuation_prefix = " " * display_width(prefix)
    for chunk in chunks[1:max_lines]:
        lines.append(crop_line(continuation_prefix + chunk, width))
    return lines[:max_lines]


def build_summary_line(label: str, skills: list[Skill], width: int) -> str:
    if not skills:
        return crop_line(f"{label}: 暂无", width)

    base = f"{label}: "
    text = base + "  ".join(skill.command for skill in skills)
    return crop_line(text, width)


def build_plugin_summary_line(label: str, plugins: list[PluginInfo], width: int) -> str:
    if not plugins:
        return crop_line(f"{label}: 暂无", width)

    base = f"{label}: "
    text = base + "  ".join(plugin.summary for plugin in plugins)
    return crop_line(text, width)


@dataclass
class PickerResult:
    copied_command: str | None = None


class SkillPickerApp:
    def __init__(
        self,
        skills: list[Skill],
        usage_map: dict[str, UsageInfo],
        plugins: list[PluginInfo],
        usage_path,
    ) -> None:
        self.skills = skills
        self.usage_map = usage_map
        self.plugins = plugins
        self.usage_path = usage_path
        self.query = ""
        self.selected_index = 0
        self.scroll_offset = 0
        self.status_message = ""

    def run(self) -> PickerResult:
        copied_command = curses.wrapper(self._main)
        return PickerResult(copied_command=copied_command)

    def _main(self, stdscr: curses.window) -> str | None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        stdscr.keypad(True)

        while True:
            visible_skills = sort_skills(self.skills, self.usage_map, self.query)
            if self.selected_index >= len(visible_skills):
                self.selected_index = max(0, len(visible_skills) - 1)

            self._render(stdscr, visible_skills)
            key = stdscr.get_wch()

            if key == curses.KEY_RESIZE:
                continue

            if key in ("q", "\x1b"):
                return None

            if key in ("\n", "\r") or key == curses.KEY_ENTER:
                if not visible_skills:
                    continue

                selected = visible_skills[self.selected_index]
                try:
                    copy_text(selected.command)
                    self.usage_map = record_usage(selected.name, self.usage_path)
                    return selected.command
                except Exception as exc:  # pragma: no cover - runtime guard
                    self.status_message = f"复制失败: {exc}"
                    continue

            if key == curses.KEY_UP or key == "k":
                self.selected_index = max(0, self.selected_index - 1)
                continue

            if key == curses.KEY_DOWN or key == "j":
                self.selected_index = min(max(0, len(visible_skills) - 1), self.selected_index + 1)
                continue

            if key == curses.KEY_BACKSPACE or key in ("\b", "\x7f"):
                self.query = self.query[:-1]
                self.selected_index = 0
                self.scroll_offset = 0
                continue

            if key == "\x15":
                self.query = ""
                self.selected_index = 0
                self.scroll_offset = 0
                continue

            if isinstance(key, str) and key.isprintable():
                self.query += key
                self.selected_index = 0
                self.scroll_offset = 0

    def _render(self, stdscr: curses.window, visible_skills: list[Skill]) -> None:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        if height < 9 or width < 24:
            safe_addstr(stdscr, 0, 0, "终端窗口太小，请放大后再试")
            stdscr.refresh()
            return

        preview_height = min(7, max(5, height // 3))
        list_top = 6
        list_height = max(3, height - list_top - preview_height)
        preview_top = list_top + list_height

        recent = top_recent(self.skills, self.usage_map)
        frequent = top_frequent(self.skills, self.usage_map)
        selected_skill = visible_skills[self.selected_index] if visible_skills else None

        title = f"cc-skills | 搜索: {self.query or '输入关键字...'}"
        help_text = self.status_message or "Enter 复制  |  ↑↓ / j k 导航  |  Backspace 删除搜索词  |  q / Esc 退出"

        safe_addstr(stdscr, 0, 0, title, curses.A_BOLD)
        safe_addstr(stdscr, 1, 0, help_text)
        safe_addstr(stdscr, 2, 0, build_summary_line("最近使用", recent, width))
        safe_addstr(stdscr, 3, 0, build_summary_line("最常用", frequent, width))
        safe_addstr(stdscr, 4, 0, build_plugin_summary_line("插件命令", self.plugins, width))
        safe_hline(stdscr, 5, 0, width)

        self._ensure_scroll(list_height, len(visible_skills))
        self._draw_list(stdscr, visible_skills, list_top, list_height, width)

        safe_hline(stdscr, preview_top, 0, width)
        self._draw_preview(stdscr, selected_skill, preview_top + 1, height - preview_top - 1, width)
        stdscr.refresh()

    def _ensure_scroll(self, list_height: int, total: int) -> None:
        if total <= 0:
            self.scroll_offset = 0
            return

        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
        elif self.selected_index >= self.scroll_offset + list_height:
            self.scroll_offset = self.selected_index - list_height + 1

    def _draw_list(
        self,
        stdscr: curses.window,
        skills: list[Skill],
        top: int,
        height: int,
        width: int,
    ) -> None:
        if not skills:
            safe_addstr(stdscr, top, 0, "没有匹配的 skills", curses.A_DIM)
            return

        name_width = min(30, max(18, width // 3))
        short_width = max(8, width - 4 - name_width - 2)
        visible = skills[self.scroll_offset : self.scroll_offset + height]

        for offset, skill in enumerate(visible):
            line_no = top + offset
            is_selected = self.scroll_offset + offset == self.selected_index
            marker = "> " if is_selected else "  "
            line = marker + pad_to_width(skill.name, name_width) + "  " + trim_to_width(skill.short, short_width)
            attr = curses.A_REVERSE if is_selected else curses.A_NORMAL
            safe_addstr(stdscr, line_no, 0, pad_to_width(line, width), attr)

    def _draw_preview(
        self,
        stdscr: curses.window,
        skill: Skill | None,
        top: int,
        height: int,
        width: int,
    ) -> None:
        if height <= 0:
            return

        if not skill:
            safe_addstr(stdscr, top, 0, "预览区：选择一个 skill 查看详情", curses.A_DIM)
            return

        info = self.usage_map.get(skill.name)
        lines: list[str] = [
            crop_line(f"命令: {skill.command}", width),
            crop_line(f"来源: {skill.group_label} | 使用: {format_usage(info)}", width),
        ]

        remaining = max(0, height - len(lines))
        summary_lines = wrap_text("说明: ", skill.summary, width, min(2, remaining))
        lines.extend(summary_lines)
        remaining = max(0, height - len(lines))

        if remaining > 0 and skill.examples.strip():
            example = reformat_examples(skill.examples)
            lines.extend(wrap_text("触发: ", example, width, min(2, remaining)))
            remaining = max(0, height - len(lines))

        for index in range(height):
            content = lines[index] if index < len(lines) else ""
            safe_addstr(stdscr, top + index, 0, pad_to_width(content, width))


def reformat_examples(examples: str) -> str:
    text = examples.replace("“", "").replace("”", "")
    parts = [part.strip() for part in text.split("；") if part.strip()]
    return parts[0] if parts else text
