#!/usr/bin/env python3
"""
Enriquece y expande las guías desde Google Places API (New).

Por qué existe: en vez de scrapear Google Maps por CDP (lento, 0.14 f/s, frágil),
la API oficial es la vía permitida y con tope gratuito por SKU (10k/mes Essentials,
5k/mes Pro desde mar-2025; +300$ una vez por cuenta nueva).

Qué hace:
  1. Enumeración: Nearby Search (New) por barrio con el rectángulo real de la
     zona (lat/lon ya 100% en guias.db) y TODOS los tipos de las 13 categorías
     en una sola query por barrio, paginando (pageToken).
  2. Detalle: Place Details (Essentials — sin reseñas, sin fotos: regla dura de
     la red: nada de imágenes de terceros) por cada place_id: teléfono, web,
     horario (currentOpeningHours), businessStatus, tipos, plusCode.
  3. Match: nombre normalizado + distancia < 150 m contra las fichas existentes.
     Vacíos se rellenan (solo si están vacíos); nuevos se insertan.
  4. Salida: guias.db (capa operativa) + delta sobre src/data/comercios.json de
     cada repo (capa web). --dry-run por defecto: no toca nada.

Coste: 2.047 fichas + ~2-3k nuevas → ~5k Details (Essentials gratis 10k) +
~4-20 Nearby (Pro gratis 5k). Dentro de los topes gratuitos mensuales.

Uso:
  export GOOGLE_PLACES_KEY=<api_key>
  python3 herramientas/places-enrich.py --dry-run            # solo informe
  python3 herramientas/places-enrich.py --lote 200 --write   # aplica 200
  python3 herramientas/places-enrich.py --write              # todo el barrido
"""
import argparse, json, math, os, re, sqlite3, sys, time, urllib.request, urllib.error
from pathlib import Path

RAIZ = Path.home() / "Proyectos"
BD = RAIZ / "impulcan" / "datos" / "guias.db"
KEY_FILE = Path.home() / ".config" / "impulcan" / "google-places.key"
API = "https://places.googleapis.com/v1"
UA = {"User-Agent": "impulcan-enrich/1.0", "X-Goog-Api-Key": os.environ.get("GOOGLE_PLACES_KEY", ""),
      "Content-Type": "application/json"}

# Rectángulos de los 4 barrios (padding ligero sobre los rangos reales de la DB)
BARRIOS = {
    "alcaravaneras":  {"low": (28.1260, -15.4370), "high": (28.1360, -15.4270)},
    "guanarteme":     {"low": (28.1200, -15.4570), "high": (28.1390, -15.4340)},
    "santacatalina":  {"low": (28.1340, -15.4390), "high": (28.1480, -15.4260)},
    "laisleta":       {"low": (28.1450, -15.4340), "high": (28.1600, -15.4200)},
}

# Categoría de la red -> tipos Google VÁLIDOS (Places API). Se fusionan en UNA query por barrio.
# guia (valor en DB) -> carpeta del repo Astro
REPO_DIR = {"alcaravaneras": "zonaalcaravaneras", "guanarteme": "zonaguanarteme",
            "santacatalina": "zonasantacatalina", "laisleta": "zonalaisleta"}

TIPOS_POR_CATEGORIA = {
    "Alimentación": ["supermarket", "grocery_store", "convenience_store", "shopping_mall"],
    "Bares y cafés": ["bar", "cafe", "restaurant"],
    "Bazares": ["store", "gift_shop", "department_store"],
    "Belleza": ["beauty_salon", "hair_salon", "spa", "nail_salon"],
    "Deporte y ocio": ["gym", "fitness_center", "sports_activity_location", "bowling_alley",
                       "amusement_center", "stadium", "park"],
    "Electrónica": ["electronics_store"],
    "Hogar y reformas": ["home_goods_store", "hardware_store", "furniture_store"],
    "Mascotas": ["pet_store", "veterinary_care"],
    "Moda": ["clothing_store", "shoe_store", "jewelry_store"],
    "Motor": ["car_dealer", "car_repair", "auto_parts_store", "car_wash"],
    "Restaurantes": ["restaurant", "bakery", "meal_delivery", "meal_takeaway", "food_court"],
    "Salud": ["pharmacy", "dentist", "doctor", "hospital", "physiotherapist", "medical_lab"],
    "Servicios": ["locksmith", "electrician", "plumber", "laundry", "travel_agency", "bank",
                  "atm", "real_estate_agency", "insurance_agency", "lawyer", "accounting",
                  "post_office"],
}
TODOS_TIPOS = sorted({t for ts in TIPOS_POR_CATEGORIA.values() for t in ts})

# Place Details (GET): el mask va SIN prefijo "places." (a diferencia de Nearby/Text).
# tier: Essentials (addressComponents,formattedAddress,location,plusCode,types) ·
# Pro (businessStatus,displayName) · Enterprise (currentOpeningHours,nationalPhoneNumber,websiteUri).
DETAILS_MASK = ("id,displayName,formattedAddress,addressComponents,nationalPhoneNumber,"
                "websiteUri,currentOpeningHours,location,businessStatus,types,plusCode")
NEARBY_MASK = "places.id,places.displayName,places.location,places.types"

ACC = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")

def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().translate(ACC))

def slugify(s):
    s = (s or "").lower().translate(ACC)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "sin-nombre"

def dist_m(a, b):
    R = 6371000
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))

def circulo_de(bbox):
    """Centro del bbox + radio que cubre el rectangulo con margen (Nearby usa circle)."""
    lat = (bbox["low"][0] + bbox["high"][0]) / 2
    lon = (bbox["low"][1] + bbox["high"][1]) / 2
    radio = dist_m(bbox["low"], bbox["high"]) / 2 * 1.25
    return {"center": {"latitude": lat, "longitude": lon}, "radius": radio}

def key():
    k = os.environ.get("GOOGLE_PLACES_KEY") or (KEY_FILE.read_text().strip() if KEY_FILE.exists() else "")
    if not k:
        sys.exit("FALTA clave: pon GOOGLE_PLACES_KEY o ~/.config/impulcan/google-places.key")
    return k

def api_call(path, payload=None, mask=None):
    hdrs = {k: v for k, v in UA.items()}
    hdrs["X-Goog-Api-Key"] = key()
    if mask:
        hdrs["X-Goog-FieldMask"] = mask
    if payload is None:
        req = urllib.request.Request(f"{API}/{path}", headers=hdrs, method="GET")
    else:
        req = urllib.request.Request(f"{API}/{path}", headers=hdrs, data=json.dumps(payload).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code} {body}")

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def nearby(bbox):
    """Enumeración paginada en un barrio. includedTypes admite <=50: troceamos.
    Nearby (New) usa locationRestriction.circle (no rectángulo)."""
    places, calls = [], 0
    circ = circulo_de(bbox)
    for chunk_tipos in chunks(TODOS_TIPOS, 45):
        payload = {
            "includedTypes": chunk_tipos,
            "locationRestriction": {"circle": circ},
            "maxResultCount": 20,
        }
        for page in range(6):
            calls += 1
            data = api_call("places:searchNearby", payload, mask=NEARBY_MASK)
            places.extend(data.get("places", []))
            tok = data.get("nextPageToken")
            if not tok:
                break
            payload = {"pageToken": tok}
            time.sleep(0.5)
    # dedupe por id
    seen, uniq = set(), []
    for p in places:
        if p.get("id") and p["id"] not in seen:
            seen.add(p["id"]); uniq.append(p)
    return uniq, calls

def details(place_id):
    """Place Details Essentials: sin reseñas ni fotos (regla dura de la red)."""
    return api_call(f"places/{place_id}", mask=DETAILS_MASK)

def clasifica(types):
    for cat, ts in TIPOS_POR_CATEGORIA.items():
        if any(t in types for t in ts):
            return cat
    return "Servicios"

def cp_de(formatted, components):
    cp = ""
    for c in components:
        if "postal_code" in c.get("types", []):
            cp = c.get("shortText", "")
    m = re.search(r"(\d{5})", formatted or "")
    return cp or (m.group(1) if m else "")

def calle_de(formatted):
    if not formatted:
        return ""
    return re.sub(r",?\s*\d{5}\s*[^,]+(?:,.*)?$", "", formatted).strip()

def hora_texto(d):
    return "; ".join(d.get("weekdayDescriptions", [])) if d else ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="aplica cambios (por defecto dry-run)")
    ap.add_argument("--lote", type=int, default=0, help="max detalles a procesar (0 = sin limite)")
    ap.add_argument("--solo-guia", default=None)
    args = ap.parse_args()

    con = sqlite3.connect(BD); con.row_factory = sqlite3.Row
    existentes = []
    for r in con.execute("SELECT guia,slug,nombre,lat,lon,categoria,telefono,web,horario FROM comercios"):
        existentes.append(dict(r))
    idx = {}
    for e in existentes:
        idx.setdefault(e["guia"], []).append(e)
    for g in idx:
        for e in idx[g]:
            e["_norm"] = norm(e["nombre"])
            e["_pos"] = (e["lat"], e["lon"]) if e["lat"] and e["lon"] else None

    json_delta = {"alcaravaneras": {"rellenados": [], "nuevos": []},
                  "guanarteme": {"rellenados": [], "nuevos": []},
                  "santacatalina": {"rellenados": [], "nuevos": []},
                  "laisleta": {"rellenados": [], "nuevos": []}}
    stats = {"nearby_calls": 0, "details_calls": 0, "nuevos": 0, "rellenados": 0,
             "sin_cambios": 0, "cerrados": 0, "matcheados": 0}

    for guia, bbox in BARRIOS.items():
        if args.solo_guia and guia != args.solo_guia:
            continue
        print(f"\n== {guia} ==")
        try:
            places, calls = nearby(bbox)
        except RuntimeError as e:
            print(f"  Nearby fallo: {e}"); stats["nearby_calls"] += 1; continue
        stats["nearby_calls"] += calls
        print(f"  enumerados {len(places)} places ({calls} llamadas Nearby)")
        for p in places:
            pid = p.get("id")
            ptypes = p.get("types", [])
            pname = (p.get("displayName") or {}).get("text", "")
            if "establishment" not in ptypes and not any(t in ptypes for t in TODOS_TIPOS):
                continue
            cat = clasifica(ptypes)
            try:
                d = details(pid)
            except RuntimeError as e:
                print(f"  detail {pid} fallo: {e}"); stats["details_calls"] += 1; continue
            stats["details_calls"] += 1
            if args.lote and stats["details_calls"] > args.lote:
                print("  lote alcanzado, parando"); break
            if d.get("businessStatus") == "CLOSED_PERMANENTLY":
                stats["cerrados"] += 1; continue
            pos = d.get("location") or p.get("location") or {}
            lat = pos.get("latitude"); lon = pos.get("longitude")
            tel = d.get("nationalPhoneNumber", "")
            web = d.get("websiteUri", "")
            hora = hora_texto(d.get("currentOpeningHours"))
            direc = d.get("formattedAddress", "")
            # match contra existentes
            match = None
            for e in idx.get(guia, []):
                if norm(pname) == e["_norm"] and e["_pos"] and lat and (dist_m((lat, lon), e["_pos"]) < 150):
                    match = e; break
            if match:
                stats["matcheados"] += 1
                cambios = {}
                for campo, val in (("telefono", tel), ("web", web), ("horario", hora)):
                    if val and not match.get(campo):
                        cambios[campo] = val
                if cambios:
                    stats["rellenados"] += 1
                    json_delta[guia]["rellenados"].append({"slug": match["slug"], **cambios})
                else:
                    stats["sin_cambios"] += 1
                continue
            # nuevo
            stats["nuevos"] += 1
            slug = slugify(pname)
            nuevo = {"nombre": pname, "categoria": cat, "calle": calle_de(direc), "cp": cp_de(direc, d.get("addressComponents", [])),
                     "telefono": tel or None, "web": web or None, "horario": hora or None,
                     "lat": lat, "lon": lon, "fuente": "google_places"}
            json_delta[guia]["nuevos"].append({"slug": slug, **nuevo})
            if len(json_delta[guia]["nuevos"]) % 50 == 0:
                print(f"  ...{len(json_delta[guia]['nuevos'])} nuevos acumulados en {guia}")
        if args.lote and stats["details_calls"] > args.lote:
            break

    print("\n================ RESUMEN ================")
    print(f"Nearby calls: {stats['nearby_calls']} | Details calls: {stats['details_calls']}")
    print(f"nuevos: {stats['nuevos']} | rellenados: {stats['rellenados']} | sin cambios: {stats['sin_cambios']} | cerrados: {stats['cerrados']} | matcheados: {stats['matcheados']}")

    if not args.write:
        print("\nDRY-RUN: no se escribió nada. Usa --write para aplicar.")
        return

    # escribir en guias.db
    for guia, d in json_delta.items():
        for c in d["rellenados"]:
            sets, vals = [], []
            for campo in ("telefono", "web", "horario"):
                if campo in c:
                    sets.append(f"{campo}=?"); vals.append(c[campo])
            if sets:
                vals.append(guia); vals.append(c["slug"])
                con.execute(f"UPDATE comercios SET {', '.join(sets)} WHERE guia=? AND slug=?", vals)
        for n in d["nuevos"]:
            con.execute(
                "INSERT OR IGNORE INTO comercios (guia,slug,nombre,categoria,calle,cp,telefono,web,horario,lat,lon,fuente) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (guia, n["slug"], n["nombre"], n["categoria"], n["calle"], n["cp"], n["telefono"],
                 n["web"], n["horario"], n["lat"], n["lon"], "google_places"))
    con.commit()

    # escribir delta en comercios.json de cada repo
    for guia, d in json_delta.items():
        if not d["rellenados"] and not d["nuevos"]:
            continue
        path = RAIZ / REPO_DIR[guia] / "src" / "data" / "comercios.json"
        fichas = json.loads(path.read_text())
        for c in d["rellenados"]:
            for f in fichas:
                if f.get("slug") == c["slug"]:
                    for campo in ("telefono", "web", "horario"):
                        if campo in c and not f.get(campo):
                            f[campo] = c[campo]
                    break
        for n in d["nuevos"]:
            ficha = {"slug": n["slug"], "nombre": n["nombre"], "categoria": n["categoria"],
                     "calle": n["calle"], "cp": n["cp"], "telefono": n["telefono"],
                     "web": n["web"], "horario": n["horario"], "lat": n["lat"], "lon": n["lon"],
                     "fuente": "google_places", "destacado": False, "rasgos": [], "fotos": []}
            if ficha not in fichas:
                fichas.append(ficha)
        path.write_text(json.dumps(fichas, ensure_ascii=False, indent=2))
        print(f"  comercios.json {guia}: {len(d['rellenados'])} rellenados, {len(d['nuevos'])} nuevos escritos")
    print("ESCRITO. Rebuild + deploy para publicar los horarios en las webs.")

if __name__ == "__main__":
    main()