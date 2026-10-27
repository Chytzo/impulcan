#!/usr/bin/env python3
"""
Validación de un sector por Google Maps (gratis, CDP headless local).

Para cada ficha del sector [categoria] de la guía [guia], busca el negocio en
Google Maps por nombre+calle, extrae tel/web/dirección si aparecen y clasifica:

  EXISTE          -> Maps devuelve el negocio con teléfono o web
  EXISTE_SIN_CTO  -> Maps lo muestra (nombre/h1) pero sin tel ni web: viable, verificar a pie
  NO_ENCONTRADO   -> Maps no lo devuelve: candidato a cerrado/mudado, verificar a pie
  BLOCKED         -> reto captcha de Google

Escribe dos salidas en datos/validacion_<guia>_<sector>.csv:
  - informe completo (una fila por negocio con estado)
  - actualiza web/telefono en guias.db SOLO cuando la ficha los tenía vacíos

Uso:
  python3 validar-sector.py [guia] [categoria] [max]
    guia      default alcaravaneras
    categoria default Restaurantes
    max       limite de fichas esta corrida (default todas)

Checkpoint en /tmp/validar-sector-checkpoint.json para reanudar. Lento a propósito.
Requiere: Chrome headless CDP en 127.0.0.1:9222 (igual que extraer-maps-completo).
"""
from pathlib import Path
import json, os, random, re, sqlite3, sys, time, urllib.parse, urllib.request
import websocket

RAIZ = str(Path.home() / "Proyectos")
BD = f"{RAIZ}/impulcan/datos/guias.db"
CP_FILE = "/tmp/validar-sector-checkpoint.json"
CDP = "http://127.0.0.1:9222"

def cerrar_tab(tab):
    """Cierra la pestaña en Chrome para no acumular renderers entre sectores."""
    try:
        tid = tab.get("id")
        if tid:
            req = urllib.request.Request(f"{CDP}/json/close/{tid}", method="GET")
            urllib.request.urlopen(req, timeout=5).read()
    except Exception:
        pass

def new_tab(url):
    req = urllib.request.Request(CDP + "/json/new?" + urllib.parse.quote(url), method="PUT")
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def connect(tab):
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=40)
    ws.settimeout(20)
    mid = [0]
    def cmd(method, params=None):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == mid[0]:
                return r
    cmd("Page.enable"); cmd("Runtime.enable")
    return ws, cmd

def ev(ws, cmd, js):
    r = cmd("Runtime.evaluate", {"expression": js, "returnByValue": True})
    return r.get("result", {}).get("result", {}).get("value")

EXTRACT = """(() => {
  const q=(s)=>document.querySelector(s), clean=(t)=>(t||'').replace(/\\s+/g,' ').trim();
  const tel=q('a[href^="tel:"]');
  const web=q('a[data-item-id="authority"]');
  const dir=q('button[data-item-id="address"]');
  const nombre=q('h1');
  return JSON.stringify({tel: tel?tel.href.replace('tel:',''):'', web: web?web.href:'',
    dir: dir?clean(dir.innerText):'', nombre: nombre?clean(nombre.innerText):'',
    title: document.title.slice(0,80)});
})()"""

def aceptar_cookies(ws, cmd):
    ev(ws, cmd, """(()=>{const b=[...document.querySelectorAll('button')].find(x=>/Aceptar todo|Accept all/i.test(x.innerText||''));if(b){b.click();return 'ok';}return 'no';})()""")

def busca_maps(ws, cmd, nombre, calle):
    query = f"{nombre} {calle} Las Palmas de Gran Canaria"
    url = "https://www.google.com/maps/search/" + urllib.parse.quote(query)
    try:
        cmd("Page.navigate", {"url": url})
    except Exception:
        pass
    t0 = time.time()
    while time.time() - t0 < 20:
        time.sleep(2)
        title = ev(ws, cmd, "document.title") or ""
        if "Google Maps" in title and "Antes de ir" not in title:
            break
    time.sleep(random.uniform(2.0, 3.5))
    raw = ev(ws, cmd, EXTRACT)
    if not raw:
        return None
    try:
        m = json.loads(raw)
    except Exception:
        return None
    if "Antes de ir a Google" in (m.get("title") or ""):
        return "BLOCKED"
    return m

def clasificar(m, r):
    if m == "BLOCKED":
        return "BLOCKED"
    if not m:
        return "NO_ENCONTRADO"
    # nombre coincide (case-insensitive, tokens) -> al menos esta en Maps
    coinciden = r["nombre"].lower() and any(
        tok in (m.get("nombre") or "").lower() for tok in re.split(r"[^a-z0-9áéíóúñü]+", r["nombre"].lower()) if len(tok) >= 3)
    if m.get("tel") or m.get("web"):
        return "EXISTE"
    if coinciden or m.get("nombre"):
        return "EXISTE_SIN_CTO"
    return "NO_ENCONTRADO"

def crear_tabla(con):
    con.execute("""CREATE TABLE IF NOT EXISTS validaciones (
        guia TEXT, slug TEXT, categoria TEXT, estado TEXT,
        maps_tel TEXT, maps_web TEXT, maps_dir TEXT,
        updated_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (guia, slug))""")
    con.commit()

def upsert_validacion(con, guia, slug, cat, ent):
    con.execute("""INSERT INTO validaciones (guia, slug, categoria, estado, maps_tel, maps_web, maps_dir, updated_at)
                   VALUES (?,?,?,?,?,?,?,datetime('now'))
                   ON CONFLICT(guia, slug) DO UPDATE SET
                     categoria=excluded.categoria, estado=excluded.estado,
                     maps_tel=excluded.maps_tel, maps_web=excluded.maps_web,
                     maps_dir=excluded.maps_dir, updated_at=excluded.updated_at""",
                (guia, slug, cat, ent.get("estado"), ent.get("maps_tel"), ent.get("maps_web"), ent.get("maps_dir")))

def validar_sector(guia, cat, limite=0, con=None, cp=None, escribir_csv=True):
    sector_slug = re.sub(r"[^a-z0-9]+", "_", cat.lower()).strip("_")
    out_csv = f"{RAIZ}/impulcan/datos/validacion_{guia}_{sector_slug}.csv"

    if con is None:
        con = sqlite3.connect(BD); con.row_factory = sqlite3.Row
    crear_tabla(con)
    if cp is None:
        cp = json.load(open(CP_FILE)) if os.path.exists(CP_FILE) else {}
    key = f"{guia}/{cat}"

    rows = con.execute(
        "SELECT guia, slug, nombre, categoria, calle, cp, web, telefono FROM comercios "
        "WHERE guia=? AND categoria=? ORDER BY nombre", (guia, cat)).fetchall()
    pend = [r for r in rows if r["slug"] not in cp.get(key, {})]
    if limite:
        pend = pend[:limite]
    print(f"sector={cat} ({guia}): {len(rows)} fichas | a validar esta corrida: {len(pend)}", flush=True)
    if not pend:
        print("nada pendiente.")
        return

    tab = new_tab("https://www.google.com/maps")
    ws, cmd = connect(tab)
    time.sleep(5)
    aceptar_cookies(ws, cmd)
    time.sleep(2)

    t0 = time.time()
    res = {}
    for i, r in enumerate(pend, 1):
        try:
            m = busca_maps(ws, cmd, r["nombre"], r["calle"] or "")
            estado = clasificar(m, r)
            ent = {"estado": estado}
            if isinstance(m, dict):
                ent.update({"maps_tel": m.get("tel"), "maps_web": m.get("web"), "maps_dir": m.get("dir")})
            res[r["slug"]] = ent
            upsert_validacion(con, r["guia"], r["slug"], cat, ent)
            con.commit()
            # rellena web/telefono en la DB solo si la ficha los tiene vacíos
            upd = {}
            if isinstance(m, dict):
                if (not r["web"]) and m.get("web"):
                    upd["web"] = m["web"]
                if (not r["telefono"]) and m.get("tel"):
                    sig = re.sub(r"[^\d+]", "", m["tel"])
                    if sig:
                        upd["telefono"] = sig
            if upd:
                sets = ", ".join(f"{k}=?" for k in upd)
                con.execute(f"UPDATE comercios SET {sets} WHERE guia=? AND slug=?", (*upd.values(), r["guia"], r["slug"]))
                con.commit()
            print(f"  [{i}/{len(pend)}] {estado:14s} {r['nombre'][:38]}", flush=True)
            if i % 10 == 0:
                cp.setdefault(key, {}).update(res); json.dump(cp, open(CP_FILE, "w"))
            time.sleep(random.uniform(1.5, 3.0))
        except Exception as e:
            print(f"  [{i}] ERR {r['nombre'][:30]}: {type(e).__name__}", flush=True)
            time.sleep(3)

    cp.setdefault(key, {}).update(res); json.dump(cp, open(CP_FILE, "w"))

    # informe CSV (todas las fichas del sector, no solo esta corrida)
    existentes = {k: v["estado"] for k, v in cp.get(key, {}).items()}
    with open(out_csv, "w") as f:
        f.write("nombre;calle;estado;telefono;web\n")
        for r in rows:
            e = existentes.get(r["slug"], "PENDIENTE")
            f.write(f'{r["nombre"]};{r["calle"] or ""};{e};{r["telefono"] or ""};{r["web"] or ""}\n')

    dt = time.time() - t0
    from collections import Counter
    cc = Counter(res[s]["estado"] for s in res)
    print(f"\nRESULTADO {dt:.0f}s ({len(res)} fichas): " + " | ".join(f"{k}={v}" for k, v in cc.items()) + f" | {len(res)/max(dt,1):.2f} f/s", flush=True)
    print(f"Informe: {out_csv}", flush=True)
    try: ws.close()
    except Exception: pass
    cerrar_tab(tab)  # suelta la pestaña/renderer del sector: no acumular RAM

if __name__ == "__main__":
    guia = sys.argv[1] if len(sys.argv) > 1 else "alcaravaneras"
    cat = sys.argv[2] if len(sys.argv) > 2 else "Restaurantes"
    limite = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 0
    validar_sector(guia, cat, limite)
