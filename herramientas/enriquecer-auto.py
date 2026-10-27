#!/usr/bin/env python3
"""
Enriquece automáticamente las fichas de comercios en las 4 guías de barrio de Impulcan
buscando teléfono, email y sitio web oficial de comercios en Las Palmas de Gran Canaria.
"""
import json
import pathlib
import re
import sys
import time
import requests

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
BARRIOS = [
    ("zonaalcaravaneras", "Las Alcaravaneras"),
    ("zonaguanarteme", "Guanarteme"),
    ("zonalaisleta", "La Isleta"),
    ("zonasantacatalina", "Santa Catalina"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

IGNORED_DOMAINS = [
    "duckduckgo.com", "bing.com", "google.com", "facebook.com", "instagram.com",
    "tripadvisor.es", "tripadvisor.com", "paginasamarillas.es", "paxinasgalegas.es",
    "einforma.com", "axesor.es", "empresite.eleconomista.es", "foursquare.com",
    "yelp.es", "w3.org", "schema.org", "wikipedia.org", "github.com",
    "callejero.net", "callejero.club", "practicatest.com", "todotest.com",
    "autoescuelas.es", "cylex.es", "vulka.es", "guiadelsur.es", "canarias7.es",
    "laprovincia.es", "eldiario.es", "boe.es", "boc.es", "laspalmasgc.es",
    "directorio", "infobel.com", "11888.es", "habissimo.es", "milanuncios.com",
    "wallapop.com", "idealista.com", "fotocasa.es"
]

IGNORED_EMAILS = [
    "info@paginasamarillas.es", "contacto@tripadvisor.com", "soporte@einforma.com",
    "info@callejero.net", "admin@practicatest.com"
]

def formatear_telefono(raw_digits):
    if len(raw_digits) == 9:
        if raw_digits.startswith("928"):
            return f"+34 {raw_digits[:3]} {raw_digits[3:5]} {raw_digits[5:7]} {raw_digits[7:]}"
        elif raw_digits.startswith("6") or raw_digits.startswith("7"):
            return f"+34 {raw_digits[:3]} {raw_digits[3:5]} {raw_digits[5:7]} {raw_digits[7:]}"
    return raw_digits

def buscar_contacto(nombre, calle, barrio):
    # Ignorar nombres puramente numéricos o genéricos de 1-2 letras
    if re.match(r"^\d+$", nombre.strip()) or len(nombre.strip()) <= 2:
        return None

    query = f"{nombre} {calle} Las Palmas de Gran Canaria"
    try:
        resp = requests.post("https://lite.duckduckgo.com/lite/", data={"q": query}, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return None
        html = resp.text
    except Exception:
        return None

    # Extraer teléfonos (928 / móviles 6XX, 7XX)
    raw_phones = re.findall(r"\b(?:\+34\s*)?(?:928|6\d{2}|7\d{2})[\s.-]?\d{2,3}[\s.-]?\d{2,3}[\s.-]?\d{2,3}\b", html)
    telefonos = []
    for p in raw_phones:
        digits = re.sub(r"[^\d]", "", p)
        if len(digits) == 9 and (digits.startswith("928") or digits.startswith("6") or digits.startswith("7")):
            telefonos.append(formatear_telefono(digits))
    telefonos = list(dict.fromkeys(telefonos))

    # Extraer emails
    raw_emails = re.findall(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", html)
    emails = []
    for e in raw_emails:
        el = e.lower()
        if not any(dom in el for dom in ["duckduckgo", "w3.org", "schema", "example", "domain", "png", "jpg", "jpeg"]):
            if el not in IGNORED_EMAILS:
                emails.append(el)
    emails = list(dict.fromkeys(emails))

    # Extraer web oficial (enlaces que no sean directorios o agregadores)
    urls = re.findall(r"href=[\"'](https?://[^\"']+)[\"']", html)
    webs = []
    for u in urls:
        u_lower = u.lower()
        if not any(dom in u_lower for dom in IGNORED_DOMAINS):
            webs.append(u)
    webs = list(dict.fromkeys(webs))

    return {
        "telefono": telefonos[0] if telefonos else None,
        "email": emails[0] if emails else None,
        "web": webs[0] if webs else None
    }

def procesar_barrio(repo, barrio_nombre, max_fichas=30):
    json_path = RAIZ / repo / "src" / "data" / "comercios.json"
    if not json_path.exists():
        print(f"[-] No existe {json_path}")
        return 0, 0, 0, 0

    with open(json_path, "r", encoding="utf-8") as f:
        comercios = json.load(f)

    modificados = 0
    tels_add, emails_add, webs_add = 0, 0, 0

    procesados_en_esta_tanda = 0
    for c in comercios:
        falta_tel = not c.get("telefono")
        falta_email = not c.get("email")
        falta_web = not c.get("web")

        if not (falta_tel or falta_email or falta_web):
            continue

        res = buscar_contacto(c["nombre"], c.get("calle", ""), barrio_nombre)
        procesados_en_esta_tanda += 1

        if res:
            cambio = False
            if falta_tel and res["telefono"]:
                c["telefono"] = res["telefono"]
                # también actualizamos el whatsapp con número sin espacios/símbolos
                digits = re.sub(r"[^\d]", "", res["telefono"])
                if len(digits) == 9:
                    c["whatsapp"] = f"34{digits}"
                tels_add += 1
                cambio = True
            if falta_email and res["email"]:
                c["email"] = res["email"]
                emails_add += 1
                cambio = True
            if falta_web and res["web"]:
                c["web"] = res["web"]
                webs_add += 1
                cambio = True

            if cambio:
                c["fuente"] = c.get("fuente") or "Búsqueda Web Enriquecida"
                modificados += 1
                print(f"  [+] {c['nombre'][:30]:32} | Tel: {res['telefono'] or '-'} | Email: {res['email'] or '-'} | Web: {res['web'] or '-'}")

        time.sleep(0.5)

        if max_fichas and procesados_en_esta_tanda >= max_fichas:
            break

    if modificados > 0:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(comercios, f, ensure_ascii=False, indent=1)

    return modificados, tels_add, emails_add, webs_add

def main():
    max_fichas = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    print(f"=== INICIANDO ENRIQUECIMIENTO (Máx {max_fichas} fichas por barrio) ===")
    
    tot_mod = 0
    tot_tels, tot_emails, tot_webs = 0, 0, 0
    for repo, barrio_nombre in BARRIOS:
        print(f"\n--- Procesando {repo} ({barrio_nombre}) ---")
        mod, tels, emails, webs = procesar_barrio(repo, barrio_nombre, max_fichas=max_fichas)
        tot_mod += mod
        tot_tels += tels
        tot_emails += emails
        tot_webs += webs
        print(f"Subtotal {repo}: {mod} comercios enriquecidos (+{tels} tels, +{emails} emails, +{webs} webs)")

    print(f"\n==========================================")
    print(f"TOTAL: {tot_mod} comercios enriquecidos")
    print(f"  + Teléfonos: {tot_tels}")
    print(f"  + Emails:    {tot_emails}")
    print(f"  + Webs:      {tot_webs}")
    print(f"==========================================")

if __name__ == "__main__":
    main()
