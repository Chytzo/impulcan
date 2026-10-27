#!/usr/bin/env python3
# Genera placeholders SVG estilo Apple (gradiente pastel + icono de línea
# fina) para las guías de barrio. Autoalojados, sin hotlinking.
# Iconos: Lucide (licencia MIT, paths embebidos). Fuente de los paths:
# https://github.com/lucide-icons/lucide (carpeta icons/, nombre <slug>.svg).
# Uso: python3 generar-placeholders.py <guia> [<guia> ...]
from pathlib import Path
import os, sys, html

# Paleta pastel por categoría (slug -> (color_superior, color_inferior))
PALETA = {
    "restaurantes":    ("#FF9A5A", "#FF7A6B"),
    "alimentacion":    ("#8FD6A8", "#4CC38A"),
    "bares-y-cafes":   ("#CBA87A", "#A9744F"),
    "bazares":         ("#F6A6C1", "#E96FA8"),
    "belleza":         ("#F5A8D0", "#E85D9E"),
    "deporte-y-ocio":  ("#8AB6F0", "#4F8DE8"),
    "electronica":     ("#9A9FF0", "#6366E8"),
    "hogar-y-reformas":("#F5C26B", "#E8A04F"),
    "mascotas":        ("#B89AF0", "#8B5FE8"),
    "moda":            ("#7FD6E8", "#3FB8D6"),
    "motor":           ("#A8B0C0", "#7A8498"),
    "salud":           ("#7FE0C0", "#3FC8A8"),
    "servicios":       ("#8AD8D0", "#4FB8B0"),
    "generico":        ("#B8C0D0", "#8A94A8"),
}

# Iconos Lucide 24x24 (MIT), children del SVG original.
ICONOS = {
    "restaurantes": '<path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/>',
    "alimentacion": '<path d="m15 11-1 9"/><path d="m19 11-4-7"/><path d="M2 11h20"/><path d="m3.5 11 1.6 7.4a2 2 0 0 0 2 1.6h9.8a2 2 0 0 0 2-1.6l1.7-7.4"/><path d="M4.5 15.5h15"/><path d="m5 11 4-7"/><path d="m9 11 1 9"/>',
    "bares-y-cafes": '<path d="M10 2v2"/><path d="M14 2v2"/><path d="M16 8a1 1 0 0 1 1 1v8a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1h14a4 4 0 1 1 0 8h-1"/><path d="M6 2v2"/>',
    "bazares": '<path d="M16 10a4 4 0 0 1-8 0"/><path d="M3.103 6.034h17.794"/><path d="M3.4 5.467a2 2 0 0 0-.4 1.2V20a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6.667a2 2 0 0 0-.4-1.2l-2-2.667A2 2 0 0 0 17 2H7a2 2 0 0 0-1.6.8z"/>',
    "belleza": '<circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12"/><path d="M20 4 8.12 15.88"/><circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/>',
    "deporte-y-ocio": '<path d="M17.596 12.768a2 2 0 1 0 2.829-2.829l-1.768-1.767a2 2 0 0 0 2.828-2.829l-2.828-2.828a2 2 0 0 0-2.829 2.828l-1.767-1.768a2 2 0 1 0-2.829 2.829z"/><path d="m2.5 21.5 1.4-1.4"/><path d="m20.1 3.9 1.4-1.4"/><path d="M5.343 21.485a2 2 0 1 0 2.829-2.828l1.767 1.768a2 2 0 1 0 2.829-2.829l-6.364-6.364a2 2 0 1 0-2.829 2.829l1.768 1.767a2 2 0 0 0-2.828 2.829z"/><path d="m9.6 14.4 4.8-4.8"/>',
    "electronica": '<rect width="14" height="20" x="5" y="2" rx="2" ry="2"/><path d="M12 18h.01"/>',
    "hogar-y-reformas": '<path d="m15 12-9.373 9.373a1 1 0 0 1-3.001-3L12 9"/><path d="m18 15 4-4"/><path d="m21.5 11.5-1.914-1.914A2 2 0 0 1 19 8.172v-.344a2 2 0 0 0-.586-1.414l-1.657-1.657A6 6 0 0 0 12.516 3H9l1.243 1.243A6 6 0 0 1 12 8.485V10l2 2h1.172a2 2 0 0 1 1.414.586L18.5 14.5"/>',
    "mascotas": '<circle cx="11" cy="4" r="2"/><circle cx="18" cy="8" r="2"/><circle cx="20" cy="16" r="2"/><path d="M9 10a5 5 0 0 1 5 5v3.5a3.5 3.5 0 0 1-6.84 1.045Q6.52 17.48 4.46 16.84A3.5 3.5 0 0 1 5.5 10Z"/>',
    "moda": '<path d="M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"/>',
    "motor": '<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>',
    "salud": '<path d="M2 9.5a5.5 5.5 0 0 1 9.591-3.676.56.56 0 0 0 .818 0A5.49 5.49 0 0 1 22 9.5c0 2.29-1.5 4-3 5.5l-5.492 5.313a2 2 0 0 1-3 .019L5 15c-1.5-1.5-3-3.2-3-5.5"/><path d="M3.22 13H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27"/>',
    "servicios": '<path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/>',
    "generico": '<path d="M15 21v-5a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v5"/><path d="M17.774 10.31a1.12 1.12 0 0 0-1.549 0 2.5 2.5 0 0 1-3.451 0 1.12 1.12 0 0 0-1.548 0 2.5 2.5 0 0 1-3.452 0 1.12 1.12 0 0 0-1.549 0 2.5 2.5 0 0 1-3.77-3.248l2.889-4.184A2 2 0 0 1 7 2h10a2 2 0 0 1 1.653.873l2.895 4.192a2.5 2.5 0 0 1-3.774 3.244"/><path d="M4 10.95V19a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8.05"/>',
}

def svg_placeholder(slug):
    c1, c2 = PALETA[slug]
    icon = ICONOS[slug]
    nombre = "Comercio del barrio" if slug == "generico" else "Comercio de " + slug.replace("-", " ").title()
    s = 6.4
    tx = (800 - 24 * s) / 2
    ty = (500 - 24 * s) / 2
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500" viewBox="0 0 800 500" role="img" aria-label="{html.escape(nombre)}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{c1}"/>
      <stop offset="1" stop-color="{c2}"/>
    </linearGradient>
    <radialGradient id="brillo" cx="0.5" cy="0.35" r="0.75">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.28"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="800" height="500" fill="url(#g)"/>
  <rect width="800" height="500" fill="url(#brillo)"/>
  <g transform="translate({tx:.1},{ty:.1}) scale({s})" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    {icon}
  </g>
</svg>
'''

def main():
    guias = sys.argv[1:] or ["zonaalcaravaneras"]
    for guia in guias:
        outdir = str(Path.home() / "Proyectos" / guia / "public" / "placeholders")
        os.makedirs(outdir, exist_ok=True)
        for slug in PALETA:
            with open(os.path.join(outdir, f"{slug}.svg"), "w") as f:
                f.write(svg_placeholder(slug))
        print(f"{guia}: {len(PALETA)} SVGs en {outdir}")

if __name__ == "__main__":
    main()
