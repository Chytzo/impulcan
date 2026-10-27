#!/usr/bin/env python3
"""Descarga el cuerpo y los adjuntos de un mensaje de Gmail (cuentas del CLI `gmail`).

El CLI `gmail` solo devuelve cabeceras. Esto baja el texto completo y guarda los adjuntos
en disco, para poder aplicar correcciones que los comercios envían por email.

Uso:
    python3 bajar-adjuntos-gmail.py impulcan <msg_id> <destino>
"""
import base64
import email
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "google-accounts"))
import gmail_account as ga  # noqa: E402


def recorrer(part, salida: list):
    if part.get("parts"):
        for p in part["parts"]:
            recorrer(p, salida)
        return
    mime = part.get("mimeType", "")
    cuerpo = part.get("body", {})
    datos = cuerpo.get("data")
    nombre = part.get("filename") or ""
    if nombre and datos:
        salida.append(("adjunto", nombre, base64.urlsafe_b64decode(datos)))
    elif datos and mime.startswith("text/"):
        salida.append(("texto", mime, base64.urlsafe_b64decode(datos)))


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    alias, msg_id, destino = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    destino.mkdir(parents=True, exist_ok=True)
    svc = ga._gmail(alias)
    full = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
    piezas: list = []
    recorrer(full.get("payload", {}), piezas)

    for tipo, nombre, datos in piezas:
        if tipo == "texto":
            sufijo = ".html" if "html" in nombre else ".txt"
            f = destino / ("cuerpo" + sufijo)
            f.write_bytes(datos)
            print(f"texto   → {f} ({len(datos)} B)")
        else:
            f = destino / os.path.basename(nombre)
            f.write_bytes(datos)
            print(f"adjunto → {f} ({len(datos)} B)")

    hdrs = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
    print(f"\nde: {hdrs.get('From')}\nasunto: {hdrs.get('Subject')}\nfecha: {hdrs.get('Date')}")
    if not piezas:
        print("(mensaje sin cuerpo descargable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
