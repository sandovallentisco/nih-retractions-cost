# Setup de la automatizacion

Este documento explica los pasos manuales que tienes que hacer **una sola vez**
para que el pipeline corra solo cada semana y la dashboard se redeploye sola.

## 1. Subir el proyecto a GitHub

```bash
cd "ruta/al/proyecto"
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin git@github.com:<TU_USUARIO>/<TU_REPO>.git
git push -u origin main
```

## 2. Configurar los secrets del repositorio

En GitHub: **Settings -> Secrets and variables -> Actions -> New repository secret**.
Anhade estos:

| Secret              | Para que sirve                                | Donde se obtiene                                          |
|---------------------|-----------------------------------------------|-----------------------------------------------------------|
| `ENTREZ_EMAIL`      | Identificarte ante NCBI/PubMed                | Tu email                                                  |
| `ENTREZ_API_KEY`    | Subir el rate-limit de PubMed                 | https://www.ncbi.nlm.nih.gov/account/settings/            |
| `SHINYAPPS_NAME`    | Cuenta de shinyapps.io                        | Panel de shinyapps.io, parte superior izquierda           |
| `SHINYAPPS_TOKEN`   | Token API de shinyapps.io                     | Panel -> Account -> Tokens -> Show -> Token               |
| `SHINYAPPS_SECRET`  | Secret asociado al token                      | Panel -> Account -> Tokens -> Show -> Secret              |
| `SHINYAPPS_APPNAME` | (Opcional) Nombre publico de la app           | Por defecto: `nih-retractions`                            |
| `GITLAB_TOKEN`      | (Opcional) Solo si el repo de RW es privado   | https://gitlab.com -> User Settings -> Access Tokens      |

## 3. Crear la cuenta de shinyapps.io (si aun no la tienes)

1. Registrate gratis en https://www.shinyapps.io.
2. Account -> Tokens -> Show. Copia `Name`, `Token` y `Secret` en los secrets
   de GitHub correspondientes.
3. Plan gratuito: 25 horas-app/mes y hasta 5 apps activas. Suficiente para
   un dashboard academico de trafico moderado.

## 4. Primera ejecucion (setup completo)

La primera vez **tienes que descargar todos los archivos historicos de NIH**
(unos cientos de MB) en local:

```bash
python -m src.downloader --full
python main.py --steps all
```

Esto deja los CSVs procesados en `data/processed/`. Comitea esos cambios:

```bash
git add data/processed/*.csv
git commit -m "chore(data): initial processed CSVs"
git push
```

## 5. Probar el workflow manualmente

En GitHub: pestana **Actions -> Weekly pipeline update -> Run workflow**.
Puedes elegir si redeployar la Shiny o no, y que pasos correr.

## 6. Activar el cron

El cron ya esta definido en `.github/workflows/weekly_update.yml`:

```yaml
on:
  schedule:
    - cron: "0 6 * * 0"   # 06:00 UTC todos los domingos
```

A partir del primer push se activa solo. **Atencion**: GitHub desactiva el
cron de un repo si no ha habido actividad en 60 dias. Para mantenerlo vivo
basta con hacer un commit cada par de meses (o el propio workflow al
commitear los CSVs procesados resetea ese contador).

## 7. Que sucede en cada corrida

1. Descarga `retraction_watch.csv` desde GitLab.
2. Descarga el FY actual + 2 anteriores de NIH ExPORTER (incremental).
3. Corre `main.py --steps all` con la cache de PubMed (solo consulta
   los DOIs nuevos -> el step 1 baja de 1.5h a unos minutos).
4. Commitea `data/processed/*.csv` (incluida la cache de PubMed) al repo.
5. Redeploya `app.R` en shinyapps.io con los CSVs nuevos.

## Troubleshooting

- **El workflow tarda mas de 6h y se cancela**: revisa que la cache se
  haya commiteado en la corrida anterior (`data/processed/pubmed_cache.csv`).
  Sin cache, el step 1 vuelve a tardar 1.5h.
- **NIH cambia el formato del CSV**: GitHub Actions te enviara un email al
  fallar el workflow. Mira los logs en la pestana Actions.
- **shinyapps.io se queda sin horas**: pasate al plan Starter ($9/mes) o
  desactiva el deploy automatico (`deploy_shiny: false` al lanzar el workflow
  manualmente) y deploya manualmente cuando convenga.
- **Invalidar la cache de PubMed**: borra
  `data/processed/pubmed_cache.csv` y haz push. La siguiente corrida la
  reconstruye desde cero.

---

## Maintaining the NIH raw-data Release asset

Since 2025 NIH no longer exposes stable bulk-download URLs on
``reporter.nih.gov/exporter`` (the page generates one-time-use opaque links
via JavaScript, which a cron cannot replay). To work around that, the
project keeps the NIH ExPORTER CSVs as a tarball published as a **GitHub
Release asset**. The cron downloads that tarball on every run.

### One-time setup

1. Open a terminal in the project folder and create a tarball with all the
   NIH CSVs you have locally:

   ```powershell
   # Windows / PowerShell
   tar -czf nih_raw.tar.gz -C "data/raw/nih_reporter" .
   ```

   On macOS or Linux the same command works. The result is a single file,
   typically 100-300 MB compressed.

2. Go to your repo on GitHub: **Releases -> Draft a new release**.
3. **Tag**: ``data-YYYY-MM-DD`` (e.g. ``data-2026-04-29``).
   **Title**: ``NIH raw data snapshot YYYY-MM-DD``.
4. Drag ``nih_raw.tar.gz`` into the asset upload area at the bottom of the
   release form. **Asset filename must be exactly ``nih_raw.tar.gz``** -
   the workflow downloads it by that exact name.
5. Click **Publish release**.

The workflow URL is fixed at
``https://github.com/<owner>/<repo>/releases/latest/download/nih_raw.tar.gz``,
which always resolves to the most recent release.

### Periodic refresh (manual, ~5 minutes)

Once a year, when NIH publishes a new full fiscal year (typically around
September), refresh the snapshot:

1. Open ``https://reporter.nih.gov/exporter`` in a browser.
2. Download the new ``RePORTER_PRJ_C_FYYYYY.zip`` via the cloud-icon button.
3. Extract its contents into your local ``data/raw/nih_reporter/`` folder.
4. Recreate the tarball with the same command above.
5. Draft a new release on GitHub, attach the new ``nih_raw.tar.gz``, publish.

Between releases the cron uses the data from the most recent snapshot, so
a delayed refresh only delays the appearance of newly-funded grants in the
dashboard. Existing analyses stay valid.

### Private repositories

If your repo is private, the workflow uses the built-in ``GITHUB_TOKEN``
secret (already configured) to authenticate against the release asset.
For local manual runs against a private repo, set ``GH_TOKEN`` in your
shell to a personal access token with ``repo`` scope before invoking the
downloader.
