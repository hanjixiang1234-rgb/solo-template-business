from __future__ import annotations

import argparse
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from process_cloud_issue import (
    article_extract,
    collapse_whitespace,
    heuristic_analysis,
    infer_source_type,
    slugify,
    summarize_with_openai,
    video_extract,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "openai_cloud_hub.sqlite3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ensure_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                title TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                processed_at TEXT,
                source_type TEXT,
                source_url TEXT,
                raw_payload_json TEXT NOT NULL,
                output_payload_json TEXT,
                error_text TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_submissions_status_id
            ON submissions(status, id)
            """
        )
        conn.commit()


def db_connection(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def require_token(headers: Any, expected: str | None) -> bool:
    if not expected:
        return True
    auth = headers.get("Authorization", "")
    return auth == f"Bearer {expected}"


def load_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(content_length) if content_length else b"{}"
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object.")
    return payload


def respond_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Minder-Client")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.end_headers()
    handler.wfile.write(body)


def record_to_api_item(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["output_payload_json"] or "{}")
    return {
        "id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "submitted_at": row["submitted_at"],
        "processed_at": row["processed_at"],
        "title": row["title"],
        "source_type": row["source_type"] or "",
        "source_url": row["source_url"] or "",
        "filename_stem": payload.get("filename_stem", ""),
        "payload": payload,
        "error_text": row["error_text"] or "",
    }


def build_idea_output(submission_id: int, raw_payload: dict[str, Any], base_url: str) -> dict[str, Any]:
    submitted_at = raw_payload["submitted_at"]
    title = collapse_whitespace(raw_payload.get("title", "")) or "灵感"
    filename_stem = f"{submitted_at[:10]}-submission-{submission_id}-{slugify(title)}"
    return {
        "kind": "idea",
        "submission_id": submission_id,
        "submission_url": f"{base_url}/api/v1/submissions/{submission_id}",
        "submitted_at": submitted_at,
        "submitted_by": raw_payload.get("submitted_by", "phone"),
        "title": f"灵感：{title}" if not title.startswith("灵感：") else title,
        "idea_summary": raw_payload.get("idea_summary", ""),
        "why_it_matters": raw_payload.get("why_it_matters", ""),
        "bucket": raw_payload.get("bucket", ""),
        "next_step": raw_payload.get("next_step", ""),
        "raw_sections": raw_payload,
        "filename_stem": filename_stem,
    }


def build_learning_output(submission_id: int, raw_payload: dict[str, Any], base_url: str) -> dict[str, Any]:
    submitted_at = raw_payload["submitted_at"]
    title = collapse_whitespace(raw_payload.get("title", "")) or "学习请求"
    source_url = raw_payload.get("source_url", "").strip()
    source_type = raw_payload.get("source_type", "").strip().lower()
    if source_type not in {"article", "video"}:
        source_type = infer_source_type(source_url)

    filename_stem = f"{submitted_at[:10]}-submission-{submission_id}-{slugify(title)}"
    payload = {
        "kind": "learning",
        "submission_id": submission_id,
        "submission_url": f"{base_url}/api/v1/submissions/{submission_id}",
        "submitted_at": submitted_at,
        "submitted_by": raw_payload.get("submitted_by", "phone"),
        "title": f"学习请求：{title}" if not title.startswith("学习请求：") else title,
        "source_type": source_type,
        "source_url": source_url,
        "source_title": raw_payload.get("source_title", "").strip(),
        "why_good": raw_payload.get("why_good", ""),
        "wanted_outputs": raw_payload.get("wanted_outputs", ""),
        "extra_context": raw_payload.get("extra_context", ""),
        "raw_sections": raw_payload,
        "filename_stem": filename_stem,
    }

    try:
        extraction = article_extract(source_url) if source_type == "article" else video_extract(source_url)
        payload["extraction"] = extraction
        payload["extraction_status"] = "completed"
    except Exception as exc:
        payload["extraction"] = {
            "url": source_url,
            "kind": source_type,
            "title": payload["source_title"] or source_url,
        }
        payload["extraction_status"] = "failed"
        payload["extraction_error"] = str(exc)

    summary, summary_error = summarize_with_openai(payload)
    fallback_summary = heuristic_analysis(payload)
    payload["analysis"] = summary or fallback_summary
    if summary:
        payload["analysis_status"] = "ai_completed"
    elif fallback_summary:
        payload["analysis_status"] = "heuristic_completed"
    elif payload["extraction_status"] == "completed":
        payload["analysis_status"] = "raw_extracted_only"
    else:
        payload["analysis_status"] = "needs_manual_review"
    if summary_error and summary_error != "missing_api_key":
        payload["analysis_error"] = summary_error
    return payload


def process_submission(db_path: Path, submission_id: int, base_url: str) -> None:
    conn = db_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id, kind, raw_payload_json FROM submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
        if row is None:
            return
        raw_payload = json.loads(row["raw_payload_json"])
        if row["kind"] == "idea":
            output_payload = build_idea_output(submission_id, raw_payload, base_url)
        else:
            output_payload = build_learning_output(submission_id, raw_payload, base_url)
        conn.execute(
            """
            UPDATE submissions
            SET status = ?, processed_at = ?, output_payload_json = ?, error_text = ?
            WHERE id = ?
            """,
            ("completed", now_iso(), json.dumps(output_payload, ensure_ascii=False), "", submission_id),
        )
        conn.commit()
    except Exception as exc:
        conn.execute(
            """
            UPDATE submissions
            SET status = ?, processed_at = ?, error_text = ?
            WHERE id = ?
            """,
            ("failed", now_iso(), str(exc), submission_id),
        )
        conn.commit()
    finally:
        conn.close()


def spawn_processor(db_path: Path, submission_id: int, base_url: str) -> None:
    thread = threading.Thread(
        target=process_submission,
        args=(db_path, submission_id, base_url),
        daemon=True,
    )
    thread.start()


class CloudHubHandler(BaseHTTPRequestHandler):
    server_version = "OpenAICloudHub/0.1"

    @property
    def db_path(self) -> Path:
        return Path(self.server.db_path)  # type: ignore[attr-defined]

    @property
    def write_token(self) -> str | None:
        return self.server.write_token  # type: ignore[attr-defined]

    @property
    def read_token(self) -> str | None:
        return self.server.read_token  # type: ignore[attr-defined]

    @property
    def base_url(self) -> str:
        return self.server.base_url  # type: ignore[attr-defined]

    def do_OPTIONS(self) -> None:
        respond_json(self, HTTPStatus.OK, {"ok": True})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            respond_json(self, HTTPStatus.OK, {"ok": True, "time": now_iso()})
            return

        if parsed.path == "/api/v1/feed":
            if not require_token(self.headers, self.read_token):
                respond_json(self, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            query = parse_qs(parsed.query)
            after_id = int((query.get("after_id") or ["0"])[0] or "0")
            limit = min(int((query.get("limit") or ["100"])[0] or "100"), 200)
            conn = db_connection(self.db_path)
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM submissions
                    WHERE status = 'completed' AND id > ?
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (after_id, limit),
                ).fetchall()
                items = [record_to_api_item(row) for row in rows]
                next_cursor = items[-1]["id"] if items else after_id
                respond_json(self, HTTPStatus.OK, {"items": items, "next_cursor": next_cursor})
            finally:
                conn.close()
            return

        if parsed.path == "/api/v1/overview":
            if not require_token(self.headers, self.read_token):
                respond_json(self, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            conn = db_connection(self.db_path)
            try:
                latest_idea = conn.execute(
                    "SELECT * FROM submissions WHERE kind = 'idea' AND status = 'completed' ORDER BY id DESC LIMIT 1"
                ).fetchone()
                latest_learning = conn.execute(
                    "SELECT * FROM submissions WHERE kind = 'learning' AND status = 'completed' ORDER BY id DESC LIMIT 1"
                ).fetchone()
                respond_json(
                    self,
                    HTTPStatus.OK,
                    {
                        "latest_idea": record_to_api_item(latest_idea) if latest_idea else None,
                        "latest_learning": record_to_api_item(latest_learning) if latest_learning else None,
                    },
                )
            finally:
                conn.close()
            return

        if parsed.path.startswith("/api/v1/submissions/"):
            if not require_token(self.headers, self.read_token):
                respond_json(self, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            try:
                submission_id = int(parsed.path.rsplit("/", 1)[-1])
            except ValueError:
                respond_json(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_submission_id"})
                return
            conn = db_connection(self.db_path)
            try:
                row = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
                if row is None:
                    respond_json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
                payload = {
                    "id": row["id"],
                    "kind": row["kind"],
                    "status": row["status"],
                    "title": row["title"],
                    "submitted_at": row["submitted_at"],
                    "processed_at": row["processed_at"],
                    "source_type": row["source_type"] or "",
                    "source_url": row["source_url"] or "",
                    "raw_payload": json.loads(row["raw_payload_json"]),
                    "output_payload": json.loads(row["output_payload_json"] or "{}"),
                    "error_text": row["error_text"] or "",
                }
                respond_json(self, HTTPStatus.OK, payload)
            finally:
                conn.close()
            return

        respond_json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/v1/submissions":
            respond_json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        if not require_token(self.headers, self.write_token):
            respond_json(self, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return

        try:
            payload = load_json_body(self)
        except Exception as exc:
            respond_json(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        kind = (payload.get("kind") or "").strip().lower()
        if kind not in {"idea", "learning"}:
            respond_json(self, HTTPStatus.BAD_REQUEST, {"error": "kind must be idea or learning"})
            return

        title = collapse_whitespace(payload.get("title", ""))
        if not title:
            respond_json(self, HTTPStatus.BAD_REQUEST, {"error": "title is required"})
            return

        if kind == "learning" and not collapse_whitespace(payload.get("source_url", "")):
            respond_json(self, HTTPStatus.BAD_REQUEST, {"error": "source_url is required for learning"})
            return

        submitted_at = now_iso()
        raw_payload = {
            **payload,
            "submitted_at": submitted_at,
            "submitted_by": collapse_whitespace(self.headers.get("X-Minder-Client", "")) or "phone-portal",
        }

        conn = db_connection(self.db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO submissions (
                    kind, status, title, submitted_at, source_type, source_url, raw_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kind,
                    "queued",
                    title,
                    submitted_at,
                    payload.get("source_type", ""),
                    payload.get("source_url", ""),
                    json.dumps(raw_payload, ensure_ascii=False),
                ),
            )
            submission_id = int(cursor.lastrowid)
            conn.commit()
        finally:
            conn.close()

        spawn_processor(self.db_path, submission_id, self.base_url)
        respond_json(
            self,
            HTTPStatus.ACCEPTED,
            {
                "id": submission_id,
                "kind": kind,
                "status": "queued",
                "detail_url": f"{self.base_url}/api/v1/submissions/{submission_id}",
            },
        )


def make_server(host: str, port: int, db_path: Path) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), CloudHubHandler)
    server.db_path = str(db_path)  # type: ignore[attr-defined]
    server.write_token = os.environ.get("MINDER_CLOUD_WRITE_TOKEN")  # type: ignore[attr-defined]
    server.read_token = os.environ.get("MINDER_CLOUD_READ_TOKEN") or os.environ.get("MINDER_CLOUD_WRITE_TOKEN")  # type: ignore[attr-defined]
    public_base = os.environ.get("MINDER_CLOUD_PUBLIC_BASE_URL", "").rstrip("/")
    server.base_url = public_base or f"http://{host}:{port}"  # type: ignore[attr-defined]
    return server


def main() -> None:
    args = parse_args()
    db_path = Path(args.db_path).resolve()
    ensure_db(db_path)
    server = make_server(args.host, args.port, db_path)
    print(
        json.dumps(
            {
                "host": args.host,
                "port": args.port,
                "db_path": str(db_path),
                "base_url": server.base_url,  # type: ignore[attr-defined]
            },
            ensure_ascii=False,
        )
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
