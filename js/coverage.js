// COVERAGE
function renderCoverage(){
  const map={};
  DATA.eventos.forEach(ev=>(ev.titulares||[]).forEach(t=>{
    const f=t.fuente||'Desconocida';
    if(!map[f])map[f]={count:0,cats:new Set(),regiones:new Set()};
    map[f].count++;
    if(ev.categoria)map[f].cats.add(CAT_SECTION[ev.categoria]||ev.categoria);
    if(t.region)map[f].regiones.add(t.region);
  }));
  const sorted=Object.entries(map).sort((a,b)=>b[1].count-a[1].count);
  const maxC=sorted[0]?.[1].count||1;
  document.getElementById('coverage-grid').innerHTML=sorted.map(([n,d])=>`
    <div class="coverage-item">
      <div class="coverage-name">${esc(n)}</div>
      <div class="coverage-bar-wrap"><div class="coverage-bar" style="width:${Math.round(d.count/maxC*100)}%"></div></div>
      <div class="coverage-count">${d.count} titular${d.count!==1?'es':''} · ${[...d.regiones].join(', ')}</div>
      <div class="coverage-cats">${[...d.cats].sort().join(' · ')}</div>
    </div>`).join('');
}
