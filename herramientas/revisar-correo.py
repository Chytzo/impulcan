#!/usr/bin/env python3
"""Revisa el correo nuevo de la cuenta `impulcan` y lo deja clasificado para que un agente razone.

No envía nada, no marca nada como leído, no borra. Solo lee y separa:
  - humano   : respuestas de comercios, proveedores, personas
  - rebote    : Delivery Status Notification / mailer-daemon (dirección inválida)
  - boletin   : newsletters (List-Unsubscribe o Auto-Submitted distinto de 'no')

Estado en datos/correo-estado.json:
  processed : ids ya alertados (no se vuelven a reportar)
  pending   : ids reportados en la última pasada y aún sin confirmar

Flujo de dos fases, para no perder correo si el agente falla a mitad:
  1) `revisar-correo.py`            → imprime lo nuevo y lo deja en `pending`
  2) `revisar-correo.py --commit`   → pasa `pending` a `processed`

Uso:
  revisar-correo.py [--lookback-days N] [--max N] [--resumen] [--commit] [--todo]
    --resumen  salida mínima (una línea por correo humano/rebote) para el monitor de cambios
    --todo     incluye también boletines y ya procesados (para inspección manual)
"""
import argparse
import base64
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "google-accounts"))
import gmail_account as ga  # noqa: E402

ALIAS = "impulcan"
BASE = Path.home() / "Proyectos" / "impulcan"
ESTADO = BASE / "datos" / "correo-estado.json"
VOLCADOS = BASE / "datos" / "correo"
MAX_PROCESADOS = 800
LIMITE_CUERPO = 1600

RUIDO_DOMINIOS = (
    "news.opencode.ai", "gmgn.ai", "kilocode.ai", "email.grok.com", "noreply-accounts@google.com",
    "no-reply@accounts.google.com", "soporte.mcdonalds", "mc donald", "infojobs.net", "linkedin.com",
    "updates@", "newsletter", "news@", "no-reply@", "noreply@",
)


def cargar_estado() -> dict:
    if ESTADO.exists():
        try:
            d = json.loads(ESTADO.read_text())
            d.setdefault("processed", [])
            d.setdefault("pending", [])
            return d
        except Exception:
            pass
    return {"processed": [], "pending": [], "created_at": datetime.now(timezone.utc).isoformat()}


def guardar_estado(d: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    d["processed"] = d["processed"][-MAX_PROCESADOS:]
    d["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    tmp.replace(ESTADO)


def texto_de(part, salida: list) -> None:
    if part.get("parts"):
        for p in part["parts"]:
            texto_de(p, salida)
        return
    mime = part.get("mimeType", "")
    datos = part.get("body", {}).get("data")
    if datos and mime == "text/plain":
        salida.insert(0, base64.urlsafe_b64decode(datos).decode("utf-8", "replace"))
    elif datos and mime == "text/html" and not salida:
        html = base64.urlsafe_b64decode(datos).decode("utf-8", "replace")
        html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
        html = re.sub(r"(?s)<[^>]+>", " ", html)
        salida.append(re.sub(r"[ \t]+", " ", html))


def limpiar_cuerpo(t: str) -> str:
    lineas = []
    for ln in t.splitlines():
        s = ln.strip()
        if s.startswith(">"):
            continue
        if re.match(r"(?i)^(el .*escribió:|on .*wrote:|de: .*enviado:)", s):
            break
        if "aviso legal" in s.lower() or "este correo y sus archivos" in s.lower():
            continue
        lineas.append(s)
    txt = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
    return txt[:LIMITE_CUERPO]


def clasificar(from_: str, asunto: str, headers: dict) -> str:
    f, a = from_.lower(), (asunto or "").lower()
    if "mailer-daemon" in f or "postmaster" in f or "delivery status notification" in a or "undelivered" in a:
        return "rebote"
    if headers.get("list-unsubscribe") or (headers.get("auto-submitted", "no").lower() not in ("no", "")):
        return "boletin"
    if any(r in f for r in RUIDO_DOMINIOS):
        return "boletin"
    return "humano"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback-days", type=int, default=7)
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--resumen", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--todo", action="store_true")
    args = ap.parse_args()

    estado = cargar_estado()

    if args.commit:
        nuevos = set(estado.get("pending", []))
        estado["processed"] = list(dict.fromkeys(estado["processed"] + list(nuevos)))
        estado["pending"] = []
        guardar_estado(estado)
        print(f"commit: {len(nuevos)} correos marcados como procesados "
              f"(total {len(estado['processed'])}).")
        return 0

    query = f"in:inbox -in:chats newer_than:{args.lookback_days}d"
    svc = ga._gmail(ALIAS)
    res = svc.users().messages().list(userId="me", q=query, maxResults=args.max).execute()
    ids = [m["id"] for m in res.get("messages", [])]
    vistos = set(estado["processed"])
    if not args.todo:
        ids = [i for i in ids if i not in vistos]

    salida = []
    for mid in ids:
        full = svc.users().messages().get(userId="me", id=mid, format="full").execute()
        # Gmail devuelve el nombre de cabecera tal cual lo escribió el emisor: comparar sin caja
        hdrs = {h["name"].lower(): h["value"] for h in full.get("payload", {}).get("headers", [])}
        from_ = hdrs.get("from", "")
        asunto = hdrs.get("subject", "")
        tipo = clasificar(from_, asunto, hdrs)
        trozos: list = []
        texto_de(full.get("payload", {}), trozos)
        cuerpo = limpiar_cuerpo("\n".join(trozos)) if trozos else full.get("snippet", "")
        ts = int(full.get("internalDate") or 0) / 1000
        entrada = {
            "id": mid,
            "threadId": full.get("threadId"),
            "fecha": datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat(timespec="minutes") if ts else "",
            "de": from_,
            "para": hdrs.get("to", ""),
            "asunto": asunto,
            "tipo": tipo,
            "cuerpo": cuerpo,
        }
        if tipo == "rebote":
            m = re.search(r"Final-Recipient:\s*rfc822;\s*(\S+)", cuerpo)
            if m:
                entrada["direccion_rebotada"] = m.group(1)
        salida.append(entrada)

    salida.sort(key=lambda m: m["fecha"])

    if not args.todo:
        estado["pending"] = list(dict.fromkeys(estado.get("pending", []) + [m["id"] for m in salida]))
        guardar_estado(estado)

    relevantes = [m for m in salida if m["tipo"] in ("humano", "rebote")]

    if args.resumen:
        humanos = [m for m in relevantes if m["tipo"] == "humano"]
        rebotes = [m for m in relevantes if m["tipo"] == "rebote"]
        for m in humanos:
            print(f"humano | {m['fecha'][:16]} | {m['de'][:60]} | {m['asunto'][:80]}")
        if rebotes:
            dirs = sorted({m.get("direccion_rebotada", "?") for m in rebotes})
            print(f"rebote | {len(rebotes)} avisos del servidor, {len(dirs)} direcciones: {', '.join(dirs)[:300]}")
        return 0

    VOLCADOS.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d-%H%M")
    fichero = VOLCADOS / f"correo-{marca}.json"
    fichero.write_text(json.dumps(salida, ensure_ascii=False, indent=1))
    print(json.dumps({
        "total_nuevos": len(salida),
        "humanos": len([m for m in salida if m["tipo"] == "humano"]),
        "rebotes": len([m for m in salida if m["tipo"] == "rebote"]),
        "boletines": len([m for m in salida if m["tipo"] == "boletin"]),
        "volcado": str(fichero),
        "correos": relevantes,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
