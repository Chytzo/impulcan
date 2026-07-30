# Desplegar impulcan.com

Sitio Astro estático. Repositorio: `Chytzo/impulcan` (privado).

## Antes de publicar — obligatorio

La Ley 34/2002 (LSSI) obliga a identificar al titular del sitio cuando hay actividad
económica detrás. Hay dos archivos con marcadores `[pendiente]` que **no se pueden
publicar así**:

- `src/pages/aviso-legal.astro` → nombre, NIF y domicilio
- `src/pages/privacidad.astro` → responsable del tratamiento

Mientras no haya sociedad constituida, ahí va **el nombre y el NIF de la persona
física**. «Impulcan» figura como nombre comercial, no como titular.

Comprobación rápida antes de desplegar:

```bash
grep -rn "pendiente" src/pages/aviso-legal.astro src/pages/privacidad.astro
```

Si eso devuelve líneas, no está listo.

## Conectar Cloudflare Pages

1. Panel de Cloudflare → **Workers & Pages** → *Create* → **Pages** → *Connect to Git*.
2. Autorizar GitHub y elegir el repositorio `Chytzo/impulcan`.
3. Configuración de compilación:
   - Framework preset: **Astro**
   - Build command: `npm run build`
   - Output directory: `dist`
   - Rama de producción: `main`
4. *Save and Deploy*. El primer despliegue tarda un par de minutos.
5. En el proyecto → *Custom domains* → añadir `impulcan.com` y `www.impulcan.com`.
   Cloudflare crea los registros solo, porque el dominio ya está en la misma cuenta.

A partir de ahí, cada `git push` a `main` publica.

## Alternativa por línea de comandos

```bash
npx wrangler login
npm run build
npx wrangler pages deploy dist --project-name=impulcan
```

`wrangler login` abre el navegador y guarda las credenciales en `~/.wrangler`.

## Comprobar después del despliegue

```bash
curl -sI https://impulcan.com | head -1
curl -s https://impulcan.com/robots.txt | head -3
curl -s https://impulcan.com/llms.txt | head -3
curl -s https://impulcan.com/sitemap-index.xml | head -3
```

Y dar de alta el sitio en Google Search Console con el sitemap
`https://impulcan.com/sitemap-index.xml`.

## Estructura

```
src/data/servicios.json          6 servicios
src/data/municipios.json         12 municipios (población: Wikidata 2025)
src/data/angulos.json            36 textos por servicio × sector económico
src/data/angulos-municipio.json  24 textos a medida de los 4 municipios grandes
src/config.js                    contacto (WhatsApp, correo)
public/robots.txt                permite rastreadores de IA
public/llms.txt                  resumen del sitio para asistentes
```

83 páginas: portada, índice de servicios, 6 servicios, 72 landings de
servicio × municipio, y aviso legal, privacidad y créditos.
