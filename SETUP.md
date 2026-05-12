# Automation Setup

This document explains the manual steps you need to perform **only once**
so that the pipeline runs automatically every week and the dashboard is redeployed by itself.

## 1. Push the project to GitHub

```bash
cd "path/to/project"
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin git@github.com:<YOUR_USER>/<YOUR_REPO>.git
git push -u origin main
```

## 2. Configure repository secrets

On GitHub: **Settings -> Secrets and variables -> Actions -> New repository secret**.
Add these:

| Secret              | Purpose                                       | Where to get it                                           |
|---------------------|-----------------------------------------------|-----------------------------------------------------------|
| `ENTREZ_EMAIL`      | Identify yourself to NCBI/PubMed              | Your email                                                |
| `ENTREZ_API_KEY`    | Increase PubMed's rate-limit                  | https://www.ncbi.nlm.nih.gov/account/settings/            |
| `SHINYAPPS_NAME`    | shinyapps.io account name                     | shinyapps.io dashboard, top left                          |
| `SHINYAPPS_TOKEN`   | shinyapps.io API Token                        | Dashboard -> Account -> Tokens -> Show -> Token           |
| `SHINYAPPS_SECRET`  | Secret associated with the token              | Dashboard -> Account -> Tokens -> Show -> Secret          |
| `SHINYAPPS_APPNAME` | (Optional) Public app name                    | Default: `nih-retractions`                                |
| `GITLAB_TOKEN`      | (Optional) Only if the RW repo is private     | https://gitlab.com -> User Settings -> Access Tokens      |

## 3. Create a shinyapps.io account (if you don't have one)

1. Register for free at https://www.shinyapps.io.
2. Account -> Tokens -> Show. Copy `Name`, `Token` and `Secret` to the corresponding
   GitHub secrets.
3. Free plan: 25 app-hours/month and up to 5 active apps. Sufficient for
   an academic dashboard with moderate traffic.

## 4. First run (full setup)

The first time **you have to download all historical NIH files**
(a few hundred MB) locally:

```bash
python -m src.downloader --full
python main.py --steps all
```

This leaves the processed CSVs in `data/processed/`. Commit these changes:

```bash
git add data/processed/*.csv
git commit -m "chore(data): initial processed CSVs"
git push
```

## 5. Test the workflow manually

On GitHub: **Actions** tab **-> Weekly pipeline update -> Run workflow**.
You can choose whether to redeploy Shiny or not, and which steps to run.

## 6. Activate the cron

The cron is already defined in `.github/workflows/weekly_update.yml`:

```yaml
on:
  schedule:
    - cron: "0 6 * * 0"   # 06:00 UTC every Sunday
```

It activates automatically after the first push. **Note**: GitHub disables a repository's
cron if there has been no activity for 60 days. To keep it alive
you just need to make a commit every couple of months (or the workflow itself
will reset this counter when committing the processed CSVs).

## 7. What happens in each run

1. Downloads `retraction_watch.csv` from GitLab.
2. Downloads the entire NIH ExPORTER raw data snapshot (`nih_raw.tar.gz`) from the GitHub Release.
3. Runs `main.py --steps all` with PubMed cache (only queries
   new DOIs -> step 1 goes down from 1.5h to a few minutes).
4. Commits `data/processed/*.csv` (including PubMed cache) to the repo.
5. Redeploys `app.R` on shinyapps.io with the new CSVs.

## Troubleshooting

- **The workflow takes more than 6h and cancels**: check that the cache was
  committed in the previous run (`data/processed/pubmed_cache.csv`).
  Without the cache, step 1 takes 1.5h again.
- **NIH changes the CSV format**: GitHub Actions will send you an email when
  the workflow fails. Check the logs in the Actions tab.
- **shinyapps.io runs out of hours**: upgrade to the Starter plan ($9/month) or
  disable auto-deploy (`deploy_shiny: false` when triggering the workflow
  manually) and deploy manually when necessary.
- **Invalidate the PubMed cache**: delete
  `data/processed/pubmed_cache.csv` and push. The next run will
  rebuild it from scratch.

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
