"""Read KAZA project submissions from KoboToolbox (API v2) and turn them into the same linked tables as the seed data.

Only the standard library is used. The API key comes from the KOBO_TOKEN environment variable
(a GitHub secret), never from a file in the repository.
"""
import base64, json, os, re, urllib.parse, urllib.request
from kazageo import parse_odk_geoshape, read_shape_file

# Organisations that pass German Government money on. When one of them is entered as the funder,
# the funder becomes "German Government" and the organisation becomes the channel (agreed rule: KfW etc. are not separate donors).
GERMAN_GOV = 'O029'
GERMAN_CHANNELS = {'O030': 'KfW', 'O092': 'BMZ', 'O079': 'GIZ', 'O141': 'IKI', 'O107': 'BMBF', 'O065': 'BENGO (via WWF Germany)'}


def _get(url, token, raw=False):
    req = urllib.request.Request(url, headers={'Authorization': f'Token {token}', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    return data if raw else json.loads(data)


def fetch_submissions(server, asset_uid, token, status=None):
    """All submissions of a form (optionally only one validation status), following the API's pages."""
    q = {'format': 'json', 'limit': 1000}
    if status: q['query'] = json.dumps({'_validation_status.uid': status})
    url = f'{server.rstrip("/")}/api/v2/assets/{asset_uid}/data/?' + urllib.parse.urlencode(q)
    out = []
    while url:
        page = _get(url, token)
        out += page.get('results', [])
        url = page.get('next')
    return out


def _flat(d):
    """Strip group prefixes ('grp_proj/proj_title' -> 'proj_title'); repeats stay lists of flat dicts."""
    out = {}
    for k, v in d.items():
        key = k.split('/')[-1]
        out[key] = [_flat(x) for x in v] if isinstance(v, list) and v and isinstance(v[0], dict) and not k.startswith('_') else v
    return out


def _multi(v):
    return [x for x in str(v or '').split() if x]


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None          # agreed rule: 0 means "no answer"


def _norm_file(name):
    return re.sub(r'[^a-z0-9.]+', '_', os.path.basename(str(name or '')).lower())


# ---------- the location code from the map picker ----------
# "KAZA-LOC1 | <summary> | <data>": data is base64url JSON {v, k, w, a, d, s:[{n, h, p:[encoded rings]}]};
# rings are encoded polylines in [lon, lat] order with precision 1e-4 degrees (see docs/picker.html).
def _decode_ring(s, prec=1e4):
    pts, i, x, y = [], 0, 0, 0
    while i < len(s):
        vals = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(s[i]) - 63; i += 1
                result |= (b & 0x1f) << shift; shift += 5
                if b < 0x20: break
            vals.append(~(result >> 1) if result & 1 else result >> 1)
        x += vals[0]; y += vals[1]
        pts.append([x / prec, y / prec])
    if pts and pts[0] != pts[-1]: pts.append(pts[0])
    return pts


def decode_location_code(text):
    """Returns the decoded dict, or None when there is no code; raises ValueError when the code is damaged."""
    text = (text or '').strip()
    if not text: return None
    if not text.startswith('KAZA-LOC1'): raise ValueError('does not start with KAZA-LOC1')
    data = re.sub(r'\s+', '', text.rsplit('|', 1)[-1])
    try:
        o = json.loads(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8'))
        for s in o.get('s', []):
            s['rings'] = [_decode_ring(r) for r in s.get('p', [])]
    except Exception as e:
        raise ValueError(f'the code is incomplete or damaged ({e.__class__.__name__}); it may have been cut off when copying')
    return o


def to_tables(submissions, orgs, areas, server=None, token=None, fetch_files=True):
    """Kobo submissions -> dict of table rows + new-area shapes + review issues.

    orgs:  {org_id: name}; areas: {area_id: properties}
    """
    T = {k: [] for k in ('projects', 'project_areas', 'project_orgs', 'funding', 'project_themes', 'new_areas')}
    issues = []
    def flag(pid, what, detail=''): issues.append({'project_id': pid, 'issue': what, 'detail': detail})
    oname = lambda code, other: (other or 'Other (not named)') if code == 'other' else ('Funder not disclosed' if code == 'undisclosed' else orgs.get(code, code))

    for raw in submissions:
        s = _flat(raw)
        pid = f'K{s.get("_id")}'
        status = (raw.get('_validation_status') or {}).get('uid', '')
        lead = oname(s.get('submit_org'), s.get('submit_org_oth'))
        end_type = s.get('end_type') or ''
        T['projects'].append({
            'project_id': pid, 'title': (s.get('proj_title') or '').strip(), 'lead_org': lead,
            'start_date': s.get('start_date') or '', 'end_date': (s.get('end_date') or '') if end_type == 'date' else '', 'end_type': end_type,
            'total_budget_usd': _num(s.get('total_budget')) if s.get('budget_known') == 'yes' else None,
            'part_of_larger': s.get('part_larger') or '', 'larger_programme': s.get('larger_name') or '',
            'location_text': '', 'countries': ' '.join(set(_multi(s.get('loc_countries'))) | {n.get('na_country') for n in s.get('new_areas') or [] if n.get('na_country')}),
            'public_ok': s.get('public_ok') or '', 'source': 'KoboToolbox',
            'submitted': (s.get('_submission_time') or '')[:10], 'review_status': status,
            'goal': s.get('proj_goal') or '', 'iati_id': s.get('iati_id') or '', 'doc_links': s.get('doc_links') or ''})
        # never copied: contact_name, contact_email (personal data)
        if not T['projects'][-1]['title']: flag(pid, 'Incomplete record', 'no title')
        if not s.get('start_date'): flag(pid, 'Start date missing')
        if end_type == 'date' and not s.get('end_date'): flag(pid, 'End date missing')
        if s.get('submit_org') == 'other': flag(pid, 'New organisation', f'lead: {lead}')
        if s.get('public_ok') != 'yes': flag(pid, 'No consent to publish')

        for t in _multi(s.get('themes')):
            T['project_themes'].append({'project_id': pid, 'theme_id': t})
        if 'other' in _multi(s.get('themes')): flag(pid, 'Theme "Other"', s.get('theme_other') or '')

        for col, role, oth in (('pip', 'primary', 'pip_other'), ('lip', 'local', 'lip_other')):
            for code in _multi(s.get(col)):
                if code == 'other':
                    for nm in [x.strip() for x in (s.get(oth) or '').split(';') if x.strip()] or ['Other (not named)']:
                        T['project_orgs'].append({'project_id': pid, 'org_id': '', 'org_name': nm, 'role': role})
                        flag(pid, 'New organisation', f'{role} partner: {nm}')
                else:
                    T['project_orgs'].append({'project_id': pid, 'org_id': code, 'org_name': orgs.get(code, code), 'role': role})
        if not _multi(s.get('pip')): flag(pid, 'No implementing partner')

        for f in s.get('funding') or []:
            fid = f.get('funder') or ''
            ch = (f.get('channel') or '') if f.get('via_channel') == 'yes' else ''
            if not fid: flag(pid, 'Funding entry without a funder'); continue
            if fid in GERMAN_CHANNELS:               # e.g. KfW entered as the funder -> German Government via KfW
                flag(pid, 'German channel entered as funder', f'{GERMAN_CHANNELS[fid]} recorded as channel of German Government')
                ch, fid = fid, GERMAN_GOV
            if ch and ch == fid: flag(pid, 'Funder and channel are the same', orgs.get(fid, fid)); ch = ''
            # amount: "All of it" = the whole project budget; "Part of it" = the amount typed; "Not known" = blank
            share = f.get('fund_share') or ''
            if share == 'all':
                amount, basis = T['projects'][-1]['total_budget_usd'], 'Whole budget (answered "All of it")'
            elif share == 'unknown':
                amount, basis = None, 'Not known or not shared'
            else:
                amount, basis = _num(f.get('fund_amount')), 'Reported in the survey'
            T['funding'].append({'project_id': pid, 'funder_id': fid if fid not in ('other', 'undisclosed') else '',
                                 'funder_name': oname(fid, f.get('funder_oth')), 'channel': oname(ch, f.get('channel_oth')) if ch else '',
                                 'amount_usd': amount, 'type': f.get('fund_type') or '', 'basis': basis})
            if fid == 'other': flag(pid, 'New organisation', f'funder: {f.get("funder_oth")}')
            if ch == 'other': flag(pid, 'New organisation', f'channel: {f.get("channel_oth")}')
        fsum = sum(x['amount_usd'] or 0 for x in T['funding'] if x['project_id'] == pid)
        b = T['projects'][-1]['total_budget_usd']
        if b and fsum > b * 1.001: flag(pid, 'Funding exceeds total budget', f'{fsum:,.0f} > {b:,.0f}')
        n_all = sum(1 for f in s.get('funding') or [] if f.get('fund_share') == 'all')
        if n_all > 1: flag(pid, 'Several funders give "all of the budget"', f'{n_all} funders answered "All of it"')
        if b and b > 100_000_000: flag(pid, 'Very large budget', f'{b:,.0f}')

        # ---- locations: the code from the map picker, or (without the map) the list questions ----
        try:
            code = decode_location_code(s.get('loc_code'))
        except ValueError as e:
            code = None; flag(pid, 'Location code could not be read', str(e))
        if code is not None:
            if code.get('k'):
                T['project_areas'].append({'project_id': pid, 'area_id': 'KAZA'})
            else:
                for a in code.get('w', []) + code.get('a', []) + code.get('d', []):
                    T['project_areas'].append({'project_id': pid, 'area_id': a})
                    if a not in areas and not a.startswith('W_'): flag(pid, 'Unknown area ID', a)
                for i, sh in enumerate(code.get('s', []), 1):
                    nid = f'{pid}-M{i}'
                    geom = {'type': 'MultiPolygon', 'coordinates': [[r] for r in sh['rings'] if len(r) >= 4]}
                    how = 'drawn on the map' if sh.get('h') == 'drawn' else (sh.get('h') or 'map').replace('file ', 'uploaded file ')
                    T['new_areas'].append({'area_id': nid, 'project_id': pid, 'name': sh.get('n') or 'unnamed', 'country': '',
                                           'description': '', 'how': how, 'geometry': geom if geom['coordinates'] else None})
                    T['project_areas'].append({'project_id': pid, 'area_id': nid})
                    flag(pid, 'New area to review', f'{sh.get("n") or "unnamed"} ({how})')
        elif s.get('whole_kaza') == 'yes':
            T['project_areas'].append({'project_id': pid, 'area_id': 'KAZA'})
        else:
            for w in _multi(s.get('loc_wdas')): T['project_areas'].append({'project_id': pid, 'area_id': w})
            for c in ('angola', 'botswana', 'namibia', 'zambia', 'zimbabwe'):
                for a in _multi(s.get(f'areas_{c}')):
                    T['project_areas'].append({'project_id': pid, 'area_id': a})
                    if a not in areas: flag(pid, 'Unknown area ID', a)
            for a in _multi(s.get('loc_districts')):            # whole districts / constituencies (admin level 2)
                T['project_areas'].append({'project_id': pid, 'area_id': a})
                if a not in areas: flag(pid, 'Unknown district ID', a)
        files = {_norm_file(a.get('filename')): a for a in raw.get('_attachments') or []}
        for i, na in enumerate(s.get('new_areas') or [], 1):
            nid = f'{pid}-A{i}'; nm = (na.get('na_name') or '').strip() or 'unnamed'
            geom, how, kid = parse_odk_geoshape(na.get('na_shape')), 'drawn', ''
            fn = na.get('na_file')
            if fn:
                att = files.get(_norm_file(fn))
                if att and fetch_files and token:
                    try:
                        g2, props = read_shape_file(fn, _get(att.get('download_url') or att.get('download_large_url'), token, raw=True))
                    except Exception as e:  # keep going; the file is checked by hand
                        g2, props = None, {}; flag(pid, 'Uploaded file could not be read', f'{fn}: {e.__class__.__name__}')
                    if g2:
                        if geom: flag(pid, 'Both drawn and uploaded', f'{nm}: using the uploaded file')
                        geom, how = g2, f'uploaded file {fn}'
                        kid = str(props.get('KAZA_ID') or props.get('kaza_id') or '').split('.')[0]
                    elif fn.lower().endswith(('.zip', '.kmz')):
                        flag(pid, 'Uploaded file needs converting', f'{fn}: convert to GeoJSON by hand')
                elif not att:
                    flag(pid, 'Uploaded file not found', fn)
            if kid and kid in areas:
                flag(pid, 'Uploaded area is already in the list', f'{nm} = {areas[kid]["name"]} [{kid}]')
                T['project_areas'].append({'project_id': pid, 'area_id': kid}); continue
            T['new_areas'].append({'area_id': nid, 'project_id': pid, 'name': nm, 'country': na.get('na_country') or '',
                                   'description': na.get('na_desc') or '', 'how': how if geom else 'no shape', 'geometry': geom})
            T['project_areas'].append({'project_id': pid, 'area_id': nid})
            flag(pid, 'New area to review' if geom else 'Area without a shape', f'{nm} ({how if geom else "description only"})')
    return T, issues
