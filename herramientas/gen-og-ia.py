#!/usr/bin/env python3
"""OG images zonaalcaravaneras: fondo IA (pollinations) + texto PIL.

Plantilla: Poster Layout System (awesome-gpt-image-2).
Fondo: escena editorial de la categoría, composición con zona oscura a la izquierda.
Texto: PIL garantiza ortografía perfecta (la IA no renderiza texto).
Salida: /tmp/og-nuevo/<categoria>.png (1200x630)
"""
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

OUT = Path("/tmp/og-nuevo")
OUT.mkdir(exist_ok=True)

GUIA = "Zona Alcaravaneras"
SUB = "Guía del barrio"

# Paleta de marca
OCEANO = (7, 59, 79)
SOL = (226, 104, 63)
ARENA = (250, 246, 238)

W, H = 1200, 630
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# slug -> (título, prompt de escena en inglés, seed)
CATS = {
    "restaurantes": ("Restaurantes", "premium editorial food photography, rustic wooden table with canarian food plates and tapas, warm soft light, shallow depth of field, dark moody left side", 42),
    "alimentacion": ("Alimentación", "premium editorial photography, fresh grocery market scene, colorful fruit crates and bread on wooden counter, warm natural light, dark moody left side", 43),
    "bares-y-cafes": ("Bares y Cafés", "premium editorial photography, cozy cafe scene, espresso cup with latte art on marble counter, warm morning light, dark moody left side", 44),
    "bazares": ("Bazares", "premium editorial photography, colorful bazaar shop interior with assorted goods on shelves, warm light, dark moody left side", 45),
    "belleza": ("Belleza", "premium editorial photography, elegant beauty salon interior, cosmetics on marble surface, soft warm glow, dark moody left side", 46),
    "deporte-y-ocio": ("Deporte y Ocio", "premium editorial photography, sports equipment and gear arranged on gym floor, dramatic light, dark moody left side", 47),
    "electronica": ("Electrónica", "premium editorial photography, modern electronics store display, gadgets and devices with soft blue light, dark moody left side", 48),
    "hogar-y-decoracion": ("Hogar y Decoración", "premium editorial photography, elegant home decor store, furniture and decorative objects, warm interior light, dark moody left side", 49),
    "hogar-y-reformas": ("Hogar y Reformas", "premium editorial photography, hardware store tools and renovation materials neatly arranged, warm workshop light, dark moody left side", 50),
    "mascotas": ("Mascotas", "premium editorial photography, pet shop interior with pet supplies and accessories, warm friendly light, dark moody left side", 51),
    "moda": ("Moda", "premium editorial photography, elegant fashion boutique, clothing rack with curated garments, soft spotlight, dark moody left side", 52),
    "motor": ("Motor", "premium editorial photography, auto workshop interior with car parts and tools, dramatic industrial light, dark moody left side", 53),
    "salud": ("Salud", "premium editorial photography, modern pharmacy interior with clean white shelves, soft clinical warm light, dark moody left side", 54),
    "servicios": ("Servicios", "premium editorial photography, modern professional office interior, desk with documents and laptop, warm light, dark moody left side", 55),
    "generico": ("Comercios del barrio", "premium editorial photography, charming canarian old town street with small shop facades, golden hour warm light, dark moody left side", 56),
}

BASE = "https://image.pollinations.ai/prompt/"


def fetch(slug: str, prompt: str, seed: int) -> Path:
    full = prompt + ", no people, no text, no watermark, no logo, photorealistic"
    url = BASE + urllib.parse.quote(full) + f"?width=1280&height=720&nologo=true&seed={seed}"
    dst = OUT / f"{slug}.bg.jpg"
    if dst.exists() and dst.stat().st_size > 10000:
        return dst
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=150) as r:
                data = r.read()
            if len(data) > 10000:
                dst.write_bytes(data)
                return dst
        except Exception as e:
            print(f"  {slug} intento {attempt+1} fallo: {e}")
            time.sleep(8)
    raise RuntimeError(f"no se pudo descargar fondo para {slug}")


def render(slug: str, titulo: str, bg_path: Path) -> Path:
    img = Image.open(bg_path).convert("RGB")
    # crop central a 1200x630
    img = img.resize((max(W, int(img.width * H / img.height)), max(H, int(img.height * W / img.width))), Image.LANCZOS)
    l = (img.width - W) // 2
    t = (img.height - H) // 2
    img = img.crop((l, t, l + W, t + H))

    # gradiente oscuro izquierda -> transparente derecha (zona de texto)
    grad = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(grad)
    for x in range(W):
        if x < 620:
            gd.line([(x, 0), (x, H)], fill=235)
        elif x < 820:
            gd.line([(x, 0), (x, H)], fill=int(235 * (820 - x) / 200))
    dark = Image.new("RGB", (W, H), OCEANO)
    img = Image.composite(dark, img, grad)

    d = ImageDraw.Draw(img)
    f_titulo = ImageFont.truetype(FONT_BOLD, 76)
    f_sub = ImageFont.truetype(FONT_REG, 30)
    f_guia = ImageFont.truetype(FONT_BOLD, 26)

    x0, y0 = 70, 200
    # franja sol
    d.rectangle([x0, y0, x0 + 90, y0 + 8], fill=SOL)
    # título
    d.text((x0, y0 + 34), titulo, font=f_titulo, fill=ARENA)
    # subtítulo
    ty = y0 + 34 + 92
    d.text((x0, ty), SUB, font=f_sub, fill=(250, 246, 238, 200))
    # guía abajo
    d.text((x0, H - 90), GUIA.upper(), font=f_guia, fill=SOL)

    out = OUT / f"{slug}.png"
    img.save(out, "PNG", optimize=True)
    return out


def main():
    ok, fail = [], []
    for slug, (titulo, prompt, seed) in CATS.items():
        print(f"[{slug}] descargando fondo...", flush=True)
        try:
            bg = fetch(slug, prompt, seed)
            out = render(slug, titulo, bg)
            print(f"[{slug}] OK -> {out}")
            ok.append(slug)
        except Exception as e:
            print(f"[{slug}] FALLO: {e}")
            fail.append(slug)
        time.sleep(4)  # rate limit pollinations
    print(f"\nTotal: {len(ok)} OK, {len(fail)} fallos {fail}")


if __name__ == "__main__":
    main()
