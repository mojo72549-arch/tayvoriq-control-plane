(function(){
  function patchedVcat(r){
    const t=(r.text||'').toLowerCase(),c=(r.cat||'').toLowerCase();
    if(/emre guerdal|emre gürdal/.test(t)) return 'Schuldenzahlung Emre';
    if(fixedRule(r))return null;
    if(/bargeldauszahlung|geldautomat/.test(t)||c.includes('bargeld'))return'Bargeld';
    if(/aral|shell|esso|avia|jet tank|tankstelle|totalenergies|bft |eni |agip/.test(t))return'Tanken';
    if(/restaurant|imbiss|mcdonald|burger king|lieferando|doener|döner|pizza|kebab|cafe |café /.test(t))return'Essen unterwegs';
    if(c.includes('lebensmittel')||c.includes('drogerie')||/lidl|aldi|kaufland|rewe|edeka|penny|netto|rossmann|dm drogerie|müller drogerie|mueller drogerie|supermarkt|backkultur|bäck|baeck/.test(t))return'Lebensmittel & Drogerie';
    if(c.includes('bekleidung')||c.includes('einkäufe')||c.includes('einkaeufe')||/amazon|action |tedi|woolworth|primark|zara|deichmann|babyone|temu|otto/.test(t))return'Shopping';
    if(c.includes('gesundheit')||/apotheke/.test(t))return'Gesundheit';
    if(c.includes('freizeit')||/netflix|kino/.test(t))return'Freizeit';
    if(c.includes('wohnen')||c.includes('garten'))return'Haushalt/Wohnen';
    if(/rückgabe lastschrift|rueckgabe lastschrift|rücklast|ruecklast/.test(t))return'Rücklastschrift';
    return'Sonstiges';
  }

  function patchedAnalyze(text){
    const rr=parseCSV(text);if(rr.length<2)throw Error('CSV leer');
    const h=rr.shift().map(x=>x.trim().toLowerCase()),ix=(...n)=>{for(const z of n){const i=h.indexOf(z.toLowerCase());if(i>=0)return i}return-1};
    const di=ix('buchungstag','valutadatum'),ai=ix('betrag'),ci=ix('kategorie'),pi=ix('verwendungszweck'),mi=ix('beguenstigter/zahlungspflichtiger','begünstigter/zahlungspflichtiger'),bi=ix('buchungstext');
    if(di<0||ai<0)throw Error('BW-Bank-Spalten nicht erkannt');
    const rows=[];
    for(const a of rr){
      const date=pd(a[di]);if(!date)continue;
      const amount=num(a[ai]),merchant=norm(a[mi]||''),purpose=a[pi]||'',cat=a[ci]||'',bt=a[bi]||'',text=(merchant+' '+purpose+' '+cat+' '+bt).toLowerCase();
      rows.push({date,amount,merchant,purpose,cat,bt,text});
    }
    if(!rows.length)throw Error('Keine verwertbaren Buchungen gefunden');
    rows.sort((a,b)=>a.date-b.date);
    const max=rows.at(-1).date,min=rows[0].date;
    const salaries=rows.filter(r=>r.amount>1000&&/vpv|gehalt|lohn/.test(r.text));
    const cycleStart=salaries.length?salaries.at(-1).date:new Date(max.getFullYear(),max.getMonth(),24);
    if(cycleStart>max)cycleStart.setMonth(cycleStart.getMonth()-1);
    const cycle=rows.filter(r=>r.date>=cycleStart&&r.date<=max),income=cycle.filter(r=>r.amount>0).reduce((s,r)=>s+r.amount,0),out=-cycle.filter(r=>r.amount<0).reduce((s,r)=>s+r.amount,0),net=income-out;

    const buckets={};
    for(const r of rows){
      if(r.amount>=0)continue;
      const q=fixedRule(r);if(!q)continue;
      const [name,category,interval]=q;
      (buckets[name]=buckets[name]||{name,category,interval,items:[]}).items.push(r);
    }
    const active=[],history=[];
    for(const b of Object.values(buckets)){
      const by={};
      for(const r of b.items){const k=mk(r.date);if(!by[k]||r.date>by[k].date)by[k]=r}
      const vals=Object.values(by).sort((a,b)=>a.date-b.date),last=vals.at(-1),age=days(last.date,max),amount=b.interval==='annual'?(-last.amount)/12:med(vals.slice(-3).map(r=>-r.amount)),o={name:b.name,category:b.category,interval:b.interval,amount,last:last.date.toISOString(),months:vals.length};
      const destination=b.interval==='annual'?(age<=400?active:history):(age<=75?active:history);
      destination.push(o);
    }
    active.sort((a,b)=>b.amount-a.amount);history.sort((a,b)=>b.last.localeCompare(a.last));
    const fixedMonthly=active.reduce((s,x)=>s+x.amount,0),financeMonthly=active.filter(x=>x.category==='Finanzierungen').reduce((s,x)=>s+x.amount,0);

    const cat={},merchants={};
    for(const r of cycle){
      if(r.amount>=0)continue;
      const c=patchedVcat(r);if(!c)continue;
      cat[c]=(cat[c]||0)-r.amount;
      merchants[c]=merchants[c]||{};
      const n=(c==='Sonstiges'||c==='Rücklastschrift')?'Weitere Ausgabe':r.merchant;
      merchants[c][n]=(merchants[c][n]||0)-r.amount;
    }
    const top=cycle.filter(r=>r.amount<0).map(r=>({name:patchedVcat(r)||fixedRule(r)?.[0]||'Ausgabe',merchant:(patchedVcat(r)==='Sonstiges'?'Weitere Ausgabe':r.merchant),amount:-r.amount,date:r.date.toISOString()})).sort((a,b)=>b.amount-a.amount).slice(0,12);
    const returns=cycle.filter(r=>/rückgabe lastschrift|rueckgabe lastschrift|rücklast|ruecklast/.test(r.text)).length;
    return{min:min.toISOString(),max:max.toISOString(),cycleStart:cycleStart.toISOString(),elapsed:Math.max(1,days(cycleStart,max)+1),cycleDays:Math.max(28,Math.min(35,days(cycleStart,new Date(cycleStart.getFullYear(),cycleStart.getMonth()+1,cycleStart.getDate())))),income,out,net,fixedMonthly,financeMonthly,active,history,cat,merchants,top,returns};
  }

  vcat=patchedVcat;
  analyze=patchedAnalyze;
})();
