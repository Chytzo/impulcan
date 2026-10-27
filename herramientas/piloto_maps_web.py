#!/usr/bin/env python3
"""
Piloto: extrae web (+telefono) de comercios SIN web desde Google Maps vía CDP.
Mide rendimiento para decidir si se escala a toda la base.
Uso: python3 piloto_maps_web.py [--lote N] [--resume]
"""
from pathlib import Path
import json, random, re, sqlite3, sys, time, urllib.parse, urllib.request
import websocket

RAIZ = str(Path.home() / "Proyectos")
BD = f"{RAIZ}/impulcan/datos/guias.db"
CP = "/tmp/piloto-maps-checkpoint.json"

BARRIOS = ["alcaravaneras", "guanarteme", "laisleta", "santacatalina"]

def new_tab(url):
    req = urllib.request.Request("http://127.0.0.1:9222/json/new?" + urllib.parse.quote(url), method="PUT")
    return json.loads(urllib.request.urlopen(req).read())

def connect(tab):
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30)
    ws.settimeout(15)
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
    cmd("Page.navigate", {"url": url})
    t0 = time.time()
    while time.time() - t0 < 20:
        time.sleep(2)
        title = ev(ws, cmd, "document.title") or ""
        if "Google Maps" in title and "Antes de ir" not in title:
            break
    time.sleep(random.uniform(2.0, 3.5))
    raw = ev(ws, cmd, EXTRACT)
    if not raw:
        return None, None
    try:
        m = json.loads(raw)
    except Exception:
        return None, None
    if "Antes de ir a Google" in (m.get("title") or ""):
        return "BLOCKED", None
    return m, None

def main():
    lote = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    con = sqlite3.connect(BD); con.row_factory = sqlite3.Row
    cp = json.load(open(CP)) if __import__("os").path.exists(CP) else {}
    tab = new_tab("https://www.google.com/maps")
    ws, cmd = connect(tab)
    time.sleep(5)
    # aceptar consentimiento
    ev(ws, cmd, """(()=>{const b=[...document.querySelectorAll('button')].find(x=>/Aceptar todo|Accept all/i.test(x.innerText||''));if(b){b.click();return 'ok';}return 'no';})()""")
    time.sleep(2)

    rows = con.execute(
        "SELECT guia, slug, nombre, calle, web FROM comercios "
        "WHERE (web IS NULL OR web='') ORDER BY guia, slug").fetchall()
    pend = [r for r in rows if r["slug"] not in cp.get(r["guia"], {})][:lote]
    print(f"comercios SIN web en base: {len(rows)} | lote a probar: {len(pend)}")

    con_web = 0; sin = 0; blocked = 0; err = 0; t0 = time.time()
    for r in pend:
        try:
            m, _ = busca_maps(ws, cmd, r["nombre"], r["calle"] or "")
            if m == "BLOCKED":
                blocked += 1
                print(f"  [BLOCKED] {r['nombre']} ({r['guia']})")
                cp.setdefault(r["guia"], {})[r["slug"]] = "blocked"
            elif not m or (not m.get("web") and not m.get("tel")):
                sin += 1
                cp.setdefault(r["guia"], {})[r["slug"]] = "sin"
            else:
                info = "web=" + (m["web"] or "-") + " tel=" + (m["tel"] or "-")
                con_web += 1
                print(f"  [+] {r['nombre']} ({r['guia']}) | {info[:90]}")
                cp.setdefault(r["guia"], {})[r["slug"]] = m
            # guardar cada 5
            if (con_web + sin + blocked + err) % 5 == 0:
                json.dump(cp, open(CP, "w"))
            time.sleep(random.uniform(1.5, 3.0))
        except Exception as e:
            err += 1
            print(f"  [ERR] {r['nombre']}: {type(e).__name__}")
            time.sleep(3)
    json.dump(cp, open(CP, "w"))
    dt = time.time() - t0
    print(f"\nRESULTADO ({dt:.0f}s): con web/tel={con_web} sin={sin} blocked={blocked} err={err} "
          f"| {(con_web+sin+blocked+err)/dt:.2f} fichas/s")
    ws.close()

if __name__ == "__main__":
    main()
