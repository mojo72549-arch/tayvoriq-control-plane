(function(){
if(window.__fpFamilyMode)return;window.__fpFamilyMode=true;
const KEY='fp_family_v17';
const DEFAULT={currentNet:3700,octNet:4600,childBenefit:518,sideJob:524,sideJobEnabled:true,saveNow:500,saveOct:1400,foodTarget:1250,shopTarget:600,fuelTarget:220,bufferTarget:2000,ikanoOpen:4500};
let S=Object.assign({},DEFAULT,load());
function load(){try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){return {}}}
function save(){localStorage.setItem(KEY,JSON.stringify(S))}
const eur=n=>new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(Number(n||0));
const week=n=>Math.round(Number(n||0)*12/52);
function el(tag,cls,html){const x=document.createElement(tag);if(cls)x.className=cls;if(html!==undefined)x.innerHTML=html;return x}
function css(){if(document.getElementById('fpFamilyCss'))return;const s=el('style');s.id='fpFamilyCss';s.textContent=`
#fpFamilyShell{position:fixed;inset:0;z-index:9999;background:#071525;color:#f6f9fc;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;overflow:auto;padding:18px 14px 34px}#fpFamilyShell *{box-sizing:border-box}.fwrap{max-width:720px;margin:auto}.fhead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.ftitle{font-size:28px;font-weight:900;letter-spacing:-.7px}.fsub{font-size:13px;color:#a8bacd;margin-top:4px}.fdetails{border:1px solid #294a67;background:#102944;color:#dbe8f5;border-radius:12px;padding:9px 11px}.fhero{margin-top:16px;background:linear-gradient(135deg,#123454,#0c2743);border:1px solid #2d5272;border-radius:24px;padding:18px}.fhero .small{font-size:12px;color:#b9cadb}.fhero .big{font-size:42px;font-weight:950;margin:4px 0;color:#39d98a}.fhero .line{font-size:14px;color:#d9e4ee;line-height:1.45}.fgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px}.fmetric{background:#102944;border:1px solid #294a67;border-radius:16px;padding:12px}.fmetric .l{font-size:11px;color:#9fb2c8}.fmetric .v{font-size:20px;font-weight:850;margin-top:5px}.fsection{margin-top:18px}.fsection h2{font-size:18px;margin:0 0 9px}.fbudget,.fsteps{background:#102944;border:1px solid #294a67;border-radius:18px;padding:8px 13px}.fbrow{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid #203c55}.fbrow:last-child{border-bottom:0}.fbname{font-size:14px;font-weight:750}.fbnote{font-size:11px;color:#9fb2c8;margin-top:3px;line-height:1.35}.fbamt{text-align:right;font-size:17px;font-weight:850}.fplan{background:#142d25;border:1px solid #28604d;border-radius:18px;padding:14px}.fplan b{font-size:15px}.fplan p{font-size:13px;color:#c6ddd3;margin:5px 0 0;line-height:1.45}.fstep{display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #203c55}.fstep:last-child{border-bottom:0}.fnum{width:28px;height:28px;border-radius:9px;background:#1a4167;display:grid;place-items:center;font-weight:850;flex:0 0 auto}.fstep b{font-size:14px}.fstep span{display:block;color:#9fb2c8;font-size:12px;margin-top:2px;line-height:1.4}.ftoggle{display:flex;justify-content:space-between;gap:10px;align-items:center;background:#102944;border:1px solid #294a67;border-radius:16px;padding:12px}.ftoggle button{border:1px solid #315a7e;background:#173b5f;color:white;border-radius:11px;padding:8px 11px;font-weight:750}.fcoach{margin-top:9px;padding:13px;border-radius:16px;background:#2c271a;border:1px solid #5c4b2c;color:#f0d9ac;font-size:13px;line-height:1.45}.fcoach.good{background:#142d25;border-color:#28604d;color:#bde0d0}.pot{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:12px;border-radius:16px;margin-top:8px}.pot.house{background:#102b43;border:1px solid #315a7e}.pot.buffer{background:#2c271a;border:1px solid #5c4b2c}.pot.debt{background:#2c1d24;border:1px solid #5a3740}.pot .pn{font-size:14px;font-weight:800}.pot .pd{font-size:11px;color:#aebfd0;margin-top:3px;line-height:1.35}.pot .pa{font-size:21px;font-weight:900}.phase{font-size:12px;color:#9fb2c8;margin:8px 0 0;line-height:1.45}.fmuted{color:#9fb2c8;font-size:11px;margin-top:12px;line-height:1.4}@media(max-width:430px){.fgrid{grid-template-columns:1fr 1fr}.ftitle{font-size:25px}.fhero .big{font-size:38px}}
`;document.head.appendChild(s)}
function currentLearning(){try{return JSON.parse(localStorage.getItem('fp_learning_v15')||'{}')}catch(e){return {}}}
function monthSpend(cat){const L=currentLearning();const key=new Date().getFullYear()+'-'+String(new Date().getMonth()+1).padStart(2,'0');return L.months&&L.months[key]?Number(L.months[key][cat]||0):0}
function pace(spend,target){const d=new Date(),dim=new Date(d.getFullYear(),d.getMonth()+1,0).getDate();const proj=d.getDate()?spend/d.getDate()*dim:spend;return {proj,ok:proj<=target}}
function coachText(food,fuel,fp,fup){if(!food&&!fuel)return 'Noch keine aktuellen Monatsdaten. Unsere Regel bleibt: Einkauf '+eur(S.foodTarget)+', Shopping '+eur(S.shopTarget)+', Tanken '+eur(S.fuelTarget)+'. Nach dem CSV-Import lernt die App euer Tempo.';let a=[];if(food)a.push(fp.ok?'Einkauf liegt auf Kurs.':'Einkauf läuft zu schnell: Hochrechnung ca. '+eur(fp.proj)+'.');if(fuel)a.push(fup.ok?'Tanken liegt auf Kurs.':'Tanken läuft zu schnell: Hochrechnung ca. '+eur(fup.proj)+'.');return a.join(' ')}
function render(){css();let shell=document.getElementById('fpFamilyShell');if(shell)shell.remove();shell=el('div');shell.id='fpFamilyShell';const w=el('div','fwrap');shell.appendChild(w);
 const incNow=S.currentNet+S.childBenefit+(S.sideJobEnabled?S.sideJob:0);const incOct=S.octNet+S.childBenefit+(S.sideJobEnabled?S.sideJob:0);const raise=S.octNet-S.currentNet;
 const food=monthSpend('food'),fuel=monthSpend('fuel');const fp=pace(food,S.foodTarget),fup=pace(fuel,S.fuelTarget);
 w.innerHTML=`
 <div class="fhead"><div><div class="ftitle">Unser Sparplan 🏠</div><div class="fsub">Einfach. Gemeinsam. Jeden Monat.</div></div><button class="fdetails" id="fDetails">Details</button></div>
 <div class="fhero"><div class="small">Ab dem nächsten Gehaltstag</div><div class="big">${eur(S.saveNow)} sparen</div><div class="line">Ab Oktober wird daraus <b>${eur(S.saveOct)} pro Monat</b>. Die rund <b>${eur(raise)} mehr Netto</b> werden nicht in den Alltag eingebaut.</div></div>
 <div class="fgrid"><div class="fmetric"><div class="l">Jetzt sparen</div><div class="v" style="color:#39d98a">${eur(S.saveNow)}</div></div><div class="fmetric"><div class="l">Ab Oktober sparen</div><div class="v" style="color:#39d98a">${eur(S.saveOct)}</div></div><div class="fmetric"><div class="l">Einnahmen jetzt*</div><div class="v">${eur(incNow)}</div></div><div class="fmetric"><div class="l">Einnahmen ab Okt.*</div><div class="v">${eur(incOct)}</div></div></div>
 <div class="fsection"><h2>Wohin geht das Geld?</h2>
   <div class="fplan"><b>Jetzt: ${eur(S.saveNow)} pro Monat</b><p>Solange der 2.000-€-Puffer noch nicht steht, teilen wir das Spargeld bewusst auf.</p></div>
   <div class="pot buffer"><div><div class="pn">🛟 Puffer</div><div class="pd">Für unerwartete Rechnungen und saubere Kontoführung.</div></div><div class="pa">300 €</div></div>
   <div class="pot debt"><div><div class="pn">💳 Ikano abbauen</div><div class="pd">Weniger Konsumschuld verbessert euren Spielraum vor dem Hauskauf.</div></div><div class="pa">200 €</div></div>
   <div class="phase">Sobald der Puffer 2.000 € erreicht: die 300 € zusätzlich zu Ikano. Sobald Ikano erledigt ist: alles aufs Hauskonto.</div>
   <div class="fplan" style="margin-top:12px"><b>Ab Oktober: ${eur(S.saveOct)} pro Monat</b><p>Die Gehaltserhöhung wird direkt sichtbar fürs Haus genutzt, während wir parallel Altlasten abbauen.</p></div>
   <div class="pot house"><div><div class="pn">🏠 Hauskonto</div><div class="pd">Direkt am Gehaltstag wegüberweisen.</div></div><div class="pa">900 €</div></div>
   <div class="pot debt"><div><div class="pn">💳 Ikano abbauen</div><div class="pd">Bis der offene Betrag weg ist.</div></div><div class="pa">300 €</div></div>
   <div class="pot buffer"><div><div class="pn">🛟 Puffer</div><div class="pd">Nur solange noch unter 2.000 €.</div></div><div class="pa">200 €</div></div>
   <div class="phase">Puffer voll? Dann werden daraus 500 € für Ikano. Ikano weg? Dann gehen die gesamten ${eur(S.saveOct)} aufs Hauskonto.</div>
 </div>
 <div class="fsection"><h2>Unsere Monatslimits</h2><div class="fbudget">
  <div class="fbrow"><div><div class="fbname">🛒 Lebensmittel + Drogerie</div><div class="fbnote">≈ ${eur(week(S.foodTarget))} pro Woche</div></div><div class="fbamt">${eur(S.foodTarget)}</div></div>
  <div class="fbrow"><div><div class="fbname">🛍️ Shopping + Kleidung</div><div class="fbnote">≈ ${eur(week(S.shopTarget))} pro Woche</div></div><div class="fbamt">${eur(S.shopTarget)}</div></div>
  <div class="fbrow"><div><div class="fbname">⛽ Tanken</div><div class="fbnote">≈ ${eur(week(S.fuelTarget))} pro Woche</div></div><div class="fbamt">${eur(S.fuelTarget)}</div></div>
 </div></div>
 <div class="fsection"><h2>Was die App heute sagt</h2><div class="fcoach ${fp.ok&&fup.ok?'good':''}">${coachText(food,fuel,fp,fup)}</div></div>
 <div class="fsection"><h2>Eine Regel für alles</h2><div class="fsteps">
  <div class="fstep"><div class="fnum">1</div><div><b>Am Gehaltstag zuerst sparen</b><span>Nicht am Monatsende hoffen, dass etwas übrig bleibt.</span></div></div>
  <div class="fstep"><div class="fnum">2</div><div><b>Unter dem Limit geblieben?</b><span>Der Rest aus Einkauf, Shopping oder Tanken geht zusätzlich aufs Hauskonto.</span></div></div>
  <div class="fstep"><div class="fnum">3</div><div><b>Keine neuen Raten</b><span>Jede erledigte Rate erhöht später automatisch das Haus-Sparziel.</span></div></div>
 </div></div>
 <div class="fsection"><div class="ftoggle"><div><b>Nebenjob in der Anzeige</b><div class="fsub">Für die spätere Hausrate nicht fest einplanen.</div></div><button id="fSide">${S.sideJobEnabled?'AN':'AUS'}</button></div></div>
 <div class="fmuted">* Kindergeld und optional Nebenjob sind in der Anzeige enthalten. Die Detailanalyse, Fixkosten und der lernende Einkaufs-/Tank-Coach laufen weiterhin im Hintergrund.</div>`;
 document.body.appendChild(shell);document.body.style.overflow='hidden';
 document.getElementById('fDetails').onclick=()=>{shell.remove();document.body.style.overflow='';sessionStorage.setItem('fp_family_hidden','1')};
 document.getElementById('fSide').onclick=()=>{S.sideJobEnabled=!S.sideJobEnabled;save();render()};
}
window.FinanzPilotFamily={show:()=>{sessionStorage.removeItem('fp_family_hidden');render()},settings:S};
setTimeout(()=>{if(sessionStorage.getItem('fp_family_hidden')!=='1')render();},500);
})();
