// TÆLLA Labs – Wortmarke mit rotem Punkt auf dem Strichende des letzten Buchstabens
// (Port von taella-app/src/design/DotWord.jsx). Aufruf: <a class="marke" href="/"></a> + dieses Skript.
(function(){
  function punkt(el){
    const text=el.textContent, cs=getComputedStyle(el), fs=parseFloat(cs.fontSize)||16;
    const ctx=document.createElement("canvas").getContext("2d");
    ctx.font=`${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    const last=text.slice(-1), m=ctx.measureText(last), bold=parseInt(cs.fontWeight,10)>=600;
    const stem=fs*(bold?0.105:0.08), d=Math.max(4,stem*(bold?1.75:2.1));
    const inkL=-m.actualBoundingBoxLeft, inkR=m.actualBoundingBoxRight;
    const cx=/[IilJj1|!]/.test(last)?(inkL+inkR)/2:inkR-stem/2;
    const anker=document.createElement("span");
    anker.setAttribute("aria-hidden","true");
    anker.style.cssText="display:inline-block;width:0;height:0;position:relative;vertical-align:baseline";
    anker.innerHTML=`<span style="position:absolute;left:${cx-m.width-d/2}px;bottom:${-d*0.12}px;width:${d}px;height:${d}px;border-radius:50%;background:var(--dot);display:block"></span>`;
    el.querySelectorAll("[aria-hidden]").forEach(x=>x.remove());
    el.appendChild(anker);
  }
  function setzen(){
    document.querySelectorAll(".marke").forEach(a=>{
      if(!a.querySelector(".wort"))a.innerHTML='<span class="wort">TÆLLA</span><span class="labs">Labs</span>';
      const w=a.querySelector(".wort");w.textContent="TÆLLA";punkt(w);
    });
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",setzen);else setzen();
  if(document.fonts&&document.fonts.ready)document.fonts.ready.then(setzen);
})();
