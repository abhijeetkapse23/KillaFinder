#!/usr/bin/env python3
"""Correct fort coordinates in assets/forts.json using OpenStreetMap + Wikidata.

For every fort we look for a same-named fort/castle/peak near our stored
coordinates. If one is found, we take its location. Every change is written
to COORDINATE_REPORT.md so it can be reviewed.

Usage: python3 scripts/fix_coords.py [--offline osm.json wd.json]
"""
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

FORTS = 'assets/forts.json'
REPORT = 'COORDINATE_REPORT.md'
UA = 'KillaFinder/1.0 (https://github.com/abhijeetkapse23/KillaFinder)'

OVERPASS_URLS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]
OVERPASS_QUERY = r"""
[out:json][timeout:240];
area["name"="Maharashtra"]["admin_level"="4"]->.mh;
(
  nwr["historic"~"^(fort|castle|citadel|fortification|city_gate)$"](area.mh);
  nwr["historic"="ruins"](area.mh);
  nwr["castle_type"](area.mh);
  nwr["natural"="peak"]["name"~"(gad|garh|gadh|ghad|durg|fort|killa|qila)",i](area.mh);
  nwr["tourism"]["name"~"(gad|garh|gadh|ghad|durg|fort|killa|qila)",i](area.mh);
);
out center tags;
"""

WIKIDATA_URL = 'https://query.wikidata.org/sparql'
WD_QUERY_FULL = """
SELECT ?item ?lat ?lon ?en ?mr (GROUP_CONCAT(DISTINCT ?alt; separator="|") AS ?alts) WHERE {
  VALUES ?cls { wd:Q57821 wd:Q1785071 wd:Q23413 wd:Q57831 }
  ?item wdt:P31/wdt:P279* ?cls .
  ?item wdt:P131* wd:Q1191 .
  ?item p:P625/psv:P625 [ wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon ] .
  OPTIONAL { ?item rdfs:label ?en FILTER(LANG(?en)="en") }
  OPTIONAL { ?item rdfs:label ?mr FILTER(LANG(?mr)="mr") }
  OPTIONAL { ?item skos:altLabel ?alt FILTER(LANG(?alt)="en") }
} GROUP BY ?item ?lat ?lon ?en ?mr
"""
WD_QUERY_SIMPLE = WD_QUERY_FULL.replace('wdt:P31/wdt:P279* ?cls', 'wdt:P31 ?cls')


def http(url, data=None, accept='application/json', timeout=300):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': UA, 'Accept': accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def fetch_osm():
    body = urllib.parse.urlencode({'data': OVERPASS_QUERY}).encode()
    for url in OVERPASS_URLS:
        for attempt in range(2):
            try:
                data = http(url, data=body)
                out = []
                for e in data.get('elements', []):
                    t = e.get('tags', {})
                    lat = e.get('lat', e.get('center', {}).get('lat'))
                    lon = e.get('lon', e.get('center', {}).get('lon'))
                    names = [t[k] for k in ('name', 'name:en', 'alt_name', 'old_name',
                                            'alt_name:en', 'official_name') if k in t]
                    names = [p.strip() for n in names for p in n.split(';')]
                    if lat is None or not names:
                        continue
                    kind = t.get('historic') or t.get('natural') or t.get('tourism') or ''
                    out.append({'names': names, 'lat': lat, 'lon': lon, 'mr': t.get('name:mr'),
                                'kind': kind, 'src': 'OSM'})
                print(f'OSM: {len(out)} candidates from {url}')
                return out
            except Exception as ex:  # noqa: BLE001
                print(f'OSM {url} attempt {attempt + 1} failed: {ex}')
                time.sleep(20)
    return []


def fetch_wikidata():
    for q in (WD_QUERY_FULL, WD_QUERY_SIMPLE):
        try:
            url = WIKIDATA_URL + '?' + urllib.parse.urlencode({'query': q, 'format': 'json'})
            data = http(url, accept='application/sparql-results+json')
            out = []
            for b in data['results']['bindings']:
                names = [b[k]['value'] for k in ('en',) if k in b]
                if 'alts' in b and b['alts']['value']:
                    names += b['alts']['value'].split('|')
                if not names:
                    continue
                out.append({'names': names, 'lat': float(b['lat']['value']),
                            'lon': float(b['lon']['value']),
                            'mr': b.get('mr', {}).get('value'), 'kind': 'wikidata',
                            'src': 'Wikidata'})
            print(f'Wikidata: {len(out)} candidates')
            return out
        except Exception as ex:  # noqa: BLE001
            print(f'Wikidata query failed: {ex}')
    return []


STOP_WORDS = {'fort', 'forts', 'killa', 'kille', 'qila', 'the', 'of', 'durg', 'castle', 'gadi', 'gadhi'}


def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    words = [w for w in re.split(r'[^a-z]+', s) if w and w not in STOP_WORDS]
    s = ''.join(words)
    s = re.sub(r'(garh|gadh|ghad|ghar)$', 'gad', s)
    s = s.replace('w', 'v').replace('z', 'j').replace('ph', 'f')
    s = re.sub(r'([kgtdbpcjs])h', r'\1', s)
    s = re.sub(r'(.)\1+', r'\1', s)
    s = s.replace('ee', 'i').replace('oo', 'u')
    return s


def variants(name):
    out = {name}
    m = re.match(r'^(.*?)\s*\((.*?)\)\s*(.*)$', name)
    if m:
        base = (m.group(1) + ' ' + m.group(3)).strip()
        out |= {base, m.group(2)}
    return {norm(v) for v in out if norm(v)}


def km(a_lat, a_lon, b_lat, b_lon):
    r = math.radians
    x = (math.sin(r(b_lat - a_lat) / 2) ** 2 +
         math.cos(r(a_lat)) * math.cos(r(b_lat)) * math.sin(r(b_lon - a_lon) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(x))


def assign(forts, cands):
    """Match forts to candidates one-to-one: best name score first, then nearest.

    Returns {fort index: (candidate, distance_km, score)}.
    """
    pairs = []
    for i, f in enumerate(forts):
        fv = variants(f['name'])
        for j, c in enumerate(cands):
            d = km(f['lat'], f['lon'], c['lat'], c['lon'])
            if d > 40:
                continue
            score = 0.0
            for cn in c['names']:
                for a in variants(cn):
                    for b in fv:
                        score = max(score, 1.0 if a == b else SequenceMatcher(None, a, b).ratio())
            if (score == 1.0 and d <= 40) or (score >= 0.85 and d <= 15):
                pairs.append((-score, d, i, j))
    pairs.sort()
    used_f, used_c, out = set(), set(), {}
    for neg_score, d, i, j in pairs:
        if i in used_f or j in used_c:
            continue
        used_f.add(i)
        used_c.add(j)
        out[i] = (cands[j], d, -neg_score)
    return out


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '--offline':
        osm = json.load(open(sys.argv[2]))
        wd = json.load(open(sys.argv[3]))
    else:
        osm, wd = fetch_osm(), fetch_wikidata()
    if not osm and not wd:
        print('No data from OSM or Wikidata – nothing changed.')
        sys.exit(1)

    forts = json.load(open(FORTS, encoding='utf-8'))
    changed, unchanged, unmatched, conflicts = [], [], [], []
    osm_m, wd_m = assign(forts, osm), assign(forts, wd)
    for i, f in enumerate(forts):
        mo, mw = osm_m.get(i), wd_m.get(i)
        if mw and mw[0].get('mr') and not f.get('mr'):
            f['mr'] = mw[0]['mr']
        elif mo and mo[0].get('mr') and not f.get('mr'):
            f['mr'] = mo[0]['mr']
        if not mo and not mw:
            unmatched.append(f)
            continue
        pick = mo or mw
        if mo and mw:
            gap = km(mo[0]['lat'], mo[0]['lon'], mw[0]['lat'], mw[0]['lon'])
            if gap > 2:
                conflicts.append((f['name'], round(gap, 1)))
        c, d = pick[0], pick[1]
        if d < 0.3:
            unchanged.append(f['name'])
            continue
        old = (f['lat'], f['lon'])
        f['lat'], f['lon'] = round(c['lat'], 5), round(c['lon'], 5)
        f['approx'] = False
        changed.append((f['name'], old, (f['lat'], f['lon']), d, c['src'], c['names'][0],
                        (mo is not None) + (mw is not None)))

    json.dump(forts, open(FORTS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

    changed.sort(key=lambda x: -x[3])
    lines = ['# Coordinate check report', '',
             f'Sources: OpenStreetMap ({len(osm)} places), Wikidata ({len(wd)} places).', '',
             f'- Corrected: **{len(changed)}**',
             f'- Already accurate (within 300 m): **{len(unchanged)}**',
             f'- Not found in either source (kept as is): **{len(unmatched)}**', '',
             '## Corrected (biggest moves first)', '',
             '| Fort | Moved | Source | Matched name | Sources agreeing | New lat, lon |',
             '|---|---|---|---|---|---|']
    for n, old, new, d, src, mname, agree in changed:
        flag = ' ⚠️' if d > 10 else ''
        lines.append(f'| {n} | {d:.1f} km{flag} | {src} | {mname} | {agree} | {new[0]}, {new[1]} |')
    lines += ['', '## OSM and Wikidata disagree by >2 km (OSM used)', '']
    lines += [f'- {n}: {g} km apart' for n, g in conflicts] or ['- none']
    lines += ['', '## Not found (check by hand)', '']
    lines += [f'- {f["name"]} ({f["district"]})' for f in unmatched] or ['- none']
    open(REPORT, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(f'Corrected {len(changed)}, accurate {len(unchanged)}, unmatched {len(unmatched)}')


if __name__ == '__main__':
    main()
