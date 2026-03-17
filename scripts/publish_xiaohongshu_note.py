from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_DIR = PROJECT_ROOT / ".browser" / "xhs"
DEFAULT_DEBUG_PORT = 9222
HOME_URL = "https://creator.xiaohongshu.com/new/home"
PUBLISH_IMAGE_URL = "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=image"
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("post", help="Path to the markdown post file")
    parser.add_argument(
        "--images-dir",
        help="Directory with rendered images. Defaults to assets/rendered/<post_name>",
    )
    parser.add_argument(
        "--profile-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="Chrome user data dir with the logged-in Xiaohongshu session",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_DEBUG_PORT,
        help="Chrome remote debugging port",
    )
    parser.add_argument(
        "--schedule-at",
        help="Schedule time in YYYY-MM-DD HH:MM format. Omit to publish immediately.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fill the note but do not click the final publish button",
    )
    return parser.parse_args()


def parse_post(post_path: Path) -> tuple[str, str]:
    text = post_path.read_text(encoding="utf-8")

    title_match = re.search(r"Title options:\n- (.+)", text)
    caption_match = re.search(r"Caption:\n\n(.+?)\n\nCTA:", text, re.S)
    cta_match = re.search(r"CTA:\n- (.+)", text)

    if not title_match or not caption_match or not cta_match:
        raise ValueError(f"Could not parse post file: {post_path}")

    title = title_match.group(1).strip()
    caption = caption_match.group(1).strip()
    cta = cta_match.group(1).strip()
    tags = infer_tags("\n".join([title, caption, cta]))

    body_parts = [caption]
    if cta:
        body_parts.append(cta)
    if tags:
        body_parts.append(" ".join(tags))

    return title, "\n\n".join(body_parts).strip()


def infer_tags(text: str) -> list[str]:
    tags = ["#轻养生"]
    mapping = [
        ("起床", "#早晨习惯"),
        ("早上", "#早晨习惯"),
        ("早起", "#早晨习惯"),
        ("下午", "#下午状态"),
        ("久坐", "#久坐人群"),
        ("打工人", "#打工人状态"),
        ("熬夜", "#作息调整"),
        ("手脚冰", "#日常调理"),
        ("吃得太乱", "#饮食节奏"),
        ("咖啡", "#咖啡依赖"),
    ]
    for needle, tag in mapping:
        if needle in text and tag not in tags:
            tags.append(tag)
    return tags[:4]


def resolve_images_dir(post_path: Path, images_dir: str | None) -> Path:
    if images_dir:
        return Path(images_dir).expanduser().resolve()
    return PROJECT_ROOT / "assets" / "rendered" / post_path.stem.lower()


def list_images(images_dir: Path) -> list[Path]:
    files = sorted(
        path
        for path in images_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTS
    )
    if not files:
        raise FileNotFoundError(f"No rendered images found in {images_dir}")
    return files


def wait_for_debugger(port: int, timeout: int = 20) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("Browser"):
                return
        except Exception as exc:  # pragma: no cover - operational polling
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Chrome debugger on port {port} did not come up") from last_error


def ensure_browser(profile_dir: Path, port: int) -> None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2):
            return
    except URLError:
        pass

    subprocess.run(
        [
            "open",
            "-na",
            "Google Chrome",
            "--args",
            f"--user-data-dir={profile_dir}",
            f"--remote-debugging-port={port}",
            "--new-window",
            HOME_URL,
        ],
        check=True,
    )
    wait_for_debugger(port)


def attach_driver(port: int) -> WebDriver:
    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    return webdriver.Chrome(options=options)


def wait_for_text(driver: WebDriver, text: str, timeout: int = 20) -> None:
    WebDriverWait(driver, timeout).until(
        lambda drv: text in drv.execute_script("return document.body.innerText")
    )


def visible_click_by_text(driver: WebDriver, text: str) -> bool:
    script = """
    const text = arguments[0];
    const selectors = 'button,a,div,span';
    const nodes = Array.from(document.querySelectorAll(selectors));
    for (const node of nodes) {
      const value = (node.innerText || '').trim();
      if (value !== text) continue;
      const rect = node.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      node.click();
      return true;
    }
    return false;
    """
    return bool(driver.execute_script(script, text))


def open_new_tab(driver: WebDriver, url: str) -> None:
    driver.switch_to.new_window("tab")
    driver.get(url)
    wait_for_text(driver, "创作服务平台")


def open_image_note_editor(driver: WebDriver) -> None:
    if driver.find_elements(By.CSS_SELECTOR, "input[type='file'][accept*='.png']"):
        return

    if visible_click_by_text(driver, "发布图文笔记"):
        WebDriverWait(driver, 20).until(
            lambda drv: drv.find_elements(By.CSS_SELECTOR, "input[type='file'][accept*='.png']")
        )
        return

    if visible_click_by_text(driver, "发布笔记"):
        time.sleep(1)
    if visible_click_by_text(driver, "上传图文"):
        time.sleep(1)

    WebDriverWait(driver, 20).until(
        lambda drv: drv.find_elements(By.CSS_SELECTOR, "input[type='file'][accept*='.png']")
    )


def upload_images(driver: WebDriver, image_paths: list[Path]) -> None:
    file_input = WebDriverWait(driver, 20).until(
        lambda drv: drv.find_element(By.CSS_SELECTOR, "input[type='file'][accept*='.png']")
    )
    file_input.send_keys("\n".join(str(path) for path in image_paths))
    wait_for_text(driver, "图片编辑", timeout=60)
    WebDriverWait(driver, 60).until(
        lambda drv: drv.find_elements(By.CSS_SELECTOR, "input[placeholder*='填写标题']")
    )


def clear_and_type_title(driver: WebDriver, title: str) -> None:
    title_input = WebDriverWait(driver, 20).until(
        lambda drv: drv.find_element(By.CSS_SELECTOR, "input[placeholder*='填写标题']")
    )
    driver.execute_script("arguments[0].focus()", title_input)
    title_input.send_keys(Keys.COMMAND, "a")
    title_input.send_keys(Keys.BACKSPACE)
    title_input.send_keys(title)


def clear_and_type_body(driver: WebDriver, body: str) -> None:
    editor = WebDriverWait(driver, 20).until(
        lambda drv: drv.find_element(By.CSS_SELECTOR, "[contenteditable='true']")
    )
    driver.execute_script("arguments[0].focus()", editor)
    editor.send_keys(Keys.COMMAND, "a")
    editor.send_keys(Keys.BACKSPACE)
    paragraphs = body.split("\n")
    for index, paragraph in enumerate(paragraphs):
        if paragraph:
            editor.send_keys(paragraph)
        if index != len(paragraphs) - 1:
            editor.send_keys(Keys.SHIFT, Keys.ENTER)


def set_schedule(driver: WebDriver, schedule_at: str) -> None:
    checkbox = WebDriverWait(driver, 20).until(
        lambda drv: drv.find_element(By.CSS_SELECTOR, ".post-time-wrapper input[type='checkbox']")
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'})", checkbox)
    if not checkbox.is_selected():
        driver.execute_script("arguments[0].click()", checkbox)

    date_input = WebDriverWait(driver, 20).until(
        lambda drv: drv.find_element(By.CSS_SELECTOR, ".date-picker-container input.d-text")
    )
    driver.execute_script("arguments[0].focus()", date_input)
    date_input.send_keys(Keys.COMMAND, "a")
    date_input.send_keys(schedule_at)
    date_input.send_keys(Keys.TAB)

    WebDriverWait(driver, 10).until(
        lambda drv: drv.find_element(By.CSS_SELECTOR, ".date-picker-container input.d-text").get_attribute("value")
        == schedule_at
    )


def click_primary_button(driver: WebDriver, button_text: str) -> None:
    buttons = driver.find_elements(By.CSS_SELECTOR, "button")
    for button in buttons:
        if (button.text or "").strip() == button_text:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'})", button)
            driver.execute_script("arguments[0].click()", button)
            return
    raise RuntimeError(f"Could not find button: {button_text}")


def submit_note(driver: WebDriver, scheduled: bool) -> None:
    button_text = "定时发布" if scheduled else "发布"
    click_primary_button(driver, button_text)

    success_markers = [
        "定时发布成功",
        "发布成功",
        "审核中",
    ]
    WebDriverWait(driver, 30).until(
        lambda drv: "published=true" in drv.current_url
        or "/publish/success" in drv.current_url
        or any(marker in drv.execute_script("return document.body.innerText") for marker in success_markers)
        or not drv.find_elements(By.CSS_SELECTOR, "input[placeholder*='填写标题']")
    )


def main() -> None:
    args = parse_args()
    post_path = Path(args.post).expanduser().resolve()
    images_dir = resolve_images_dir(post_path, args.images_dir)
    image_paths = list_images(images_dir)
    title, body = parse_post(post_path)

    ensure_browser(Path(args.profile_dir).expanduser().resolve(), args.port)
    driver = attach_driver(args.port)
    try:
        open_new_tab(driver, PUBLISH_IMAGE_URL)
        open_image_note_editor(driver)
        upload_images(driver, image_paths)
        clear_and_type_title(driver, title)
        clear_and_type_body(driver, body)

        if args.schedule_at:
            set_schedule(driver, args.schedule_at)

        if args.dry_run:
            print("Dry run complete.")
            print(f"title={title}")
            print(f"images={len(image_paths)}")
            print(f"schedule_at={args.schedule_at or 'now'}")
            return

        submit_note(driver, scheduled=bool(args.schedule_at))
        print("Publish flow submitted.")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
