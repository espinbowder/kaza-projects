# KAZA projects: who is doing what, and where

A public dashboard of conservation and development projects in the Kavango Zambezi Transfrontier Conservation Area (KAZA TFCA), kept up to date from a KoboToolbox survey.

```
KoboToolbox survey ──► reviewer marks submissions "Approved"
                              │
                              ▼
GitHub Actions (every night, or on demand) runs scripts/update.py
   starting data (data/seed)  +  approved submissions
   → area matching, WDA counting (2% rule), countries, checks
   → writes docs/data/*.json
                              │
                              ▼
GitHub Pages website (docs/):  index.html = dashboard,  picker.html = map picker → survey
```

## What is in this repository

| Folder / file | What it is | Who changes it |
|---|---|---|
| `docs/index.html` | The dashboard (map, filters, charts, project list) | rarely |
| `docs/picker.html` | Map picker: people click areas, districts or WDAs, draw or upload areas, and get a location code for the survey | rarely |
| `docs/site.json` | The survey link the picker opens | you, once |
| `docs/data/` | Data the website reads. **Rebuilt automatically**, don't edit by hand | the update script |
| `data/seed/` | The 187 projects from the 2021–2024 survey (starting data) | you, if a correction is needed |
| `data/reference/` | Areas (parks, conservancies, WDAs, KAZA boundary), country segments (`countries.geojson`), districts / constituencies (`districts.geojson`, admin level 2), organisations, themes | you, when new areas or organisations are approved |
| `scripts/` | The update script (Python) | rarely |
| `config.json` | KoboToolbox address and form ID, WDA rule threshold | you, once |
| `forms/` | The KoboToolbox form (XLSForm) | you, when the survey changes |
| `reports/` | Checks on approved submissions and new areas to review | the update script |
| `.github/workflows/update.yml` | The schedule that runs the update script | rarely |

## Rules the script applies

- **Status:** a project with no end date (or "ongoing") counts as Active.
- **WDAs:** whole KAZA → all six WDAs. A whole WDA ticked → only that WDA, even where WDA outlines overlap. Listed and drawn areas → a WDA counts when at least 2% of the project's area lies in it. For the starting data, the shapes drawn for KAZA_Projects_24 decide.
- **Countries:** what people report, plus the country of every listed area or district they choose. The map (country segments) is only used where no country is given, i.e. drawn or uploaded areas and whole WDAs, and a country counts from 5% of that area (`country_min_share` in `config.json`), so small border differences between layers don't add a country.
- **Districts:** admin level 2 (Namibia: constituencies) can be chosen as whole units in the picker ("Districts" view) and the survey. They count like listed areas (2% WDA rule). Districts with less than 100 km² inside KAZA are left out as edge slivers, except the towns Victoria Falls, Hwange Urban, Rundu Urban and Katima Mulilo Urban.
- **Locations (location code):** people choose areas, districts or whole WDAs on the map picker, and draw or upload areas that are not on the map (GeoJSON, KML/KMZ or a zipped shapefile in WGS 84 or Web Mercator; shapes are simplified to about 100 m). The picker turns this into a *location code* (`KAZA-LOC1 | summary | data`) that is pasted into the survey, or passed along automatically when people start from the map. The update script decodes it; drawn and uploaded areas appear in `reports/candidate_areas.geojson` for review. People who cannot use the map answer the list questions instead.
- **Funding:** German Government is the funder; KfW, BMZ, GIZ, IKI, BMBF and BENGO are channels. If someone enters KfW as the funder, it is recorded as German Government via KfW.
- **Amounts:** 0 means "no answer".
- **Publishing:** only submissions that are **Approved** in KoboToolbox **and** where the submitter said the project may be shown publicly. Contact names and e-mails are never copied into this repository.

## Step-by-step setup (all in the web browser)

### 1. Create the repository
1. Sign in at github.com. Click **+** (top right) → **New repository**.
2. Name: `kaza-projects`. Choose **Public** (needed for free GitHub Pages). Tick **Add a README file**. Click **Create repository**.

### 2. Upload the files
1. Unzip the package on your computer.
2. In the repository, click **Add file → Upload files**. Drag in the folders `data`, `docs`, `forms`, `reports`, `scripts` and the files `config.json`, `README.md`, `.gitignore` (replace the README).
3. Write a short message such as "First upload" and click **Commit changes**.
4. The automation file sits in a hidden folder, which drag-and-drop often skips. Add it by hand: **Add file → Create new file**, type the name `.github/workflows/update.yml` (the slashes create the folders), paste the content of that file from the package, and click **Commit changes**.

### 3. Switch on the website
1. **Settings → Pages**. Under *Build and deployment*, Source: **Deploy from a branch**. Branch: **main**, folder: **/docs**. Click **Save**.
2. After 1–2 minutes the site is at `https://<your-user-name>.github.io/kaza-projects/`. The picker is at `…/kaza-projects/picker.html`.

### 4. Set up the survey in KoboToolbox (kf.kobotoolbox.org)
1. **New → Upload an XLSForm**, choose `forms/KAZA_Projects_Kobo_v3.xlsx`. Open it in the form builder once to check it, then **Deploy**.
2. Note the form's ID: it is the part of the address after `/forms/`, e.g. `aBcD1234eFgH5678`.
3. **Form → Collect data**: copy the **online-only** web form link (it looks like `https://ee.kobotoolbox.org/x/AbCdEfGh`).
4. Your API key: click your profile picture → **Account settings → Security**, then display/copy the **API key**. Treat it like a password.

### 5. Connect GitHub to KoboToolbox
1. In GitHub open `config.json` → pencil icon (**Edit**). Paste the form ID into `"kobo_asset_uid": ""` → **Commit changes**.
2. Open `docs/site.json` → **Edit**. Paste the web form link into `"survey_url": ""` → **Commit changes**.
3. **Settings → Secrets and variables → Actions → New repository secret**. Name: `KOBO_TOKEN`. Secret: your API key. **Add secret**. Nobody can read it back, not even you; you can only replace it.

### 6. Run the update
1. **Actions** tab. If asked, click **I understand my workflows, go ahead and enable them**.
2. Choose **Update KAZA projects data → Run workflow → Run workflow**.
3. After a minute the run shows a green tick. Click it to see the summary: how many projects were published and which submissions are waiting for review (by Kobo `_id` only, no names).
4. It then runs by itself every night. The website changes when new submissions are approved.

### 7. Reviewing submissions (the approval step)
1. In KoboToolbox open the form → **Data → Table**.
2. Read the new submission. The run summary on GitHub lists automatic checks for submissions still waiting (missing dates, new organisations, new areas, funding above budget…), by `_id`.
3. Fix answers if needed (**Edit** on the submission), then set **Validation status** to **Approved**. "On hold" means "waiting for information"; "Not approved" keeps it out.
4. The next run (tonight, or **Run workflow** now) publishes it.
5. New areas drawn by people are collected in `reports/candidate_areas.geojson`. When one is right, add it to `data/reference/areas.geojson` (and to the survey's area list) so the next person can pick it.

## If something goes wrong

- **Red cross on a run:** click it, open the failed step and read the last lines. "401" or "403" means the API key or the form ID is wrong.
- **The run cannot save ("Permission denied to github-actions"):** Settings → Actions → General → Workflow permissions → **Read and write permissions** → Save.
- **The site shows old data:** Pages takes a minute or two after each run.
- **Scheduled runs stop:** GitHub pauses schedules in public repositories after 60 days without any change. The nightly run normally saves a new data file each time, which keeps it active; if it ever pauses, the Actions tab shows a button to enable it again.

## Running it on your own computer (optional)

```
pip install numpy
python scripts/update.py                     # starting data only (or Kobo if KOBO_TOKEN is set)
python scripts/update.py --kobo-file x.json  # test with a saved KoboToolbox download
cd docs && python -m http.server              # then open http://localhost:8000
```
