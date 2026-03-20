from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--focus-path")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def first_nonempty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def submitted_date(payload: dict[str, Any]) -> str:
    submitted_at = payload.get("submitted_at", "") or now_iso()
    return submitted_at[:10]


def submitted_time(payload: dict[str, Any]) -> str:
    submitted_at = payload.get("submitted_at", "") or now_iso()
    if "T" in submitted_at:
        return submitted_at.split("T", 1)[1][:5]
    return submitted_at[11:16] if len(submitted_at) >= 16 else ""


def payload_sort_key(item: tuple[str, dict[str, Any]]) -> tuple[str, str]:
    stem, payload = item
    return (payload.get("submitted_at", ""), stem)


def load_payload_entries(source_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(source_dir.glob("*.json")):
        entries.append((path.stem, read_json(path, {})))
    return sorted(entries, key=payload_sort_key)


def bullet_lines(items: list[str], fallback: str = "- (待补充)") -> list[str]:
    if items:
        return [f"- {item}" for item in items]
    return [fallback]


def render_idea_markdown(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {payload.get('title', 'Idea')}",
            "",
            f"- Submitted at: {payload.get('submitted_at', '')}",
            f"- Submitted by: {payload.get('submitted_by', '')}",
            f"- Bucket: {payload.get('bucket', '')}",
            f"- Issue: {payload.get('issue_url', '')}",
            "",
            "## Idea",
            payload.get("idea_summary", "") or "",
            "",
            "## Why It Matters",
            payload.get("why_it_matters", "") or "",
            "",
            "## Next Step",
            payload.get("next_step", "") or "",
            "",
        ]
    ).strip() + "\n"


def render_learning_markdown(payload: dict[str, Any]) -> str:
    analysis = payload.get("analysis") or {}
    extraction = payload.get("extraction") or {}
    reusable = analysis.get("reusable_patterns") or []
    hooks = analysis.get("hook_observations") or []
    adaptations = analysis.get("local_adaptation_ideas") or []
    return "\n".join(
        [
            f"# {payload.get('title', 'Learning')}",
            "",
            f"- Submitted at: {payload.get('submitted_at', '')}",
            f"- Source type: {payload.get('source_type', '')}",
            f"- Source URL: {payload.get('source_url', '')}",
            f"- Analysis status: {payload.get('analysis_status', '')}",
            f"- Extraction status: {payload.get('extraction_status', '')}",
            "",
            "## Why This Was Sent",
            payload.get("why_good", "") or "",
            "",
            "## Wanted Outputs",
            payload.get("wanted_outputs", "") or "",
            "",
            "## Source Summary",
            analysis.get("source_summary") or extraction.get("title") or payload.get("source_title", ""),
            "",
            "## Reusable Patterns",
            *(f"- {item}" for item in reusable),
            "",
            "## Hook Observations",
            *(f"- {item}" for item in hooks),
            "",
            "## Local Adaptation Ideas",
            *(f"- {item}" for item in adaptations),
            "",
            "## Raw Extraction Snapshot",
            extraction.get("description")
            or extraction.get("text_excerpt")
            or extraction.get("extraction_note")
            or "",
            "",
            "## Memory Summary",
            analysis.get("memory_summary", ""),
            "",
            "## Reuse Hint",
            analysis.get("reuse_hint", ""),
            "",
            "## Errors",
            payload.get("extraction_error") or payload.get("analysis_error") or "",
            "",
        ]
    ).strip() + "\n"


def render_idea_daily_block(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"## {submitted_time(payload)} {payload.get('title', 'Idea')}".strip(),
            "",
            f"- Bucket: {payload.get('bucket', '')}",
            f"- Issue: {payload.get('issue_url', '')}",
            "",
            "### Idea",
            payload.get("idea_summary", "") or "",
            "",
            "### Why It Matters",
            payload.get("why_it_matters", "") or "",
            "",
            "### Next Step",
            payload.get("next_step", "") or "",
        ]
    ).strip()


def render_learning_daily_block(payload: dict[str, Any]) -> str:
    analysis = payload.get("analysis") or {}
    extraction = payload.get("extraction") or {}
    reusable = analysis.get("reusable_patterns") or []
    adaptations = analysis.get("local_adaptation_ideas") or []
    return "\n".join(
        [
            f"## {submitted_time(payload)} {payload.get('title', 'Learning')}".strip(),
            "",
            f"- Source type: {payload.get('source_type', '')}",
            f"- Source URL: {payload.get('source_url', '')}",
            f"- Issue: {payload.get('issue_url', '')}",
            f"- Analysis status: {payload.get('analysis_status', '')}",
            "",
            "### Source Summary",
            analysis.get("source_summary") or extraction.get("title") or payload.get("source_title", ""),
            "",
            "### Reusable Patterns",
            *(f"- {item}" for item in reusable),
            "",
            "### Local Adaptation Ideas",
            *(f"- {item}" for item in adaptations),
            "",
            "### Memory Summary",
            analysis.get("memory_summary", ""),
            "",
            "### Reuse Hint",
            analysis.get("reuse_hint", ""),
        ]
    ).strip()


def build_idea_memory_entry(source_file: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "synced_at": now_iso(),
        "source_file": source_file,
        "kind": "idea",
        "title": payload.get("title", ""),
        "bucket": payload.get("bucket", ""),
        "idea_summary": payload.get("idea_summary", ""),
        "why_it_matters": payload.get("why_it_matters", ""),
        "next_step": payload.get("next_step", ""),
        "issue_url": payload.get("issue_url", ""),
    }


def build_learning_memory_entry(source_file: str, payload: dict[str, Any]) -> dict[str, Any]:
    analysis = payload.get("analysis") or {}
    extraction = payload.get("extraction") or {}
    return {
        "synced_at": now_iso(),
        "source_file": source_file,
        "kind": "learning",
        "title": payload.get("title", ""),
        "source_type": payload.get("source_type", ""),
        "source_url": payload.get("source_url", ""),
        "analysis_status": payload.get("analysis_status", ""),
        "source_summary": analysis.get("source_summary") or extraction.get("title") or payload.get("source_title", ""),
        "reusable_patterns": analysis.get("reusable_patterns") or [],
        "hook_observations": analysis.get("hook_observations") or [],
        "local_adaptation_ideas": analysis.get("local_adaptation_ideas") or [],
        "memory_summary": analysis.get("memory_summary", ""),
        "reuse_hint": analysis.get("reuse_hint", ""),
        "issue_url": payload.get("issue_url", ""),
    }


def rewrite_markdown_views(
    directory: Path,
    entries: list[tuple[str, dict[str, Any]]],
    renderer,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    active_names: set[str] = set()
    for stem, payload in entries:
        target = directory / f"{stem}.md"
        target.write_text(renderer(payload), encoding="utf-8")
        active_names.add(target.name)
    for path in directory.glob("*.md"):
        if path.name not in active_names:
            path.unlink()


def rewrite_daily_logs(
    directory: Path,
    *,
    title_suffix: str,
    entries: list[tuple[str, dict[str, Any]]],
    renderer,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[str]] = {}
    for _stem, payload in entries:
        grouped.setdefault(submitted_date(payload), []).append(renderer(payload))

    active_names: set[str] = set()
    for day, blocks in sorted(grouped.items()):
        path = directory / f"{day}.md"
        body = "\n\n".join(block for block in blocks if block.strip()).strip()
        path.write_text(f"# {day} {title_suffix}\n\n{body}\n", encoding="utf-8")
        active_names.add(path.name)

    for path in directory.glob("*.md"):
        if path.name not in active_names:
            path.unlink()


def render_bilibili_thread_context(entries: list[tuple[str, dict[str, Any]]]) -> str:
    lines = [
        "# Cat Meme Learning Context",
        "",
        "这个文件由 `solo-template-business` 的云端学习中枢自动重建。",
        "即使电脑没开机，云端也会先更新这里；本地项目上线后再镜像到本地。",
        "",
        "## 使用方式",
        "- 先看最新 3 条学习记录，决定今天最值得复用的钩子或节奏。",
        "- 再把 `本地落地动作` 直接转成脚本、镜头节奏或素材挑选规则。",
        "- 如果要同步进长期记忆，优先摘 `一句话记忆` 和 `复用提示`。",
        "",
        "## 最新学习输入",
        "",
    ]
    for _stem, payload in reversed(entries[-8:]):
        analysis = payload.get("analysis") or {}
        extraction = payload.get("extraction") or {}
        summary = first_nonempty(
            analysis.get("source_summary"),
            extraction.get("title"),
            payload.get("source_title"),
            payload.get("source_url"),
        )
        lines.extend(
            [
                f"### {payload.get('title', 'Learning')}",
                "",
                f"- Source URL: {payload.get('source_url', '')}",
                f"- Analysis status: {payload.get('analysis_status', '')}",
                f"- 一句话概括: {summary}",
                "",
                "#### 可直接套用的方法",
                *bullet_lines(analysis.get("reusable_patterns") or []),
                "",
                "#### 钩子观察",
                *bullet_lines(analysis.get("hook_observations") or []),
                "",
                "#### 本地落地动作",
                *bullet_lines(analysis.get("local_adaptation_ideas") or []),
                "",
                "#### 一句话记忆",
                analysis.get("memory_summary", "") or "这条内容值得继续观察，但当前还缺更深入的自动分析。",
                "",
                "#### 复用提示",
                analysis.get("reuse_hint", "") or "先把这条内容拆成开场、反应、转折三个节奏点，再匹配猫素材。",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def render_bilibili_method_cards(entries: list[tuple[str, dict[str, Any]]]) -> str:
    lines = [
        "# Cat Meme Method Cards",
        "",
        "这份文件给猫 meme 制作线程直接拿来用，按条查看即可。",
        "它先在云端重建，电脑开机后才会同步到本地项目。",
        "",
    ]
    for _stem, payload in entries:
        analysis = payload.get("analysis") or {}
        extraction = payload.get("extraction") or {}
        lines.extend(
            [
                f"## {payload.get('title', 'Learning')}",
                "",
                f"- Source URL: {payload.get('source_url', '')}",
                f"- Source Summary: {first_nonempty(analysis.get('source_summary'), extraction.get('title'), payload.get('source_title'))}",
                f"- Analysis status: {payload.get('analysis_status', '')}",
                "",
                "### 可复用结构",
                *bullet_lines(analysis.get("reusable_patterns") or []),
                "",
                "### 钩子与情绪",
                *bullet_lines(analysis.get("hook_observations") or []),
                "",
                "### 猫 meme 落地动作",
                *bullet_lines(analysis.get("local_adaptation_ideas") or []),
                "",
                "### 记忆摘要",
                analysis.get("memory_summary", "") or "暂时只有原始提取结果，后面还可以继续补强。",
                "",
                "### 复用提示",
                analysis.get("reuse_hint", "") or "先把这条学习改写成猫 meme 的对白和反应节奏。",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_focus_summary(
    *,
    focus_path: str | None,
    idea_entries: list[tuple[str, dict[str, Any]]],
    learning_entries: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "cloud_views_root": "cloud/views",
        "cloud_thread_sync_root": "cloud/thread_sync",
    }
    if not focus_path:
        return summary

    focus = Path(focus_path)
    stem = focus.stem
    if "inbox/ideas" in focus_path:
        payload = dict(idea_entries).get(stem, {})
        day = submitted_date(payload) if payload else ""
        summary.update(
            {
                "focus_view": f"cloud/views/ideas/{stem}.md",
                "focus_daily_log": f"cloud/views/daily_ideas/{day}.md" if day else "",
            }
        )
    elif "processed" in focus_path:
        payload = dict(learning_entries).get(stem, {})
        day = submitted_date(payload) if payload else ""
        summary.update(
            {
                "focus_view": f"cloud/views/learnings/{stem}.md",
                "focus_daily_log": f"cloud/views/daily_learning_updates/{day}.md" if day else "",
                "focus_thread_context": "cloud/thread_sync/cat_meme_learning_context.md",
                "focus_method_cards": "cloud/thread_sync/cat_meme_method_cards.md",
            }
        )
    return summary


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()

    ideas_dir = repo_root / "cloud" / "inbox" / "ideas"
    learnings_dir = repo_root / "cloud" / "processed"
    cloud_views_root = repo_root / "cloud" / "views"
    views_ideas_dir = cloud_views_root / "ideas"
    views_learnings_dir = cloud_views_root / "learnings"
    views_daily_ideas_dir = cloud_views_root / "daily_ideas"
    views_daily_learnings_dir = cloud_views_root / "daily_learning_updates"
    cloud_memory_root = repo_root / "cloud" / "memory"
    cloud_thread_sync_root = repo_root / "cloud" / "thread_sync"

    idea_entries = load_payload_entries(ideas_dir)
    learning_entries = load_payload_entries(learnings_dir)

    rewrite_markdown_views(views_ideas_dir, idea_entries, render_idea_markdown)
    rewrite_markdown_views(views_learnings_dir, learning_entries, render_learning_markdown)
    rewrite_daily_logs(
        views_daily_ideas_dir,
        title_suffix="Ideas",
        entries=idea_entries,
        renderer=render_idea_daily_block,
    )
    rewrite_daily_logs(
        views_daily_learnings_dir,
        title_suffix="Learning Updates",
        entries=learning_entries,
        renderer=render_learning_daily_block,
    )
    write_jsonl(
        cloud_memory_root / "idea_memory.jsonl",
        [build_idea_memory_entry(f"{stem}.json", payload) for stem, payload in idea_entries],
    )
    write_jsonl(
        cloud_memory_root / "learning_memory.jsonl",
        [build_learning_memory_entry(f"{stem}.json", payload) for stem, payload in learning_entries],
    )
    cloud_thread_sync_root.mkdir(parents=True, exist_ok=True)
    (cloud_thread_sync_root / "cat_meme_learning_context.md").write_text(
        render_bilibili_thread_context(learning_entries),
        encoding="utf-8",
    )
    (cloud_thread_sync_root / "cat_meme_method_cards.md").write_text(
        render_bilibili_method_cards(learning_entries),
        encoding="utf-8",
    )

    print(
        json.dumps(
            build_focus_summary(
                focus_path=args.focus_path,
                idea_entries=idea_entries,
                learning_entries=learning_entries,
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
