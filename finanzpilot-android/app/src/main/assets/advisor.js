(()=>{
  if(window.__finanzAdvisorUI)return; window.__finanzAdvisorUI=true;
  const fmt=n=>new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(Number(n||0));
  const exact=n=>new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(n||0));
  const readBool=(k,d=false)=>localStorage.getItem(k)==null?d:localStorage.getItem(k)==='1';
  const saveBool=(k,v)=>localStorage.setItem(k,v?'1':'0');
  const baseline={
    mainNet:4600, childBenefit:518, sideJob:524,
    fixedMandatory:1486, fixedOptional:51, fixedTotal:1537,
    variableAvg:3559, foodAvg:1601, shopAvg:1114,
    foodTarget:1250, shopTarget:600,
    installments:788, ikano:4500, ikanoLimit:5000, ikanoRate:160,
    electricity:198, gas:201, hukYear:1803.22, hukDue:'2026-10-17',
    phoneTariff:65, phoneDevice:42, giroBuffer:2000
  };

  function addStyles(){
    const s=document.createElement('style');
    s.textContent=`
      #advisor .adv-hero{padding:17px;border:1px solid #31516c;border-radius:20px;background:linear-gradient(135deg,#14375b,#0c2947);margin-bottom:12px}
      #advisor .adv-score{font-size:40px;font-weight:900;line-height:1;margin:5px 0 6px}
      #advisor .adv-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:9px}
      #advisor .adv-card{background:#102944;border:1px solid #294a67;border-radius:17px;padding:13px}
      #advisor .adv-label{font-size:11px;color:#9fb2c8}.adv-value{font-size:20px;font-weight:850;margin-top:5px}
      #advisor .adv-section{margin-top:17px}#advisor .adv-section h2{font-size:17px;margin:0 0 9px}
      #advisor .adv-task{display:grid;grid-template-columns:32px minmax(0,1fr) auto;gap:9px;align-items:start;padding:11px 0;border-bottom:1px solid #203c55}
      #advisor .adv-task:last-child{border-bottom:0}.adv-num{width:30px;height:30px;border-radius:10px;background:#1a4167;display:grid;place-items:center;font-weight:900}
      #advisor .adv-task b{font-size:13px}.adv-task p{margin:3px 0 0;font-size:11px;color:#9fb2c8;line-height:1.4}.adv-tag{font-size:10px;padding:5px 7px;border-radius:999px;white-space:nowrap;border:1px solid #3b5770}
      #advisor .red{color:#ff8790;background:#392128}.orange{color:#ffd08a;background:#352b1c}.green{color:#83e5b7;background:#17372d}.blue{color:#a9d0ff;background:#173657}
      #advisor .adv-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;padding:10px 0;border-bottom:1px solid #203c55}#advisor .adv-row:last-child{border-bottom:0}
      #advisor .adv-row b{font-size:13px}.adv-row small{display:block;color:#9fb2c8;margin-top:2px;line-height:1.35}.adv-right{text-align:right;font-weight:850}
      #advisor .adv-switch{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid #203c55}.adv-switch:last-child{border-bottom:0}
      #advisor input[type=checkbox]{width:22px;height:22px;accent-color:#39d98a}.adv-input{width:108px;background:#0a2037;color:#fff;border:1px solid #294a67;border-radius:10px;padding:8px;text-align:right;font-weight:800}
      #advisor .adv-alert{border:1px solid #5d3841;background:#2c1d24;border-radius:15px;padding:12px;margin-top:8px}.adv-alert.orangeBox{border-color:#5e4c2d;background:#2b261b}.adv-alert.greenBox{border-color:#2d624f;background:#142d25}
      #advisor .adv-alert b{font-size:13px}.adv-alert p{font-size:11px;color:#d5c0c4;margin:4px 0 0;line-height:1.45}.adv-alert.greenBox p{color:#b8d9ca}.adv-alert.orangeBox p{color:#dbc9a9}
      #advisor .progress{height:10px;border-radius:99px;background:#081a2c;overflow:hidden;margin-top:8px}.progress>span{display:block;height:100%;border-radius:99px;background:#66a9ff}
      #advisor .adv-mini{font-size:11px;color:#9fb2c8;line-height:1.45}.adv-btn{width:100%;border:0;border-radius:13px;padding:12px;background:#2d7ce6;color:#fff;font-weight:850;margin-top:9px}
      #advisorNav .ico{font-size:19px}
      @media(min-width:600px){#advisor .adv-grid{grid-template-columns:repeat(4,1fr)}}`;
    document.head.appendChild(s);
  }

  function createView(){
    const main=document.querySelector('main.content')||document.querySelector('main');
    if(!main)return;
    const sec=document.createElement('section'); sec.id='advisor'; sec.className='view';
    sec.innerHTML=`
      <div class="adv-hero">
        <div class="eyebrow">Finanzberater · Haus-Modus</div>
        <div class="adv-score" id="advScore">–</div>
        <div class="note" id="advScoreText">Ich bewerte nicht nur Ausgaben, sondern ob eure Struktur haustauglich wird.</div>
        <div class="progress"><span id="advScoreBar" style="width:0%"></span></div>
      </div>
      <div class="adv-grid">
        <div class="adv-card"><div class="adv-label">Sicheres Einkommen</div><div class="adv-value" id="advSafeIncome">–</div><div class="adv-mini">Hauptjob + Kindergeld</div></div>
        <div class="adv-card"><div class="adv-label">Mit Nebenjob</div><div class="adv-value" id="advIncomeSide">–</div><div class="adv-mini">nicht für Hausrate verplanen</div></div>
        <div class="adv-card"><div class="adv-label">Ziel-Überschuss</div><div class="adv-value" id="advSurplus">–</div><div class="adv-mini">nach aktuellen Sparzielen</div></div>
        <div class="adv-card"><div class="adv-label">Sparhebel</div><div class="adv-value" id="advPotential">–</div><div class="adv-mini">Food + Shopping</div></div>
      </div>

      <div class="adv-section"><h2>Was ich dir jetzt rate</h2><div class="adv-card" id="advTasks"></div></div>

      <div class="adv-section"><h2>Fixkosten mit Berater-Brille</h2><div class="adv-card">
        <div class="adv-row"><div><b>Strom · LichtBlick</b><small>198 €/Monat · nicht pauschal „zu teuer“ nennen, bevor kWh und Tarif geprüft sind</small></div><div class="adv-right orange">prüfen</div></div>
        <div class="adv-row"><div><b>Gas · Grünwelt</b><small>201 €/Monat · Verbrauch, Arbeitspreis und Grundpreis entscheiden</small></div><div class="adv-right orange">prüfen</div></div>
        <div class="adv-row"><div><b>Strom + Gas zusammen</b><small>399 €/Monat = 4.788 €/Jahr · großer Hebel, deshalb Tarif-/Verbrauchscheck sinnvoll</small></div><div class="adv-right">399 €</div></div>
        <div class="adv-row"><div><b>HUK24 Kfz</b><small>1.803,22 €/Jahr · monatlich 150,27 € zurücklegen; nächste Fälligkeit 17.10.2026</small></div><div class="adv-right orange">150 €</div></div>
        <div class="adv-row"><div><b>Telefonica</b><small>Tarif ca. 65 € + Geräte-Rate ca. 42 € = ca. 107 €/Monat</small></div><div class="adv-right orange">prüfen</div></div>
        <div class="adv-row"><div><b>Finanzierungen/Raten</b><small>Auto, Ikano, AMC, OTTO, Telefonica-Gerät · dieser Block schwächt die Hausfinanzierung</small></div><div class="adv-right red">≈ 788 €</div></div>
        <div class="adv-row"><div><b>Freiwillige feste Kosten</b><small>Abos/Mitgliedschaften ca. 51 €/Monat · nicht kritisch, aber leicht optimierbar</small></div><div class="adv-right blue">≈ 51 €</div></div>
      </div></div>

      <div class="adv-section"><h2>Variable Kosten · Limits</h2><div class="adv-card">
        <div class="adv-row"><div><b>Lebensmittel + Drogerie</b><small>Ø 1.601 €/Monat · Ziel 1.250 €</small></div><div class="adv-right orange">−351 €</div></div>
        <div class="adv-row"><div><b>Shopping + Kleidung</b><small>Ø 1.114 €/Monat · Ziel max. 600 €</small></div><div class="adv-right red">−514 €</div></div>
        <div class="adv-row"><div><b>Bargeld</b><small>möglichst ≤ 200 €/Monat, damit die Ausgaben nachvollziehbar bleiben</small></div><div class="adv-right orange">Deckel</div></div>
        <div class="adv-row"><div><b>Neue Ratenkäufe</b><small>Bis Ikano abgebaut ist: keine neuen OTTO-/Karten-/Konsumraten</small></div><div class="adv-right red">0 € neu</div></div>
      </div></div>

      <div class="adv-section"><h2>Haus-Check konfigurieren</h2><div class="adv-card">
        <div class="adv-switch"><div><b>Nebenjob ist aktuell vorhanden</b><div class="adv-mini">wird als Bonus gerechnet, nicht als notwendiges Haus-Einkommen</div></div><input id="advSide" type="checkbox"></div>
        <div class="adv-switch"><div><b>2.000 € Giro-Puffer steht</b><div class="adv-mini">unter diesen Betrag soll das Girokonto nicht fallen</div></div><input id="advBuffer" type="checkbox"></div>
        <div class="adv-switch"><div><b>HUK 1.803,22 € bereits reserviert</b><div class="adv-mini">sonst hat diese Fälligkeit vor Extra-Tilgung Priorität</div></div><input id="advHuk" type="checkbox"></div>
        <div class="adv-switch"><div><b>Ikano aktuell offen</b><div class="adv-mini">90 % Auslastung bei 4.500 € von 5.000 €</div></div><input id="advIkano" class="adv-input" inputmode="decimal" value="4500"></div>
      </div></div>

      <div class="adv-section"><h2>Energie-Check vorbereiten</h2><div class="adv-card">
        <div class="adv-switch"><div><b>Stromverbrauch/Jahr</b><div class="adv-mini">aus letzter Jahresabrechnung in kWh</div></div><input id="advPowerKwh" class="adv-input" inputmode="decimal" placeholder="kWh"></div>
        <div class="adv-switch"><div><b>Gasverbrauch/Jahr</b><div class="adv-mini">aus letzter Jahresabrechnung in kWh</div></div><input id="advGasKwh" class="adv-input" inputmode="decimal" placeholder="kWh"></div>
        <div class="adv-alert orangeBox"><b>Warum ich nicht nur den Abschlag bewerte</b><p>198 € Strom oder 201 € Gas kann durch hohen Verbrauch, einen teuren Tarif oder eine bewusst hohe Abschlagsreserve entstehen. Für eine sinnvolle Beratung brauche ich Jahresverbrauch + Arbeitspreis + Grundpreis. Die App merkt sich die kWh, sobald du sie einträgst.</p></div>
      </div></div>

      <div class="adv-section"><h2>Mein Haus-Modus für euch</h2><div id="advHousePlan"></div></div>
      <button class="adv-btn" id="advRefresh" type="button">Berater-Check neu berechnen</button>
    `;
    main.appendChild(sec);
  }

  function addNav(){
    const nav=document.querySelector('.nav'); if(!nav||document.getElementById('advisorNav'))return;
    nav.style.gridTemplateColumns='repeat(6,1fr)';
    const b=document.createElement('button'); b.id='advisorNav'; b.type='button'; b.innerHTML='<span class="ico">◈</span>Berater'; nav.appendChild(b);
    b.addEventListener('click',()=>{
      document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
      document.getElementById('advisor')?.classList.add('active');
      document.querySelectorAll('.nav button').forEach(x=>x.classList.remove('active')); b.classList.add('active');
      window.scrollTo({top:0,behavior:'smooth'}); render();
    });
    nav.querySelectorAll('button:not(#advisorNav)').forEach(x=>x.addEventListener('click',()=>b.classList.remove('active')));
  }

  function daysTo(date){return Math.max(0,Math.ceil((new Date(date+'T12:00:00')-new Date())/86400000));}
  function calcScore(){
    const buffer=readBool('fp_adv_buffer'),huk=readBool('fp_adv_huk'),ikano=Number(localStorage.getItem('fp_adv_ikano')||baseline.ikano);
    let score=100;
    score-=Math.min(22,baseline.installments/40);
    score-=Math.min(18,Math.max(0,baseline.foodAvg-baseline.foodTarget)/20);
    score-=Math.min(22,Math.max(0,baseline.shopAvg-baseline.shopTarget)/25);
    if(ikano>0)score-=Math.min(14,ikano/baseline.ikanoLimit*14);
    if(!buffer)score-=12; if(!huk)score-=8;
    return Math.max(0,Math.min(100,Math.round(score)));
  }

  function taskHtml(){
    const huk=readBool('fp_adv_huk'),buffer=readBool('fp_adv_buffer'),side=readBool('fp_adv_side',true),ikano=Number(localStorage.getItem('fp_adv_ikano')||baseline.ikano);
    const dueDays=daysTo(baseline.hukDue), months=Math.max(1,Math.ceil(dueDays/30.4)), hukMonthly=huk?0:baseline.hukYear/months;
    const items=[];
    if(!huk)items.push(['HUK-Fälligkeit absichern',`${exact(baseline.hukYear)} bis 17.10.2026. Bei ${months} Restmonat(en) sind grob ${fmt(hukMonthly)} pro Monat zu reservieren, bevor Extra-Tilgung aggressiv wird.`,'SOFORT','red']);
    if(!buffer)items.push(['2.000 € Liquiditätspuffer herstellen','Das ist dein Schutz gegen Rücklastschriften und ungeplante Rechnungen. Erst wenn der Puffer steht, gilt überschüssiges Geld als wirklich frei.','PRIO 1','red']);
    if(ikano>0)items.push(['Ikano gezielt abbauen',`${fmt(ikano)} offen. Nach Puffer/HUK würde ich den Nebenjob${side?' + Sparhebel':''} bevorzugt hierhin lenken. Keine neuen Konsumraten.`,'PRIO 2','orange']);
    items.push(['Shopping auf 600 € deckeln',`Der Jahresschnitt liegt bei ca. ${fmt(baseline.shopAvg)}. Das ist allein ein Potenzial von rund ${fmt(baseline.shopAvg-baseline.shopTarget)} monatlich.`,'MONATLICH','orange']);
    items.push(['Lebensmittel auf 1.250 € führen',`Nicht radikal sparen: ein Wochenbudget von ca. ${fmt(baseline.foodTarget/4.33)} gibt euch weiterhin Spielraum, verhindert aber die 1.600-€-Monate.`,'MONATLICH','blue']);
    return items.slice(0,5).map((x,i)=>`<div class="adv-task"><div class="adv-num">${i+1}</div><div><b>${x[0]}</b><p>${x[1]}</p></div><span class="adv-tag ${x[3]}">${x[2]}</span></div>`).join('');
  }

  function housePlan(){
    const side=readBool('fp_adv_side',true),buffer=readBool('fp_adv_buffer'),huk=readBool('fp_adv_huk'),ikano=Number(localStorage.getItem('fp_adv_ikano')||baseline.ikano);
    const safe=baseline.mainNet+baseline.childBenefit;
    const potential=(baseline.foodAvg-baseline.foodTarget)+(baseline.shopAvg-baseline.shopTarget);
    const targetVariable=baseline.variableAvg-potential;
    const targetTotal=baseline.fixedTotal+targetVariable;
    const baseSurplus=safe-targetTotal;
    const sideSurplus=baseSurplus+(side?baseline.sideJob:0);
    const debtFreeGain=ikano<=0?baseline.ikanoRate:0;
    const boxes=[];
    boxes.push(`<div class="adv-alert ${baseSurplus>=800?'greenBox':'orangeBox'}"><b>1 · Hausrate nie vom Nebenjob abhängig machen</b><p>Mit dem sicheren Einkommen von ${fmt(safe)} und den Zielbudgets bleiben rechnerisch etwa ${fmt(baseSurplus)} im Monat. Der Nebenjob soll Reserve, Tilgung und Eigenkapital beschleunigen – nicht eine zu hohe Rate retten.</p></div>`);
    boxes.push(`<div class="adv-alert ${buffer?'greenBox':'orangeBox'}"><b>2 · Liquidität vor maximaler Tilgung</b><p>${buffer?'Der 2.000-€-Puffer ist als erledigt markiert.':'Der 2.000-€-Puffer fehlt noch.'} ${huk?'Die HUK-Fälligkeit ist reserviert.':'Zusätzlich ist die HUK-Fälligkeit noch nicht als reserviert markiert.'}</p></div>`);
    boxes.push(`<div class="adv-alert ${ikano<=0?'greenBox':'orangeBox'}"><b>3 · Konsumschulden vor Hauskauf reduzieren</b><p>${ikano>0?`Ikano steht bei ${fmt(ikano)}. Jede beseitigte Konsumrate verbessert eure Haushaltsrechnung und macht die spätere Immobilienrate robuster.`:`Ikano ist als erledigt markiert; dadurch sind ca. ${fmt(baseline.ikanoRate)} monatlich zusätzlich frei.`}</p></div>`);
    boxes.push(`<div class="adv-alert greenBox"><b>4 · 6-Monats-Haus-Probelauf</b><p>Sobald Puffer und kurzfristige Fälligkeiten stehen: jeden Monat mindestens ${fmt(Math.max(1000,Math.round(sideSurplus/50)*50))} auf ein separates Hauskonto überweisen. Wenn das sechs Monate ohne Rückholung funktioniert, habt ihr einen belastbaren Praxistest.</p></div>`);
    return boxes.join('');
  }

  function render(){
    const side=readBool('fp_adv_side',true); const safe=baseline.mainNet+baseline.childBenefit;
    const potential=(baseline.foodAvg-baseline.foodTarget)+(baseline.shopAvg-baseline.shopTarget);
    const targetVariable=baseline.variableAvg-potential; const targetTotal=baseline.fixedTotal+targetVariable;
    const surplus=safe-targetTotal+(side?baseline.sideJob:0);
    const score=calcScore();
    document.getElementById('advScore').textContent=score+'/100'; document.getElementById('advScoreBar').style.width=score+'%';
    document.getElementById('advScoreBar').style.background=score>=75?'#39d98a':score>=55?'#ffb24f':'#ff6874';
    document.getElementById('advScoreText').textContent=score>=75?'Gute Richtung. Jetzt Stabilität über mehrere Monate beweisen.':score>=55?'Solide Basis, aber Raten und variable Ausgaben bremsen den Hauskauf noch.':'Hausmodus noch nicht stabil genug: zuerst Liquidität und Konsumschulden ordnen.';
    document.getElementById('advSafeIncome').textContent=fmt(safe); document.getElementById('advIncomeSide').textContent=fmt(safe+(side?baseline.sideJob:0));
    document.getElementById('advSurplus').textContent=fmt(surplus); document.getElementById('advPotential').textContent=fmt(potential);
    document.getElementById('advTasks').innerHTML=taskHtml(); document.getElementById('advHousePlan').innerHTML=housePlan();
    document.getElementById('advSide').checked=side; document.getElementById('advBuffer').checked=readBool('fp_adv_buffer'); document.getElementById('advHuk').checked=readBool('fp_adv_huk');
    document.getElementById('advIkano').value=localStorage.getItem('fp_adv_ikano')||String(baseline.ikano);
    document.getElementById('advPowerKwh').value=localStorage.getItem('fp_adv_power_kwh')||''; document.getElementById('advGasKwh').value=localStorage.getItem('fp_adv_gas_kwh')||'';
  }

  function bind(){
    document.getElementById('advSide')?.addEventListener('change',e=>{saveBool('fp_adv_side',e.target.checked);render()});
    document.getElementById('advBuffer')?.addEventListener('change',e=>{saveBool('fp_adv_buffer',e.target.checked);render()});
    document.getElementById('advHuk')?.addEventListener('change',e=>{saveBool('fp_adv_huk',e.target.checked);render()});
    document.getElementById('advIkano')?.addEventListener('change',e=>{localStorage.setItem('fp_adv_ikano',String(Math.max(0,Number(String(e.target.value).replace(',','.'))||0)));render()});
    document.getElementById('advPowerKwh')?.addEventListener('change',e=>localStorage.setItem('fp_adv_power_kwh',String(Math.max(0,Number(String(e.target.value).replace(',','.'))||0))));
    document.getElementById('advGasKwh')?.addEventListener('change',e=>localStorage.setItem('fp_adv_gas_kwh',String(Math.max(0,Number(String(e.target.value).replace(',','.'))||0))));
    document.getElementById('advRefresh')?.addEventListener('click',render);
  }

  function init(){addStyles();createView();addNav();bind();render();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else setTimeout(init,0);
})();