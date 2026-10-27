#!/usr/bin/env python3
"""
Extracción completa: de Google Maps a la base — rellena `web` y `telefono`
de los comercios sin esos datos, y guarda el resultado en guias.db.

Cadena: Maps -> web -> (despues) extraer-emails de cada web nueva.

Uso:
  python3 extraer-maps-completo.py [N]      N = max fichas esta corrida (default todas)
  --resume no hace falta: usa checkpoint /tmp/extraer-maps-checkpoint.json
Escribe en guias.db (UPDATE comercios SET web/telefono WHERE vacio), respeta
checkpoint para reanudar tras interrupciones.
"""
from pathlib import Path
import json, os, random, re, sqlite3, sys, time, urllib.parse, urllib.request
import websocket

RAIZ = str(Path.home() / "Proyectos")
BD = f"{RAIZ}/impulcan/datos/guias.db"
CP_FILE = "/tmp/extraer-maps-checkpoint.json"

BARRIOS = ["alcaravaneras", "guanarteme", "laisleta", "santacatalina"]

def new_tab(url):
    req = urllib.request.Request("http://127.0.0.1:9222/json/new?" + urllib.parse.quote(url), method="PUT")
    return json.loads(urllib.request.urlopen(req).read())

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

def main():
    lote = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 0
    con = sqlite3.connect(BD); con.row_factory = sqlite3.Row
    cp = json.load(open(CP_FILE)) if os.path.exists(CP_FILE) else {}

    tab = new_tab("https://www.google.com/maps")
    ws, cmd = connect(tab)
    time.sleep(5)
    ev(ws, cmd, """(()=>{const b=[...document.querySelectorAll('button')].find(x=>/Aceptar todo|Accept all/i.test(x.innerText||''));if(b){b.click();return 'ok';}return 'no';})()""")
    time.sleep(2)

    total = con.execute("SELECT COUNT(*) n FROM comercios WHERE (web IS NULL OR web='') AND (telefono IS NULL OR telefono='')").fetchone()["n"]
    rows = con.execute(
        "SELECT guia, slug, nombre, calle, web, telefono FROM comercios "
        "WHERE (web IS NULL OR web='') AND (telefono IS NULL OR telefono='') "
        "ORDER BY guia, slug").fetchall()
    pend = [r for r in rows if r["slug"] not in cp.get(r["guia"], {})]
    if lote:
        pend = pend[:lote]
    print(f"sin web Y sin telefono: {total} | a procesar esta corrida: {len(pend)}", flush=True)

    ok=0; solo_tel=0; sin=0; blocked=0; err=0
    t0=time.time()
    for i, r in enumerate(pend, 1):
        try:
            m = busca_maps(ws, cmd, r["nombre"], r["calle"] or "")
            if m == "BLOCKED":
                blocked += 1
                cp.setdefault(r["guia"], {})[r["slug"]] = "blocked"
            elif not m or (not m.get("web") and not m.get("tel")):
                sin += 1
                cp.setdefault(r["guia"], {})[r["slug"]] = "sin"
            else:
                upd = {}
                if not r["web"] and m.get("web"):
                    upd["web"] = m["web"]
                if not r["telefono"] and m.get("tel"):
                    upd["telefono"] = m["tel"]
                if upd:
                    sets = ", ".join(f"{k}=?" for k in upd)
                    con.execute(f"UPDATE comercios SET {sets} WHERE guia=? AND slug=?",
                                (*upd.values(), r["guia"], r["slug"]))
                    con.commit()
                if upd.get("web"):
                    ok += 1
                elif upd:
                    solo_tel += 1
                cp.setdefault(r["guia"], {})[r["slug"]] = upd or "sin"
                print(f"  [{i}] {r['nombre']} ({r['guia']}) web={'+' if upd.get('web') else '-'} tel={'+' if upd.get('telefono') else '-'}", flush=True)
            if i % 10 == 0:
                json.dump(cp, open(CP_FILE, "w"))
            time.sleep(random.uniform(1.2, 2.5))
        except Exception as e:
            err += 1
            print(f"  [{i}] ERR {r['nombre']}: {type(e).__name__}", flush=True)
            time.sleep(3)
    json.dump(cp, open(CP_FILE, "w"))
    dt = time.time()-t0
    print(f"\nRESULTADO {dt:.0f}s: con web={ok} solo_tel={solo_tel} sin={sin} blocked={blocked} err={err} | {len(pend)/max(dt,1):.2f} f/s", flush=True)
    try: ws.close()
    except Exception: pass

if __name__ == "__main__":
    main()
