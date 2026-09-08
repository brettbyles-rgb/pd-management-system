from __future__ import annotations

import argparse
import json
import mimetypes
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .database import connect_database, import_document, initialise_database
from .embeddings import DEFAULT_MODEL_NAME, load_sentence_transformer
from .intelligence_prepare import prepare_pd_intelligence


SECTION_KEYS = [
    "role_details", "metadata", "primary_purpose", "key_accountabilities",
    "key_challenges", "key_relationships", "role_dimensions",
    "knowledge_experience", "essential_requirements", "capabilities", "issues",
]
APP_VERSION = "2026-07-03-blank-capability-5"
_EMBEDDER_CACHE: dict[str, object] = {}


def _embedder(model_name: str = DEFAULT_MODEL_NAME):
    if model_name not in _EMBEDDER_CACHE:
        _EMBEDDER_CACHE[model_name] = load_sentence_transformer(model_name)
    return _EMBEDDER_CACHE[model_name]


def list_validation_records(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute("""
        SELECT pd.id, pd.role_title, pd.source_filename, pd.extraction_status,
               vr.validation_status, vr.updated_at,
               CASE
                   WHEN EXISTS (
                       SELECT 1 FROM embeddings e
                       WHERE e.source_type = 'pd' AND e.source_id = CAST(pd.id AS TEXT)
                   ) THEN 'Ready'
                   WHEN EXISTS (
                       SELECT 1 FROM pd_mapping_texts mt
                       WHERE mt.position_description_id = pd.id
                   ) THEN 'Mapping text only'
                   ELSE 'Not prepared'
               END AS intelligence_status
        FROM position_descriptions pd
        JOIN validation_records vr ON vr.position_description_id = pd.id
        ORDER BY pd.role_title
    """)]


def get_validation_record(connection: sqlite3.Connection, pd_id: int) -> dict | None:
    row = connection.execute("""
        SELECT pd.id, pd.source_filename, pd.extraction_status,
               vr.validation_status, vr.extracted_json, vr.draft_json,
               vr.section_statuses_json, vr.edited_paths_json, vr.updated_at, vr.validated_at,
               CASE
                   WHEN EXISTS (
                       SELECT 1 FROM embeddings e
                       WHERE e.source_type = 'pd' AND e.source_id = CAST(pd.id AS TEXT)
                   ) THEN 'Ready'
                   WHEN EXISTS (
                       SELECT 1 FROM pd_mapping_texts mt
                       WHERE mt.position_description_id = pd.id
                   ) THEN 'Mapping text only'
                   ELSE 'Not prepared'
               END AS intelligence_status
        FROM position_descriptions pd
        JOIN validation_records vr ON vr.position_description_id = pd.id
        WHERE pd.id = ?
    """, (pd_id,)).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "source_filename": row["source_filename"],
        "extraction_status": row["extraction_status"],
        "validation_status": row["validation_status"],
        "extracted": json.loads(row["extracted_json"]),
        "draft": json.loads(row["draft_json"]),
        "section_statuses": json.loads(row["section_statuses_json"]),
        "edited_paths": json.loads(row["edited_paths_json"]),
        "updated_at": row["updated_at"],
        "validated_at": row["validated_at"],
        "intelligence_status": row["intelligence_status"],
    }


def save_validation_draft(
    connection: sqlite3.Connection, pd_id: int, draft: dict,
    section_statuses: dict, edited_paths: list[str], status: str = "Pending validation",
) -> None:
    with connection:
        changed = connection.execute("""
            UPDATE validation_records SET draft_json = ?, section_statuses_json = ?,
                   edited_paths_json = ?, validation_status = ?,
                   updated_at = CURRENT_TIMESTAMP, validated_at = NULL
            WHERE position_description_id = ?
        """, (
            json.dumps(draft, ensure_ascii=False), json.dumps(section_statuses),
            json.dumps(sorted(set(edited_paths))), status, pd_id,
        )).rowcount
        if not changed:
            raise KeyError(pd_id)
        connection.execute(
            "INSERT INTO validation_events(position_description_id, event_type, event_details) VALUES (?, ?, ?)",
            (pd_id, "Draft saved", json.dumps({"edited_sections": sorted(set(edited_paths))})),
        )


def validation_errors(draft: dict) -> list[str]:
    # PD templates have recurring legitimate exceptions. Missing content is retained as
    # an extraction issue for review, but a human validator may confirm the exception.
    return []


def confirm_validation(
    connection: sqlite3.Connection, pd_id: int, draft: dict,
    section_statuses: dict, edited_paths: list[str],
) -> list[str]:
    errors = validation_errors(draft)
    if errors:
        return errors
    confirmed = {key: "Confirmed" for key in SECTION_KEYS}
    confirmed.update(section_statuses)
    now = datetime.now(timezone.utc).isoformat()
    with connection:
        changed = connection.execute("""
            UPDATE validation_records SET draft_json = ?, section_statuses_json = ?,
                   edited_paths_json = ?, validation_status = 'Validated',
                   updated_at = CURRENT_TIMESTAMP, validated_at = ?
            WHERE position_description_id = ?
        """, (
            json.dumps(draft, ensure_ascii=False), json.dumps(confirmed),
            json.dumps(sorted(set(edited_paths))), now, pd_id,
        )).rowcount
        if not changed:
            raise KeyError(pd_id)
        connection.execute(
            "INSERT INTO validation_events(position_description_id, event_type, event_details) VALUES (?, 'Validation completed', ?)",
            (pd_id, json.dumps({"edited_sections": sorted(set(edited_paths))})),
        )
        import_document(connection, draft)
    return []


def get_validated_export(connection: sqlite3.Connection, pd_id: int) -> dict | None:
    row = connection.execute("""
        SELECT draft_json FROM validation_records
        WHERE position_description_id = ? AND validation_status = 'Validated'
    """, (pd_id,)).fetchone()
    return json.loads(row["draft_json"]) if row else None


HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>PD Validation</title>
<style>
:root{--purple:#481579;--ink:#172033;--muted:#667085;--line:#d7dce6;--bg:#f3f5f8;--green:#16794d;--amber:#9a5a00;--red:#b42318}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:var(--bg);font:14px/1.45 system-ui,Segoe UI,sans-serif}.system-nav{background:white;border-bottom:1px solid var(--line);padding:0 28px;display:flex;align-items:center;justify-content:space-between}.system-brand{font-size:17px;font-weight:800;color:#082646;text-decoration:none;white-space:nowrap}.system-links{display:flex;gap:20px;align-items:center}.system-links a{color:var(--muted);text-decoration:none;border-bottom:3px solid transparent;padding:18px 0 14px;font-weight:700;white-space:nowrap}.system-links a:hover,.system-links a.active{color:var(--purple);border-bottom-color:var(--purple)}
.layout{display:grid;grid-template-columns:310px minmax(0,1fr);min-height:calc(100vh - 56px)}.sidebar{background:#211238;color:white;height:calc(100vh - 56px);position:sticky;top:0;overflow:auto;padding:22px}
.sidebar h1{font-size:20px;margin:0 0 4px}.sidebar p{color:#d5cbe1;margin:0 0 16px}.pd-list{display:grid;gap:5px}.pd-button{border:0;text-align:left;padding:9px;border-radius:7px;color:white;background:transparent;cursor:pointer}.pd-button:hover,.pd-button.active{background:#ffffff1b}.pd-button small{display:block;color:#d5cbe1}
main{padding:26px;max-width:1250px;width:100%}.toolbar,.panel{background:white;border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:16px}.toolbar{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.toolbar h2{margin:3px 0}.buttons{display:flex;gap:8px;flex-wrap:wrap}button,.source-link{border:1px solid var(--purple);color:var(--purple);background:white;padding:8px 11px;border-radius:7px;cursor:pointer;text-decoration:none}button.primary{background:var(--purple);color:white}button:disabled{cursor:default;opacity:.65}button.danger{border-color:#d92d20;color:#b42318}.status{font-size:12px;font-weight:700;padding:4px 8px;border-radius:20px;background:#fff0d3;color:var(--amber)}.status.valid{background:#e5f5ed;color:var(--green)}
.section-head{display:flex;justify-content:space-between;align-items:center;gap:12px}.section-head h3{margin:0}.section-actions{display:flex;align-items:center;gap:8px}.review-state{font-size:12px;font-weight:700;padding:4px 8px;border-radius:20px;background:#eef0f4;color:var(--muted)}.review-state.reviewed{background:#e5f5ed;color:var(--green)}.review-state.edited{background:#fff0d3;color:var(--amber)}.confirm.confirmed{background:#e5f5ed;border-color:var(--green);color:var(--green)}label{font-weight:650;display:block;margin:10px 0 4px}input,textarea,select{width:100%;min-width:0;border:1px solid #bfc6d2;border-radius:6px;padding:8px;font:inherit}textarea{min-height:100px;resize:vertical}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.row-card{border:1px solid var(--line);border-radius:8px;padding:12px;margin:9px 0;background:#fbfcfd}.row-grid{display:grid;grid-template-columns:110px 1fr 150px;gap:8px}.relationship-grid{display:grid;grid-template-columns:140px 1fr 2fr;gap:8px}.cap-grid{display:grid;grid-template-columns:160px minmax(240px,1fr) 150px;gap:8px 12px}.cap-grid>*{min-width:0}.cap-grid label{margin:0}.cap-name{grid-column:1 / 3}.cap-name.full{grid-column:1 / 4}.cap-code{grid-column:3}.meta-row{display:grid;grid-template-columns:240px 1fr auto;gap:8px;margin:8px 0;align-items:center}.empty{color:var(--muted);font-style:italic}.issues{color:var(--red)}.notice{padding:10px;border-radius:7px;background:#fff0d3;color:#7a4700;margin-bottom:14px}.hidden{display:none}@media(max-width:1000px){.system-nav{align-items:flex-start;flex-direction:column;padding-top:14px}.system-links{flex-wrap:wrap;gap:8px 16px}.system-links a{padding:8px 0}}@media(max-width:850px){.layout{display:block}.sidebar{position:static;height:auto}.grid,.row-grid,.relationship-grid,.cap-grid,.meta-row{grid-template-columns:1fr}.cap-name,.cap-name.full,.cap-code{grid-column:1}.section-head{align-items:flex-start}.section-actions{align-items:flex-end;flex-direction:column}}
</style></head><body><nav class="system-nav"><a class="system-brand" href="http://127.0.0.1:8766/">PD Manager</a><div class="system-links"><a href="http://127.0.0.1:8766/#upload">Upload</a><a class="active" href="/">Validation Queue</a><a href="http://127.0.0.1:8766/#library">Search</a><a href="http://127.0.0.1:8766/mapping-assistant">Mapping Assistant</a><a href="http://127.0.0.1:8766/admin/classifications">Classification Admin</a><a href="http://127.0.0.1:8766/#workbook">Mapping Workbook Import</a></div></nav><div class="layout"><aside class="sidebar"><h1>PD Validation</h1><p>Review, correct and confirm extracted data.</p><div id="pd-list" class="pd-list"></div></aside><main><div id="welcome" class="panel"><h2>Select a position description</h2><p>Choose a record from the left to begin validation.</p></div><div id="app" class="hidden"></div></main></div>
<script>
const sectionNames={role_details:'Role details',metadata:'Role Description Fields',primary_purpose:'Primary purpose',key_accountabilities:'Key accountabilities',key_challenges:'Key challenges',key_relationships:'Key relationships',role_dimensions:'Role dimensions',knowledge_experience:'Key Knowledge and Experience',essential_requirements:'Essential requirements',capabilities:'Capabilities',issues:'Extraction issues'};
const frameworks=['NSW Public Sector Capability Framework','Asset management','Finance','Human resources','Infrastructure and Construction Project Leader (ICPL)','Information and Communication Technology (ICT)','Legal','Procurement','Property acquisition'];
const nswCapabilities=['Display Resilience and Courage','Act with Integrity','Manage Self','Value Diversity and Inclusion','Communicate Effectively','Commit to Customer Service','Work Collaboratively','Influence and Negotiate','Deliver Results','Plan and Prioritise','Think and Solve Problems','Demonstrate Accountability','Finance','Technology','Procurement and Contract Management','Project Management','Manage and Develop People','Inspire Direction and Purpose','Optimise Business Outcomes','Manage Reform and Change'];
const capabilityLevels=['Foundational','Intermediate','Adept','Advanced','Highly Advanced','Level 1','Level 2','Level 3','Level 4','Level 5','Level 6','Level 7'];
const metadataMap={'department agency':'department_agency','division branch unit':'division_branch_unit','position description no':'position_description_no','classification grade band':'classification_grade_band','senior executive work level standards':'senior_executive_work_level_standards','anzsco code':'anzsco_code','osca code':'osca_code','pcat code':'pcat_code','date of approval':'date_of_approval'};
let current=null,edited=new Set(),statuses={};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const options=(items,value)=>{const values=items.includes(value)?items:[...items,value].filter(Boolean);return `<option value="" ${value?'':'selected'}></option>`+values.map(x=>`<option ${x===value?'selected':''}>${esc(x)}</option>`).join('')};
async function api(url,options={}){const r=await fetch(url,{headers:{'Content-Type':'application/json'},...options});const j=await r.json();if(!r.ok)throw new Error((j.errors||[j.error||'Request failed']).join('\n'));return j}
async function loadList(){const rows=await api('/api/pds');document.querySelector('#pd-list').innerHTML=rows.map(r=>`<button class="pd-button" data-id="${r.id}" onclick="loadPD(${r.id})">${esc(r.role_title)}<small>${esc(r.validation_status)}</small></button>`).join('');const selected=new URLSearchParams(location.search).get('pd');if(selected&&rows.some(r=>String(r.id)===String(selected)))await loadPD(Number(selected))}
function sectionHead(key){const state=statuses[key]==='Confirmed'?'Reviewed':statuses[key]==='Needs review'?'Edited — review required':'Pending review',stateClass=statuses[key]==='Confirmed'?'reviewed':statuses[key]==='Needs review'?'edited':'';return `<div class="section-head"><h3>${sectionNames[key]}</h3><div class="section-actions"><span class="review-state ${stateClass}">${state}</span><button class="confirm ${statuses[key]==='Confirmed'?'confirmed':''}" onclick="confirmSection('${key}',this)">${statuses[key]==='Confirmed'?'Reviewed':'Mark section reviewed'}</button></div></div>`}
function panel(key,body){return `<section class="panel" data-section="${key}">${sectionHead(key)}${body}</section>`}
function textItems(key,items){return panel(key,`<div id="${key}-rows">${(items||[]).map((x,i)=>itemRow(key,i,x.text)).join('')}</div><button onclick="addTextRow('${key}')">+ Add row</button>`)}
function itemRow(key,i,text){return `<div class="row-card"><textarea data-path="${key}.${i}.text">${esc(text)}</textarea><button class="danger" onclick="removeRow(this)">Delete</button></div>`}
function metadataRow(x,i){return `<div class="meta-row" data-metadata-index="${i}"><input data-field="field_name" value="${esc(x.field_name||'')}" placeholder="Field name"><input data-field="field_value" value="${esc(x.field_value||'')}" placeholder="Field value"><button class="danger" onclick="deleteMetadataRow(${i})">Delete</button></div>`}
function issueRow(x,i){return `<div class="row-card" data-issue-index="${i}"><div class="issues"><b>${esc(x.severity||'Low')}</b> — ${esc(x.description||'New issue')}</div><label>Severity<select data-field="severity">${options(['Low','Medium','High','Blocking'],x.severity||'Low')}</select></label><label>Issue description<input data-field="description" value="${esc(x.description||'')}"></label><label><input type="checkbox" style="width:auto" data-field="resolved" ${x.resolved?'checked':''}> Resolved</label><label>Resolution notes<input data-field="resolution_notes" value="${esc(x.resolution_notes||'')}"></label><button class="danger" onclick="deleteIssue(${i})">Delete issue</button></div>`}
function capabilityRow(x,i){const isNSW=x.framework==='NSW Public Sector Capability Framework',hasCode=Boolean(x.capability_code)||x.framework==='Information and Communication Technology (ICT)';return `<div class="row-card cap-grid" data-capability-index="${i}"><label>Type<select data-field="capability_type">${options(['Focus','Complementary','Unclassified'],x.capability_type)}</select></label><label>Framework<select data-field="framework" onchange="changeCapabilityFramework(${i},this.value)">${options(frameworks,x.framework)}</select></label><label>Level<select data-field="level">${options(capabilityLevels,x.level)}</select></label><label class="cap-name ${hasCode?'':'full'}">Capability name${isNSW?`<select data-field="capability_name">${options(nswCapabilities,x.capability_name)}</select>`:`<input data-field="capability_name" value="${esc(x.capability_name)}">`}</label>${hasCode?`<label class="cap-code">Code<input data-field="capability_code" value="${esc(x.capability_code||'')}"></label>`:''}<button class="danger" onclick="deleteCapability(${i})">Delete capability</button></div>`}
function intelligenceControls(){if(current.validation_status!=='Validated')return '';const ready=current.intelligence_status==='Ready';return `${ready?'<span class="status valid">Ready for Mapping Assistant</span>':`<span class="status">Intelligence: ${esc(current.intelligence_status||'Not prepared')}</span><button id="prepare-button" onclick="prepareIntelligence()">Prepare for Mapping Assistant</button>`}`}
function render(){const d=current.draft,s=d.sections||{},f=d.role_description_fields||{};document.querySelector('#welcome').classList.add('hidden');const issues=d.extraction_issues||[];document.querySelector('#app').classList.remove('hidden');document.querySelector('#app').innerHTML=`
<div class="toolbar"><div><span id="validation-status" class="status ${current.validation_status==='Validated'?'valid':''}">${esc(current.validation_status)}</span> ${intelligenceControls()}<h2>${esc(d.pd_record.role_title)}</h2><div>${esc(current.source_filename)}</div></div><div class="buttons"><a class="source-link" href="/source/${encodeURIComponent(current.source_filename)}">Open Word source</a>${current.validation_status==='Validated'?`<a class="source-link validated-only" href="/api/pds/${current.id}/export?view=1" target="_blank">View validated JSON</a><a class="source-link validated-only" href="/api/pds/${current.id}/export" download>Download JSON file</a>`:''}<button onclick="saveDraft()">Save draft</button><button id="validate-button" class="primary" onclick="validateAll()" ${current.validation_status==='Validated'?'disabled':''}>${current.validation_status==='Validated'?'PD validated':'Validate entire PD'}</button></div></div>
<div id="message"></div>
${panel('role_details',`<label>Role title</label><input data-path="pd_record.role_title" value="${esc(d.pd_record.role_title)}">`)}
${panel('metadata',`<div id="metadata-rows">${(f.raw_fields||[]).map(metadataRow).join('')}</div><button onclick="addMetadataRow()">+ Add metadata row</button>`)}
${panel('primary_purpose',`<textarea data-path="sections.primary_purpose">${esc(s.primary_purpose)}</textarea>`)}
${textItems('key_accountabilities',d.key_accountabilities)}${textItems('key_challenges',d.key_challenges)}
${panel('key_relationships',`<div id="relationship-rows">${(d.key_relationships||[]).map((x,i)=>`<div class="row-card relationship-grid"><select data-path="key_relationships.${i}.relationship_group"><option ${x.relationship_group==='Internal'?'selected':''}>Internal</option><option ${x.relationship_group==='External'?'selected':''}>External</option><option ${x.relationship_group==='Ministerial'?'selected':''}>Ministerial</option><option ${x.relationship_group==='Other / Unclassified'?'selected':''}>Other / Unclassified</option></select><input data-path="key_relationships.${i}.who" value="${esc(x.who)}"><textarea data-path="key_relationships.${i}.why">${esc(x.why)}</textarea><button class="danger" onclick="removeRow(this)">Delete</button></div>`).join('')}</div><button onclick="addRelationship()">+ Add relationship</button>`)}
${panel('role_dimensions',`<div class="grid"><div><label>Decision making</label><textarea data-path="sections.decision_making">${esc(s.decision_making)}</textarea></div><div><label>Reporting line</label><textarea data-path="sections.reporting_line">${esc(s.reporting_line)}</textarea></div><div><label>Direct reports</label><textarea data-path="sections.direct_reports">${esc(s.direct_reports)}</textarea></div><div><label>Budget/Expenditure</label><textarea data-path="sections.budget_expenditure">${esc(s.budget_expenditure)}</textarea></div></div>`)}
${textItems('knowledge_experience',d.key_knowledge_and_experience)}${textItems('essential_requirements',d.essential_requirements)}
${panel('capabilities',`<div id="capability-rows">${(d.capabilities||[]).map(capabilityRow).join('')}</div><button onclick="addCapability()">+ Add capability</button>`)}
${panel('issues',`<div id="issue-rows">${issues.length?issues.map(issueRow).join(''):'<p class="empty">No extraction issues.</p>'}</div><button onclick="addIssue()">+ Add issue</button>`)}
`;document.querySelectorAll('[data-path],[data-field]').forEach(el=>el.addEventListener('input',onEdit));}
async function loadPD(id){current=await api('/api/pds/'+id);statuses=current.section_statuses||{};edited=new Set(current.edited_paths||[]);document.querySelectorAll('.pd-button').forEach(b=>b.classList.toggle('active',Number(b.dataset.id)===id));render()}
function markPDChanged(){if(current.validation_status==='Validated')current.validation_status='Pending validation';const badge=document.querySelector('#validation-status'),button=document.querySelector('#validate-button');if(badge){badge.textContent=current.validation_status;badge.classList.remove('valid')}if(button){button.disabled=false;button.textContent='Validate entire PD'}document.querySelectorAll('.validated-only').forEach(x=>x.remove())}
function onEdit(e){const section=e.target.closest('[data-section]')?.dataset.section;if(section){markPDChanged();edited.add(section);statuses[section]='Needs review';renderSectionState(e.target.closest('.panel'),section)}}
function renderSectionState(panel,key){const badge=panel.querySelector('.review-state'),button=panel.querySelector('.confirm'),confirmed=statuses[key]==='Confirmed';badge.textContent=confirmed?'Reviewed':statuses[key]==='Needs review'?'Edited — review required':'Pending review';badge.className=`review-state ${confirmed?'reviewed':statuses[key]==='Needs review'?'edited':''}`;button.classList.toggle('confirmed',confirmed);button.textContent=confirmed?'Reviewed':'Mark section reviewed'}
function confirmSection(key,b){statuses[key]='Confirmed';renderSectionState(b.closest('.panel'),key)}
function collect(){const d=structuredClone(current.draft);document.querySelectorAll('[data-path]').forEach(el=>{let target=d;const parts=el.dataset.path.split('.');for(let i=0;i<parts.length-1;i++){const k=/^\d+$/.test(parts[i])?Number(parts[i]):parts[i];if(target[k]===undefined)target[k]={};target=target[k]}const last=/^\d+$/.test(parts.at(-1))?Number(parts.at(-1)):parts.at(-1);target[last]=el.type==='checkbox'?el.checked:el.value});
for(const key of ['key_accountabilities','key_challenges','key_knowledge_and_experience','essential_requirements']){const domKey=key==='key_knowledge_and_experience'?'knowledge_experience':key;d[key]=[...document.querySelectorAll(`#${domKey}-rows .row-card`)].map((r,i)=>({sequence:i+1,text:r.querySelector('textarea').value}))}
d.key_relationships=[...document.querySelectorAll('#relationship-rows .row-card')].map((r,i)=>{const els=r.querySelectorAll('select,input,textarea');return{relationship_group:els[0].value,sequence:i+1,who:els[1].value,why:els[2].value}});collectMetadata(d);collectCapabilities(d);collectIssues(d);current.draft=d;return d}
function collectMetadata(d){const fields=d.role_description_fields;fields.raw_fields=[...document.querySelectorAll('#metadata-rows .meta-row')].map((row,i)=>({sequence:i+1,field_name:row.querySelector('[data-field="field_name"]').value,field_value:row.querySelector('[data-field="field_value"]').value}));Object.values(metadataMap).forEach(key=>fields[key]='');fields.raw_fields.forEach(x=>{const key=x.field_name.toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();if(metadataMap[key])fields[metadataMap[key]]=x.field_value});return d}
function collectCapabilities(d){d.capabilities=[...document.querySelectorAll('#capability-rows .row-card')].map((row,i)=>{const old=current.draft.capabilities[Number(row.dataset.capabilityIndex)]||{};const item=structuredClone(old);row.querySelectorAll('[data-field]').forEach(el=>item[el.dataset.field]=el.value);if(!row.querySelector('[data-field="capability_code"]')&&item.framework!=='Information and Communication Technology (ICT)')item.capability_code='';item.sequence=i+1;return item});return d}
function collectIssues(d){d.extraction_issues=[...document.querySelectorAll('#issue-rows .row-card')].map((row,i)=>{const old=current.draft.extraction_issues[Number(row.dataset.issueIndex)]||{issue_type:'User raised issue',field_or_section:'User validation'};const item=structuredClone(old);row.querySelectorAll('[data-field]').forEach(el=>item[el.dataset.field]=el.type==='checkbox'?el.checked:el.value);return item});return d}
async function saveDraft(){try{await api(`/api/pds/${current.id}/draft`,{method:'PUT',body:JSON.stringify({draft:collect(),section_statuses:statuses,edited_paths:[...edited]})});show('Draft saved.');current.validation_status='Pending validation';await loadList()}catch(e){show(e.message,true)}}
async function validateAll(){if(current.validation_status==='Validated')return;const button=document.querySelector('#validate-button');try{if(button){button.disabled=true;button.textContent='Validating...'}show('Validating PD and saving the reviewed structured record.');Object.keys(sectionNames).forEach(k=>statuses[k]='Confirmed');await api(`/api/pds/${current.id}/confirm`,{method:'POST',body:JSON.stringify({draft:collect(),section_statuses:statuses,edited_paths:[...edited]})});current=await api('/api/pds/'+current.id);statuses=current.section_statuses||{};edited=new Set(current.edited_paths||[]);render();show('Validation completed. This PD is now the trusted validated record. Next, prepare it for Mapping Assistant when you are ready.');await loadList()}catch(e){if(button){button.disabled=false;button.textContent='Validate entire PD'}show(e.message,true)}}
async function prepareIntelligence(){const button=document.querySelector('#prepare-button');try{if(button){button.disabled=true;button.textContent='Preparing...'}show('Preparing for Mapping Assistant. This may take a moment while the embedding model runs.');await api(`/api/pds/${current.id}/prepare-intelligence`,{method:'POST',body:'{}'});current=await api('/api/pds/'+current.id);render();show('Preparation completed. This PD is ready for Mapping Assistant.');await loadList()}catch(e){if(button){button.disabled=false;button.textContent='Prepare for Mapping Assistant'}show(e.message,true)}}
function show(text,error=false){document.querySelector('#message').innerHTML=`<div class="notice ${error?'issues':''}">${esc(text).replace(/\n/g,'<br>')}</div>`}
function removeRow(b){const panel=b.closest('[data-section]'),key=panel.dataset.section;markPDChanged();edited.add(key);statuses[key]='Needs review';b.closest('.row-card').remove();renderSectionState(panel,key)}
function addTextRow(key){document.querySelector(`#${key}-rows`).insertAdjacentHTML('beforeend',itemRow(key,document.querySelectorAll(`#${key}-rows .row-card`).length,''));renderListeners(key)}
function renderListeners(key){markPDChanged();const panel=document.querySelector(`[data-section="${key}"]`);panel.querySelectorAll('[data-path],[data-field]').forEach(el=>el.addEventListener('input',onEdit));edited.add(key);statuses[key]='Needs review';renderSectionState(panel,key)}
function addRelationship(){document.querySelector('#relationship-rows').insertAdjacentHTML('beforeend','<div class="row-card relationship-grid"><select><option>Internal</option><option>External</option><option>Ministerial</option><option>Other / Unclassified</option></select><input placeholder="Who"><textarea placeholder="Why"></textarea><button class="danger" onclick="removeRow(this)">Delete</button></div>');renderListeners('key_relationships')}
function addMetadataRow(){collect();markPDChanged();current.draft.role_description_fields.raw_fields.push({sequence:current.draft.role_description_fields.raw_fields.length+1,field_name:'',field_value:''});edited.add('metadata');statuses.metadata='Needs review';render()}
function deleteMetadataRow(i){collect();markPDChanged();current.draft.role_description_fields.raw_fields.splice(i,1);edited.add('metadata');statuses.metadata='Needs review';render()}
function addCapability(){collect();markPDChanged();current.draft.capabilities.push({capability_type:'',sequence:current.draft.capabilities.length+1,framework:'',capability_name:'',capability_code:'',level:''});edited.add('capabilities');statuses.capabilities='Needs review';render()}
function deleteCapability(i){collect();markPDChanged();current.draft.capabilities.splice(i,1);current.draft.capabilities.forEach((x,n)=>x.sequence=n+1);edited.add('capabilities');statuses.capabilities='Needs review';render()}
function changeCapabilityFramework(i,value){collect();markPDChanged();const item=current.draft.capabilities[i];item.framework=value;if(value==='NSW Public Sector Capability Framework'&&!nswCapabilities.includes(item.capability_name))item.capability_name='';if(value!=='Information and Communication Technology (ICT)')item.capability_code='';edited.add('capabilities');statuses.capabilities='Needs review';render()}
function addIssue(){collect();markPDChanged();current.draft.extraction_issues.push({issue_type:'User raised issue',field_or_section:'User validation',description:'',severity:'Low',resolved:false,resolution_notes:''});edited.add('issues');statuses.issues='Needs review';render()}
function deleteIssue(i){collect();markPDChanged();current.draft.extraction_issues.splice(i,1);edited.add('issues');statuses.issues='Needs review';render()}
loadList();
</script></body></html>'''


def render_validation_app(*, read_only: bool = False) -> str:
    """Render the legacy editor inside the joined application and route namespace."""
    html = HTML
    navigation = (
        '<nav class="system-nav"><a class="system-brand" href="/">PD Manager</a>'
        '<div class="system-links"><a href="/career-explorer">Career Explorer</a>'
        '<a href="/#upload">Upload</a><a class="active" href="/validation">Validation Queue</a>'
        '<a href="/#library">Role Library</a><a href="/#semantic">Semantic Search</a>'
        '<a href="/mapping-assistant">Mapping Assistant</a>'
        '<a href="/admin/classifications">Classification Admin</a>'
        '<a href="/#workbook">Mapping Workbook Import</a></div></nav>'
    )
    nav_start = html.index('<nav class="system-nav">')
    nav_end = html.index('</nav>', nav_start) + len('</nav>')
    html = html[:nav_start] + navigation + html[nav_end:]
    html = html.replace("'/api/pds", "'/api/validation/pds")
    html = html.replace('href="/api/pds/', 'href="/api/validation/pds/')
    html = html.replace('href="/source/', 'href="/validation/source/')
    if not read_only:
        return html

    html = html.replace(
        '</style>',
        '.readonly-banner{background:#fff4d8;border-bottom:1px solid #e6c878;color:#684b00;'
        'padding:10px 24px;text-align:center;font-weight:800}.hosted-readonly #app input,'
        '.hosted-readonly #app textarea,.hosted-readonly #app select{background:#f3f4f6;color:#667085}'
        '</style>',
        1,
    )
    html = html.replace(
        '<body>',
        '<body class="hosted-readonly"><div class="readonly-banner">Hosted read-only proof of concept — '
        'review and export are available; editing and validation are disabled.</div>',
        1,
    )
    readonly_script = r'''
const applyHostedReadOnly=()=>{
  document.querySelectorAll('#app input,#app textarea,#app select,#app button').forEach(el=>{
    el.disabled=true;el.title='Editing is disabled in the hosted read-only proof of concept';
  });
};
new MutationObserver(applyHostedReadOnly).observe(document.documentElement,{childList:true,subtree:true});
document.addEventListener('DOMContentLoaded',applyHostedReadOnly);
'''
    return html.replace('loadList();\n</script>', readonly_script + 'loadList();\n</script>', 1)


def make_handler(database_path: Path, samples_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, value: object, status: int = 200) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self) -> None:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            if path == "/":
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/pds":
                with connect_database(database_path) as connection:
                    self._json(list_validation_records(connection))
                return
            if path == "/api/version":
                self._json({"version": APP_VERSION, "missing_fields_block_validation": False})
                return
            if path.startswith("/api/pds/") and path.endswith("/export"):
                try:
                    pd_id = int(path.split("/")[3])
                except ValueError:
                    self._json({"error": "Invalid PD id"}, 400); return
                with connect_database(database_path) as connection:
                    export = get_validated_export(connection, pd_id)
                if export is None:
                    self._json({"error": "This PD has not been validated"}, 409); return
                body = json.dumps(export, indent=2, ensure_ascii=False).encode("utf-8")
                filename = Path(export.get("pd_record", {}).get("source_filename", f"pd-{pd_id}")).stem
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                disposition = "inline" if parse_qs(parsed_url.query).get("view") == ["1"] else "attachment"
                self.send_header("Content-Disposition", f'{disposition}; filename="{filename}-validated.json"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if path.startswith("/api/pds/"):
                try:
                    pd_id = int(path.rsplit("/", 1)[1])
                except ValueError:
                    self._json({"error": "Invalid PD id"}, 400); return
                with connect_database(database_path) as connection:
                    record = get_validation_record(connection, pd_id)
                self._json(record or {"error": "Not found"}, 200 if record else 404)
                return
            if path.startswith("/source/"):
                filename = Path(unquote(path.removeprefix("/source/"))).name
                source = samples_dir / filename
                if not source.is_file():
                    source = Path("output/uploaded-pds") / filename
                if not source.is_file():
                    source = Path("samples") / filename
                if not source.is_file():
                    self.send_error(404); return
                body = source.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(source.name)[0] or "application/octet-stream")
                self.send_header("Content-Disposition", f'inline; filename="{source.name}"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            self.send_error(404)

        def do_PUT(self) -> None:
            path = urlparse(self.path).path
            if not path.startswith("/api/pds/") or not path.endswith("/draft"):
                self.send_error(404); return
            try:
                pd_id = int(path.split("/")[3]); payload = self._body()
                with connect_database(database_path) as connection:
                    save_validation_draft(connection, pd_id, payload["draft"], payload.get("section_statuses", {}), payload.get("edited_paths", []))
                self._json({"ok": True})
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, 400)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                if path.startswith("/api/pds/") and path.endswith("/confirm"):
                    pd_id = int(path.split("/")[3]); payload = self._body()
                    with connect_database(database_path) as connection:
                        errors = confirm_validation(connection, pd_id, payload["draft"], payload.get("section_statuses", {}), payload.get("edited_paths", []))
                    self._json({"ok": not errors, "errors": errors}, 200 if not errors else 400)
                    return
                if path.startswith("/api/pds/") and path.endswith("/prepare-intelligence"):
                    pd_id = int(path.split("/")[3])
                    with connect_database(database_path) as connection:
                        record = get_validation_record(connection, pd_id)
                        if record is None:
                            self._json({"error": "Not found"}, 404); return
                        if record["validation_status"] != "Validated":
                            self._json({"error": "Validate the PD before preparing it for Mapping Assistant"}, 409); return
                        summary = prepare_pd_intelligence(connection, pd_id, _embedder(), model_name=DEFAULT_MODEL_NAME)
                    self._json({"ok": True, "summary": summary})
                    return
                self.send_error(404); return
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, 400)
            except Exception as exc:
                self._json({"error": str(exc)}, 500)

        def log_message(self, format: str, *args: object) -> None:
            pass
    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local PD validation application")
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument("--samples", type=Path, default=Path("samples"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    connection = connect_database(args.database)
    try:
        initialise_database(connection)
    finally:
        connection.close()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.database, args.samples))
    print(f"PD validation app: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from pd_extractor.config import default_database_path
