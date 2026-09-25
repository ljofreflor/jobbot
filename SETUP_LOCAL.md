# Configuración Local de JobBot

Guía paso a paso para usar JobBot en tu computadora local.

## ✅ Estado Actual del Workspace (VM)

Este workspace ya está completamente configurado:
- ✅ Rama: `cursor/companies-recon-1023`
- ✅ Virtual env: `.venv/` con todas las dependencias
- ✅ Perfil: `data/profile.yaml` configurado
- ✅ Base de datos: `data/jobbot.sqlite` funcionando
- ✅ Features: Torre + SDK + Merge con develop completo

## 🏠 Para Usar en Tu Computadora Local

### Opción A: Clonar este Repositorio

#### 1. Clonar y cambiar a la rama correcta
```bash
# Clonar
git clone https://github.com/ljofreflor/jobbot.git
cd jobbot

# Cambiar a nuestra rama con todas las features
git checkout cursor/companies-recon-1023

# Verificar que estés en la rama correcta
git branch --show-current
# Debe mostrar: cursor/companies-recon-1023
```

#### 2. Crear entorno virtual e instalar

**Windows (PowerShell):**
```powershell
# Crear entorno virtual
python -m venv .venv

# Activar
.\.venv\Scripts\Activate.ps1

# Si da error de permisos, ejecuta:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Instalar jobbot
pip install -e .
```

**Windows (CMD):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
pip install -e .
```

**Mac/Linux:**
```bash
# Crear entorno virtual
python3 -m venv .venv

# Activar
source .venv/bin/activate

# Instalar jobbot
pip install -e .
```

#### 3. Configurar tu perfil

```bash
# Copiar ejemplo
cp data/profile.example.yaml data/profile.yaml

# Editar con tus datos
# Windows: notepad data/profile.yaml
# Mac: open -a TextEdit data/profile.yaml
# Linux: nano data/profile.yaml
```

**Edita estos campos importantes:**
- `name`: Tu nombre
- `email`: Tu email
- `phone`: Tu teléfono
- `location`: Tu ubicación
- `summary`: Resumen profesional
- `skills`: Tus habilidades
- `experience`: Tu experiencia laboral
- `education`: Tu educación

#### 4. Verificar instalación

```bash
# Verificar que jobbot esté instalado
jobbot --version

# Ver comandos disponibles
jobbot --help

# Probar funcionalidad básica
jobbot jobs --help
jobbot torre --help
```

### Opción B: Usar Cursor con Carpeta Local

#### 1. Abrir carpeta local en Cursor
```
File > Open Folder... > Selecciona donde clonaste jobbot
```

#### 2. Cursor detectará el `.venv/` automáticamente

#### 3. Abrir terminal en Cursor y verificar:
```bash
# Debe activarse automáticamente
which jobbot  # Mac/Linux
where jobbot  # Windows

# Probar comandos
jobbot --version
```

## 🌐 Usar con Edge/Chrome Local

### 1. Abrir navegador con remote debugging

**Edge (Windows):**
```powershell
# Cerrar Edge completamente primero
# Luego ejecutar:
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="$env:TEMP\edge-jobbot"
```

**Edge (Mac):**
```bash
/Applications/Microsoft\ Edge.app/Contents/MacOS/Microsoft\ Edge --remote-debugging-port=9222 --user-data-dir=/tmp/edge-jobbot
```

**Chrome (cualquier OS):**
```bash
# Usa el comando automático de jobbot:
jobbot browser chrome-debug --site linkedin
```

### 2. Verificar conexión

```bash
# Ver sesiones de navegador disponibles
jobbot browser sessions

# Debe mostrar algo como:
# linkedin │ ready │ http://127.0.0.1:9222 │ signed in: /feed
```

### 3. Usar con LinkedIn

```bash
# Con navegador abierto y logueado:
jobbot get "https://www.linkedin.com/jobs/view/4471107884/" --cdp http://localhost:9222
```

## 🎯 Comandos Útiles para Empezar

### Buscar trabajos (sin autenticación)
```bash
# Torre (LATAM/remoto) - API pública
jobbot torre search "python developer" --remote --limit 10

# Ver trabajos almacenados
jobbot jobs show J0001
```

### Matching con tu perfil
```bash
# Ver qué tan bien matcheas con un trabajo
jobbot jobs match J0001

# Ver todos los trabajos ranqueados
jobbot jobs shortlist
```

### Construir CV
```bash
# CV base
jobbot cv build

# CV específico para un trabajo
jobbot cv build --job J0001

# El PDF se guarda en: output/base/cv.pdf
```

### SDK (programático)
```python
from jobbot.sdk import JobBotClient

with JobBotClient() as client:
    # Buscar trabajos
    jobs = client.jobs.search("python", source="torre", remote=True)
    
    # Match
    matches = client.jobs.match(jobs)
    
    # Construir CV
    cv_path = client.cv.build(job=jobs[0], style="moderncv")
```

## 🐛 Solución de Problemas

### Error: "command not found: jobbot"
```bash
# Asegúrate de activar el entorno virtual
source .venv/bin/activate  # Mac/Linux
.\.venv\Scripts\Activate.ps1  # Windows PowerShell
```

### Error: "No module named 'jobbot'"
```bash
# Reinstalar en modo editable
pip install -e .
```

### Error al abrir Edge/Chrome
```bash
# Cierra TODAS las ventanas del navegador primero
# Luego abre con el comando de debugging

# Verificar si hay procesos corriendo:
# Windows: tasklist | findstr msedge
# Mac/Linux: ps aux | grep -i edge
```

### LinkedIn no responde
```bash
# Verifica que estés logueado en el navegador con CDP
jobbot browser sessions

# Debe mostrar "ready" o "signed in", no "needs_login"
```

## 📚 Documentación

- **SDK**: `docs/sdk.md` - API programática completa
- **CLI**: `AGENTS.md` - Guía de todos los comandos
- **Arquitectura**: `docs/architecture-di.md` - Patrones de diseño
- **Ejemplos**: `examples/sdk_*.py` - Scripts de ejemplo

## 🚀 Features Disponibles

### ✅ Torre Integration
- Búsqueda de trabajos en Torre.ai
- API pública (no requiere auth)
- Soporte LATAM y remoto

### ✅ SDK Programático
- `JobBotClient` para uso en scripts
- `JobsApi` para búsqueda y matching
- `CvApi` para construcción de CVs

### ✅ Multi-Browser Support
- Chrome, Edge, Brave, Chromium
- Detección automática
- CDP para LinkedIn, Indeed, Gmail

### ✅ Job Management
- Búsqueda y almacenamiento
- Matching con perfil
- Ranking por score

### ✅ CV Builder
- CVs base y específicos por trabajo
- Múltiples estilos
- Exportación a PDF

## 🆘 Ayuda

Si tienes problemas:
1. Revisa esta guía
2. Ejecuta: `jobbot --help`
3. Revisa los logs en: `data/jobbot.sqlite`
4. Pregunta en el chat

---

**Última actualización**: 2026-09-24  
**Rama**: `cursor/companies-recon-1023`  
**Features**: Torre + SDK + Multi-browser + Merge develop
