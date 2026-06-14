# Activar la automatización (una sola vez, ~5 minutos)

Ya dejé todo el código listo: el repositorio git está inicializado y el job automático
(`.github/workflows/update-tournament.yml`) ya está escrito. Ese job, una vez activado,
corre la simulación de 50.000 partidos con **datos frescos cada día** y redespliega la web
solo. Después de esto **no tendrás que tocar el PC ni desplegar nada nunca más**.

Solo faltan 3 pasos que, por seguridad, únicamente puedes hacer tú (involucran tu login y un token).

---

## Paso 1 — Crear el repositorio en GitHub y subir el código

1. Entra a https://github.com/new
2. Nombre sugerido: `worldcup-2026-predictor`. Puede ser **privado**. **No** marques "Add a README".
3. Crea el repo. GitHub te mostrará la URL (ej. `https://github.com/TU_USUARIO/worldcup-2026-predictor.git`).
4. En PowerShell, dentro de la carpeta del proyecto, ejecuta (cambia la URL por la tuya):

```powershell
git remote add origin https://github.com/TU_USUARIO/worldcup-2026-predictor.git
git push -u origin main
```

La primera vez, git abrirá el navegador para que inicies sesión en GitHub. Eso es todo.

---

## Paso 2 — Crear un token de Vercel

1. Entra a https://vercel.com/account/settings/tokens
2. "Create Token" → nombre `github-actions` → scope tu cuenta → crea.
3. **Copia el token** (solo se muestra una vez).

---

## Paso 3 — Guardar el token como secreto en GitHub

1. En tu repo de GitHub: **Settings** → **Secrets and variables** → **Actions**.
2. "New repository secret".
3. Name: `VERCEL_TOKEN` · Secret: pega el token del Paso 2 · "Add secret".

---

## Listo. Probar que funciona

1. En tu repo: pestaña **Actions** → workflow **"Actualizar probabilidades del torneo"** → **Run workflow**.
2. En ~8-10 min corre la simulación y redespliega. Verás el resultado en
   https://vercel-app-henna-psi.vercel.app/tournament.html

A partir de ahí corre **solo todos los días a las 09:00 UTC**. No tienes que hacer nada más.

---

## Qué queda 100% automático tras esto

| Pieza | Antes | Después |
|---|---|---|
| Predictor por partido | automático (ya estaba) | automático |
| Probabilidades del torneo (campeón/grupos) | manual (snapshot) | **automático diario** |
| Datos (resultados nuevos) | manual | **se descargan solos en el job** |
| Redespliegue | manual | **automático** |
| Respaldo del código | solo en tu PC | **en GitHub** |

> Nota: el cron de GitHub corre sobre la rama `main`. Si cambias la frecuencia, edita la línea
> `cron:` del workflow (formato UTC). El job usa la fecha real de ejecución como fecha de corte,
> así que durante el Mundial siempre simula con el estado más reciente.
