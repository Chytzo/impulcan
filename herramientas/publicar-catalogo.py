#!/usr/bin/env python3
"""
Publica el catálogo OSM (y el resto de directorio.db no publicado) como fichas
en las webs de las 4 guías. Fuente: datos/directorio.db. Sin duplicados.

Escribe en cada https://.../src/data/comercios.json solo los que no existen ya.
Uso:
  python3 publicar-catalogo.py [--dry-run]
"""
import argparse, json, sqlite3, sys
from pathlib import Path

RAIZ = Path.home() / "Proyectos"
DB = RAIZ / "impulcan" / "datos" / "directorio.db"
REPO = {"alcaravaneras": "zonaalcaravaneras", "guanarteme": "zonaguanarteme",
        "santacatalina": "zonasantacatalina", "laisleta": "zonalaisleta"}

def ficha(n):
    return {
        "slug": n["slug"], "nombre": n["nombre"], "categoria": n["categoria"] or "Servicios",
        "calle": n["calle"] or "", "cp": n["cp"] or "", "telefono": n["telefono"],
        "whatsapp": "", "web": n["web"], "email": n["email"], "horario": n["horario"],
        "horarioSchema": [], "lat": n["lat"], "lon": n["lon"], "rasgos": [],
        "destacado": False, "fotos": [], "fuente": n["fuente"] or "osm",
        "maps": "", "descripcion": "",
    }

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); args = ap.parse_args()
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    total = 0
    for guia, repo in REPO.items():
        p = RAIZ / repo / "src" / "data" / "comercios.json"
        fichas = json.loads(p.read_text())
        existentes = {f.get("slug") for f in fichas} | {f.get("nombre") for f in fichas}
        nuevos = 0
        for r in con.execute("SELECT * FROM negocios WHERE guia=? ORDER BY nombre", (guia,)):
            n = dict(r)
            if n["slug"] in existentes or n["nombre"] in existentes:
                continue
            fichas.append(ficha(n)); existentes.add(n["slug"]); existentes.add(n["nombre"]); nuevos += 1
        print(f"{repo}: +{nuevos} fichas nuevas (total {len(fichas)})")
        total += nuevos
        if not args.dry_run:
            p.write_text(json.dumps(fichas, ensure_ascii=False, indent=2))
    print(f"TOTAL fichas nuevas a publicar en las webs: {total}")
    if args.dry_run:
        print("DRY-RUN: no se escribió nada.")

if __name__ == "__main__":
    main()