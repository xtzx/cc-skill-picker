from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cc_skills.core import (
    DISPLAY_OVERRIDES_PATH,
    PluginInfo,
    SCAN_DEFAULTS_PATH,
    Skill,
    UsageInfo,
    discover_catalog,
    discover_skills,
    load_usage,
    load_enabled_plugins,
    make_skill,
    record_usage,
    resolve_default_usage_path,
    sort_skills,
)


class CoreTests(unittest.TestCase):
    def test_load_enabled_plugins_respects_settings_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            claude_dir = root / ".claude"
            claude_dir.mkdir(parents=True)
            (claude_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "enabledPlugins": {
                            "alpha@market": True,
                            "beta@market": False,
                        }
                    }
                ),
                encoding="utf-8",
            )

            project = root / "project"
            (project / ".claude").mkdir(parents=True)
            (project / ".claude" / "settings.local.json").write_text(
                json.dumps(
                    {
                        "enabledPlugins": {
                            "beta@market": True,
                        }
                    }
                ),
                encoding="utf-8",
            )

            enabled = load_enabled_plugins(project, claude_dir)

        self.assertEqual(enabled, {"alpha@market", "beta@market"})

    def test_discover_catalog_filters_default_ignored_skill_series_and_exposes_plugin_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            claude_dir = root / ".claude"
            (claude_dir / "skills" / "global-skill").mkdir(parents=True)
            (claude_dir / "skills" / "global-skill" / "SKILL.md").write_text(
                """---
name: global-skill
description: Global helper
---
Body
""",
                encoding="utf-8",
            )
            (claude_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "enabledPlugins": {
                            "document-skills@market": True,
                            "superpowers@market": True,
                            "code-review@market": True,
                        }
                    }
                ),
                encoding="utf-8",
            )

            plugin_skill_dir = (
                claude_dir
                / "plugins"
                / "cache"
                / "market"
                / "document-skills"
                / "1.0.0"
                / "skills"
                / "algorithmic-art"
            )
            plugin_skill_dir.mkdir(parents=True)
            (plugin_skill_dir / "SKILL.md").write_text(
                """---
name: algorithmic-art
description: Create algorithmic art
when_to_use: generative art
---
Body
""",
                encoding="utf-8",
            )

            superpowers_skill_dir = (
                claude_dir
                / "plugins"
                / "cache"
                / "market"
                / "superpowers"
                / "1.0.0"
                / "skills"
                / "brainstorming"
            )
            superpowers_skill_dir.mkdir(parents=True)
            (superpowers_skill_dir / "SKILL.md").write_text(
                """---
name: brainstorming
description: Use when exploring ideas before implementation
---
Body
""",
                encoding="utf-8",
            )

            project = root / "project"
            (project / ".claude" / "skills" / "local-skill").mkdir(parents=True)
            (project / ".claude" / "skills" / "local-skill" / "SKILL.md").write_text(
                """---
name: local-skill
description: Local helper
---
Body
""",
                encoding="utf-8",
            )

            (project / ".claude" / "skills" / "lark-demo").mkdir(parents=True)
            (project / ".claude" / "skills" / "lark-demo" / "SKILL.md").write_text(
                """---
name: lark-demo
description: Lark helper
---
Body
""",
                encoding="utf-8",
            )

            catalog = discover_catalog(project, claude_dir)
            skill_map = {skill.name: skill for skill in catalog.skills}
            names = set(skill_map)
            plugins = {plugin.name: plugin for plugin in catalog.plugins}

        self.assertIn("global-skill", names)
        self.assertIn("local-skill", names)
        self.assertNotIn("lark-demo", names)
        self.assertNotIn("document-skills:algorithmic-art", names)
        self.assertNotIn("superpowers:brainstorming", names)
        self.assertIn("document-skills", plugins)
        self.assertFalse(plugins["document-skills"].has_skills)
        self.assertEqual(plugins["document-skills"].skill_count, 0)
        self.assertEqual(plugins["document-skills"].command, "/document-skills")
        self.assertEqual(plugins["document-skills"].summary, "/document-skills(无 skill)")
        self.assertIn("superpowers", plugins)
        self.assertFalse(plugins["superpowers"].has_skills)
        self.assertEqual(plugins["superpowers"].skill_count, 0)
        self.assertEqual(plugins["superpowers"].command, "/superpowers")
        self.assertEqual(plugins["superpowers"].summary, "/superpowers(无 skill)")
        self.assertIn("code-review", plugins)
        self.assertFalse(plugins["code-review"].has_skills)
        self.assertEqual(plugins["code-review"].skill_count, 0)
        self.assertEqual(plugins["code-review"].command, "/code-review")
        self.assertEqual(plugins["code-review"].summary, "/code-review(无 skill)")

    def test_discover_catalog_respects_ignore_skill_rules_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            claude_dir = root / ".claude"
            claude_dir.mkdir(parents=True)
            (claude_dir / "settings.json").write_text(
                json.dumps({"enabledPlugins": {"superpowers@market": True}}),
                encoding="utf-8",
            )

            plugin_root = claude_dir / "plugins" / "cache" / "market" / "superpowers" / "1.0.0" / "skills"
            (plugin_root / "brainstorming").mkdir(parents=True)
            (plugin_root / "brainstorming" / "SKILL.md").write_text(
                """---
name: brainstorming
description: Use when exploring ideas before implementation
---
Body
""",
                encoding="utf-8",
            )
            (plugin_root / "document-search").mkdir(parents=True)
            (plugin_root / "document-search" / "SKILL.md").write_text(
                """---
name: document-search
description: Search document content
---
Body
""",
                encoding="utf-8",
            )

            project = root / "project"
            (project / ".claude").mkdir(parents=True)
            (project / ".claude" / "settings.local.json").write_text(
                json.dumps(
                    {
                        "cc-skills": {
                            "ignoreSkillRules": [
                                {"type": "prefix", "value": "document-"},
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            (project / ".claude" / "skills" / "lark-demo").mkdir(parents=True)
            (project / ".claude" / "skills" / "lark-demo" / "SKILL.md").write_text(
                """---
name: lark-demo
description: Lark helper
---
Body
""",
                encoding="utf-8",
            )

            catalog = discover_catalog(project, claude_dir)
            names = {skill.name for skill in catalog.skills}

        self.assertIn("lark-demo", names)
        self.assertNotIn("superpowers:document-search", names)
        self.assertIn("superpowers:brainstorming", names)

    def test_legacy_ignore_skill_keys_no_longer_override_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            claude_dir = root / ".claude"
            claude_dir.mkdir(parents=True)
            (claude_dir / "settings.json").write_text(
                json.dumps({"enabledPlugins": {"superpowers@market": True}}),
                encoding="utf-8",
            )

            plugin_root = claude_dir / "plugins" / "cache" / "market" / "superpowers" / "1.0.0" / "skills"
            (plugin_root / "brainstorming").mkdir(parents=True)
            (plugin_root / "brainstorming" / "SKILL.md").write_text(
                """---
name: brainstorming
description: Use when exploring ideas before implementation
---
Body
""",
                encoding="utf-8",
            )

            project = root / "project"
            (project / ".claude").mkdir(parents=True)
            (project / ".claude" / "settings.local.json").write_text(
                json.dumps(
                    {
                        "cc-skills": {
                            "ignoreSkillPrefixes": [],
                            "ignoreSkillNamespaces": [],
                        }
                    }
                ),
                encoding="utf-8",
            )
            (project / ".claude" / "skills" / "lark-demo").mkdir(parents=True)
            (project / ".claude" / "skills" / "lark-demo" / "SKILL.md").write_text(
                """---
name: lark-demo
description: Lark helper
---
Body
""",
                encoding="utf-8",
            )

            catalog = discover_catalog(project, claude_dir)
            names = {skill.name for skill in catalog.skills}

        self.assertNotIn("lark-demo", names)
        self.assertNotIn("superpowers:brainstorming", names)

    def test_user_invocable_false_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            claude_dir = root / ".claude"
            claude_dir.mkdir(parents=True)
            (claude_dir / "settings.json").write_text(
                json.dumps({"enabledPlugins": {"alpha@market": True}}),
                encoding="utf-8",
            )
            skill_dir = claude_dir / "plugins" / "cache" / "market" / "alpha" / "1.0.0" / "skills" / "hidden-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                """---
name: hidden-skill
description: Hidden helper
user-invocable: false
---
Body
""",
                encoding="utf-8",
            )

            skills = discover_skills(root, claude_dir)

        self.assertEqual(skills, [])

    def test_unknown_skill_falls_back_to_original_english(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "unknown-skill"
            skill_dir.mkdir(parents=True)
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(
                """---
name: unknown-skill
description: Use when checking an unfamiliar workflow before automation
---
Body
""",
                encoding="utf-8",
            )

            skill = make_skill(
                skill_file,
                namespace=None,
                source_type="global",
                source_label="全局",
            )

        self.assertIsNotNone(skill)
        assert skill is not None
        self.assertEqual(skill.summary, "Use when checking an unfamiliar workflow before automation")
        self.assertTrue(skill.short.startswith("checking an unfamiliar"))

    def test_display_overrides_loaded_from_config_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = Path(tmpdir) / "brainstorming"
            skill_dir.mkdir(parents=True)
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(
                """---
name: brainstorming
description: Use when exploring ideas before implementation
when_to_use: feature design
---
Body
""",
                encoding="utf-8",
            )

            skill = make_skill(
                skill_file,
                namespace="superpowers",
                source_type="plugin",
                source_label="插件 / superpowers",
            )

        self.assertIsNotNone(skill)
        assert skill is not None
        self.assertEqual(skill.short, "先澄清需求再比较方案设计")
        self.assertIn("澄清用户意图", skill.summary)

    def test_plugin_info_command_uses_slash_prefix(self) -> None:
        plugin = PluginInfo(name="ralph-loop", marketplace="market", has_skills=False, skill_count=0)

        self.assertEqual(plugin.command, "/ralph-loop")
        self.assertEqual(plugin.summary, "/ralph-loop(无 skill)")

    def test_resource_files_live_under_resources_directory(self) -> None:
        self.assertEqual(SCAN_DEFAULTS_PATH.parent.name, "resources")
        self.assertEqual(DISPLAY_OVERRIDES_PATH.parent.name, "resources")

    def test_record_usage_increments_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "skills-usage.json"
            record_usage("lark-vc", path)
            usage = record_usage("lark-vc", path)

            self.assertIn("lark-vc", usage)
            self.assertEqual(usage["lark-vc"].use_count, 2)
            self.assertEqual(load_usage(path)["lark-vc"].use_count, 2)

    def test_resolve_default_usage_path_uses_nearest_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = root / "project"
            nested = project / "src" / "feature"
            nested.mkdir(parents=True)
            (project / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

            path = resolve_default_usage_path(nested)

        self.assertEqual(path, project.resolve() / ".cache" / "cc-skills" / "skills-usage.json")

    def test_sort_skills_uses_usage_as_tiebreaker(self) -> None:
        skills = [
            Skill(
                directory="lark-mail",
                name="lark-mail",
                short="飞书邮件",
                summary="收发飞书邮件。",
                examples="起草邮件",
                scenes="邮件处理",
                group="飞书 / Lark 技能",
                group_label="Lark",
                order=0,
            ),
            Skill(
                directory="lark-vc",
                name="lark-vc",
                short="查会议纪要",
                summary="查询飞书历史会议记录与纪要产物。",
                examples="整理会议纪要",
                scenes="会后复盘",
                group="飞书 / Lark 技能",
                group_label="Lark",
                order=1,
            ),
        ]
        usage = {
            "lark-vc": UsageInfo(use_count=5, last_used_at="2026-04-16T12:00:00"),
            "lark-mail": UsageInfo(use_count=1, last_used_at="2026-04-15T12:00:00"),
        }

        ranked = sort_skills(skills, usage, "lark")
        self.assertEqual(ranked[0].name, "lark-vc")


if __name__ == "__main__":
    unittest.main()
