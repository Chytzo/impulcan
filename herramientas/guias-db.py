#!/usr/bin/env python3
"""Base de datos de la red de guías de barrio.

Reúne en un solo sitio los comercios de las cuatro guías y el estado de
captación de cada uno: a quién se ha llamado, quién ha mandado foto, quién
ha pedido la baja y quién ha acabado siendo cliente de Impulcan.

Las fichas se sincronizan desde los `comercios.json` de cada repo, que
siguen siendo la fuente de verdad de lo que se publica. Esta base añade
encima lo que no vive en la web: el trabajo comercial.

Uso:
  guias-db.py sync                       vuelca los JSON a la base
  guias-db.py resumen                    estado por guía
  guias-db.py ruta <guia> [--calle X]    a quién visitar, agrupado por calle
  guias-db.py pendientes <guia>          sin teléfono, sin horario o sin foto
  guias-db.py contacto <guia> <slug> <estado> [--nota "..."] [--via telefono]
  guias-db.py ficha <guia> <slug>        todo lo que sabemos de un comercio
"""
import argparse, json, pathlib, sqlite3, sys
from datetime import date

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
BD = RAIZ / 'impulcan' / 'datos' / 'guias.db'
GUIAS = {
    'alcaravaneras': ('zonaalcaravaneras', 'zonaalcaravaneras.com'),
    'guanarteme': ('zonaguanarteme', 'zonaguanarteme.com'),
    'santacatalina': ('zonasantacatalina', 'zonasantacatalina.com'),
    'laisleta': ('zonalaisleta', 'zonalaisleta.com'),
}
ESTADOS = ['sin_contactar', 'llamado', 'no_contesta', 'interesado',
           'foto_recibida', 'datos_corregidos', 'baja_pedida', 'cliente',
           'email_enviado']

ESQUEMA = """
CREATE TABLE IF NOT EXISTS guias (
  clave TEXT PRIMARY KEY, repo TEXT NOT NULL, dominio TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comercios (
  guia TEXT NOT NULL, slug TEXT NOT NULL,
  nombre TEXT NOT NULL, categoria TEXT, calle TEXT, cp TEXT,
  telefono TEXT, whatsapp TEXT, email TEXT, web TEXT,
  horario TEXT, tiene_foto INTEGER NOT NULL DEFAULT 0,
  lat REAL, lon REAL, fuente TEXT,
  PRIMARY KEY (guia, slug),
  FOREIGN KEY (guia) REFERENCES guias(clave)
);
CREATE TABLE IF NOT EXISTS contactos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guia TEXT NOT NULL, slug TEXT NOT NULL,
  fecha TEXT NOT NULL, estado TEXT NOT NULL, via TEXT, nota TEXT,
  FOREIGN KEY (guia, slug) REFERENCES comercios(guia, slug)
);
CREATE INDEX IF NOT EXISTS idx_comercios_calle ON comercios(guia, calle);
CREATE INDEX IF NOT EXISTS idx_contactos_ficha ON contactos(guia, slug, fecha);

-- Último estado conocido de cada comercio
CREATE VIEW IF NOT EXISTS estado_actual AS
SELECT c.guia, c.slug, c.nombre, c.calle, c.telefono, c.tiene_foto,
       COALESCE(u.estado, 'sin_contactar') AS estado,
       u.fecha AS ultima_fecha
FROM comercios c
LEFT JOIN (
  SELECT guia, slug, estado, fecha,
         ROW_NUMBER() OVER (PARTITION BY guia, slug ORDER BY fecha DESC, id DESC) AS n
  FROM contactos
) u ON u.guia = c.guia AND u.slug = c.slug AND u.n = 1;
"""


def abre():
    BD.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(BD)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def sync(con):
    for clave, (repo, dominio) in GUIAS.items():
        con.execute('INSERT OR REPLACE INTO guias VALUES (?,?,?)', (clave, repo, dominio))
        fichas = json.loads((RAIZ / repo / 'src/data/comercios.json').read_text())
        for f in fichas:
            con.execute("""INSERT INTO comercios
                (guia, slug, nombre, categoria, calle, cp, telefono, whatsapp,
                 email, web, horario, tiene_foto, lat, lon, fuente)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(guia, slug) DO UPDATE SET
                 nombre=excluded.nombre, categoria=excluded.categoria,
                 calle=excluded.calle, cp=excluded.cp, telefono=excluded.telefono,
                 whatsapp=excluded.whatsapp, email=excluded.email, web=excluded.web,
                 horario=excluded.horario, tiene_foto=excluded.tiene_foto,
                 lat=excluded.lat, lon=excluded.lon, fuente=excluded.fuente""",
                (clave, f['slug'], f['nombre'], f.get('categoria'), f.get('calle'),
                 f.get('cp'), f.get('telefono'), f.get('whatsapp'), f.get('email'),
                 f.get('web'), f.get('horario'), 1 if f.get('fotos') else 0,
                 f.get('lat'), f.get('lon'), f.get('fuente')))
        print(f'{clave:16} {len(fichas):4} fichas')
    con.commit()


def resumen(con):
    filas = con.execute("""
        SELECT guia, COUNT(*) n,
               SUM(telefono IS NOT NULL AND telefono <> '') con_tel,
               SUM(web IS NOT NULL AND web <> '') con_web,
               SUM(horario IS NOT NULL AND horario <> '') con_horario,
               SUM(tiene_foto) con_foto
        FROM comercios GROUP BY guia ORDER BY n DESC""").fetchall()
    print(f"{'guía':16}{'fichas':>7}{'teléfono':>10}{'web':>7}{'horario':>9}{'foto':>7}")
    for f in filas:
        print(f"{f['guia']:16}{f['n']:>7}{f['con_tel']:>10}{f['con_web']:>7}"
              f"{f['con_horario']:>9}{f['con_foto']:>7}")
    print()
    for f in con.execute("""SELECT estado, COUNT(*) n FROM estado_actual
                            GROUP BY estado ORDER BY n DESC"""):
        print(f"  {f['estado']:18} {f['n']}")


def ruta(con, guia, calle=None):
    sql = """SELECT calle, nombre, slug, telefono, estado FROM estado_actual
             WHERE guia = ? AND estado = 'sin_contactar'"""
    args = [guia]
    if calle:
        sql += ' AND calle LIKE ?'
        args.append(f'%{calle}%')
    sql += ' ORDER BY calle, nombre'
    actual = None
    for f in con.execute(sql, args):
        if f['calle'] != actual:
            actual = f['calle']
            print(f'\n{actual}')
        tel = f['telefono'] or '— sin teléfono'
        print(f"  {f['nombre'][:38]:40} {tel:16} {f['slug']}")


def pendientes(con, guia):
    for f in con.execute("""SELECT nombre, slug, calle,
              (telefono IS NULL OR telefono = '') falta_tel,
              (horario IS NULL OR horario = '') falta_hor,
              (tiene_foto = 0) falta_foto
            FROM comercios WHERE guia = ?
              AND ((telefono IS NULL OR telefono = '')
                OR (horario IS NULL OR horario = '') OR tiene_foto = 0)
            ORDER BY falta_tel DESC, calle, nombre""", (guia,)):
        falta = ' '.join(x for x, v in
                         (('teléfono', f['falta_tel']), ('horario', f['falta_hor']),
                          ('foto', f['falta_foto'])) if v)
        print(f"{f['nombre'][:38]:40} {f['calle'][:26]:28} falta: {falta}")


def contacto(con, guia, slug, estado, via, nota):
    if estado not in ESTADOS:
        sys.exit(f'Estado desconocido. Usa uno de: {", ".join(ESTADOS)}')
    if not con.execute('SELECT 1 FROM comercios WHERE guia=? AND slug=?',
                       (guia, slug)).fetchone():
        sys.exit(f'No existe {slug} en {guia}')
    con.execute('INSERT INTO contactos (guia, slug, fecha, estado, via, nota) '
                'VALUES (?,?,?,?,?,?)',
                (guia, slug, date.today().isoformat(), estado, via, nota))
    con.commit()
    print(f'{slug}: {estado}')


def ficha(con, guia, slug):
    f = con.execute('SELECT * FROM comercios WHERE guia=? AND slug=?',
                    (guia, slug)).fetchone()
    if not f:
        sys.exit(f'No existe {slug} en {guia}')
    for k in f.keys():
        if f[k] not in (None, ''):
            print(f'{k:12} {f[k]}')
    print('\nhistorial:')
    for c in con.execute('SELECT * FROM contactos WHERE guia=? AND slug=? ORDER BY fecha',
                         (guia, slug)):
        print(f"  {c['fecha']} {c['estado']:16} {c['via'] or '':10} {c['nota'] or ''}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='orden', required=True)
    sub.add_parser('sync')
    sub.add_parser('resumen')
    r = sub.add_parser('ruta'); r.add_argument('guia'); r.add_argument('--calle')
    pe = sub.add_parser('pendientes'); pe.add_argument('guia')
    c = sub.add_parser('contacto')
    c.add_argument('guia'); c.add_argument('slug'); c.add_argument('estado')
    c.add_argument('--via', default='telefono'); c.add_argument('--nota', default='')
    fi = sub.add_parser('ficha'); fi.add_argument('guia'); fi.add_argument('slug')
    a = p.parse_args()

    con = abre()
    if a.orden == 'sync': sync(con)
    elif a.orden == 'resumen': resumen(con)
    elif a.orden == 'ruta': ruta(con, a.guia, a.calle)
    elif a.orden == 'pendientes': pendientes(con, a.guia)
    elif a.orden == 'contacto': contacto(con, a.guia, a.slug, a.estado, a.via, a.nota)
    elif a.orden == 'ficha': ficha(con, a.guia, a.slug)


if __name__ == '__main__':
    main()
