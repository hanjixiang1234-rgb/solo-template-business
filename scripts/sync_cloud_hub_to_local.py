from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
BILIBILI_THREAD_SYNC_DIR = BILIBILI_MINDER_ROOT / "thread_sync"
BILIBILI_THREAD_CONTEXT = BILIBILI_THREAD_SYNC_DIR / "cat_meme_learning_context.md"
BILIBILI_METHOD_CARDS = BILIBILI_THREAD_SYNC_DIR / "cat_meme_method_cards.md"
STATE_FILE = PROJECT_ROOT / "data" / "cloud_sync_state.json"
RUN_LOG = PROJECT_ROOT / "data" / "cloud_sync_runs.jsonl"
IDEA_MEMORY_LEDGER = PROJECT_ROOT / "data" / "cloud_idea_memory.jsonl"
LEARNING_MEMORY_LEDGER = PROJECT_ROOT / "data" / "cloud_learning_memory.jsonl"
SYNC_STATUS_DIR = MINDER_ROOT / "sync_status"
SYNC_STATUS_JSON = SYNC_STATUS_DIR / "latest.json"
SYNC_STATUS_MD = SYNC_STATUS_DIR / "latest.md"
OPENAI_CLOUD_CONFIG = PROJECT_ROOT / "config" / "openai_cloud_hub.local.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pull", action="store_true")
    parser.add_argument("--trigger-label", default="manual")
    parser.add_argument("--config-path", default=str(OPENAI_CLOUD_CONFIG))
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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def git_cmd(*args: str) -> list[str]:
    if GIT_DIR.exists():
        return [
            "git",
            f"--git-dir={GIT_DIR}",
            f"--work-tree={PROJECT_ROOT}",
            *args,
        ]
    return ["git", "-C", str(PROJECT_ROOT), *args]


def git_stdout(*args: str) -> str:
    result = subprocess.run(
        git_cmd(*args),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def infer_repo_base_url() -> str:
    remote = git_stdout("remote", "get-url", "origin")
    if not remote:
        return ""

    https_match = re.match(r"https://github\.com/([^/]+/[^/.]+)(?:\.git)?$", remote)
    if https_match:
        return f"https://github.com/{https_match.group(1)}"

    ssh_match = re.match(r"(?:ssh://)?git@[^:]+:(.+?)(?:\.git)?$", remote)
    if ssh_match:
        return f"https://github.com/{ssh_match.group(1)}"

    alt_ssh_match = re.match(r"(?:ssh://)?git@[^/]+/(.+?)(?:\.git)?$", remote)
    if alt_ssh_match:
        return f"https://github.com/{alt_ssh_match.group(1)}"
    return ""


def infer_repo_branch() -> str:
    return git_stdout("branch", "--show-current") or "main"


def repo_blob_url(repo_base_url: str, branch: str, relative_path: str) -> str:
    if not repo_base_url:
        return relative_path
    return f"{repo_base_url}/blob/{branch}/{relative_path}"


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


def file_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_state_bucket(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    if isinstance(value, list):
        return {str(item): "" for item in value}
    return {}


def normalize_cursor(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def state() -> dict[str, Any]:
    raw = read_json(STATE_FILE, {"ideas": {}, "learnings": {}})
    return {
        "ideas": normalize_state_bucket(raw.get("ideas", {})),
        "learnings": normalize_state_bucket(raw.get("learnings", {})),
        "remote_cursor": normalize_cursor(raw.get("remote_cursor", 0)),
    }


def load_openai_cloud_config(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    raw = read_json(path, {})
    api_base_url = str(raw.get("api_base_url", "")).strip().rstrip("/")
    read_token = str(raw.get("read_token", "")).strip()
    if not api_base_url or not read_token:
        return None
    return {
        "api_base_url": api_base_url,
        "read_token": read_token,
    }


def fetch_openai_cloud_feed(config: dict[str, str], after_id: int) -> dict[str, Any]:
    query = urlencode({"after_id": str(after_id), "limit": "100"})
    url = f"{config['api_base_url']}/api/v1/feed?{query}"
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {config['read_token']}",
            "User-Agent": "minder-local-sync/1.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as exc:
        raise RuntimeError(str(exc)) from exc


def refresh_local_cloud_views() -> dict[str, Any]:
    result = subprocess.run(
        [
            "/usr/bin/python3",
            str(PROJECT_ROOT / "scripts" / "build_cloud_hub_views.py"),
            "--repo-root",
            str(PROJECT_ROOT),
        ],
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


def write_remote_api_item(item: dict[str, Any]) -> str:
    payload = item.get("payload") or {}
    stem = str(item.get("filename_stem") or payload.get("filename_stem") or "")
    kind = str(item.get("kind") or payload.get("kind") or "")
    if not stem:
        submitted_at = str(payload.get("submitted_at", now_iso()))
        title = first_nonempty(payload.get("title", ""), f"{kind}-{item.get('id', 'item')}")
        stem = f"{submitted_at[:10]}-submission-{item.get('id', 'item')}-{slugify(title)}"

    if kind == "idea":
        destination = IDEAS_DIR / f"{stem}.json"
    else:
        destination = LEARNINGS_DIR / f"{stem}.json"
    write_json(destination, payload)
    return str(destination)


def first_nonempty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip()).strip("-").lower()
    return normalized or "item"


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


def payload_sort_key(item: tuple[str, dict[str, Any]]) -> tuple[str, str]:
    stem, payload = item
    return (payload.get("submitted_at", ""), stem)


def load_payload_entries(source_dir: Path) -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(source_dir.glob("*.json")):
        entries.append((path.stem, read_json(path, {})))
    return sorted(entries, key=payload_sort_key)


def rewrite_daily_logs(
    directory: Path,
    *,
    title_suffix: str,
    entries: list[tuple[str, dict[str, Any]]],
    renderer,
) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[str]] = {}
    for _stem, payload in entries:
        grouped.setdefault(submitted_date(payload), []).append(renderer(payload))

    written: list[str] = []
    active_names: set[str] = set()
    for day, blocks in sorted(grouped.items()):
        path = directory / f"{day}.md"
        body = "\n\n".join(block for block in blocks if block.strip()).strip()
        path.write_text(f"# {day} {title_suffix}\n\n{body}\n", encoding="utf-8")
        written.append(str(path))
        active_names.add(path.name)

    for path in directory.glob("*.md"):
        if path.name not in active_names:
            path.unlink()
    return written


def bullet_lines(items: list[str], fallback: str = "- (待补充)") -> list[str]:
    if items:
        return [f"- {item}" for item in items]
    return [fallback]


def render_bilibili_thread_context(entries: list[tuple[str, dict[str, Any]]]) -> str:
    lines = [
        "# Cat Meme Learning Context",
        "",
        "这个文件由 `solo-template-business` 的云端学习中枢自动重建。",
        "开新线程做猫 meme 之前，先读这里，再去看最新的每日学习日志。",
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
        title = payload.get("title", "Learning")
        summary = first_nonempty(
            analysis.get("source_summary"),
            extraction.get("title"),
            payload.get("source_title"),
            payload.get("source_url"),
        )
        lines.extend(
            [
                f"### {title}",
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


def rewrite_local_ledgers(
    idea_entries: list[tuple[str, dict[str, Any]]],
    learning_entries: list[tuple[str, dict[str, Any]]],
) -> None:
    write_jsonl(
        IDEA_MEMORY_LEDGER,
        [build_idea_memory_entry(f"{stem}.json", payload) for stem, payload in idea_entries],
    )
    write_jsonl(
        LEARNING_MEMORY_LEDGER,
        [build_learning_memory_entry(f"{stem}.json", payload) for stem, payload in learning_entries],
    )


def rewrite_bilibili_views(learning_entries: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    if not BILIBILI_ROOT.exists():
        return {"status": "skipped", "reason": "bilibili_root_missing"}

    BILIBILI_DAILY_LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)
    BILIBILI_THREAD_SYNC_DIR.mkdir(parents=True, exist_ok=True)

    write_jsonl(
        BILIBILI_MEMORY_LEDGER,
        [build_learning_memory_entry(f"{stem}.json", payload) for stem, payload in learning_entries],
    )
    daily_logs = rewrite_daily_logs(
        BILIBILI_DAILY_LEARNINGS_DIR,
        title_suffix="Learning Updates",
        entries=learning_entries,
        renderer=render_learning_daily_block,
    )
    BILIBILI_THREAD_CONTEXT.write_text(render_bilibili_thread_context(learning_entries), encoding="utf-8")
    BILIBILI_METHOD_CARDS.write_text(render_bilibili_method_cards(learning_entries), encoding="utf-8")
    return {
        "status": "synced",
        "daily_logs": daily_logs,
        "thread_context": str(BILIBILI_THREAD_CONTEXT),
        "method_cards": str(BILIBILI_METHOD_CARDS),
        "memory_ledger": str(BILIBILI_MEMORY_LEDGER),
    }


def sync_learning_into_bilibili(stem: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not BILIBILI_ROOT.exists():
        return {"status": "skipped", "reason": "bilibili_root_missing"}

    BILIBILI_LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)
    target = BILIBILI_LEARNINGS_DIR / f"{stem}.md"
    target.write_text(render_learning_markdown(payload), encoding="utf-8")
    return {
        "status": "synced",
        "learning_note": str(target),
    }


def latest_entry(entries: list[tuple[str, dict[str, Any]]]) -> tuple[str, dict[str, Any]] | None:
    if not entries:
        return None
    return entries[-1]


def render_sync_status_markdown(
    *,
    payload: dict[str, Any],
    idea_entries: list[tuple[str, dict[str, Any]]],
    learning_entries: list[tuple[str, dict[str, Any]]],
    repo_base_url: str,
    branch: str,
) -> str:
    latest_idea = latest_entry(idea_entries)
    latest_learning = latest_entry(learning_entries)
    pull_result = payload.get("pull_result") or {}
    local_cloud_views_root = PROJECT_ROOT / "cloud" / "views"
    local_thread_sync_root = PROJECT_ROOT / "cloud" / "thread_sync"

    def bullet(label: str, value: str) -> str:
        return f"- {label}: {value}" if value else f"- {label}: (空)"

    lines = [
        "# Minder Sync Status",
        "",
        "这份状态页由本地同步脚本自动重写，用来确认电脑开机联网后有没有把云端结果拉回本地。",
        "",
        "## 本次运行",
        "",
        bullet("运行时间", payload.get("time", "")),
        bullet("触发方式", payload.get("trigger_label", "")),
        bullet("拉取状态", pull_result.get("status", "skipped") if isinstance(pull_result, dict) else "skipped"),
        bullet("git pull 输出", (pull_result.get("stdout", "") or pull_result.get("stderr", "")).strip() if isinstance(pull_result, dict) else ""),
        bullet("API 拉取模式", "已启用" if payload.get("api_fetch_result") else "未启用"),
        bullet("API 来源", payload.get("api_fetch_result", {}).get("api_base_url", "") if isinstance(payload.get("api_fetch_result"), dict) else ""),
        bullet("API 新拉取条数", str(len(payload.get("api_fetch_result", {}).get("written_files", []))) if isinstance(payload.get("api_fetch_result"), dict) else "0"),
        bullet("本地云端视图刷新", payload.get("local_cloud_view_refresh", {}).get("status", "") if isinstance(payload.get("local_cloud_view_refresh"), dict) else ""),
        bullet("新导入灵感数", str(len(payload.get("imported_ideas", [])))),
        bullet("新导入学习数", str(len(payload.get("imported_learnings", [])))),
        "",
        "## 手机端永久入口",
        "",
        bullet("OpenAI Cloud Hub API", payload.get("api_fetch_result", {}).get("api_base_url", "") if isinstance(payload.get("api_fetch_result"), dict) else ""),
        f"- GitHub 模板选择页（回退入口）: {repo_base_url}/issues/new/choose" if repo_base_url else "- GitHub 模板选择页（回退入口）: (空)",
        f"- GitHub 灵感收件箱（回退入口）: {repo_base_url}/issues/new?template=idea-inbox.yml" if repo_base_url else "- GitHub 灵感收件箱（回退入口）: (空)",
        f"- GitHub 内容解析请求（回退入口）: {repo_base_url}/issues/new?template=learning-request.yml" if repo_base_url else "- GitHub 内容解析请求（回退入口）: (空)",
        bullet("本地云端控制台", str(PROJECT_ROOT / "CLOUD_HUB.md")),
        "",
    ]

    if latest_idea:
        stem, idea_payload = latest_idea
        lines.extend(
            [
                "## 最新灵感同步",
                "",
                bullet("标题", idea_payload.get("title", stem)),
                bullet("本地灵感文件", str(LOCAL_IDEAS_DIR / f"{stem}.md")),
                bullet("每日日志", str(MINDER_DAILY_IDEAS_DIR / f"{submitted_date(idea_payload)}.md")),
                bullet("本地云端阅读版", str(local_cloud_views_root / "ideas" / f"{stem}.md")),
                "",
            ]
        )
    if latest_learning:
        stem, learning_payload = latest_learning
        lines.extend(
            [
                "## 最新学习同步",
                "",
                bullet("标题", learning_payload.get("title", stem)),
                bullet("本地学习文件", str(LOCAL_LEARNINGS_DIR / f"{stem}.md")),
                bullet("minder 每日日志", str(MINDER_DAILY_LEARNINGS_DIR / f"{submitted_date(learning_payload)}.md")),
                bullet("猫 meme 镜像", str(BILIBILI_LEARNINGS_DIR / f"{stem}.md")),
                bullet("猫 meme 线程上下文", str(BILIBILI_THREAD_CONTEXT)),
                bullet("本地云端阅读版", str(local_cloud_views_root / "learnings" / f"{stem}.md")),
                bullet("本地云端方法卡片", str(local_thread_sync_root / "cat_meme_method_cards.md")),
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def sync_bucket(
    *,
    source_dir: Path,
    destination_dir: Path,
    known_items: dict[str, str],
    render,
    after_import=None,
) -> tuple[dict[str, str], list[str]]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    changed: list[str] = []
    current_names: set[str] = set()
    for path in sorted(source_dir.glob("*.json")):
        current_names.add(path.name)
        fingerprint = file_fingerprint(path)
        target = destination_dir / f"{path.stem}.md"
        if known_items.get(path.name) == fingerprint and target.exists():
            continue
        payload = read_json(path, {})
        target.write_text(render(payload), encoding="utf-8")
        if after_import is not None:
            after_import(path.stem, payload)
        known_items[path.name] = fingerprint
        changed.append(path.name)

    for name in list(known_items):
        if name not in current_names:
            known_items.pop(name, None)
            stale_target = destination_dir / f"{Path(name).stem}.md"
            if stale_target.exists():
                stale_target.unlink()
    return known_items, changed


def main() -> None:
    args = parse_args()
    api_config = load_openai_cloud_config(Path(args.config_path).expanduser())
    pull_result: dict[str, Any] | None
    if api_config:
        pull_result = {"status": "skipped", "reason": "api_mode_enabled"}
    else:
        pull_result = maybe_pull_repo() if args.pull else None
    repo_base_url = infer_repo_base_url()
    branch = infer_repo_branch()
    sync_state = state()
    bilibili_sync_results: list[dict[str, Any]] = []
    api_fetch_result: dict[str, Any] | None = None
    local_cloud_view_refresh: dict[str, Any] | None = None

    if api_config:
        after_id = normalize_cursor(sync_state.get("remote_cursor", 0))
        try:
            feed = fetch_openai_cloud_feed(api_config, after_id)
            written_files = [write_remote_api_item(item) for item in feed.get("items", [])]
            sync_state["remote_cursor"] = normalize_cursor(feed.get("next_cursor", after_id))
            local_cloud_view_refresh = refresh_local_cloud_views()
            api_fetch_result = {
                "status": "completed",
                "api_base_url": api_config["api_base_url"],
                "written_files": written_files,
                "next_cursor": sync_state["remote_cursor"],
                "view_refresh": local_cloud_view_refresh,
            }
        except Exception as exc:
            api_fetch_result = {
                "status": "failed",
                "api_base_url": api_config["api_base_url"],
                "error": str(exc),
                "written_files": [],
                "next_cursor": normalize_cursor(sync_state.get("remote_cursor", 0)),
            }

    def after_learning_import(stem: str, payload: dict[str, Any]) -> None:
        bilibili_sync_results.append(sync_learning_into_bilibili(stem, payload))

    sync_state["ideas"], imported_ideas = sync_bucket(
        source_dir=IDEAS_DIR,
        destination_dir=LOCAL_IDEAS_DIR,
        known_items=sync_state["ideas"],
        render=render_idea_markdown,
    )
    sync_state["learnings"], imported_learnings = sync_bucket(
        source_dir=LEARNINGS_DIR,
        destination_dir=LOCAL_LEARNINGS_DIR,
        known_items=sync_state["learnings"],
        render=render_learning_markdown,
        after_import=after_learning_import,
    )
    idea_entries = load_payload_entries(IDEAS_DIR)
    learning_entries = load_payload_entries(LEARNINGS_DIR)
    rewrite_local_ledgers(idea_entries, learning_entries)
    minder_idea_logs = rewrite_daily_logs(
        MINDER_DAILY_IDEAS_DIR,
        title_suffix="Ideas",
        entries=idea_entries,
        renderer=render_idea_daily_block,
    )
    minder_learning_logs = rewrite_daily_logs(
        MINDER_DAILY_LEARNINGS_DIR,
        title_suffix="Learning Updates",
        entries=learning_entries,
        renderer=render_learning_daily_block,
    )
    bilibili_sync_results.append(rewrite_bilibili_views(learning_entries))
    write_json(STATE_FILE, sync_state)

    payload = {
        "time": now_iso(),
        "trigger_label": args.trigger_label,
        "repo_base_url": repo_base_url,
        "branch": branch,
        "pull_result": pull_result,
        "api_fetch_result": api_fetch_result,
        "local_cloud_view_refresh": local_cloud_view_refresh,
        "imported_ideas": imported_ideas,
        "imported_learnings": imported_learnings,
        "minder_idea_logs": minder_idea_logs,
        "minder_learning_logs": minder_learning_logs,
        "bilibili_sync_results": bilibili_sync_results,
    }
    SYNC_STATUS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(SYNC_STATUS_JSON, payload)
    SYNC_STATUS_MD.write_text(
        render_sync_status_markdown(
            payload=payload,
            idea_entries=idea_entries,
            learning_entries=learning_entries,
            repo_base_url=repo_base_url,
            branch=branch,
        ),
        encoding="utf-8",
    )
    append_jsonl(RUN_LOG, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
