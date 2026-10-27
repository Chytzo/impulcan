"""Genera public/llms-full.txt de Impulcan: el contenido completo del sitio en texto
plano, para que los agentes de IA (Claude, GPT, Gemini, Perplexity…) puedan
responder sobre Impulcan y sus páginas sin navegar.

Uso: python3 herramientas/generar-llms-full.py
"""
import json, os

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
servicios = json.load(open(os.path.join(RAIZ, 'src/data/servicios.json')))
municipios = json.load(open(os.path.join(RAIZ, 'src/data/municipios.json')))
precios = json.load(open(os.path.join(RAIZ, 'src/data/precios.json')))
DOM = 'https://impulcan.com'

paginas = [
    ('Inicio', '/'),
    ('Servicios (índice)', '/servicios/'),
]
for s in servicios:
    paginas.append((f'Servicio: {s["nombre"]}', f'/servicios/{s["slug"]}/'))
    for m in municipios:
        paginas.append((f'{s["nombre"]} en {m["nombre"]}', f'/servicios/{s["slug"]}/{m["slug"]}/'))
paginas += [('Aviso legal', '/aviso-legal/'), ('Privacidad', '/privacidad/'),
            ('Créditos', '/creditos/')]

L = ['# Impulcan — contenido completo', '']
L.append(f'> Marketing y automatizaciones para negocios de Las Palmas de Gran Canaria y el '
         f'resto de Gran Canaria (Canarias, España). Este archivo contiene el contenido '
         f'completo del sitio, incluidos los {len(servicios)} servicios, los {len(municipios)} municipios cubiertos, los '
         f'precios y las {len(paginas)} páginas. Para una versión resumida, ver llms.txt.')
L += ['', 'Impulcan trabaja con comercios de barrio, talleres, clínicas, hostelería y pymes '
         'de Gran Canaria. El enfoque es presencial y local: visitamos el negocio antes de '
         'proponer nada. No usamos permanencias ni paquetes cerrados, y lo que montamos '
         'queda en manos del cliente. Primera revisión del negocio gratuita y sin compromiso.',
      '', '## Servicios', '']

for s in servicios:
    L.append(f"### {s['nombre']} — {s['titular']}")
    L.append('')
    L.append(f"Resumen: {s['resumen']}")
    L.append('')
    L.append(f"Problema que resuelve: {s['problema']}")
    L += ['', 'Qué hacemos:']
    for q in s['que_hacemos']:
        L.append(f'- {q}')
    L += ['', 'Entregables:']
    for e in s['entregables']:
        L.append(f'- {e}')
    L += ['', 'Preguntas frecuentes:']
    for p in s['preguntas']:
        L.append(f'- {p["p"]} → {p["r"]}')
    L.append(f'- Página del servicio: {DOM}/servicios/{s["slug"]}/')
    L += ['', f'Versiones por municipio: ' +
          ', '.join(f'{m["nombre"]} ({DOM}/servicios/{s["slug"]}/{m["slug"]}/)'
                    for m in municipios) + '.', '']

L += ['## Municipios cubiertos', '']
for m in municipios:
    L.append(f"### {m['nombre']} ({m['poblacion']:,} hab., {m['km2']} km², {m['anio']})")
    L.append('')
    L.append(f"Perfil: {m['perfil']}.")
    L.append(f"Contexto: {m['contexto']}")
    L.append(f"Tejido comercial: {m['tejido']}")
    L.append(f"Cercanía: {m['cercania']}")
    L.append(f"Servicios ofrecidos en {m['nombre']}: " +
             ', '.join(f'{s["nombre"]} ({DOM}/servicios/{s["slug"]}/{m["slug"]}/)'
                       for s in servicios) + '.')
    L.append('')

L += ['## Precios', '']
L.append(f"Nota: {precios['nota']}")
L.append('')
for p in precios['planes']:
    L.append(f"- **{p['nombre']} — {p['precio']} €, {p['unidad']}.** {p['gancho']}")
    for i in p['incluye']:
        L.append(f"  - {i}")
    if p.get('coletilla'):
        L.append(f"  {p['coletilla']}")
    L.append('')
L += ['', 'La primera visita para ver el negocio es gratuita y sin compromiso.', '',
      '## Proyectos propios: guías de barrio', '']
L.append('Cuatro guías de comercio local en Las Palmas de Gran Canaria, 2.047 comercios '
         'en total, con ficha básica gratuita para los comercios y sin vinculación con ninguna asociación '
         'ni partido político. Cada una tiene su propio llms-full.txt:')
L.append('- Zona Alcaravaneras (327): https://zonaalcaravaneras.com/llms-full.txt')
L.append('- Zona Guanarteme (656): https://zonaguanarteme.com/llms-full.txt')
L.append('- Zona Santa Catalina (754): https://zonasantacatalina.com/llms-full.txt')
L.append('- Zona La Isleta (310): https://zonalaisleta.com/llms-full.txt')
L += ['', '## Zona de actuación', '',
      'Las Palmas de Gran Canaria y el resto de la isla de Gran Canaria (Canarias, '
      'España). Trabajo presencial en la isla.', '',
      '## Páginas del sitio', '']
for titulo, ruta in paginas:
    L.append(f'- {titulo}: {DOM}{ruta}')
L += ['', '## Contacto', '',
      '- WhatsApp: +34 633 50 51 53',
      '- Correo: hola@impulcan.com',
      '- Web: https://impulcan.com', '']

contenido = '\n'.join(L)
open(os.path.join(RAIZ, 'public/llms-full.txt'), 'w').write(contenido)
print(f"llms-full.txt de Impulcan: {len(contenido)} bytes, {len(paginas)} páginas")
