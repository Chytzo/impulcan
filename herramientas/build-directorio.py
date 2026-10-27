#!/usr/bin/env python3
"""
Consolida el directorio de los 4 barrios en una base de datos única y completa.

Fuentes (sin fotos — derechos de autor):
  1. guias.db        — fichas ya enriquecidas (nombre, cat, dir, tel, web, email,
                       horario, lat/lon) + el trabajo comercial (email).
  2. osm_catalogo.json — catálogo TOTAL de OpenStreetMap del barrio (negocios que
                       aún no tenemos).

Merge: match por nombre normalizado + distancia (<150 m). Si coincide, completa
campos vacíos desde OSM; si no, añade el negocio nuevo. Exporta:
  datos/directorio.db  (SQLite)
  datos/directorio.csv
  datos/directorio.json
Uso:
  python3 build-directorio.py
"""
import csv, json, math, re, sqlite3
from pathlib import Path

RAIZ = Path.home() / "Proyectos"
BD = RAIZ / "impulcan" / "datos" / "guias.db"
OSM = RAIZ / "impulcan" / "datos" / "osm_catalogo.json"
OUT = RAIZ / "impulcan" / "datos"

ACC = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
def norm(s):
    s = (s or "").lower().translate(ACC)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    # quita artículos iniciales y sufijos societarios que rompen el match
    s = re.sub(r"^(el|la|los|las) ", "", s)
    s = re.sub(r"(,?\s*(s\.l\.|s\.l|sl|c\.b\.|cb|scp|s\.c\.p\.))$", "", s)
    return re.sub(r"\s+", " ", s).strip()

def sim(a, b):
    """Jaccard de tokens entre dos nombres normalizados."""
    if not a or not b: return 0.0
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb: return 0.0
    return len(ta & tb) / len(ta | tb)

def slugify(s):
    s = (s or "").lower().translate(ACC)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "sin-nombre"

def dist_m(a, b):
    if not a or not b: return 1e9
    R=6371000; p1,p2=math.radians(a[0]),math.radians(b[0])
    dp=p2-p1; dl=math.radians(b[1]-a[1])
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))

# OSM categoria -> categoria de la red
OSM2CAT = [
    (["restaurant","food","fast_food","cafe","bar","pub","ice_cream","bistro"], "Restaurantes"),
    (["supermarket","convenience","greengrocer","butcher","bakery","deli","fishmonger","food"], "Alimentación"),
    (["beauty","hairdresser","hairdresser,","cosmetics","tattoo","nails","sunbed"], "Belleza"),
    (["clothes","shoes","fashion","jewelry","bag","textile","boutique"], "Moda"),
    (["electronics","computer","mobile_phone","hifi","electric"], "Electrónica"),
    (["furniture","houseware","hardware","doityourself","home","garden_centre","paint"], "Hogar y reformas"),
    (["pet","veterinary"], "Mascotas"),
    (["car","motorcycle","auto","tyres","fuel","car_repair"], "Motor"),
    (["sport","gym","fitness","bicycle","outdoor","swimming"], "Deporte y ocio"),
    (["pharmacy","chemist","optician","dentist","doctor","hearing","medical"], "Salud"),
    (["tobacco","newsagent","kiosk","lottery","gift","stationery","book","florist","laundry","dry_cleaning"], "Servicios"),
    (["shop","store","mall","general","second_hand","variety"], "Bazares"),
]

def cat_red(cat):
    c = (cat or "").lower()
    for keys, red in OSM2CAT:
        if any(k in c for k in keys):
            return red
    if "amenity" in c or "office" in c or "craft" in c or "leisure" in c or "tourism" in c:
        return "Servicios"
    return "Servicios"

def main():
    con = sqlite3.connect(BD); con.row_factory = sqlite3.Row
    existentes = [dict(r) for r in con.execute("SELECT * FROM comercios")]
    for e in existentes:
        e["_norm"] = norm(e["nombre"])
        e["_pos"] = (e["lat"], e["lon"]) if e["lat"] and e["lon"] else None

    osm = json.loads(OSM.read_text()) if OSM.exists() else {}
    osm_items = [(g, n) for g, ns in osm.items() for n in ns]

    master = []
    slugs_red = set()
    matched = 0
    nuevos = 0

    def push(guia, nombre, cat, calle, cp, tel, web, horario, email, lat, lon, fuente, slug=None):
        nonlocal master, slugs_red
        s = slug or slugify(nombre)
        base = s
        i = 2
        while s in slugs_red:
            s = f"{base}-{i}"; i += 1
        slugs_red.add(s)
        master.append({"guia": guia, "slug": s, "nombre": nombre, "categoria": cat,
                       "calle": calle, "cp": cp, "telefono": tel, "web": web,
                       "horario": horario, "email": email, "lat": lat, "lon": lon,
                       "fuente": fuente})

    # 1) fichas existentes
    for e in existentes:
        push(e["guia"], e["nombre"], e["categoria"] or "Servicios", e["calle"] or "",
             e["cp"] or "", e["telefono"], e["web"], e["horario"], e["email"],
             e["lat"], e["lon"], e.get("fuente") or "guia", slug=e["slug"])

    # 2) OSM -> rellena o añade
    for guia, n in osm_items:
        calle = (n.get("calle") or "") + (f", {n['housenumber']}" if n.get("housenumber") else "")
        best = None
        nn = norm(n["nombre"])
        for e in existentes:
            if e["guia"] != guia:
                continue
            if not e["_pos"] or not n.get("lat"):
                continue
            if dist_m((n["lat"], n["lon"]), e["_pos"]) > 120:
                continue
            s = sim(nn, e["_norm"])
            if s >= 0.6 or (nn and (nn in e["_norm"] or e["_norm"] in nn)):
                best = e; break
        if best:
            matched += 1
            m = next((x for x in master if x["slug"] == best["slug"]), None)
            if not m: continue
            for campo, val in (("telefono", n.get("telefono")), ("web", n.get("web")),
                               ("horario", n.get("horario")), ("cp", n.get("cp"))):
                if val and not m[campo]:
                    m[campo] = val
            continue
        nuevos += 1
        push(guia, n["nombre"], cat_red(n.get("categoria_osm")), calle, n.get("cp") or "",
             n.get("telefono"), n.get("web"), n.get("horario"), "", n.get("lat"), n.get("lon"), "osm")

    # 3) export
    OUT.mkdir(parents=True, exist_ok=True)
    dbp = OUT / "directorio.db"
    c = sqlite3.connect(dbp)
    c.execute("DROP TABLE IF EXISTS negocios")
    c.execute("""CREATE TABLE negocios(
        guia TEXT, slug TEXT, nombre TEXT, categoria TEXT, calle TEXT, cp TEXT,
        telefono TEXT, web TEXT, horario TEXT, email TEXT, lat REAL, lon REAL, fuente TEXT)""")
    c.executemany("INSERT INTO negocios VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  list([tuple(m[k] for k in ("guia","slug","nombre","categoria","calle","cp","telefono",
                                             "web","horario","email","lat","lon","fuente")) for m in master]))
    c.commit()
    with open(OUT / "directorio.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(master[0].keys()))
        w.writeheader(); w.writerows(master)
    (OUT / "directorio.json").write_text(json.dumps(master, ensure_ascii=False, indent=2))

    print(f"MASTER: {len(master)} negocios | {matched} matcheados OSM->ficha | {nuevos} nuevos de OSM")
    print(f"con telefono: {sum(1 for m in master if m['telefono'])} | con web: {sum(1 for m in master if m['web'])}")
    print(f"con horario: {sum(1 for m in master if m['horario'])} | con email: {sum(1 for m in master if m['email'])}")
    print(f"sin contacto: {sum(1 for m in master if not (m['telefono'] or m['email'] or m['web']))}")
    print("con fotos: 0 (excluidas por copyright)")
    print(f"-> {dbp}, {OUT/'directorio.csv'}, {OUT/'directorio.json'}")

if __name__ == "__main__":
    main()