from __future__ import annotations

import math
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "jaspervoice_promo_10s.avi"

W, H = 1280, 720
FPS = 24
DURATION = 10
FRAMES = FPS * DURATION

BG = (15, 15, 15)
PANEL = (25, 25, 25)
PANEL_2 = (35, 33, 33)
TEXT = (232, 230, 230)
MUTED = (158, 154, 154)
ACCENT = (217, 119, 87)
ACCENT_2 = (255, 169, 123)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/seguisb.ttf") if bold else Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf") if bold else Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


FONT_HERO = font(74, True)
FONT_TITLE = font(48, True)
FONT_BODY = font(32)
FONT_SMALL = font(24)
FONT_MONO = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", size=28) if Path("C:/Windows/Fonts/consola.ttf").exists() else font(28)


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def draw_center(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fnt: ImageFont.ImageFont, fill=TEXT) -> None:
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text((xy[0] - (box[2] - box[0]) / 2, xy[1] - (box[3] - box[1]) / 2), text, font=fnt, fill=fill)


def rounded_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int = 34, fill=PANEL) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=(47, 45, 45), width=2)


def draw_logo(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, pulse: float) -> None:
    r = size // 2
    draw.rounded_rectangle((cx - r, cy - r, cx + r, cy + r), radius=size // 5, fill=BG, outline=(42, 42, 42), width=2)
    wave = int(8 * pulse)
    for side in (-1, 1):
        x = cx + side * int(size * 0.32)
        start = 120 if side < 0 else -60
        end = 240 if side < 0 else 60
        draw.arc((x - 34 - wave, cy - 45 - wave, x + 34 + wave, cy + 45 + wave), start, end, fill=ACCENT, width=5)
        draw.arc((x - 18, cy - 28, x + 18, cy + 28), start, end, fill=MUTED, width=4)
    draw.rounded_rectangle((cx - 22, cy - 62, cx + 22, cy + 20), radius=22, fill=ACCENT)
    draw.ellipse((cx - 8, cy - 47, cx + 8, cy - 31), fill=(150, 73, 58))
    draw.arc((cx - 40, cy - 18, cx + 40, cy + 58), 0, 180, fill=TEXT, width=7)
    draw.line((cx, cy + 60, cx, cy + 91), fill=TEXT, width=7)
    draw.line((cx - 27, cy + 91, cx + 27, cy + 91), fill=TEXT, width=7)


def draw_waveform(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, t: float) -> None:
    mid = y + h // 2
    points = []
    for i in range(w):
        amp = math.sin((i / 28) + t * 10) * math.sin((i / 83) + t * 3)
        envelope = math.sin(math.pi * i / max(1, w))
        yy = mid + int(amp * envelope * h * 0.42)
        points.append((x + i, yy))
    draw.line(points, fill=ACCENT_2, width=5, joint="curve")
    draw.line((x, mid, x + w, mid), fill=(65, 54, 50), width=2)


def draw_cursor_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, pct: float) -> None:
    rounded_panel(draw, box, 26, (245, 244, 241))
    x, y, _, _ = box
    draw.text((x + 28, y + 26), "Notas.txt", font=FONT_SMALL, fill=(80, 80, 80))
    visible = text[: int(len(text) * ease(pct))]
    draw.text((x + 28, y + 86), visible, font=FONT_MONO, fill=(23, 23, 23))
    cursor_x = x + 28 + int(draw.textlength(visible, font=FONT_MONO)) + 3
    if int(pct * 12) % 2 == 0:
        draw.line((cursor_x, y + 87, cursor_x, y + 120), fill=ACCENT, width=3)


def frame_at(n: int) -> Image.Image:
    t = n / FPS
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    for i in range(34):
        alpha = i / 33
        color = tuple(int(lerp(BG[c], (28, 20, 18)[c], alpha)) for c in range(3))
        draw.rectangle((0, int(H * i / 34), W, int(H * (i + 1) / 34) + 1), fill=color)

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((860 + int(math.sin(t) * 40), -160, 1440, 430), fill=(217, 119, 87, 42))
    gd.ellipse((-260, 360, 320, 940), fill=(217, 119, 87, 25))
    img = Image.alpha_composite(img.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(54))).convert("RGB")
    draw = ImageDraw.Draw(img)

    draw_logo(draw, 118, 98, 112, (math.sin(t * 4) + 1) / 2)
    draw.text((196, 58), "JasperVoice", font=FONT_TITLE, fill=TEXT)
    draw.text((200, 114), "ditado local para Windows", font=FONT_SMALL, fill=MUTED)

    if t < 2:
        p = ease(t / 2)
        draw.text((95, 260 - int((1 - p) * 24)), "Fale. Solte. O texto aparece.", font=FONT_HERO, fill=TEXT)
        draw.text((100, 360), "Push-to-talk com Whisper rodando na sua máquina.", font=FONT_BODY, fill=MUTED)
        rounded_panel(draw, (870, 250, 1135, 410), 34, PANEL_2)
        draw_center(draw, (1002, 306), "Ctrl + Shift", FONT_BODY, TEXT)
        draw_center(draw, (1002, 362), "Space", FONT_TITLE, ACCENT_2)
    elif t < 4:
        local = t - 2
        draw.text((95, 246), "Segure o atalho", font=FONT_HERO, fill=TEXT)
        draw.text((100, 344), "Grave só enquanto pressiona. Sem janelas no caminho.", font=FONT_BODY, fill=MUTED)
        rounded_panel(draw, (735, 232, 1165, 468), 36, PANEL_2)
        draw_center(draw, (950, 286), "REC", FONT_TITLE, ACCENT_2)
        draw_waveform(draw, 795, 350, 310, 82, local)
    elif t < 6:
        local = t - 4
        draw.text((95, 246), "Transcrição offline", font=FONT_HERO, fill=TEXT)
        draw.text((100, 344), "Whisper local. Áudio privado. Sem cloud obrigatória.", font=FONT_BODY, fill=MUTED)
        rounded_panel(draw, (735, 218, 1165, 485), 36, PANEL_2)
        draw_center(draw, (950, 292), "Whisper", FONT_TITLE, TEXT)
        draw_center(draw, (950, 360), "local", FONT_HERO, ACCENT_2)
        for i in range(4):
            x = 820 + i * 88
            y = 432 + int(math.sin(local * 5 + i) * 8)
            draw.rounded_rectangle((x, y, x + 52, y + 12), radius=6, fill=ACCENT)
    elif t < 8:
        local = t - 6
        draw.text((95, 246), "Funciona em qualquer app", font=FONT_HERO, fill=TEXT)
        draw.text((100, 344), "O resultado entra onde o cursor já está.", font=FONT_BODY, fill=MUTED)
        draw_cursor_text(draw, (705, 210, 1170, 478), "Preciso revisar esse PR hoje.", local / 2)
    else:
        p = ease((t - 8) / 2)
        draw.text((95, 222), "Sem assinatura. Sem telemetria.", font=FONT_HERO, fill=TEXT)
        draw.text((100, 320), "Ditado rápido, local e discreto para o seu fluxo diário.", font=FONT_BODY, fill=MUTED)
        draw_logo(draw, 980, 345, int(170 + p * 22), p)
        draw.rounded_rectangle((95, 435, 505, 505), radius=24, fill=ACCENT)
        draw_center(draw, (300, 468), "JasperVoice", FONT_BODY, (15, 15, 15))

    draw.text((96, 650), "Ctrl+Shift+Space", font=FONT_SMALL, fill=ACCENT_2)
    draw.text((300, 650), "|", font=FONT_SMALL, fill=(75, 69, 67))
    draw.text((326, 650), "privado por padrão", font=FONT_SMALL, fill=MUTED)
    return img


def chunk(name: bytes, payload: bytes) -> bytes:
    pad = b"\0" if len(payload) % 2 else b""
    return name + struct.pack("<I", len(payload)) + payload + pad


def list_chunk(name: bytes, payload: bytes) -> bytes:
    return b"LIST" + struct.pack("<I", len(payload) + 4) + name + payload + (b"\0" if len(payload) % 2 else b"")


def jpeg_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


def write_avi(path: Path, frames: list[bytes]) -> None:
    max_frame = max(len(f) for f in frames)
    movi_payload = b"".join(chunk(b"00dc", f) for f in frames)
    movi = list_chunk(b"movi", movi_payload)

    avih = struct.pack(
        "<IIIIIIIIII4I",
        int(1_000_000 / FPS),
        max_frame * FPS,
        0,
        0x10,
        len(frames),
        0,
        1,
        max_frame,
        W,
        H,
        0,
        0,
        0,
        0,
    )
    strh = struct.pack(
        "<4s4sIHHIIIIIIIIhhhh",
        b"vids",
        b"MJPG",
        0,
        0,
        0,
        0,
        1,
        FPS,
        0,
        len(frames),
        max_frame,
        0xFFFFFFFF,
        0,
        0,
        0,
        W,
        H,
    )
    strf = struct.pack("<IiiHH4sIiiII", 40, W, H, 1, 24, b"MJPG", W * H * 3, 0, 0, 0, 0)
    strl = list_chunk(b"strl", chunk(b"strh", strh) + chunk(b"strf", strf))
    hdrl = list_chunk(b"hdrl", chunk(b"avih", avih) + strl)

    index = []
    current = 4
    for f in frames:
        index.append(struct.pack("<4sIII", b"00dc", 0x10, current, len(f)))
        current += 8 + len(f) + (len(f) % 2)
    idx1 = chunk(b"idx1", b"".join(index))

    body = hdrl + movi + idx1
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(b"RIFF" + struct.pack("<I", len(body) + 4) + b"AVI " + body)


def main() -> None:
    frames = [jpeg_bytes(frame_at(i)) for i in range(FRAMES)]
    write_avi(OUT, frames)
    print(OUT)


if __name__ == "__main__":
    main()
