# Noticiero con IA

Aplicacion web en Django que lee una noticia desde un archivo `.txt`, genera una voz con Text-to-Speech, muestra un video central como presentador de IA y rota imagenes cada 5 segundos.

## Estructura local

```text
noticiero ia/
├── manage.py
├── requirements.txt
├── scraper_noticias.py
├── abrir_noticiero_fullscreen.bat
├── abrir_noticiero_fullscreen.ps1
├── abrir_noticiero_google_tv.bat
├── abrir_noticiero_google_tv.ps1
├── config/
├── news/
│   ├── services.py
│   ├── views.py
│   ├── templates/news/index.html
│   └── static/news/
└── media/
    ├── video/
    │   └── video.mp4
    └── noticias/
        ├── textos/
        │   └── .gitkeep
        ├── imagenes/
        │   └── .gitkeep
        └── audio/
```

## Como agregar muchas noticias manualmente

La aplicacion acepta noticias manuales y las reproduce una despues de otra. El orden se define por el nombre del archivo, asi que conviene numerarlas:

```text
media/noticias/textos/
├── 001.txt
├── 002.txt
├── 003.txt
└── 100.txt

media/noticias/imagenes/
├── 001/
│   ├── foto1.jpg
│   └── foto2.jpg
├── 002/
│   ├── foto1.jpg
│   └── foto2.jpg
└── 100/
    └── foto1.jpg
```

Reglas:

1. Cada noticia debe tener un archivo `.txt` dentro de `media/noticias/textos/`.
2. La primera linea del `.txt` sera el titulo.
3. Las demas lineas seran el resumen/cuerpo que se leera en voz alta.
4. Las imagenes de cada noticia van en `media/noticias/imagenes/NOMBRE_DEL_TXT/`.
5. Si el texto se llama `025.txt`, sus imagenes van en `media/noticias/imagenes/025/`.
6. El video del presentador debe estar en `media/video/video.mp4`.

Ejemplo de texto:

```text
Titulo de la noticia

Cuerpo de la noticia en uno o mas parrafos.
```

Tambien puedes usar nombres descriptivos:

```text
media/noticias/textos/economia.txt
media/noticias/imagenes/economia/foto1.jpg
media/noticias/imagenes/economia/foto2.jpg
```

Para 100 noticias manuales, lo mas ordenado es usar `001.txt`, `002.txt`, `003.txt` y asi sucesivamente. Cuando una noticia termina su audio, el frontend pasa automaticamente a la siguiente.

## Ejecutar

Con el Python de Codex en este equipo:

```powershell
C:\Users\CARLOS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m venv .venv-codex
.\.venv-codex\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-codex\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Luego abre:

```text
http://127.0.0.1:8000/
```

El audio se genera automaticamente en `media/noticias/audio/`. El backend intenta `gTTS`, luego `edge-tts` y despues `pyttsx3`; si no logra crear un archivo, el navegador usa su voz integrada al presionar el boton.

Si `media/noticias/noticias_cache.json` no existe o queda antiguo, Django intenta actualizarlo automaticamente desde la fuente definida en `NEWS_SOURCE_URL`. Por defecto toma 6 noticias, refresca cada 360 minutos y genera un resumen local sin Gemini para evitar que Cloud quede sin contenido si no hay API key configurada.

## Subir a GitHub

El repositorio esta preparado para no subir archivos locales sensibles o generados, como `.env`, `db.sqlite3`, audios, caches del scraper, imagenes descargadas y entornos virtuales. El video usado por la app queda en `media/video/video.mp4`.

Comandos para el primer push:

```powershell
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
git push -u origin main
```

Antes de ejecutar la app en otro equipo, copia `.env.example` como `.env` y completa tus valores locales.

## Abrir como noticiero en pantalla completa

Para proyectar sin barra de direcciones ni URL visible, usa el lanzador:

```powershell
.\abrir_noticiero_fullscreen.bat
```

Ese archivo inicia Django si no esta corriendo y abre Edge o Chrome en modo kiosko. Para salir del modo kiosko, usa `Alt + F4`.

Si abres manualmente `http://127.0.0.1:8000/` en el navegador, la pagina tambien intenta entrar a pantalla completa al presionar `Iniciar noticiero`, pero el navegador no permite ocultar la barra de direcciones automaticamente apenas carga una pagina normal. Para eso se necesita el modo kiosko del lanzador.

Controles disponibles en pantalla:

1. `Iniciar noticiero`: comienza la reproduccion de la playlist.
2. `Siguiente noticia`: salta manualmente a la siguiente noticia. Si esta sonando una voz o audio, lo corta y reproduce la siguiente. Al llegar a la ultima, vuelve al inicio.

## Proyectar en una TV por Google

La opcion recomendada para una television con Chromecast o Google TV es:

```powershell
.\abrir_noticiero_google_tv.bat
```

Ese lanzador hace tres cosas:

1. Inicia Django en `0.0.0.0:8000`, visible desde la red local.
2. Abre el noticiero en modo kiosko con `?autoplay=1`.
3. Muestra una URL tipo `http://192.168.x.x:8000/?autoplay=1` para usar desde otro dispositivo en la misma red.

Formas de proyectar:

1. Desde el computador: abre el lanzador, luego en Chrome o Edge usa la opcion `Transmitir` y elige tu Chromecast/Google TV. Para que no se vea la barra de URL, transmite la pantalla completa o la ventana en modo kiosko.
2. Desde un Google TV con navegador: abre la URL de red local que muestra el lanzador, por ejemplo `http://192.168.1.25:8000/?autoplay=1`.
3. Desde otro computador conectado a la misma red: abre esa misma URL y luego transmite desde Chrome/Edge.

Si la TV u otro dispositivo no puede abrir la URL `192.168.x.x`, revisa que ambos esten en la misma red Wi-Fi y que Windows Firewall permita conexiones entrantes a Python/Django en el puerto `8000`.

## Automatizar noticias desde UCM con Gemini

El archivo `scraper_noticias.py` extrae todas las noticias disponibles desde la seccion "Noticias de la Facultad" de la Facultad de Ciencias Basicas UCM, entra al detalle de cada noticia, genera un guion de presentador con Gemini y crea una cache local que Django usa como playlist.

Por defecto, el scraper no descarga imagenes ni crea `.txt` permanentes por noticia. Guarda solo:

```text
media/noticias/noticias_cache.json
```

Ese archivo esta ignorado por Git, igual que audios, textos e imagenes generadas. Asi puedes subir el proyecto a GitHub sin subir contenido scrapeado.

Primero crea un archivo `.env` en la raiz del proyecto:

```text
GEMINI_API_KEY=tu_api_key_de_gemini
GEMINI_MODEL=gemini-1.5-flash
NEWS_SOURCE_URL=https://www.ucm.cl/facultades/facultad-de-ciencias-basicas/
NEWS_AUTO_REFRESH=1
NEWS_AUTO_REFRESH_LIMIT=6
NEWS_AUTO_REFRESH_MAX_AGE_MINUTES=360
NEWS_AUTO_REFRESH_USE_GEMINI=0
```

Ejecutar para tomar todas las noticias disponibles:

```powershell
.\.venv-codex\Scripts\python.exe scraper_noticias.py
```

Limitar la cantidad, por ejemplo 6:

```powershell
.\.venv-codex\Scripts\python.exe scraper_noticias.py --limit 6
```

Preparado para muchas noticias:

```powershell
.\.venv-codex\Scripts\python.exe scraper_noticias.py --limit 100
```

Modo de prueba sin Gemini:

```powershell
.\.venv-codex\Scripts\python.exe scraper_noticias.py --limit 1 --sin-gemini
```

Si ademas quieres crear archivos `.txt` e imagenes locales por noticia, usa:

```powershell
.\.venv-codex\Scripts\python.exe scraper_noticias.py --guardar-archivos
```

En modo `--guardar-archivos`, el scraper crea esta estructura:

```text
media/noticias/textos/001_titulo-de-la-noticia.txt
media/noticias/imagenes/001_titulo-de-la-noticia/imagen_01.jpg
media/noticias/imagenes/001_titulo-de-la-noticia/imagen_02.jpg
```

El noticiero prioriza `media/noticias/noticias_cache.json`. Si esa cache no existe, vuelve al modo manual leyendo `media/noticias/textos/`.
