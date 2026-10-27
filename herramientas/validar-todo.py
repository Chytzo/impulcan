#!/usr/bin/env python3
"""
Driver: valida TODOS los sectores de TODAS las guías vía Google Maps CDP,
persistiendo cada resultado en la tabla `validaciones` de guias.db y generando
un CSV por sector. Reanudable: salta sectores ya completos en el checkpoint.

Uso:
  python3 validar-todo.py [guia]     limita a una guía (opcional)
  --solo sector1,sector2            limita a sectores concretos (opcional)

Requiere Chrome headless CDP en 127.0.0.1:9222. Invoca validar-sector.py
por subproceso (cada sector abre su propia pestaña).
"""
from pathlib import Path
import json, os, sqlite3, subprocess, sys, time

RAIZ = str(Path.home() / "Proyectos")
BD = f"{RAIZ}/impulcan/datos/guias.db"
CP_FILE = "/tmp/validar-sector-checkpoint.json"
VENV = str(Path.home() / "Proyectos/cardmarket-ops/.venv/bin/python3")
SCRIPT = f"{RAIZ}/impulcan/herramientas/validar-sector.py"
CHROME = "/opt/google/chrome/chrome"
RECYCLE_THRESHOLD = 40  # sectores con >= esta cantidad de fichas reciclan Chrome antes

def chrome_up():
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3)
        return True
    except Exception:
        return False

def recycle_chrome():
    """Mata y relanza Chrome 9222 para soltar la RAM acumulada por Maps."""
    subprocess.run(["pkill", "-f", "remote-debugging-port=9222"], capture_output=True)
    time.sleep(2)
    args = [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--remote-debugging-port=9222", "--user-data-dir=/tmp/cdp-chrome",
            "--remote-allow-origins=*", "--noerrdialogs", "--no-first-run",
            "--ozone-platform=headless", "--ozone-override-screen-size=1200,900",
            "--use-angle=swiftshader-webgl", "about:blank"]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    t0 = time.time()
    while not chrome_up() and time.time() - t0 < 25:
        time.sleep(2)
    return chrome_up()

def main():
    solo_guia = None
    solo_cats = None
    for a in sys.argv[1:]:
        if a.startswith("--solo"):
            solo_cats = [x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()]
        elif solo_guia is None:
            solo_guia = a

    con = sqlite3.connect(BD); con.row_factory = sqlite3.Row
    cp = json.load(open(CP_FILE)) if os.path.exists(CP_FILE) else {}

    combos = con.execute(
        "SELECT guia, categoria, COUNT(*) n FROM comercios GROUP BY guia, categoria "
        "ORDER BY guia, categoria").fetchall()
    if solo_guia:
        combos = [c for c in combos if c["guia"] == solo_guia]
    if solo_cats:
        combos = [c for c in combos if c["categoria"] in solo_cats]

    print(f"PLAN: {len(combos)} sectores, {sum(c['n'] for c in combos)} fichas totales\n", flush=True)

    t_total = time.time()
    for c in combos:
        key = f"{c['guia']}/{c['categoria']}"
        ya = sum(1 for s in cp.get(key, {}).values() if isinstance(s, dict) and s.get("estado"))
        if ya >= c["n"]:
            print(f"[skip] {key} ya completo ({ya}/{c['n']})", flush=True)
            continue
        t0 = time.time()
        print(f">>> {key} ({c['n']} fichas, pend {c['n']-ya})", flush=True)
        if c["n"] >= RECYCLE_THRESHOLD:
            ok = recycle_chrome()
            print(f"  [reciclado Chrome 9222 antes del sector] {'ok' if ok else 'FALLO'}", flush=True)
        r = subprocess.run([VENV, SCRIPT, c["guia"], c["categoria"]], text=True, capture_output=True,
                           cwd=f"{RAIZ}/impulcan")
        sys.stdout.write(r.stdout)
        sys.stdout.flush()
        if r.returncode != 0:
            sys.stderr.write(r.stderr)
            print(f"  !! sector {key} exit={r.returncode}", flush=True)
        cp = json.load(open(CP_FILE)) if os.path.exists(CP_FILE) else {}
        print(f"  sector {key} en {time.time()-t0:.0f}s\n", flush=True)

    res = con.execute(
        "SELECT guia, estado, COUNT(*) n FROM validaciones GROUP BY guia, estado "
        "ORDER BY guia, estado").fetchall()
    print(f"\n== RESUMEN FINAL ({time.time()-t_total:.0f}s) ==", flush=True)
    from collections import defaultdict
    agg = defaultdict(lambda: defaultdict(int))
    for r in res:
        agg[r["guia"]][r["estado"]] = r["n"]
    for g in agg:
        print(f"  {g}: " + " | ".join(f"{k}={v}" for k, v in sorted(agg[g].items())), flush=True)
    tot = sum(v for d in agg.values() for v in d.values())
    print(f"  TOTAL validaciones en DB: {tot}", flush=True)
    con.close()

if __name__ == "__main__":
    main()
