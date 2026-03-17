from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import requests  # type: ignore
except ImportError:
    requests = None


SECTION_RE = re.compile(r"^###\s+(.+?)\n(.*?)(?=^###\s+|\Z)", re.S | re.M)
URL_RE = re.compile(r"https?://\S+")
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
VIDEO_HOST_HINTS = (
    "b23.tv",
    "youtube.com",
    "youtu.be",
    "bilibili.com",
    "douyin.com",
    "tiktok.com",
    "vimeo.com",
    "x.com",
    "twitter.com",
    "xiaohongshu.com",
)
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-path", required=True)
    parser.add_argument("--repo-root", required=True)
    return parser.parse_args()


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value.strip()).strip("-").lower()
    return normalized or "item"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_issue_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for heading, content in SECTION_RE.findall(body or ""):
        key = heading.strip().lower().replace(" ", "_")
        sections[key] = content.strip()
    return sections


def extract_first_url(text: str) -> str:
    match = URL_RE.search(text or "")
    return match.group(0).rstrip(").,]") if match else ""


def infer_source_type(source_url: str) -> str:
    parsed = urlparse(source_url)
    hostname = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if any(hint in hostname for hint in VIDEO_HOST_HINTS):
        return "video"
    if Path(path).suffix in VIDEO_EXTENSIONS:
        return "video"
    return "article"


def clean_json_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    match = re.search(r"\{.*\}", stripped, re.S)
    return match.group(0).strip() if match else stripped


def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def truncate_text(text: str, limit: int = 240) -> str:
    collapsed = collapse_whitespace(text)
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def split_hint_items(text: str) -> list[str]:
    items = [collapse_whitespace(part) for part in re.split(r"[，,、；;。/\n]+", text or "")]
    return [item for item in items if item]


def looks_like_url(text: str) -> bool:
    return bool(text and URL_RE.fullmatch(text.strip()))


def extract_meta_value(html: str, keys: tuple[str, ...]) -> str:
    patterns = []
    for key in keys:
        patterns.extend(
            [
                rf'<meta[^>]+property=["\']{re.escape(key)}["\'][^>]+content=["\'](.*?)["\']',
                rf'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']{re.escape(key)}["\']',
                rf'<meta[^>]+name=["\']{re.escape(key)}["\'][^>]+content=["\'](.*?)["\']',
                rf'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']{re.escape(key)}["\']',
            ]
        )
    for pattern in patterns:
        match = re.search(pattern, html, re.I | re.S)
        if match:
            return collapse_whitespace(re.sub(r"<[^>]+>", " ", match.group(1)))
    return ""


def fetch_text_response(url: str) -> tuple[str, str]:
    if requests is not None:
        response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.text, response.url

    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=20) as response:
            content = response.read().decode("utf-8", errors="ignore")
            return content, response.geturl()
    except (HTTPError, URLError) as exc:
        raise RuntimeError(str(exc)) from exc


def fetch_headers(url: str) -> tuple[dict[str, str], str]:
    if requests is not None:
        with requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}, stream=True) as response:
            response.raise_for_status()
            return dict(response.headers), response.url

    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=30) as response:
            return {key: value for key, value in response.headers.items()}, response.geturl()
    except (HTTPError, URLError) as exc:
        raise RuntimeError(str(exc)) from exc


def issue_metadata(event_payload: dict[str, Any]) -> dict[str, Any]:
    issue = event_payload["issue"]
    labels = [label["name"] for label in issue.get("labels", [])]
    return {
        "number": issue["number"],
        "title": issue["title"],
        "body": issue.get("body", ""),
        "html_url": issue["html_url"],
        "labels": labels,
        "created_at": issue["created_at"],
        "updated_at": issue["updated_at"],
        "user": issue["user"]["login"],
    }


def choose_issue_kind(meta: dict[str, Any]) -> str | None:
    labels = meta.get("labels", [])
    if "idea-inbox" in labels:
        return "idea"
    if "learning-request" in labels:
        return "learning"
    title = (meta.get("title") or "").strip()
    body = meta.get("body") or ""
    if title.startswith("灵感：") or "### 灵感一句话" in body:
        return "idea"
    if title.startswith("学习请求：") or "### 来源类型" in body:
        return "learning"
    return None


def save_idea_payload(repo_root: Path, meta: dict[str, Any], sections: dict[str, str]) -> Path:
    created_at = datetime.fromisoformat(meta["created_at"].replace("Z", "+00:00"))
    filename = f"{created_at.strftime('%Y-%m-%d')}-issue-{meta['number']}-{slugify(meta['title'])}.json"
    destination = repo_root / "cloud" / "inbox" / "ideas" / filename
    payload = {
        "kind": "idea",
        "issue_number": meta["number"],
        "issue_url": meta["html_url"],
        "submitted_at": meta["created_at"],
        "submitted_by": meta["user"],
        "title": meta["title"],
        "idea_summary": sections.get("灵感一句话", ""),
        "why_it_matters": sections.get("为什么值得记下来", ""),
        "bucket": sections.get("灵感归类", ""),
        "next_step": sections.get("你希望后面怎么处理", ""),
        "raw_sections": sections,
    }
    write_json(destination, payload)
    return destination


def article_extract(url: str) -> dict[str, Any]:
    result: dict[str, Any] = {"url": url, "kind": "article"}
    try:
        import trafilatura  # type: ignore
    except ImportError:
        trafilatura = None

    if trafilatura is not None:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            result["source_html_available"] = True
            result["title"] = trafilatura.extract(downloaded, output_format="json")
            try:
                parsed = json.loads(result["title"]) if result["title"] else {}
                if isinstance(parsed, dict):
                    result["title"] = parsed.get("title") or ""
                    text = parsed.get("text") or ""
                    result["text_excerpt"] = text[:8000]
                    result["author"] = parsed.get("author") or ""
                    result["date"] = parsed.get("date") or ""
                    return result
            except json.JSONDecodeError:
                pass

    html, final_url = fetch_text_response(url)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else url
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, re.I | re.S)
    text = " ".join(re.sub(r"<[^>]+>", " ", para) for para in paragraphs)
    text = re.sub(r"\s+", " ", text).strip()
    result["title"] = title
    result["text_excerpt"] = text[:8000]
    result["domain"] = urlparse(final_url).netloc
    return result


def html_video_extract(url: str) -> dict[str, Any]:
    html, final_url = fetch_text_response(url)
    title = extract_meta_value(html, ("og:title", "twitter:title", "title"))
    if not title:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = collapse_whitespace(title_match.group(1)) if title_match else url
    description = extract_meta_value(html, ("og:description", "description", "twitter:description"))
    parsed = urlparse(final_url)
    return {
        "url": url,
        "resolved_url": final_url,
        "kind": "video",
        "title": title or url,
        "description": description[:8000],
        "domain": parsed.netloc,
        "extraction_note": "Used HTML page metadata fallback because yt-dlp was unavailable or unsupported.",
    }


def direct_video_extract(url: str) -> dict[str, Any]:
    headers, final_url = fetch_headers(url)
    parsed = urlparse(final_url)
    return {
        "url": url,
        "resolved_url": final_url,
        "kind": "video",
        "title": Path(parsed.path).name or final_url,
        "content_type": headers.get("Content-Type", ""),
        "content_length": headers.get("Content-Length", ""),
        "domain": parsed.netloc,
        "extraction_note": "Used direct URL metadata fallback because yt-dlp was unavailable or unsupported.",
    }


def video_extract(url: str) -> dict[str, Any]:
    yt_dlp_path = shutil.which("yt-dlp")
    if yt_dlp_path:
        command = [
            yt_dlp_path,
            "--skip-download",
            "--dump-single-json",
            url,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            metadata = json.loads(result.stdout)
            return {
                "url": url,
                "kind": "video",
                "title": metadata.get("title") or "",
                "description": (metadata.get("description") or "")[:8000],
                "uploader": metadata.get("uploader") or "",
                "duration": metadata.get("duration"),
                "webpage_url": metadata.get("webpage_url") or url,
                "tags": metadata.get("tags") or [],
                "categories": metadata.get("categories") or [],
                "thumbnail": metadata.get("thumbnail") or "",
            }
        if infer_source_type(url) == "video":
            try:
                return html_video_extract(url)
            except Exception:
                return direct_video_extract(url)
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "yt-dlp metadata extraction failed")

    if infer_source_type(url) == "video":
        try:
            return html_video_extract(url)
        except Exception:
            return direct_video_extract(url)
    raise RuntimeError("yt-dlp is unavailable and the source URL does not look like a direct video link.")


def summarize_with_openai(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, "missing_api_key"

    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        return None, str(exc)

    client = OpenAI(api_key=api_key)
    model = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    prompt = f"""
你是一个内容学习助手。请把下面的输入整理成严格 JSON。

目标：
1. 提炼内容核心信息
2. 抽出可复用的方法、结构、钩子、节奏或选题模式
3. 给出适合“小红书/猫meme/内容运营”场景的本地化启发

输出 JSON 字段：
- source_summary: string
- reusable_patterns: array of strings
- hook_observations: array of strings
- local_adaptation_ideas: array of strings
- tags: array of strings
- memory_summary: string
- reuse_hint: string

输入：
{json.dumps(payload, ensure_ascii=False)}
""".strip()
    try:
        response = client.responses.create(
            model=model,
            input=prompt,
            reasoning={"effort": "minimal"},
        )
        text = clean_json_text(response.output_text.strip())
        return json.loads(text), None
    except Exception as exc:
        return None, str(exc)


def heuristic_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    extraction = payload.get("extraction") or {}
    source_type = payload.get("source_type", "")
    raw_title = extraction.get("title") or payload.get("source_title") or ""
    title = raw_title if raw_title and not looks_like_url(raw_title) else ""
    title = title or payload.get("title") or payload.get("source_url") or ""
    description = extraction.get("description") or extraction.get("text_excerpt") or ""
    why_good = collapse_whitespace(payload.get("why_good", ""))
    wanted_outputs = split_hint_items(payload.get("wanted_outputs", ""))
    summary_seed = description or why_good or title
    source_summary = truncate_text(summary_seed or title or payload.get("source_url", ""), limit=180)

    reusable_patterns: list[str] = []
    hook_observations: list[str] = []
    local_adaptation_ideas: list[str] = []
    tags: list[str] = [source_type or "learning"]

    if title:
        reusable_patterns.append(f"先用“{truncate_text(title, 36)}”这类明确主题或情绪入口定调，再展开内容。")
        hook_observations.append(f"标题或封面要先传达“{truncate_text(title, 24)}”的核心情绪。")
    if why_good:
        reusable_patterns.append(f"优先复用这条内容最打人的感受层：{truncate_text(why_good, 60)}。")
        hook_observations.append(f"前 1 到 3 秒先让观众感到：{truncate_text(why_good, 48)}。")

    if source_type == "video":
        reusable_patterns.append("先找情绪钩子和画面转折点，再安排字幕、反应镜头和特效节奏。")
        local_adaptation_ideas.append("做猫 meme 时，把最强情绪点拆成“主反应猫 + 补刀猫 + 字幕翻转”三拍。")
        local_adaptation_ideas.append("特效只放在情绪翻转或反应放大的瞬间，不要全程铺满。")
        tags.append("video")
    else:
        reusable_patterns.append("先把核心观点压成一句短句，再拆成可单独成段的表达。")
        local_adaptation_ideas.append("做猫 meme 时，先把文章观点改成一句冲突字幕，再配对应反应猫。")
        tags.append("article")

    for item in wanted_outputs[:3]:
        reusable_patterns.append(f"这次学习重点是：{item}。输出时围绕这个目标回看结构。")
        tags.append(item)
        if "钩子" in item:
            hook_observations.append("开头不要直接讲结论，先抛出冲突或情绪失衡感，再让角色反应接住。")
            local_adaptation_ideas.append("猫 meme 开场先放一句冲突字幕，再让惊讶猫或质问猫在第 2 拍接上。")
        if "特效" in item:
            reusable_patterns.append("特效服务情绪升级，不单独抢戏；先定节奏点，再决定闪白、定格或放大。")
            local_adaptation_ideas.append("猫 meme 里优先用定格、轻微放大、闪白和节奏字幕，不要上复杂转场。")
        if "节奏" in item:
            reusable_patterns.append("节奏先轻后重，最后一拍留给反转或情绪落点。")

    reusable_patterns = list(dict.fromkeys(item for item in reusable_patterns if item))
    hook_observations = list(dict.fromkeys(item for item in hook_observations if item))
    local_adaptation_ideas = list(dict.fromkeys(item for item in local_adaptation_ideas if item))
    tags = list(dict.fromkeys(item for item in tags if item))

    return {
        "source_summary": source_summary or title,
        "reusable_patterns": reusable_patterns,
        "hook_observations": hook_observations,
        "local_adaptation_ideas": local_adaptation_ideas,
        "tags": tags,
        "memory_summary": truncate_text(
            f"{title} 这条内容值得记住的不是素材本身，而是它先用情绪抓人，再用结构和节奏把感受放大。",
            limit=140,
        ),
        "reuse_hint": "下次做猫 meme 时，先把这条学习拆成“开场钩子 / 反应节奏 / 特效落点”三列，再回头挑猫素材。",
    }


def build_learning_payload(meta: dict[str, Any], sections: dict[str, str]) -> dict[str, Any]:
    source_type = sections.get("来源类型", "").strip().lower()
    source_url = sections.get("来源链接", "").strip() or extract_first_url(meta.get("body", ""))
    if not source_url:
        raise ValueError("Source URL is required.")
    if source_type not in {"article", "video"}:
        source_type = infer_source_type(source_url)

    payload = {
        "kind": "learning",
        "issue_number": meta["number"],
        "issue_url": meta["html_url"],
        "submitted_at": meta["created_at"],
        "submitted_by": meta["user"],
        "title": meta["title"],
        "source_type": source_type,
        "source_url": source_url,
        "source_title": sections.get("来源标题（可选）", "").strip(),
        "why_good": sections.get("你觉得它哪里好", ""),
        "wanted_outputs": sections.get("你希望我重点提炼什么", ""),
        "extra_context": sections.get("补充说明（可选）", ""),
        "raw_sections": sections,
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
    fallback_summary = heuristic_analysis(payload) if payload["extraction_status"] == "completed" else None
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


def save_learning_payload(repo_root: Path, payload: dict[str, Any]) -> Path:
    created_at = datetime.fromisoformat(payload["submitted_at"].replace("Z", "+00:00"))
    filename = f"{created_at.strftime('%Y-%m-%d')}-issue-{payload['issue_number']}-{slugify(payload['title'])}.json"
    destination = repo_root / "cloud" / "processed" / filename
    write_json(destination, payload)
    return destination


def main() -> None:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    event_payload = read_json(Path(args.event_path))
    meta = issue_metadata(event_payload)
    kind = choose_issue_kind(meta)
    if kind is None:
        raise SystemExit("Issue does not match a supported cloud hub label.")

    sections = parse_issue_sections(meta["body"])
    if kind == "idea":
        path = save_idea_payload(repo_root, meta, sections)
        print(json.dumps({"kind": "idea", "path": str(path)}, ensure_ascii=False))
        return

    learning_payload = build_learning_payload(meta, sections)
    path = save_learning_payload(repo_root, learning_payload)
    print(
        json.dumps(
            {
                "kind": "learning",
                "path": str(path),
                "analysis_status": learning_payload.get("analysis_status"),
                "extraction_status": learning_payload.get("extraction_status"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
