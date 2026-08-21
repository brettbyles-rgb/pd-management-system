from __future__ import annotations

import html
import json
from typing import Any


def render_career_explorer(payload: dict[str, Any]) -> str:
    data = html.escape(json.dumps(payload, ensure_ascii=False), quote=False)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Career Pathways Explorer</title>
<style>
:root {{
  --ink:#14213d; --muted:#5f6c80; --line:#d7dde8; --line-soft:#e9edf4;
  --page:#f5f7fb; --panel:#fff; --nav:#0b2545; --accent:#2d6cdf;
  --accent-soft:#e8f0ff; --teal:#0f6f78; --green:#087443; --warn:#925400;
  --radius:6px; --shadow:0 10px 26px rgba(20,33,61,.08);
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--page);color:var(--ink);font:14px/1.45 Arial,Helvetica,sans-serif}}
button,input,select{{font:inherit}}
button{{cursor:pointer}}
.topbar{{background:var(--nav);color:white;border-bottom:4px solid #60a5fa}}
.topbar-inner{{max-width:1480px;margin:0 auto;padding:15px 24px;display:flex;align-items:center;justify-content:space-between;gap:16px}}
.brand{{font-size:18px;font-weight:800}}
.navlinks{{display:flex;gap:18px;font-size:13px;font-weight:700}}
.navlinks a{{color:#dbeafe;text-decoration:none}}
.navlinks a.active{{color:white;border-bottom:2px solid white;padding-bottom:3px}}
.wrap{{max-width:1480px;margin:0 auto;padding:24px}}
.intro{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:22px;align-items:end;margin-bottom:18px}}
h1,h2,h3,p{{margin:0}}
h1{{font-size:30px;letter-spacing:0;color:var(--ink)}}
.lead{{color:var(--muted);font-size:16px;margin-top:7px;max-width:72ch}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}}
.stat{{background:white;border:1px solid var(--line);border-radius:var(--radius);padding:10px 13px;min-width:112px}}
.stat b{{display:block;font-size:21px;color:var(--nav);line-height:1}}
.stat span{{display:block;color:var(--muted);font-size:12px;margin-top:5px}}
.filters{{background:white;border:1px solid var(--line);border-radius:var(--radius);padding:16px;margin-bottom:18px;box-shadow:var(--shadow)}}
.filter-grid{{display:grid;grid-template-columns:minmax(240px,1.2fr) repeat(3,minmax(170px,.7fr)) auto;gap:12px;align-items:end}}
label{{display:block;font-weight:800;font-size:12px;color:#34445c;margin-bottom:5px}}
input,select{{width:100%;border:1px solid #bdc7d6;border-radius:4px;padding:10px 11px;background:white;color:var(--ink)}}
.btn{{border:1px solid var(--nav);background:white;color:var(--nav);border-radius:4px;padding:10px 13px;font-weight:800;white-space:nowrap}}
.btn.primary{{background:var(--nav);color:white}}
.btn:hover{{background:var(--accent-soft)}}
.btn.primary:hover{{background:#123966}}
.family-strip{{display:flex;gap:8px;overflow:auto;padding:4px 0 1px;margin-top:14px}}
.family-chip{{border:1px solid var(--line);background:#fbfcff;color:var(--ink);border-radius:999px;padding:7px 11px;font-weight:800;font-size:12px;white-space:nowrap}}
.family-chip.active{{border-color:var(--accent);background:var(--accent-soft);color:#174ea6}}
.main{{display:grid;grid-template-columns:380px minmax(0,1fr);gap:18px;align-items:start}}
.panel{{background:white;border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}}
.panel-head{{padding:15px 16px;border-bottom:1px solid var(--line-soft);display:flex;align-items:center;justify-content:space-between;gap:12px}}
.panel-head h2{{font-size:18px}}
.small{{font-size:12px;color:var(--muted)}}
.result-list{{max-height:calc(100vh - 292px);overflow:auto}}
.role-btn{{width:100%;border:0;border-bottom:1px solid var(--line-soft);background:white;text-align:left;padding:14px 16px;display:grid;gap:7px;color:var(--ink)}}
.role-btn:hover,.role-btn.active{{background:#f7faff}}
.role-title{{font-weight:800;font-size:15px}}
.role-meta{{display:flex;gap:7px;flex-wrap:wrap;align-items:center}}
.tag{{display:inline-flex;border:1px solid var(--line);border-radius:999px;padding:2px 7px;color:#42526a;background:white;font-size:11px;font-weight:800}}
.tag.family{{border-color:#b9d7dc;background:#edf8fa;color:#0f5961}}
.tag.manager{{border-color:#c9b9ef;background:#f4efff;color:#4c247a}}
.map-toolbar{{display:flex;gap:8px;align-items:center;justify-content:flex-end}}
.seg{{display:inline-flex;border:1px solid var(--line);border-radius:4px;overflow:hidden}}
.seg button{{border:0;border-right:1px solid var(--line);background:white;padding:8px 10px;color:var(--muted);font-weight:800}}
.seg button:last-child{{border-right:0}}
.seg button.active{{background:var(--nav);color:white}}
.map-scroll{{overflow:auto;max-height:calc(100vh - 292px)}}
.matrix{{border-collapse:separate;border-spacing:0;width:max-content;min-width:100%}}
.matrix th,.matrix td{{border-right:1px solid var(--line-soft);border-bottom:1px solid var(--line-soft);vertical-align:top;text-align:left}}
.matrix th{{position:sticky;top:0;z-index:2;background:#eef4ff;color:#233a5c;padding:10px;min-width:210px;font-size:12px;text-transform:uppercase;letter-spacing:.03em}}
.matrix th.grade-head{{left:0;z-index:3;min-width:130px}}
.grade-cell{{position:sticky;left:0;background:#fbfcff;z-index:1;width:130px;padding:12px 10px;font-weight:800;color:#233a5c}}
.matrix td{{padding:8px;background:white;min-width:210px;max-width:250px}}
.cell-stack{{display:grid;gap:7px}}
.mini-card{{border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:4px;background:white;padding:8px;display:grid;gap:4px;cursor:pointer}}
.mini-card:hover{{box-shadow:0 5px 14px rgba(20,33,61,.12)}}
.mini-title{{font-weight:800;font-size:12.5px}}
.mini-meta{{font-size:11px;color:var(--muted)}}
.empty-cell{{color:#a0a8b8;font-size:12px;padding:4px}}
.detail{{padding:16px;border-top:1px solid var(--line-soft);background:#fbfcff}}
.detail h3{{font-size:20px;margin-bottom:5px}}
.detail-grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:12px}}
.detail-box{{border:1px solid var(--line);background:white;border-radius:4px;padding:12px}}
.detail-box h4{{margin:0 0 7px;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
.detail-box ul{{margin:0;padding-left:17px}}
.cards-view{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;padding:14px}}
.cards-view .mini-card{{min-height:96px}}
.hidden{{display:none!important}}
@media(max-width:980px){{
  .intro,.main{{grid-template-columns:1fr}}
  .filter-grid{{grid-template-columns:1fr 1fr}}
  .result-list,.map-scroll{{max-height:none}}
}}
@media(max-width:620px){{
  .wrap{{padding:16px}}
  .topbar-inner{{padding:14px 16px;display:block}}
  .navlinks{{margin-top:8px;flex-wrap:wrap}}
  .filter-grid{{grid-template-columns:1fr}}
  h1{{font-size:24px}}
}}
</style>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <div class="brand">Career Pathways Explorer</div>
    <nav class="navlinks">
      <a class="active" href="/career-explorer">Explore roles</a>
      <a href="/">Role intelligence</a>
      <a href="/mapping-assistant">Mapping assistant</a>
    </nav>
  </div>
</header>
<main class="wrap">
  <section class="intro">
    <div>
      <h1>Discover roles across job families</h1>
      <p class="lead">A conservative fallback explorer modelled on the NSW procurement pattern, expanded for a multi-family workforce map.</p>
    </div>
    <div class="stats">
      <div class="stat"><b id="statRoles">0</b><span>roles</span></div>
      <div class="stat"><b id="statFamilies">0</b><span>job families</span></div>
      <div class="stat"><b id="statGrades">0</b><span>grade bands</span></div>
    </div>
  </section>

  <section class="filters">
    <div class="filter-grid">
      <div><label for="q">Search by keyword</label><input id="q" placeholder="Role title, PD number, family, capability"></div>
      <div><label for="family">Job family</label><select id="family"></select></div>
      <div><label for="grade">Grade</label><select id="grade"></select></div>
      <div><label for="capability">Capability</label><select id="capability"></select></div>
      <button class="btn" id="reset">Reset</button>
    </div>
    <div id="familyStrip" class="family-strip"></div>
  </section>

  <section class="main">
    <aside class="panel">
      <div class="panel-head">
        <h2>Roles</h2>
        <span class="small"><span id="resultCount">0</span> results</span>
      </div>
      <div id="roleList" class="result-list"></div>
    </aside>
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2 id="mapTitle">Career map</h2>
          <p id="mapSub" class="small"></p>
        </div>
        <div class="map-toolbar">
          <div class="seg" aria-label="View mode">
            <button id="matrixMode" class="active" type="button">Matrix</button>
            <button id="cardsMode" type="button">Cards</button>
          </div>
        </div>
      </div>
      <div id="mapScroll" class="map-scroll"></div>
      <div id="detail" class="detail hidden"></div>
    </section>
  </section>
</main>
<script id="explorer-data" type="application/json">{data}</script>
<script>
const payload = JSON.parse(document.getElementById('explorer-data').textContent);
const roles = payload.roles || [];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const state = {{q:'', family:'', grade:'', capability:'', view:'matrix', selectedId: roles[0]?.id || null}};

const byId = id => document.getElementById(id);
const familyName = r => r.job_family_name || 'Unmapped';
const familyCode = r => r.job_family_code || '__unmapped';
const gradeName = r => r.classification_display || r.classification_abbreviation || r.classification_raw || 'Unclassified';
const streamName = r => r.sub_family_name || r.job_family_name || 'Unmapped';
const roleSearchText = r => [
  r.position_description_no, r.role_title, r.job_family_name, r.sub_family_name,
  r.mapping_name, r.classification_display, r.classification_abbreviation,
  ...(r.capabilities || [])
].join(' ').toLowerCase();

function uniqueSorted(values) {{
  return [...new Set(values.filter(Boolean))].sort((a,b) => a.localeCompare(b));
}}

function setup() {{
  const families = uniqueSorted(roles.map(familyName));
  const grades = [...new Map(roles.map(r => [gradeName(r), Number(r.classification_order ?? 9999)])).entries()]
    .sort((a,b) => a[1] - b[1] || a[0].localeCompare(b[0])).map(x => x[0]);
  const caps = uniqueSorted(roles.flatMap(r => r.capabilities || []));
  populateSelect('family', 'All job families', families);
  populateSelect('grade', 'All grades', grades);
  populateSelect('capability', 'All capabilities', caps);
  byId('statRoles').textContent = payload.summary?.role_count ?? roles.length;
  byId('statFamilies').textContent = payload.summary?.job_family_count ?? families.filter(name => name !== 'Unmapped').length;
  byId('statGrades').textContent = payload.summary?.grade_count ?? grades.length;
  byId('familyStrip').innerHTML = ['All', ...families].map(name =>
    `<button class="family-chip ${{name === 'All' ? 'active' : ''}}" data-family="${{esc(name === 'All' ? '' : name)}}">${{esc(name)}}</button>`
  ).join('');
  byId('familyStrip').addEventListener('click', e => {{
    const btn = e.target.closest('.family-chip');
    if (!btn) return;
    state.family = btn.dataset.family || '';
    byId('family').value = state.family;
    render();
  }});
  ['q','family','grade','capability'].forEach(id => {{
    byId(id).addEventListener(id === 'q' ? 'input' : 'change', e => {{
      state[id] = e.target.value;
      render();
    }});
  }});
  byId('reset').addEventListener('click', () => {{
    Object.assign(state, {{q:'', family:'', grade:'', capability:''}});
    ['q','family','grade','capability'].forEach(id => byId(id).value = '');
    render();
  }});
  byId('matrixMode').addEventListener('click', () => setView('matrix'));
  byId('cardsMode').addEventListener('click', () => setView('cards'));
  render();
}}

function populateSelect(id, label, values) {{
  byId(id).innerHTML = `<option value="">${{esc(label)}}</option>` + values.map(v => `<option>${{esc(v)}}</option>`).join('');
}}

function filteredRoles() {{
  const q = state.q.trim().toLowerCase();
  return roles.filter(r =>
    (!q || roleSearchText(r).includes(q)) &&
    (!state.family || familyName(r) === state.family) &&
    (!state.grade || gradeName(r) === state.grade) &&
    (!state.capability || (r.capabilities || []).includes(state.capability))
  );
}}

function render() {{
  const rows = filteredRoles();
  if (!rows.some(r => r.id === state.selectedId)) state.selectedId = rows[0]?.id || null;
  byId('resultCount').textContent = rows.length;
  document.querySelectorAll('.family-chip').forEach(btn => btn.classList.toggle('active', (btn.dataset.family || '') === state.family));
  renderList(rows);
  renderMap(rows);
  renderDetail(rows.find(r => r.id === state.selectedId));
}}

function renderList(rows) {{
  byId('roleList').innerHTML = rows.map(r => `
    <button class="role-btn ${{r.id === state.selectedId ? 'active' : ''}}" data-id="${{r.id}}">
      <span class="role-title">${{esc(r.role_title)}}</span>
      <span class="role-meta">
        <span class="tag">${{esc(r.position_description_no || 'No PD')}}</span>
        <span class="tag">${{esc(gradeName(r))}}</span>
        <span class="tag family">${{esc(familyName(r))}}</span>
        ${{r.manager_role ? '<span class="tag manager">Manager role</span>' : ''}}
      </span>
    </button>
  `).join('') || '<p class="small" style="padding:16px">No matching roles.</p>';
  byId('roleList').onclick = e => {{
    const btn = e.target.closest('.role-btn');
    if (!btn) return;
    state.selectedId = Number(btn.dataset.id);
    render();
  }};
}}

function setView(view) {{
  state.view = view;
  byId('matrixMode').classList.toggle('active', view === 'matrix');
  byId('cardsMode').classList.toggle('active', view === 'cards');
  renderMap(filteredRoles());
}}

function renderMap(rows) {{
  const title = state.family || 'All job families';
  byId('mapTitle').textContent = title;
  byId('mapSub').textContent = state.family
    ? 'Grades run vertically; sub-families or streams run horizontally.'
    : 'Grades run vertically; job families run horizontally. Scroll across to scan the full workforce map.';
  state.view === 'matrix' ? renderMatrix(rows) : renderCards(rows);
}}

function gradeOrder(rows) {{
  return [...new Map(rows.map(r => [gradeName(r), Number(r.classification_order ?? 9999)])).entries()]
    .sort((a,b) => a[1] - b[1] || a[0].localeCompare(b[0])).map(x => x[0]);
}}

function columns(rows) {{
  const values = state.family ? rows.map(streamName) : rows.map(familyName);
  return uniqueSorted(values);
}}

function renderMatrix(rows) {{
  const grades = gradeOrder(rows);
  const cols = columns(rows);
  const grouped = new Map();
  rows.forEach(r => {{
    const key = gradeName(r) + '||' + (state.family ? streamName(r) : familyName(r));
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(r);
  }});
  byId('mapScroll').innerHTML = `<table class="matrix"><thead><tr><th class="grade-head">Grade</th>${{cols.map(c => `<th>${{esc(c)}}</th>`).join('')}}</tr></thead><tbody>${{
    grades.map(g => `<tr><td class="grade-cell">${{esc(g)}}</td>${{
      cols.map(c => {{
        const cell = grouped.get(g + '||' + c) || [];
        return `<td><div class="cell-stack">${{cell.length ? cell.slice(0,4).map(miniCard).join('') + (cell.length > 4 ? `<div class="small">+${{cell.length - 4}} more</div>` : '') : '<span class="empty-cell">-</span>'}}</div></td>`;
      }}).join('')
    }}</tr>`).join('')
  }}</tbody></table>`;
  bindMiniCards();
}}

function renderCards(rows) {{
  byId('mapScroll').innerHTML = `<div class="cards-view">${{rows.map(miniCard).join('') || '<p class="small">No matching roles.</p>'}}</div>`;
  bindMiniCards();
}}

function miniCard(r) {{
  return `<article class="mini-card" data-id="${{r.id}}">
    <div class="mini-title">${{esc(r.role_title)}}</div>
    <div class="mini-meta">${{esc(r.position_description_no || '')}} | ${{esc(gradeName(r))}}</div>
    <div class="mini-meta">${{esc(state.family ? streamName(r) : familyName(r))}}</div>
  </article>`;
}}

function bindMiniCards() {{
  byId('mapScroll').onclick = e => {{
    const card = e.target.closest('.mini-card');
    if (!card) return;
    state.selectedId = Number(card.dataset.id);
    render();
  }};
}}

function renderDetail(r) {{
  const target = byId('detail');
  if (!r) {{
    target.classList.add('hidden');
    target.innerHTML = '';
    return;
  }}
  target.classList.remove('hidden');
  target.innerHTML = `
    <h3>${{esc(r.role_title)}}</h3>
    <p class="small">${{esc(r.position_description_no || 'No PD number')}} | ${{esc(gradeName(r))}} | ${{esc(familyName(r))}}</p>
    <div class="detail-grid">
      <section class="detail-box"><h4>Mapped pathway</h4><p>${{esc(r.pathway || 'Unmapped')}}</p></section>
      <section class="detail-box"><h4>Role purpose</h4><p>${{esc(r.purpose || 'No role purpose available.')}}</p></section>
      <section class="detail-box"><h4>Focus capabilities</h4>${{(r.capabilities || []).length ? `<ul>${{r.capabilities.slice(0,8).map(c => `<li>${{esc(c)}}</li>`).join('')}}</ul>` : '<p class="small">No capability data available.</p>'}}</section>
      <section class="detail-box"><h4>Source</h4><p>${{esc(r.source_filename || '')}}</p></section>
    </div>`;
}}

setup();
</script>
</body>
</html>"""
