from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GIT_DIR = PROJECT_ROOT / ".git"
IDEAS_DIR = PROJECT_ROOT / "cloud" / "inbox" / "ideas"
LEARNINGS_DIR = PROJECT_ROOT / "cloud" / "processed"
LOCAL_IDEAS_DIR = PROJECT_ROOT / "research" / "mobile_inbox" / "ideas"
LOCAL_LEARNINGS_DIR = PROJECT_ROOT / "research" / "cloud_learnings"
MINDER_ROOT = PROJECT_ROOT / "minder"
MINDER_DAILY_IDEAS_DIR = MINDER_ROOT / "daily_ideas"
MINDER_DAILY_LEARNINGS_DIR = MINDER_ROOT / "daily_learning_updates"
BILIBILI_ROOT = Path("/Users/Zhuanz1/Documents/bilibili-cat-meme")
BILIBILI_MINDER_ROOT = BILIBILI_ROOT / "minder"
BILIBILI_LEARNINGS_DIR = BILIBILI_MINDER_ROOT / "cloud_learnings"
BILIBILI_DAILY_LEARNINGS_DIR = BILIBILI_MINDER_ROOT / "daily_learning_updates"
BILIBILI_MEMORY_LEDGER = BILIBILI_MINDER_ROOT / "learning_memory.jsonl"
STATE_FILE = PROJECT_ROOT / "data" / "cloud_sync_state.json"
RUN_LOG = PROJECT_ROOT / "data" / "cloud_sync_runs.jsonl"
IDEA_MEMORY_LEDGER = PROJECT_ROOT / "data" / "cloud_idea_memory.jsonl"
LEARNING_MEMORY_LEDGER = PROJECT_ROOT / "data" / "cloud_learning_memory.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pull", action="store_true")
    parser.add_argument("--trigger-label", default="manual")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def git_cmd(*args: str) -> list[str]:
    if GIT_DIR.exists():
        return [
            "git",
            f"--git-dir={GIT_DIR}",
            f"--work-tree={PROJECT_ROOT}",
            *args,
        ]
    return ["git", "-C", str(PROJECT_ROOT), *args]


def submitted_date(payload: dict[str, Any]) -> str:
    submitted_at = payload.get("submitted_at", "") or now_iso()
    return submitted_at[:10]


def submitted_time(payload: dict[str, Any]) -> str:
    submitted_at = payload.get("submitted_at", "") or now_iso()
    if "T" in submitted_at:
        return submitted_at.split("T", 1)[1][:5]
    return submitted_at[11:16] if len(submitted_at) >= 16 else ""


def append_markdown_block(path: Path, header: str, block: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# {header}\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(block.rstrip() + "\n\n")


def maybe_pull_repo() -> dict[str, Any]:
    if not GIT_DIR.exists():
        return {"status": "skipped", "reason": "not_a_git_repo"}

    repo_check = subprocess.run(
        git_cmd("status", "--short"),
        capture_output=True,
        text=True,
        check=False,
    )
    if repo_check.returncode != 0:
        return {"status": "skipped", "reason": "not_a_git_repo"}

    upstream_check = subprocess.run(
        git_cmd("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"),
        capture_output=True,
        text=True,
        check=False,
    )
    if upstream_check.returncode != 0:
        return {"status": "skipped", "reason": "no_upstream_remote"}

    result = subprocess.run(
        git_cmd("pull", "--ff-only"),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "status": "completed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def state() -> dict[str, list[str]]:
    return read_json(STATE_FILE, {"ideas": [], "learnings": []})


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


def append_memory_entry(path: Path, payload: dict[str, Any]) -> None:
    append_jsonl(path, payload)


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


def sync_idea_into_minder(payload: dict[str, Any]) -> str:
    day = submitted_date(payload)
    log_path = MINDER_DAILY_IDEAS_DIR / f"{day}.md"
    append_markdown_block(log_path, f"{day} Ideas", render_idea_daily_block(payload))
    return str(log_path)


def sync_learning_into_minder(payload: dict[str, Any]) -> str:
    day = submitted_date(payload)
    log_path = MINDER_DAILY_LEARNINGS_DIR / f"{day}.md"
    append_markdown_block(log_path, f"{day} Learning Updates", render_learning_daily_block(payload))
    return str(log_path)


def sync_learning_into_bilibili(stem: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not BILIBILI_ROOT.exists():
        return {"status": "skipped", "reason": "bilibili_root_missing"}

    BILIBILI_LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)
    target = BILIBILI_LEARNINGS_DIR / f"{stem}.md"
    target.write_text(render_learning_markdown(payload), encoding="utf-8")

    day = submitted_date(payload)
    daily_log_path = BILIBILI_DAILY_LEARNINGS_DIR / f"{day}.md"
    append_markdown_block(daily_log_path, f"{day} Learning Updates", render_learning_daily_block(payload))
    append_memory_entry(BILIBILI_MEMORY_LEDGER, build_learning_memory_entry(f"{stem}.json", payload))
    return {
        "status": "synced",
        "learning_note": str(target),
        "daily_log": str(daily_log_path),
    }


def sync_bucket(
    *,
    source_dir: Path,
    destination_dir: Path,
    known_items: list[str],
    render,
    memory_path: Path,
    memory_builder,
    after_import=None,
) -> tuple[list[str], list[str]]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    imported: list[str] = []
    seen = set(known_items)
    for path in sorted(source_dir.glob("*.json")):
        if path.name in seen:
            continue
        payload = read_json(path, {})
        target = destination_dir / f"{path.stem}.md"
        target.write_text(render(payload), encoding="utf-8")
        append_memory_entry(memory_path, memory_builder(path.name, payload))
        if after_import is not None:
            after_import(path.stem, payload)
        known_items.append(path.name)
        imported.append(path.name)
    return known_items, imported


def main() -> None:
    args = parse_args()
    pull_result = maybe_pull_repo() if args.pull else None
    sync_state = state()
    minder_idea_logs: list[str] = []
    minder_learning_logs: list[str] = []
    bilibili_sync_results: list[dict[str, Any]] = []

    def after_idea_import(_stem: str, payload: dict[str, Any]) -> None:
        minder_idea_logs.append(sync_idea_into_minder(payload))

    def after_learning_import(stem: str, payload: dict[str, Any]) -> None:
        minder_learning_logs.append(sync_learning_into_minder(payload))
        bilibili_sync_results.append(sync_learning_into_bilibili(stem, payload))

    sync_state["ideas"], imported_ideas = sync_bucket(
        source_dir=IDEAS_DIR,
        destination_dir=LOCAL_IDEAS_DIR,
        known_items=sync_state["ideas"],
        render=render_idea_markdown,
        memory_path=IDEA_MEMORY_LEDGER,
        memory_builder=build_idea_memory_entry,
        after_import=after_idea_import,
    )
    sync_state["learnings"], imported_learnings = sync_bucket(
        source_dir=LEARNINGS_DIR,
        destination_dir=LOCAL_LEARNINGS_DIR,
        known_items=sync_state["learnings"],
        render=render_learning_markdown,
        memory_path=LEARNING_MEMORY_LEDGER,
        memory_builder=build_learning_memory_entry,
        after_import=after_learning_import,
    )
    write_json(STATE_FILE, sync_state)

    payload = {
        "time": now_iso(),
        "trigger_label": args.trigger_label,
        "pull_result": pull_result,
        "imported_ideas": imported_ideas,
        "imported_learnings": imported_learnings,
        "minder_idea_logs": minder_idea_logs,
        "minder_learning_logs": minder_learning_logs,
        "bilibili_sync_results": bilibili_sync_results,
    }
    append_jsonl(RUN_LOG, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
