#!/usr/bin/env python3
"""
Mejoras de accesibilidad y SEO en las guías de barrio, aplicadas de forma idempotente.

Qué hace, por repo:
  1. Deriva de su PROPIA paleta dos tokens nuevos con contraste suficiente:
       --sol-cta      (fondo de botón con texto blanco, >= 4.5:1)
       --agua-texto   (enlaces sobre arena y sobre sol-claro, >= 4.5:1)
     No copia valores de otra guía: cada zona tiene su paleta y se oscurece la suya.
  2. Ajusta contraste y tamaño: sello de estado, placeholder, crédito de foto,
     borde visible del buscador, velo superior de la cabecera.
  3. Objetivos táctiles a 44px (filtros, cifras) y foco de teclado visible.
  4. h1 sin <br>: salto con span de bloque y espacio real (los rastreadores lo leen).
  5. robots.txt con la línea Sitemap de su dominio.
  6. 404.astro propio (Cloudflare Pages sirve dist/404.html con estado 404 real).

Uso:
  python3 mejoras-diseno-guias.py                 # dry-run: dice qué haría
  python3 mejoras-diseno-guias.py --aplicar       # escribe (con backup .bak-AAAAMMDD)
  python3 mejoras-diseno-guias.py --solo zonalaisleta --aplicar
"""
import argparse
import datetime
import re
import shutil
import sys
from pathlib import Path

RAIZ = Path.home() / "Proyectos"
GUIA_DOMINIO = {
    "zonaalcaravaneras": "zonaalcaravaneras.com",
    "zonaguanarteme": "zonaguanarteme.com",
    "zonasantacatalina": "zonasantacatalina.com",
    "zonalaisleta": "zonalaisleta.com",
}
HOY = datetime.date.today().strftime("%Y%m%d")


# ---------- color ----------
def lum(hexcolor):
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def oscurecer(hexcolor, fondos, objetivo=4.5, paso=0.02):
    """Oscurece el color lo justo para que contrastе con TODOS los fondos dados."""
    h = hexcolor.lstrip("#")
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    k = 1.0
    while k > 0.05:
        cand = "#" + "".join(f"{max(0, int(c * k)):02x}" for c in rgb)
        if all(ratio(cand, f) >= objetivo for f in fondos):
            return cand
        k -= paso
    return "#000000"


def token(css, nombre, defecto=None):
    m = re.search(rf"--{re.escape(nombre)}:\s*(#[0-9a-fA-F]{{6}})", css)
    return m.group(1) if m else defecto


# ---------- ediciones ----------
def reemplaza(css, viejo, nuevo, etiqueta, avisos, obligatorio=True):
    n = css.count(viejo)
    if n == 1:
        return css.replace(viejo, nuevo), True
    if n == 0 and not obligatorio:
        avisos.append(f"  · omitido (ya aplicado o no existe): {etiqueta}")
        return css, False
    raise SystemExit(f"ABORTADO: '{etiqueta}' aparece {n} veces (se esperaba 1)")


def procesa_repo(nombre, aplicar):
    repo = RAIZ / nombre
    if not repo.is_dir():
        return f"{nombre}: no existe"
    dominio = GUIA_DOMINIO.get(nombre, f"{nombre}.com")
    css_path = repo / "src/styles/global.css"
    idx_path = repo / "src/pages/index.astro"
    robots_path = repo / "public/robots.txt"
    page404 = repo / "src/pages/404.astro"
    for p in (css_path, idx_path, robots_path):
        if not p.exists():
            return f"{nombre}: falta {p}"

    css = css_path.read_text()
    idx = idx_path.read_text()
    avisos, cambios = [], []

    # 1. tokens de contraste derivados de su propia paleta
    if "--sol-cta" not in css:
        sol = token(css, "sol")
        agua = token(css, "agua")
        arena = token(css, "arena", "#ffffff")
        sol_claro = token(css, "sol-claro", arena)
        if not sol or not agua:
            return f"{nombre}: no encuentro --sol o --agua en su paleta"
        sol_cta = oscurecer(sol, ["#ffffff"])
        agua_texto = oscurecer(agua, [arena, sol_claro])
        css, _ = reemplaza(
            css,
            f"  --sol-claro: {sol_claro};\n",
            f"  --sol-claro: {sol_claro};\n"
            f"  --sol-cta: {sol_cta};      /* {ratio('#ffffff', sol_cta):.2f}:1 con texto blanco */\n"
            f"  --agua-texto: {agua_texto}; /* {ratio(agua_texto, arena):.2f}:1 sobre arena */\n",
            "tokens de contraste", avisos)
        cambios.append(f"tokens: sol {sol}→{sol_cta}, agua {agua}→{agua_texto}")
    else:
        avisos.append("  · tokens de contraste ya presentes")

    # 2. fondos de botón que llevan texto blanco
    css, c1 = reemplaza(css, ".barra nav a.cta {\n  background: var(--sol);",
                        ".barra nav a.cta {\n  background: var(--sol-cta);", "cta", avisos, False)
    css, c2 = reemplaza(css, "  background: var(--sol);\n  color: #fff;\n  text-decoration: none;",
                        "  background: var(--sol-cta);\n  color: #fff;\n  text-decoration: none;", "boton", avisos, False)
    if c1 or c2:
        cambios.append("botones con blanco: --sol-cta")

    # 3. enlaces: agua oscurecida
    css, c3 = reemplaza(css, "a { color: var(--agua);", "a { color: var(--agua-texto);", "enlaces", avisos, False)
    if c3:
        cambios.append("enlaces: --agua-texto")

    # 4. sello de estado abierto
    m = re.search(r"\.tarjeta \.estado\.abierto \{ background: (#[0-9a-fA-F]{6}); \}", css)
    if m and ratio("#ffffff", m.group(1)) < 4.5:
        nuevo = oscurecer(m.group(1), ["#ffffff"])
        css = css.replace(m.group(0), f".tarjeta .estado.abierto {{ background: {nuevo}; }}")
        cambios.append(f"estado abierto: {m.group(1)}→{nuevo} ({ratio('#ffffff', nuevo):.2f}:1)")

    # 5. crédito de foto y texto pequeño
    css, c4 = reemplaza(css,
        "  font-size: 0.68rem;\n  color: rgba(255, 255, 255, 0.6);\n  z-index: 2;",
        "  font-size: 0.75rem;\n  color: rgba(255, 255, 255, 0.92);\n  text-shadow: 0 1px 3px rgba(4, 34, 46, 0.85);\n  z-index: 2;",
        "credito foto", avisos, False)
    if c4:
        cambios.append("crédito de foto: 12px y opaco")
    css, c5 = reemplaza(css, "  padding: 0.22rem 0.6rem;\n  font-size: 0.7rem;",
                        "  padding: 0.22rem 0.6rem;\n  font-size: 0.75rem;", "sello estado 12px", avisos, False)
    if c5:
        cambios.append("sello de estado: 12px")

    # 6. placeholder legible
    css = re.sub(r"(\.buscador::placeholder \{ color: )#[0-9a-fA-F]{6}(;)", r"\1var(--tinta-suave)\2", css)

    # 7. un solo control visible: borde en el panel, no en el input
    css, c6 = reemplaza(css, ".panel-busqueda {\n  background: #fff;\n  border-radius: var(--radio);",
                        ".panel-busqueda {\n  background: #fff;\n  border: 1px solid rgba(7, 59, 79, 0.55);\n  border-radius: var(--radio);",
                        "borde del buscador", avisos, False)
    if c6:
        cambios.append("buscador: borde en el panel")

    # 8. objetivos táctiles
    css, c7 = reemplaza(css, "  border-radius: 999px;\n  padding: 0.42rem 0.95rem;\n  font-size: 0.88rem;",
                        "  border-radius: 999px;\n  display: inline-flex;\n  align-items: center;\n  min-height: 44px;\n  padding: 0.42rem 0.95rem;\n  font-size: 0.88rem;",
                        "filtros 44px", avisos, False)
    css, c8 = reemplaza(css, ".cifras a,\n.cifras button {\n  font: inherit;",
                        ".cifras a,\n.cifras button {\n  display: inline-flex;\n  align-items: center;\n  gap: 0.3rem;\n  min-height: 44px;\n  font: inherit;",
                        "cifras 44px", avisos, False)
    if c7 or c8:
        cambios.append("objetivos táctiles a 44px")

    # 9. velo de cabecera para el contraste del wordmark sobre la foto
    css, c9 = reemplaza(css, ".barra {\n  position: absolute;\n  inset: 0 0 auto;\n  z-index: 3;\n  padding: 1.15rem 0;\n}",
                        ".barra {\n  position: absolute;\n  inset: 0 0 auto;\n  z-index: 3;\n  padding: 1.15rem 0;\n  background: linear-gradient(to bottom, rgba(4, 34, 46, 0.62), rgba(4, 34, 46, 0.18) 65%, transparent);\n}",
                        "velo cabecera", avisos, False)
    if c9:
        cambios.append("velo superior de cabecera")

    # 10. bloque final: foco, overflow, atribución, medida de lectura
    if "Foco de teclado visible" not in css:
        css += """
/* ---------- Foco de teclado visible (sloplint 26a) ---------- */
a:focus-visible,
button:focus-visible,
input:focus-visible,
summary:focus-visible,
[tabindex]:focus-visible {
  outline: 2px solid var(--agua-texto);
  outline-offset: 3px;
  border-radius: 4px;
}
.buscador:focus-visible { outline: 2px solid var(--agua-texto); outline-offset: 1px; border-radius: 6px; }
.panel-busqueda:focus-within { box-shadow: 0 0 0 2px rgba(7, 59, 79, 0.55), var(--sombra-alta); }

/* ---------- Suelo tipografico y de desbordamiento (sloplint 34 y 75) ---------- */
html, body { overflow-x: clip; }
.leaflet-container .leaflet-control-attribution,
.leaflet-container .leaflet-control-attribution a { font-size: 12px !important; }
p { text-wrap: pretty; }
h1, h2, h3 { text-wrap: balance; }
.prosa p, .nota-mapa, .cols p { max-width: 68ch; }
h1 .salto { display: block; }
"""
        cambios.append("foco visible, overflow-x, atribución 12px, medida de lectura")

    # 11. h1 sin <br>
    m = re.search(r"<h1>(Los comercios de)(?:&nbsp;)?<br\s*/?>\s*([^<]+)</h1>", idx)
    if m:
        idx = idx.replace(m.group(0), f'<h1>{m.group(1)} <span class="salto">{m.group(2).strip()}</span></h1>')
        cambios.append(f"h1 sin <br> (espacio real antes de «{m.group(2).strip()}»)")

    # 12. robots.txt con Sitemap
    robots = robots_path.read_text()
    if "Sitemap:" not in robots:
        lineas = robots.split("\n")
        robots = f"Sitemap: https://{dominio}/sitemap-index.xml\n" + robots
        cambios.append(f"robots.txt: Sitemap https://{dominio}/sitemap-index.xml")

    # 13. 404 real
    if not page404.exists():
        cambios.append("404.astro nuevo")

    print(f"\n### {nombre} ({dominio})")
    for c in cambios:
        print(f"  ✓ {c}")
    for a in avisos:
        print(a)
    if not cambios:
        print("  sin cambios pendientes (idempotente)")

    if not aplicar:
        return f"{nombre}: dry-run"

    for p in (css_path, idx_path, robots_path):
        shutil.copy2(p, p.with_suffix(p.suffix + f".bak-{HOY}"))
    css_path.write_text(css)
    idx_path.write_text(idx)
    robots_path.write_text(robots)
    return f"{nombre}: aplicado ({len(cambios)} cambios)"


PLANTILLA_404 = """---
import Base from '../layouts/Base.astro';
import {{ contacto, enlaceWhatsapp }} from '../config.js';

const wa = enlaceWhatsapp('Hola, quiero añadir mi comercio a la guía de {zona}.');
---

<Base
  titulo="Página no encontrada — {zona}"
  descripcion="Esta dirección no existe en la guía de comercios de {zona}. Vuelve a la portada o busca tu comercio por categoría."
>
  <section class="cinta" slot="portada">
    <div class="contenedor">
      <span class="etiqueta-cat">Error 404</span>
      <h1>Esta página no existe</h1>
    </div>
  </section>

  <div class="contenedor"><div class="prosa">
    <p>
      La dirección que has escrito no corresponde a ningún comercio ni a ninguna sección
      de la guía. Puede que el enlace esté mal copiado o que el negocio haya cerrado.
    </p>
    <p>
      Vuelve a la <a href="/">portada de la guía</a> para ver los comercios del barrio,
      o escríbenos y lo buscamos por ti.
    </p>
    <div class="acciones">
      <a class="boton" href="/">Ir a la portada</a>
      <a class="boton secundario" href={{wa}}>Escribir por WhatsApp</a>
    </div>
    <p>
      ¿Tienes un comercio en el barrio y no aparece? <a href={{wa}}>Añadirlo es gratis</a>
      y se queda mientras quieras. También puedes escribir a
      <a href={{`mailto:${{contacto.email}}`}}>{{contacto.email}}</a>.
    </p>
  </div></div>
</Base>
"""


def crea_404(nombre, aplicar):
    repo = RAIZ / nombre
    page = repo / "src/pages/404.astro"
    if page.exists():
        return
    zona = nombre.replace("zona", "Zona ").replace("alcaravaneras", "Alcaravaneras") \
                 .replace("guanarteme", "Guanarteme").replace("santacatalina", "Santa Catalina") \
                 .replace("laisleta", "La Isleta")
    if aplicar:
        page.write_text(PLANTILLA_404.format(zona=zona))
        print(f"  ✓ {nombre}: 404.astro creado ({zona})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--solo")
    args = ap.parse_args()
    nombres = [args.solo] if args.solo else list(GUIA_DOMINIO)
    for n in nombres:
        print(procesa_repo(n, args.aplicar))
    if args.aplicar:
        for n in nombres:
            crea_404(n, True)
    print("\nDespués: npm run build en cada repo y medir con sloplint e imp.")


if __name__ == "__main__":
    sys.exit(main())
