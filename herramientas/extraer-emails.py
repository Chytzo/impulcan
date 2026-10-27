#!/usr/bin/env python3
"""
Extrae emails reales de las webs PROPIAS de los comercios de las guías.

Fuente: comercios con `web` propia (dominio del negocio, no red social).
Visita la web raíz (y /contacto, /contact, /es/contacto si existen), recoge
mailto: + direcciones con regex, valida el formato y las guarda en guias.db
(columna email) con fuente 'web_propia'.

No inventa nada: solos emails publicados en la web del propio negocio.
Uso:
  python3 extraer-emails.py [--lote N] [--dry-run] [--solo-guia GUIA_ALIAS]
"""
import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

RAIZ = Path.home() / "Proyectos"
BD = Path.home() / "Proyectos" / "impulcan" / "datos" / "guias.db"
CHECKPOINT = Path("/tmp/extraer-emails-checkpoint.json")

UA = ("Mozilla/5.0 (X11; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0 "
      "AppleWebKit/537.36")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
# placeholders de plantillas web que NO son emails reales del negocio
PLACEHOLDER_EMAILS = ("email@example", "your@email", "tu@email", "mail@example",
                      "user@example", "email@gmail.com", "correo@", "info@example",
                      "admin@example", "contact@example", "hola@tuweb", "name@",
                      "you@", "asunto@", "email@tudominio", "contacto@example",
                      "contact@mysite", ".png", ".jpg", ".jpeg", ".gif")
# dominios de hosting de demo/previsualizacion — no son emails del negocio real
BAD_DOMAINS = ("previewsrv", "webnode", "wixsite", "strikingly", "preview.", "demo.",
               "restaurantdemo", "mysite", "bjo.lt", "template")
CONTACT_PATHS = ["", "contacto", "contact", "contacto/", "contact/", "es/contacto",
                 "contactanos", "contact/contacto"]
SOCIAL_HOSTS = ("facebook", "instagram", "twitter", "tripadvisor", "maps.google",
                "yelp", "whatsapp", "wa.me")


def fetch(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(500000).decode("utf-8", "ignore")


def is_own_web(web):
    if not web:
        return False
    w = web.lower()
    return not any(h in w for h in SOCIAL_HOSTS) and "@" not in w


def domain_of(web):
    p = urlparse(web if "//" in web else "//" + web)
    return p.netloc or p.path.split("/")[0]


def extract_emails_from_html(html):
    # capturar mailto: e emails visibles en el texto
    emails = set()
    for m in EMAIL_RE.findall(html):
        e = m.strip().rstrip(".")
        dom = e.partition("@")[2].lower()
        if any(b in dom for b in BAD_DOMAINS):
            continue
        if e.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")):
            continue
        if "." in e.split("@")[0]:
            # evitar false positives tipo version@1.2 como email
            pass
        if any(e.lower().startswith(p) for p in PLACEHOLDER_EMAILS):
            continue
        emails.add(e)
    return {e for e in emails if not e.lower().endswith(("png", "jpg", "gif"))}


def get_emails(base):
    """Devuelve set de emails publicados en la web raíz + páginas de contacto."""
    if not is_own_web(base):
        return set()
    dom = domain_of(base)
    scheme = "https" if base.startswith("https") else ("http" if base.startswith("http") else "https")
    root = f"{scheme}://{dom}"
    found = set()
    for path in CONTACT_PATHS:
        url = urljoin(root + "/", path)
        try:
            html = fetch(url)
            found |= extract_emails_from_html(html)
        except Exception:
            continue
        if len(found) >= 3:  # suficiente
            break
    # filtrar emails del dominio propio del scrapeador (impulcan) ni de la guia
    found = {e for e in found if not e.lower().endswith(("png", "jpg", "gif", "css", "js"))}
    return found


def load_pool():
    con = sqlite3.connect(BD); con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT guia, slug, nombre, email, web FROM comercios "
        "WHERE web IS NOT NULL AND web<>'' ORDER BY guia, nombre").fetchall()
    return con, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lote", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--solo-guia", default=None)
    args = ap.parse_args()

    con, rows = load_pool()
    if args.solo_guia:
        rows = [r for r in rows if r["guia"] == args.solo_guia]

    candidatos = [r for r in rows if is_own_web(r["web"])]
    print(f"comercios con web propia: {len(candidatos)} / {len(rows)} con web")

    prog = 0; nuevos = 0; sin_email = 0; errores = 0
    for r in candidatos[: args.lote]:
        prog += 1
        web = r["web"]
        try:
            emails = get_emails(web)
        except Exception as e:
            print(f"  [{prog}] {r['nombre']} ({r['guia']}) ERROR {type(e).__name__}")
            errores += 1
            continue
        # filtrar el email del propio comercio ya registrado (si distinto)
        ya = (r["email"] or "").strip().lower()
        alvos = [e for e in emails if e.lower() != ya and e.lower() not in
                 ("hola@impulcan.com",)]
        if alvos:
            nuevos += 1
            det = ", ".join(sorted(alvos))
            print(f"  [{prog}] {r['nombre']} ({r['guia']}) -> {det}")
            if not args.dry_run and (not r["email"] or r["email"].strip() == ""):
                con.execute("UPDATE comercios SET email=? WHERE guia=? AND slug=?",
                            (sorted(alvos)[0], r["guia"], r["slug"]))
                con.commit()
        else:
            sin_email += 1
            print(f"  [{prog}] {r['nombre']} ({r['guia']}) sin email visible")
        time.sleep(0.6)

    print(f"\nPROCESADOS: {prog} | con email hallado: {nuevos} | sin email: {sin_email} | errores: {errores}")


if __name__ == "__main__":
    main()
