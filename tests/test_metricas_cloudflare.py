"""Pruebas del cliente de métricas de Cloudflare. Sin red: se prueba el agregado puro."""

import importlib.util
import os
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "metricas", RAIZ / "herramientas" / "metricas-cloudflare.py")
assert _spec and _spec.loader
met = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(met)

MAPA = {"zonaalcaravaneras.com": "tag-a", "zonaguanarteme.com": "tag-g"}

ZONAS = [
    {"zoneTag": "tag-a", "httpRequests1dGroups": [
        {"dimensions": {"date": "2026-10-20"},
         "sum": {"requests": 100, "bytes": 2_000_000, "cachedRequests": 80},
         "uniq": {"uniques": 30}},
        {"dimensions": {"date": "2026-10-21"},
         "sum": {"requests": 50, "bytes": 1_000_000, "cachedRequests": 25},
         "uniq": {"uniques": 20}},
    ]},
    {"zoneTag": "tag-g", "httpRequests1dGroups": [
        {"dimensions": {"date": "2026-10-21"},
         "sum": {"requests": 10, "bytes": 0, "cachedRequests": 0},
         "uniq": {"uniques": 4}},
    ]},
]


class TestAgregado(unittest.TestCase):
    def setUp(self):
        self.filas = met.agregar(ZONAS, MAPA)
        self.por_dom = {f["dominio"]: f for f in self.filas}

    def test_suma_peticiones_y_dias(self):
        a = self.por_dom["zonaalcaravaneras.com"]
        self.assertEqual(a["peticiones"], 150)
        self.assertEqual(a["dias"], 2)

    def test_suma_visitantes_y_bytes(self):
        a = self.por_dom["zonaalcaravaneras.com"]
        self.assertEqual(a["visitantes"], 50)
        self.assertEqual(a["MB"], 3.0)

    def test_cache_porcentaje(self):
        self.assertAlmostEqual(self.por_dom["zonaalcaravaneras.com"]["cache_pct"], 70.0)   # 105/150
        self.assertEqual(self.por_dom["zonaguanarteme.com"]["cache_pct"], 0.0)

    def test_orden_por_peticiones(self):
        self.assertEqual([f["dominio"] for f in self.filas],
                         ["zonaalcaravaneras.com", "zonaguanarteme.com"])

    def test_serie_vacia_no_rompe(self):
        filas = met.agregar([{"zoneTag": "tag-vacio", "httpRequests1dGroups": []}], MAPA)
        self.assertEqual(filas[0]["peticiones"], 0)
        self.assertEqual(filas[0]["cache_pct"], 0.0)
        self.assertEqual(filas[0]["dominio"], "tag-vacio")


class TestToken(unittest.TestCase):
    def test_sin_token_aborta_con_exit_2(self):
        entorno = dict(os.environ)
        os.environ.pop("CF_API_TOKEN", None)
        try:
            with self.assertRaises(SystemExit) as ctx:
                met.token()
            self.assertEqual(ctx.exception.code, 2)
        finally:
            os.environ.clear()
            os.environ.update(entorno)

    def test_lee_de_entorno(self):
        entorno = os.environ.get("CF_API_TOKEN")
        os.environ["CF_API_TOKEN"] = "abc123"
        try:
            self.assertEqual(met.token(), "abc123")
        finally:
            if entorno is None:
                os.environ.pop("CF_API_TOKEN", None)
            else:
                os.environ["CF_API_TOKEN"] = entorno


if __name__ == "__main__":
    unittest.main(verbosity=2)
