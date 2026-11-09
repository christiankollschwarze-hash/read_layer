// TÆLLA Labs Cockpit – Hilfe je Stage (Popup). Texte: config/stage_hilfe.json (GET /api/hilfe).
(function(){
  let H=null;
  const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  async function laden(){if(!H){try{H=await (await fetch("/api/hilfe")).json();}catch(e){H={};}}return H;}
  function zu(){const o=document.getElementById("hilfe-o");if(o)o.remove();document.removeEventListener("keydown",taste);}
  function taste(e){if(e.key==="Escape")zu();}
  window.hilfeZeigen=async function(stage,ev){
    if(ev){ev.stopPropagation();ev.preventDefault();}
    const h=(await laden())[stage];zu();
    const o=document.createElement("div");o.id="hilfe-o";o.className="hilfe-o";o.onclick=e=>{if(e.target===o)zu();};
    o.innerHTML=h?`<div class="hilfe" role="dialog" aria-label="Hilfe Stage ${esc(stage)}">
      <button class="hilfe-x" aria-label="Schließen" onclick="document.getElementById('hilfe-o').remove()">×</button>
      <div class="seitentitel">Stage ${esc(stage)}</div><h2>${esc(h.name)}</h2>
      <h3>Warum gibt es diese Stage?</h3><p>${esc(h.warum)}</p>
      <h3>Was wird hier produziert?</h3><p>${esc(h.produziert)}</p>
      <h3>Was entscheidet der Mensch?</h3><p>${esc(h.mensch)}</p></div>`
      :`<div class="hilfe"><button class="hilfe-x" onclick="document.getElementById('hilfe-o').remove()">×</button><p>Für Stage ${esc(stage)} gibt es noch keinen Hilfetext.</p></div>`;
    document.body.appendChild(o);document.addEventListener("keydown",taste);
  };
  window.hilfeKnopf=stage=>`<button class="hilfe-k" title="Hilfe zu Stage ${stage}" aria-label="Hilfe zu Stage ${stage}" onclick="hilfeZeigen('${stage}',event)">?</button>`;
})();
