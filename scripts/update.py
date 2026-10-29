"""Rebuild the public KAZA projects data.

  seed data (data/seed)  +  approved KoboToolbox submissions  ->  docs/data/*.json (read by the website)

Run by GitHub Actions every day and on demand. Locally:
    python scripts/update.py                      # seed + Kobo (if KOBO_TOKEN is set)
    python scripts/update.py --kobo-file x.json   # test with a saved Kobo download instead of the API
"""
import csv, datetime, json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kazageo import Grid, rings_of, simplify, merge
import kobo
import dissolve

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, 'config.json')))
OUT = os.path.join(ROOT, 'docs', 'data'); os.makedirs(OUT, exist_ok=True)
REP = os.path.join(ROOT, 'reports'); os.makedirs(REP, exist_ok=True)
TODAY = datetime.date.today().isoformat()
MIN_SHARE = CFG.get('wda_min_share', 0.02)

WDA = {'W_KR': 'Kwando River', 'W_ZCF': 'Zambezi-Chobe Floodplain', 'W_HKC': 'Hwange-Kazuma-Chobe', 'W_KN': 'Khaudum-Ngamiland',
       'W_HMN': 'Hwange-Makgadikgadi-Nxai Pan', 'W_ZMT': 'Zambezi-Mosi-oa-Tunya'}
COUNTRIES = ['Angola', 'Botswana', 'Namibia', 'Zambia', 'Zimbabwe']


def read_csv(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f: return list(csv.DictReader(f))


def num(v):
    try: x = float(v)
    except (TypeError, ValueError): return None
    return x if x > 0 else None


# ---------------- reference data ----------------
ref = json.load(open(os.path.join(ROOT, 'data/reference/areas.geojson')))
AREAS = {f['properties']['area_id']: f['properties'] for f in ref['features']}
AGEOM = {f['properties']['area_id']: f['geometry'] for f in ref['features']}
DISTRICTS = []                                                                  # admin level 2: districts / constituencies (ids D_...)
if os.path.exists(os.path.join(ROOT, 'data/reference/districts.geojson')):
    for f in json.load(open(os.path.join(ROOT, 'data/reference/districts.geojson')))['features']:
        AREAS[f['properties']['area_id']] = f['properties']; AGEOM[f['properties']['area_id']] = f['geometry']; DISTRICTS.append(f['properties']['area_id'])
csegs = {}
if os.path.exists(os.path.join(ROOT, 'data/reference/countries.geojson')):     # KAZA country segments, when supplied
    for f in json.load(open(os.path.join(ROOT, 'data/reference/countries.geojson')))['features']:
        csegs[f['properties']['country'].title()] = f['geometry']
ORGS = {o['org_id']: o['name'] for o in read_csv('data/reference/organisations.csv')}
THEMES = {t['theme_id']: t['label'] for t in read_csv('data/reference/themes.csv')}

# ---------------- seed ----------------
T = {k: read_csv(f'data/seed/{k}.csv') for k in ('projects', 'project_areas', 'project_orgs', 'funding', 'project_themes')}
for o in T['project_orgs']: o['org_name'] = ORGS.get(o['org_id'], o['org_id'])
for f in T['funding']: f['funder_name'] = ORGS.get(f['funder_id'], f['funder_id']); f['amount_usd'] = num(f['amount_usd'])
for p in T['projects']: p['total_budget_usd'] = num(p['total_budget_usd'])
FOOT = {f['properties']['project_id']: f['geometry'] for f in json.load(open(os.path.join(ROOT, 'data/seed/footprints.geojson')))['features']}
NEW_AREAS = {}

# ---------------- KoboToolbox ----------------
kobo_info = {'used': False}
pending_issues = []
subs = None
if '--kobo-file' in sys.argv:
    d = json.load(open(sys.argv[sys.argv.index('--kobo-file') + 1])); subs = d['results'] if isinstance(d, dict) else d
elif os.environ.get('KOBO_TOKEN') and CFG.get('kobo_asset_uid'):
    subs = kobo.fetch_submissions(CFG['kobo_server'], CFG['kobo_asset_uid'], os.environ['KOBO_TOKEN'])
if subs is not None:
    status = lambda s: (s.get('_validation_status') or {}).get('uid', '')
    approved = [s for s in subs if status(s) == 'validation_status_approved']
    waiting = [s for s in subs if status(s) in ('', 'validation_status_on_hold')]
    K, issues = kobo.to_tables(approved, ORGS, AREAS, CFG.get('kobo_server'), os.environ.get('KOBO_TOKEN'))
    _, pending_issues = kobo.to_tables(waiting, ORGS, AREAS, fetch_files=False)
    for k in T: T[k] += K[k]
    for a in K['new_areas']: NEW_AREAS[a['area_id']] = a
    kobo_info = {'used': True, 'submissions': len(subs), 'approved': len(approved), 'waiting_for_review': len(waiting),
                 'not_approved': len(subs) - len(approved) - len(waiting)}
else:
    issues = []

# ---------------- per-project geometry, WDAs, countries ----------------
G = Grid(CFG.get('grid_km', 1.0))
_mask_cache = {}
def amask(aid):
    if aid not in _mask_cache:
        geom = AGEOM.get(aid) or (NEW_AREAS.get(aid) or {}).get('geometry')
        _mask_cache[aid] = G.mask(rings_of(geom)) if geom else None
    return _mask_cache[aid]
WMASK = {k: amask(k) for k in WDA}
KMASK = amask('KAZA')
CMASK = {c: G.mask(rings_of(g)) for c, g in csegs.items()}

links = {}
for r in T['project_areas']: links.setdefault(r['project_id'], []).append(r['area_id'])
wda_rows, geo_of, countries_of, outside, area_of, DSTATS = [], {}, {}, {}, {}, {}
for p in T['projects']:
    pid = p['project_id']; ids = links.get(pid, [])
    parts = [i for i in ids if i not in WDA and i != 'KAZA']
    seed = pid in FOOT
    # display geometry: the curated footprint for seed projects, otherwise the chosen areas put together
    raw = FOOT.get(pid) or merge([AGEOM.get(i) or (NEW_AREAS.get(i) or {}).get('geometry') for i in ids])
    geo_of[pid] = raw
    # one clean outline for the map: merge overlapping/touching parts, close thin gaps, drop tiny pieces and holes
    if raw and dissolve.HAVE_SHAPELY and 'KAZA' not in ids:
        try:
            geo_of[pid], area_of[pid] = dissolve.clean_outline([raw], CFG.get('gap_close_m', 250), CFG.get('min_piece_km2', 2.0), DSTATS)
        except Exception as e:                      # keep the uncleaned outline rather than stopping the whole update
            DSTATS['failed'] = DSTATS.get('failed', 0) + 1; print(f'  outline clean-up failed for {pid}: {e.__class__.__name__}: {e}')
    # mask used for the 2% rule: listed + new areas (not whole WDAs / whole KAZA)
    # seed projects: the curated footprint (the shape drawn for KAZA_Projects_24) decides
    masks = ([G.mask(rings_of(FOOT[pid]))] if FOOT.get(pid) else []) if seed else [amask(i) for i in parts if amask(i) is not None]
    pm = np.logical_or.reduce(masks) if masks else None
    if 'KAZA' in ids:
        for k in WDA: wda_rows.append({'project_id': pid, 'wda_id': k, 'basis': 'Whole KAZA', 'share': None, 'counted': True})
        countries_of[pid] = COUNTRIES[:]
        continue
    ticked = [] if seed else [k for k in WDA if k in ids]
    for k in ticked: wda_rows.append({'project_id': pid, 'wda_id': k, 'basis': 'Whole WDA', 'share': None, 'counted': True})
    if pm is not None and pm.any():
        n = pm.sum()
        for k, wm in WMASK.items():
            if k in ticked: continue
            share = float((pm & wm).sum() / n)
            if share > 0: wda_rows.append({'project_id': pid, 'wda_id': k, 'basis': f'{MIN_SHARE:.0%} rule', 'share': round(share, 4), 'counted': share >= MIN_SHARE})
        outside[pid] = float((pm & ~KMASK).sum() / n)
    # Countries: what people report + the country of each listed area / district they chose.
    # The map (country segments) is only used where no country is given: drawn or uploaded areas and whole WDAs,
    # with a 5% threshold so small border differences between layers do not add a country.
    cs = {c.strip().title() for c in (p.get('countries') or '').replace(';', ' ').split()}
    cs |= {(AREAS.get(i) or {}).get('country', '').title() for i in ids if i in AREAS}
    measure = [amask(i) for i in ids if i in NEW_AREAS and amask(i) is not None] + [WMASK[k] for k in ticked]
    if CMASK and measure:
        mm = np.logical_or.reduce(measure); n = mm.sum()
        if n: cs |= {c for c, cm in CMASK.items() if (mm & cm).sum() / n >= CFG.get('country_min_share', 0.05)}
    countries_of[pid] = sorted(cs & set(COUNTRIES))
for pid, share in outside.items():
    if pid.startswith('K') and share > 0.10: issues.append({'project_id': pid, 'issue': 'Area outside KAZA', 'detail': f'{share:.0%} of the mapped area lies outside the KAZA boundary'})
for p in T['projects']:
    if p['project_id'].startswith('K') and not geo_of.get(p['project_id']): issues.append({'project_id': p['project_id'], 'issue': 'No map shape', 'detail': ''})

# ---------------- flattened layer ----------------
def group(rows):
    g = {}
    for r in rows: g.setdefault(r['project_id'], []).append(r)
    return g
FUN, ORG, THM, WDR = group(T['funding']), group(T['project_orgs']), group(T['project_themes']), group(wda_rows)
def area_name(i):
    if i == 'KAZA': return 'Whole KAZA TFCA'
    if i in WDA: return WDA[i] + ' WDA'
    return (AREAS.get(i) or NEW_AREAS.get(i) or {}).get('name', i)
def status(p):
    end = p.get('end_date') or ''
    if p.get('end_type') == 'ongoing' or not end: return 'Active'          # agreed rule: no end date = active
    return 'Active' if end[:10] >= TODAY else 'Expired'

features, flat = [], []
published = [p for p in T['projects'] if p.get('public_ok', 'yes') == 'yes' and p.get('title')]
for p in published:
    pid = p['project_id']
    fu = FUN.get(pid, []); og = ORG.get(pid, []); th = [t['theme_id'] for t in THM.get(pid, [])]
    counted = [w['wda_id'] for w in WDR.get(pid, []) if w['counted']]
    ids = links.get(pid, [])
    donors = []
    for f in fu:
        lab = f['funder_name'] + (f' (via {f["channel"]})' if f.get('channel') else '')
        if lab not in donors: donors.append(lab)
    scale = 'Whole KAZA' if 'KAZA' in ids else ('Whole WDA' if any(i in WDA for i in ids) else 'Local')
    props = {
        'project_id': pid, 'title': p['title'], 'lead_org': p.get('lead_org', ''), 'status': status(p),
        'start_date': (p.get('start_date') or '')[:10] or None, 'end_date': (p.get('end_date') or '')[:10] or None,
        'ongoing': 'yes' if p.get('end_type') == 'ongoing' or not p.get('end_date') else 'no',
        'budget_usd': p.get('total_budget_usd'),
        'funding_reported_usd': round(sum(f['amount_usd'] or 0 for f in fu), 2) or None,
        'themes': '; '.join(THEMES.get(t, t) for t in th),
        'funders': '; '.join(sorted({f['funder_name'] for f in fu})),
        'donors': '; '.join(donors),
        'primary_partners': '; '.join(o['org_name'] for o in og if o['role'] == 'primary'),
        'local_partners': '; '.join(o['org_name'] for o in og if o['role'] == 'local'),
        'areas': '; '.join(area_name(i) for i in ids),
        'countries': '; '.join(countries_of.get(pid, [])),
        'wdas': '; '.join(WDA[k] for k in WDA if k in counted) or ('Outside WDAs' if geo_of.get(pid) else ''),
        'scale': scale, 'larger_programme': p.get('larger_programme') or None, 'source': p.get('source', ''),
        'map_area_km2': area_of.get(pid),
    }
    for k in WDA: props['wda_' + k[2:].lower()] = 1 if k in counted else 0
    for t in THEMES: props['theme_' + t] = 1 if t in th else 0
    flat.append(props)
    g = AGEOM['KAZA'] if 'KAZA' in ids else geo_of.get(pid)
    features.append({'type': 'Feature', 'properties': props, 'geometry': simplify(g, CFG.get('display_tolerance', 0.004)) if g else None})

def dump(name, obj):
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f: json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
dump('kaza_projects.geojson', {'type': 'FeatureCollection', 'name': 'kaza_projects', 'features': features})
pub_ids = {p['project_id'] for p in published}
dump('tables.json', {
    'funding': [{'project_id': f['project_id'], 'funder': f['funder_name'], 'channel': f.get('channel') or '', 'amount_usd': f['amount_usd'], 'type': f.get('type', '')}
                for f in T['funding'] if f['project_id'] in pub_ids],
    'organisations': [{'project_id': o['project_id'], 'org': o['org_name'], 'role': o['role']} for o in T['project_orgs'] if o['project_id'] in pub_ids],
    'wdas': [w for w in wda_rows if w['project_id'] in pub_ids],
    'themes': THEMES, 'wda_names': WDA})
dump('map_layers.json', {
    'kaza': simplify(AGEOM['KAZA'], 0.01),
    'wdas': [{'id': k, 'name': WDA[k], 'geometry': simplify(AGEOM[k], 0.01)} for k in WDA],
    'countries': [{'name': c, 'geometry': simplify(g, 0.01)} for c, g in sorted(csegs.items())]})
# area list for the map picker (outer rings only, clockwise like shapefile rings)
pick = []
for k, a in AREAS.items():
    if not a.get('in_picker'): continue
    rings = [[pt for pt in poly[0][::-1]] for poly in (AGEOM[k]['coordinates'] if AGEOM[k] else [])]
    pick.append({'id': k, 'n': a['name'], 't': a['type'], 'c': a['country'], 'w': a.get('wda') or '', 'km2': a.get('km2'), 'g': rings})
pick.sort(key=lambda a: -(a['km2'] or 0))
dist = [{'id': k, 'n': AREAS[k]['name'], 't': AREAS[k]['type'], 'p': AREAS[k].get('province', ''), 'c': AREAS[k]['country'], 'km2': AREAS[k].get('km2'),
         'g': [poly[0][::-1] for poly in simplify(AGEOM[k], 0.003)['coordinates']]} for k in DISTRICTS]
dump('picker_areas.json', {'areas': pick, 'districts': dist,
                           'wdas': [{'id': k, 'n': WDA[k], 'g': [poly[0][::-1] for poly in simplify(AGEOM[k], 0.004)['coordinates']]} for k in WDA],
                           'kaza': [poly[0][::-1] for poly in simplify(AGEOM['KAZA'], 0.004)['coordinates']]})
counts = {'projects_published': len(published), 'active': sum(f['status'] == 'Active' for f in flat),
          'seed_projects': sum(p['project_id'].startswith('P') for p in published), 'kobo_projects': sum(p['project_id'].startswith('K') for p in published),
          'not_published_no_consent': sum(1 for p in T['projects'] if p.get('public_ok', 'yes') != 'yes')}
dump('meta.json', {'updated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), 'counts': counts, 'kobo': kobo_info,
                   'rules': {'status': 'No end date = Active', 'wda': f'Whole KAZA = all WDAs; a ticked whole WDA counts only in that WDA; '
                             f'listed and drawn areas count in a WDA when at least {MIN_SHARE:.0%} of their area lies in it',
                             'funding': 'German Government is the funder; KfW, BMZ, GIZ, IKI, BMBF and BENGO are channels'}})

# ---------------- reports ----------------
# checks on approved records (published: no personal data; not published: issue only, no details)
with open(os.path.join(REP, 'checks_approved.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['project_id', 'issue', 'detail']); w.writeheader()
    for i in issues: w.writerow(i if i['project_id'] in pub_ids else {**i, 'detail': ''})
new_feats = [{'type': 'Feature', 'properties': {k: a[k] for k in ('area_id', 'project_id', 'name', 'country', 'how')}, 'geometry': a['geometry']}
             for a in NEW_AREAS.values() if a['project_id'] in pub_ids and a['geometry']]
with open(os.path.join(REP, 'candidate_areas.geojson'), 'w', encoding='utf-8') as f:
    json.dump({'type': 'FeatureCollection', 'features': new_feats}, f, ensure_ascii=False)
lines = ['## KAZA projects update', '', f'Published projects: **{counts["projects_published"]}** '
         f'({counts["seed_projects"]} from the starting data, {counts["kobo_projects"]} from KoboToolbox); active: {counts["active"]}.', '']
if kobo_info['used']:
    lines += [f'KoboToolbox: {kobo_info["submissions"]} submissions, {kobo_info["approved"]} approved, {kobo_info["waiting_for_review"]} waiting for review.', '']
    if pending_issues:
        lines += ['### Waiting for review (look these up in KoboToolbox by their _id)', '', '| Kobo _id | Issue |', '|---|---|']
        lines += [f'| {i["project_id"][1:]} | {i["issue"]} |' for i in pending_issues]
else:
    lines += ['KoboToolbox not connected (no KOBO_TOKEN secret or no kobo_asset_uid in config.json): starting data only.']
if dissolve.HAVE_SHAPELY:
    lines += ['', f'Map outlines cleaned for {DSTATS.get("projects", 0)} projects: {DSTATS.get("pieces_merged", 0)} overlapping or touching parts merged, '
              f'{DSTATS.get("pieces_removed", 0)} small pieces and {DSTATS.get("holes_removed", 0)} small holes removed'
              + (f'; clean-up failed for {DSTATS["failed"]} (their outlines were kept as they are).' if DSTATS.get('failed') else '.')]
else:
    lines += ['', 'Shapely is not installed, so map outlines were not merged or cleaned.']
summary = '\n'.join(lines)
print(summary)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    open(os.environ['GITHUB_STEP_SUMMARY'], 'a').write(summary + '\n')
