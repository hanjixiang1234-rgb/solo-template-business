from pathlib import Path
import argparse
import math
import re

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1080
HEIGHT = 1440
PANEL = (58, 62, WIDTH - 58, HEIGHT - 58)
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"


PALETTES = {
    "minimal": {
        "bg_top": "#FFF7F4",
        "bg_bottom": "#F9E9EC",
        "paper": "#FFFDFC",
        "text": "#221A18",
        "muted": "#80655E",
        "accent": "#FF7A70",
        "accent_soft": "#FFD7D2",
        "accent_alt": "#FFEFE7",
        "outline": "#F1D3CC",
        "shadow": "#F2D7D2",
    },
    "checklist": {
        "bg_top": "#FFF8EA",
        "bg_bottom": "#F6EAC2",
        "paper": "#FFFDF6",
        "text": "#28221B",
        "muted": "#786A54",
        "accent": "#F1C550",
        "accent_soft": "#FAE7A6",
        "accent_alt": "#FFF5D6",
        "outline": "#E6D7AD",
        "shadow": "#E9DAB2",
    },
    "persona": {
        "bg_top": "#FFF4E1",
        "bg_bottom": "#FFD7A6",
        "paper": "#FFF9F0",
        "text": "#251B13",
        "muted": "#7D5C46",
        "accent": "#FF8E43",
        "accent_soft": "#FFD8B7",
        "accent_alt": "#FFF0D8",
        "outline": "#F0C79A",
        "shadow": "#F1D1AB",
    },
}

LANE_META = {
    "minimal": {
        "chip": "轻养生笔记",
        "eyebrow": "一眼看懂",
        "cta": "先收藏，晚点照着做",
    },
    "checklist": {
        "chip": "先收藏",
        "eyebrow": "清单型封面",
        "cta": "信息一页看完，适合反复翻",
    },
    "persona": {
        "chip": "真的要试试",
        "eyebrow": "人格感封面",
        "cta": "有点态度，也更容易点开",
    },
}


def load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def read_post(post_path: Path) -> tuple[str, list[list[str]]]:
    text = post_path.read_text(encoding="utf-8")

    cover_match = re.search(r"Cover text:\n- (.+)", text)
    if not cover_match:
        raise ValueError("Could not find cover text")
    cover = cover_match.group(1).strip()

    slides_block = re.search(r"Slides:\n\n(.+?)\nCaption:", text, re.S)
    if not slides_block:
        raise ValueError("Could not find slides block")

    slides: list[list[str]] = []
    current: list[str] = []
    for raw_line in slides_block.group(1).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^\d+\.$", line):
            if current:
                slides.append(current)
                current = []
            continue
        if line.startswith("- "):
            current.append(line[2:].strip())
    if current:
        slides.append(current)

    return cover, slides


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def draw_vertical_gradient(image: Image.Image, top: str, bottom: str) -> None:
    draw = ImageDraw.Draw(image)
    top_rgb = tuple(int(top[i : i + 2], 16) for i in (1, 3, 5))
    bottom_rgb = tuple(int(bottom[i : i + 2], 16) for i in (1, 3, 5))
    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        color = tuple(
            int(top_rgb[idx] + (bottom_rgb[idx] - top_rgb[idx]) * ratio)
            for idx in range(3)
        )
        draw.line((0, y, WIDTH, y), fill=color)


def draw_dot_pattern(draw: ImageDraw.ImageDraw, palette: dict[str, str]) -> None:
    for row in range(6):
        for col in range(8):
            x = 104 + col * 98 + (row % 2) * 8
            y = 126 + row * 86
            draw.ellipse((x, y, x + 10, y + 10), fill=palette["accent_soft"])


def draw_background_blobs(draw: ImageDraw.ImageDraw, palette: dict[str, str]) -> None:
    draw.ellipse((760, 96, 1140, 436), fill=palette["accent_soft"])
    draw.ellipse((728, 204, 1048, 534), fill=palette["accent_alt"])
    draw.rounded_rectangle((116, 1050, 430, 1302), radius=72, fill=palette["accent_alt"])


def create_canvas(lane: str) -> tuple[Image.Image, ImageDraw.ImageDraw, dict[str, str]]:
    palette = PALETTES[lane]
    image = Image.new("RGB", (WIDTH, HEIGHT), palette["bg_top"])
    draw_vertical_gradient(image, palette["bg_top"], palette["bg_bottom"])
    draw = ImageDraw.Draw(image)

    draw_background_blobs(draw, palette)
    draw_dot_pattern(draw, palette)

    shadow_rect = (PANEL[0] + 12, PANEL[1] + 18, PANEL[2] + 12, PANEL[3] + 18)
    draw.rounded_rectangle(shadow_rect, radius=56, fill=palette["shadow"])
    draw.rounded_rectangle(PANEL, radius=56, fill=palette["paper"], outline=palette["outline"], width=4)

    return image, draw, palette


def choose_lane(text: str) -> str:
    if any(keyword in text for keyword in ["顺序", "方法", "公式", "清单", "怎么", "几点", "小方法"]):
        return "checklist"
    if any(keyword in text for keyword in ["别再", "真的要", "不必", "先别", "快醒醒", "邪修"]):
        return "persona"
    return "minimal"


def choose_icon(text: str) -> str:
    if any(keyword in text for keyword in ["脑", "清晰", "脑雾"]):
        return "brain"
    if any(keyword in text for keyword in ["眼", "眼浊"]):
        return "eye"
    if any(keyword in text for keyword in ["吹风机", "热", "寒", "暖"]):
        return "heat"
    if any(keyword in text for keyword in ["咖啡", "提神"]):
        return "cup"
    if any(keyword in text for keyword in ["起床", "睡", "熬夜", "晚上"]):
        return "bed"
    if any(keyword in text for keyword in ["吃", "饭", "胃"]):
        return "plate"
    if any(keyword in text for keyword in ["气", "情绪", "心"]):
        return "heart"
    return "spark"


def draw_chip(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, palette: dict[str, str]) -> None:
    font = load_font(28)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + 42
    height = bbox[3] - bbox[1] + 24
    draw.rounded_rectangle((x, y, x + width, y + height), radius=24, fill=palette["accent"])
    draw.text((x + 20, y + 11), text, font=font, fill="#FFFFFF")


def draw_caption_bar(draw: ImageDraw.ImageDraw, text: str, palette: dict[str, str]) -> None:
    font = load_font(26)
    x1, y1, x2, y2 = 112, 1238, 968, 1298
    draw.rounded_rectangle((x1, y1, x2, y2), radius=28, fill=palette["accent_alt"])
    draw.text((x1 + 28, y1 + 15), text, font=font, fill=palette["muted"])


def draw_emphasis_blocks(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_width: int,
    lane: str,
    palette: dict[str, str],
) -> int:
    font = load_font(68 if lane != "checklist" else 60)
    lines = wrap_text(draw, text, font, max_width)
    cur_y = y
    fills = {
        "minimal": [palette["paper"], palette["accent_soft"], palette["paper"]],
        "checklist": [palette["accent"], palette["paper"], palette["paper"]],
        "persona": [palette["accent"], "#FFFFFF", palette["accent_soft"]],
    }[lane]
    text_colors = {
        "minimal": [palette["text"], palette["text"], palette["text"]],
        "checklist": [palette["text"], palette["text"], palette["text"]],
        "persona": ["#FFFFFF", palette["text"], palette["text"]],
    }[lane]

    for index, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        width = bbox[2] - bbox[0] + 46
        height = bbox[3] - bbox[1] + 32
        tilt = -8 if lane == "persona" and index == 0 else 0
        line_image = Image.new("RGBA", (width + 24, height + 24), (0, 0, 0, 0))
        line_draw = ImageDraw.Draw(line_image)
        line_draw.rounded_rectangle((12, 12, width + 12, height + 12), radius=28, fill=fills[index % len(fills)])
        line_draw.text((34, 26), line, font=font, fill=text_colors[index % len(text_colors)])
        if tilt:
            line_image = line_image.rotate(tilt, expand=True, resample=Image.Resampling.BICUBIC)
        draw._image.paste(line_image, (x - 10, cur_y - 12), line_image)
        cur_y += line_image.size[1] - 6
    return cur_y


def draw_mini_checks(draw: ImageDraw.ImageDraw, palette: dict[str, str]) -> None:
    box_font = load_font(24)
    items = ["别急着刷信息", "先活动一下", "再开始看手机"]
    start_y = 864
    for index, item in enumerate(items):
        top = start_y + index * 72
        draw.rounded_rectangle((668, top, 932, top + 52), radius=20, fill="#FFFFFF", outline=palette["outline"], width=3)
        draw.rounded_rectangle((682, top + 12, 710, top + 40), radius=10, fill=palette["accent"])
        draw.text((722, top + 11), item, font=box_font, fill=palette["text"])


def draw_persona_stickers(draw: ImageDraw.ImageDraw, palette: dict[str, str]) -> None:
    font = load_font(24)
    stickers = [("先舒服一点", 680, 836), ("真的会点开", 760, 1110)]
    for text, x, y in stickers:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0] + 28
        h = bbox[3] - bbox[1] + 18
        draw.rounded_rectangle((x, y, x + w, y + h), radius=16, fill="#FFFFFF", outline=palette["accent"], width=3)
        draw.text((x + 14, y + 8), text, font=font, fill=palette["accent"])


def draw_minimal_wave(draw: ImageDraw.ImageDraw, palette: dict[str, str]) -> None:
    points = []
    for step in range(12):
        x = 660 + step * 26
        y = 830 + math.sin(step / 1.5) * 18
        points.append((x, y))
    draw.line(points, fill=palette["accent"], width=8)


def draw_hero_icon(draw: ImageDraw.ImageDraw, icon: str, lane: str, palette: dict[str, str]) -> None:
    base_x = 786
    base_y = 608

    if icon == "brain":
        draw.ellipse((base_x - 120, base_y, base_x + 30, base_y + 126), fill=palette["accent_soft"], outline=palette["text"], width=6)
        draw.ellipse((base_x - 40, base_y - 18, base_x + 110, base_y + 118), fill=palette["accent_soft"], outline=palette["text"], width=6)
        draw.line((base_x - 12, base_y + 22, base_x - 12, base_y + 122), fill=palette["text"], width=6)
        draw.arc((base_x - 78, base_y + 34, base_x + 46, base_y + 110), start=200, end=340, fill=palette["text"], width=6)
        draw.arc((base_x - 10, base_y + 24, base_x + 96, base_y + 110), start=200, end=340, fill=palette["text"], width=6)
    elif icon == "eye":
        draw.ellipse((base_x - 128, base_y + 12, base_x + 120, base_y + 148), outline=palette["text"], width=8, fill=palette["accent_soft"])
        draw.ellipse((base_x - 34, base_y + 38, base_x + 26, base_y + 98), fill=palette["text"])
        draw.ellipse((base_x + 6, base_y + 50, base_x + 68, base_y + 112), fill="#FFFFFF")
        draw.ellipse((base_x + 24, base_y + 68, base_x + 46, base_y + 90), fill=palette["text"])
    elif icon == "heat":
        draw.rounded_rectangle((base_x - 88, base_y + 54, base_x + 94, base_y + 176), radius=30, fill=palette["accent_soft"], outline=palette["text"], width=8)
        draw.arc((base_x + 64, base_y + 84, base_x + 142, base_y + 152), start=270, end=90, fill=palette["text"], width=8)
        for offset in (-44, 0, 44):
            draw.line((base_x + offset, base_y - 10, base_x + offset, base_y + 54), fill=palette["accent"], width=10)
            draw.arc((base_x + offset - 20, base_y - 28, base_x + offset + 20, base_y + 12), start=0, end=180, fill=palette["accent"], width=8)
    elif icon == "cup":
        draw.rounded_rectangle((base_x - 98, base_y + 72, base_x + 66, base_y + 176), radius=24, fill=palette["accent_soft"], outline=palette["text"], width=8)
        draw.arc((base_x + 42, base_y + 90, base_x + 126, base_y + 160), start=270, end=90, fill=palette["text"], width=8)
        draw.line((base_x - 76, base_y + 190, base_x + 108, base_y + 190), fill=palette["text"], width=10)
        for offset in (-40, 0, 38):
            draw.line((base_x + offset, base_y - 6, base_x + offset, base_y + 52), fill=palette["accent"], width=8)
    elif icon == "bed":
        draw.rounded_rectangle((base_x - 116, base_y + 86, base_x + 118, base_y + 166), radius=24, fill=palette["accent_soft"], outline=palette["text"], width=8)
        draw.rounded_rectangle((base_x - 90, base_y + 42, base_x - 18, base_y + 98), radius=18, fill="#FFFFFF", outline=palette["text"], width=6)
        draw.line((base_x - 116, base_y + 166, base_x - 116, base_y + 210), fill=palette["text"], width=10)
        draw.line((base_x + 118, base_y + 166, base_x + 118, base_y + 210), fill=palette["text"], width=10)
        draw.ellipse((base_x + 66, base_y - 16, base_x + 146, base_y + 64), fill=palette["accent"], outline=palette["text"], width=4)
    elif icon == "plate":
        draw.ellipse((base_x - 118, base_y + 28, base_x + 118, base_y + 232), fill=palette["accent_soft"], outline=palette["text"], width=8)
        draw.ellipse((base_x - 44, base_y + 96, base_x + 44, base_y + 164), fill="#FFFFFF", outline=palette["text"], width=6)
        draw.line((base_x - 154, base_y + 74, base_x - 154, base_y + 206), fill=palette["text"], width=8)
        draw.line((base_x + 154, base_y + 74, base_x + 154, base_y + 206), fill=palette["text"], width=8)
    elif icon == "heart":
        draw.ellipse((base_x - 110, base_y + 22, base_x - 8, base_y + 124), fill=palette["accent_soft"], outline=palette["text"], width=6)
        draw.ellipse((base_x - 4, base_y + 22, base_x + 98, base_y + 124), fill=palette["accent_soft"], outline=palette["text"], width=6)
        draw.polygon([(base_x - 128, base_y + 92), (base_x + 112, base_y + 92), (base_x - 8, base_y + 234)], fill=palette["accent_soft"], outline=palette["text"])
    else:
        for angle in range(0, 360, 45):
            x = base_x + math.cos(math.radians(angle)) * 84
            y = base_y + 118 + math.sin(math.radians(angle)) * 84
            draw.line((base_x, base_y + 118, x, y), fill=palette["accent"], width=8)
        draw.ellipse((base_x - 58, base_y + 60, base_x + 58, base_y + 176), fill=palette["accent_soft"], outline=palette["text"], width=8)

    if lane == "checklist":
        draw_mini_checks(draw, palette)
    elif lane == "persona":
        draw_persona_stickers(draw, palette)
    else:
        draw_minimal_wave(draw, palette)


def render_cover(title: str, lane: str, icon: str, out_path: Path) -> None:
    image, draw, palette = create_canvas(lane)
    meta = LANE_META[lane]

    draw_chip(draw, 108, 108, meta["chip"], palette)
    eyebrow_font = load_font(24)
    draw.text((814, 124), meta["eyebrow"], font=eyebrow_font, fill=palette["muted"])

    draw_emphasis_blocks(draw, title, 102, 246, 520, lane, palette)
    draw_hero_icon(draw, icon, lane, palette)
    draw_caption_bar(draw, meta["cta"], palette)

    footer_font = load_font(24)
    draw.text((110, 1328), "做给普通人看的轻养生图文", font=footer_font, fill=palette["muted"])
    draw.text((820, 1328), "3秒看懂", font=footer_font, fill=palette["accent"])

    image.save(out_path)


def draw_slide_panel(draw: ImageDraw.ImageDraw, palette: dict[str, str], lane: str) -> tuple[int, int]:
    left = 92
    top = 176
    right = WIDTH - 92
    bottom = HEIGHT - 180
    shadow = (left + 10, top + 14, right + 10, bottom + 14)
    draw.rounded_rectangle(shadow, radius=42, fill=palette["shadow"])
    draw.rounded_rectangle((left, top, right, bottom), radius=42, fill="#FFFFFF", outline=palette["outline"], width=4)
    if lane == "checklist":
        for offset in range(top + 74, bottom, 72):
            draw.line((left + 34, offset, right - 34, offset), fill=palette["accent_alt"], width=2)
    return left, top


def render_slide(
    lines: list[str],
    page_num: int,
    total_pages: int,
    lane: str,
    icon: str,
    out_path: Path,
) -> None:
    image, draw, palette = create_canvas(lane)
    left, top = draw_slide_panel(draw, palette, lane)

    badge_font = load_font(28)
    draw.rounded_rectangle((left + 26, top + 24, left + 128, top + 70), radius=22, fill=palette["accent"])
    draw.text((left + 48, top + 35), f"{page_num:02d}", font=badge_font, fill="#FFFFFF")

    headline_font = load_font(56)
    body_font = load_font(40)
    small_font = load_font(24)

    y = top + 120
    max_width = WIDTH - 2 * left - 90
    for index, line in enumerate(lines):
        font = headline_font if index == 0 else body_font
        color = palette["text"] if index < 2 else palette["muted"]
        wrapped = wrap_text(draw, line, font, max_width)
        for wrapped_line in wrapped:
            draw.text((left + 44, y), wrapped_line, font=font, fill=color)
            bbox = draw.textbbox((left + 44, y), wrapped_line, font=font)
            if index == 0:
                draw.rounded_rectangle((left + 32, y - 10, left + 32 + (bbox[2] - bbox[0]) + 28, y + (bbox[3] - bbox[1]) + 16), radius=18, outline=palette["accent"], width=3)
            y += (bbox[3] - bbox[1]) + (22 if index == 0 else 16)
        y += 18

    footer = f"{page_num}/{total_pages}"
    bbox = draw.textbbox((0, 0), footer, font=small_font)
    draw.text((WIDTH - 156 - (bbox[2] - bbox[0]), HEIGHT - 136), footer, font=small_font, fill=palette["muted"])

    # smaller icon in the lower-right corner makes the carousel feel more branded
    small_icon = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    icon_draw = ImageDraw.Draw(small_icon)
    draw_hero_icon(icon_draw, icon, lane, palette)
    small_icon = small_icon.resize((192, 192), Image.Resampling.LANCZOS)
    image.paste(small_icon, (814, 1040), small_icon)

    image.save(out_path)


def render_post(post_path: Path, output_dir: Path) -> list[Path]:
    cover, slides = read_post(post_path)
    lane = choose_lane(cover)
    icon = choose_icon(cover)
    post_name = post_path.stem.lower()
    post_output = output_dir / post_name
    post_output.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []
    cover_path = post_output / "00_cover.png"
    render_cover(cover, lane, icon, cover_path)
    outputs.append(cover_path)

    total = len(slides)
    for index, slide in enumerate(slides, start=1):
        slide_path = post_output / f"{index:02d}.png"
        render_slide(slide, index, total, lane, icon, slide_path)
        outputs.append(slide_path)

    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("post", help="Path to the markdown post file")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parents[1] / "assets" / "rendered"),
        help="Directory for rendered images",
    )
    args = parser.parse_args()

    outputs = render_post(Path(args.post), Path(args.output_dir))
    for path in outputs:
        print(path)


if __name__ == "__main__":
    main()
