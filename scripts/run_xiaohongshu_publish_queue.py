from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUEUE_FILE = PROJECT_ROOT / "data" / "publish_queue.json"
LOG_FILE = PROJECT_ROOT / "data" / "publish_runs.jsonl"
PUBLISH_SCRIPT = PROJECT_ROOT / "scripts" / "publish_xiaohongshu_note.py"
DEFAULT_SLOT_TIMES = {"morning": "07:40", "night": "21:10"}
SCHEDULE_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["reconcile", "slot"], default="reconcile")
    parser.add_argument("--slot", choices=["morning", "night"])
    parser.add_argument("--queue-file", default=str(QUEUE_FILE))
    parser.add_argument("--log-file", default=str(LOG_FILE))
    parser.add_argument("--publish-script", default=str(PUBLISH_SCRIPT))
    parser.add_argument("--lookahead", type=int, default=6)
    parser.add_argument("--minimum-lead-minutes", type=int, default=180)
    parser.add_argument("--morning-time", default=DEFAULT_SLOT_TIMES["morning"])
    parser.add_argument("--night-time", default=DEFAULT_SLOT_TIMES["night"])
    parser.add_argument("--trigger-label", default="manual")
    parser.add_argument("--connectivity-url", default="https://creator.xiaohongshu.com")
    parser.add_argument("--skip-network-check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.mode == "slot" and not args.slot:
        parser.error("--slot is required when --mode slot is used")
    return args


def load_queue(queue_file: Path) -> list[dict[str, Any]]:
    return json.loads(queue_file.read_text(encoding="utf-8"))


def save_queue(queue_file: Path, queue: list[dict[str, Any]]) -> None:
    queue_file.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_log(log_file: Path, payload: dict[str, Any]) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def now_local() -> datetime:
    return datetime.now().astimezone()


def iso_local(dt: datetime) -> str:
    return dt.astimezone().isoformat(timespec="seconds")


def format_schedule_at(dt: datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def has_network(connectivity_url: str) -> bool:
    request = Request(connectivity_url, method="HEAD")
    try:
        with urlopen(request, timeout=5):
            return True
    except URLError:
        return False
    except Exception:
        return False


def parse_slot_time(value: str) -> tuple[int, int]:
    hour_str, minute_str = value.split(":", 1)
    return int(hour_str), int(minute_str)


def parse_entry_schedule(entry: dict[str, Any]) -> datetime | None:
    candidates = [
        entry.get("native_schedule_at"),
        entry.get("scheduled_for"),
        entry.get("scheduled_publish_at"),
    ]
    note = entry.get("note")
    if isinstance(note, str):
        match = SCHEDULE_RE.search(note)
        if match:
            candidates.append(match.group(1))

    for candidate in candidates:
        if not candidate:
            continue
        try:
            if isinstance(candidate, str) and "T" in candidate:
                return datetime.fromisoformat(candidate)
            if isinstance(candidate, str):
                return datetime.strptime(candidate, "%Y-%m-%d %H:%M").replace(tzinfo=now_local().tzinfo)
        except ValueError:
            continue
    return None


def pending_entries(
    queue: list[dict[str, Any]],
    mode: str,
    slot: str | None,
    lookahead: int,
) -> list[tuple[int, dict[str, Any]]]:
    indexed_entries: list[tuple[int, dict[str, Any]]] = []
    for index, entry in enumerate(queue):
        if entry.get("status") != "pending":
            continue
        if mode == "slot" and entry.get("slot") != slot:
            continue
        indexed_entries.append((index, entry))
        if mode == "slot":
            break
        if len(indexed_entries) >= lookahead:
            break
    return indexed_entries


def next_slot_datetime(slot: str, earliest: datetime, slot_times: dict[str, str]) -> datetime:
    hour, minute = parse_slot_time(slot_times[slot])
    candidate = earliest.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate < earliest:
        candidate += timedelta(days=1)
    return candidate


def existing_reserved_slots(queue: list[dict[str, Any]], now: datetime) -> set[str]:
    reserved: set[str] = set()
    for entry in queue:
        if entry.get("status") != "scheduled_native":
            continue
        scheduled_for = parse_entry_schedule(entry)
        if scheduled_for and scheduled_for >= now:
            reserved.add(format_schedule_at(scheduled_for))
    return reserved


def build_plan(
    queue: list[dict[str, Any]],
    mode: str,
    slot: str | None,
    lookahead: int,
    minimum_lead_minutes: int,
    slot_times: dict[str, str],
    now: datetime,
) -> list[dict[str, Any]]:
    selected = pending_entries(queue, mode=mode, slot=slot, lookahead=lookahead)
    reserved = existing_reserved_slots(queue, now)
    earliest = now + timedelta(minutes=minimum_lead_minutes)
    plan: list[dict[str, Any]] = []

    for index, entry in selected:
        candidate = next_slot_datetime(entry["slot"], earliest, slot_times)
        while format_schedule_at(candidate) in reserved:
            candidate = next_slot_datetime(entry["slot"], candidate + timedelta(minutes=1), slot_times)
        reserved.add(format_schedule_at(candidate))
        plan.append(
            {
                "queue_index": index,
                "post": entry["post"],
                "slot": entry["slot"],
                "schedule_at": format_schedule_at(candidate),
            }
        )
        earliest = candidate + timedelta(minutes=1)

    return plan


def count_statuses(queue: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in queue:
        status = entry.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def queue_summary(queue: list[dict[str, Any]]) -> str:
    counts = count_statuses(queue)
    ordered = [f"{key}={counts[key]}" for key in sorted(counts)]
    return ", ".join(ordered)


def make_receipt(
    *,
    now: datetime,
    trigger_label: str,
    mode: str,
    status: str,
    queue: list[dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "time": iso_local(now),
        "trigger_label": trigger_label,
        "mode": mode,
        "status": status,
        "queue_summary": count_statuses(queue),
    }
    receipt.update(extra)
    return receipt


def run_publish_command(
    publish_script: Path,
    post_path: Path,
    schedule_at: str,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable or "python3",
        str(publish_script),
        str(post_path),
        "--schedule-at",
        schedule_at,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def apply_scheduled_result(
    entry: dict[str, Any],
    *,
    now: datetime,
    schedule_at: str,
    stdout: str,
) -> None:
    entry["status"] = "scheduled_native"
    entry["last_attempt_at"] = iso_local(now)
    entry["native_schedule_at"] = schedule_at
    entry["scheduled_at"] = iso_local(now)
    entry["last_error"] = ""
    entry["publish_output"] = stdout
    entry["note"] = f"Queued in Xiaohongshu native scheduler for {schedule_at}"


def apply_error_result(
    entry: dict[str, Any],
    *,
    now: datetime,
    schedule_at: str,
    stderr: str,
) -> None:
    entry["last_attempt_at"] = iso_local(now)
    entry["last_error"] = stderr[-4000:]
    entry["last_schedule_attempt"] = schedule_at
    entry["schedule_attempts"] = int(entry.get("schedule_attempts", 0)) + 1


def main() -> None:
    args = parse_args()
    queue_file = Path(args.queue_file).expanduser().resolve()
    log_file = Path(args.log_file).expanduser().resolve()
    publish_script = Path(args.publish_script).expanduser().resolve()
    queue = load_queue(queue_file)
    now = now_local()
    slot_times = {"morning": args.morning_time, "night": args.night_time}

    plan = build_plan(
        queue,
        mode=args.mode,
        slot=args.slot,
        lookahead=args.lookahead,
        minimum_lead_minutes=args.minimum_lead_minutes,
        slot_times=slot_times,
        now=now,
    )

    if not plan:
        receipt = make_receipt(
            now=now,
            trigger_label=args.trigger_label,
            mode=args.mode,
            status="noop",
            queue=queue,
            message="No pending queue item matched this run.",
            slot=args.slot,
        )
        append_log(log_file, receipt)
        print("No pending queue item.")
        print(queue_summary(queue))
        return

    if args.dry_run:
        receipt = make_receipt(
            now=now,
            trigger_label=args.trigger_label,
            mode=args.mode,
            status="dry_run",
            queue=queue,
            planned_actions=plan,
            slot=args.slot,
        )
        append_log(log_file, receipt)
        print(json.dumps({"planned_actions": plan, "queue_summary": count_statuses(queue)}, ensure_ascii=False, indent=2))
        return

    if not args.skip_network_check and not has_network(args.connectivity_url):
        receipt = make_receipt(
            now=now,
            trigger_label=args.trigger_label,
            mode=args.mode,
            status="deferred_offline",
            queue=queue,
            planned_actions=plan,
            slot=args.slot,
            message=f"Connectivity check failed for {args.connectivity_url}",
        )
        append_log(log_file, receipt)
        print("Deferred because the network check failed.")
        print(queue_summary(queue))
        return

    results: list[dict[str, Any]] = []
    queue_changed = False

    for action in plan:
        entry = queue[action["queue_index"]]
        post_path = (PROJECT_ROOT / entry["post"]).resolve()
        result = run_publish_command(publish_script, post_path, action["schedule_at"])
        stdout = result.stdout.strip()
        stderr = (result.stderr or result.stdout).strip()

        if result.returncode == 0:
            apply_scheduled_result(entry, now=now_local(), schedule_at=action["schedule_at"], stdout=stdout)
            queue_changed = True
            status = "scheduled_native"
        else:
            apply_error_result(entry, now=now_local(), schedule_at=action["schedule_at"], stderr=stderr)
            queue_changed = True
            status = "error"

        action_result = {
            "post": entry["post"],
            "slot": entry["slot"],
            "scheduled_for": action["schedule_at"],
            "status": status,
            "stdout": stdout,
        }
        if stderr and status == "error":
            action_result["stderr"] = stderr
        results.append(action_result)

        append_log(
            log_file,
            make_receipt(
                now=now_local(),
                trigger_label=args.trigger_label,
                mode=args.mode,
                status=status,
                queue=queue,
                slot=args.slot,
                **action_result,
            ),
        )

    if queue_changed:
        save_queue(queue_file, queue)

    success_count = sum(1 for result in results if result["status"] == "scheduled_native")
    error_count = sum(1 for result in results if result["status"] == "error")
    summary_status = "completed_with_errors" if error_count else "completed"
    append_log(
        log_file,
        make_receipt(
            now=now_local(),
            trigger_label=args.trigger_label,
            mode=args.mode,
            status=summary_status,
            queue=queue,
            slot=args.slot,
            success_count=success_count,
            error_count=error_count,
            results=results,
        ),
    )

    print(f"scheduled_native={success_count} error={error_count}")
    print(queue_summary(queue))

    if error_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
