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
| `docs/site.json` | The survey link the picker opens, and the CARTO key for the background map | you, once |
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
- **Map outlines:** each project's areas are merged into one clean outline for the map (overlapping and touching parts dissolved, gaps narrower than 250 m closed, separate pieces and holes smaller than 2 km² removed; a project that is only a small site keeps its largest piece). This uses Shapely, which the workflow installs. The thresholds can be changed in `config.json` (`gap_close_m`, `min_piece_km2`). Only the outline changes: the list of areas, and the WDA and country counts, are not affected.
- **Funding:** German Government is the funder; KfW, BMZ, GIZ, IKI, BMBF and BENGO are channels. If someone enters KfW as the funder, it is recorded as German Government via KfW.
- **Amounts:** in the starting data (from Survey123, which stores an unanswered number as 0) a budget or amount of 0 means "no answer". KoboToolbox leaves unanswered numbers empty, and the form only accepts amounts above zero, so this does not arise for new submissions.
- **Publishing:** only submissions that are **Approved** in KoboToolbox **and** where the submitter said the project may be shown publicly. Contact names and e-mails are never copied into this repository.

## Background maps on the dashboard

The dashboard map has a switch for the background: **Map** (default), **Satellite** and **None** (plain). Each visitor's choice is remembered in their own browser.

- **Map:** CARTO Positron (Dark Matter in dark mode), with OpenStreetMap data: towns, roads and borders. Free for non-commercial use with a free CARTO key ([carto.com/basemaps/apikey](https://carto.com/basemaps/apikey/), no account needed). Without a key CARTO shows an "API key required" watermark. Add the key to `docs/site.json`:
  ```
  { "survey_url": "…your survey link…", "carto_key": "…your key…" }
  ```
- **Satellite:** EOxCloudless, a cloud-free Sentinel-2 mosaic (10 m) by EOX. No key needed; free for non-commercial use (CC BY-NC-SA 4.0). The 2025 mosaic is used; another year can be set with `"satellite_year": 2024` in `site.json`.
- Both require the credit line, which the dashboard shows under the map. Don't remove it.

## Survey version 4: IATI-compatible data capture

The v4 form (`forms/KAZA_Projects_Kobo_v4.xlsx`) records information in the structure of the IATI Standard, so projects can be matched with IATI and donor registries. Nothing is published to IATI.

| Asked in the survey | IATI element | Codes |
|---|---|---|
| Stage of the project | activity-status | 1 pipeline … 6 suspended (Cancelled, Suspended and Pipeline override the date rule on the dashboard) |
| Start date; current and original end date | activity-date | 1/2 start; 3 planned end (original kept separately) |
| IATI identifier(s); funders' project numbers | iati-identifier; other-identifier | |
| Larger programme name and identifier | related-activity | type 1 (parent) |
| Amounts (in USD, confirmed), date agreed | value @currency, @value-date | always USD |
| Budget scope and KAZA share | – | the dashboard shows the KAZA share when known |
| Type of funding | finance-type | 110 grant, 421 loan, 422 reimbursable grant, 510 equity, 1100 guarantee (in-kind has no code) |
| Funder / channel / lead / partners | participating-org @role | 1 Funding, 3 Extending, 2 Accountable, 4 Implementing |
| Type of a new organisation | participating-org @type | OrganisationType (10 government … 80 academic) |
| Four "main objective" questions | policy-marker | 5 biodiversity, 7 adaptation, 6 mitigation, 8 desertification; significance 2/1/0 |
| Themes | sector (vocabulary 1) | OECD DAC 5-digit codes in `data/reference/themes.csv` |
| Countries, districts | recipient-country; location administrative | ISO 3166; GADM ids in `districts.geojson` |

**Amounts are in US dollars.** The form asks for all amounts in USD and, after the total budget, asks the respondent to confirm: "Are you certain this is in US dollars ($ USD)?". Answering "No" points them to a currency converter and the form can't be submitted until they confirm. No exchange rates are kept in this repository; `config.json` only needs `"fx_to_usd": { "USD": 1.0 }`.

**Reference columns to fill in over time:** `organisations.csv` → `iati_org_id` (from org-id.guide), `iati_org_type`, `crs_channel_code`, `website`; `areas.geojson` → `wdpa_id` (World Database on Protected Areas). They are not needed for the dashboard, but they make automatic matching with IATI and other registries possible.

**Other landscapes.** The form builder takes the landscape name as a setting; the area, district and WDA lists come from the reference files. A new landscape needs its own reference files and its own repository (or folder), and can reuse the scripts and the form structure unchanged.

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
3. **Check the locations:** copy the text in "Location code" and open the picker in review mode, `https://<your-user-name>.github.io/kaza-projects/picker.html?review`. Paste the code and click **Show on map**. Correct it if needed: remove or add areas, rename shapes, or click **edit corners** on a drawn or uploaded shape (drag a corner to move it, click or drag a small dot on an edge to add one, double-click a corner to delete it; **Undo**, **Done**, **Cancel changes**). Then click **Copy location code**. Review mode never changes the picker selection saved in your browser.
4. Fix answers if needed (**Edit** on the submission; paste the corrected location code there), then set **Validation status** to **Approved**. "On hold" means "waiting for information"; "Not approved" keeps it out.
5. The next run (tonight, or **Run workflow** now) publishes it.
6. New areas drawn by people are collected in `reports/candidate_areas.geojson`. When one is right, add it to `data/reference/areas.geojson` (and to the survey's area list) so the next person can pick it.

## Changing the official areas

The areas people can pick are in `data/reference/areas.geojson`. The picker and the nightly update read this file; the survey's drop-down list is part of the KoboToolbox form.

- **Change a boundary or a name:** download the file (open it on GitHub → **Download raw file**), edit it in QGIS or ArcGIS Pro, keep the `area_id` unchanged, save as GeoJSON in WGS 84 (EPSG:4326, 5 decimals is plenty), and upload it to `data/reference/` in place of the old one. After the next run the picker shows the new outline, and every KoboToolbox project that lists the area uses it (outline, WDA and country counts). The 187 starting projects keep their own outlines from KAZA_Projects_24.
- **Add an area** (for example one from `reports/candidate_areas.geojson`): add the feature with a new, unique `area_id` (e.g. `A0001`, `A0002`, never reused), `name`, `type`, `country` (angola, botswana, namibia, zambia or zimbabwe), `wda` (optional), `level` = `3 Named area`, `in_picker` = `1`. It appears in the picker after the next run. For the survey's drop-down list, add it to the `areas` choice list of the form as well (name = the `area_id`).
- **Remove an area:** don't delete it, because older submissions refer to its `area_id`. Set `in_picker` to `0` instead.
- The run summary lists problems in the file (a missing or duplicate `area_id`, a feature without a polygon). Single-part polygons saved by GIS tools are accepted.

## If something goes wrong

- **Red cross on a run:** click it, open the failed step and read the last lines. "401" or "403" means the API key or the form ID is wrong.
- **The run cannot save ("Permission denied to github-actions"):** Settings → Actions → General → Workflow permissions → **Read and write permissions** → Save.
- **The site shows old data:** Pages takes a minute or two after each run.
- **Scheduled runs stop:** GitHub pauses schedules in public repositories after 60 days without any change. The nightly run normally saves a new data file each time, which keeps it active; if it ever pauses, the Actions tab shows a button to enable it again.

## Running it on your own computer (optional)

```
pip install numpy shapely
python scripts/update.py                     # starting data only (or Kobo if KOBO_TOKEN is set)
python scripts/update.py --kobo-file x.json  # test with a saved KoboToolbox download
cd docs && python -m http.server              # then open http://localhost:8000
```
