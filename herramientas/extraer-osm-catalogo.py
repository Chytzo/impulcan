#!/usr/bin/env python3
"""
Catálogo completo de negocios de los 4 barrios desde OpenStreetMap (Overpass).
Fuente abierta y legal — da el inventario TOTAL (nombres, categorías, direcciones,
teléfono/web/horario cuando OSM los tiene). Sin fotos (derechos de autor).

Barrios (bbox reales de guias.db, con padding):
  alcaravaneras  28.1260,-15.4370 | 28.1360,-15.4270
  guanarteme     28.1200,-15.4570 | 28.1390,-15.4340
  santacatalina  28.1340,-15.4390 | 28.1480,-15.4260
  laisleta       28.1450,-15.4340 | 28.1600,-15.4200

Guardas en datos/osm_catalogo.json (bruto) + salida resumen.
"""
import json, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

RAIZ = Path.home() / "Proyectos"
OUT_RAW = RAIZ / "impulcan" / "datos" / "osm_catalogo.json"

BARRIOS = {
    "alcaravaneras": (28.1260, -15.4370, 28.1360, -15.4270),
    "guanarteme": (28.1200, -15.4570, 28.1390, -15.4340),
    "santacatalina": (28.1340, -15.4390, 28.1480, -15.4260),
    "laisleta": (28.1450, -15.4340, 28.1600, -15.4200),
}

# claves POI de negocio (sin 'garden' suelto ni parques residenciales)
KEYS = "shop|amenity|office|craft|leisure|healthcare|tourism|club"
# filtrar amenity no-comercial
FILTRO_AMENITY = {"parking","bench","waste_basket","drinking_water","toilets","fountain",
    "recycling","bench","telephone","post_box","bicycle_parking","street_light","bus_station",
    "public_building","shelter","vending_machine","kindergarten","school","university",
    "college","library","place_of_worship","fuel_car","charging_station"}

def query_overpass(bbox, intentos=3):
    lo,wn,hi,en = bbox
    q = f"""[out:json][timeout:60];
(
  nwr[shop]({lo},{wn},{hi},{en});
  nwr[amenity]({lo},{wn},{hi},{en});
  nwr[office]({lo},{wn},{hi},{en});
  nwr[craft]({lo},{wn},{hi},{en});
  nwr[leisure]({lo},{wn},{hi},{en});
  nwr[healthcare]({lo},{wn},{hi},{en});
  nwr[tourism]({lo},{wn},{hi},{en});
  nwr[club]({lo},{wn},{hi},{en});
);
out center tags;"""
    endpoints = ["https://overpass-api.de/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter",
                 "https://lz4.overpass-api.de/api/interpreter"]
    for ep in endpoints:
        for i in range(intentos):
            req = urllib.request.Request(
                ep,
                data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded",
                         "User-Agent": "impulcan-catalog/1.0 (business directory enrich)"})
            try:
                with urllib.request.urlopen(req, timeout=100) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                print(f"    {ep.split('/')[2]} HTTP {e.code}, intento {i+1}, espero...")
                time.sleep(15 + 10 * i)
            except Exception as e:
                print(f"    {ep.split('/')[2]} err {e}, intento {i+1}")
                time.sleep(10)
    return {"elements": []}

def conv_hora(h):
    """opening_hours OSM -> string compacto (passthrough legible)."""
    return h if h else ""

def main():
    catalogo = json.loads(OUT_RAW.read_text()) if OUT_RAW.exists() else {}
    for guia, bbox in BARRIOS.items():
        if guia in catalogo and catalogo[guia]:
            print(f"{guia}: ya en catálogo ({len(catalogo[guia])}), skip")
            continue
        d = query_overpass(bbox)
        els = d.get("elements", [])
        negocios = []
        for e in els:
            t = e.get("tags", {})
            cat = (t.get("shop") or t.get("amenity") or t.get("office") or
                   t.get("craft") or t.get("leisure") or t.get("healthcare") or t.get("tourism"))
            if not cat or (t.get("amenity") in FILTRO_AMENITY):
                continue
            if not t.get("name"):
                continue
            lat = t.get("lat") or (e.get("center") or {}).get("lat")
            lon = t.get("lon") or (e.get("center") or {}).get("lon")
            negocios.append({
                "osm_id": f"{e.get('type')}/{e.get('id')}",
                "nombre": t.get("name"),
                "categoria_osm": cat,
                "categoria_extra": t.get("shop") or t.get("craft"),
                "calle": t.get("addr:street",""),
                "housenumber": t.get("addr:housenumber",""),
                "cp": t.get("addr:postcode",""),
                "telefono": t.get("phone") or t.get("contact:phone",""),
                "web": t.get("website") or t.get("contact:website") or t.get("url",""),
                "horario": conv_hora(t.get("opening_hours")),
                "lat": lat, "lon": lon,
                "fuente": "osm",
            })
        catalogo[guia] = negocios
        con_cat = sum(1 for n in negocios if n["calle"])
        con_tel = sum(1 for n in negocios if n["telefono"])
        con_web = sum(1 for n in negocios if n["web"])
        print(f"{guia}: {len(negocios)} negocios | con calle {con_cat} | tel {con_tel} | web {con_web}")
        time.sleep(2)
    OUT_RAW.write_text(json.dumps(catalogo, ensure_ascii=False, indent=2))
    tot = sum(len(v) for v in catalogo.values())
    print(f"\nTOTAL catálogo OSM 4 barrios: {tot} negocios -> {OUT_RAW}")

if __name__ == "__main__":
    main()