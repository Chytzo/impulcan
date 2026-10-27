#!/usr/bin/env python3
"""
Rescate lento: re-consulta Maps para las fichas SIN datos (ni telefono ni web).

Por que lento: Google acaba de bloquear temporalmente; pacing 10-14s y variantes
de query cortas. Solo rellena campos VACIOS. Resumible por checkpoint.
Escribe en guias.db Y en src/data/comercios.json (fuente de las webs).
Uso:
  python3 extraer-maps-recovery.py [N]   N=max fichas esta corrida (default todas)
"""
import json, os, random, re, sqlite3, sys, time, urllib.parse, urllib.request, websocket
from pathlib import Path

RAIZ = Path.home() / "Proyectos"
BD = RAIZ / "impulcan" / "datos" / "guias.db"
CP_FILE = "/tmp/extraer-maps-recovery-checkpoint.json"

def new_tab(url):
    req = urllib.request.Request("http://127.0.0.1:9222/json/new?" + urllib.parse.quote(url), method="PUT")
    return json.loads(urllib.request.urlopen(req).read())

def connect(tab):
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=40)
    ws.settimeout(25)
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
  const nombre=q('h1');
  // evita resultados sueltos: exige que el panel sea de un negocio (h1 + al menos tel o web)
  return JSON.stringify({tel: tel?tel.href.replace('tel:','').trim():'', web: web?web.href.trim():'',
    nombre: nombre?clean(nombre.innerText):'', ok: !!(nombre && (tel || web))});
})()"""

def busca(ws, cmd, query):
    cmd("Page.navigate", {"url": "https://www.google.com/maps/search/" + urllib.parse.quote(query)})
    time.sleep(random.uniform(5.0, 6.5))
    return json.loads(ev(ws, cmd, EXTRACT) or "{}")

def main():
    maxn = int(sys.argv[1]) if len(sys.argv) > 1 else 99999
    con = sqlite3.connect(BD); con.row_factory = sqlite3.Row
    fichas = [dict(r) for r in con.execute(
        "SELECT guia,slug,nombre,calle,telefono,web FROM comercios "
        "WHERE (telefono IS NULL OR telefono='' OR telefono='000000000') "
        "AND (web IS NULL OR web='')")]
    cc = json.loads(open(CP_FILE).read()) if Path(CP_FILE).exists() else {}
    pendientes = [f for f in fichas if cc.get(f["guia"], {}).get(f["slug"]) is None]
    print(f"sin datos: {len(fichas)} | pendientes: {len(pendientes)}")

    tab = new_tab("about:blank")
    ws, cmd = connect(tab)
    ok = rellena = fallo = 0
    for f in pendientes[:maxn]:
        nombre, calle, guia, slug = f["nombre"], f["calle"], f["guia"], f["slug"]
        q1 = f"{nombre} {calle} Las Palmas de Gran Canaria"
        r = busca(ws, cmd, q1)
        if not r.get("ok") and len(nombre) > 4:
            time.sleep(random.uniform(4, 7))
            r = busca(ws, cmd, f"{nombre} Las Palmas")
        cc.setdefault(guia, {})[slug] = "hecho"
        if r.get("ok"):
            ok += 1
            cambios = {}
            if r.get("tel") and not f["telefono"]:
                cambios["telefono"] = r["tel"]
            if r.get("web") and not f["web"]:
                cambios["web"] = r["web"]
            if cambios:
                rellena += 1
                sets = ", ".join(f"{k}=?" for k in cambios)
                con.execute(f"UPDATE comercios SET {sets} WHERE guia=? AND slug=?",
                            (*cambios.values(), guia, slug))
                # espejo en comercios.json (fuente de las webs)
                jp = RAIZ / guia / "src" / "data" / "comercios.json"
                if jp.exists():
                    data = json.loads(jp.read_text())
                    for ficha in data:
                        if ficha.get("slug") == slug:
                            for k, v in cambios.items():
                                if not ficha.get(k):
                                    ficha[k] = v
                            break
                    jp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            fallo += 1
        if (ok + fallo) % 20 == 0:
            con.commit()
            open(CP_FILE, "w").write(json.dumps(cc))
            print(f"  ...{ok + fallo}/{len(pendientes[:maxn])} ok={ok} rellena={rellena}")
        time.sleep(random.uniform(10, 14))  # pacing anti-bloqueo
    con.commit()
    open(CP_FILE, "w").write(json.dumps(cc))
    print(f"DONE ok={ok} rellena={rellena} fallo={fallo}")

if __name__ == "__main__":
    main()