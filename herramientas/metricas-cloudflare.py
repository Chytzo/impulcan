#!/usr/bin/env python3
"""Métricas de tráfico de las guías desde Cloudflare (GraphQL Analytics API).

El token se lee de CF_API_TOKEN (entorno) o de ~/.hermes/.env — nunca del repositorio.
Permisos mínimos:  Zone → Analytics: Read   y   Account → Account Analytics: Read.

Uso:
    python3 metricas-cloudflare.py                 # últimos 7 días, tabla
    python3 metricas-cloudflare.py --dias 30
    python3 metricas-cloudflare.py --json

Sin Web Analytics activado, Cloudflare da peticiones, ancho de banda, caché y visitantes únicos
estimados (uniques por día). Las páginas vistas exactas requieren Web Analytics en cada proyecto.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import NoReturn

API = "https://api.cloudflare.com/client/v4/graphql"
DOMINIOS = ["zonaalcaravaneras.com", "zonalaisleta.com", "zonaguanarteme.com",
            "zonasantacatalina.com", "impulcan.com"]
ENVF = Path.home() / ".hermes" / ".env"

ZONAS_Q = "query { viewer { zones(filter: {}) { zoneTag name } } }"

HTTP_Q = """
query($tags: [String!], $desde: Date, $hasta: Date) {
  viewer {
    zones(filter: {zoneTag_in: $tags}) {
      zoneTag
      httpRequests1dGroups(limit: 100, filter: {date_geq: $desde, date_leq: $hasta}) {
        dimensions { date }
        sum { requests bytes cachedRequests threats }
        uniq { uniques }
      }
    }
  }
}
"""


def salir(msg: str) -> NoReturn:
    print(f"ERROR: {msg}", file=__import__("sys").stderr)
    raise SystemExit(2)


def token() -> str:
    t = os.environ.get("CF_API_TOKEN", "").strip()
    if t:
        return t
    if ENVF.exists():
        for linea in ENVF.read_text(errors="replace").splitlines():
            if linea.startswith("CF_API_TOKEN="):
                valor = linea.split("=", 1)[1].strip().strip("'\"")
                if valor:
                    return valor
    salir("falta CF_API_TOKEN (variable de entorno o ~/.hermes/.env)")


def gql(tok: str, consulta: str, variables: dict) -> dict:
    datos = json.dumps({"query": consulta, "variables": variables}).encode()
    req = urllib.request.Request(API, data=datos, headers={
        "Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    cuerpo: dict = {}
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            cuerpo = json.load(r)
    except urllib.error.HTTPError as e:
        salir(f"HTTP {e.code} de Cloudflare: {e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        salir(f"no se pudo conectar con la API: {e.reason}")
    if cuerpo.get("errors"):
        salir("GraphQL: " + "; ".join(str(x.get("message")) for x in cuerpo["errors"]))
    return cuerpo.get("data") or {}


def agregar(zonas: list[dict], mapa: dict[str, str]) -> list[dict]:
    """Suma las series diarias de cada zona. Función pura (sin red) para poder probarla."""
    filas = []
    for z in zonas:
        nombre = next((n for n, t in mapa.items() if t == z.get("zoneTag")), str(z.get("zoneTag")))
        serie = z.get("httpRequests1dGroups") or []
        req = sum(int(g.get("sum", {}).get("requests") or 0) for g in serie)
        vis = sum(int(g.get("uniq", {}).get("uniques") or 0) for g in serie)
        byt = sum(int(g.get("sum", {}).get("bytes") or 0) for g in serie)
        cac = sum(int(g.get("sum", {}).get("cachedRequests") or 0) for g in serie)
        filas.append({"dominio": nombre, "dias": len(serie), "peticiones": req,
                      "visitantes": vis, "MB": round(byt / 1e6, 1),
                      "cache_pct": round(100 * cac / req, 1) if req else 0.0})
    filas.sort(key=lambda f: -f["peticiones"])
    return filas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    tok = token()
    hasta = date.today()
    desde = hasta - timedelta(days=args.dias)

    zonas = gql(tok, ZONAS_Q, {})
    mapa = {z["name"]: z["zoneTag"] for z in (zonas.get("viewer", {}).get("zones") or [])}
    nuestros = {d: mapa[d] for d in DOMINIOS if d in mapa}
    faltan = [d for d in DOMINIOS if d not in mapa]
    if not nuestros:
        salir("el token no ve ninguna de nuestras zonas (revisa permiso Zone:Read)")

    datos = gql(tok, HTTP_Q, {"tags": list(nuestros.values()),
                              "desde": desde.isoformat(), "hasta": hasta.isoformat()})
    filas = agregar(datos.get("viewer", {}).get("zones") or [], nuestros)

    if args.json:
        print(json.dumps({"desde": desde.isoformat(), "hasta": hasta.isoformat(),
                          "zonas": filas, "sin_datos": faltan}, ensure_ascii=False, indent=1))
        return 0

    print(f"Cloudflare · {desde} → {hasta} ({args.dias} días)\n")
    print(f"  {'dominio':24} {'días':>4} {'peticiones':>11} {'visitantes':>11} {'MB':>8} {'caché':>7}")
    for f in filas:
        print(f"  {f['dominio']:24} {f['dias']:4} {f['peticiones']:11} {f['visitantes']:11} "
              f"{f['MB']:8} {f['cache_pct']:6}%")
    if faltan:
        print(f"\n  zonas no visibles con este token: {', '.join(faltan)}")
    print("\n  'visitantes' es la estimación de Cloudflare (uniques por día). Las páginas vistas")
    print("  exactas requieren activar Web Analytics en cada proyecto del panel.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
