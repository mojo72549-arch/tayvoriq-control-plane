(function(){
if(window.__fpFamilyMode)return;window.__fpFamilyMode=true;
const KEY='fp_family_v16';
const DEFAULT={currentNet:3700,octNet:4600,childBenefit:518,sideJob:524,sideJobEnabled:true,houseAutoSave:900,foodTarget:1250,shopTarget:600,fuelTarget:220,bufferTarget:2000,ikanoOpen:4500};
let S=Object.assign({},DEFAULT,load());
function load(){try{return JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){return {}}}
function save(){localStorage.setItem(KEY,JSON.stringify(S))}
const eur=n=>new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(Number(n||0));
const week=n=>Math.round(Number(n||0)*12/52);
function el(tag,cls,html){const x=document.createElement(tag);if(cls)x.className=cls;if(html!==undefined)x.innerHTML=html;return x}
function css(){if(document.getElementById('fpFamilyCss'))return;const s=el('style');s.id='fpFamilyCss';s.textContent=`
#fpFamilyShell{position:fixed;inset:0;z-index:9999;background:#071525;color:#f6f9fc;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;overflow:auto;padding:18px 14px 34px}
#fpFamilyShell *{box-sizing:border-box}.fwrap{max-width:720px;margin:auto}.fhead{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.ftitle{font-size:28px;font-weight:900;letter-spacing:-.7px}.fsub{font-size:13px;color:#a8bacd;margin-top:4px}.fdetails{border:1px solid #294a67;background:#102944;color:#dbe8f5;border-radius:12px;padding:9px 11px}.fhero{margin-top:16px;background:linear-gradient(135deg,#123454,#0c2743);border:1px solid #2d5272;border-radius:24px;padding:18px}.fhero .small{font-size:12px;color:#b9cadb}.fhero .big{font-size:42px;font-weight:950;margin:4px 0;color:#39d98a}.fhero .line{font-size:14px;color:#d9e4ee}.fgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}.fmetric{background:#102944;border:1px solid #294a67;border-radius:16px;padding:12px}.fmetric .l{font-size:11px;color:#9fb2c8}.fmetric .v{font-size:20px;font-weight:850;margin-top:5px}.fsection{margin-top:18px}.fsection h2{font-size:18px;margin:0 0 9px}.fbudget{background:#102944;border:1px solid #294a67;border-radius:18px;padding:13px;margin-top:8px}.fbrow{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:9px 0;border-bottom:1px solid #203c55}.fbrow:last-child{border-bottom:0}.fbname{font-size:14px;font-weight:750}.fbnote{font-size:11px;color:#9fb2c8;margin-top:3px}.fbamt{text-align:right;font-size:17px;font-weight:850}.fplan{background:#142d25;border:1px solid #28604d;border-radius:18px;padding:14px}.fplan b{font-size:15px}.fplan p{font-size:13px;color:#c6ddd3;margin:5px 0 0;line-height:1.45}.fsteps{background:#102944;border:1px solid #294a67;border-radius:18px;padding:8px 13px}.fstep{display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #203c55}.fstep:last-child{border-bottom:0}.fnum{width:28px;height:28px;border-radius:9px;background:#1a4167;display:grid;place-items:center;font-weight:850;flex:0 0 auto}.fstep b{font-size:14px}.fstep span{display:block;color:#9fb2c8;font-size:12px;margin-top:2px;line-height:1.4}.ftoggle{display:flex;justify-content:space-between;gap:10px;align-items:center;background:#102944;border:1px solid #294a67;border-radius:16px;padding:12px}.ftoggle button{border:1px solid #315a7e;background:#173b5f;color:white;border-radius:11px;padding:8px 11px;font-weight:750}.fcoach{margin-top:9px;padding:13px;border-radius:16px;background:#2c271a;border:1px solid #5c4b2c;color:#f0d9ac;font-size:13px;line-height:1.45}.fcoach.good{background:#142d25;border-color:#28604d;color:#bde0d0}.fmuted{color:#9fb2c8;font-size:11px;margin-top:12px;line-height:1.4}@media(max-width:430px){.fgrid{grid-template-columns:1fr}.ftitle{font-size:25px}.fhero .big{font-size:38px}}
`;document.head.appendChild(s)}
function currentLearning(){try{return JSON.parse(localStorage.getItem('fp_learning_v15')||'{}')}catch(e){return {}}}
function monthSpend(cat){const L=currentLearning();const key=new Date().getFullYear()+'-'+String(new Date().getMonth()+1).padStart(2,'0');return L.months&&L.months[key]?Number(L.months[key][cat]||0):0}
function pace(spend,target){const d=new Date(),dim=new Date(d.getFullYear(),d.getMonth()+1,0).getDate();const proj=d.getDate()?spend/d.getDate()*dim:spend;return {proj,ok:proj<=target}}
function render(){css();let shell=document.getElementById('fpFamilyShell');if(shell)shell.remove();shell=el('div');shell.id='fpFamilyShell';const w=el('div','fwrap');shell.appendChild(w);
 const incNow=S.currentNet+S.childBenefit+(S.sideJobEnabled?S.sideJob:0);const incOct=S.octNet+S.childBenefit+(S.sideJobEnabled?S.sideJob:0);const raise=S.octNet-S.currentNet;
 const food=monthSpend('food'),fuel=monthSpend('fuel');const fp=pace(food,S.foodTarget),fup=pace(fuel,S.fuelTarget);
 w.innerHTML=`
 <div class="fhead"><div><div class="ftitle">Unser Sparplan 🏠</div><div class="fsub">Einfach gemeinsam sparen – Hauskauf im Blick</div></div><button class="fdetails" id="fDetails">Details</button></div>
 <div class="fhero"><div class="small">Ab Oktober jeden Monat zuerst fürs Haus</div><div class="big">${eur(S.houseAutoSave)}</div><div class="line">Dein Netto steigt von <b>${eur(S.currentNet)}</b> auf <b>${eur(S.octNet)}</b> – also <b>+${eur(raise)}</b>. Dieses Plus soll nicht im Alltag verschwinden.</div></div>
 <div class="fgrid"><div class="fmetric"><div class="l">Jetzt netto</div><div class="v">${eur(S.currentNet)}</div></div><div class="fmetric"><div class="l">Ab Oktober</div><div class="v">${eur(S.octNet)}</div></div><div class="fmetric"><div class="l">Sicheres Plus</div><div class="v" style="color:#39d98a">+${eur(raise)}</div></div></div>
 <div class="fsection"><h2>Unsere einfachen Monatslimits</h2><div class="fbudget">
  <div class="fbrow"><div><div class="fbname">🛒 Lebensmittel + Drogerie</div><div class="fbnote">≈ ${eur(week(S.foodTarget))} pro Woche</div></div><div class="fbamt">${eur(S.foodTarget)}</div></div>
  <div class="fbrow"><div><div class="fbname">🛍️ Shopping + Kleidung</div><div class="fbnote">≈ ${eur(week(S.shopTarget))} pro Woche</div></div><div class="fbamt">${eur(S.shopTarget)}</div></div>
  <div class="fbrow"><div><div class="fbname">⛽ Tanken</div><div class="fbnote">≈ ${eur(week(S.fuelTarget))} pro Woche</div></div><div class="fbamt">${eur(S.fuelTarget)}</div></div>
 </div></div>
 <div class="fsection"><h2>Was die App heute sagt</h2><div class="fcoach ${fp.ok&&fup.ok?'good':''}">${coachText(food,fuel,fp,fup)}</div></div>
 <div class="fsection"><h2>Unser Weg</h2><div class="fsteps">
  <div class="fstep"><div class="fnum">1</div><div><b>2.000 € Puffer halten</b><span>Damit keine Rücklastschrift mehr passiert und unerwartete Rechnungen uns nicht aus der Bahn werfen.</span></div></div>
  <div class="fstep"><div class="fnum">2</div><div><b>Ab Oktober +900 € automatisch weg</b><span>Am Gehaltstag direkt aufs Hauskonto. Nicht erst am Monatsende schauen, was übrig ist.</span></div></div>
  <div class="fstep"><div class="fnum">3</div><div><b>Ikano abbauen</b><span>Keine neuen Ratenkäufe. Offener Betrag aktuell ca. ${eur(S.ikanoOpen)}.</span></div></div>
  <div class="fstep"><div class="fnum">4</div><div><b>Zusätzliche Ersparnis behalten</b><span>Wenn Einkauf, Shopping oder Tanken unter dem Limit bleiben, geht der Rest ebenfalls aufs Hauskonto.</span></div></div>
 </div></div>
 <div class="fsection"><div class="ftoggle"><div><b>Nebenjob in der Anzeige</b><div class="fsub">Für die Hausrate trotzdem nicht fest einplanen.</div></div><button id="fSide">${S.sideJobEnabled?'AN':'AUS'}</button></div></div>
 <div class="fsection"><div class="fplan"><b>Gemeinsames Ziel</b><p>Der Lebensstandard soll durch die Gehaltserhöhung nicht automatisch teurer werden. Erst sparen, dann ausgeben. So wird aus dem neuen Einkommen echtes Eigenkapital.</p></div></div>
 <div class="fmuted">Die Detailanalyse, Fixkosten und der lernende Einkauf-/Tank-Coach laufen im Hintergrund weiter. Dieser Bildschirm zeigt euch nur das, was ihr im Alltag gemeinsam braucht.</div>`;
 document.body.appendChild(shell);document.body.style.overflow='hidden';
 document.getElementById('fDetails').onclick=()=>{shell.remove();document.body.style.overflow='';sessionStorage.setItem('fp_family_hidden','1')};
 document.getElementById('fSide').onclick=()=>{S.sideJobEnabled=!S.sideJobEnabled;save();render()};
 }
function coachText(food,fuel,fp,fup){if(!food&&!fuel)return 'Noch keine aktuellen Monatsdaten im Coach. Unsere Regel bleibt trotzdem einfach: Einkauf max. '+eur(S.foodTarget)+', Tanken max. '+eur(S.fuelTarget)+'. Nach dem CSV-Import lernt die App euer echtes Tempo.';let a=[];if(food)a.push(fp.ok?'Einkauf liegt aktuell auf Kurs.':'Einkauf läuft zu schnell: Hochrechnung ca. '+eur(fp.proj)+'.');if(fuel)a.push(fup.ok?'Tanken liegt aktuell auf Kurs.':'Tanken läuft zu schnell: Hochrechnung ca. '+eur(fup.proj)+'.');return a.join(' ')}
window.FinanzPilotFamily={show:()=>{sessionStorage.removeItem('fp_family_hidden');render()},settings:S};
setTimeout(()=>{if(sessionStorage.getItem('fp_family_hidden')!=='1')render();},500);
})();
