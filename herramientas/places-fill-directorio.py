#!/usr/bin/env python3
"""
Completa contactos/horarios de directorio.db desde Google Places (Text Search New).

Una llamada Text Search por negocio devuelve teléfono, web, horario y dirección
en un solo request (con Enterprise fields en el mask). Reutiliza la key guardada.

GUARD DE COSTE (duro): para no pasarse del presupuesto, para cuando el gasto
estimado alcanza max_cost. Estimación conservadora a $60/1k (Text Search con
campos Enterprise) — si la tarifa real es menor, procesa más por el mismo coste.

Uso:
  python3 places-fill-directorio.py [--max-cost 150] [--lote 500]
Escribe en datos/directorio.db (solo campos vacíos).
"""
import argparse, json, math, os, re, time, urllib.request, urllib.error
from pathlib import Path

RAIZ = Path.home() / "Proyectos"
KEY_FILE = Path.home() / ".config" / "impulcan" / "google-places.key"
DB = RAIZ / "impulcan" / "datos" / "directorio.db"
COST_PER_1K = 60.0   # estimación conservadora (USD) por 1k llamadas con campos Enterprise
BARRIO = {"alcaravaneras": "Alcaravaneras Las Palmas de Gran Canaria",
          "guanarteme": "Guanarteme Las Palmas de Gran Canaria",
          "santacatalina": "Santa Catalina Las Palmas de Gran Canaria",
          "laisleta": "La Isleta Las Palmas de Gran Canaria"}
MASK = ("places.id,places.displayName,places.formattedAddress,places.addressComponents,"
        "places.nationalPhoneNumber,places.websiteUri,places.currentOpeningHours,"
        "places.location,places.businessStatus,places.types,places.googleMapsUri")

def key():
    k = (KEY_FILE.read_text().strip() if KEY_FILE.exists() else "") or os.environ.get("GOOGLE_PLACES_KEY","")
    if not k: raise SystemExit("falta key")
    return k

def text_search(query, mask):
    req = urllib.request.Request(
        "https://places.googleapis.com/v1/places:searchText",
        data=json.dumps({"textQuery": query, "regionCode": "ES",
                         "pageSize": 5}).encode(),
        headers={"X-Goog-Api-Key": key(), "X-Goog-FieldMask": mask,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {e.read().decode()[:200]}")

def norm(s):
    s=(s or "").lower()
    for a,b in zip("áéíóúüñ", "aeiouun"): s=s.replace(a,b)
    return re.sub(r"[^a-z0-9 ]","",s).strip()

def sim(a,b):
    a,b=set(norm(a).split()),set(norm(b).split())
    return len(a&b)/len(a|b) if (a and b) else 0.0

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--max-cost", type=float, default=150.0)
    ap.add_argument("--lote", type=int, default=0); args=ap.parse_args()
    import sqlite3
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
    filas=[dict(r) for r in con.execute(
        "SELECT * FROM negocios WHERE (telefono IS NULL OR telefono='') "
        "AND fuente='osm' ORDER BY guia")]
    print(f"candidatos sin telefono: {len(filas)} | tope gasto: {args.max_cost}$")
    calls=0; gasto=0.0; ok=0; sinmatch=0; err=0; i=-1
    for i,f in enumerate(filas):
        if args.lote and i>=args.lote: break
        if gasto >= args.max_cost:
            print(f"  GUARD: gasto estimado {gasto:.0f}$ alcanzado en {i} procesados, paro.")
            break
        q = f"{f['nombre']}, {BARRIO.get(f['guia'], 'Las Palmas de Gran Canaria')}"
        if f.get("calle"): q = f"{f['nombre']}, {f['calle'].split(',')[0]}, {BARRIO.get(f['guia'])}"
        try:
            d = text_search(q, MASK)
        except RuntimeError as e:
            err+=1; time.sleep(1.5); continue
        calls+=1; gasto = calls*COST_PER_1K/1000.0
        places = d.get("places", [])
        if not places:
            sinmatch+=1; time.sleep(0.3); continue
        # elegir el mejor candidato por similitud de nombre
        cand = max(places, key=lambda p: sim(f["nombre"], (p.get("displayName") or {}).get("text","")))
        if sim(f["nombre"], (cand.get("displayName") or {}).get("text","")) < 0.4:
            sinmatch+=1; time.sleep(0.3); continue
        if cand.get("businessStatus") == "CLOSED_PERMANENTLY":
            sinmatch+=1; time.sleep(0.3); continue
        upd={}
        upd["telefono"]=cand.get("nationalPhoneNumber","")
        upd["web"]=cand.get("websiteUri","")
        ho=cand.get("currentOpeningHours") or {}
        ud=ho.get("weekdayDescriptions")
        upd["horario"]=("; ".join(ud) if ud else "")
        if cand.get("formattedAddress"):
            upd["calle"]=cand["formattedAddress"].split(",")[0].strip()
            m=re.search(r"(\d{5})", cand["formattedAddress"])
            upd["cp"]=m.group(1) if m else f.get("cp","")
        sets=", ".join(f"{k}=?" for k in upd if upd[k])
        if sets:
            vals=[upd[k] for k in upd if upd[k]]+[f["slug"]]
            con.execute(f"UPDATE negocios SET {sets} WHERE slug=?", vals)
            ok+=1
        time.sleep(0.25)
        if (i+1)%100==0:
            con.commit(); print(f"  ...{i+1} | ok={ok} sinmatch={sinmatch} err={err} gasto~{gasto:.0f}$")
    con.commit()
    print(f"DONE: {i+1} procesados | ok={ok} sinmatch={sinmatch} err={err} | calls={calls} | gasto_est~{gasto:.0f}$ (tope {args.max_cost}$)")

if __name__=="__main__":
    main()
