from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUEUE_FILE = PROJECT_ROOT / "data" / "publish_queue.json"
RUN_LOG_FILE = PROJECT_ROOT / "data" / "mobile_inbox_runs.jsonl"
IDEA_LOG_FILE = PROJECT_ROOT / "data" / "mobile_idea_requests.jsonl"
ICLOUD_ROOT = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Codex Sync" / "XHS Inbox"
INCOMING_DIR = ICLOUD_ROOT / "incoming"
PROCESSED_DIR = ICLOUD_ROOT / "processed"
FAILED_DIR = ICLOUD_ROOT / "failed"
SUPPORTED_EXTS = {".md", ".txt", ".json"}
VALID_SLOTS = {"morning", "night"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--incoming-dir", default=str(INCOMING_DIR))
    parser.add_argument("--processed-dir", default=str(PROCESSED_DIR))
    parser.add_argument("--failed-dir", default=str(FAILED_DIR))
    parser.add_argument("--queue-file", default=str(QUEUE_FILE))
    parser.add_argument("--run-log-file", default=str(RUN_LOG_FILE))
    parser.add_argument("--idea-log-file", default=str(IDEA_LOG_FILE))
    parser.add_argument("--trigger-label", default="manual")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso_local(dt: datetime) -> str:
    return dt.astimezone().isoformat(timespec="seconds")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_queue(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_queue(path: Path, queue: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_key_value_text(text: str) -> dict[str, str]:
    payload: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def commit() -> None:
        nonlocal current_key, current_lines
        if current_key is None:
            return
        payload[current_key] = "\n".join(line for line in current_lines if line is not None).strip()
        current_key = None
        current_lines = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            if current_key is not None:
                current_lines.append("")
            continue
        if line.lstrip().startswith("#"):
            continue
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            normalized_key = key.strip().lower().replace(" ", "_")
            if normalized_key:
                commit()
                current_key = normalized_key
                current_lines = [value.strip()]
                continue
        if current_key is not None:
            current_lines.append(line.strip())
    commit()
    return payload


def parse_request_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("JSON request files must contain an object at the top level.")
        return payload
    return parse_key_value_text(text)


def resolve_post_path(post_value: str) -> Path:
    candidate = Path(post_value)
    if candidate.is_absolute() and candidate.exists():
        return candidate.resolve()

    normalized = candidate.as_posix()
    possible_paths = [
        PROJECT_ROOT / normalized,
        PROJECT_ROOT / "content" / "xiaohongshu" / normalized,
    ]
    if "/" not in normalized:
        possible_paths.append(PROJECT_ROOT / "content" / "xiaohongshu" / normalized)

    for possible in possible_paths:
        if possible.exists():
            return possible.resolve()
    raise FileNotFoundError(f"Could not resolve post path: {post_value}")


def next_destination(path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    candidate = destination_dir / path.name
    if not candidate.exists():
        return candidate
    stem = path.stem
    suffix = path.suffix
    index = 1
    while True:
        candidate = destination_dir / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def move_request_file(path: Path, destination_dir: Path) -> Path:
    destination = next_destination(path, destination_dir)
    shutil.move(str(path), str(destination))
    return destination


def count_statuses(queue: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in queue:
        status = entry.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def queue_contains_post(queue: list[dict[str, Any]], post_relpath: str) -> bool:
    for entry in queue:
        if entry.get("post") == post_relpath:
            return True
    return False


def process_queue_existing_post(
    request: dict[str, Any],
    *,
    queue: list[dict[str, Any]],
    request_name: str,
    now: datetime,
) -> dict[str, Any]:
    slot = str(request.get("slot", "")).strip().lower()
    if slot not in VALID_SLOTS:
        raise ValueError("queue_existing_post requests must use slot: morning or slot: night")

    post_path = resolve_post_path(str(request.get("post", "")).strip())
    post_relpath = post_path.relative_to(PROJECT_ROOT).as_posix()
    if queue_contains_post(queue, post_relpath):
        return {
            "status": "skipped_duplicate",
            "request_type": "queue_existing_post",
            "post": post_relpath,
            "slot": slot,
        }

    entry: dict[str, Any] = {
        "slot": slot,
        "post": post_relpath,
        "status": "pending",
        "source": "mobile_inbox",
        "request_file": request_name,
        "requested_at": iso_local(now),
    }
    note = str(request.get("note", "")).strip()
    if note:
        entry["request_note"] = note
    queue.append(entry)
    return {
        "status": "queued",
        "request_type": "queue_existing_post",
        "post": post_relpath,
        "slot": slot,
    }


def process_note_idea(
    request: dict[str, Any],
    *,
    request_name: str,
    idea_log_file: Path,
    now: datetime,
) -> dict[str, Any]:
    idea_payload = {
        "time": iso_local(now),
        "request_file": request_name,
        "type": "note_idea",
        "slot": str(request.get("slot", "")).strip().lower() or None,
        "title": str(request.get("title", "")).strip(),
        "notes": str(request.get("notes", "")).strip(),
    }
    append_jsonl(idea_log_file, idea_payload)
    return {
        "status": "captured_idea",
        "request_type": "note_idea",
        "title": idea_payload["title"],
        "slot": idea_payload["slot"],
    }


def main() -> None:
    args = parse_args()
    incoming_dir = Path(args.incoming_dir).expanduser().resolve()
    processed_dir = Path(args.processed_dir).expanduser().resolve()
    failed_dir = Path(args.failed_dir).expanduser().resolve()
    queue_file = Path(args.queue_file).expanduser().resolve()
    run_log_file = Path(args.run_log_file).expanduser().resolve()
    idea_log_file = Path(args.idea_log_file).expanduser().resolve()
    now = now_local()

    incoming_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    queue = load_queue(queue_file)
    requests = sorted(
        path
        for path in incoming_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTS and not path.name.startswith("_")
    )

    if not requests:
        append_jsonl(
            run_log_file,
            {
                "time": iso_local(now),
                "trigger_label": args.trigger_label,
                "status": "noop",
                "message": "No mobile inbox requests found.",
            },
        )
        print("No mobile inbox requests found.")
        return

    queue_changed = False
    results: list[dict[str, Any]] = []

    for request_path in requests:
        try:
            request = parse_request_file(request_path)
            request_type = str(request.get("type", "queue_existing_post")).strip().lower()
            if request_type == "queue_existing_post":
                result = process_queue_existing_post(
                    request,
                    queue=queue,
                    request_name=request_path.name,
                    now=now_local(),
                )
                queue_changed = queue_changed or result["status"] == "queued"
            elif request_type == "note_idea":
                result = process_note_idea(
                    request,
                    request_name=request_path.name,
                    idea_log_file=idea_log_file,
                    now=now_local(),
                )
            else:
                raise ValueError(f"Unsupported request type: {request_type}")

            result["request_file"] = request_path.name
            if not args.dry_run:
                destination = move_request_file(request_path, processed_dir)
                result["moved_to"] = destination.name
        except Exception as exc:
            result = {
                "status": "failed",
                "request_file": request_path.name,
                "error": str(exc),
            }
            if not args.dry_run:
                move_request_file(request_path, failed_dir)
        results.append(result)

    if queue_changed and not args.dry_run:
        save_queue(queue_file, queue)

    summary = {
        "time": iso_local(now_local()),
        "trigger_label": args.trigger_label,
        "status": "dry_run" if args.dry_run else "completed",
        "results": results,
        "queue_summary": count_statuses(queue),
    }
    append_jsonl(run_log_file, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
