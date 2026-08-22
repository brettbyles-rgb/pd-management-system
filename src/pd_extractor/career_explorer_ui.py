from __future__ import annotations

import json
from typing import Any


HTML = r"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Career Pathways — proof of concept</title>
<style>
:root{
  --ink:#05284a;--purple:#4b1482;--teal:#0f6e86;--slate:#5b6b7f;
  --page:#f4f7fb;--panel:#fff;--line:#dbe3ee;--line-soft:#eaeff6;
  --muted:#5d7085;--muted-2:#8798aa;--canvas:#062f52;--canvas-2:#04203f;
  --focus:#4b1482;--r:10px;--shadow:0 1px 2px rgba(5,40,74,.06),0 8px 24px rgba(5,40,74,.06)
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;background:var(--page);color:var(--ink);font-size:15px;line-height:1.5;display:flex;flex-direction:column}
button,input{font:inherit;color:inherit}button{cursor:pointer}:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.hidden{display:none!important}.eyebrow{font-size:10.5px;font-weight:750;letter-spacing:.13em;text-transform:uppercase;color:var(--muted-2)}
.appbar{display:flex;align-items:center;gap:14px;padding:14px 22px;background:var(--panel);border-bottom:1px solid var(--line);flex-shrink:0;position:relative;z-index:5}
.mark{width:30px;height:30px;border-radius:8px;background:var(--ink);display:grid;place-items:center;flex-shrink:0}.mark svg{width:16px;height:16px}
.brand{text-decoration:none;color:var(--ink)}.brand strong{display:block;font-size:13.5px;line-height:1.25}.brand span{display:block;font-size:11px;color:var(--muted-2);letter-spacing:.04em}
.poc-tag{font-size:10px;font-weight:750;letter-spacing:.12em;text-transform:uppercase;color:var(--teal);border:1px solid #cfe4ea;background:#f0f8fa;padding:4px 9px;border-radius:5px}
.toplinks{display:flex;align-items:center;gap:16px;margin-left:14px}.toplinks a{font-size:12px;font-weight:650;color:var(--muted);text-decoration:none}.toplinks a:hover{color:var(--purple)}
.spacer{flex:1}.role-chip{display:flex;align-items:center;gap:10px;padding:6px 8px 6px 12px;border:1px solid var(--line);border-radius:999px;background:var(--page);max-width:min(46vw,430px)}
.role-chip .lbl{font-size:10px;color:var(--muted-2);letter-spacing:.1em;text-transform:uppercase}.role-chip .val{font-size:13px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.role-chip button,.quiet-btn{font-size:12px;font-weight:700;color:var(--purple);padding:4px 10px;border-radius:999px;border:1px solid #e0d5ee;background:#fff}.role-chip button:hover,.quiet-btn:hover{background:#f6f1fc}
.stage{flex:1;display:flex;min-height:0;position:relative}

/* Front door */
.frontdoor{flex:1;display:flex;justify-content:center;overflow:auto;padding:min(9vh,84px) 24px 40px}.fd-inner{width:100%;max-width:650px}
.fd-inner h1{font-size:clamp(28px,3.4vw,38px);line-height:1.14;letter-spacing:-.03em;margin:14px 0 11px}.lede{font-size:16px;color:var(--muted);max-width:49ch;margin-bottom:27px}
.search-wrap{position:relative}.search-field{display:flex;align-items:center;gap:11px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:0 14px;box-shadow:var(--shadow)}
.search-field:focus-within{border-color:var(--purple);box-shadow:0 0 0 3px rgba(75,20,130,.1)}.search-field svg{width:18px;color:var(--muted-2)}
.search-field input{flex:1;border:0;outline:0;background:none;font-size:16px;padding:15px 0}.search-field input::placeholder{color:var(--muted-2)}
.clear{border:0;background:none;color:var(--muted-2);font-size:20px;padding:3px}.results{margin-top:8px;background:var(--panel);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);overflow:auto;max-height:min(46vh,390px)}
.result-row{display:flex;align-items:center;gap:12px;width:100%;text-align:left;padding:11px 15px;border:0;border-bottom:1px solid var(--line-soft);background:#fff}.result-row:last-child{border-bottom:0}.result-row:hover{background:#f7f4fd;box-shadow:inset 3px 0 var(--purple)}
.result-title{font-size:14px;font-weight:650;flex:1}.result-meta{font-size:11.5px;color:var(--muted-2);white-space:nowrap}.grade{font-size:11px;font-weight:650;color:var(--muted);background:var(--page);border:1px solid var(--line);border-radius:4px;padding:1px 6px;white-space:nowrap}
.empty{padding:16px;color:var(--muted);font-size:13px}.fd-hint{margin-top:17px;font-size:12.5px;color:var(--muted-2)}.suggestions{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}.suggestions button{font-size:12.5px;padding:6px 12px;border:1px solid var(--line);border-radius:999px;background:#fff}.suggestions button:hover{border-color:var(--purple);color:var(--purple)}
.privacy{margin-top:32px;font-size:12px;color:var(--muted-2);display:flex;gap:8px;align-items:center}.privacy svg{width:14px}

/* Explorer shell */
.explorer{flex:1;display:grid;grid-template-columns:300px minmax(0,1fr);min-height:0;width:100%}.rail{background:#fff;border-right:1px solid var(--line);padding:22px 19px;overflow:auto;position:relative;z-index:2}
.rail h2{font-size:19px;line-height:1.25;margin:7px 0 5px}.rail-meta{font-size:12px;color:var(--muted);margin-bottom:17px}.rail-section{padding:16px 0;border-top:1px solid var(--line-soft)}.rail-section h3{font-size:12px;margin-bottom:7px}.rail-section p{font-size:12.5px;color:var(--muted)}
.path-list{display:grid;gap:7px;margin-top:9px}.path-item{width:100%;text-align:left;border:1px solid var(--line);background:#fff;border-radius:8px;padding:9px 10px;font-size:12px}.path-item.active{border-color:var(--purple);background:#f8f4fc;color:var(--purple)}
.legend{display:grid;gap:8px;margin-top:9px}.legend span{font-size:11.5px;color:var(--muted);display:flex;align-items:center;gap:8px}.dot{width:9px;height:9px;border-radius:50%;display:inline-block}.dot.root{background:#fff;border:2px solid #8bd5dc}.dot.anchor{background:#bca2d5}.dot.option{background:#fff;border:2px solid #7aa4bb}
.status-note{font-size:11.5px;color:#654e16;background:#fff9e8;border:1px solid #efe0a9;border-radius:8px;padding:10px;margin-top:10px}
.canvas-wrap{min-width:0;min-height:0;display:flex;flex-direction:column;background:linear-gradient(145deg,var(--canvas),var(--canvas-2));position:relative}.canvas-toolbar{display:flex;align-items:center;gap:12px;padding:14px 18px;color:#fff;border-bottom:1px solid rgba(255,255,255,.12);background:rgba(4,32,63,.58)}
.canvas-toolbar h1{font-size:16px}.canvas-toolbar p{font-size:11.5px;color:#bdd1df}.canvas-toolbar .spacer{flex:1}.tool-badge{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#c8eff1;border:1px solid rgba(139,213,220,.45);border-radius:5px;padding:4px 8px}
.canvas-scroll{flex:1;overflow:auto;position:relative}.canvas{position:relative;min-width:900px;min-height:650px}.links{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.links path{fill:none;stroke:#5f8da7;stroke-width:1.5}.links path.option{stroke-dasharray:5 6;opacity:.75}
.node{position:absolute;width:210px;transform:translate(-50%,-50%);border-radius:10px;color:var(--ink);box-shadow:0 10px 26px rgba(0,0,0,.22);transition:transform .15s,box-shadow .15s}.node:hover{transform:translate(-50%,-50%) translateY(-2px);box-shadow:0 14px 32px rgba(0,0,0,.28)}
.node-card{width:100%;text-align:left;border:1px solid #cbd9e2;background:#fff;border-radius:10px;padding:12px}.node.anchor .node-card{border:2px solid #bca2d5}.node.root .node-card{border:2px solid #8bd5dc}.node.option .node-card{border-left:4px solid #78a8bb}.node.active .node-card{box-shadow:0 0 0 3px rgba(188,162,213,.35)}
.node-label{display:block;font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--teal);font-weight:750;margin-bottom:4px}.node-title{display:block;font-size:13.5px;font-weight:750;line-height:1.25}.node-meta{display:block;font-size:10.5px;color:var(--muted);margin-top:5px}.node-score{display:flex;gap:6px;align-items:center;margin-top:8px;font-size:10.5px;color:var(--muted)}.score-bar{height:4px;background:#e3eaf0;border-radius:3px;flex:1;overflow:hidden}.score-bar i{display:block;height:100%;background:var(--teal)}
.node-actions{display:flex;gap:6px;margin-top:9px}.node-actions button{border:1px solid var(--line);background:#fff;border-radius:6px;padding:5px 8px;font-size:10.5px;font-weight:700}.node-actions .spawn{background:var(--purple);border-color:var(--purple);color:#fff}
.fan-control{position:absolute;transform:translate(-50%,0);display:flex;align-items:center;gap:8px;color:#d5e3eb;font-size:11px;white-space:nowrap}.fan-control button{color:#fff;border:1px solid rgba(255,255,255,.28);border-radius:999px;background:rgba(255,255,255,.08);padding:5px 10px;font-size:11px;font-weight:700}.fan-control button:hover{background:rgba(255,255,255,.16)}
.loading{color:#d7e6ef;font-size:13px}.canvas-empty{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);color:#d7e6ef;text-align:center}.canvas-empty button{margin-top:12px;color:#fff;border:1px solid rgba(255,255,255,.3);border-radius:8px;padding:7px 12px;background:rgba(255,255,255,.08)}
.detail{position:absolute;right:18px;top:72px;width:min(360px,calc(100% - 36px));max-height:calc(100% - 92px);overflow:auto;background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:0 18px 48px rgba(0,0,0,.3);padding:18px;z-index:4}.detail-close{float:right;border:0;background:none;font-size:20px;color:var(--muted)}.detail h2{font-size:19px;line-height:1.25;padding-right:25px}.detail .detail-meta{font-size:12px;color:var(--muted);margin:5px 0 15px}.detail section{border-top:1px solid var(--line-soft);padding-top:13px;margin-top:13px}.detail h3{font-size:11px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted-2);margin-bottom:6px}.detail p,.detail li{font-size:12.5px;color:var(--slate)}.detail ul{padding-left:18px}.error{color:#9f2d20;background:#fff3f1;border:1px solid #f2c5bf;padding:9px;border-radius:7px;font-size:12px}
@media(max-width:820px){.toplinks{display:none}.appbar{padding:11px 14px}.poc-tag{display:none}.role-chip{max-width:50vw}.explorer{grid-template-columns:1fr}.rail{display:none}.canvas{min-width:760px}.node{width:190px}}
</style>
</head>
<body>
<header class="appbar">
  <div class="mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2"><path d="M12 2 2 7l10 5 10-5-10-5Z"/><path d="m2 12 10 5 10-5M2 17l10 5 10-5"/></svg></div>
  <a class="brand" href="/career-explorer"><strong>Career Pathways</strong><span>TAFE NSW</span></a>
  <span class="poc-tag">Proof of concept</span>
  <nav class="toplinks" aria-label="System navigation"><a href="/">PD Manager</a><a href="/mapping-assistant">Mapping Assistant</a></nav>
  <div class="spacer"></div>
  <div class="role-chip hidden" id="roleChip"><span class="lbl">Your role</span><span class="val" id="roleChipValue"></span><button id="changeRole">Change</button></div>
</header>
<main class="stage" id="stage"></main>
<script id="explorer-data" type="application/json">__EXPLORER_DATA__</script>
<script>
const payload=JSON.parse(document.getElementById('explorer-data').textContent);
const roles=payload.roles||[];
const byRoleId=new Map(roles.map(r=>[r.role_id,r]));
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const grade=r=>r.classification_abbreviation||r.classification_display||r.classification_raw||'Unclassified';
const family=r=>r.job_family_name||'Unmapped';
const stage=document.getElementById('stage');
const state={current:null,anchors:[],active:null,fans:new Map(),detail:null,search:''};
const icons={
 search:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
 lock:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>'
};

function searchRoles(query){
 const words=query.toLowerCase().trim().split(/\s+/).filter(Boolean);
 if(!words.length)return [];
 return roles.map(r=>({r,text:[r.role_title,r.position_description_no,grade(r),family(r),r.sub_family_name].join(' ').toLowerCase()}))
  .filter(x=>words.every(w=>x.text.includes(w))).slice(0,30).map(x=>x.r);
}
function suggestedRoles(){
 const wanted=['Customer Service Representative','Developer','Teacher'];
 return wanted.map(t=>roles.find(r=>r.role_title===t)).filter(Boolean);
}
function renderFront(){
 document.getElementById('roleChip').classList.add('hidden');
 stage.innerHTML=`<section class="frontdoor"><div class="fd-inner">
  <span class="eyebrow">Start with what you know</span><h1>Where could your current role take you?</h1>
  <p class="lede">Choose a role to discover related work across TAFE NSW. Each branch shows another plausible direction—not a prescribed career ladder.</p>
  <div class="search-wrap"><div class="search-field">${icons.search}<input id="roleSearch" autocomplete="off" placeholder="Search for your current role" aria-label="Search roles"><button class="clear hidden" id="clearSearch" aria-label="Clear search">×</button></div><div id="results"></div></div>
  <p class="fd-hint">Or try an example</p><div class="suggestions">${suggestedRoles().map(r=>`<button data-start="${esc(r.role_id)}">${esc(r.role_title)}</button>`).join('')}</div>
  <p class="privacy">${icons.lock}<span>This local proof of concept does not collect or save employee information.</span></p>
 </div></section>`;
 const input=document.getElementById('roleSearch');input.focus();
 input.addEventListener('input',e=>{state.search=e.target.value;renderResults();});
 document.getElementById('clearSearch').addEventListener('click',()=>{state.search='';input.value='';renderResults();input.focus()});
 stage.querySelectorAll('[data-start]').forEach(b=>b.addEventListener('click',()=>start(b.dataset.start)));
}
function renderResults(){
 const target=document.getElementById('results'),input=document.getElementById('roleSearch'),clear=document.getElementById('clearSearch');
 clear.classList.toggle('hidden',!state.search);const matches=searchRoles(state.search);
 if(!state.search.trim()){target.className='';target.innerHTML='';return}
 target.className='results';target.innerHTML=matches.length?matches.map(r=>`<button class="result-row" data-start="${esc(r.role_id)}"><span class="result-title">${esc(r.role_title)}</span><span class="result-meta">${esc(family(r))}</span><span class="grade">${esc(grade(r))}</span></button>`).join(''):'<p class="empty">No matching roles found.</p>';
 target.querySelectorAll('[data-start]').forEach(b=>b.addEventListener('click',()=>start(b.dataset.start)));
 input.setAttribute('aria-expanded',matches.length?'true':'false');
}
async function start(roleId){
 const role=byRoleId.get(roleId);if(!role)return;
 state.current=roleId;state.anchors=[{id:'a0',roleId,parent:null,depth:0}];state.active='a0';state.fans.clear();state.detail=null;
 document.getElementById('roleChipValue').textContent=role.role_title;document.getElementById('roleChip').classList.remove('hidden');
 renderExplorer();await loadFan('a0',0);
}
function activeAnchor(){return state.anchors.find(a=>a.id===state.active)}
function roleForAnchor(a){return byRoleId.get(a.roleId)}
function anchorIds(){return state.anchors.map(a=>a.roleId)}
async function loadFan(anchorId,cursor=0){
 const anchor=state.anchors.find(a=>a.id===anchorId);if(!anchor)return;
 state.fans.set(anchorId,{loading:true,items:[],counter:'',next_cursor:0,total:0});renderGraph();
 const params=new URLSearchParams({role_id:anchor.roleId,cursor:String(cursor),anchored:anchorIds().join(',')});
 try{
  const response=await fetch('/api/career-explorer/neighbours?'+params);const data=await response.json();
  if(!response.ok)throw new Error(data.error||'Could not load related roles');state.fans.set(anchorId,data);
 }catch(error){state.fans.set(anchorId,{error:error.message,items:[],counter:'',next_cursor:0,total:0})}
 renderGraph();
}
function renderExplorer(){
 const current=byRoleId.get(state.current);
 stage.innerHTML=`<section class="explorer"><aside class="rail" id="rail"></aside><section class="canvas-wrap">
  <header class="canvas-toolbar"><div><h1>Career constellation</h1><p>Choose a node, then keep branching to discover less obvious connections.</p></div><div class="spacer"></div><span class="tool-badge">Live unified data</span></header>
  <div class="canvas-scroll"><div class="canvas" id="canvas"></div></div><aside class="detail hidden" id="detail"></aside>
 </section></section>`;
 document.getElementById('changeRole').onclick=()=>{state.current=null;state.anchors=[];state.fans.clear();renderFront()};
 renderRail();renderGraph();
}
function renderRail(){
 const rail=document.getElementById('rail');if(!rail)return;const current=byRoleId.get(state.current);const fan=state.fans.get(state.active);const algorithm=fan&&fan.algorithm;
 rail.innerHTML=`<span class="eyebrow">Your starting point</span><h2>${esc(current.role_title)}</h2><p class="rail-meta">${esc(grade(current))} · ${esc(family(current))}</p>
 <div class="rail-section"><h3>How to explore</h3><p>Select any anchored role to branch from it. Add one of its three suggestions to keep it on the map. “Less obvious” replaces the suggestions with the next three.</p></div>
 <div class="rail-section"><h3>Roles on your map</h3><div class="path-list">${state.anchors.map(a=>{const r=roleForAnchor(a);return `<button class="path-item ${a.id===state.active?'active':''}" data-select="${a.id}">${esc(r.role_title)}<br><small>${esc(grade(r))}</small></button>`}).join('')}</div></div>
 <div class="rail-section"><h3>Legend</h3><div class="legend"><span><i class="dot root"></i>Your starting role</span><span><i class="dot anchor"></i>Role you anchored</span><span><i class="dot option"></i>Suggested connection</span></div>
 ${algorithm&&algorithm.provisional?`<p class="status-note">The screen is using the retained provisional neighbour graph while the replacement Constellation inputs are completed.</p>`:''}</div>`;
 rail.querySelectorAll('[data-select]').forEach(b=>b.addEventListener('click',()=>{state.active=b.dataset.select;state.detail=null;renderRail();renderGraph();if(!state.fans.has(state.active))loadFan(state.active,0)}));
}
function layout(){
 const positions=new Map(),levels=new Map();
 state.anchors.forEach(a=>{if(!levels.has(a.depth))levels.set(a.depth,[]);levels.get(a.depth).push(a)});
 const fan=state.fans.get(state.active),active=activeAnchor(),suggestions=(fan&&fan.items)||[];
 const maxCount=Math.max(1,...[...levels.values()].map(x=>x.length),suggestions.length);
 const height=Math.max(650,maxCount*170+170),width=Math.max(950,(Math.max(0,...state.anchors.map(a=>a.depth))+2)*300+180);
 levels.forEach((items,depth)=>items.forEach((a,i)=>positions.set(a.id,{x:150+depth*300,y:height*(i+1)/(items.length+1)})));
 const suggestionPositions=suggestions.map((item,i)=>({item,x:150+(active.depth+1)*300,y:height*(i+1)/(suggestions.length+1)}));
 return {positions,suggestionPositions,width,height};
}
function curve(a,b){const mid=(a.x+b.x)/2;return `M ${a.x+105} ${a.y} C ${mid} ${a.y},${mid} ${b.y},${b.x-105} ${b.y}`}
function nodeHTML(role,pos,kind,id,extra=''){
 return `<article class="node ${kind} ${id===state.active?'active':''}" style="left:${pos.x}px;top:${pos.y}px" data-node="${id}"><button class="node-card" data-inspect="${esc(role.role_id)}"><span class="node-label">${kind==='root'?'Your role':kind==='anchor'?'Anchored role':'Related role'}</span><span class="node-title">${esc(role.role_title)}</span><span class="node-meta">${esc(grade(role))} · ${esc(family(role))}</span>${extra}</button></article>`;
}
function renderGraph(){
 const canvas=document.getElementById('canvas');if(!canvas)return;const active=activeAnchor(),fan=state.fans.get(state.active),l=layout();canvas.style.width=l.width+'px';canvas.style.height=l.height+'px';
 let paths='';state.anchors.filter(a=>a.parent).forEach(a=>{const parent=l.positions.get(a.parent),child=l.positions.get(a.id);if(parent&&child)paths+=`<path d="${curve(parent,child)}"/>`});
 l.suggestionPositions.forEach(s=>{const parent=l.positions.get(state.active);if(parent)paths+=`<path class="option" d="${curve(parent,s)}"/>`});
 let html=`<svg class="links" viewBox="0 0 ${l.width} ${l.height}" preserveAspectRatio="none">${paths}</svg>`;
 state.anchors.forEach(a=>{const r=roleForAnchor(a);html+=nodeHTML(r,l.positions.get(a.id),a.parent?'anchor':'root',a.id)});
 if(fan&&fan.loading){const p=l.positions.get(state.active);html+=`<p class="fan-control loading" style="left:${p.x+300}px;top:${p.y}px">Finding related roles…</p>`}
 if(fan&&fan.error){const p=l.positions.get(state.active);html+=`<div class="fan-control error" style="left:${p.x+300}px;top:${p.y}px">${esc(fan.error)}</div>`}
 l.suggestionPositions.forEach((s,i)=>{const r=byRoleId.get(s.item.role_id);if(!r)return;const pct=Math.max(4,Math.min(100,s.item.score*100));const extra=`<span class="node-score"><span>Relatedness</span><span class="score-bar"><i style="width:${pct}%"></i></span></span><span class="node-actions"><button data-inspect="${esc(r.role_id)}">Details</button><button class="spawn" data-spawn="${esc(r.role_id)}">Add to map</button></span>`;html+=nodeHTML(r,s,'option','option-'+i,extra)});
 if(fan&&!fan.loading&&!fan.error&&fan.total===0){const p=l.positions.get(state.active);html+=`<div class="canvas-empty" style="left:${p.x+300}px;top:${p.y}px"><p>No related roles are available for this record yet.</p></div>`}
 if(fan&&fan.total>3){const last=l.suggestionPositions[l.suggestionPositions.length-1]||l.positions.get(state.active);html+=`<div class="fan-control" style="left:${last.x}px;top:${last.y+94}px"><span>${esc(fan.counter)}</span><button data-more="${state.active}">Less obvious ›</button></div>`}
 canvas.innerHTML=html;wireGraph();renderRail();renderDetail();
}
function wireGraph(){
 document.querySelectorAll('[data-node]').forEach(n=>n.addEventListener('click',e=>{if(e.target.closest('[data-spawn],[data-inspect]'))return;const id=n.dataset.node;if(id.startsWith('a')){state.active=id;renderGraph()}}));
 document.querySelectorAll('[data-spawn]').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();spawn(b.dataset.spawn)}));
 document.querySelectorAll('[data-inspect]').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();state.detail=b.dataset.inspect;renderDetail()}));
 document.querySelectorAll('[data-more]').forEach(b=>b.addEventListener('click',()=>{const fan=state.fans.get(b.dataset.more);loadFan(b.dataset.more,fan.next_cursor)}));
}
async function spawn(roleId){
 if(state.anchors.some(a=>a.roleId===roleId)){state.active=state.anchors.find(a=>a.roleId===roleId).id;renderGraph();return}
 const parent=activeAnchor(),id='a'+state.anchors.length;state.anchors.push({id,roleId,parent:parent.id,depth:parent.depth+1});state.active=id;state.detail=roleId;renderGraph();await loadFan(id,0);
}
function renderDetail(){
 const target=document.getElementById('detail');if(!target)return;const r=byRoleId.get(state.detail);if(!r){target.classList.add('hidden');target.innerHTML='';return}
 target.classList.remove('hidden');target.innerHTML=`<button class="detail-close" aria-label="Close">×</button><span class="eyebrow">Role detail</span><h2>${esc(r.role_title)}</h2><p class="detail-meta">${esc(grade(r))} · ${esc(family(r))}</p>
 <section><h3>Mapped pathway</h3><p>${esc(r.pathway||'Unmapped')}</p></section><section><h3>Role purpose</h3><p>${esc(r.purpose||'No role purpose available.')}</p></section>
 <section><h3>Focus capabilities</h3>${(r.capabilities||[]).length?`<ul>${r.capabilities.slice(0,10).map(c=>`<li>${esc(c)}</li>`).join('')}</ul>`:'<p>No capability data available.</p>'}</section>`;
 target.querySelector('.detail-close').onclick=()=>{state.detail=null;renderDetail()};
}
renderFront();
</script>
</body>
</html>"""


def render_career_explorer(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return HTML.replace("__EXPLORER_DATA__", data)
