#!/usr/bin/env python3
"""
Mejora del catálogo: `horario` texto -> `horarioSchema` (OpeningHours schema.org,
["Mo-Fr 07:00-21:00"]) para que el JSON-LD emita `openingHours`.

Acepta formatos: por día ("Monday: 9:00 AM–1:45 AM"), rango de días
("lunes-domingo 09:00-23:00"), día solo ("lunes 09:00-14:00"), 24h y 12h AM/PM,
con espacios unicode. Días consecutivos con igual horario se agrupan.
Uso: python3 horario-schema.py [--dry-run]
"""
import argparse, json, re, unicodedata
from pathlib import Path

RAIZ = Path.home() / "Proyectos"
REPO = {"alcaravaneras": "zonaalcaravaneras", "guanarteme": "zonaguanarteme",
        "santacatalina": "zonasantacatalina", "laisleta": "zonalaisleta"}

NOM = [
  ("mo","Mo"),("tu","Tu"),("we","We"),("th","Th"),("fr","Fr"),("sa","Sa"),("su","Su"),
]
NOM_RE = {
  "Mo": r"lunes|monday|mon", "Tu": r"martes|tuesday|tues",
  "We": r"mi[eé]rcoles|wednesday|wed", "Th": r"jueves|thursday|thu(rs)?",
  "Fr": r"viernes|friday|fri", "Sa": r"s[aá]bado|saturday|sat", "Su": r"domingo|sunday|sun",
}
ORD = ["Mo","Tu","We","Th","Fr","Sa","Su"]

def limpia(t):
    return unicodedata.normalize("NFKC", t or "").strip()

def to24(mm):
    mm = mm.replace("：",":").replace("–","-").replace("\u2009"," ").replace("\u202f"," ").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})\s*(AM|PM)?\s*$", mm, re.I)
    if not m: return None
    h, mn, ap = int(m.group(1)), m.group(2), (m.group(3) or "").upper()
    if ap:
        if ap=="PM" and h!=12: h+=12
        if ap=="AM" and h==12: h=0
    return f"{h:02d}:{mn}"

def dia_por_txt(t):
    for code, pat in NOM_RE.items():
        if re.fullmatch(pat, t, re.I): return code
    return None

def expande(dias_str, by_code):
    # "Mo-Fr" -> lista
    m = re.match(r"^([A-Za-z]+)\s*[-–]\s*([A-Za-z]+)$", dias_str)
    if m:
        a, b = dia_por_txt(m.group(1)), dia_por_txt(m.group(2))
        if a and b and ORD.index(a) <= ORD.index(b):
            return [ORD[i] for i in range(ORD.index(a), ORD.index(b)+1)]
    c = dia_por_txt(dias_str)
    return [c] if c else []

def parse(horario):
    if not horario: return None
    by_code = {}
    for parte in re.split(r"[;\n]", limpia(horario)):
        parte = parte.strip()
        if not parte: continue
        m = re.match(r"^([A-Za-záéíóúáéíóúÁÉÍÓÚ]+\s*[-–]?\s*[A-Za-záéíóúÁÉÍÓÚ]*)\s*[:\-–]\s*(.+)$", parte)
        if not m:
            m = re.match(r"^([A-Za-záéíóúÁÉÍÓÚ]+)\s+(.+)$", parte)
        if not m: continue
        dias_str, rango = m.group(1).strip(), m.group(2).strip()
        if re.search(r"closed|cerrado", rango, re.I):
            for c in (expande(dias_str, None) or []):
                by_code[c] = None
            continue
        rangel = re.sub("–","-", rango).lower()
        if re.search(r"24\s*hours|24h|todo el d[ií]a|abierto 24", rangel):
            for c in (expande(dias_str,None) or []): by_code[c]="00:00-23:59"
            continue
        # horas
        iv = re.findall(r"(\d{1,2}):(\d{2})\s*(am|pm)?\s*[-–]\s*(\d{1,2}):(\d{2})\s*(am|pm)?", rango, re.I)
        if not iv: continue
        h1 = to24(f"{iv[0][0]}:{iv[0][1]} {iv[0][2]}")
        h2 = to24(f"{iv[0][3]}:{iv[0][4]} {iv[0][5]}")
        if not h1 or not h2: continue
        codes = expande(dias_str, None)
        if not codes: 
            c = dia_por_txt(dias_str.strip().split()[-1] if dias_str else "")
            codes = [c] if c else []
        for c in codes: by_code[c] = f"{h1}-{h2}"
    if not by_code: return None
    # agrupar días consecutivos iguales
    grupos = []
    i = 0
    while i < 7:
        c = ORD[i]
        if c not in by_code:
            i += 1; continue
        h = by_code[c]
        if h is None:
            i += 1; continue
        j = i
        while j+1 < 7 and ORD[j+1] in by_code and by_code[ORD[j+1]] == h:
            j += 1
        grupos.append((f"{ORD[i]}-{ORD[j]} {h}" if j > i else f"{ORD[i]} {h}"))
        i = j+1
    return grupos

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); args = ap.parse_args()
    total = 0
    for guia, repo in REPO.items():
        p = RAIZ / repo / "src" / "data" / "comercios.json"
        fichas = json.loads(p.read_text())
        n = 0
        for f in fichas:
            if not f.get("horario") or f.get("horarioSchema"):
                continue
            g = parse(f["horario"])
            if g:
                f["horarioSchema"] = g; n += 1
        print(f"{repo}: +{n} con horarioSchema")
        total += n
        if not args.dry_run:
            p.write_text(json.dumps(fichas, ensure_ascii=False, indent=2))
    print(f"TOTAL: {total} fichas con horarioSchema generado")
    if args.dry_run: print("DRY-RUN")

if __name__ == "__main__":
    main()