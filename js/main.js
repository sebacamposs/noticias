let DATA=null,activeTab='eventos',activeEl=null,filteredCache=[];

// CAT → SECTION NAME
const CAT_SECTION={
  'Política':'Política Nacional','Economía':'Economía y Negocios',
  'Sociedad':'Sociedad','Internacional':'Internacional',
  'Deportes':'Deportes','Cultura y Entretenimiento':'Cultura',
  'Catástrofes y Emergencias':'Emergencias','Ciencia y Tecnología':'Ciencia',
};

function esc(s){return(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}

// FILE LOAD
const dropZone=document.getElementById('drop-zone'),fileInput=document.getElementById('file-input');
dropZone.addEventListener('dragover',e=>{e.preventDefault();dropZone.classList.add('drag-over')});
dropZone.addEventListener('dragleave',()=>dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop',e=>{e.preventDefault();dropZone.classList.remove('drag-over');if(e.dataTransfer.files[0])loadFile(e.dataTransfer.files[0])});
fileInput.addEventListener('change',e=>{if(e.target.files[0])loadFile(e.target.files[0])});
function loadFile(f){const r=new FileReader();r.onload=e=>{try{DATA=JSON.parse(e.target.result);initUI()}catch(err){alert('Error: '+err.message)}};r.readAsText(f,'utf-8')}

// INIT
function initUI(){
  const ts=DATA.timestamp||'';
  const meses=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
  let fechaStr='—';
  if(ts.length>=8){
    const d=new Date(+ts.slice(0,4),+ts.slice(4,6)-1,+ts.slice(6,8));
    fechaStr=`${d.getDate()} de ${meses[d.getMonth()]} de ${d.getFullYear()}`;
  }
  document.getElementById('mh-date').textContent=fechaStr;
  document.getElementById('mh-edition').textContent=ts.length>=13?`${ts.slice(9,11)}:${ts.slice(11,13)} hrs`:'';
  document.getElementById('mh-total').textContent=`${DATA.total_titulares||0} titulares`;
  const fuentes=new Set(DATA.eventos.flatMap(e=>e.fuentes||[]));
  const regiones=new Set(DATA.eventos.flatMap(e=>e.regiones||[]));
  document.getElementById('mh-fuentes').textContent=`${fuentes.size} medios`;
  document.getElementById('stat-eventos').textContent=DATA.eventos.length;
  document.getElementById('stat-titulares').textContent=DATA.total_titulares||0;
  document.getElementById('stat-fuentes').textContent=fuentes.size;
  document.getElementById('stat-regiones').textContent=regiones.size;

  const cats=[...new Set(DATA.eventos.map(e=>e.categoria).filter(Boolean))].sort();
  document.getElementById('filter-cat').innerHTML='<option value="">Todas las secciones</option>'+
    cats.map(c=>`<option value="${c}">${CAT_SECTION[c]||c}</option>`).join('');
  const regs=[...regiones].sort();
  document.getElementById('filter-region').innerHTML='<option value="">Todas las regiones</option>'+
    regs.map(r=>`<option value="${esc(r)}">${esc(r)}</option>`).join('');

  document.getElementById('drop-section').classList.add('hidden');
  ['stats-bar','tabs','toolbar','grid-section'].forEach(id=>document.getElementById(id).classList.remove('hidden'));
  renderEventos();renderCoverage();bindFilters();
}

// RENDER
function renderEventos(){
  const search=document.getElementById('search-input').value.toLowerCase();
  const catF=document.getElementById('filter-cat').value;
  const regF=document.getElementById('filter-region').value;
  filteredCache=[...DATA.eventos].sort((a,b)=>(b.n_titulares||0)-(a.n_titulares||0)).filter(ev=>{
    if(catF&&ev.categoria!==catF)return false;
    if(regF&&!(ev.regiones||[]).includes(regF))return false;
    if(search){const h=(ev.evento||'').toLowerCase().includes(search)||(ev.titulares||[]).some(t=>(t.titular||'').toLowerCase().includes(search));if(!h)return false}
    return true;
  });
  document.getElementById('result-count').textContent=`${filteredCache.length} de ${DATA.eventos.length} notas`;

  const catF2=document.getElementById('filter-cat').value;
  const sectionName=catF2?(CAT_SECTION[catF2]||catF2):'Noticias del Día';
  document.getElementById('section-title').textContent=sectionName;

  const grid=document.getElementById('news-columns'),empty=document.getElementById('empty-filtered');
  if(!filteredCache.length){grid.innerHTML='';empty.classList.remove('hidden');return}
  empty.classList.add('hidden');
  // filteredCache already sorted by n_titulares desc
  // CSS grid fills left→right, top→bottom
  grid.innerHTML=filteredCache.map((ev,i)=>buildStory(ev,i)).join('');
  grid.querySelectorAll('.story').forEach((el,i)=>
    el.addEventListener('click',()=>openPanel(filteredCache[i],el))
  );
}

function buildStory(ev,i){
  const n=ev.n_titulares||0;
  const size=n>=12?'story-lg':n>=6?'story-md':'story-sm';
  const kicker=CAT_SECTION[ev.categoria]||ev.categoria||'General';
  const imgHtml=ev.imagen?`<img class="story-img" src="${esc(ev.imagen)}" alt="" loading="lazy" onerror="this.style.display='none'">`:'';
  const fuentes=(ev.fuentes||[]).slice(0,3).join(', ')+(ev.fuentes&&ev.fuentes.length>3?` y ${ev.fuentes.length-3} más`:'');
  return`<div class="story ${size}" tabindex="0" role="button" data-idx="${i}">
    <div class="story-kicker">${esc(kicker)}</div>
    <div class="story-headline">${esc(ev.evento||'Sin título')}</div>
    ${imgHtml}
    <div class="story-meta">
      <span class="fuentes">${esc(fuentes)}</span>
      <span>${n} titular${n!==1?'es':''}</span>
    </div>
  </div>`;
}

// PANEL — grouping logic
const normTitular=s=>{
  if(!s)return'';
  return s.trim().replace(/\s+-\s+\S+\.\S+\s*$/,'').trim();
};

// Group titulares by source, sorted by count desc
const agruparPorFuente=items=>{
  const map={};
  for(const t of items){
    const f=t.fuente||'—';
    const texto=normTitular(t.titular||'').trim();
    if(!texto)continue;
    if(!map[f])map[f]=[];
    map[f].push({texto,link:t.link||'',region:t.region||''});
  }
  const grupos=Object.entries(map)
    .map(([fuente,tits])=>({fuente,tits}))
    .sort((a,b)=>b.tits.length-a.tits.length);

  // Fusionar grupos de 1 titular con texto idéntico entre distintas fuentes
  const solos=grupos.filter(g=>g.tits.length===1);
  const multi=grupos.filter(g=>g.tits.length>1);
  const textoMap={};
  const fusionados=[];
  for(const g of solos){
    const key=g.tits[0].texto.toLowerCase();
    if(textoMap[key]!==undefined){
      fusionados[textoMap[key]].fuentes.push({fuente:g.fuente,link:g.tits[0].link,region:g.tits[0].region});
    } else {
      textoMap[key]=fusionados.length;
      fusionados.push({
        fuente:g.fuente,
        tits:g.tits,
        fuentes:[{fuente:g.fuente,link:g.tits[0].link,region:g.tits[0].region}],
        _fusionado:false,
      });
    }
  }
  fusionados.forEach(g=>{ g._fusionado=g.fuentes.length>1; });
  return [
    ...multi,
    ...fusionados.sort((a,b)=>b.fuentes.length-a.fuentes.length),
  ];
};

// Active carousel state
const _cars={};
let _uidCounter=0;

const renderGrupos=grupos=>grupos.map(renderGrupo).join('');

const renderHeadlines=items=>{
  const grupos=agruparPorFuente(items);
  return grupos.map(renderGrupo).join('');
};

const renderGrupo=(g,gi)=>{
    const uid='psg'+(++_uidCounter);
    const t0=g.tits[0];
    const mkLink=(t)=>t.link?`<a href="${esc(t.link)}" target="_blank" rel="noopener">${esc(t.texto)}</a>`:esc(t.texto);
    // Pre-render all texts as hidden spans to measure max height
    const hiddenItems=g.tits.map(t=>`<span class="psg-text" style="visibility:hidden;position:absolute">${mkLink(t)}</span>`).join('');
    const nav=g.tits.length<2?'':
      `<div class="psg-nav">
        <button class="psg-btn" data-uid="${uid}" data-dir="-1">&#8249;</button>
        <div class="psg-dots" id="dots-${uid}">${g.tits.map((_,i)=>`<span class="psg-dot${i===0?' active':''}" data-uid="${uid}" data-i="${i}"></span>`).join('')}</div>
        <button class="psg-btn" data-uid="${uid}" data-dir="1">&#8250;</button>
      </div><div class="psg-progress"><div class="psg-progress-bar" id="prog-${uid}"></div></div>`;
    const headerHtml=g._fusionado
      ? `<div class="psg-header psg-header-multi"><div class="psg-chips">${g.fuentes.map(f=>f.link?`<a class="psg-chip" href="${esc(f.link)}" target="_blank" rel="noopener">${esc(f.fuente)}</a>`:`<span class="psg-chip">${esc(f.fuente)}</span>`).join('')}</div><span class="psg-count">${g.fuentes.length} fuentes</span></div>`
      : `<div class="psg-header"><span class="psg-name">${esc(g.fuente)}</span>${g.tits.length>1?`<span class="psg-count">${g.tits.length} titulares</span>`:''}</div>`;
    return`<div class="ph-source-group${g._fusionado?' psg-multi':''}" data-uid="${uid}" data-fuente="${esc(g.fuente)}">
      ${headerHtml}
      <div class="psg-stage" id="stage-${uid}">
        ${hiddenItems}
        <div class="psg-text" id="text-${uid}">${mkLink(t0)}</div>
      </div>
      ${nav}
    </div>`;
};

const _mkLink=(t)=>t.link?`<a href="${esc(t.link)}" target="_blank" rel="noopener">${esc(t.texto)}</a>`:esc(t.texto);

function lockStageHeights(){
  document.querySelectorAll('.psg-stage').forEach(stage=>{
    // Measure all hidden ghost spans to find tallest
    const ghosts=stage.querySelectorAll('span.psg-text');
    let maxH=0;
    ghosts.forEach(g=>{maxH=Math.max(maxH,g.offsetHeight)});
    // Also measure the visible text
    const vis=stage.querySelector('div.psg-text');
    if(vis)maxH=Math.max(maxH,vis.offsetHeight);
    if(maxH>0)stage.style.minHeight=maxH+'px';
    // Remove ghost spans after measuring
    ghosts.forEach(g=>g.remove());
  });
}



// ── GLOBAL SYNC TIMER ──
let _syncTick=0;
let _syncTimer=null;

function _startSyncTimer(){
  if(_syncTimer)return;
  _syncTimer=setInterval(()=>{
    _syncTick++;
    const now=Date.now();
    Object.entries(_cars).forEach(([uid,state])=>{
      if(!state||!state.g||state.g.tits.length<2)return;
      if(state.manualUntil&&now<state.manualUntil)return;
      const next=_syncTick%state.g.tits.length;
      if(next===state.idx)return;
      _updateCarouselUI(uid,next,state.g,state.container,1,state.idx);
      state.idx=next;
    });
  },6000);
}

function startCar(uid,g,container){
  _cars[uid]={idx:0,g,container,manualUntil:0};
  _startSyncTimer();
  resetProg(uid,container);
}

function goCar(uid,idx,g,dir,container){
  if(!g)return;
  const con=container||(_cars[uid]&&_cars[uid].container)||document;
  const prevIdx=(_cars[uid]||{idx:0}).idx;
  const isManual=(dir!==undefined);
  _cars[uid]={idx,g,container:con,manualUntil:isManual?Date.now()+6000:0};
  _updateCarouselUI(uid,idx,g,con,dir,prevIdx);
  if(isManual)resetProg(uid,con);
}

function _updateCarouselUI(uid,idx,g,con,dir,prevIdx){
  const scope=con||document;
  const el=scope.querySelector('#text-'+uid);
  if(el){
    const slideDir=dir!==undefined?dir:(prevIdx!==undefined?(idx>prevIdx?1:-1):1);
    const outClass=slideDir>0?'slide-out-left':'slide-out-right';
    const inClass=slideDir>0?'slide-in-left':'slide-in-right';
    el.classList.add(outClass);
    setTimeout(()=>{
      el.classList.remove(outClass);
      el.innerHTML=_mkLink(g.tits[idx]);
      el.classList.add(inClass);
      setTimeout(()=>el.classList.remove(inClass),240);
    },220);
  }
  scope.querySelectorAll(`.psg-dot[data-uid="${uid}"]`).forEach((d,i)=>d.classList.toggle('active',i===idx));
}

function stepCar(uid,dir,g){
  if(!g)return;
  const cur=(_cars[uid]||{idx:0}).idx;
  const con=(_cars[uid]||{}).container;
  goCar(uid,(cur+dir+g.tits.length)%g.tits.length,g,dir,con);
}

function resetProg(uid,con){
  const scope=con||document;
  const b=scope.querySelector('#prog-'+uid);if(!b)return;
  b.style.transition='none';b.style.width='0%';
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
    b.style.transition='width 6s linear';b.style.width='100%';
  }));
}

function initCarousels(containerEl,grupos){
  const gmap={};
  // Limpiar listeners anteriores reemplazando con clon limpio
  const fresh=containerEl.cloneNode(true);
  containerEl.parentNode.replaceChild(fresh,containerEl);

  // Mapear UIDs y arrancar carruseles
  fresh.querySelectorAll('.ph-source-group').forEach((el,gi)=>{
    const uid=el.dataset.uid;
    if(grupos[gi]){
      gmap[uid]=grupos[gi];
      if(grupos[gi].tits.length>1)startCar(uid,grupos[gi],fresh);
    }
  });

  fresh.addEventListener('click',e=>{
    const btn=e.target.closest('.psg-btn');
    if(btn){e.stopPropagation();const uid=btn.dataset.uid;stepCar(uid,+btn.dataset.dir,gmap[uid]);return}
    const dot=e.target.closest('.psg-dot');
    if(dot){e.stopPropagation();const uid=dot.dataset.uid;goCar(uid,+dot.dataset.i,gmap[uid],undefined,fresh);return}
    const grp=e.target.closest('.ph-source-group');
    if(grp)openSourceModal(grp.dataset.fuente,gmap[grp.dataset.uid]);
  });

  return fresh; // devolver referencia actualizada al DOM
}


function openSourceModal(fuente,g){
  if(!g)return;
  // Para grupos fusionados, mostrar todas las fuentes con sus links
  if(g._fusionado&&g.fuentes&&g.fuentes.length>1){
    document.getElementById('smo-title').textContent='Titular compartido';
    document.getElementById('smo-sub').textContent=`${g.fuentes.length} medios publicaron este mismo titular`;
    document.getElementById('smo-body').innerHTML=g.fuentes.map(f=>`
      <div class="source-modal-item">
        <div class="smi-text" style="font-weight:600;font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;color:var(--accent)">${esc(f.fuente)}</div>
        <div class="smi-text">${f.link?`<a href="${esc(f.link)}" target="_blank" rel="noopener">${esc(g.tits[0].texto)}</a>`:esc(g.tits[0].texto)}</div>
        ${f.region?`<div class="smi-region">${esc(f.region)}</div>`:''}
      </div>`).join('');
  } else {
    document.getElementById('smo-title').textContent=fuente;
    document.getElementById('smo-sub').textContent=`${g.tits.length} titular${g.tits.length!==1?'es':''} sobre este evento`;
    document.getElementById('smo-body').innerHTML=g.tits.map(t=>`
      <div class="source-modal-item">
        <div class="smi-text">${_mkLink(t)}</div>
        ${t.region?`<div class="smi-region">${esc(t.region)}</div>`:''}
      </div>`).join('');
  }
  document.getElementById('source-modal-overlay').classList.add('open');
}
function closeSourceModal(){
  const ov=document.getElementById('source-modal-overlay');
  if(ov)ov.classList.remove('open');
}
// Bind modal close buttons after DOM ready
document.addEventListener('DOMContentLoaded',()=>{
  const smoClose=document.getElementById('smo-close');
  const smoOv=document.getElementById('source-modal-overlay');
  if(smoClose)smoClose.addEventListener('click',closeSourceModal);
  if(smoOv)smoOv.addEventListener('click',e=>{if(e.target===e.currentTarget)closeSourceModal()});
});

function openPanel(ev,cardEl){
  if(activeEl)activeEl.classList.remove('active');
  activeEl=cardEl;cardEl.classList.add('active');

  document.getElementById('panel-kicker').textContent=(CAT_SECTION[ev.categoria]||ev.categoria||'General').toUpperCase();
  document.getElementById('panel-stats-bar').textContent=`${ev.n_titulares||0} titulares · ${(ev.fuentes||[]).length} medios`;

  const imgWrap=document.getElementById('panel-img-wrap'),img=document.getElementById('panel-img');
  if(ev.imagen){img.src=ev.imagen;img.onerror=()=>imgWrap.classList.add('hidden');imgWrap.classList.remove('hidden')}
  else imgWrap.classList.add('hidden');

  document.getElementById('panel-title').textContent=ev.evento||'Sin título';
  document.getElementById('panel-stats-center').textContent=`${ev.n_titulares||0} titulares en ${(ev.fuentes||[]).length} medios`;
  document.getElementById('panel-regiones').innerHTML=(ev.regiones||[]).map(r=>`<span class="panel-region-chip">${esc(r)}</span>`).join('');

  const tits=ev.titulares||[];
  // Agrupar TODOS los titulares juntos para detectar duplicados entre fuentes
  const todosGrupos=agruparPorFuente(tits);
  const mid=Math.ceil(todosGrupos.length/2);
  const lg=todosGrupos.slice(0,mid),rg=todosGrupos.slice(mid);

  const leftEl=document.getElementById('panel-left'),rightEl=document.getElementById('panel-right');
  document.getElementById('panel-left-label').textContent=`${lg.length} fuente${lg.length!==1?'s':''}`;
  leftEl.innerHTML=document.getElementById('panel-left-label').outerHTML+renderGrupos(lg);
  if(rg.length){
    document.getElementById('panel-right-label').textContent=`${rg.length} fuente${rg.length!==1?'s':''}`;
    rightEl.innerHTML=document.getElementById('panel-right-label').outerHTML+renderGrupos(rg);
    rightEl.style.display='';
  } else {
    rightEl.style.display='none';
  }
  leftEl.scrollTop=0;rightEl.scrollTop=0;
  document.getElementById('panel-center').scrollTop=0;

  // Init carousels — pass the already-computed grupos so UIDs match DOM
  const freshLeft=initCarousels(leftEl,lg);
  const freshRight=initCarousels(rightEl,rg);
  // Lock stage heights after render tick (using fresh DOM refs)
  requestAnimationFrame(()=>lockStageHeights());

  document.getElementById('panel-overlay').classList.add('open');
  document.getElementById('slide-panel').classList.add('open');
}
function closePanel(){
  document.getElementById('panel-overlay').classList.remove('open');
  document.getElementById('slide-panel').classList.remove('open');
  if(activeEl){activeEl.classList.remove('active');activeEl=null}
}
document.getElementById('panel-close').addEventListener('click',closePanel);
document.getElementById('panel-overlay').addEventListener('click',closePanel);
document.addEventListener('keydown',e=>{if(e.key==='Escape')closePanel()});


// TABS
document.querySelectorAll('.tab-btn').forEach(btn=>btn.addEventListener('click',()=>{
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');activeTab=btn.dataset.tab;
  document.getElementById('toolbar').classList.toggle('hidden',activeTab!=='eventos'||activeTab==='juegos');
  document.getElementById('grid-section').classList.toggle('hidden',activeTab!=='eventos');
  const cov=document.getElementById('coverage-section');
  const reg=document.getElementById('regional-section');
  activeTab==='cobertura'?cov.classList.remove('hidden'):cov.classList.add('hidden');
  activeTab==='regional'?reg.classList.remove('hidden'):reg.classList.add('hidden');
  const jue=document.getElementById('juegos-section');
  activeTab==='juegos'?jue.classList.remove('hidden'):jue.classList.add('hidden');
  if(activeTab==='regional'&&DATA)initRegional();
  closePanel();
}));

// FILTERS
function bindFilters(){
  document.getElementById('search-input').addEventListener('input',renderEventos);
  document.getElementById('filter-cat').addEventListener('change',renderEventos);
  document.getElementById('filter-region').addEventListener('change',renderEventos);
  document.getElementById('btn-clear').addEventListener('click',()=>{
    document.getElementById('search-input').value='';
    document.getElementById('filter-cat').value='';
    document.getElementById('filter-region').value='';
    renderEventos();
  });
}


// ══════════════════════════════════════════