#!/usr/bin/env python3
"""Genera og-images por categoría para las guías de barrio.

Salida: public/og/<categoria>.png (1200x630) + public/og/generico.png
Fondo: gradiente oceánico de la paleta de cada guía, texto con nombre de
categoría y de la guía. Sin imágenes externas, sin personas, sin rastreo.
"""
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GUIAS = {
    "zonaalcaravaneras": ("Zona Alcaravaneras", "Las Alcaravaneras"),
    "zonaguanarteme": ("Zona Guanarteme", "Guanarteme"),
    "zonasantacatalina": ("Zona Santa Catalina", "Santa Catalina"),
    "zonalaisleta": ("Zona La Isleta", "La Isleta"),
}

# Paleta común (misma identidad en las 4 guías)
OCEANO = (7, 59, 79)
OCEANO_HONDO = (4, 34, 46)
SOL = (226, 104, 63)
ARENA = (250, 246, 238)
AGUA = (27, 127, 158)

W, H = 1200, 630
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def slug_cat(nombre: str) -> str:
    # sin tildes, guiones en vez de espacios (misma regla que TarjetaComercio)
    import unicodedata
    s = unicodedata.normalize("NFD", nombre.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "generico"


def gradiente() -> Image.Image:
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        r = int(OCEANO[0] + (OCEANO_HONDO[0] - OCEANO[0]) * t)
        g = int(OCEANO[1] + (OCEANO_HONDO[1] - OCEANO[1]) * t)
        b = int(OCEANO[2] + (OCEANO_HONDO[2] - OCEANO[2]) * t)
        for x in range(W):
            px[x, y] = (r, g, b)
    return img


def render(guia_titulo: str, barrio: str, categoria: str | None, out: Path) -> None:
    img = gradiente()
    d = ImageDraw.Draw(img)

    # franja sol (acento)
    d.rectangle([0, H - 14, W, H], fill=SOL)

    f_guia = ImageFont.truetype(FONT_REG, 34)
    f_sub = ImageFont.truetype(FONT_REG, 30)

    # nombre de la guía arriba
    d.text((72, 64), guia_titulo, font=f_guia, fill=ARENA)
    d.line([(72, 120), (200, 120)], fill=SOL, width=6)

    # categoría (o texto genérico) centrada
    texto = categoria or "Comercios del barrio"
    # ajuste de tamaño si es larga
    size = 88
    font = ImageFont.truetype(FONT_BOLD, size)
    while d.textlength(texto, font=font) > W - 144 and size > 44:
        size -= 4
        font = ImageFont.truetype(FONT_BOLD, size)
    d.text((72, 210), texto, font=font, fill=(255, 255, 255))

    # subtítulo
    sub = f"Guía gratuita de comercios de {barrio} · Las Palmas de Gran Canaria"
    d.text((72, 420), sub, font=f_sub, fill=(220, 240, 246))

    img.save(out, "PNG", optimize=True)


def main() -> None:
    base = Path.home() / "Proyectos"
    for repo, (titulo, barrio) in GUIAS.items():
        data = json.loads((base / repo / "src/data/comercios.json").read_text())
        cats = sorted({c.get("categoria", "") for c in data if c.get("categoria")})
        outdir = base / repo / "public/og"
        outdir.mkdir(exist_ok=True)
        n = 0
        for cat in cats:
            render(titulo, barrio, cat, outdir / f"{slug_cat(cat)}.png")
            n += 1
        render(titulo, barrio, None, outdir / "generico.png")
        print(f"{repo}: {n} categorías + generico -> {outdir}")


if __name__ == "__main__":
    sys.exit(main())
