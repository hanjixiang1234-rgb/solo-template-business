from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
from datetime import datetime
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from run_xiaohongshu_publish_queue import (
    DEFAULT_SLOT_TIMES,
    QUEUE_FILE,
    build_plan,
    count_statuses,
    load_queue,
    now_local,
)
from sync_xhs_mobile_inbox import INCOMING_DIR, RUN_LOG_FILE


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_ROOT = PROJECT_ROOT / "mobile_panel"
CONTENT_DIR = PROJECT_ROOT / "content" / "xiaohongshu"
ASSETS_DIR = PROJECT_ROOT / "assets" / "rendered"
PUBLISH_RUNS_FILE = PROJECT_ROOT / "data" / "publish_runs.jsonl"
SYNC_SCRIPT = PROJECT_ROOT / "scripts" / "sync_xhs_mobile_inbox.py"
RECONCILE_SCRIPT = PROJECT_ROOT / "scripts" / "run_xiaohongshu_publish_queue.py"
SLOT_TIMES = dict(DEFAULT_SLOT_TIMES)
SUPPORTED_STATIC_DIRS = {
    "/assets/": PROJECT_ROOT / "assets",
    "/mobile_panel/": PANEL_ROOT,
}
TITLE_RE = re.compile(r"Title options:\n- (.+)")
CAPTION_RE = re.compile(r"Caption:\n\n(.+?)\n\nCTA:", re.S)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def read_jsonl_tail(path: Path, limit: int = 8) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payloads: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                payloads.append(payload)
        except json.JSONDecodeError:
            continue
    return list(reversed(payloads))


def parse_post_metadata(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    title_match = TITLE_RE.search(text)
    caption_match = CAPTION_RE.search(text)
    post_slug = path.stem.lower()
    cover_path = ASSETS_DIR / post_slug / "00_cover.png"
    return {
        "id": path.stem,
        "filename": path.name,
        "relative_path": path.relative_to(PROJECT_ROOT).as_posix(),
        "title": title_match.group(1).strip() if title_match else path.stem,
        "caption": caption_match.group(1).strip() if caption_match else "",
        "cover_url": f"/assets/rendered/{post_slug}/00_cover.png" if cover_path.exists() else None,
    }


def queue_entries_with_index(queue: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(queue):
        post = entry.get("post")
        if isinstance(post, str):
            merged = dict(entry)
            merged["queue_index"] = index
            entries[post] = merged
    return entries


def available_posts(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue_lookup = queue_entries_with_index(queue)
    posts = sorted(CONTENT_DIR.glob("POST_*.md"))
    payload: list[dict[str, Any]] = []
    for path in posts:
        metadata = parse_post_metadata(path)
        queue_state = queue_lookup.get(metadata["relative_path"])
        metadata["queue_entry"] = queue_state
        payload.append(metadata)
    return payload


def incoming_requests() -> list[dict[str, Any]]:
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in INCOMING_DIR.iterdir() if path.is_file() and not path.name.startswith("_"))
    return [
        {
            "name": path.name,
            "size": path.stat().st_size,
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
        }
        for path in files
    ]


def upcoming_plan(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = build_plan(
        queue,
        mode="reconcile",
        slot=None,
        lookahead=6,
        minimum_lead_minutes=180,
        slot_times=SLOT_TIMES,
        now=now_local(),
    )
    return plan


def queue_snapshot() -> dict[str, Any]:
    queue = load_queue(QUEUE_FILE)
    return {
        "generated_at": now_local().isoformat(timespec="seconds"),
        "queue_summary": count_statuses(queue),
        "queue": queue,
        "posts": available_posts(queue),
        "incoming_requests": incoming_requests(),
        "upcoming_plan": upcoming_plan(queue),
        "recent_publish_runs": read_jsonl_tail(PUBLISH_RUNS_FILE),
        "recent_mobile_inbox_runs": read_jsonl_tail(RUN_LOG_FILE),
    }


def create_request_file(prefix: str, payload: dict[str, Any]) -> Path:
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = now_local().strftime("%Y%m%d-%H%M%S")
    safe_prefix = re.sub(r"[^a-z0-9_-]+", "-", prefix.lower()).strip("-") or "request"
    candidate = INCOMING_DIR / f"{timestamp}-{safe_prefix}.json"
    counter = 1
    while candidate.exists():
        candidate = INCOMING_DIR / f"{timestamp}-{safe_prefix}-{counter}.json"
        counter += 1
    candidate.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return candidate


def run_subprocess(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def sync_inbox(*, dry_run: bool, trigger_label: str) -> dict[str, Any]:
    command = [sys.executable, str(SYNC_SCRIPT), "--trigger-label", trigger_label]
    if dry_run:
        command.append("--dry-run")
    return run_subprocess(command)


def reconcile_queue(*, dry_run: bool, trigger_label: str) -> dict[str, Any]:
    command = [sys.executable, str(RECONCILE_SCRIPT), "--mode", "reconcile", "--trigger-label", trigger_label]
    if dry_run:
        command.append("--dry-run")
    return run_subprocess(command)


def detect_lan_ip() -> str | None:
    for interface in ("en0", "en1"):
        try:
            result = subprocess.run(
                ["ipconfig", "getifaddr", interface],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            result = None
        if result and result.returncode == 0:
            candidate = result.stdout.strip()
            if candidate:
                return candidate
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return None


class MobilePanelHandler(BaseHTTPRequestHandler):
    server_version = "MobilePanel/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self.send_json(queue_snapshot())
            return
        if parsed.path == "/api/health":
            self.send_json({"status": "ok", "time": now_local().isoformat(timespec="seconds")})
            return
        if parsed.path == "/" or parsed.path == "/index.html":
            self.serve_file(PANEL_ROOT / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/assets/") or parsed.path.startswith("/mobile_panel/"):
            static_path = self.resolve_static_path(parsed.path)
            if static_path is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
                return
            self.serve_file(static_path, self.guess_content_type(static_path))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self.read_json_body()
        if payload is None:
            return

        if parsed.path == "/api/requests/queue-post":
            post_filename = str(payload.get("post", "")).strip()
            slot = str(payload.get("slot", "")).strip().lower()
            note = str(payload.get("note", "")).strip()
            import_now = bool(payload.get("import_now", True))
            if not post_filename or slot not in {"morning", "night"}:
                self.send_json({"error": "post and slot are required"}, status=HTTPStatus.BAD_REQUEST)
                return
            request_file = create_request_file(
                "queue-post",
                {"type": "queue_existing_post", "post": post_filename, "slot": slot, "note": note},
            )
            sync_result = sync_inbox(dry_run=False, trigger_label="mobile-panel-queue-post") if import_now else None
            self.send_json(
                {
                    "ok": True,
                    "request_file": request_file.name,
                    "sync_result": sync_result,
                    "status": queue_snapshot(),
                }
            )
            return

        if parsed.path == "/api/requests/note-idea":
            title = str(payload.get("title", "")).strip()
            slot = str(payload.get("slot", "")).strip().lower()
            notes = str(payload.get("notes", "")).strip()
            import_now = bool(payload.get("import_now", True))
            if not title:
                self.send_json({"error": "title is required"}, status=HTTPStatus.BAD_REQUEST)
                return
            request_file = create_request_file(
                "note-idea",
                {"type": "note_idea", "title": title, "slot": slot, "notes": notes},
            )
            sync_result = sync_inbox(dry_run=False, trigger_label="mobile-panel-note-idea") if import_now else None
            self.send_json(
                {
                    "ok": True,
                    "request_file": request_file.name,
                    "sync_result": sync_result,
                    "status": queue_snapshot(),
                }
            )
            return

        if parsed.path == "/api/actions/sync-inbox":
            dry_run = bool(payload.get("dry_run", True))
            result = sync_inbox(dry_run=dry_run, trigger_label="mobile-panel-sync")
            self.send_json({"ok": result["returncode"] == 0, "result": result, "status": queue_snapshot()})
            return

        if parsed.path == "/api/actions/reconcile":
            dry_run = bool(payload.get("dry_run", True))
            result = reconcile_queue(dry_run=dry_run, trigger_label="mobile-panel-reconcile")
            self.send_json({"ok": result["returncode"] == 0, "result": result, "status": queue_snapshot()})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def read_json_body(self) -> dict[str, Any] | None:
        length = self.headers.get("Content-Length")
        if not length:
            return {}
        raw = self.rfile.read(int(length))
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON body"}, status=HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(payload, dict):
            self.send_json({"error": "JSON body must be an object"}, status=HTTPStatus.BAD_REQUEST)
            return None
        return payload

    def resolve_static_path(self, request_path: str) -> Path | None:
        for prefix, root in SUPPORTED_STATIC_DIRS.items():
            if request_path.startswith(prefix):
                relative = request_path[len(prefix) :]
                candidate = (root / relative).resolve()
                if candidate.is_file() and candidate.is_relative_to(root.resolve()):
                    return candidate
        return None

    def serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def guess_content_type(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".css":
            return "text/css; charset=utf-8"
        if suffix == ".js":
            return "application/javascript; charset=utf-8"
        if suffix == ".json":
            return "application/json; charset=utf-8"
        if suffix == ".webmanifest":
            return "application/manifest+json; charset=utf-8"
        if suffix == ".png":
            return "image/png"
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        return "application/octet-stream"

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    args = parse_args()
    handler = partial(MobilePanelHandler)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    lan_ip = detect_lan_ip()
    print(f"Mobile panel server running on http://127.0.0.1:{args.port}")
    if lan_ip:
        print(f"LAN URL: http://{lan_ip}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
