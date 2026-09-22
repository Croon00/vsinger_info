"""Static boundaries for the intentionally minimal X/Discord runtime."""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def imported_modules(path: str) -> set[str]:
    tree = ast.parse(source(path))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_discord_bot_contains_no_command_or_management_surface():
    code = source("app/bots/discord_bot.py")
    for forbidden in ("app_commands", "@bot.tree.command", "Interaction"):
        assert forbidden not in code
    modules = imported_modules("app/bots/discord_bot.py")
    assert not any(name.startswith((
        "app.core.db", "app.integrations", "app.lyrics_pipeline", "app.repositories"
    )) for name in modules)


def test_x_scheduler_has_no_classification_calendar_or_music_collector_imports():
    modules = imported_modules("app/agents/scheduler.py")
    assert not any(name.startswith((
        "app.agents.music_graph", "app.core.db", "app.integrations.google",
        "app.integrations.youtube", "app.integrations.spotify",
        "app.integrations.karaoke", "app.lyrics_pipeline",
    )) for name in modules)


def test_x_classification_graph_is_removed_but_youtube_setlist_ai_remains():
    assert not (ROOT / "app/agents/music_graph.py").exists()
    code = source("app/integrations/ai_extractor.py")
    assert "classify_source_item" not in code
    assert "extract_music_event" not in code
    assert "extract_youtube_setlist" in code
    assert "register_youtube_live" not in source(
        "app/integrations/youtube_live_archive.py"
    )
