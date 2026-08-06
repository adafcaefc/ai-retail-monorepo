/* =====================================================================
   AI RETAIL 360 — DEMAND FORECASTING (enriched v7). Vanilla JS, offline.
   ===================================================================== */
let LANG='en', CHALLENGE=false;
function T(en,id){return LANG==='id'?id:en;}
function rng(seed){let s=seed>>>0;return()=>{s=(s*1664525+1013904223)>>>0;return s/4294967296;};}
function fmt(n){return Math.round(n).toLocaleString('en-US');}
function pct(n){return(n>=0?'+':'')+n.toFixed(1)+'%';}
const G=id=>document.getElementById(id);

/* ---------- master data ---------- */
const STORES=[
  {id:'S01',name:'HERO Kemang',size:1.10,cluster:'Premium',health:1.00,idx:1.06},
  {id:'S02',name:'HERO Gandaria City',size:1.35,cluster:'Urban Mall',health:0.82,idx:1.18},
  {id:'S03',name:'HERO Pondok Indah',size:1.25,cluster:'Premium',health:1.18,idx:1.12},
  {id:'S04',name:'HERO BSD City',size:1.00,cluster:'Suburban',health:0.72,idx:0.90},
  {id:'S05',name:'HERO Kelapa Gading',size:1.15,cluster:'Urban Mall',health:0.94,idx:1.02},
  {id:'S06',name:'HERO Bali Sunset',size:0.85,cluster:'Resort',health:1.28,idx:0.86},
];
const CLUSTERS=['Premium','Urban Mall','Suburban','Resort'];
const CATS=[
  {id:'FRT',name:'Fruit',fresh:true},{id:'VEG',name:'Vegetable',fresh:true},{id:'MEA',name:'Meat & Poultry',fresh:true},
  {id:'BAK',name:'Bakery',fresh:true},{id:'DAI',name:'Dairy',fresh:true},
  {id:'BEV',name:'Beverages',fresh:false},{id:'SNK',name:'Snacks',fresh:false},{id:'HOU',name:'Household',fresh:false},{id:'PCR',name:'Personal Care',fresh:false},
];
const CCOLOR={FRT:'#E8792B',VEG:'#107C41',MEA:'#D13438',BAK:'#C19C00',DAI:'#0078D4',BEV:'#008575',SNK:'#5C2D91',HOU:'#0A9ED4',PCR:'#B4009E'};
const SKU_NAMES={
  FRT:['Apple Fuji 1kg','Banana Cavendish 1kg','Orange Sunkist 1kg','Mango Harum 1kg'],
  VEG:['Bok Choy 250g','Tomato 500g','Spinach 200g','Carrot 500g'],
  MEA:['Chicken Fillet 500g','Beef Slice 300g','Salmon 200g','Chicken Wing 500g'],
  BAK:['White Bread 400g','Croissant 4pcs','Choco Donut 6pcs','Baguette 250g'],
  DAI:['Fresh Milk 1L','Greek Yogurt 200g','Cheese Slice 170g','Butter 200g'],
  BEV:['Mineral Water 600ml','Cola 1.5L','Orange Juice 1L','Canned Coffee 240ml'],
  SNK:['Potato Chips 68g','Choco Wafer 55g','Roasted Peanuts 200g','Butter Biscuit 300g'],
  HOU:['Dish Soap 800ml','Floor Cleaner 1L','Facial Tissue 250s','Trash Bag 30s'],
  PCR:['Shampoo 340ml','Body Wash 500ml','Toothpaste 190g','Hand Soap 250ml'],
};
const SEAS_FRESH=[0.95,0.92,0.98,1.00,1.05,1.08,1.12,1.10,1.02,1.00,1.06,1.20];
const SEAS_DRY=[1.02,0.98,1.00,1.01,1.04,1.06,1.10,1.05,1.00,1.02,1.08,1.25];
const DOW=[0.85,0.90,0.95,1.00,1.15,1.35,1.25];
const MONTH=6;
const SKUS=[];let sid=0;
CATS.forEach((c,ci)=>SKU_NAMES[c.id].forEach((nm,ii)=>{
  const r=rng(100+ci*17+ii*7);const base=(c.fresh?18:26)*(0.7+r()*1.1);
  SKUS.push({id:c.id+'-'+String(++sid).padStart(3,'0'),name:nm,catId:c.id,cat:c.name,fresh:c.fresh,base,
    price:(c.fresh?18000:12000)*(0.6+r()*1.5),marginPct:0.12+r()*0.16,lead:c.fresh?2:4,onHandDays:c.fresh?2.4:8.5,
    openPO:Math.round(base*(c.fresh?1:3)*(0.5+r())),safety:c.fresh?1:3,expiry:c.fresh?[2,3,4,5,7][Math.floor(r()*5)]:180,
    vendor:['PT Sinar Segar','PT Boga Nusantara','PT Prima Dairy','CV Fresh Farm','PT Anugrah Snack'][Math.floor(r()*5)],
    dc:['DC Cibitung','DC Cikarang','DC Balaraja'][Math.floor(r()*3)],
    viral:r()<0.22,promo:r()<0.32,growth:0.9+r()*0.5});
}));

/* ---------- state ---------- */
const state={agent:'df',itemMode:'all',cats:new Set(),skus:new Set(),storeMode:'all',stores:new Set(),
  period:'daily',horizon:8,matrixDim:'store',
  triggers:{},sim:{price:0,promo:0,seas:0,viral:0,lead:3,safe:2}};
const TRIGGERS=[['minmax','Min / Max',1],['seasonal','Calendar Seasonal',1],['reorder','Reorder Point',1],
  ['ads','ADS Fresh / AMS Non-Fresh',1],['lead','Vendor Lead Time',1],['onhand','On Hand',1],['openpo','Open PO',1],
  ['safety','Safety Stock',1],['expiry','Expired Date DC',1],['custom','Additional Custom Formula',0],['history','Data History',1],
  ['calendar','Retail Calendar (03:00 cut-off)',1],['viral','Viral Market Trend',1],['promotion','Promotion',1],
  ['assortment','Assortment',0],['promo','Promo',1],['loyalty','Loyalty',0]];
TRIGGERS.forEach(t=>state.triggers[t[0]]=!!t[2]);
let scenarios=[],actionLog=[],actionState='pending',simRun=null,received={},poWF=null;

/* ---------- scope helpers ---------- */
function activeSKUs(){
  if(state.itemMode==='cat'&&state.cats.size) return SKUS.filter(s=>state.cats.has(s.catId));
  if(state.itemMode==='item'&&state.skus.size) return SKUS.filter(s=>state.skus.has(s.id));
  return SKUS;
}
function activeStores(){ if(state.storeMode==='sel'&&state.stores.size) return STORES.filter(s=>state.stores.has(s.id)); return STORES; }
function storeFactor(){ return activeStores().reduce((a,s)=>a+s.size,0); }
function triggerAdj(){const t=state.triggers;let m=1;if(t.viral)m*=1.05;if(t.promotion||t.promo)m*=1.06;if(t.calendar)m*=0.99;if(t.loyalty)m*=1.02;return m;}
function scopeDailyBase(){let sum=0;activeSKUs().forEach(s=>sum+=s.base*(s.fresh?SEAS_FRESH:SEAS_DRY)[MONTH]);return sum*storeFactor();}
function simMult(i){const s=state.sim;let m=1;m*=(1+(s.price/100)*-0.9);m*=(1+(s.promo/100)*1.3);m*=(1+s.seas/100);m*=(1+(s.viral/100)*Math.max(0.3,1-i/20));return Math.max(0.2,m);}

/* ---------- period-aware series ---------- */
function periodMeta(){
  const D=scopeDailyBase();
  switch(state.period){
    case 'weekly': return {unit:D*7,histN:16,fcN:state.horizon,label:'week',pre:'W-',prf:'W+',mult:1};
    case 'monthly': return {unit:D*30,histN:18,fcN:Math.max(2,Math.round(state.horizon/4.33)),label:'month',pre:'M-',prf:'M+',mult:1};
    case 'quarterly': return {unit:D*91,histN:8,fcN:Math.max(1,Math.round(state.horizon/13)),label:'quarter',pre:'Q-',prf:'Q+',mult:1};
    case 'yearly': return {unit:D*365,histN:3,fcN:Math.max(1,Math.round(state.horizon/52)),label:'year',pre:'Y-',prf:'Y+',mult:1};
    default: return {unit:D,histN:42,fcN:Math.min(70,state.horizon*7),label:'day',pre:'D-',prf:'D+',mult:1};
  }
}
function genSeries(withSim){
  const m=periodMeta();const r=rng(hashScope());const hist=[],fc=[],band=[],labels=[];
  const tadj=triggerAdj();
  // history
  for(let i=m.histN;i>0;i--){
    let wave=1;
    if(state.period==='daily') wave=DOW[(999-i)%7];
    else if(state.period==='weekly') wave=1+0.10*Math.sin(i/2.3);
    else if(state.period==='monthly') wave=(activeSKUs().some(s=>s.fresh)?SEAS_FRESH:SEAS_DRY)[(MONTH-i%12+24)%12];
    else if(state.period==='quarterly') wave=1+0.08*Math.sin(i/1.5);
    else if(state.period==='yearly') wave=1-0.06*i;
    hist.push(Math.round(m.unit*wave*(0.9+r()*0.2)));
    labels.push(m.pre+i);
  }
  // forecast
  for(let i=0;i<m.fcN;i++){
    let wave=1;
    if(state.period==='daily') wave=DOW[i%7];
    else if(state.period==='weekly') wave=1+0.10*Math.sin((i+8)/2.3);
    else if(state.period==='monthly') wave=(activeSKUs().some(s=>s.fresh)?SEAS_FRESH:SEAS_DRY)[(MONTH+i)%12];
    else if(state.period==='quarterly') wave=1+0.08*Math.sin((i+6)/1.5);
    else if(state.period==='yearly') wave=1+0.05*(i+1);
    let v=m.unit*wave*tadj*(0.97+r()*0.05);
    if(withSim) v*=simMult(i);
    v=Math.round(v);const g=Math.min(0.30,0.05+0.0038*i);fc.push(v);band.push([Math.round(v*(1-g)),Math.round(v*(1+g))]);labels.push(m.prf+(i+1));
  }
  return {hist,fc,band,labels,histLabels:labels.slice(0,m.histN),fcLabels:labels.slice(m.histN)};
}
function hashScope(){let h=state.period.length*7+state.horizon;activeSKUs().forEach(s=>h+=s.id.charCodeAt(4));activeStores().forEach(s=>h+=s.size*13);return Math.floor(h)>>>0;}

/* ---------- KPIs ---------- */
const ALLSIZES=STORES.reduce((a,s)=>a+s.size,0);
const STATECOL={Stockout:'#D13438',Low:'#E8792B',Expiry:'#C77700',Overstock:'#5C2D91','Slow-mover':'#0A9ED4',Healthy:'#107C41'};
function stockFactor(s){const idn=parseInt(s.id.slice(4))||1;return 0.4+((idn*37)%100)/58;}
function healthFactor(){const st=activeStores();return st.length?st.reduce((a,s)=>a+(s.health||1),0)/st.length:1;}
function storeIdx(){const st=activeStores();return st.length?st.reduce((a,s)=>a+(s.idx||1),0)/st.length:1;}
function invMetrics(s){
  const seas=(s.fresh?SEAS_FRESH:SEAS_DRY)[MONTH];const sf=storeFactor();const frac=sf/ALLSIZES;
  const ads=s.base*seas*sf;
  const onHandU=s.base*s.onHandDays*stockFactor(s)*healthFactor()*sf;
  const reservedU=Math.round(onHandU*0.12);
  const openPOu=Math.round(s.openPO*frac);
  const position=Math.round(onHandU+openPOu);
  const dos=ads>0?position/ads:0;
  const rop=Math.round(ads*(s.lead+s.safety));
  const maxLevel=Math.round(ads*(s.lead+s.safety+4));
  let st='Healthy';
  if(position<rop*0.6)st='Stockout';
  else if(position<rop)st='Low';
  else if(s.fresh&&dos>s.expiry)st='Expiry';
  else if(!s.fresh&&dos>15)st='Overstock';
  else if(s.growth<1.0&&dos>10)st='Slow-mover';
  const value=Math.round(position*s.price);
  const excess=Math.round(Math.max(0,position-maxLevel)*s.price);
  const unitsExpiry=s.fresh?Math.max(0,Math.round(position-ads*s.expiry)):0;
  return {ads:Math.round(ads),onHandU:Math.round(onHandU),reservedU,openPOu,position,dos,rop,maxLevel,state:st,value,excess,unitsExpiry,price:s.price,expiryDays:s.fresh?s.expiry:null};
}
function genDaily(){const sv=state.period;state.period='daily';const s=genSeries(false);state.period=sv;return s;}
function computeK_INV(){
  const daily=genDaily();
  const list=activeSKUs().map(invMetrics);
  const stockout=list.filter(m=>m.state==='Stockout'||m.state==='Low').length;
  const overstock=list.filter(m=>m.state==='Overstock').length;
  const overstockVal=list.reduce((a,m)=>a+m.excess,0);
  const expiryUnits=list.reduce((a,m)=>a+m.unitsExpiry,0);
  const slow=list.filter(m=>m.state==='Slow-mover').length;
  const avgDOS=list.length?list.reduce((a,m)=>a+m.dos,0)/list.length:0;
  const invValue=list.reduce((a,m)=>a+m.value,0);
  const healthy=list.filter(m=>m.state==='Healthy').length;
  return {stockout,overstock,overstockVal,expiryUnits,slow,avgDOS,invValue,healthy,list,daily};
}
const KPIDEFS_INV=[
  {key:'stockout',color:'#D13438',lab:['Stockout-Risk SKUs','SKU Risiko Stockout'],fmt:k=>fmt(k.stockout),delta:k=>T('need action','perlu aksi'),dcls:()=>'down',
   f:'count( Position < ROP ) · Position = On Hand + Open PO',e:['SKUs below reorder point — risk of running out.','SKU di bawah reorder point — berisiko habis.'],val:k=>k.stockout},
  {key:'overstock',color:'#5C2D91',lab:['Overstock SKUs','SKU Overstock'],fmt:k=>fmt(k.overstock),delta:k=>'Rp '+fmt(k.overstockVal),dcls:()=>'',
   f:'count( Days of Supply > 45 ) · excess = Σ(Position−Max)×price',e:['Excess stock tying up working capital.','Stok berlebih yang mengikat modal kerja.'],val:k=>k.overstock},
  {key:'expiryUnits',color:'#C77700',lab:['Expiry-Risk Units','Unit Risiko Expiry'],fmt:k=>fmt(k.expiryUnits)+' u',delta:k=>T('fresh','fresh'),dcls:()=>'down',
   f:'Σ max(0, Position − ADS × shelf-life)',e:['Fresh units unlikely to sell before expiry.','Unit fresh yang mungkin tak terjual sebelum expiry.'],val:k=>k.expiryUnits},
  {key:'slow',color:'#0A9ED4',lab:['Slow-Moving SKUs','SKU Slow-Moving'],fmt:k=>fmt(k.slow),delta:k=>T('aging','menua'),dcls:()=>'',
   f:'count( growth < 1.0 AND Days of Supply > 22 )',e:['Aging, low-velocity items.','Item lambat & menua.'],val:k=>k.slow},
  {key:'avgDOS',color:'#0078D4',lab:['Avg Days of Supply','Rata Days of Supply'],fmt:k=>k.avgDOS.toFixed(1)+' d',delta:k=>T('target 7–21d','target 7–21h'),dcls:()=>'',
   f:'mean( Position ÷ ADS )',e:['Average days of cover across in-scope SKUs.','Rata-rata hari cover SKU dalam scope.'],val:k=>k.avgDOS},
  {key:'invValue',color:'#107C41',lab:['Inventory Value','Nilai Inventory'],fmt:k=>'Rp '+fmt(k.invValue),delta:k=>T('working capital','modal kerja'),dcls:()=>'',
   f:'Σ Position × unit price',e:['Total stock value in scope (working capital).','Total nilai stok dalam scope (modal kerja).'],val:k=>k.invValue},
];
function renderKPIs(){
  const k=computeK();const row=G('kpirow');row.innerHTML='';
  KPIDEFS.forEach(def=>{
    const el=document.createElement('div');el.className='kpi';
    el.innerHTML=`<div class="accent" style="background:${def.color}"></div><div class="drill">⤢</div>
      <div class="lab">${T(def.lab[0],def.lab[1])}</div>
      <div class="val" data-k="${def.key}">${def.fmt(k)}</div>
      <div class="delta ${def.dcls(k)}">${def.delta(k)}</div>
      <div class="spark">${spark(k.daily.hist.slice(-14),def.color)}</div>`;
    const v=el.querySelector('.val');
    v.addEventListener('mouseenter',e=>showFormula(e,def,k));v.addEventListener('mouseleave',hideFormula);
    el.addEventListener('click',()=>openDrawer(def,k));
    row.appendChild(el);
  });
}

/* ---------- SVG lib ---------- */
const NS='http://www.w3.org/2000/svg';
function E(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;}
function spark(v,c){const w=52,h=20,mn=Math.min(...v),mx=Math.max(...v),r=(mx-mn)||1;
  const p=v.map((x,i)=>`${(i/(v.length-1))*w},${h-((x-mn)/r)*h}`).join(' ');
  return `<svg width="${w}" height="${h}"><polyline points="${p}" fill="none" stroke="${c}" stroke-width="1.7"/></svg>`;}
function smoothPath(pts){ // catmull-rom to bezier
  if(pts.length<2)return'';let d=`M ${pts[0][0]},${pts[0][1]}`;
  for(let i=0;i<pts.length-1;i++){const p0=pts[i-1]||pts[i],p1=pts[i],p2=pts[i+1],p3=pts[i+2]||p2;
    const c1x=p1[0]+(p2[0]-p0[0])/6,c1y=p1[1]+(p2[1]-p0[1])/6,c2x=p2[0]-(p3[0]-p1[0])/6,c2y=p2[1]-(p3[1]-p1[1])/6;
    d+=` C ${c1x},${c1y} ${c2x},${c2y} ${p2[0]},${p2[1]}`;}return d;}
function lineChart(id,ser,opt={}){
  const w=G(id);w.innerHTML='';const W=w.clientWidth||620,H=opt.h||215,pl=40,pr=14,pt=12,pb=24;
  const all=[...ser.hist,...ser.fc,...ser.band.map(b=>b[1])];const mx=Math.max(...all)*1.06,mn=Math.min(...all,0)*0.9;
  const N=ser.hist.length+ser.fc.length;const X=i=>pl+(i/(N-1))*(W-pl-pr);const Y=v=>pt+(1-(v-mn)/(mx-mn))*(H-pt-pb);
  const svg=E('svg',{viewBox:`0 0 ${W} ${H}`,height:H});
  const grad=E('linearGradient',{id:id+'g',x1:0,y1:0,x2:0,y2:1});grad.appendChild(E('stop',{offset:0,'stop-color':'#0078D4','stop-opacity':.22}));grad.appendChild(E('stop',{offset:1,'stop-color':'#0078D4','stop-opacity':0}));svg.appendChild(grad);
  for(let g=0;g<=4;g++){const y=pt+g*(H-pt-pb)/4;svg.appendChild(E('line',{x1:pl,y1:y,x2:W-pr,y2:y,class:'grid-line'}));const t=E('text',{x:4,y:y+3,class:'axis'});t.textContent=fmt(mx-(g*(mx-mn)/4));svg.appendChild(t);}
  // band
  let bt='',bb='';ser.band.forEach((b,i)=>bt+=`${X(ser.hist.length+i)},${Y(b[1])} `);for(let i=ser.band.length-1;i>=0;i--)bb+=`${X(ser.hist.length+i)},${Y(ser.band[i][0])} `;
  svg.appendChild(E('polygon',{points:bt+bb,fill:'#e9def5',opacity:.75}));
  // actual area+line
  const ap=ser.hist.map((v,i)=>[X(i),Y(v)]);
  const area=smoothPath(ap)+` L ${X(ser.hist.length-1)},${H-pb} L ${pl},${H-pb} Z`;
  svg.appendChild(E('path',{d:area,fill:`url(#${id}g)`}));
  svg.appendChild(E('path',{d:smoothPath(ap),fill:'none',stroke:'#0078D4','stroke-width':2.2}));
  // forecast line (Copilot purple)
  const fp=[[X(ser.hist.length-1),Y(ser.hist[ser.hist.length-1])],...ser.fc.map((v,i)=>[X(ser.hist.length+i),Y(v)])];
  svg.appendChild(E('path',{d:smoothPath(fp),fill:'none',stroke:'#5C2D91','stroke-width':2.6,'stroke-dasharray':'6 4'}));
  const xd=X(ser.hist.length-1);svg.appendChild(E('line',{x1:xd,y1:pt,x2:xd,y2:H-pb,stroke:'#c3c9dc','stroke-dasharray':'3 3'}));
  const tl=E('text',{x:xd+3,y:pt+10,class:'axis'});tl.textContent='now';svg.appendChild(tl);
  [...ser.hist,...ser.fc].forEach((v,i)=>{const isF=i>=ser.hist.length;
    svg.appendChild(E('circle',{cx:X(i),cy:Y(v),r:2.3,fill:isF?'#5C2D91':'#0078D4'}));
    const c=E('circle',{cx:X(i),cy:Y(v),r:9,fill:'transparent'});c.style.cursor='crosshair';
    c.addEventListener('mousemove',e=>tip(e,`${isF?'Forecast':'Actual'} ${ser.labels[i]}`,[['Units',fmt(v)],isF?['Range',fmt(ser.band[i-ser.hist.length][0])+'–'+fmt(ser.band[i-ser.hist.length][1])]:['','']].filter(r=>r[0]),isF?T('unit(period) × seasonality × trigger adj','unit(periode) × seasonality × penyesuaian trigger'):T('actual sales history','histori penjualan aktual')));
    c.addEventListener('mouseleave',hideTip);svg.appendChild(c);});
  // x labels (sparse)
  const step=Math.ceil(N/9);for(let i=0;i<N;i+=step){const t=E('text',{x:X(i),y:H-pb+14,class:'axis','text-anchor':'middle'});t.textContent=ser.labels[i];svg.appendChild(t);}
  w.appendChild(svg);
}
function barChart(id,data,opt={}){
  const w=G(id);w.innerHTML='';const W=w.clientWidth||300,H=opt.h||210,pl=opt.pl||36,pr=10,pt=10,pb=opt.pb||46;
  const mx=Math.max(...data.map(d=>d.value))*1.14||1;const bw=(W-pl-pr)/data.length;const Y=v=>pt+(1-v/mx)*(H-pt-pb);
  const svg=E('svg',{viewBox:`0 0 ${W} ${H}`,height:H});
  for(let g=0;g<=3;g++){const y=pt+g*(H-pt-pb)/3;svg.appendChild(E('line',{x1:pl,y1:y,x2:W-pr,y2:y,class:'grid-line'}));const t=E('text',{x:4,y:y+3,class:'axis'});t.textContent=fmt(mx-(g*mx/3));svg.appendChild(t);}
  data.forEach((d,i)=>{const x=pl+i*bw+bw*0.16,bwid=bw*0.68,y=Y(d.value),h=H-pb-y;
    const rect=E('rect',{x,y,width:bwid,height:Math.max(1,h),rx:5,fill:d.color||'#0078D4'});
    if(d.onclick){rect.style.cursor='pointer';rect.addEventListener('click',d.onclick);}
    rect.addEventListener('mousemove',e=>tip(e,d.label,[['Units',fmt(d.value)],d.sub?['',d.sub]:['','']].filter(r=>r[0]||r[1]),d.fx));
    rect.addEventListener('mouseleave',hideTip);svg.appendChild(rect);
    const t=E('text',{x:x+bwid/2,y:H-pb+13,class:'axis','text-anchor':'end',transform:`rotate(-32 ${x+bwid/2} ${H-pb+13})`});t.textContent=d.label.length>13?d.label.slice(0,12)+'…':d.label;svg.appendChild(t);});
  w.appendChild(svg);
}
function hbarChart(id,data){
  const w=G(id);w.innerHTML='';const W=w.clientWidth||300,rh=27,H=data.length*rh+14,pl=112,pr=46;
  const mx=Math.max(...data.map(d=>d.value))*1.1||1;const svg=E('svg',{viewBox:`0 0 ${W} ${H}`,height:H});
  data.forEach((d,i)=>{const y=8+i*rh,wd=(d.value/mx)*(W-pl-pr);
    const lt=E('text',{x:pl-8,y:y+13,class:'axis','text-anchor':'end',fill:'#404a63'});lt.textContent=d.label;svg.appendChild(lt);
    const rect=E('rect',{x:pl,y:y+2,width:Math.max(2,wd),height:16,rx:5,fill:d.color||'#0a68b8'});
    if(d.onclick){rect.style.cursor='pointer';rect.addEventListener('click',d.onclick);}
    rect.addEventListener('mousemove',e=>tip(e,d.label,[['Forecast',fmt(d.value)]],d.fx));rect.addEventListener('mouseleave',hideTip);svg.appendChild(rect);
    const vt=E('text',{x:pl+wd+6,y:y+14,class:'axis',fill:'#1B2237'});vt.textContent=fmt(d.value);svg.appendChild(vt);});
  w.appendChild(svg);
}
function waterfall(id,items){ // items: {label,value,color, total?}
  const w=G(id);w.innerHTML='';const W=w.clientWidth||300,H=220,pl=36,pr=10,pt=12,pb=46;
  let cum=0;const tops=[];items.forEach(it=>{if(it.total){tops.push([0,it.value]);}else{tops.push([cum,cum+it.value]);cum+=it.value;}});
  const mx=Math.max(...tops.map(t=>t[1]))*1.12;const bw=(W-pl-pr)/items.length;const Y=v=>pt+(1-v/mx)*(H-pt-pb);
  const svg=E('svg',{viewBox:`0 0 ${W} ${H}`,height:H});
  for(let g=0;g<=3;g++){const y=pt+g*(H-pt-pb)/3;svg.appendChild(E('line',{x1:pl,y1:y,x2:W-pr,y2:y,class:'grid-line'}));}
  items.forEach((it,i)=>{const x=pl+i*bw+bw*0.18,bwid=bw*0.64,y0=Y(tops[i][1]),y1=Y(tops[i][0]);
    const rect=E('rect',{x,y:y0,width:bwid,height:Math.max(2,y1-y0),rx:4,fill:it.color});
    rect.addEventListener('mousemove',e=>tip(e,it.label,[['Contribution',fmt(it.value)]],T('driver contribution added to the forecast','kontribusi driver ke forecast')));rect.addEventListener('mouseleave',hideTip);svg.appendChild(rect);
    const t=E('text',{x:x+bwid/2,y:H-pb+13,class:'axis','text-anchor':'end',transform:`rotate(-30 ${x+bwid/2} ${H-pb+13})`});t.textContent=it.label;svg.appendChild(t);});
  w.appendChild(svg);
}
function heatmap(id,rows,cols,vals,onCell){
  const w=G(id);w.innerHTML='';const cw=Math.max(58,(w.clientWidth-140)/cols.length),rh=24,pl=138,pt=54;
  const W=pl+cols.length*cw+10,H=pt+rows.length*rh+6;const mx=Math.max(...vals.flat())||1;
  const svg=E('svg',{viewBox:`0 0 ${W} ${H}`,height:H,width:W});
  cols.forEach((c,j)=>{const t=E('text',{x:pl+j*cw+cw/2,y:pt-8,class:'axis','text-anchor':'end',transform:`rotate(-32 ${pl+j*cw+cw/2} ${pt-8})`});t.textContent=c.length>12?c.slice(0,11)+'…':c;svg.appendChild(t);});
  rows.forEach((rw,i)=>{const t=E('text',{x:pl-8,y:pt+i*rh+16,class:'axis','text-anchor':'end',fill:'#404a63'});t.textContent=rw.length>18?rw.slice(0,17)+'…':rw;svg.appendChild(t);
    cols.forEach((c,j)=>{const v=vals[i][j];const a=0.12+0.85*(v/mx);
      const rect=E('rect',{x:pl+j*cw+2,y:pt+i*rh+2,width:cw-4,height:rh-4,rx:4,fill:`rgba(0,120,212,${a.toFixed(2)})`,class:'heatcell'});
      rect.addEventListener('mousemove',e=>tip(e,rw,[[c,fmt(v)+' u']]));rect.addEventListener('mouseleave',hideTip);
      if(onCell){rect.addEventListener('click',()=>onCell(i,j));}
      svg.appendChild(rect);
      if(cw>52){const vt=E('text',{x:pl+j*cw+cw/2,y:pt+i*rh+16,class:'axis','text-anchor':'middle',fill:a>0.55?'#fff':'#404a63'});vt.textContent=fmt(v);svg.appendChild(vt);}});});
  w.appendChild(svg);
}
function multiLine(id,seriesArr,labels){
  const w=G(id);w.innerHTML='';if(!seriesArr.length){w.innerHTML='<div class="tiny muted" style="padding:20px;text-align:center">'+T('No scenarios saved yet. Save 2+ in What-If to compare.','Belum ada skenario. Simpan 2+ di What-If untuk membandingkan.')+'</div>';return;}
  const W=w.clientWidth||620,H=210,pl=40,pr=12,pt=12,pb=24;const all=seriesArr.flatMap(s=>s.data);const mx=Math.max(...all)*1.08,mn=Math.min(...all,0)*0.9;
  const N=labels.length,X=i=>pl+(i/(N-1))*(W-pl-pr),Y=v=>pt+(1-(v-mn)/(mx-mn))*(H-pt-pb);
  const svg=E('svg',{viewBox:`0 0 ${W} ${H}`,height:H});
  for(let g=0;g<=4;g++){const y=pt+g*(H-pt-pb)/4;svg.appendChild(E('line',{x1:pl,y1:y,x2:W-pr,y2:y,class:'grid-line'}));const t=E('text',{x:4,y:y+3,class:'axis'});t.textContent=fmt(mx-(g*(mx-mn)/4));svg.appendChild(t);}
  seriesArr.forEach(s=>{const pts=s.data.map((v,i)=>[X(i),Y(v)]);svg.appendChild(E('path',{d:smoothPath(pts),fill:'none',stroke:s.color,'stroke-width':2.3,'stroke-dasharray':s.dash||'1 0'}));
    s.data.forEach((v,i)=>{const c=E('circle',{cx:X(i),cy:Y(v),r:8,fill:'transparent'});c.addEventListener('mousemove',e=>tip(e,s.name+' · '+labels[i],[['Units',fmt(v)]]));c.addEventListener('mouseleave',hideTip);svg.appendChild(c);});});
  const step=Math.ceil(N/8);for(let i=0;i<N;i+=step){const t=E('text',{x:X(i),y:H-pb+14,class:'axis','text-anchor':'middle'});t.textContent=labels[i];svg.appendChild(t);}
  w.appendChild(svg);
}

/* ---------- render charts ---------- */
function renderForecast_INV(){
  const list=activeSKUs().map(invMetrics);
  const pos=list.reduce((a,m)=>a+m.position,0);
  const ads=Math.max(1,list.reduce((a,m)=>a+m.ads,0));
  const rop=list.reduce((a,m)=>a+m.rop,0);
  const inbound=list.reduce((a,m)=>a+m.openPOu,0);
  const avgLead=Math.round(activeSKUs().reduce((a,s)=>a+s.lead,0)/Math.max(1,activeSKUs().length));
  const days=Math.min(70,state.horizon*7);
  const r=rng(hashScope());const hist=[],fc=[],band=[],labels=[];
  let p=pos+ads*5;
  for(let i=42;i>0;i--){p-=ads*(0.6+r()*0.8);if(i%7===0)p+=ads*4;p=Math.max(ads,p);hist.push(Math.round(p));labels.push('D-'+i);}
  let q=pos,dts='>'+days+'d';
  for(let i=0;i<days;i++){q-=ads;if(i===avgLead)q+=inbound;if(q<rop&&dts.charAt(0)==='>'&&i>0)dts=i+'d';if(q<rop*0.35)q+=ads*7;q=Math.max(0,q);
    fc.push(Math.round(q));const g=Math.min(0.3,0.05+0.0038*i);band.push([Math.round(q*(1-g)),Math.round(q*(1+g))]);labels.push('D+'+(i+1));}
  lineChart('chart-forecast',{hist,fc,band,labels});
  G('forenote').textContent=T(`Projected on-hand depletion · restock at ROP · horizon ${state.horizon}wk · scope: ${scopeShort()}`,`Proyeksi penurunan on-hand · restock di ROP · horizon ${state.horizon}mgg · scope: ${scopeShort()}`);
  G('forecastStats').innerHTML=`<div class="m"><div class="k">${T('On-hand position','Posisi on-hand')}</div><b data-fx="invPosition">${fmt(pos)} u</b></div>
    <div class="m"><div class="k">${T('Avg Days of Supply','Rata DoS')}</div><b data-fx="dosBox">${(pos/ads).toFixed(1)} d</b></div>
    <div class="m"><div class="k">${T('Reorder Point','Reorder Point')}</div><b data-fx="ropBox">${fmt(rop)} u</b></div>
    <div class="m"><div class="k">${T('Days to stockout','Hari ke stockout')}</div><b data-fx="daysToStockout">${dts}</b></div>
    <div class="m"><div class="k">${T('Inbound (Open PO)','Inbound (Open PO)')}</div><b data-fx="inbound">${fmt(inbound)} u</b></div>`;}
function renderDriver_INV(){
  const list=activeSKUs().map(invMetrics);
  const stockoutVal=list.filter(m=>m.state==='Stockout'||m.state==='Low').reduce((a,m)=>a+m.value,0);
  const expiryVal=list.reduce((a,m)=>a+m.unitsExpiry*m.price,0);
  const overstockVal=list.reduce((a,m)=>a+m.excess,0);
  const slowVal=list.filter(m=>m.state==='Slow-mover').reduce((a,m)=>a+m.value,0);
  const total=stockoutVal+expiryVal+overstockVal+slowVal;
  waterfall('chart-driver',[
    {label:T('Stockout','Stockout'),value:stockoutVal,color:'#D13438'},
    {label:'Expiry',value:expiryVal,color:'#C77700'},
    {label:'Overstock',value:overstockVal,color:'#5C2D91'},
    {label:'Slow-mover',value:slowVal,color:'#0A9ED4'},
    {label:T('Total at-risk','Total berisiko'),value:total,color:'#D13438',total:true},
  ]);
}
function renderTrend_INV(){
  const fresh=activeSKUs().filter(s=>s.fresh).map(s=>({s,m:invMetrics(s)}));
  const pool=fresh.filter(x=>x.m.unitsExpiry>0).sort((a,b)=>a.s.expiry-b.s.expiry);
  const show=(pool.length?pool:fresh).slice(0,5);
  G('trendlist').innerHTML=show.map(x=>`<div class="trow"><span class="fireicon">⏰</span>
    <div><div class="tn">${x.s.name}</div><div class="tc">${x.s.cat} · ${x.s.expiry}d shelf-life · ${fmt(x.m.unitsExpiry)}u ${T('at risk','berisiko')}</div></div>
    <div class="tu down">${x.s.expiry}d</div></div>`).join('')||`<div class="tiny muted">${T('No fresh items in scope.','Tidak ada item fresh di scope.')}</div>`;
}
function renderCat_INV(){
  const data=CATS.map(c=>{let v=0;SKUS.filter(s=>s.catId===c.id).forEach(s=>v+=invMetrics(s).value);
    return {label:c.name,value:v,color:CCOLOR[c.id],sub:c.fresh?'Fresh':c.name,fx:'Σ Position × unit price for category',
      onclick:()=>{state.itemMode='cat';state.cats=new Set([c.id]);syncSegs();refreshAll();toast('🗂️ '+T('Filtered: ','Filter: ')+c.name);}};});
  barChart('chart-cat',data,{pb:52});
}
function storeRisk2(store){let so=0,lo=0;const list=activeSKUs();list.forEach(s=>{const seas=(s.fresh?SEAS_FRESH:SEAS_DRY)[MONTH];const ads=s.base*seas*store.size;const pos=(s.base*s.onHandDays*stockFactor(s)*store.size+s.openPO*(store.size/ALLSIZES))*store.health;const rop=ads*(s.lead+s.safety);if(pos<rop*0.6)so++;else if(pos<rop)lo++;});return {so,lo,tot:list.length};}
function renderStore_INV(){
  const rows=STORES.map(st=>{const r=storeRisk2(st);return {st,label:st.name.replace('HERO ',''),so:r.so,lo:r.lo,risk:r.so+r.lo,tot:r.tot};}).sort((a,b)=>b.risk-a.risk||b.so-a.so);
  const w=G('chart-store');
  w.innerHTML='<div class="tiny muted" style="display:flex;gap:14px;padding:2px 8px 8px"><span><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:#D13438;vertical-align:middle"></i> '+T('Stockout (Pos < 0.6×ROP)','Stockout (Pos < 0.6×ROP)')+'</span><span><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:#E8792B;vertical-align:middle"></i> '+T('Low (Pos < ROP)','Low (Pos < ROP)')+'</span></div>';
  const W=w.clientWidth||320,rh=30,H=rows.length*rh+14,pl=118,pr=70;const mx=Math.max(...rows.map(r=>r.risk),1)*1.14;const scale=(W-pl-pr)/mx;
  const svg=E('svg',{viewBox:`0 0 ${W} ${H}`,height:H});
  const hover=(r)=>e=>tip(e,r.st.name.replace('HERO ','')+' · '+r.st.cluster,[['Stockout',r.so],['Low',r.lo],['At-risk',r.risk+' / '+r.tot],['% of SKUs',((r.risk/r.tot)*100).toFixed(0)+'%'],['Supply health',(r.st.health*100).toFixed(0)+'%']],'health<1 = understocked → more risk');
  const click=(r)=>()=>{state.storeMode='sel';state.stores=new Set([r.st.id]);syncSegs();refreshAll();toast('🏪 '+T('Filtered: ','Filter: ')+r.st.name);};
  rows.forEach((r,i)=>{const y=8+i*rh;
    const lt=E('text',{x:pl-8,y:y+15,class:'axis','text-anchor':'end',fill:'#404a63'});lt.textContent=r.label;svg.appendChild(lt);
    const wso=r.so*scale,wlo=r.lo*scale;
    [[r.so,pl,'#D13438',wso],[r.lo,pl+wso,'#E8792B',wlo]].forEach(([v,x,col,wd])=>{if(v<=0)return;const rc=E('rect',{x,y:y+4,width:Math.max(1.5,wd),height:16,rx:3,fill:col});rc.style.cursor='pointer';rc.addEventListener('mousemove',hover(r));rc.addEventListener('mouseleave',hideTip);rc.addEventListener('click',click(r));svg.appendChild(rc);});
    const vt=E('text',{x:pl+wso+wlo+6,y:y+16,class:'axis',fill:'#1B2237'});vt.textContent=`${r.risk} (${r.so} SO)`;svg.appendChild(vt);
  });
  w.appendChild(svg);
}
function renderCluster_INV(){
  const cc={Premium:'#5C2D91','Urban Mall':'#0078D4',Suburban:'#008575',Resort:'#C77700'};
  const data=CLUSTERS.map(cl=>{const stores=STORES.filter(s=>s.cluster===cl);let v=0;
    activeSKUs().forEach(s=>{stores.forEach(store=>{const ads=s.base*(s.fresh?SEAS_FRESH:SEAS_DRY)[MONTH]*store.size;const pos=s.base*s.onHandDays*stockFactor(s)*store.size+s.openPO*(store.size/ALLSIZES);const maxL=ads*(s.lead+s.safety+4);v+=Math.max(0,pos-maxL)*s.price;});});
    return {label:cl,value:Math.round(v),color:cc[cl],fx:'Σ excess capital (Position−Max)×price in cluster',
      onclick:()=>{state.storeMode='sel';state.stores=new Set(STORES.filter(s=>s.cluster===cl).map(s=>s.id));syncSegs();refreshAll();toast('🧭 '+T('Cluster: ','Cluster: ')+cl);}};});
  barChart('chart-cluster',data,{pb:40});
}
function renderSeason_INV(){
  const buckets=[['≤1d',1],['2d',2],['3d',3],['4–5d',5],['6–7d',7],['>7d',999]];
  const vals=buckets.map(()=>0);
  activeSKUs().filter(s=>s.fresh).forEach(s=>{const m=invMetrics(s);let bi=buckets.findIndex(b=>s.expiry<=b[1]);if(bi<0)bi=buckets.length-1;vals[bi]+=(m.unitsExpiry||Math.round(m.position*0.12));});
  const cols=['#D13438','#E8792B','#C77700','#EAB308','#0A9ED4','#cfe0f3'];
  const data=buckets.map((b,i)=>({label:b[0],value:Math.round(vals[i]),color:cols[i],fx:'Σ fresh units in this days-to-expiry bucket'}));
  barChart('chart-season',data,{h:196,pb:26});
}
function miniBars(vals,color){const n=vals.length,w=Math.max(58,n*8),h=22,mx=Math.max(...vals)||1;
  return `<svg width="${w}" height="${h}">`+vals.map((v,i)=>{const bh=Math.max(1.5,(v/mx)*(h-2));return `<rect x="${(i*(w/n)+1).toFixed(1)}" y="${(h-bh).toFixed(1)}" width="${(w/n-2).toFixed(1)}" height="${bh.toFixed(1)}" rx="1.5" fill="${color}"/>`;}).join('')+`</svg>`;}
function rankState(st){return {Stockout:0,Low:1,Expiry:2,Overstock:3,'Slow-mover':4,Healthy:5}[st];}
function riskAction(st){return {Stockout:['Replenish now','Replenish sekarang'],Low:['Replenish','Replenish'],Expiry:['Markdown / transfer','Markdown / transfer'],Overstock:['Reduce PO / transfer','Kurangi PO / transfer'],'Slow-mover':['Markdown / delist','Markdown / delist'],Healthy:['—','—']}[st];}
function renderMatrix_INV(){
  const storeLbl=(state.storeMode==='sel'&&state.stores.size)?(state.stores.size===1?STORES.find(s=>state.stores.has(s.id)).name.replace('HERO ',''):state.stores.size+' stores'):T('All','Semua');
  const rows=activeSKUs().map(s=>({s,m:invMetrics(s)})).sort((a,b)=>rankState(a.m.state)-rankState(b.m.state)||a.m.dos-b.m.dos).slice(0,14);
  G('chart-matrix').innerHTML=`<table class="tbl"><thead><tr>
    <th>SKU</th><th>Item</th><th>Category</th><th>Store</th><th>On Hand</th><th>Reserved</th><th>Open PO</th><th>Days of Supply</th><th>ROP</th><th>Status</th><th>Expiry</th><th>${T('Action','Aksi')}</th></tr></thead><tbody>
    ${rows.map(({s,m})=>`<tr style="cursor:pointer" onclick="drillSku('${s.id}')">
      <td>${s.id}</td><td style="text-align:left">${s.name}</td>
      <td style="text-align:left"><span class="badge" style="background:${CCOLOR[s.catId]}22;color:${CCOLOR[s.catId]}">${s.cat}</span></td>
      <td style="text-align:left">${storeLbl}</td>
      <td data-fx="onhandU">${fmt(m.onHandU)}</td>
      <td data-fx="reserved">${fmt(m.reservedU)}</td>
      <td data-fx="openpoU">${fmt(m.openPOu)}</td>
      <td data-fx="dosBox"><b>${m.dos.toFixed(1)}d</b></td>
      <td data-fx="ropBox">${fmt(m.rop)}</td>
      <td><span class="badge" style="background:${STATECOL[m.state]}22;color:${STATECOL[m.state]}">${m.state}</span></td>
      <td data-fx="expiryCell">${m.expiryDays?m.expiryDays+'d':'—'}</td>
      <td style="text-align:left">${T(riskAction(m.state)[0],riskAction(m.state)[1])}</td></tr>`).join('')}
  </tbody></table>`;
}
function drillSku(id){state.itemMode='item';state.skus=new Set([id]);syncSegs();refreshAll();toast('🔎 '+(SKUS.find(s=>s.id===id)||{}).name);}
function renderCompare(){
  const daily=genDaily();const labels=daily.fcLabels.slice(0,14);
  const arr=[{name:'BASE',color:'#94a3c8',dash:'4 3',data:daily.fc.slice(0,14)}];
  const pal=['#0078D4','#5C2D91','#107C41','#C77700','#008575'];
  scenarios.forEach((s,i)=>arr.push({name:s.name,color:pal[i%pal.length],data:s.series}));
  multiLine('chart-compare',scenarios.length?arr:[],labels);
  G('comparehint').textContent=scenarios.length?T(scenarios.length+' scenario(s) vs base','vs base'):T('save 2+ scenarios to overlay','simpan 2+ skenario');
  renderScenTable();
}

/* ---------- what-if ---------- */
function onHorizon(){state.horizon=+G('horizon').value;G('horizonv').textContent=state.horizon+' wk';renderForecast();renderMatrix();}
function onSim(){const s=state.sim;s.price=+G('s-price').value;s.promo=+G('s-promo').value;s.seas=+G('s-seas').value;s.viral=+G('s-viral').value;s.lead=+G('s-lead').value;s.safe=+G('s-safe').value;
  G('v-price').textContent=s.price+'%';G('v-promo').textContent=s.promo+'%';G('v-seas').textContent=s.seas+'%';G('v-viral').textContent=s.viral+'%';G('v-lead').textContent=s.lead+' d';G('v-safe').textContent=s.safe+' d';runSim();}
function runSim_INV(){
  const dem=1+state.sim.price/100, markdown=state.sim.promo/100, inboundBoost=1+state.sim.seas/100, transferOut=state.sim.viral/100;
  const list=activeSKUs().map(invMetrics);
  let stockoutAfter=0, expiryAfter=0, capital=0;
  list.forEach(m=>{
    const pos=m.position*inboundBoost*(1-transferOut*(m.state==='Overstock'?0.6:0.1));
    const coverDays=pos/Math.max(1,m.ads*dem)+(state.sim.safe-2)*0.6;
    if(coverDays<state.sim.lead) stockoutAfter++;
    let exp=m.unitsExpiry*(1-Math.min(0.9,markdown*1.6));
    if(m.expiryDays){const fd=pos/Math.max(1,m.ads*dem);if(fd>m.expiryDays)exp=Math.max(exp,pos-m.ads*dem*m.expiryDays);}
    expiryAfter+=Math.max(0,exp);capital+=pos*m.price;
  });
  const pos0=list.reduce((a,m)=>a+m.position,0)*inboundBoost;
  const ads0=Math.max(1,list.reduce((a,m)=>a+m.ads,0)*dem);
  const rop0=list.reduce((a,m)=>a+m.rop,0)*dem;
  const inbound=list.reduce((a,m)=>a+m.openPOu,0)*inboundBoost;
  const hist=[],fc=[],band=[],labels=[];let p=pos0+ads0*4;
  for(let i=14;i>0;i--){p-=ads0*0.7;if(i%7===0)p+=ads0*4;p=Math.max(ads0,p);hist.push(Math.round(p));labels.push('D-'+i);}
  let q=pos0;for(let i=0;i<14;i++){q-=ads0;if(i===3)q+=inbound;if(q<rop0*0.35)q+=ads0*7;q=Math.max(0,q);fc.push(Math.round(q));const g=Math.min(0.3,0.05+0.01*i);band.push([Math.round(q*(1-g)),Math.round(q*(1+g))]);labels.push('D+'+(i+1));}
  lineChart('chart-sim',{hist,fc,band,labels},{h:180});
  const baseK=computeK();
  const dExpiry=baseK.expiryUnits>0?((expiryAfter/baseK.expiryUnits)-1)*100:0;
  const dCapital=baseK.invValue>0?((capital/baseK.invValue)-1)*100:0;
  const svc=Math.min(99,90+state.sim.safe*1.4-state.sim.lead*0.6+state.sim.seas*0.1);
  simRun={order:stockoutAfter,dDem:dExpiry,dMgn:dCapital,svc,series:fc};
  G('sim-order').textContent=fmt(stockoutAfter)+' SKU';
  const dd=G('sim-delta');dd.textContent=pct(dExpiry);dd.className=dExpiry<=0?'up':'down';
  const dm=G('sim-margin');dm.textContent=pct(dCapital);dm.className=dCapital<=0?'up':'down';G('sim-svc').textContent=svc.toFixed(1)+'%';
}
function saveScenario(){if(!simRun)runSim();const n=scenarios.length+1;
  scenarios.push({name:'S'+n,price:state.sim.price,promo:state.sim.promo,seas:state.sim.seas,viral:state.sim.viral,lead:state.sim.lead,safe:state.sim.safe,order:simRun.order,dDem:simRun.dDem,dMgn:simRun.dMgn,svc:simRun.svc,series:simRun.series});
  renderCompare();toast('💾 '+T('Scenario saved · ','Skenario disimpan · ')+scenarios.length+' total');}
function renderScenTable(){const w=G('scentablewrap');if(!scenarios.length){w.innerHTML='';return;}
  const L=LABELS[state.agent];const good=v=>L.scenDir==='lower'?v<=0:v>=0;
  const baseFirst=state.agent==='inv'?fmt(computeK().stockout)+' SKU':fmt(genDaily().fc.slice(0,5).reduce((a,b)=>a+b,0));
  w.innerHTML=`<table class="tbl" style="margin-top:10px"><thead><tr><th>${T('Scenario','Skenario')}</th><th>${L.scenC1}</th><th>${L.scenC2}</th><th>Lead</th><th>${L.scen[0]}</th><th>${L.scen[1]}</th><th>${L.scen[2]}</th><th>Svc</th><th></th></tr></thead><tbody>
    <tr><td><span class="badge base">BASE</span></td><td>0%</td><td>0%</td><td>3d</td><td data-fx="${L.metrics[0][2]}">${baseFirst}</td><td>—</td><td>—</td><td>—</td><td></td></tr>
    ${scenarios.map((s,i)=>`<tr><td><span class="badge new">${s.name}</span></td><td>${s.price}%</td><td>${s.promo}%</td><td>${s.lead}d</td><td data-fx="${L.metrics[0][2]}">${fmt(s.order)}${L.unit}</td><td data-fx="${L.metrics[1][2]}" class="${good(s.dDem)?'up':'down'}">${pct(s.dDem)}</td><td data-fx="${L.metrics[2][2]}" class="${good(s.dMgn)?'up':'down'}">${pct(s.dMgn)}</td><td data-fx="${L.metrics[3][2]}">${s.svc.toFixed(0)}%</td><td><button class="btn ghost sm" onclick="delScen(${i})">✕</button></td></tr>`).join('')}
  </tbody></table>`;}
function delScen(i){scenarios.splice(i,1);renderCompare();}
function loadScenario(){if(!scenarios.length){toast(T('No saved scenarios','Belum ada skenario'));return;}const s=scenarios[scenarios.length-1];
  G('s-price').value=s.price;G('s-promo').value=s.promo;G('s-seas').value=s.seas;G('s-viral').value=s.viral;G('s-lead').value=s.lead;G('s-safe').value=s.safe;onSim();toast('📂 '+T('Loaded ','Muat ')+s.name);}
function exportScenarios(){if(!scenarios.length){toast(T('Save a scenario first','Simpan skenario dulu'));return;}
  const h=['Scenario','Price%','Promo%','Seas%','Viral%','Lead','Safety','Order','dDemand%','dMargin%','Service%'];
  downloadCSV('AI360_Scenarios.csv',[h,...scenarios.map(s=>[s.name,s.price,s.promo,s.seas,s.viral,s.lead,s.safe,s.order,s.dDem.toFixed(1),s.dMgn.toFixed(1),s.svc.toFixed(1)])]);toast('⬇ '+T('Exported','Diekspor'));}
function downloadCSV(fn,rows){const csv='\ufeff'+rows.map(r=>r.map(c=>`"${String(c).replace(/"/g,'""')}"`).join(',')).join('\r\n');
  const b=new Blob([csv],{type:'text/csv;charset=utf-8;'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=fn;a.click();}

/* ---------- Best Action + PO ---------- */
function renderAction_INV(){
  const k=computeK();
  const stTag={pending:'st-pending',approved:'st-approved',rejected:'st-rejected',cancelled:'st-cancelled',reopened:'st-reopened',sent:'st-sent'}[actionState];
  const stTxt={pending:T('Pending','Menunggu'),approved:'Approved',rejected:'Rejected',cancelled:T('Cancelled','Dibatalkan'),reopened:'Reopened',sent:T('Sent →','Terkirim →')}[actionState];
  const transferU=Math.round(k.list.filter(m=>m.state==='Overstock').reduce((a,m)=>a+Math.max(0,m.position-m.maxLevel),0));
  G('actionbody').innerHTML=`
    <div class="action-card"><div class="ah"><span class="pri high">${T('HIGH PRIORITY','PRIORITAS TINGGI')}</span>
      <b>${T('Rebalance stock & clear expiry risk','Rebalance stok & bereskan risiko expiry')}</b><span class="status-tag ${stTag}">${stTxt}</span></div>
      <div class="tiny muted">${T('Agent detected','Agent mendeteksi')} <b style="color:#D13438">${k.stockout} ${T('stockout','stockout')}</b>, <b style="color:#5C2D91">${k.overstock} ${T('overstock','overstock')}</b>, <b style="color:#C77700">${fmt(k.expiryUnits)}u ${T('expiry','expiry')}</b> ${T('in scope.','di scope.')}</div>
      <div class="impact">
        <div><span class="muted tiny">${T('Transfer units','Unit transfer')}</span><b data-fx="transferU">${fmt(transferU)} u</b></div>
        <div><span class="muted tiny">${T('Expiry to clear','Expiry dibereskan')}</span><b class="down" data-fx="expirySave">${fmt(k.expiryUnits)} u</b></div>
        <div><span class="muted tiny">${T('Capital to free','Modal dibebaskan')}</span><b data-fx="capitalFree">Rp ${fmt(k.overstockVal)}</b></div>
        <div><span class="muted tiny">Service</span><b data-fx="svcAction">${(94+state.sim.safe*0.7).toFixed(1)}%</b></div></div>
      <div class="agentic-row">
        <button class="abtn approve" onclick="agentic('approved')">✔ ${T('Approve','Setujui')}</button>
        <button class="abtn reject" onclick="agentic('rejected')">✕ ${T('Reject','Tolak')}</button>
        <button class="abtn cancel" onclick="agentic('cancelled')">⊘ ${T('Cancel','Batal')}</button>
        <button class="abtn reopen" onclick="agentic('reopened')">↻ ${T('Reopen','Buka lagi')}</button>
        <button class="btn indigo sm" style="margin-left:auto" onclick="togglePO()">📦 ${T('Generate PO (by route)','Buat PO (per rute)')}</button></div></div>
    <div id="po-preview"></div>`;
}
let poOpen=false;
const PO_ROUTE={
  direct:{title:['PO Direct Store','PO Direct Store'],sub:['Vendor → Store · Fresh (short shelf-life, fast)','Vendor → Store · Fresh (shelf-life pendek, cepat)'],dc:false,handle:0},
  flow:{title:['PO DC Flow-Through','PO DC Flow-Through'],sub:['Vendor → DC (flow-through, no storage) → Store','Vendor → DC (flow-through, tanpa simpan) → Store'],dc:true,handle:1},
  cross:{title:['PO Cross-Docking','PO Cross-Docking'],sub:['Vendor → DC (cross-dock, consolidate) → Store','Vendor → DC (cross-dock, konsolidasi) → Store'],dc:true,handle:2}
};
function poClassify(s){ if(s.fresh) return 'direct'; return (s.catId==='BEV'||s.catId==='HOU')?'flow':'cross'; }
function buildPOgroups(){
  const store=activeStores()[0];
  const need=activeSKUs().map(s=>({s,m:invMetrics(s)})).filter(x=>x.m.state==='Stockout'||x.m.state==='Low');
  const g={direct:[],flow:[],cross:[]};
  need.forEach(({s,m})=>{const k=poClassify(s);const qty=Math.max(0,m.maxLevel-m.position);
    const eta=new Date(Date.now()+(s.lead+PO_ROUTE[k].handle)*864e5).toLocaleDateString('en-GB',{day:'2-digit',month:'short'});
    const src=PO_ROUTE[k].dc?(s.dc+(k==='cross'?' · X-dock':' · flow')):s.vendor;
    g[k].push({sku:s.id,name:s.name,cat:s.cat,store:store.name.replace('HERO ',''),qty,onhand:m.onHandU,openpo:m.openPOu,pos:m.position,rop:m.rop,eta,src,fresh:s.fresh});});
  return g;
}
function poTableFor(k){const L=PO_ROUTE[k];const rows=(window.__POG&&window.__POG[k])||[];
  return `<div class="tiny muted" style="margin:6px 2px 9px">${T(L.sub[0],L.sub[1])} · ${T('shows Expected Delivery, On Hand, Source '+(L.dc?'DC':'Vendor'),'menampilkan Expected Delivery, On Hand, Sumber '+(L.dc?'DC':'Vendor'))}</div>
    <div style="overflow:auto;border:1px solid var(--line);border-radius:11px"><table class="tbl"><thead><tr>
      <th>SKU</th><th>Item</th><th>Category</th><th>Store</th><th>Order Qty</th><th>On Hand</th><th>Open PO</th><th>Position</th><th>ROP</th><th>Exp. Delivery</th><th>${L.dc?'Source DC':'Source Vendor'}</th></tr></thead>
      <tbody>${rows.length?rows.map(r=>`<tr><td>${r.sku}</td><td style="text-align:left">${r.name}</td><td style="text-align:left"><span class="badge" style="background:${CCOLOR[r.sku.split('-')[0]]}22;color:${CCOLOR[r.sku.split('-')[0]]}">${r.cat}</span></td>
        <td style="text-align:left">${r.store}</td><td data-fx="actQty"><b>${fmt(r.qty)}</b></td><td data-fx="onhandU">${fmt(r.onhand)}</td><td data-fx="openpoU">${fmt(r.openpo)}</td>
        <td data-fx="position" class="${r.pos<r.rop?'pos-low':'pos-ok'}">${fmt(r.pos)}</td><td data-fx="ropBox">${fmt(r.rop)}</td><td>${r.eta}</td><td style="text-align:left">${r.src}</td></tr>`).join(''):`<tr><td colspan="11" style="text-align:center;color:var(--muted);padding:14px">${T('No PO on this route for current scope.','Tidak ada PO rute ini untuk scope saat ini.')}</td></tr>`}</tbody></table></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:9px">
      <button class="btn teal sm" onclick="releaseOrHandoff('${rows.length+' '+T('line(s)','baris')+' · '+T(L.title[0],L.title[1])}')">➤ ${T((HANDOFF[state.agent]||HANDOFF.df).to[0],(HANDOFF[state.agent]||HANDOFF.df).to[1])}</button>
      <button class="btn sm" onclick="exportPOgrp('${k}')">⬇ ${T('Export to Excel','Export ke Excel')}</button></div>`;
}
function togglePO_INV(){poOpen=!poOpen;const w=G('po-preview');if(!poOpen){w.innerHTML='';return;}
  window.__POG=buildPOgroups();const g=window.__POG;
  const tab=(k,active)=>`<button class="${active?'active':''}" onclick="poTab('${k}',this)">${T(PO_ROUTE[k].title[0],PO_ROUTE[k].title[1])}${k==='direct'?' · Fresh':''} <span class="tabc">${g[k].length}</span></button>`;
  w.innerHTML=`<div class="tiny muted" style="margin:2px 0 8px">${T('Agentic PO generation, split by fulfilment route. Only stockout/low SKUs are ordered.','Generasi PO agentik, dipecah per rute pemenuhan. Hanya SKU stockout/low yang diorder.')}</div>
    <div class="po-routebar">${tab('direct',true)}${tab('flow',false)}${tab('cross',false)}</div>
    <div id="po-tabbody">${poTableFor('direct')}</div>`;
}
function poTab(k,btn){document.querySelectorAll('.po-routebar button').forEach(b=>b.classList.remove('active'));btn.classList.add('active');G('po-tabbody').innerHTML=poTableFor(k);}
function exportPOgrp(k){const rows=(window.__POG&&window.__POG[k])||[];const h=['SKU','Item','Category','Store','Order Qty','On Hand','Open PO','Position','ROP','Expected Delivery','Source'];
  downloadCSV('AI360_'+PO_ROUTE[k].title[0].replace(/[^a-z0-9]/gi,'_')+'.csv',[[PO_ROUTE[k].title[0]],h,...rows.map(r=>[r.sku,r.name,r.cat,r.store,r.qty,r.onhand,r.openpo,r.pos,r.rop,r.eta,r.src])]);toast('⬇ '+T('Exported','Diekspor')+' · '+PO_ROUTE[k].title[0]);}
function exportPO_INV(rows){exportPOgrp('direct');}
function agentic(st){const ag=(LABELS[state.agent]||LABELS.df).name[0];actionState=st;actionLog.unshift({time:new Date().toLocaleString('en-GB'),action:({approved:T('Approved: ','Disetujui: '),rejected:T('Rejected: ','Ditolak: '),cancelled:T('Cancelled: ','Dibatalkan: '),reopened:T('Reopened: ','Dibuka lagi: ')}[st])+ag,st});renderAction();toast(({approved:'✔ ',rejected:'✕ ',cancelled:'⊘ ',reopened:'↻ '}[st])+T('Action ','Aksi ')+st);}
function sendHandoff(payload){const hf=HANDOFF[state.agent]||HANDOFF.df;const from=(LABELS[state.agent]||LABELS.df).name[0];
  if(actionState==='rejected'||actionState==='cancelled'){toast('⚠ '+T('Approve the plan before handing off','Setujui rencana dulu sebelum estafet'));return;}
  const label=T(hf.to[0],hf.to[1]);const desc=from+' → '+label+(payload?(' · '+payload):'');
  actionLog.unshift({time:new Date().toLocaleString('en-GB'),action:desc,st:'sent'});
  actionState='sent';                                  // card now shows a persistent "Sent →" status
  (hf.rx||[]).forEach(k=>received[k]=true);             // badge the receiving agent(s) in the rail
  renderAction();renderAgentNav();
  toast('➤ '+label+(payload?(' · '+payload):'')+' · '+T('logged to Agent Status & History','tercatat di Agent Status & History'));
  openHistory();}
/* Any agent that commits to D365 F&O (Replenishment PO, Assortment change) routes through an approval workflow (SoD + signing/approval limits), not a direct release */
const D365_FLOWS={
 rep:{badge:'PurchTable',valLabel:['PO value','Nilai PO'],limitLabel:['signing limit','limit approval'],requester:['Replenishment Planner (AI)','Planner Replenishment (AI)'],
   title:['Purchase Order — approval workflow','Purchase Order — workflow approval'],
   policy:['Per D365 F&O purchasing policy, the PO is routed for approval by signing limit before release. Segregation of Duties: the requester cannot approve their own PO.','Sesuai kebijakan purchasing D365 F&O, PO dirutekan untuk approval berdasarkan signing limit sebelum rilis. Segregation of Duties: pembuat PO tidak boleh menyetujui PO-nya sendiri.'],
   value:()=>computeK().orderValue||0,
   tiers:[{role:['Purchasing Manager','Manajer Purchasing'],name:'Andi Wijaya',limit:100e6},{role:['Category / Procurement Director','Direktur Kategori / Procurement'],name:'Sri Lestari',limit:500e6},{role:['Chief Financial Officer (CFO)','CFO'],name:'Michael Tan',limit:Infinity}],
   confirm:['Confirm & post to D365 F&O (PurchTable)','Confirm & posting ke D365 F&O (PurchTable)'],
   submitMsg:['Submitted PO to D365 F&O approval workflow — pending approval','Submit PO ke workflow approval D365 F&O — menunggu approval'],
   confirmMsg:['PO confirmed & released to D365 F&O (PurchTable)','PO dikonfirmasi & dirilis ke D365 F&O (PurchTable)'],
   confirmedNote:['PO confirmed and released to D365 F&O.','PO dikonfirmasi dan dirilis ke D365 F&O.']},
 assort:{badge:'Released products',valLabel:['Annual margin impact','Dampak margin tahunan'],limitLabel:['approval limit','limit approval'],requester:['Assortment Planner (AI)','Planner Assortment (AI)'],
   title:['Assortment change — approval workflow','Perubahan assortment — workflow approval'],
   policy:['Per merchandising policy, assortment changes (delist / grow) are published to D365 F&O only after approval by margin-impact authority. Segregation of Duties: the planner cannot approve their own assortment change.','Sesuai kebijakan merchandising, perubahan assortment (delist / grow) dipublikasikan ke D365 F&O hanya setelah approval berdasarkan otoritas dampak margin. Segregation of Duties: planner tidak boleh menyetujui perubahannya sendiri.'],
   value:()=>computeK().marginImpact||0,
   tiers:[{role:['Category Manager','Manajer Kategori'],name:'Dewi Anggraini',limit:150e6},{role:['Merchandising Director','Direktur Merchandising'],name:'Rangga Pratama',limit:1500e6},{role:['Chief Financial Officer (CFO)','CFO'],name:'Michael Tan',limit:Infinity}],
   confirm:['Confirm & publish to D365 F&O (Released products)','Confirm & publish ke D365 F&O (Released products)'],
   submitMsg:['Submitted assortment change to D365 F&O approval — pending approval','Submit perubahan assortment ke approval D365 F&O — menunggu approval'],
   confirmMsg:['Assortment change confirmed & published to D365 F&O','Perubahan assortment dikonfirmasi & dipublikasikan ke D365 F&O'],
   confirmedNote:['Assortment changes published to D365 F&O.','Perubahan assortment dipublikasikan ke D365 F&O.']}
};
function releaseOrHandoff(payload){ return D365_FLOWS[state.agent]?submitD365Workflow(payload):sendHandoff(payload); }
function submitD365Workflow(payload){
  const F=D365_FLOWS[state.agent];if(!F)return sendHandoff(payload);
  const total=F.value()||0;
  const steps=[];for(const t of F.tiers){steps.push({role:t.role,name:t.name,limit:t.limit});if(total<=t.limit)break;}
  poWF={flow:state.agent,total,steps,idx:0,payload,rejected:false,confirmed:false,ts:new Date().toLocaleString('en-GB')};
  actionState='pending';
  actionLog.unshift({time:poWF.ts,action:T(F.submitMsg[0],F.submitMsg[1])+' · Rp '+fmt(total),st:'pending'});
  renderAction();renderWF();showOverlay();G('modal-wf').classList.add('show');
  toast('🧾 '+T('Submitted to D365 approval workflow','Disubmit ke workflow approval D365'));
}
function wfStatus(){const wf=poWF;if(!wf)return['','',''];const F=D365_FLOWS[wf.flow]||D365_FLOWS.rep;if(wf.rejected)return[T('Rejected / change requested','Ditolak / minta perubahan'),'st-rejected','✕'];if(wf.confirmed)return[T('Confirmed → posted to '+F.badge,'Confirmed → diposting ke '+F.badge),'st-sent','✓'];if(wf.idx>=wf.steps.length)return[T('Approved → ready to confirm','Approved → siap confirm'),'st-approved','✓'];return[T('In review · Pending approval','In review · Menunggu approval'),'st-pending','⏳'];}
function renderWF(){
  const wf=poWF;if(!wf)return;const F=D365_FLOWS[wf.flow]||D365_FLOWS.rep;const [stTxt,stCls]=wfStatus();const done=wf.idx>=wf.steps.length;
  const ladder=wf.steps.map((s,i)=>{
    const cls=wf.rejected&&i===wf.idx?'no':i<wf.idx?'ok':i===wf.idx&&!done&&!wf.confirmed?'cur':'';
    const icon=wf.rejected&&i===wf.idx?'✕':i<wf.idx?'✓':(i+1);
    const stateTxt=wf.rejected&&i===wf.idx?T('Rejected','Ditolak'):i<wf.idx?T('Approved','Disetujui'):i===wf.idx&&!wf.confirmed?T('Pending','Menunggu'):T('Waiting','Antre');
    const limTxt=s.limit===Infinity?T('no upper limit','tanpa batas atas'):'≤ Rp '+fmt(s.limit);
    return `<div class="wf-step ${cls}"><div class="wf-ic">${icon}</div><div style="flex:1"><div class="role">${T(s.role[0],s.role[1])}</div><div class="sub">${s.name} · ${T(F.limitLabel[0],F.limitLabel[1])} ${limTxt}</div></div><span class="status-tag ${cls==='ok'?'st-approved':cls==='no'?'st-rejected':cls==='cur'?'st-pending':'st-cancelled'}">${stateTxt}</span></div>${i<wf.steps.length-1?'<div class="wf-conn"></div>':''}`;
  }).join('');
  const acting=!wf.rejected&&!wf.confirmed&&!done?wf.steps[wf.idx]:null;
  G('wf-body').innerHTML=`
    <div class="tiny muted" style="margin-bottom:10px">${T(F.policy[0],F.policy[1])}</div>
    <div class="action-card" style="border-left-color:#C77700;background:linear-gradient(100deg,#fff7ec,#eef2fb)">
      <div class="ah"><span class="pri high" style="background:#C77700">D365 F&O</span><b>${T(F.title[0],F.title[1])}</b><span class="status-tag ${stCls}" style="margin-left:auto">${stTxt}</span></div>
      <div class="impact">
        <div><span class="muted tiny">${T(F.valLabel[0],F.valLabel[1])}</span><b>Rp ${fmt(wf.total)}</b></div>
        <div><span class="muted tiny">${T('Requested by','Diminta oleh')}</span><b style="font-size:12px">${T(F.requester[0],F.requester[1])}</b></div>
        <div><span class="muted tiny">${T('Approval steps','Langkah approval')}</span><b>${wf.steps.length}</b></div>
        <div><span class="muted tiny">${T('Submitted','Disubmit')}</span><b style="font-size:12px">${wf.ts}</b></div></div>
    </div>
    <div style="margin:6px 2px 8px;font-weight:600;font-size:12px">${T('Approval hierarchy','Hierarki approval')} · SoA</div>
    ${ladder}
    <div class="agentic-row" style="margin-top:12px">
      ${acting?`<div class="tiny muted" style="width:100%;margin-bottom:4px">${T('Acting approver','Approver saat ini')}: <b style="color:var(--ink)">${acting.name}</b> · ${T(acting.role[0],acting.role[1])}</div>
      <button class="abtn approve" onclick="wfApprove()">✔ ${T('Approve','Setujui')}</button>
      <button class="abtn reject" onclick="wfReject()">✕ ${T('Reject / request change','Tolak / minta ubah')}</button>`:''}
      ${done&&!wf.confirmed&&!wf.rejected?`<button class="abtn approve" onclick="wfConfirm()" style="background:#008575;color:#fff;border-color:#008575">📮 ${T(F.confirm[0],F.confirm[1])}</button>`:''}
      ${wf.confirmed?`<div class="tiny" style="color:#008575;font-weight:600">✓ ${T(F.confirmedNote[0],F.confirmedNote[1])}</div>`:''}
      ${wf.rejected?`<button class="abtn reopen" onclick="submitD365Workflow(poWF.payload)">↻ ${T('Resubmit','Submit ulang')}</button>`:''}
    </div>`;
}
function wfApprove(){const wf=poWF;if(!wf||wf.rejected||wf.confirmed)return;const s=wf.steps[wf.idx];
  actionLog.unshift({time:new Date().toLocaleString('en-GB'),action:T('Approved by ','Disetujui oleh ')+s.name+' · '+T(s.role[0],s.role[1]),st:'approved'});
  wf.idx++;const done=wf.idx>=wf.steps.length;if(done)actionState='approved';renderAction();renderWF();
  toast('✔ '+T('Approved by ','Disetujui oleh ')+s.name);}
function wfReject(){const wf=poWF;if(!wf)return;const s=wf.steps[wf.idx];wf.rejected=true;actionState='rejected';
  actionLog.unshift({time:new Date().toLocaleString('en-GB'),action:T('Rejected by ','Ditolak oleh ')+s.name+' · '+T(s.role[0],s.role[1]),st:'rejected'});
  renderAction();renderWF();toast('✕ '+T('Rejected by ','Ditolak oleh ')+s.name);}
function wfConfirm(){const wf=poWF;if(!wf||wf.rejected)return;const F=D365_FLOWS[wf.flow]||D365_FLOWS.rep;wf.confirmed=true;actionState='sent';
  actionLog.unshift({time:new Date().toLocaleString('en-GB'),action:T(F.confirmMsg[0],F.confirmMsg[1])+(wf.payload?(' · '+wf.payload):''),st:'sent'});
  renderAction();renderWF();toast('📮 '+T('Released to D365 F&O','Dirilis ke D365 F&O'));}

/* ---------- tooltip / formula ---------- */
const tipEl=G('tip'),popEl=G('pop');
function tip(e,title,rows,fxText){tipEl.innerHTML=`<div class="th">${title}</div>`+rows.map(r=>`<div class="row"><span>${r[0]}</span><b>${r[1]}</b></div>`).join('')+(fxText?`<div style="margin-top:5px;border-top:1px solid var(--line);padding-top:5px;font-family:ui-monospace,Menlo,monospace;font-size:10px;color:#0a746b">&fnof; ${fxText}</div>`:'');tipEl.style.opacity=1;place(tipEl,e);}
function hideTip(){tipEl.style.opacity=0;}
function place(box,e){let x=e.clientX+14,y=e.clientY+14;const r=box.getBoundingClientRect();if(x+r.width>innerWidth)x=e.clientX-r.width-14;if(y+r.height>innerHeight)y=e.clientY-r.height-14;box.style.left=x+'px';box.style.top=y+'px';}
let popTimer;
function showFormula(e,def,k){clearTimeout(popTimer);const val=def.val?def.val(k):'';
  popEl.innerHTML=`<div class="pt">🔍 ${T('Explain this calculation','Jelaskan kalkulasi ini')}</div>
    <div style="font-weight:600;font-size:12px">${T(def.lab[0],def.lab[1])}</div>
    <div class="formula">${def.f}</div><div class="expl">${T(def.e[0],def.e[1])}</div>
    <div class="nums">${T('Current value','Nilai saat ini')}: <b>${typeof val==='number'?fmt(val):val}</b> · ${T('scope','scope')}: ${scopeShort()}</div>
    <div class="plink" onclick="explainInChat('${T(def.lab[0],def.lab[1])}')">💬 ${T('Explain in chat','Jelaskan di chat')} →</div>`;
  popEl.classList.add('show');place(popEl,e);}
function hideFormula(){popTimer=setTimeout(()=>popEl.classList.remove('show'),260);}
popEl.addEventListener('mouseenter',()=>clearTimeout(popTimer));popEl.addEventListener('mouseleave',()=>popEl.classList.remove('show'));

/* ---------- universal number-hover formula registry ---------- */
const FX={
 sigmaHorizon:{t:['Σ over horizon','Σ sepanjang horizon'],f:'Σ forecast(period) for every period in the horizon',e:['Total predicted demand across the whole horizon window.','Total demand prediksi sepanjang jendela horizon.']},
 avgPeriod:{t:['Average per period','Rata-rata per periode'],f:'Σ over horizon ÷ number of periods',e:['Mean demand per period in the current Sales View.','Rata-rata demand per periode pada Tampilan terpilih.']},
 peak:{t:['Peak period','Periode puncak'],f:'max( forecast over horizon )',e:['Highest single-period demand — size capacity for this.','Demand tertinggi satu periode — siapkan kapasitas untuk ini.']},
 confidence:{t:['Confidence interval','Interval kepercayaan'],f:'± min(30%, 5% + 0.38% × period index)',e:['Uncertainty band; widens further into the future.','Rentang ketidakpastian; makin jauh makin lebar.']},
 periods:{t:['Periods ahead','Periode ke depan'],f:'horizon(weeks) → current view unit',e:['How many periods the forecast covers in the Sales View.','Jumlah periode forecast pada Tampilan Penjualan.']},
 fads:{t:['Forecast ADS','Forecast ADS'],f:'Base ADS × Seasonality × Driver multipliers',e:['Predicted average daily sales for this SKU & scope.','Prediksi rata-rata penjualan harian untuk SKU & scope ini.']},
 horizonUnits:{t:['Horizon units','Unit horizon'],f:'Σ ( Forecast ADS × 7 ) over H weeks',e:['Total predicted units over the horizon for this SKU.','Total unit prediksi sepanjang horizon untuk SKU ini.']},
 conf:{t:['Confidence','Interval'],f:'± ( 8% + 1.1% × horizon weeks )',e:['Confidence band for this SKU; grows with horizon.','Interval untuk SKU ini; melebar seiring horizon.']},
 drivers:{t:['Driver multiplier','Multiplier driver'],f:'Seasonality × Viral × Promo factors',e:['Combined uplift applied on top of base ADS.','Gabungan uplift di atas base ADS.']},
 deltaDemand:{t:['Δ Expiry units','Δ Unit expiry'],f:'( expiry units after ÷ expiry base ) − 1',e:['Change in expiry-risk units under the simulation. Lower is better.','Perubahan unit risiko expiry di simulasi. Lebih rendah lebih baik.']},
 deltaMargin:{t:['Δ Working capital','Δ Modal kerja'],f:'( inventory value after ÷ base ) − 1',e:['Change in tied-up capital. Lower is better.','Perubahan modal terikat. Lebih rendah lebih baik.']},
 service:{t:['Service level','Service level'],f:'90% + 1.4 × safety − 0.6 × lead + 0.1 × inbound',e:['Expected in-stock service level under the simulation.','Perkiraan service level di bawah simulasi.']},
 suggestedOrderSim:{t:['Stockout SKUs (after)','SKU stockout (sesudah)'],f:'count( Position < ROP ) after simulation levers',e:['SKUs still below reorder point after the simulation.','SKU yang masih di bawah reorder point setelah simulasi.']},
 rop:{t:['Reorder Point (ROP)','Reorder Point (ROP)'],f:'ADS × ( Lead time + Safety )',e:['Stock level that triggers a reorder.','Level stok yang memicu reorder.']},
 minv:{t:['Min','Min'],f:'ROP = ADS × ( Lead + Safety )',e:['Minimum stock before replenishment is needed.','Stok minimum sebelum perlu replenishment.']},
 maxv:{t:['Max','Max'],f:'ADS × ( Lead + Safety + Review )',e:['Order-up-to level.','Level target pengisian (order-up-to).']},
 position:{t:['Position','Posisi'],f:'On Hand + Open PO',e:['Current + inbound stock available to cover demand.','Stok saat ini + inbound untuk menutup demand.']},
 suggestion:{t:['Suggestion','Saran'],f:'max( 0, Max − Position )',e:['Recommended order quantity.','Jumlah order yang direkomendasikan.']},
 target:{t:['Target ADS / AMS','Target ADS / AMS'],f:'Fresh: ADS per day · Non-fresh: AMS = ADS × 30',e:['Demand baseline used for planning.','Baseline demand untuk perencanaan.']},
 uplift:{t:['Sales uplift','Uplift penjualan'],f:'stockout-risk SKUs × 1.8%',e:['Sales expected to recover by acting on risk SKUs.','Penjualan yang diperkirakan pulih dengan bertindak.']},
 marginProtect:{t:['Margin protection','Proteksi margin'],f:'Suggested order × margin/unit (≈ Rp 4,200)',e:['Margin protected by preventing stockouts.','Margin yang dilindungi dengan mencegah stockout.']},
 svcAction:{t:['Service level','Service level'],f:'94% + 0.7 × safety days',e:['Projected availability after the action.','Perkiraan ketersediaan setelah aksi.']},
 scenOrder:{t:['Stockout SKUs','SKU stockout'],f:'count( Position < ROP )',e:['Stockout-risk SKU count for the scenario.','Jumlah SKU risiko stockout untuk skenario.']},
 drawerFcst:{t:['Forecast 7d (store)','Forecast 7h (toko)'],f:'Σ scope ADS × store size × 7',e:['Store-level 7-day forecast.','Forecast 7 hari level toko.']},
 drawerAcc:{t:['Accuracy','Akurasi'],f:'100% − MAPE (per store)',e:['Backtested accuracy for the store.','Akurasi backtest untuk toko.']},
 drawerRisk:{t:['Stockout risk','Risiko stockout'],f:'SKUs where OnHand+OpenPO < ADS×(Lead+Safety)',e:['Risk-SKU count for the store.','Jumlah SKU berisiko untuk toko.']},
 invPosition:{t:['On-hand position','Posisi on-hand'],f:'Σ ( On Hand + Open PO ) across scope',e:['Total units available now plus inbound.','Total unit tersedia sekarang + inbound.']},
 dosBox:{t:['Days of Supply','Days of Supply'],f:'Position ÷ ADS',e:['How many days current stock covers demand.','Berapa hari stok saat ini menutup demand.']},
 ropBox:{t:['Reorder Point','Reorder Point'],f:'ADS × ( Lead + Safety )',e:['Stock level that should trigger a reorder.','Level stok yang memicu reorder.']},
 daysToStockout:{t:['Days to stockout','Hari ke stockout'],f:'first day projected on-hand falls below ROP',e:['Runway before replenishment is required.','Sisa waktu sebelum perlu replenishment.']},
 inbound:{t:['Inbound (Open PO)','Inbound (Open PO)'],f:'Σ Open PO units scaled to scope',e:['Units already on order arriving soon.','Unit yang sudah dipesan, segera tiba.']},
 onhandU:{t:['On Hand','On Hand'],f:'ADS × on-hand days × store scope',e:['Physical stock currently in scope.','Stok fisik saat ini di scope.']},
 reserved:{t:['Reserved','Reserved'],f:'≈ 12% of on-hand (allocated)',e:['Stock committed to orders, not available to sell.','Stok teralokasi, tidak tersedia untuk dijual.']},
 openpoU:{t:['Open PO','Open PO'],f:'Open PO units scaled to store scope',e:['Inbound purchase orders for this SKU.','PO inbound untuk SKU ini.']},
 expiryCell:{t:['Shelf-life','Shelf-life'],f:'remaining days before expiry (fresh)',e:['Days until the batch expires.','Hari tersisa sebelum batch expiry.']},
 transferU:{t:['Transfer units','Unit transfer'],f:'Σ ( Position − Max ) for overstock SKUs',e:['Excess units to move to needier stores/DC.','Unit berlebih untuk dipindah ke toko/DC yang butuh.']},
 expirySave:{t:['Expiry to clear','Expiry dibereskan'],f:'Σ fresh units at expiry risk',e:['Units to clear via markdown/transfer before expiry.','Unit dibereskan lewat markdown/transfer sebelum expiry.']},
 capitalFree:{t:['Capital to free','Modal dibebaskan'],f:'Σ excess capital = Σ ( Position − Max ) × price',e:['Working capital released by clearing overstock.','Modal kerja yang dibebaskan dengan clear overstock.']},
 actQty:{t:['Action quantity','Jumlah aksi'],f:'Replenish: Max−Position · Transfer: Position−Max · Markdown: expiry units',e:['Quantity for the recommended action.','Jumlah untuk aksi yang direkomendasikan.']},
 df_suggestedOrder:{t:['Suggested order','Saran order'],f:'Σ forecast over ( lead + safety ) days',e:['Units to cover demand across the replenishment cycle.','Unit untuk menutup demand selama siklus.']},
 df_deltaDemand:{t:['Δ Demand','Δ Demand'],f:'( simulated forecast ÷ base forecast ) − 1',e:['Change in 7-day demand vs base.','Perubahan demand 7 hari vs dasar.']},
 df_deltaMargin:{t:['Δ Margin','Δ Margin'],f:'price change% − ½ × promo depth%',e:['Estimated margin impact of levers.','Perkiraan dampak margin dari lever.']},
 df_service:{t:['Service level','Service level'],f:'90% + 1.4 × safety − 0.6 × lead',e:['Expected in-stock service under simulation.','Perkiraan service level di simulasi.']},
 inv_stockoutAfter:{t:['Stockout SKUs (after)','SKU stockout (sesudah)'],f:'count( Position < ROP ) after levers',e:['SKUs still below ROP after simulation.','SKU masih di bawah ROP setelah simulasi.']},
 inv_dExpiry:{t:['Δ Expiry units','Δ Unit expiry'],f:'( expiry after ÷ base ) − 1',e:['Change in expiry-risk units. Lower is better.','Perubahan unit expiry. Lebih rendah lebih baik.']},
 inv_dCapital:{t:['Δ Working capital','Δ Modal kerja'],f:'( inventory value after ÷ base ) − 1',e:['Change in tied-up capital. Lower is better.','Perubahan modal terikat. Lebih rendah lebih baik.']},
 inv_service:{t:['Service level','Service level'],f:'90% + 1.4 × safety − 0.6 × lead + 0.1 × inbound',e:['Expected in-stock service under simulation.','Perkiraan service level di simulasi.']}
};
function showFx(e,el){clearTimeout(popTimer);const fx=FX[el.dataset.fx];if(!fx)return;const val=(el.dataset.fxval||el.textContent||'').trim();
  popEl.innerHTML=`<div class="pt">🔍 ${T('Explain this calculation','Jelaskan kalkulasi ini')}</div>
    <div style="font-weight:600;font-size:12px">${T(fx.t[0],fx.t[1])}</div>
    <div class="formula">${fx.f}</div><div class="expl">${T(fx.e[0],fx.e[1])}</div>
    ${val?`<div class="nums">${T('Value','Nilai')}: <b>${val}</b>${el.dataset.fxin?' · '+el.dataset.fxin:''}</div>`:''}
    <div class="plink" onclick="explainInChat('${T(fx.t[0],fx.t[1]).replace(/'/g,'')}')">💬 ${T('Explain in chat','Jelaskan di chat')} →</div>`;
  popEl.classList.add('show');place(popEl,e);}
document.addEventListener('mouseover',e=>{const el=e.target.closest('[data-fx]');if(el)showFx(e,el);});
document.addEventListener('mouseout',e=>{const el=e.target.closest('[data-fx]');if(el)hideFormula();});

/* ================= MULTI-AGENT CONTROLLER ================= */
function computeK_DF(){
  const daily=genDaily();
  const fore7=daily.fc.slice(0,7).reduce((a,b)=>a+b,0);
  const last7=daily.hist.slice(-7).reduce((a,b)=>a+b,0);
  const _l=activeSKUs();const freshShare=_l.length?_l.filter(s=>s.fresh).length/_l.length:0;const viralShare=_l.length?_l.filter(s=>s.viral).length/_l.length:0;
  const trend=((fore7/7)/(last7/7)-1)*100+(healthFactor()-1)*10+(storeIdx()-1)*12+viralShare*15;
  let risk=0;_l.forEach(s=>{const m=invMetrics(s);if(m.position<m.rop)risk++;});
  const acc=88.3+(state.itemMode==='item'?2.2:0)-(state.triggers.viral?0:1.2)+(healthFactor()-1)*6+(storeIdx()-1)*8-freshShare*3;
  const seasIdx=Math.round((freshShare>=0.5?SEAS_FRESH:SEAS_DRY)[MONTH]*100*(0.94+0.12*storeIdx()));
  const promoUp=state.triggers.promotion?14.2:0;
  const trendCount=Math.max(0,Math.round(_l.filter(s=>s.viral).length*storeIdx()));
  return {fore7,last7,trend,risk,acc,seasIdx,promoUp,trendCount,daily};
}
const KPIDEFS_DF=[
  {key:'fore7',color:'#0078D4',lab:['Forecast (next 7d)','Forecast (7 hari)'],fmt:k=>fmt(k.fore7)+' u',delta:k=>pct(k.trend),dcls:k=>k.trend>=0?'up':'down',
   f:'Σ ( ADS × DOW × Seasonality × TriggerAdj ), d=1..7',e:['7-day demand for the current scope.','Demand 7 hari untuk scope terpilih.'],val:k=>k.fore7},
  {key:'acc',color:'#0A9ED4',lab:['Forecast Accuracy','Akurasi Forecast'],fmt:k=>k.acc.toFixed(1)+'%',delta:k=>T('MAPE-based','berbasis MAPE'),dcls:()=>'up',
   f:'100% − MAPE ; MAPE = mean(|Act−Fcst|÷Act)',e:['Backtested accuracy.','Akurasi backtest.'],val:k=>k.acc},
  {key:'trend',color:'#5C2D91',lab:['Demand Trend','Trend Demand'],fmt:k=>pct(k.trend),delta:k=>T('vs last 7d','vs 7 hari lalu'),dcls:k=>k.trend>=0?'up':'down',
   f:'(avg Fcst next7 ÷ avg Act last7) − 1',e:['Direction of demand vs last week.','Arah demand vs minggu lalu.'],val:k=>k.trend},
  {key:'risk',color:'#D13438',lab:['Stockout-Risk SKUs','SKU Risiko Stockout'],fmt:k=>fmt(k.risk),delta:k=>T('need action','perlu aksi'),dcls:()=>'down',
   f:'count(OnHand+OpenPO < ADS×(Lead+Safety))',e:['SKUs supply cannot cover in lead time.','SKU yang supply tak cukup dalam lead time.'],val:k=>k.risk},
  {key:'trendCount',color:'#E8792B',lab:['Predicted to Trend','Diprediksi Nge-trend'],fmt:k=>fmt(k.trendCount)+' SKU',delta:k=>T('rising signal','sinyal naik'),dcls:()=>'up',
   f:'count( viral/seasonal uplift > +15% )',e:['SKUs predicted to rise from viral + seasonal signals.','SKU diprediksi naik dari sinyal viral + seasonal.'],val:k=>k.trendCount},
  {key:'seasIdx',color:'#107C41',lab:['Seasonality Index','Indeks Seasonality'],fmt:k=>k.seasIdx,delta:()=>'Jul',dcls:()=>'',
   f:'SeasonalityFactor(month) × 100',e:['100 = average month.','100 = bulan rata-rata.'],val:k=>k.seasIdx},
];
function renderForecast_DF(){const ser=genSeries(false);lineChart('chart-forecast',ser);
  const m=periodMeta();const total=ser.fc.reduce((a,b)=>a+b,0);const avg=Math.round(total/ser.fc.length);const peak=Math.max(...ser.fc);const confW=Math.round(Math.min(0.30,0.05+0.0038*ser.fc.length)*100);
  G('forenote').textContent=T(`View: ${state.period.toUpperCase()} · ${m.fcN} ${m.label}(s) ahead · horizon ${state.horizon}wk · scope: ${scopeShort()}`,`Tampilan: ${state.period.toUpperCase()} · ${m.fcN} ${m.label} ke depan · horizon ${state.horizon}mgg · scope: ${scopeShort()}`);
  G('forecastStats').innerHTML=`<div class="m"><div class="k">${T('Σ over horizon','Σ sepanjang horizon')}</div><b data-fx="sigmaHorizon">${fmt(total)} u</b></div>
    <div class="m"><div class="k">${T('Avg per','Rata2 per')} ${m.label}</div><b data-fx="avgPeriod">${fmt(avg)} u</b></div>
    <div class="m"><div class="k">${T('Peak','Puncak')}</div><b data-fx="peak">${fmt(peak)} u</b></div>
    <div class="m"><div class="k">${T('Confidence ±','Interval ±')}</div><b data-fx="confidence">${confW}%</b></div>
    <div class="m"><div class="k">${T('Periods','Periode')}</div><b data-fx="periods">${m.fcN} ${m.label}</b></div>`;}
function renderDriver_DF(){
  const base=scopeDailyBase()*7;const t=state.triggers;
  const items=[
    {label:T('Baseline','Baseline'),value:base*0.72,color:'#94a3c8'},
    {label:'Seasonality',value:base*(t.seasonal?0.11:0.03),color:'#107C41'},
    {label:'Weekday',value:base*0.08,color:'#0078D4'},
    {label:'Promotion',value:base*(t.promotion||t.promo?0.06:0),color:'#C77700'},
    {label:'Viral',value:base*(t.viral?0.05:0),color:'#E8792B'},
    {label:'Loyalty',value:base*(t.loyalty?0.02:0),color:'#5C2D91'},
    {label:T('Forecast','Forecast'),value:base*(0.72+0.08+(t.seasonal?0.11:0.03)+(t.promotion||t.promo?0.06:0)+(t.viral?0.05:0)+(t.loyalty?0.02:0)),color:'#0078D4',total:true},
  ];
  waterfall('chart-driver',items);
}
function renderTrend_DF(){
  const list=activeSKUs().filter(s=>s.viral).slice(0,5);
  const pool=list.length?list:activeSKUs().slice().sort((a,b)=>b.growth-a.growth).slice(0,5);
  const el=G('trendlist');el.innerHTML=pool.map(s=>{const up=((s.viral?18:8)+s.growth*10);
    return `<div class="trow"><span class="fireicon">${s.viral?'🔥':'📈'}</span>
      <div><div class="tn">${s.name}</div><div class="tc">${s.cat} · ${s.viral?T('viral signal','sinyal viral'):T('seasonal lift','naik seasonal')}</div></div>
      <div class="tu up">${pct(up)}</div></div>`;}).join('')||`<div class="tiny muted">${T('No trending items in scope.','Tidak ada item nge-trend di scope.')}</div>`;
}
function renderCat_DF(){
  const stF=storeFactor();
  const data=CATS.map(c=>{let v=0;SKUS.filter(s=>s.catId===c.id).forEach(s=>v+=s.base*(s.fresh?SEAS_FRESH:SEAS_DRY)[MONTH]);
    return {label:c.name,value:v*stF*7,color:CCOLOR[c.id],sub:c.fresh?'Fresh':c.name,fx:'Σ ADS(category) × store scope × 7 days',
      onclick:()=>{state.itemMode='cat';state.cats=new Set([c.id]);syncSegs();refreshAll();toast('🗂️ '+T('Filtered: ','Filter: ')+c.name);}};});
  barChart('chart-cat',data,{pb:52});
}
function renderStore_DF(){
  let dailyAll=0;activeSKUs().forEach(s=>dailyAll+=s.base*(s.fresh?SEAS_FRESH:SEAS_DRY)[MONTH]);
  const data=STORES.map(st=>({label:st.name.replace('HERO ',''),value:dailyAll*st.size*7,color:'#0a68b8',fx:'Σ scope ADS × store size × 7 days',
    onclick:()=>{state.storeMode='sel';state.stores=new Set([st.id]);syncSegs();refreshAll();toast('🏪 '+T('Filtered: ','Filter: ')+st.name);}}))
    .sort((a,b)=>b.value-a.value);
  hbarChart('chart-store',data);
}
function renderCluster_DF(){
  let dailyAll=0;activeSKUs().forEach(s=>dailyAll+=s.base*(s.fresh?SEAS_FRESH:SEAS_DRY)[MONTH]);
  const cc={Premium:'#5C2D91','Urban Mall':'#0078D4',Suburban:'#008575',Resort:'#C77700'};
  const data=CLUSTERS.map(cl=>{const sz=STORES.filter(s=>s.cluster===cl).reduce((a,s)=>a+s.size,0);
    return {label:cl,value:dailyAll*sz*7,color:cc[cl],fx:'Σ scope ADS × Σ store size(cluster) × 7 days',
      onclick:()=>{state.storeMode='sel';state.stores=new Set(STORES.filter(s=>s.cluster===cl).map(s=>s.id));syncSegs();refreshAll();toast('🧭 '+T('Cluster: ','Cluster: ')+cl);}};});
  barChart('chart-cluster',data,{pb:40});
}
function renderSeason_DF(){const isF=activeSKUs().some(s=>s.fresh);
  const data=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].map((m,i)=>({label:m,value:(isF?SEAS_FRESH:SEAS_DRY)[i]*100,color:i===MONTH?'#C77700':'#cfe0f3',fx:'Seasonality factor(month) × 100 (100 = average month)'}));
  barChart('chart-season',data,{h:196,pb:26});
}
function renderMatrix_DF(){
  const H=state.horizon;const sf=storeFactor();
  const storeLbl=(state.storeMode==='sel'&&state.stores.size)?(state.stores.size===1?STORES.find(s=>state.stores.has(s.id)).name.replace('HERO ',''):state.stores.size+' stores'):T('All','Semua');
  const rows=activeSKUs().map(s=>{
    const seas=(s.fresh?SEAS_FRESH:SEAS_DRY)[MONTH];
    const dv=s.viral&&state.triggers.viral, dp=s.promo&&(state.triggers.promotion||state.triggers.promo);
    const mult=seas*(dv?1.12:1)*(dp?1.08:1);
    const fads=Math.round(s.base*mult*sf);
    const weeks=[];for(let w=0;w<H;w++)weeks.push(Math.round(fads*7*(1+0.08*Math.sin((w+MONTH)/2.2))));
    const units=weeks.reduce((a,b)=>a+b,0);const conf=Math.round(8+H*1.1);
    const drivers=[dv?'viral':'',dp?'promo':'',seas>1.03?'seasonal':''].filter(Boolean).join(', ')||T('baseline','baseline');
    return {s,fads,units,mult,conf,weeks,drivers};
  }).sort((a,b)=>b.units-a.units).slice(0,12);
  G('chart-matrix').innerHTML=`<table class="tbl"><thead><tr>
    <th>SKU</th><th>Item</th><th>Category</th><th>Store</th><th>Forecast ADS</th><th>${H}-wk units</th><th>Drivers ×</th><th>Conf ±</th><th>${T('Horizon trend','Trend horizon')}</th></tr></thead><tbody>
    ${rows.map(r=>`<tr style="cursor:pointer" onclick="drillSku('${r.s.id}')">
      <td>${r.s.id}</td><td style="text-align:left">${r.s.name}</td>
      <td style="text-align:left"><span class="badge" style="background:${CCOLOR[r.s.catId]}22;color:${CCOLOR[r.s.catId]}">${r.s.cat}</span></td>
      <td style="text-align:left">${storeLbl}</td>
      <td data-fx="fads"><b style="color:#5C2D91">${fmt(r.fads)}</b>/d</td>
      <td data-fx="horizonUnits"><b>${fmt(r.units)}</b></td>
      <td data-fx="drivers" style="text-align:left">×${r.mult.toFixed(2)} <span class="tiny muted">${r.drivers}</span></td>
      <td data-fx="conf">±${r.conf}%</td>
      <td>${miniBars(r.weeks,CCOLOR[r.s.catId])}</td></tr>`).join('')}
  </tbody></table>`;
}
function runSim_DF(){
  const sv=state.period;state.period='daily';const ser=genSeries(true);const base=genSeries(false);state.period=sv;
  const fcS=ser.fc.slice(0,14),bandS=ser.band.slice(0,14),fcL=ser.fcLabels.slice(0,14);
  lineChart('chart-sim',{hist:ser.hist.slice(-14),fc:fcS,band:bandS,labels:[...ser.histLabels.slice(-14),...fcL]},{h:180});
  const order=ser.fc.slice(0,state.sim.lead+state.sim.safe).reduce((a,b)=>a+b,0);
  const nf=ser.fc.slice(0,7).reduce((a,b)=>a+b,0),bf=base.fc.slice(0,7).reduce((a,b)=>a+b,0);
  const dDem=(nf/bf-1)*100,dMgn=(state.sim.price*0.01-state.sim.promo*0.01*0.5)*100,svc=Math.min(99,90+state.sim.safe*1.4-state.sim.lead*0.6);
  simRun={order,dDem,dMgn,svc,series:ser.fc.slice(0,14)};
  G('sim-order').textContent=fmt(order)+' u';const dd=G('sim-delta');dd.textContent=pct(dDem);dd.className=dDem>=0?'up':'down';
  const dm=G('sim-margin');dm.textContent=pct(dMgn);dm.className=dMgn>=0?'up':'down';G('sim-svc').textContent=svc.toFixed(1)+'%';
}
function renderAction_DF(){
  const k=computeK();const orderQty=Math.round(scopeDailyBase()*(state.sim.lead+state.sim.safe));
  const stTag={pending:'st-pending',approved:'st-approved',rejected:'st-rejected',cancelled:'st-cancelled',reopened:'st-reopened',sent:'st-sent'}[actionState];
  const stTxt={pending:T('Pending','Menunggu'),approved:'Approved',rejected:'Rejected',cancelled:T('Cancelled','Dibatalkan'),reopened:'Reopened',sent:T('Sent →','Terkirim →')}[actionState];
  G('actionbody').innerHTML=`
    <div class="action-card"><div class="ah"><span class="pri high">${T('HIGH PRIORITY','PRIORITAS TINGGI')}</span>
      <b>${T('Replenish before 03:00 cut-off','Replenish sebelum cut-off 03:00')}</b><span class="status-tag ${stTag}">${stTxt}</span></div>
      <div class="tiny muted">${T('Agent detected','Agent mendeteksi')} <b style="color:#c81e4a">${k.risk} SKU</b> ${T('at stockout risk within lead time.','berisiko stockout dalam lead time.')}</div>
      <div class="impact">
        <div><span class="muted tiny">${T('Suggested Order','Saran Order')}</span><b class="val" data-k="order">${fmt(orderQty)} u</b></div>
        <div><span class="muted tiny">${T('Sales Uplift','Uplift Penjualan')}</span><b class="up" data-fx="uplift">+${(k.risk*1.8).toFixed(1)}%</b></div>
        <div><span class="muted tiny">${T('Margin Protect','Proteksi Margin')}</span><b data-fx="marginProtect">Rp ${fmt(orderQty*4200)}</b></div>
        <div><span class="muted tiny">Service</span><b data-fx="svcAction">${(94+state.sim.safe*0.7).toFixed(1)}%</b></div></div>
      <div class="agentic-row">
        <button class="abtn approve" onclick="agentic('approved')">✔ ${T('Approve','Setujui')}</button>
        <button class="abtn reject" onclick="agentic('rejected')">✕ ${T('Reject','Tolak')}</button>
        <button class="abtn cancel" onclick="agentic('cancelled')">⊘ ${T('Cancel','Batal')}</button>
        <button class="abtn reopen" onclick="agentic('reopened')">↻ ${T('Reopen','Buka lagi')}</button>
        <button class="btn indigo sm" style="margin-left:auto" onclick="togglePO()">📦 ${T('Generate PO Recommendation','Buat Rekomendasi PO')}</button></div></div>
    <div id="po-preview"></div>`;
  G('actionbody').querySelectorAll('.val').forEach(v=>{v.addEventListener('mouseenter',e=>showFormula(e,{key:'order',f:'ADS × (Lead + Safety) − On Hand − Open PO',e:['Cover demand across replenishment cycle, net of stock/inbound.','Menutup demand selama siklus, dikurangi stok/inbound.'],lab:['Suggested Order','Saran Order'],val:()=>orderQty},k));v.addEventListener('mouseleave',hideFormula);});
}
function togglePO_DF(){return togglePO_INV();}
function __togglePO_DF_dead(){poOpen=!poOpen;const w=G('po-preview');if(!poOpen){w.innerHTML='';return;}
  const list=activeSKUs().slice(0,10);const store=activeStores()[0];
  const rows=list.map(s=>{const m=invMetrics(s);const ads=m.ads;const ams=Math.round(m.ads*30);const targetLabel=s.fresh?fmt(ads)+' /d':fmt(ams)+' /mo';
    const rop=m.rop;const min=m.rop;const max=m.maxLevel;
    const pos=m.position;const sug=Math.max(0,m.maxLevel-m.position);
    const route=s.fresh?'direct':(s.base>25?'flow':'cross');const eta=new Date(Date.now()+s.lead*864e5).toLocaleDateString('en-GB',{day:'2-digit',month:'short'});
    return {sku:s.id,name:s.name,cat:s.cat,store:store.name.replace('HERO ',''),target:targetLabel,rop,min,max,pos,sug,route,eta,src:s.fresh?s.vendor:s.dc,low:pos<rop};});
  w.innerHTML=`<div class="tiny muted" style="margin:4px 0 6px">${T('PO recommendation — Target ADS/AMS, ROP, Min/Max, Position vs Suggestion. Fresh routes Direct-to-Store; non-fresh via DC (Flow-Through / Cross-Dock).','Rekomendasi PO — Target ADS/AMS, ROP, Min/Max, Position vs Suggestion. Fresh Direct-to-Store; non-fresh via DC.')}</div>
    <div style="overflow:auto;border:1px solid var(--line);border-radius:11px"><table class="tbl"><thead><tr>
      <th>SKU</th><th>Item</th><th>Category</th><th>Store</th><th>Target ADS/AMS</th><th>ROP</th><th>Min</th><th>Max</th><th>Position</th><th>Suggestion</th><th>Route</th><th>Exp.Del</th><th>Source</th></tr></thead>
      <tbody>${rows.map(r=>`<tr><td>${r.sku}</td><td style="text-align:left">${r.name}</td><td style="text-align:left"><span class="badge" style="background:${CCOLOR[r.sku.split('-')[0]]}22;color:${CCOLOR[r.sku.split('-')[0]]}">${r.cat}</span></td>
        <td style="text-align:left">${r.store}</td><td data-fx="target">${r.target}</td><td data-fx="rop">${fmt(r.rop)}</td><td data-fx="minv">${fmt(r.min)}</td><td data-fx="maxv">${fmt(r.max)}</td>
        <td data-fx="position" class="${r.low?'pos-low':'pos-ok'}">${fmt(r.pos)}</td><td data-fx="suggestion"><b>${fmt(r.sug)}</b></td>
        <td style="text-align:left"><span class="route ${r.route}">${r.route==='direct'?'Direct':r.route==='flow'?'Flow-Through':'Cross-Dock'}</span></td><td>${r.eta}</td><td style="text-align:left">${r.src}</td></tr>`).join('')}</tbody></table></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:9px">
      <button class="btn teal sm" onclick="sendHandoff('${rows.length+' '+T('PO line(s)','baris PO')}')">➤ ${T('Send to Replenishment Agent','Kirim ke Replenishment Agent')}</button>
      <button class="btn sm" onclick='exportPO(${JSON.stringify(rows)})'>⬇ ${T('Export PO to Excel','Export PO ke Excel')}</button></div>`;
}
function exportPO_DF(rows){const h=['SKU','Item','Category','Store','Target ADS/AMS','ROP','Min','Max','Position','Suggestion','Route','Expected Delivery','Source'];
  downloadCSV('AI360_PO_Recommendation.csv',[h,...rows.map(r=>[r.sku,r.name,r.cat,r.store,r.target,r.rop,r.min,r.max,r.pos,r.sug,r.route,r.eta,r.src])]);toast('⬇ '+T('PO exported','PO diekspor'));}
function aiReply_DF(q){const k=computeK();const ql=q.toLowerCase();const ch=CHALLENGE;
  const base=scopeDailyBase();
  if(ql.includes('lead time')||ql.includes('lead')&&ch){
    const rop=Math.round(base*(state.sim.lead+state.sim.safe)),rop2=Math.round(base*(state.sim.lead*2+state.sim.safe));
    addMsg('ai',`${T('If vendor lead time doubles','Kalau lead time vendor 2x')} (${state.sim.lead}→${state.sim.lead*2}d), ${T('reorder point and exposure rise sharply:','reorder point dan eksposur naik tajam:')}
      <div class="calcbox">ROP = ADS × (Lead + Safety)
now  = ${fmt(base)} × (${state.sim.lead}+${state.sim.safe}) = ${fmt(rop)} u
x2   = ${fmt(base)} × (${state.sim.lead*2}+${state.sim.safe}) = ${fmt(rop2)} u
Δ exposure = +${fmt(rop2-rop)} u (+${((rop2/rop-1)*100).toFixed(0)}%)</div>
      ${T('Risk: fresh items with 2–5 day shelf life would exceed expiry before selling. Recommend dual-sourcing or DC buffer.','Risiko: item fresh shelf-life 2–5 hari bisa lewat expiry sebelum terjual. Sarankan dual-sourcing atau buffer DC.')}`,true);
  }else if(ql.includes('stockout')||ql.includes('risk')){
    const list=activeSKUs().slice().sort((a,b)=>a.onHandDays-b.onHandDays).slice(0,4);
    addMsg('ai',`${T('Highest stockout-risk items in scope:','Item paling berisiko stockout:')}
      <div class="calcbox">risk if  OnHand + OpenPO  <  ADS × (Lead+Safety)</div>
      <table class="mini-table"><thead><tr><th>Item</th><th>OnHand(d)</th><th>Lead</th><th>ADS</th><th>ROP</th></tr></thead><tbody>
      ${list.map(s=>`<tr><td>${s.name}</td><td>${s.onHandDays}</td><td>${s.lead}</td><td>${fmt(s.base)}</td><td>${fmt(s.base*(s.lead+s.safety))}</td></tr>`).join('')}</tbody></table>
      ${ch?T('<br>Challenge: 3 of these share one vendor. A single delay cascades. Diversify.','<br>Challenge: 3 di antaranya 1 vendor. Satu telat, semua kena. Diversifikasi.'):''}`,ch);
  }else if(ql.includes('accuracy')||ql.includes('akuras')){
    addMsg('ai',`${T('Forecast accuracy','Akurasi forecast')} = <b>${k.acc.toFixed(1)}%</b>.
      <div class="calcbox">Accuracy = 100% − MAPE
MAPE = mean(|Actual − Forecast| ÷ Actual)
active triggers = ${Object.values(state.triggers).filter(Boolean).length}/17</div>
      ${ch?T('Challenge: MAPE hides big misses on low-volume SKUs (small denominator inflates error). For fresh, also track bias and waste%, not just MAPE.','Challenge: MAPE menyembunyikan miss besar di SKU volume kecil. Untuk fresh, pantau bias dan waste% juga, bukan cuma MAPE.'):T('Viral, promotion and history triggers lift accuracy.','Trigger viral, promotion, history menaikkan akurasi.')}`,ch);
  }else if(ql.includes('po')||ql.includes('order')||ql.includes('replenish')){
    addMsg('ai',`${T('PO recommendation ready with Target ADS/AMS, ROP, Min/Max, Position, Suggestion.','Rekomendasi PO siap dengan Target ADS/AMS, ROP, Min/Max, Position, Suggestion.')}
      <div class="calcbox">Suggestion = max(0, Max − Position)
Max = ADS × (Lead+Safety+Review)</div>
      <button class="btn indigo sm" onclick="togglePO();document.querySelector('[data-sec=action]').scrollIntoView({behavior:'smooth'})">📦 ${T('Open PO','Buka PO')}</button>`,ch);
  }else if(ql.includes('why')||ql.includes('kenapa')||ql.includes('demand')||ql.includes('driver')){
    addMsg('ai',`${T('Demand is','Demand')} <b>${pct(k.trend)}</b> ${T('vs last week. Decomposition:','vs minggu lalu. Dekomposisi:')}
      <div class="calcbox">Forecast = Baseline × Σ(driver factors)</div>
      <table class="mini-table"><tbody>
      <tr><td>Seasonality (Jul)</td><td>+${(k.seasIdx-100)}%</td></tr><tr><td>Weekend (DOW)</td><td>+18%</td></tr>
      <tr><td>${state.triggers.viral?'Viral':'Viral (off)'}</td><td>${state.triggers.viral?'+5%':'0%'}</td></tr>
      <tr><td>${state.triggers.promotion?'Promotion':'Promotion (off)'}</td><td>${state.triggers.promotion?'+6%':'0%'}</td></tr></tbody></table>
      ${ch?T('<br>Challenge: weekend uplift assumes staffing holds. If understaffed, availability caps the uplift.','<br>Challenge: uplift weekend asumsi staff cukup. Kalau kurang staff, availability membatasi uplift.'):''}`,ch);
  }else if(ql.includes('peak')||ql.includes('stress')){
    const peak=Math.round(base*1.35*(state.sim.lead+state.sim.safe));
    addMsg('ai',`${T('Peak-week stress test (Sat/Sun DOW 1.35, Dec seasonality 1.25):','Stress-test minggu puncak (Sab/Min DOW 1.35, Des 1.25):')}
      <div class="calcbox">Peak order = ADS × DOW × Seas × (Lead+Safety)
= ${fmt(base)} × 1.35 × 1.25 × (${state.sim.lead}+${state.sim.safe})
≈ ${fmt(peak*1.25)} u</div>
      ${T('Recommend pre-building safety stock 3–4 days before peak; watch fresh expiry.','Sarankan bangun safety stock 3–4 hari sebelum puncak; awasi expiry fresh.')}`,true);
  }else if(ql.includes('explain')){
    addMsg('ai',T('Hover any number on the dashboard to see its formula, inputs and current value. Every answer here also shows the math.','Arahkan kursor ke angka mana pun untuk lihat formula, input, dan nilainya. Tiap jawaban di sini juga menampilkan hitungannya.'),ch);
  }else{
    addMsg('ai',T('I can explain demand drivers, stockout risk, accuracy, run PO recommendations, and stress-test scenarios. Turn on Challenge mode to pressure-test the numbers.','Saya bisa jelaskan driver demand, risiko stockout, akurasi, rekomendasi PO, dan stress-test skenario. Nyalakan Challenge mode untuk menguji angkanya.'),ch);
  }
}
const CHIPS_DF=[['Why is demand up this week?','Kenapa demand naik minggu ini?',0],['Top stockout-risk items','Item paling berisiko stockout',0],['Explain forecast accuracy','Jelaskan akurasi forecast',0],['Recommend PO for fresh','Rekomendasi PO untuk fresh',0]];
const CHIPS_CH_DF=[['Challenge: what if lead time doubles?','Challenge: kalau lead time 2x?',1],['Stress-test peak week demand','Stress-test demand minggu puncak',1],['Challenge the accuracy number','Tantang angka akurasi',1]];

let KPIDEFS=null, CHIPS=[], CHIPS_CH=[];
const SUF={df:'DF',inv:'INV',rep:'REP',promo:'PROMO',pm:'PM',assort:'ASSORT',ai:'AI'};
const A=n=>window[n+'_'+(SUF[state.agent]||'DF')];
function computeK(){return A('computeK')();}
function renderForecast(){return A('renderForecast')();}
function renderDriver(){return A('renderDriver')();}
function renderTrend(){return A('renderTrend')();}
function renderCat(){return A('renderCat')();}
function renderStore(){return A('renderStore')();}
function renderCluster(){return A('renderCluster')();}
function renderSeason(){return A('renderSeason')();}
function renderMatrix(){return A('renderMatrix')();}
function runSim(){return A('runSim')();}
function renderAction(){return A('renderAction')();}
function togglePO(){return state.agent==='promo'?togglePromoPlan():state.agent==='pm'?togglePMPlan():state.agent==='assort'?toggleAssortPlan():state.agent==='ai'?toggleAISummary():togglePO_INV();}
function exportPO(r){return (A('exportPO')||exportPO_INV)(r);}
function aiReply(q){return A('aiReply')(q);}

const LABELS={
 df:{ name:['Demand Forecasting','Demand Forecasting'], sub:['Demand Forecasting \u00b7 Hero','Demand Forecasting \u00b7 Hero'], crumb:'Agent 1 of 8',
   forecast:['Forecast vs Actual + Confidence','Forecast vs Aktual + Interval'],
   legend:[['Actual','Aktual'],['Forecast','Forecast'],['Confidence','Interval']],
   driver:['Driver Decomposition','Dekomposisi Driver'], driverHint:['what builds the forecast','pembentuk forecast'],
   trend:['Predicted to Trend','Diprediksi Nge-trend'], trendHint:['next 2 weeks','2 minggu ke depan'],
   cat:['Demand by Category','Demand per Kategori'], store:['Forecast by Store','Forecast per Toko'],
   cluster:['Aggregate by Store Cluster','Agregat per Cluster Toko'], season:['Seasonality & Retail Calendar','Seasonality & Kalender'],
   seasonNote:['\ud83d\udd52 Hero receiving: daily until 03:00; late orders shift to next receiving day.','\ud83d\udd52 Terima Hero: harian sampai 03:00; order telat geser ke hari berikutnya.'],
   matrix:['Forecast by SKU / Store / Period','Forecast per SKU / Toko / Periode'], matrixHint:['ranked by horizon units \u00b7 click a row to drill','urut berdasarkan unit horizon \u00b7 klik baris untuk drill'],
   sliders:[['Price change','Perubahan harga'],['Promo depth','Kedalaman promo'],['Seasonality boost','Boost seasonality'],['Viral trend factor','Faktor trend viral'],['Vendor lead time','Lead time vendor'],['Safety stock','Safety stock']],
   simCaption:['Simulated forecast','Forecast tersimulasi'],
   metrics:[['Suggested order','Saran order','df_suggestedOrder'],['\u0394 Demand','\u0394 Demand','df_deltaDemand'],['\u0394 Margin','\u0394 Margin','df_deltaMargin'],['Service','Service','df_service']],
   scenC1:'Price', scenC2:'Promo', scen:['Order','\u0394Dem','\u0394Mgn'], scenDir:'higher', unit:'' },
 inv:{ name:['Inventory Risk','Inventory Risk'], sub:['Inventory Risk \u00b7 Hero','Inventory Risk \u00b7 Hero'], crumb:'Agent 2 of 8',
   forecast:['Projected On-Hand vs Demand','Proyeksi On-Hand vs Demand'],
   legend:[['On-hand','On-hand'],['Projected','Proyeksi'],['Range','Rentang']],
   driver:['At-Risk Inventory Value','Nilai Inventory Berisiko'], driverHint:['value at risk by state (Rp)','nilai berisiko per status (Rp)'],
   trend:['Expiry Watchlist','Watchlist Expiry'], trendHint:['soonest expiry','paling dekat expiry'],
   cat:['Inventory Value by Category','Nilai Inventory per Kategori'], store:['Stockout-Risk by Store','Risiko Stockout per Toko'],
   cluster:['Overstock Value by Cluster','Nilai Overstock per Cluster'], season:['Expiry Timeline','Timeline Expiry'],
   seasonNote:['\u23f0 Fresh units grouped by remaining shelf-life. \u22643 days = markdown/transfer now.','\u23f0 Unit fresh dikelompokkan per sisa shelf-life. \u22643 hari = markdown/transfer sekarang.'],
   matrix:['Inventory Risk Register','Register Risiko Inventory'], matrixHint:['ranked by risk severity \u00b7 click a row to drill','urut berdasarkan tingkat risiko \u00b7 klik baris untuk drill'],
   sliders:[['Demand change','Perubahan demand'],['Markdown depth','Kedalaman markdown'],['Extra inbound','Inbound tambahan'],['Transfer out','Transfer keluar'],['Vendor lead time','Lead time vendor'],['Safety stock','Safety stock']],
   simCaption:['Projected on-hand under levers','Proyeksi on-hand dengan lever'],
   metrics:[['Stockout SKUs','SKU stockout','inv_stockoutAfter'],['\u0394 Expiry','\u0394 Expiry','inv_dExpiry'],['\u0394 Capital','\u0394 Capital','inv_dCapital'],['Service','Service','inv_service']],
   scenC1:'Dem%', scenC2:'Mkdn%', scen:['Stockout','\u0394Expiry','\u0394Capital'], scenDir:'lower', unit:' SKU' },
 rep:{ name:['Replenishment','Replenishment'], sub:['Replenishment \u00b7 Hero','Replenishment \u00b7 Hero'], crumb:'Agent 3 of 8',
   forecast:['Replenishment Coverage','Cakupan Replenishment'],
   legend:[['On-hand','On-hand'],['Projected','Proyeksi'],['Range','Rentang']],
   driver:['Order Value by Route','Nilai Order per Rute'], driverHint:['Direct / Flow-Through / Cross-Dock','Direct / Flow-Through / Cross-Dock'],
   trend:['Reorder Now','Reorder Sekarang'], trendHint:['largest gap to ROP','gap terbesar ke ROP'],
   cat:['Order Value by Category','Nilai Order per Kategori'], store:['Reorder SKUs by Store','SKU Reorder per Toko'],
   cluster:['Order Value by Cluster','Nilai Order per Cluster'], season:['Order Units by Expected Delivery','Unit Order per Expected Delivery'],
   seasonNote:['\ud83d\ude9a Grouped by expected delivery lead. Order before 03:00 for next-day receiving.','\ud83d\ude9a Dikelompokkan per lead pengiriman. Order sebelum 03:00 untuk terima besok.'],
   matrix:['Replenishment Plan','Rencana Replenishment'], matrixHint:['ranked by gap to ROP \u00b7 click a row to drill','urut per gap ke ROP \u00b7 klik baris untuk drill'],
   sliders:[['Demand change','Perubahan demand'],['MOQ round-up','Pembulatan MOQ'],['Extra inbound','Inbound tambahan'],['Transfer out','Transfer keluar'],['Vendor lead time','Lead time vendor'],['Safety stock','Safety stock']],
   simCaption:['Projected on-hand under levers','Proyeksi on-hand dengan lever'],
   metrics:[['SKUs to reorder','SKU reorder','rep_reorderAfter'],['\u0394 Order units','\u0394 Unit order','rep_dOrderU'],['\u0394 Order value','\u0394 Nilai order','rep_dOrderV'],['Fill rate','Fill rate','rep_fill']],
   scenC1:'Dem%', scenC2:'MOQ%', scen:['Reorder','\u0394Units','\u0394Value'], scenDir:'lower', unit:' SKU' },
 promo:{ name:['Promotion Effectiveness','Promotion Effectiveness'], sub:['Promotion Effectiveness \u00b7 Hero','Promotion Effectiveness \u00b7 Hero'], crumb:'Agent 4 of 8',
   forecast:['Baseline vs Promoted Demand','Demand Baseline vs Promo'],
   legend:[['Baseline','Baseline'],['Promoted','Promo'],['Range','Rentang']],
   driver:['Incremental Margin Components','Komponen Margin Inkremental'], driverHint:['GM \u2212 markdown + funding = net','GM \u2212 markdown + funding = net'],
   trend:['Top Promo Performers','Promo Terbaik'], trendHint:['by ROI','berdasarkan ROI'],
   cat:['Incremental Margin by Category','Margin Inkremental per Kategori'], store:['Incremental Margin by Store','Margin Inkremental per Toko'],
   cluster:['Incremental Margin by Cluster','Margin Inkremental per Cluster'], season:['Uplift by Discount Depth','Uplift per Kedalaman Diskon'],
   seasonNote:['\ud83c\udff7\ufe0f Deeper discount lifts uplift but raises give-away \u2014 watch ROI.','\ud83c\udff7\ufe0f Diskon lebih dalam menaikkan uplift tapi menambah give-away \u2014 perhatikan ROI.'],
   matrix:['Promotion Effectiveness','Efektivitas Promosi'], matrixHint:['ranked by incremental margin \u00b7 click a row to drill','urut per margin inkremental \u00b7 klik baris untuk drill'],
   sliders:[['Breadth (more SKUs)','Perluasan (SKU)'],['Discount depth','Kedalaman diskon'],['Duration','Durasi'],['Supplier funding','Funding supplier'],['Elasticity','Elastisitas'],['Cannibalization','Kanibalisasi']],
   simCaption:['Baseline vs promoted under levers','Baseline vs promo dengan lever'],
   metrics:[['Incr Margin','Margin Inkremental','promo_incrM'],['ROI','ROI','promo_roi'],['\u0394 vs base','\u0394 vs base','promo_dbase'],['Uplift','Uplift','promo_uplift']],
   scenC1:'Breadth%', scenC2:'Disc%', scen:['IncrM','ROI','\u0394vs'], scenDir:'higher', unit:'' },
 pm:{ name:['Pricing & Markdown','Pricing & Markdown'], sub:['Pricing & Markdown \u00b7 Hero','Pricing & Markdown \u00b7 Hero'], crumb:'Agent 5 of 8',
   forecast:['At-Risk Stock Burn-down: Hold vs Markdown','Burn-down Stok Berisiko: Tahan vs Markdown'],
   legend:[['Hold (no action)','Tahan (tanpa aksi)'],['With markdown','Dengan markdown'],['Shelf-life limit','Batas shelf-life']],
   driver:['Margin Bridge (Rp)','Jembatan Margin (Rp)'], driverHint:['value at risk \u2192 recovered by markdown','nilai berisiko \u2192 diselamatkan markdown'],
   trend:['Top Markdown Actions','Aksi Markdown Teratas'], trendHint:['largest value at risk','nilai berisiko terbesar'],
   cat:['Value at Risk by Category','Nilai Berisiko per Kategori'], store:['Markdown Candidates by Store','Kandidat Markdown per Toko'],
   cluster:['Recoverable Value by Cluster','Nilai Terselamatkan per Cluster'], season:['Markdown Depth by Shelf-life','Kedalaman Markdown per Shelf-life'],
   seasonNote:['\ud83c\udff7\ufe0f Closer to expiry \u2192 deeper markdown to clear before write-off. Non-fresh cleared over ~14 days.','\ud83c\udff7\ufe0f Makin dekat expiry \u2192 markdown makin dalam agar habis sebelum write-off. Non-fresh dihabiskan ~14 hari.'],
   matrix:['Markdown & Repricing Register','Register Markdown & Repricing'], matrixHint:['ranked by value at risk \u00b7 click a row to drill','urut per nilai berisiko \u00b7 klik baris untuk drill'],
   sliders:[['Demand change','Perubahan demand'],['Extra markdown depth','Tambahan kedalaman markdown'],['Clearance duration','Durasi clearance'],['Supplier markdown support','Dukungan markdown supplier'],['Elasticity','Elastisitas'],['Competitor pressure','Tekanan kompetitor']],
   simCaption:['At-risk burn-down under levers','Burn-down stok berisiko dengan lever'],
   metrics:[['Recoverable value','Nilai terselamatkan','pm_recover'],['\u0394 vs base','\u0394 vs base','pm_dbase'],['Sell-through','Sell-through','pm_sellthru'],['Candidates','Kandidat','pm_cands']],
   scenC1:'Dem%', scenC2:'Mkdn%', scen:['Recover','\u0394vs','Sell'], scenDir:'higher', unit:'' },
 assort:{ name:['Assortment Optimization','Assortment Optimization'], sub:['Assortment Optimization \u00b7 Hero','Assortment Optimization \u00b7 Hero'], crumb:'Agent 6 of 8',
   forecast:['Cumulative Margin Uplift (optimized vs current)','Uplift Margin Kumulatif (optimal vs sekarang)'],
   legend:[['Current (baseline)','Sekarang (baseline)'],['Cumulative uplift','Uplift kumulatif'],['Range','Rentang']],
   driver:['Margin Bridge (Rp/yr)','Jembatan Margin (Rp/thn)'], driverHint:['delist tail + grow winners \u2192 net uplift','delist ekor + perbesar juara \u2192 uplift bersih'],
   trend:['Top Delist Candidates','Kandidat Delist Teratas'], trendHint:['lowest GMROI / velocity','GMROI / velocity terendah'],
   cat:['Delist Candidates by Category','Kandidat Delist per Kategori'], store:['Tail-SKU Share by Store','Porsi SKU Ekor per Toko'],
   cluster:['GMROI by Cluster','GMROI per Cluster'], season:['SKU Distribution by Performance Tier','Distribusi SKU per Tier Performa'],
   seasonNote:['\ud83e\uddec Star / Core = keep & grow. Slow / Tail = review & delist. Rationalize the long tail, reinvest space in winners.','\ud83e\uddec Star / Core = pertahankan & perbesar. Slow / Tail = review & delist. Rasionalkan long tail, alihkan ruang ke juara.'],
   matrix:['Assortment Action Register','Register Aksi Assortment'], matrixHint:['ranked by margin contribution \u00b7 click a row to drill','urut per kontribusi margin \u00b7 klik baris untuk drill'],
   sliders:[['Delist depth (tail)','Kedalaman delist (ekor)'],['Space reallocation','Realokasi ruang'],['Demand transfer','Transfer demand'],['GMROI threshold','Ambang GMROI'],['Grow investment','Investasi grow'],['Cannibalization','Kanibalisasi']],
   simCaption:['Optimized margin under levers','Margin optimal dengan lever'],
   metrics:[['Margin impact','Dampak margin','assort_impact'],['\u0394 vs base','\u0394 vs base','assort_dbase'],['Capital freed','Modal bebas','assort_capital'],['Delist','Delist','assort_delist']],
   scenC1:'Delist%', scenC2:'Realloc%', scen:['Impact','\u0394vs','Capital'], scenDir:'higher', unit:'' },
 ai:{ name:['AI Explanation & Summary','AI Explanation & Summary'], sub:['AI Explanation & Summary \u00b7 Hero','AI Explanation & Summary \u00b7 Hero'], crumb:'Agent 7 of 8',
   forecast:['Cumulative Value Captured Across the Pipeline','Nilai Kumulatif Terkumpul Sepanjang Pipeline'],
   legend:[['No AI (baseline)','Tanpa AI (baseline)'],['With AI Retail 360','Dengan AI Retail 360'],['Range','Rentang']],
   driver:['Value Contribution by Agent (Rp/yr)','Kontribusi Nilai per Agent (Rp/thn)'], driverHint:['where the money comes from','dari mana nilainya'],
   trend:['Pipeline Scorecard (Agent 1\u21926)','Scorecard Pipeline (Agent 1\u21926)'], trendHint:['headline per agent','headline per agent'],
   cat:['Value Opportunity by Category','Peluang Nilai per Kategori'], store:['Value Opportunity by Store','Peluang Nilai per Toko'],
   cluster:['Value Opportunity by Cluster','Peluang Nilai per Cluster'], season:['Confidence by Signal Source','Confidence per Sumber Sinyal'],
   seasonNote:['\ud83e\udde0 Summary reads live from every agent above \u2014 same shared engine, so the numbers reconcile end-to-end.','\ud83e\udde0 Ringkasan membaca langsung dari setiap agent di atas \u2014 engine yang sama, jadi angkanya konsisten end-to-end.'],
   matrix:['Decision & Explanation Log (end-to-end)','Log Keputusan & Penjelasan (end-to-end)'], matrixHint:['how each agent decided \u00b7 click a row to open that agent','bagaimana tiap agent memutuskan \u00b7 klik baris untuk buka agent'],
   sliders:[['Demand shift','Pergeseran demand'],['Service target','Target service'],['Promo intensity','Intensitas promo'],['Markdown intensity','Intensitas markdown'],['Assortment aggressiveness','Agresivitas assortment'],['Cost inflation','Inflasi biaya']],
   simCaption:['Total pipeline value under levers','Total nilai pipeline dengan lever'],
   metrics:[['Total value','Total nilai','ai_total'],['\u0394 vs base','\u0394 vs base','ai_dbase'],['Margin impact','Dampak margin','ai_margin'],['Service','Service','ai_service']],
   scenC1:'Dem%', scenC2:'Svc%', scen:['Value','\u0394vs','Margin'], scenDir:'higher', unit:'' }
};
const HANDOFF={
 df:{to:['Send to Replenishment Agent','Kirim ke Agent Replenishment'],hint:['hands forecast + order signal → Replenishment Agent','estafet forecast + sinyal order → Agent Replenishment'],rx:['rep']},
 inv:{to:['Route to Replenishment / Pricing','Teruskan ke Replenishment / Pricing'],hint:['handoff → Replenishment (PO) & Pricing (markdown)','estafet → Replenishment (PO) & Pricing (markdown)'],rx:['rep','pm']},
 rep:{to:['Release PO to D365 F&O','Rilis PO ke D365 F&O'],hint:['execute → D365 F&O (PurchTable) & track outcome','eksekusi → D365 F&O (PurchTable) & lacak hasil'],rx:[]},
 promo:{to:['Send to Pricing & Markdown Agent','Kirim ke Agent Pricing & Markdown'],hint:['handoff → Pricing & Markdown Agent (promo → price actions)','estafet → Agent Pricing & Markdown (promo → aksi harga)'],rx:['pm']},
 pm:{to:['Send delist candidates to Assortment Agent','Kirim kandidat delist ke Agent Assortment'],hint:['markdown expiry/overstock now; route slow-movers → Assortment Optimization','markdown expiry/overstock sekarang; slow-mover → Assortment Optimization'],rx:['assort']},
 assort:{to:['Publish assortment to D365 F&O','Publikasikan assortment ke D365 F&O'],hint:['delist tail & grow winners → D365 F&O (Released products) via approval','delist ekor & perbesar juara → D365 F&O (Released products) via approval'],rx:[]},
 ai:{to:['Publish executive summary','Publikasikan ringkasan eksekutif'],hint:['distribute the end-to-end board pack to leadership (reporting, not a D365 transaction)','distribusikan board pack end-to-end ke leadership (pelaporan, bukan transaksi D365)'],rx:[]}
};
function setTxt(el,en,id){ if(!el)return; el.setAttribute('data-en',en); el.setAttribute('data-id',id); el.textContent=(LANG==='id'?id:en); }
function applyLabels(key){ const L=LABELS[key]; const q=s=>document.querySelector(s);
  setTxt(q('.rail-brand .s'),L.sub[0],L.sub[1]); setTxt(q('.maintop h1'),L.name[0],L.name[1]);
  setTxt(q('[data-sec="forecast"] .t span[data-en]'),L.forecast[0],L.forecast[1]);
  const lg=document.querySelectorAll('[data-sec="forecast"] .legend .lg span[data-en]'); L.legend.forEach((v,i)=>{if(lg[i])setTxt(lg[i],v[0],v[1]);});
  setTxt(q('[data-sec="driver"] .t span[data-en]'),L.driver[0],L.driver[1]); setTxt(q('[data-sec="driver"] .hint'),L.driverHint[0],L.driverHint[1]);
  setTxt(q('[data-sec="trend"] .t span[data-en]'),L.trend[0],L.trend[1]); setTxt(q('[data-sec="trend"] .hint'),L.trendHint[0],L.trendHint[1]);
  setTxt(q('[data-sec="cat"] .t span[data-en]'),L.cat[0],L.cat[1]); setTxt(q('[data-sec="store"] .t span[data-en]'),L.store[0],L.store[1]);
  setTxt(q('[data-sec="cluster"] .t span[data-en]'),L.cluster[0],L.cluster[1]); setTxt(q('[data-sec="season"] .t span[data-en]'),L.season[0],L.season[1]);
  setTxt(q('[data-sec="season"] .chartbody .tiny.muted'),L.seasonNote[0],L.seasonNote[1]);
  setTxt(q('[data-sec="matrix"] .t span[data-en]'),L.matrix[0],L.matrix[1]); setTxt(G('matrixhint'),L.matrixHint[0],L.matrixHint[1]);
  const hf=HANDOFF[key]||HANDOFF.df; setTxt(q('[data-sec="action"] .panel-h .hint'),hf.hint[0],hf.hint[1]);
  const sl=document.querySelectorAll('[data-sec="sim"] .slider .sh span[data-en]'); L.sliders.forEach((v,i)=>{if(sl[i])setTxt(sl[i],v[0],v[1]);});
  setTxt(q('[data-sec="sim"] .simgrid > div:nth-child(2) .tiny.muted'),L.simCaption[0],L.simCaption[1]);
  const mk=document.querySelectorAll('[data-sec="sim"] .metrics4 .m .k'); const mb=[G('sim-order'),G('sim-delta'),G('sim-margin'),G('sim-svc')];
  L.metrics.forEach((v,i)=>{ if(mk[i])setTxt(mk[i],v[0],v[1]); if(mb[i])mb[i].setAttribute('data-fx',v[2]); });
}
function setAgent(key){ if(!SUF[key]){toast(T('This agent mockup is built next','Mockup agent ini dibangun berikutnya'));return;}
  state.agent=key;
  KPIDEFS=({df:KPIDEFS_DF,inv:KPIDEFS_INV,rep:KPIDEFS_REP,promo:KPIDEFS_PROMO,pm:KPIDEFS_PM,assort:KPIDEFS_ASSORT,ai:KPIDEFS_AI})[key]||KPIDEFS_DF;
  CHIPS=({df:CHIPS_DF,inv:CHIPS_INV,rep:CHIPS_REP,promo:CHIPS_PROMO,pm:CHIPS_PM,assort:CHIPS_ASSORT,ai:CHIPS_AI})[key]||CHIPS_DF;
  CHIPS_CH=({df:CHIPS_CH_DF,inv:CHIPS_CH_INV,rep:CHIPS_CH_REP,promo:CHIPS_CH_PROMO,pm:CHIPS_CH_PM,assort:CHIPS_CH_ASSORT,ai:CHIPS_CH_AI})[key]||CHIPS_CH_DF;
  scenarios.length=0; poOpen=false;
  applyLabels(key); renderAgentNav(); renderChips(); refreshAll(); runSim();
}
/* ========================================================= */
/* ================= REPLENISHMENT AGENT (shared invMetrics) ================= */
Object.assign(FX,{
 rep_reorderAfter:{t:['SKUs to reorder','SKU reorder'],f:'count( Position < ROP )',e:['SKUs at/below reorder point.','SKU di/bawah reorder point.']},
 rep_orderValue:{t:['Order value','Nilai order'],f:'Σ ( Max − Position ) × unit price',e:['Purchase value of the plan.','Nilai beli rencana.']},
 rep_fill:{t:['Fill rate','Fill rate'],f:'SKUs (Position ≥ ROP) ÷ total SKUs',e:['Share of SKUs above reorder point.','Porsi SKU di atas reorder point.']},
 rep_dOrderU:{t:['Δ Order units','Δ Unit order'],f:'( order units after ÷ base ) − 1',e:['Change in order units under levers.','Perubahan unit order di simulasi.']},
 rep_dOrderV:{t:['Δ Order value','Δ Nilai order'],f:'( order value after ÷ base ) − 1',e:['Change in buy value under levers.','Perubahan nilai beli di simulasi.']}
});
function computeK_REP(){
  const daily=genDaily();
  const list=activeSKUs().map(s=>({s,m:invMetrics(s)}));
  const reorder=list.filter(x=>x.m.position<x.m.rop);
  const orderUnits=reorder.reduce((a,x)=>a+Math.max(0,x.m.maxLevel-x.m.position),0);
  const orderValue=reorder.reduce((a,x)=>a+Math.max(0,x.m.maxLevel-x.m.position)*x.m.price,0);
  const inbound=list.reduce((a,x)=>a+x.m.openPOu,0);
  const covered=list.filter(x=>x.m.position>=x.m.rop).length;
  const fillRate=list.length?covered/list.length*100:100;
  const avgCover=list.length?list.reduce((a,x)=>a+x.m.dos,0)/list.length:0;
  return {reorderCount:reorder.length,orderUnits,orderValue,inbound,fillRate,avgCover,list,reorder,daily};
}
const KPIDEFS_REP=[
  {key:'reorderCount',color:'#D13438',lab:['SKUs to Reorder','SKU untuk Reorder'],fmt:k=>fmt(k.reorderCount),delta:k=>T('Position < ROP','Position < ROP'),dcls:()=>'down',
   f:'count( Position < ROP ) · Position = On Hand + Open PO',e:['SKUs at/below reorder point — order now.','SKU di/bawah reorder point — order sekarang.'],val:k=>k.reorderCount},
  {key:'orderUnits',color:'#0078D4',lab:['Order Units','Unit Order'],fmt:k=>fmt(k.orderUnits)+' u',delta:k=>T('to Max','ke Max'),dcls:()=>'',
   f:'Σ max(0, Max − Position) for reorder SKUs',e:['Total units to bring stock up to Max.','Total unit untuk isi stok sampai Max.'],val:k=>k.orderUnits},
  {key:'orderValue',color:'#107C41',lab:['Order Value','Nilai Order'],fmt:k=>'Rp '+fmt(k.orderValue),delta:k=>T('buy value','nilai beli'),dcls:()=>'',
   f:'Σ ( Max − Position ) × unit price',e:['Purchase value of the replenishment plan.','Nilai beli rencana replenishment.'],val:k=>k.orderValue},
  {key:'inbound',color:'#0A9ED4',lab:['Inbound (Open PO)','Inbound (Open PO)'],fmt:k=>fmt(k.inbound)+' u',delta:k=>T('already on order','sudah dipesan'),dcls:()=>'up',
   f:'Σ Open PO units (in scope)',e:['Units already on order arriving soon.','Unit yang sudah dipesan, segera tiba.'],val:k=>k.inbound},
  {key:'fillRate',color:'#008575',lab:['Fill Rate','Fill Rate'],fmt:k=>k.fillRate.toFixed(1)+'%',delta:k=>T('covered ≥ ROP','tercukupi ≥ ROP'),dcls:()=>'up',
   f:'SKUs (Position ≥ ROP) ÷ total SKUs',e:['Share of SKUs above reorder point.','Porsi SKU di atas reorder point.'],val:k=>k.fillRate},
  {key:'avgCover',color:'#5C2D91',lab:['Avg Days Cover','Rata Hari Cover'],fmt:k=>k.avgCover.toFixed(1)+' d',delta:k=>T('target 7–21d','target 7–21h'),dcls:()=>'',
   f:'mean( Position ÷ ADS )',e:['Average days of cover across SKUs.','Rata-rata hari cover antar SKU.'],val:k=>k.avgCover},
];
function renderForecast_REP(){
  const list=activeSKUs().map(invMetrics);
  const pos=list.reduce((a,m)=>a+m.position,0);
  const ads=Math.max(1,list.reduce((a,m)=>a+m.ads,0));
  const rop=list.reduce((a,m)=>a+m.rop,0);
  const inbound=list.reduce((a,m)=>a+m.openPOu,0);
  const avgLead=Math.round(activeSKUs().reduce((a,s)=>a+s.lead,0)/Math.max(1,activeSKUs().length));
  const days=Math.min(70,state.horizon*7);
  const r=rng(hashScope());const hist=[],fc=[],band=[],labels=[];
  let p=pos+ads*5;
  for(let i=42;i>0;i--){p-=ads*(0.6+r()*0.8);if(i%7===0)p+=ads*4;p=Math.max(ads,p);hist.push(Math.round(p));labels.push('D-'+i);}
  let q=pos;
  for(let i=0;i<days;i++){q-=ads;if(i===avgLead)q+=inbound;if(q<rop*0.35)q+=ads*7;q=Math.max(0,q);fc.push(Math.round(q));const g=Math.min(0.3,0.05+0.0038*i);band.push([Math.round(q*(1-g)),Math.round(q*(1+g))]);labels.push('D+'+(i+1));}
  lineChart('chart-forecast',{hist,fc,band,labels});
  const k=computeK_REP();
  G('forenote').textContent=T(`Replenishment coverage · reorder at ROP · horizon ${state.horizon}wk · scope: ${scopeShort()}`,`Cakupan replenishment · reorder di ROP · horizon ${state.horizon}mgg · scope: ${scopeShort()}`);
  G('forecastStats').innerHTML=`<div class="m"><div class="k">${T('SKUs to reorder','SKU reorder')}</div><b data-fx="rep_reorderAfter">${fmt(k.reorderCount)}</b></div>
    <div class="m"><div class="k">${T('Order units','Unit order')}</div><b data-fx="actQty">${fmt(k.orderUnits)} u</b></div>
    <div class="m"><div class="k">${T('Order value','Nilai order')}</div><b data-fx="rep_orderValue">Rp ${fmt(k.orderValue)}</b></div>
    <div class="m"><div class="k">${T('Inbound (Open PO)','Inbound')}</div><b data-fx="inbound">${fmt(k.inbound)} u</b></div>
    <div class="m"><div class="k">${T('Fill rate','Fill rate')}</div><b data-fx="rep_fill">${k.fillRate.toFixed(1)}%</b></div>`;
}
function renderDriver_REP(){
  const g=buildPOgroups();
  const val=k=>g[k].reduce((a,r)=>{const s=SKUS.find(x=>x.id===r.sku);return a+r.qty*(s?s.price:0);},0);
  const d=val('direct'),f=val('flow'),c=val('cross');
  waterfall('chart-driver',[
    {label:T('Direct Store','Direct Store'),value:Math.round(d),color:'#0a68b8'},
    {label:'Flow-Through',value:Math.round(f),color:'#5C2D91'},
    {label:'Cross-Dock',value:Math.round(c),color:'#C77700'},
    {label:T('Total order','Total order'),value:Math.round(d+f+c),color:'#0078D4',total:true},
  ]);
}
function renderTrend_REP(){
  const pool=activeSKUs().map(s=>({s,m:invMetrics(s)})).filter(x=>x.m.position<x.m.rop).map(x=>({s:x.s,m:x.m,gap:x.m.rop-x.m.position})).sort((a,b)=>b.gap-a.gap).slice(0,5);
  G('trendlist').innerHTML=pool.map(x=>`<div class="trow"><span class="fireicon">🛒</span>
    <div><div class="tn">${x.s.name}</div><div class="tc">${x.s.cat} · Pos ${fmt(x.m.position)} / ROP ${fmt(x.m.rop)} · ${T('order','order')} ${fmt(Math.max(0,x.m.maxLevel-x.m.position))}</div></div>
    <div class="tu down">−${fmt(x.gap)}</div></div>`).join('')||`<div class="tiny muted">${T('No SKU below ROP in scope.','Tidak ada SKU di bawah ROP.')}</div>`;
}
function renderCat_REP(){
  const data=CATS.map(c=>{let v=0;SKUS.filter(s=>s.catId===c.id).forEach(s=>{const m=invMetrics(s);if(m.position<m.rop)v+=Math.max(0,m.maxLevel-m.position)*m.price;});
    return {label:c.name,value:Math.round(v),color:CCOLOR[c.id],fx:'Σ (Max−Position)×price for reorder SKUs in category',
      onclick:()=>{state.itemMode='cat';state.cats=new Set([c.id]);syncSegs();refreshAll();toast('🗂️ '+T('Filtered: ','Filter: ')+c.name);}};});
  barChart('chart-cat',data,{pb:52});
}
function renderStore_REP(){return renderStore_INV();}
function renderCluster_REP(){
  const cc={Premium:'#5C2D91','Urban Mall':'#0078D4',Suburban:'#008575',Resort:'#C77700'};
  const data=CLUSTERS.map(cl=>{const stores=STORES.filter(s=>s.cluster===cl);let v=0;
    activeSKUs().forEach(s=>{stores.forEach(store=>{const seas=(s.fresh?SEAS_FRESH:SEAS_DRY)[MONTH];const ads=s.base*seas*store.size;const pos=(s.base*s.onHandDays*stockFactor(s)*store.size+s.openPO*(store.size/ALLSIZES))*store.health;const rop=ads*(s.lead+s.safety);const max=ads*(s.lead+s.safety+4);if(pos<rop)v+=Math.max(0,max-pos)*s.price;});});
    return {label:cl,value:Math.round(v),color:cc[cl],fx:'Σ order value (Max−Position)×price in cluster',
      onclick:()=>{state.storeMode='sel';state.stores=new Set(STORES.filter(s=>s.cluster===cl).map(s=>s.id));syncSegs();refreshAll();toast('🧭 '+T('Cluster: ','Cluster: ')+cl);}};});
  barChart('chart-cluster',data,{pb:40});
}
function renderSeason_REP(){
  const buckets=[['1d',1],['2d',2],['3d',3],['4–5d',5],['6–7d',7],['>7d',999]];const vals=buckets.map(()=>0);
  activeSKUs().map(s=>({s,m:invMetrics(s)})).filter(x=>x.m.position<x.m.rop).forEach(({s,m})=>{const lead=s.lead+(s.fresh?0:1);let bi=buckets.findIndex(bk=>lead<=bk[1]);if(bi<0)bi=buckets.length-1;vals[bi]+=Math.max(0,m.maxLevel-m.position);});
  const cols=['#0a68b8','#0078D4','#0A9ED4','#5C2D91','#C77700','#cfe0f3'];
  const data=buckets.map((bk,i)=>({label:bk[0],value:Math.round(vals[i]),color:cols[i],fx:'Σ order units by expected delivery lead'}));
  barChart('chart-season',data,{h:196,pb:26});
}
function renderMatrix_REP(){
  const storeLbl=(state.storeMode==='sel'&&state.stores.size)?(state.stores.size===1?STORES.find(s=>state.stores.has(s.id)).name.replace('HERO ',''):state.stores.size+' stores'):T('All','Semua');
  const rlbl={direct:'Direct',flow:'Flow-Through',cross:'Cross-Dock'};
  const rows=activeSKUs().map(s=>({s,m:invMetrics(s)})).filter(x=>x.m.position<x.m.rop).map(x=>({s:x.s,m:x.m,order:Math.max(0,x.m.maxLevel-x.m.position),route:poClassify(x.s)})).sort((a,b)=>(b.m.rop-b.m.position)-(a.m.rop-a.m.position)).slice(0,14);
  G('chart-matrix').innerHTML=`<table class="tbl"><thead><tr>
    <th>SKU</th><th>Item</th><th>Category</th><th>Store</th><th>ADS</th><th>On Hand</th><th>Open PO</th><th>Position</th><th>ROP</th><th>Max</th><th>Order</th><th>Route</th></tr></thead><tbody>
    ${rows.map(({s,m,order,route})=>`<tr style="cursor:pointer" onclick="drillSku('${s.id}')">
      <td>${s.id}</td><td style="text-align:left">${s.name}</td>
      <td style="text-align:left"><span class="badge" style="background:${CCOLOR[s.catId]}22;color:${CCOLOR[s.catId]}">${s.cat}</span></td>
      <td style="text-align:left">${storeLbl}</td>
      <td data-fx="fads"><b style="color:#5C2D91">${fmt(m.ads)}</b>/d</td>
      <td data-fx="onhandU">${fmt(m.onHandU)}</td><td data-fx="openpoU">${fmt(m.openPOu)}</td>
      <td data-fx="position" class="pos-low">${fmt(m.position)}</td><td data-fx="ropBox">${fmt(m.rop)}</td><td data-fx="maxv">${fmt(m.maxLevel)}</td>
      <td data-fx="actQty"><b>${fmt(order)}</b></td>
      <td style="text-align:left"><span class="route ${route}">${rlbl[route]}</span></td></tr>`).join('')}
  </tbody></table>`;
}
function runSim_REP(){
  const dem=1+state.sim.price/100, moq=state.sim.promo/100, inboundBoost=1+state.sim.seas/100, transferOut=state.sim.viral/100, lead=state.sim.lead, safe=state.sim.safe;
  const list=activeSKUs().map(invMetrics);
  let reorder=0,orderU=0,orderV=0,covered=0;
  list.forEach(m=>{
    const pos=m.position*inboundBoost*(1-transferOut*0.1);
    const ads=Math.max(1,m.ads*dem);
    const rop=Math.round(ads*(lead+safe)); const max=Math.round(ads*(lead+safe+4));
    if(pos<rop){reorder++;let q=Math.max(0,max-pos);if(moq>0){const step=Math.max(1,Math.round(ads*moq*3));q=Math.ceil(q/step)*step;}orderU+=q;orderV+=q*m.price;}else covered++;
  });
  const fill=list.length?covered/list.length*100:100;
  const pos0=list.reduce((a,m)=>a+m.position,0)*inboundBoost;const ads0=Math.max(1,list.reduce((a,m)=>a+m.ads,0)*dem);const rop0=list.reduce((a,m)=>a+m.rop,0)*dem;const inb=list.reduce((a,m)=>a+m.openPOu,0)*inboundBoost;
  const hist=[],fc=[],band=[],labels=[];let p=pos0+ads0*4;
  for(let i=14;i>0;i--){p-=ads0*0.7;if(i%7===0)p+=ads0*4;p=Math.max(ads0,p);hist.push(Math.round(p));labels.push('D-'+i);}
  let q=pos0;for(let i=0;i<14;i++){q-=ads0;if(i===3)q+=inb;if(q<rop0*0.35)q+=ads0*7;q=Math.max(0,q);fc.push(Math.round(q));const g=Math.min(0.3,0.05+0.01*i);band.push([Math.round(q*(1-g)),Math.round(q*(1+g))]);labels.push('D+'+(i+1));}
  lineChart('chart-sim',{hist,fc,band,labels},{h:180});
  const baseK=computeK_REP();
  const dU=baseK.orderUnits>0?((orderU/baseK.orderUnits)-1)*100:0;
  const dV=baseK.orderValue>0?((orderV/baseK.orderValue)-1)*100:0;
  simRun={order:reorder,dDem:dU,dMgn:dV,svc:fill,series:fc};
  G('sim-order').textContent=fmt(reorder)+' SKU';
  const dd=G('sim-delta');dd.textContent=pct(dU);dd.className=dU<=0?'up':'down';
  const dm=G('sim-margin');dm.textContent=pct(dV);dm.className=dV<=0?'up':'down';G('sim-svc').textContent=fill.toFixed(1)+'%';
}
function renderAction_REP(){
  const k=computeK_REP();
  const stTag={pending:'st-pending',approved:'st-approved',rejected:'st-rejected',cancelled:'st-cancelled',reopened:'st-reopened',sent:'st-sent'}[actionState];
  const stTxt={pending:T('Pending','Menunggu'),approved:'Approved',rejected:'Rejected',cancelled:T('Cancelled','Dibatalkan'),reopened:'Reopened',sent:T('Sent →','Terkirim →')}[actionState];
  G('actionbody').innerHTML=`
    <div class="action-card"><div class="ah"><span class="pri high">${T('HIGH PRIORITY','PRIORITAS TINGGI')}</span>
      <b>${T('Release replenishment POs before 03:00 cut-off','Rilis PO replenishment sebelum cut-off 03:00')}</b><span class="status-tag ${stTag}">${stTxt}</span></div>
      <div class="tiny muted">${T('Agent proposes','Agent mengusulkan')} <b style="color:#0078D4">${fmt(k.reorderCount)} PO</b> · <b>${fmt(k.orderUnits)} u</b> · <b>Rp ${fmt(k.orderValue)}</b> ${T('across 3 routes.','di 3 rute.')}</div>
      <div class="impact">
        <div><span class="muted tiny">${T('SKUs to reorder','SKU reorder')}</span><b data-fx="rep_reorderAfter">${fmt(k.reorderCount)}</b></div>
        <div><span class="muted tiny">${T('Order units','Unit order')}</span><b data-fx="actQty">${fmt(k.orderUnits)} u</b></div>
        <div><span class="muted tiny">${T('Order value','Nilai order')}</span><b data-fx="rep_orderValue">Rp ${fmt(k.orderValue)}</b></div>
        <div><span class="muted tiny">Fill rate</span><b data-fx="rep_fill">${k.fillRate.toFixed(1)}%</b></div></div>
      <div class="agentic-row">
        <button class="abtn approve" onclick="agentic('approved')">✔ ${T('Approve','Setujui')}</button>
        <button class="abtn reject" onclick="agentic('rejected')">✕ ${T('Reject','Tolak')}</button>
        <button class="abtn cancel" onclick="agentic('cancelled')">⊘ ${T('Cancel','Batal')}</button>
        <button class="abtn reopen" onclick="agentic('reopened')">↻ ${T('Reopen','Buka lagi')}</button>
        <button class="btn indigo sm" style="margin-left:auto" onclick="togglePO()">📦 ${T('Generate PO (by route)','Buat PO (per rute)')}</button></div></div>
    <div id="po-preview"></div>`;
}
function aiReply_REP(q){const k=computeK_REP();const ql=q.toLowerCase();const ch=CHALLENGE;
  if(ql.includes('lead')&&ch){
    addMsg('ai',`${T('If vendor lead time doubles, more SKUs cross ROP and order units jump:','Kalau lead time vendor 2x, makin banyak SKU lewat ROP dan unit order melonjak:')}
      <div class="calcbox">ROP = ADS × (Lead + Safety)
lead 2× raises ROP → reorder count & order units up
now: ${fmt(k.reorderCount)} SKU · ${fmt(k.orderUnits)} u</div>
      ${T('Recommend safety-stock buffer for long-lead vendors, or dual-source.','Sarankan buffer safety-stock untuk vendor lead panjang, atau dual-source.')}`,true);
  }else if(ql.includes('reorder')||ql.includes('what to')||ql.includes('order')){
    const rows=k.reorder.slice().sort((a,b)=>(b.m.rop-b.m.position)-(a.m.rop-a.m.position)).slice(0,4);
    addMsg('ai',`${T('Reorder now (Position below ROP):','Reorder sekarang (Position di bawah ROP):')} <b>${fmt(k.reorderCount)} SKU</b> · <b>${fmt(k.orderUnits)} u</b>
      <div class="calcbox">Order = max(0, Max − Position) · Max = ADS × (Lead+Safety+Review)</div>
      <table class="mini-table"><thead><tr><th>Item</th><th>Pos</th><th>ROP</th><th>Order</th></tr></thead><tbody>
      ${rows.map(x=>`<tr><td>${x.s.name}</td><td>${fmt(x.m.position)}</td><td>${fmt(x.m.rop)}</td><td>${fmt(Math.max(0,x.m.maxLevel-x.m.position))}</td></tr>`).join('')||('<tr><td colspan=4>'+T('None','Tidak ada')+'</td></tr>')}</tbody></table>
      ${ch?T('<br>Challenge: check MOQ and truck fill — tiny orders may not be economical to ship.','<br>Challenge: cek MOQ dan muatan truk — order kecil bisa tak ekonomis dikirim.'):''}`,ch);
  }else if(ql.includes('value')||ql.includes('cost')||ql.includes('budget')){
    addMsg('ai',`${T('Replenishment buy value:','Nilai beli replenishment:')} <b>Rp ${fmt(k.orderValue)}</b>
      <div class="calcbox">Order value = Σ (Max − Position) × unit price</div>
      ${T('Open the PO to see the split: Direct / Flow-Through / Cross-Dock.','Buka PO untuk lihat pembagian: Direct / Flow-Through / Cross-Dock.')}`,ch);
  }else if(ql.includes('route')||ql.includes('po')||ql.includes('cross')||ql.includes('flow')){
    addMsg('ai',`${T('PO is split into 3 fulfilment routes: Direct Store (fresh), DC Flow-Through, Cross-Docking.','PO dipecah 3 rute: Direct Store (fresh), DC Flow-Through, Cross-Docking.')}
      <div style="margin-top:7px"><button class="btn indigo sm" onclick="togglePO();document.querySelector('[data-sec=action]').scrollIntoView({behavior:'smooth'})">📦 ${T('Open PO','Buka PO')}</button></div>`,ch);
  }else if(ql.includes('fill')||ql.includes('service')){
    addMsg('ai',`${T('Fill rate','Fill rate')} = <b>${k.fillRate.toFixed(1)}%</b>
      <div class="calcbox">Fill = SKUs (Position ≥ ROP) ÷ total SKUs</div>
      ${T('Raise safety stock or inbound to lift fill rate — see What-If.','Naikkan safety stock atau inbound untuk menaikkan fill rate — lihat What-If.')}`,ch);
  }else if(ql.includes('explain')){
    addMsg('ai',T('Hover any number to see its formula, inputs and value. Every answer shows the math.','Arahkan kursor ke angka mana pun untuk lihat formula, input, dan nilainya. Tiap jawaban ada hitungannya.'),ch);
  }else{
    addMsg('ai',T('I can tell you what to reorder, order units & value, fill rate, PO routes, and lead-time risk. Turn on Challenge mode to stress-test.','Saya bisa jelaskan apa yang perlu direorder, unit & nilai order, fill rate, rute PO, dan risiko lead-time. Nyalakan Challenge mode untuk stress-test.'),ch);
  }
}
const CHIPS_REP=[['What should I reorder now?','Apa yang perlu direorder sekarang?',0],['Replenishment buy value','Nilai beli replenishment',0],['Show PO by route','Tampilkan PO per rute',0],['Fill rate & how to lift it','Fill rate & cara menaikkan',0]];
const CHIPS_CH_REP=[['Challenge: what if lead time doubles?','Challenge: kalau lead time 2x?',1],['Challenge tiny orders vs MOQ','Tantang order kecil vs MOQ',1],['Stress-test a demand spike','Stress-test lonjakan demand',1]];
/* ================= END REPLENISHMENT ================= */
/* ================= PROMOTION EFFECTIVENESS AGENT (shared baseline) ================= */
Object.assign(FX,{
 promo_active:{t:['Active Promo SKUs','SKU Promo Aktif'],f:'count( SKU on promotion in scope )',e:['SKUs currently on an active promotion.','SKU yang sedang promo aktif.']},
 promo_uplift:{t:['Promo Uplift','Uplift Promo'],f:'Σ(uplift × ADS) ÷ Σ ADS  (weighted)',e:['Weighted incremental demand from promotions.','Rata-rata tertimbang demand tambahan dari promo.']},
 promo_incrM:{t:['Incremental Margin','Margin Inkremental'],f:'Σ ( incr GM − baseline give-away + supplier funding )',e:['Net extra margin generated by the promo plan.','Margin bersih tambahan dari rencana promo.']},
 promo_roi:{t:['Promo ROI','ROI Promo'],f:'Σ incremental margin ÷ Σ net promo cost',e:['Return per rupiah of net promo spend. >1 = profitable.','Imbal hasil per rupiah biaya promo bersih. >1 = untung.']},
 promo_cannib:{t:['Cannibalization','Kanibalisasi'],f:'avg share of uplift taken from other SKUs',e:['Portion of uplift that is not truly incremental.','Porsi uplift yang bukan benar-benar tambahan.']},
 promo_funded:{t:['Supplier Funding','Funding Supplier'],f:'avg supplier-funded share of the discount',e:['Share of discount cost paid by suppliers.','Porsi biaya diskon yang ditanggung supplier.']},
 promo_dbase:{t:['Δ vs base','Δ vs base'],f:'( scenario incr margin ÷ base incr margin ) − 1',e:['Change in incremental margin under levers.','Perubahan margin inkremental di simulasi.']},
 discPct:{t:['Discount depth','Kedalaman diskon'],f:'1 − promo price ÷ regular price',e:['Depth of the promotional discount.','Kedalaman diskon promo.']},
 upliftCell:{t:['Uplift','Uplift'],f:'promoted demand ÷ baseline − 1',e:['Incremental demand for this SKU.','Demand tambahan untuk SKU ini.']},
 roiCell:{t:['ROI','ROI'],f:'net incremental margin ÷ net promo cost',e:['Profitability of this promo.','Profitabilitas promo ini.']},
 fundedCell:{t:['Funded','Funded'],f:'supplier-funded share of discount',e:['Supplier-funded portion.','Porsi ditanggung supplier.']},
 incrMCell:{t:['Incr Margin','Margin Inkremental'],f:'incr GM − baseline give-away + funding',e:['Net incremental margin for this SKU.','Margin inkremental bersih SKU ini.']}
});
function promoMetrics(s){
  const base=invMetrics(s);const ads=base.ads;const idn=parseInt(s.id.slice(4))||1;
  const active=!!s.promo;
  const si=storeIdx();
  const disc=active?(0.06+((idn*13)%14)/100):0;                 // 6–19% off
  const uplift=active?((0.50+((idn*29)%80)/100+(s.viral?0.15:0))*si):0; // store-responsive
  const cannib=active?Math.min(0.5,(0.08+((idn*7)%12)/100)*(2-si)):0;   // better stores cannibalize less
  const funded=active?Math.min(0.9,(0.40+((idn*17)%45)/100)*(0.6+0.4*si)):0;
  const period=14, baselineFactor=0.75;                          // 75% of baseline is price-driven markdown
  const price=s.price, cost=price*(1-s.marginPct), promoPrice=price*(1-disc);
  const baseUnits=ads*period, incrU=ads*uplift*period*(1-cannib);
  const incrGM=incrU*(promoPrice-cost);                          // margin on incremental units (can be <0 if deep)
  const grossMarkdown=baseUnits*(price-promoPrice)*baselineFactor;
  const funding=grossMarkdown*funded;
  const netCost=Math.max(0,grossMarkdown-funding);              // retailer's net markdown outlay
  const incrMargin=incrGM-netCost;
  const roi=incrGM/Math.max(1,netCost);
  return {ads,active,disc,uplift,cannib,funded,price,cost,promoPrice,period,incrU:Math.round(incrU),incrGM:Math.round(incrGM),grossMarkdown:Math.round(grossMarkdown),funding:Math.round(funding),incrMargin:Math.round(incrMargin),promoCost:Math.round(netCost),roi};
}
function computeK_PROMO(){
  const daily=genDaily();
  const list=activeSKUs().map(s=>({s,m:promoMetrics(s)}));
  const active=list.filter(x=>x.m.active);
  const wsum=active.reduce((a,x)=>a+x.m.ads,0)||1;
  const upliftAvg=active.reduce((a,x)=>a+x.m.uplift*x.m.ads,0)/wsum*100;
  const incrGMtot=active.reduce((a,x)=>a+x.m.incrGM,0);
  const promoCost=active.reduce((a,x)=>a+x.m.promoCost,0);
  const incrMargin=incrGMtot-promoCost;
  const roi=incrGMtot/Math.max(1,promoCost);
  const cannibAvg=active.length?active.reduce((a,x)=>a+x.m.cannib,0)/active.length*100:0;
  const fundedAvg=active.length?active.reduce((a,x)=>a+x.m.funded,0)/active.length*100:0;
  return {activeCount:Math.max(0,Math.round(active.length*storeIdx())),upliftAvg,incrMargin,roi,cannibAvg,fundedAvg,promoCost,list,active,daily};
}
const KPIDEFS_PROMO=[
  {key:'activeCount',color:'#C77700',lab:['Active Promo SKUs','SKU Promo Aktif'],fmt:k=>fmt(k.activeCount),delta:k=>T('on promotion','sedang promo'),dcls:()=>'',
   f:'count( SKU on promotion in scope )',e:['SKUs currently on an active promotion.','SKU yang sedang promo aktif.'],val:k=>k.activeCount},
  {key:'upliftAvg',color:'#107C41',lab:['Promo Uplift','Uplift Promo'],fmt:k=>'+'+k.upliftAvg.toFixed(1)+'%',delta:k=>T('weighted','tertimbang'),dcls:()=>'up',
   f:'Σ(uplift × ADS) ÷ Σ ADS',e:['Weighted incremental demand from promos.','Rata-rata tertimbang demand tambahan.'],val:k=>k.upliftAvg},
  {key:'incrMargin',color:'#0078D4',lab:['Incremental Margin','Margin Inkremental'],fmt:k=>'Rp '+fmt(k.incrMargin),delta:k=>T('net extra','tambahan bersih'),dcls:()=>'up',
   f:'Σ ( incr GM − baseline give-away + funding )',e:['Net extra margin from the promo plan.','Margin bersih tambahan dari rencana promo.'],val:k=>k.incrMargin},
  {key:'roi',color:'#008575',lab:['Promo ROI','ROI Promo'],fmt:k=>k.roi.toFixed(2)+'x',delta:k=>k.roi>=1?T('profitable','untung'):T('below 1x','di bawah 1x'),dcls:k=>k.roi>=1?'up':'down',
   f:'Σ incremental margin ÷ Σ net promo cost',e:['Return per rupiah of net promo spend.','Imbal hasil per rupiah biaya promo bersih.'],val:k=>k.roi},
  {key:'cannibAvg',color:'#F43F6E',lab:['Cannibalization','Kanibalisasi'],fmt:k=>k.cannibAvg.toFixed(1)+'%',delta:k=>T('of uplift','dari uplift'),dcls:()=>'down',
   f:'avg share of uplift taken from other SKUs',e:['Uplift that is not truly incremental.','Uplift yang bukan tambahan sejati.'],val:k=>k.cannibAvg},
  {key:'fundedAvg',color:'#5C2D91',lab:['Supplier Funding','Funding Supplier'],fmt:k=>k.fundedAvg.toFixed(1)+'%',delta:k=>T('of discount','dari diskon'),dcls:()=>'up',
   f:'avg supplier-funded share of the discount',e:['Discount cost covered by suppliers.','Biaya diskon yang ditanggung supplier.'],val:k=>k.fundedAvg},
];
function renderForecast_PROMO(){
  const list=activeSKUs().map(promoMetrics);
  const base=Math.max(1,list.reduce((a,m)=>a+m.ads,0));
  const wsum=list.filter(m=>m.active).reduce((a,m)=>a+m.ads,0)||1;
  const up=list.filter(m=>m.active).reduce((a,m)=>a+m.uplift*m.ads,0)/wsum;
  const days=Math.min(70,state.horizon*7);const period=14;
  const r=rng(hashScope());const hist=[],fc=[],band=[],labels=[];
  for(let i=42;i>0;i--){const dow=DOW[(999-i)%7];hist.push(Math.round(base*dow*(0.92+r()*0.16)));labels.push('D-'+i);}
  for(let i=0;i<days;i++){const dow=DOW[i%7];const boost=i<period?up:Math.max(0,up*(1-(i-period)/7));const v=Math.round(base*dow*(1+boost));fc.push(v);const g=Math.min(0.3,0.05+0.0038*i);band.push([Math.round(v*(1-g)),Math.round(v*(1+g))]);labels.push('D+'+(i+1));}
  lineChart('chart-forecast',{hist,fc,band,labels});
  const k=computeK_PROMO();
  G('forenote').textContent=T(`Baseline vs promoted demand · ${period}-day campaign · horizon ${state.horizon}wk · scope: ${scopeShort()}`,`Demand baseline vs promo · kampanye ${period} hari · horizon ${state.horizon}mgg · scope: ${scopeShort()}`);
  G('forecastStats').innerHTML=`<div class="m"><div class="k">${T('Active promos','Promo aktif')}</div><b data-fx="promo_active">${fmt(k.activeCount)}</b></div>
    <div class="m"><div class="k">${T('Uplift','Uplift')}</div><b data-fx="promo_uplift">+${k.upliftAvg.toFixed(1)}%</b></div>
    <div class="m"><div class="k">${T('Incr margin','Margin inkr')}</div><b data-fx="promo_incrM">Rp ${fmt(k.incrMargin)}</b></div>
    <div class="m"><div class="k">ROI</div><b data-fx="promo_roi">${k.roi.toFixed(2)}x</b></div>
    <div class="m"><div class="k">${T('Funding','Funding')}</div><b data-fx="promo_funded">${k.fundedAvg.toFixed(0)}%</b></div>`;
}
function renderDriver_PROMO(){
  const list=activeSKUs().map(promoMetrics).filter(m=>m.active);
  const incrGM=list.reduce((a,m)=>a+m.incrGM,0);
  const markdown=list.reduce((a,m)=>a+m.grossMarkdown,0);
  const funding=list.reduce((a,m)=>a+m.funding,0);
  const net=incrGM-markdown+funding;
  barChart('chart-driver',[
    {label:T('Incr GM','GM Inkr'),value:Math.round(incrGM),color:'#107C41',fx:'gross margin on incremental units'},
    {label:T('Markdown','Markdown'),value:Math.round(markdown),color:'#F43F6E',fx:'give-away on baseline units (×0.75)'},
    {label:T('Funding','Funding'),value:Math.round(funding),color:'#5C2D91',fx:'supplier-funded share of markdown'},
    {label:T('Net margin','Margin bersih'),value:Math.round(Math.abs(net)),color:net>=0?'#0078D4':'#D13438',fx:'incr GM − markdown + funding'},
  ],{pb:40});
}
function renderTrend_PROMO(){
  const pool=activeSKUs().map(s=>({s,m:promoMetrics(s)})).filter(x=>x.m.active).sort((a,b)=>b.m.roi-a.m.roi).slice(0,5);
  G('trendlist').innerHTML=pool.map(x=>`<div class="trow"><span class="fireicon">🏷️</span>
    <div><div class="tn">${x.s.name}</div><div class="tc">${x.s.cat} · ${(x.m.disc*100).toFixed(0)}% off · +${(x.m.uplift*100).toFixed(0)}% uplift</div></div>
    <div class="tu ${x.m.roi>=1?'up':'down'}">${x.m.roi.toFixed(2)}x</div></div>`).join('')||`<div class="tiny muted">${T('No active promo in scope.','Tidak ada promo aktif di scope.')}</div>`;
}
function renderCat_PROMO(){
  const data=CATS.map(c=>{let v=0;SKUS.filter(s=>s.catId===c.id).forEach(s=>{const m=promoMetrics(s);if(m.active)v+=m.incrMargin;});
    return {label:c.name,value:Math.round(v),color:CCOLOR[c.id],fx:'Σ incremental margin for active promos in category',
      onclick:()=>{state.itemMode='cat';state.cats=new Set([c.id]);syncSegs();refreshAll();toast('🗂️ '+T('Filtered: ','Filter: ')+c.name);}};});
  barChart('chart-cat',data,{pb:52});
}
function renderStore_PROMO(){
  const totalIncr=activeSKUs().map(promoMetrics).filter(m=>m.active).reduce((a,m)=>a+m.incrMargin,0);
  const sf=storeFactor()||1;
  const data=STORES.map(st=>({label:st.name.replace('HERO ',''),value:Math.round(totalIncr*st.size/sf),color:'#0078D4',fx:'incremental margin scaled by store demand size',
    onclick:()=>{state.storeMode='sel';state.stores=new Set([st.id]);syncSegs();refreshAll();toast('🏪 '+T('Filtered: ','Filter: ')+st.name);}})).sort((a,b)=>b.value-a.value);
  hbarChart('chart-store',data);
}
function renderCluster_PROMO(){
  const cc={Premium:'#5C2D91','Urban Mall':'#0078D4',Suburban:'#008575',Resort:'#C77700'};
  const totalIncr=activeSKUs().map(promoMetrics).filter(m=>m.active).reduce((a,m)=>a+m.incrMargin,0);const sf=storeFactor()||1;
  const data=CLUSTERS.map(cl=>{const sz=STORES.filter(s=>s.cluster===cl).reduce((a,s)=>a+s.size,0);
    return {label:cl,value:Math.round(totalIncr*sz/sf),color:cc[cl],fx:'incremental margin scaled by cluster demand size',
      onclick:()=>{state.storeMode='sel';state.stores=new Set(STORES.filter(s=>s.cluster===cl).map(s=>s.id));syncSegs();refreshAll();toast('🧭 '+T('Cluster: ','Cluster: ')+cl);}};});
  barChart('chart-cluster',data,{pb:40});
}
function renderSeason_PROMO(){
  const buckets=[['≤10%',0.10],['10–15%',0.15],['15–20%',0.20],['20–25%',0.25],['25–30%',0.30],['>30%',1]];const vals=buckets.map(()=>0);
  activeSKUs().map(promoMetrics).filter(m=>m.active).forEach(m=>{let bi=buckets.findIndex(b=>m.disc<=b[1]);if(bi<0)bi=buckets.length-1;vals[bi]+=m.incrMargin;});
  const cols=['#0A9ED4','#0078D4','#107C41','#C77700','#F43F6E','#5C2D91'];
  const data=buckets.map((b,i)=>({label:b[0],value:Math.round(vals[i]),color:cols[i],fx:'Σ incremental margin by discount depth bucket'}));
  barChart('chart-season',data,{h:196,pb:26});
}
function renderMatrix_PROMO(){
  const storeLbl=(state.storeMode==='sel'&&state.stores.size)?(state.stores.size===1?STORES.find(s=>state.stores.has(s.id)).name.replace('HERO ',''):state.stores.size+' stores'):T('All','Semua');
  const rec=m=>m.roi>=2?['Scale up','Perbesar']:m.roi>=1?['Continue','Lanjut']:['Stop / redesign','Stop / desain ulang'];
  const rows=activeSKUs().map(s=>({s,m:promoMetrics(s)})).filter(x=>x.m.active).sort((a,b)=>b.m.incrMargin-a.m.incrMargin).slice(0,14);
  G('chart-matrix').innerHTML=`<table class="tbl"><thead><tr>
    <th>SKU</th><th>Item</th><th>Category</th><th>Store</th><th>Baseline ADS</th><th>Disc %</th><th>Uplift %</th><th>Incr Units</th><th>Incr Margin</th><th>Funded %</th><th>ROI</th><th>${T('Recommendation','Rekomendasi')}</th></tr></thead><tbody>
    ${rows.map(({s,m})=>`<tr style="cursor:pointer" onclick="drillSku('${s.id}')">
      <td>${s.id}</td><td style="text-align:left">${s.name}</td>
      <td style="text-align:left"><span class="badge" style="background:${CCOLOR[s.catId]}22;color:${CCOLOR[s.catId]}">${s.cat}</span></td>
      <td style="text-align:left">${storeLbl}</td>
      <td data-fx="fads"><b style="color:#5C2D91">${fmt(m.ads)}</b>/d</td>
      <td data-fx="discPct">${(m.disc*100).toFixed(0)}%</td><td data-fx="upliftCell">+${(m.uplift*100).toFixed(0)}%</td>
      <td data-fx="actQty">${fmt(m.incrU)}</td><td data-fx="incrMCell"><b>Rp ${fmt(m.incrMargin)}</b></td>
      <td data-fx="fundedCell">${(m.funded*100).toFixed(0)}%</td>
      <td data-fx="roiCell" class="${m.roi>=1?'pos-ok':'pos-low'}"><b>${m.roi.toFixed(2)}x</b></td>
      <td style="text-align:left">${T(rec(m)[0],rec(m)[1])}</td></tr>`).join('')}
  </tbody></table>`;
}
function runSim_PROMO(){
  const breadth=1+state.sim.price/100, dDisc=state.sim.promo/100, durM=1+state.sim.seas/100, fund=state.sim.viral/100, elast=state.sim.lead/5, cannibX=1+state.sim.safe/20;
  const list=activeSKUs();
  let incrGMtot=0,promoCost=0,upW=0,w=0,units=0;
  list.forEach(s=>{
    const pm=promoMetrics(s);
    const on=pm.active||(breadth>1&&((parseInt(s.id.slice(4))||1)%Math.max(2,Math.round(1/Math.max(0.01,breadth-1)))===0));
    if(!on)return;
    const disc=Math.min(0.6,(pm.disc||0.12)+dDisc);
    const uplift=(pm.uplift||0.5)*(1+dDisc*elast);
    const period=pm.period*durM;
    const price=pm.price,cost=pm.cost,promoPrice=price*(1-disc);
    const baseUnits=pm.ads*period, incrU=pm.ads*uplift*period*(1-Math.min(0.6,pm.cannib*cannibX));
    const incrGM=incrU*(promoPrice-cost);
    const grossMarkdown=baseUnits*(price-promoPrice)*0.75;
    const funding=grossMarkdown*Math.min(0.9,pm.funded+fund);
    const netCost=Math.max(0,grossMarkdown-funding);
    incrGMtot+=incrGM; promoCost+=netCost;
    units+=incrU; upW+=uplift*pm.ads; w+=pm.ads;
  });
  const incrMargin=incrGMtot-promoCost;
  const roi=incrGMtot/Math.max(1,promoCost);
  const upliftAvg=w>0?upW/w*100:0;
  // baseline vs promoted mini line
  const base=Math.max(1,list.reduce((a,s)=>a+invMetrics(s).ads,0));
  const hist=[],fc=[],band=[],labels=[];const r=rng(hashScope());
  for(let i=14;i>0;i--){const d=DOW[(999-i)%7];hist.push(Math.round(base*d*(0.94+r()*0.12)));labels.push('D-'+i);}
  for(let i=0;i<14;i++){const d=DOW[i%7];const v=Math.round(base*d*(1+(upliftAvg/100)));fc.push(v);const g=Math.min(0.3,0.05+0.01*i);band.push([Math.round(v*(1-g)),Math.round(v*(1+g))]);labels.push('D+'+(i+1));}
  lineChart('chart-sim',{hist,fc,band,labels},{h:180});
  const baseK=computeK_PROMO();
  const dBase=baseK.incrMargin!==0?((incrMargin/baseK.incrMargin)-1)*100:0;
  simRun={order:incrMargin,dDem:roi,dMgn:dBase,svc:upliftAvg,series:fc};
  G('sim-order').textContent='Rp '+fmt(Math.round(incrMargin));
  const dd=G('sim-delta');dd.textContent=roi.toFixed(2)+'x';dd.className=roi>=1?'up':'down';
  const dm=G('sim-margin');dm.textContent=pct(dBase);dm.className=dBase>=0?'up':'down';G('sim-svc').textContent=upliftAvg.toFixed(0)+'%';
}
function renderAction_PROMO(){
  const k=computeK_PROMO();
  const stTag={pending:'st-pending',approved:'st-approved',rejected:'st-rejected',cancelled:'st-cancelled',reopened:'st-reopened',sent:'st-sent'}[actionState];
  const stTxt={pending:T('Pending','Menunggu'),approved:'Approved',rejected:'Rejected',cancelled:T('Cancelled','Dibatalkan'),reopened:'Reopened',sent:T('Sent →','Terkirim →')}[actionState];
  const stop=k.active.filter(x=>x.m.roi<1).length;
  G('actionbody').innerHTML=`
    <div class="action-card"><div class="ah"><span class="pri high">${T('HIGH PRIORITY','PRIORITAS TINGGI')}</span>
      <b>${T('Optimize the promo plan (scale winners, stop losers)','Optimalkan rencana promo (perbesar yang menang, stop yang rugi)')}</b><span class="status-tag ${stTag}">${stTxt}</span></div>
      <div class="tiny muted">${T('Agent evaluated','Agent mengevaluasi')} <b style="color:#C77700">${fmt(k.activeCount)}</b> ${T('active promos ·','promo aktif ·')} <b style="color:#D13438">${stop}</b> ${T('below 1x ROI.','di bawah ROI 1x.')}</div>
      <div class="impact">
        <div><span class="muted tiny">${T('Incr Margin','Margin Inkr')}</span><b data-fx="promo_incrM">Rp ${fmt(k.incrMargin)}</b></div>
        <div><span class="muted tiny">ROI</span><b class="${k.roi>=1?'up':'down'}" data-fx="promo_roi">${k.roi.toFixed(2)}x</b></div>
        <div><span class="muted tiny">Uplift</span><b class="up" data-fx="promo_uplift">+${k.upliftAvg.toFixed(1)}%</b></div>
        <div><span class="muted tiny">Funding</span><b data-fx="promo_funded">${k.fundedAvg.toFixed(0)}%</b></div></div>
      <div class="agentic-row">
        <button class="abtn approve" onclick="agentic('approved')">✔ ${T('Approve','Setujui')}</button>
        <button class="abtn reject" onclick="agentic('rejected')">✕ ${T('Reject','Tolak')}</button>
        <button class="abtn cancel" onclick="agentic('cancelled')">⊘ ${T('Cancel','Batal')}</button>
        <button class="abtn reopen" onclick="agentic('reopened')">↻ ${T('Reopen','Buka lagi')}</button>
        <button class="btn indigo sm" style="margin-left:auto" onclick="togglePO()">🏷️ ${T('Generate Promo Plan','Buat Rencana Promo')}</button></div></div>
    <div id="po-preview"></div>`;
}
function togglePromoPlan(){poOpen=!poOpen;const w=G('po-preview');if(!poOpen){w.innerHTML='';return;}
  const rec=m=>m.roi>=2?['Scale up','direct']:m.roi>=1?['Continue','flow']:['Stop / redesign','cross'];
  const rows=activeSKUs().map(s=>({s,m:promoMetrics(s)})).filter(x=>x.m.active).sort((a,b)=>b.m.roi-a.m.roi).slice(0,12)
    .map(({s,m})=>({sku:s.id,name:s.name,cat:s.cat,disc:(m.disc*100).toFixed(0)+'%',uplift:'+'+(m.uplift*100).toFixed(0)+'%',incr:m.incrMargin,roi:m.roi,funded:(m.funded*100).toFixed(0)+'%',rec:rec(m)}));
  w.innerHTML=`<div class="tiny muted" style="margin:2px 0 8px">${T('Promo plan — continue/scale winners (ROI ≥ 1x), stop/redesign losers. Routes to Pricing & Markdown Agent.','Rencana promo — lanjut/perbesar yang menang (ROI ≥ 1x), stop/desain ulang yang rugi. Diteruskan ke Agent Pricing & Markdown.')}</div>
    <div style="overflow:auto;border:1px solid var(--line);border-radius:11px"><table class="tbl"><thead><tr>
      <th>SKU</th><th>Item</th><th>Category</th><th>Discount</th><th>Uplift</th><th>Funded</th><th>Incr Margin</th><th>ROI</th><th>${T('Action','Aksi')}</th></tr></thead>
      <tbody>${rows.map(r=>`<tr><td>${r.sku}</td><td style="text-align:left">${r.name}</td><td style="text-align:left"><span class="badge" style="background:${CCOLOR[r.sku.split('-')[0]]}22;color:${CCOLOR[r.sku.split('-')[0]]}">${r.cat}</span></td>
        <td data-fx="discPct">${r.disc}</td><td data-fx="upliftCell">${r.uplift}</td><td data-fx="fundedCell">${r.funded}</td><td data-fx="incrMCell"><b>Rp ${fmt(r.incr)}</b></td>
        <td data-fx="roiCell" class="${r.roi>=1?'pos-ok':'pos-low'}"><b>${r.roi.toFixed(2)}x</b></td>
        <td style="text-align:left"><span class="route ${r.rec[1]}">${r.rec[0]}</span></td></tr>`).join('')}</tbody></table></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:9px">
      <button class="btn teal sm" onclick="sendHandoff('${rows.length+' '+T('promo line(s)','baris promo')}')">➤ ${T('Send to Pricing & Markdown Agent','Kirim ke Agent Pricing & Markdown')}</button>
      <button class="btn sm" onclick='exportPromoPlan(${JSON.stringify(rows)})'>⬇ ${T('Export to Excel','Export ke Excel')}</button></div>`;
}
function exportPromoPlan(rows){const h=['SKU','Item','Category','Discount','Uplift','Funded','Incr Margin','ROI','Action'];
  downloadCSV('AI360_Promo_Plan.csv',[h,...rows.map(r=>[r.sku,r.name,r.cat,r.disc,r.uplift,r.funded,r.incr,r.roi.toFixed(2)+'x',r.rec[0]])]);toast('⬇ '+T('Exported','Diekspor'));}
function aiReply_PROMO(q){const k=computeK_PROMO();const ql=q.toLowerCase();const ch=CHALLENGE;
  if(ql.includes('cannib')&&ch || (ql.includes('challenge')&&ql.includes('uplift'))){
    addMsg('ai',`${T('Reported uplift overstates true incremental sales because of cannibalization:','Uplift yang dilaporkan melebih-lebihkan penjualan tambahan sejati karena kanibalisasi:')}
      <div class="calcbox">true incremental = uplift × (1 − cannibalization)
avg cannibalization = ${k.cannibAvg.toFixed(1)}%
so ~${(k.upliftAvg*(1-k.cannibAvg/100)).toFixed(1)}% of the +${k.upliftAvg.toFixed(1)}% is real</div>
      ${T('Also check basket/halo effects and pantry-loading before scaling.','Cek juga efek basket/halo dan penimbunan sebelum memperbesar.')}`,true);
  }else if(ql.includes('roi')||ql.includes('work')||ql.includes('best')||ql.includes('perform')){
    const rows=k.active.slice().sort((a,b)=>b.m.roi-a.m.roi).slice(0,4);
    addMsg('ai',`${T('Portfolio promo ROI:','ROI promo portofolio:')} <b>${k.roi.toFixed(2)}x</b> · ${T('incr margin','margin inkr')} <b>Rp ${fmt(k.incrMargin)}</b>
      <div class="calcbox">ROI = Σ incremental margin ÷ Σ net promo cost</div>
      <table class="mini-table"><thead><tr><th>Item</th><th>Disc</th><th>Uplift</th><th>ROI</th></tr></thead><tbody>
      ${rows.map(x=>`<tr><td>${x.s.name}</td><td>${(x.m.disc*100).toFixed(0)}%</td><td>+${(x.m.uplift*100).toFixed(0)}%</td><td>${x.m.roi.toFixed(2)}x</td></tr>`).join('')||('<tr><td colspan=4>'+T('No active promo','Tidak ada promo aktif')+'</td></tr>')}</tbody></table>`,ch);
  }else if(ql.includes('fund')||ql.includes('supplier')){
    addMsg('ai',`${T('Average supplier funding:','Rata-rata funding supplier:')} <b>${k.fundedAvg.toFixed(1)}%</b> ${T('of discount cost.','dari biaya diskon.')}
      <div class="calcbox">retailer net promo cost = give-away − supplier funding</div>
      ${T('Push for higher funding on deep-discount SKUs to protect ROI.','Dorong funding lebih tinggi untuk SKU diskon dalam agar ROI terjaga.')}`,ch);
  }else if(ql.includes('next')||ql.includes('offer')||ql.includes('plan')||ql.includes('promo')){
    addMsg('ai',`${T('Next-best plan: scale ROI ≥ 2x, keep 1–2x, stop < 1x. Open the plan to review.','Rencana terbaik: perbesar ROI ≥ 2x, pertahankan 1–2x, stop < 1x. Buka rencana untuk review.')}
      <div style="margin-top:7px"><button class="btn indigo sm" onclick="togglePO();document.querySelector('[data-sec=action]').scrollIntoView({behavior:'smooth'})">🏷️ ${T('Open promo plan','Buka rencana promo')}</button></div>`,ch);
  }else if(ql.includes('explain')){
    addMsg('ai',T('Hover any number to see its formula, inputs and value. Every answer shows the math.','Arahkan kursor ke angka mana pun untuk lihat formula, input, dan nilainya. Tiap jawaban ada hitungannya.'),ch);
  }else{
    addMsg('ai',T('I can explain promo uplift, ROI, cannibalization, supplier funding, and the next-best plan. Turn on Challenge mode to pressure-test uplift.','Saya bisa jelaskan uplift promo, ROI, kanibalisasi, funding supplier, dan rencana terbaik. Nyalakan Challenge mode untuk menguji uplift.'),ch);
  }
}
const CHIPS_PROMO=[['Which promos work best (ROI)?','Promo mana paling untung (ROI)?',0],['Average supplier funding','Rata-rata funding supplier',0],['Show promo plan','Tampilkan rencana promo',0],['Next-best offer plan','Rencana next-best offer',0]];
const CHIPS_CH_PROMO=[['Challenge the uplift (cannibalization)','Tantang uplift (kanibalisasi)',1],['Challenge deep-discount ROI','Tantang ROI diskon dalam',1],['Stress-test if funding is cut','Stress-test kalau funding dipangkas',1]];
/* ================= END PROMOTION ================= */


/* ================= PRICING & MARKDOWN AGENT (shared invMetrics) ================= */
Object.assign(FX,{
 pm_cands:{t:['Markdown Candidates','Kandidat Markdown'],f:'count( state ∈ {Expiry, Overstock, Slow-mover} )',e:['SKUs flagged by Inventory Risk for price action.','SKU yang ditandai Inventory Risk untuk aksi harga.']},
 pm_depth:{t:['Avg Markdown Depth','Rata-rata Kedalaman Markdown'],f:'Σ(depth × at-risk value) ÷ Σ at-risk value',e:['Value-weighted markdown percentage.','Persentase markdown tertimbang nilai.']},
 pm_atrisk:{t:['Value at Risk','Nilai Berisiko'],f:'Σ at-risk units × regular price',e:['Retail value exposed to write-off if no action.','Nilai retail yang berisiko write-off tanpa aksi.']},
 pm_recover:{t:['Recoverable Value','Nilai Terselamatkan'],f:'Σ cleared units × markdown price',e:['Revenue rescued by markdown vs total write-off.','Pendapatan diselamatkan markdown vs write-off penuh.']},
 pm_elast:{t:['Avg Price Elasticity','Rata-rata Elastisitas'],f:'Σ(elasticity × ADS) ÷ Σ ADS',e:['Weighted demand response to price. More negative = markdown works harder.','Respons demand tertimbang thd harga. Makin negatif = markdown makin efektif.']},
 pm_comp:{t:['Competitor Index','Indeks Kompetitor'],f:'our price ÷ market basket × 100',e:['100 = at market. >100 = priced above market.','100 = setara pasar. >100 = di atas pasar.']},
 pm_dbase:{t:['Δ vs base','Δ vs base'],f:'( scenario recoverable ÷ base recoverable ) − 1',e:['Change in recoverable value under levers.','Perubahan nilai terselamatkan di simulasi.']},
 pm_sellthru:{t:['Sell-through','Sell-through'],f:'cleared units ÷ at-risk units',e:['Share of at-risk stock cleared before write-off.','Porsi stok berisiko yang habis sebelum write-off.']},
 depthCell:{t:['Depth','Kedalaman'],f:'1 − markdown price ÷ regular price',e:['Markdown depth for this SKU.','Kedalaman markdown SKU ini.']},
 newPriceCell:{t:['New price','Harga baru'],f:'regular price × (1 − depth)',e:['Proposed markdown price.','Harga markdown yang diusulkan.']},
 elastCell:{t:['Elasticity','Elastisitas'],f:'%Δ demand ÷ %Δ price (fresh ≈ −1.8, dry ≈ −1.0, × store index)',e:['Price sensitivity for this SKU.','Sensitivitas harga SKU ini.']},
 atRiskCell:{t:['At risk','Berisiko'],f:'expiry: units > ADS×shelf-life · overstock: Position − Max · slow: Position − ADS×10',e:['Units exposed to write-off.','Unit yang berisiko write-off.']},
 recoverCell:{t:['Recover','Selamatkan'],f:'cleared units × markdown price',e:['Value rescued for this SKU.','Nilai diselamatkan SKU ini.']}
});
const PM_WINDOW=14;                                   // non-fresh clearance window (days)
function pmMetrics(s){
  const m=invMetrics(s);const idn=parseInt(s.id.slice(4))||1;const si=storeIdx();
  const price=s.price, cost=price*(1-s.marginPct);
  let reason='none';
  if(m.state==='Expiry'||(s.fresh&&m.unitsExpiry>0)) reason='expiry';
  else if(m.state==='Overstock') reason='overstock';
  else if(m.state==='Slow-mover') reason='slow';
  const candidate=reason!=='none';
  let riskUnits=0, urgency=0, window=PM_WINDOW;
  if(reason==='expiry'){ riskUnits=m.unitsExpiry; window=s.expiry||3; urgency=Math.min(1,(7-(s.expiry||5))/6+0.25); }
  else if(reason==='overstock'){ riskUnits=Math.max(0,m.position-m.maxLevel); urgency=Math.min(1,(m.dos-15)/22); }
  else if(reason==='slow'){ riskUnits=Math.max(0,Math.round(m.position-m.ads*10)); urgency=Math.min(1,(m.dos-10)/24); }
  // depth: base + urgency, per-SKU variation, deeper where demand is weaker (low store index)
  const depth=candidate?Math.max(0.05,Math.min(0.55,0.10+urgency*0.30+((idn*11)%9)/100+(1-si)*0.06)):0;
  const newPrice=price*(1-depth);
  // elasticity: fresh more elastic; weaker-demand stores (si<1) more elastic
  const elast=(s.fresh?-1.8:-1.0)*(2-si);
  const lift=candidate?Math.min(1.6,-elast*depth):0;                 // demand uplift from markdown
  // only markdown-driven incremental demand clears the surplus (baseline serves regular turnover)
  const clearedUnits=candidate?Math.min(riskUnits,Math.round(m.ads*lift*window)):0;
  const atRisk=Math.round(riskUnits*price);                           // retail value exposed
  const recoverable=Math.round(clearedUnits*newPrice);               // value rescued vs write-off
  const recoveryRate=riskUnits>0?clearedUnits/riskUnits:0;
  const compIndex=Math.round((100+(s.marginPct-0.20)*55+(si-1)*10+(((idn*7)%7)-3))*10)/10;
  return {m,candidate,reason,price,cost,depth,newPrice,elast,lift,window,riskUnits,clearedUnits,atRisk,recoverable,recoveryRate,compIndex,ads:m.ads};
}
function computeK_PM(){
  const daily=genDaily();
  const list=activeSKUs().map(s=>({s,p:pmMetrics(s)}));
  const cands=list.filter(x=>x.p.candidate);
  const atRiskTot=cands.reduce((a,x)=>a+x.p.atRisk,0);
  const recoverTot=cands.reduce((a,x)=>a+x.p.recoverable,0);
  const depthW=atRiskTot>0?cands.reduce((a,x)=>a+x.p.depth*x.p.atRisk,0)/atRiskTot*100:0;
  const wads=activeSKUs().reduce((a,s)=>a+invMetrics(s).ads,0)||1;
  const elastW=activeSKUs().reduce((a,s)=>{const p=pmMetrics(s);return a+p.elast*p.ads;},0)/wads;
  const compW=activeSKUs().reduce((a,s)=>{const p=pmMetrics(s);return a+p.compIndex*p.ads;},0)/wads;
  const sellthru=cands.reduce((a,x)=>a+x.p.riskUnits,0);
  const sellRate=sellthru>0?cands.reduce((a,x)=>a+x.p.clearedUnits,0)/sellthru*100:0;
  return {candCount:cands.length,depthW,atRiskTot,recoverTot,elastW,compW,sellRate,list,cands,daily};
}
const KPIDEFS_PM=[
  {key:'candCount',color:'#C77700',lab:['Markdown Candidates','Kandidat Markdown'],fmt:k=>fmt(k.candCount)+' SKU',delta:k=>T('need price action','perlu aksi harga'),dcls:()=>'down',
   f:'count( state ∈ {Expiry, Overstock, Slow-mover} )',e:['SKUs flagged by Inventory Risk for markdown.','SKU yang ditandai Inventory Risk untuk markdown.'],val:k=>k.candCount},
  {key:'depthW',color:'#E8792B',lab:['Avg Markdown Depth','Rata-rata Kedalaman'],fmt:k=>k.depthW.toFixed(1)+'%',delta:k=>T('value-weighted','tertimbang nilai'),dcls:()=>'',
   f:'Σ(depth × at-risk value) ÷ Σ at-risk value',e:['Value-weighted markdown percentage.','Persentase markdown tertimbang nilai.'],val:k=>k.depthW},
  {key:'atRiskTot',color:'#D13438',lab:['Value at Risk','Nilai Berisiko'],fmt:k=>'Rp '+fmt(k.atRiskTot),delta:k=>T('write-off exposure','eksposur write-off'),dcls:()=>'down',
   f:'Σ at-risk units × regular price',e:['Retail value exposed to write-off if no action.','Nilai retail berisiko write-off tanpa aksi.'],val:k=>k.atRiskTot},
  {key:'recoverTot',color:'#107C41',lab:['Recoverable Value','Nilai Terselamatkan'],fmt:k=>'Rp '+fmt(k.recoverTot),delta:k=>T('rescued by markdown','diselamatkan markdown'),dcls:()=>'up',
   f:'Σ cleared units × markdown price',e:['Revenue rescued by markdown vs total write-off.','Pendapatan diselamatkan markdown vs write-off penuh.'],val:k=>k.recoverTot},
  {key:'elastW',color:'#5C2D91',lab:['Avg Price Elasticity','Rata-rata Elastisitas'],fmt:k=>k.elastW.toFixed(2),delta:k=>T('demand vs price','demand vs harga'),dcls:()=>'',
   f:'Σ(elasticity × ADS) ÷ Σ ADS',e:['Weighted demand response to price.','Respons demand tertimbang thd harga.'],val:k=>Math.abs(k.elastW)},
  {key:'compW',color:'#0078D4',lab:['Competitor Index','Indeks Kompetitor'],fmt:k=>k.compW.toFixed(1),delta:k=>k.compW>=100?T('above market','di atas pasar'):T('below market','di bawah pasar'),dcls:k=>k.compW>=100?'down':'up',
   f:'our price ÷ market basket × 100',e:['100 = at market. >100 = priced above market.','100 = setara pasar. >100 = di atas pasar.'],val:k=>k.compW},
];
function renderForecast_PM(){
  const cands=activeSKUs().map(pmMetrics).filter(p=>p.candidate);
  const startU=Math.max(1,cands.reduce((a,p)=>a+p.riskUnits,0));
  const adsSum=Math.max(1,cands.reduce((a,p)=>a+p.ads,0));
  const wLift=cands.length?cands.reduce((a,p)=>a+p.lift*p.ads,0)/adsSum:0.4;
  const shelfDay=Math.max(3,Math.round(cands.reduce((a,p)=>a+p.window*p.riskUnits,0)/startU));
  const clearedTot=cands.reduce((a,p)=>a+p.clearedUnits,0);const residual=Math.max(0,startU-clearedTot); // stock markdown can't clear in time
  const days=Math.max(14,Math.min(70,state.horizon*7));const hold=[],mkdn=[],labels=[];
  let md=startU;
  for(let i=0;i<days;i++){
    hold.push(i<shelfDay?startU:0);        // surplus lingers, then writes off at shelf-life
    mkdn.push(Math.round(Math.max(residual,md)));
    labels.push('D+'+(i+1));
    md-=adsSum*wLift;                       // cleared by markdown-driven incremental demand
  }
  multiLine('chart-forecast',[
    {name:T('Hold (no action)','Tahan (tanpa aksi)'),color:'#8A8886',data:hold,dash:'5 4'},
    {name:T('With markdown','Dengan markdown'),color:'#0078D4',data:mkdn},
  ],labels);
  const k=computeK_PM();
  G('forenote').textContent=T(`At-risk stock burn-down · hold vs markdown · ${k.candCount} candidates · horizon ${state.horizon}wk · scope: ${scopeShort()}`,`Burn-down stok berisiko · tahan vs markdown · ${k.candCount} kandidat · horizon ${state.horizon}mgg · scope: ${scopeShort()}`);
  G('forecastStats').innerHTML=`<div class="m"><div class="k">${T('Candidates','Kandidat')}</div><b data-fx="pm_cands">${fmt(k.candCount)}</b></div>
    <div class="m"><div class="k">${T('At risk','Berisiko')}</div><b data-fx="pm_atrisk">Rp ${fmt(k.atRiskTot)}</b></div>
    <div class="m"><div class="k">${T('Recoverable','Terselamatkan')}</div><b data-fx="pm_recover">Rp ${fmt(k.recoverTot)}</b></div>
    <div class="m"><div class="k">${T('Avg depth','Kedalaman')}</div><b data-fx="pm_depth">${k.depthW.toFixed(1)}%</b></div>
    <div class="m"><div class="k">Sell-through</div><b data-fx="pm_sellthru">${k.sellRate.toFixed(0)}%</b></div>`;
}
function renderDriver_PM(){
  const cands=activeSKUs().map(pmMetrics).filter(p=>p.candidate);
  const atRisk=cands.reduce((a,p)=>a+p.atRisk,0);
  const recover=cands.reduce((a,p)=>a+p.recoverable,0);
  const giveUp=cands.reduce((a,p)=>a+Math.round(p.clearedUnits*(p.price-p.newPrice)),0);
  const writeOff=Math.max(0,atRisk-recover-giveUp);
  barChart('chart-driver',[
    {label:T('Value at risk','Nilai berisiko'),value:Math.round(atRisk),color:'#D13438',fx:'Σ at-risk units × regular price'},
    {label:T('Markdown give-up','Give-up markdown'),value:Math.round(giveUp),color:'#E8792B',fx:'cleared units × (price − markdown price)'},
    {label:T('Residual write-off','Sisa write-off'),value:Math.round(writeOff),color:'#8A8886',fx:'at-risk value not cleared in time'},
    {label:T('Recovered','Terselamatkan'),value:Math.round(recover),color:'#107C41',fx:'cleared units × markdown price'},
  ],{pb:44});
}
function renderTrend_PM(){
  const pool=activeSKUs().map(s=>({s,p:pmMetrics(s)})).filter(x=>x.p.candidate).sort((a,b)=>b.p.atRisk-a.p.atRisk).slice(0,5);
  const ic={expiry:'⏰',overstock:'📦',slow:'🐌'};
  G('trendlist').innerHTML=pool.map(x=>`<div class="trow"><span class="fireicon">${ic[x.p.reason]||'🏷️'}</span>
    <div><div class="tn">${x.s.name}</div><div class="tc">${x.s.cat} · ${x.p.reason} · −${(x.p.depth*100).toFixed(0)}% → Rp ${fmt(Math.round(x.p.newPrice))}</div></div>
    <div class="tu down">Rp ${fmt(x.p.atRisk)}</div></div>`).join('')||`<div class="tiny muted">${T('No markdown candidate in scope.','Tidak ada kandidat markdown di scope.')}</div>`;
}
function renderCat_PM(){
  const data=CATS.map(c=>{let v=0;SKUS.filter(s=>s.catId===c.id).forEach(s=>{const p=pmMetrics(s);if(p.candidate)v+=p.atRisk;});
    return {label:c.name,value:Math.round(v),color:CCOLOR[c.id],fx:'Σ value at risk for markdown candidates in category',
      onclick:()=>{state.itemMode='cat';state.cats=new Set([c.id]);syncSegs();refreshAll();toast('🗂️ '+T('Filtered: ','Filter: ')+c.name);}};});
  barChart('chart-cat',data,{pb:52});
}
function renderStore_PM(){
  const sv={sm:state.storeMode,st:new Set(state.stores)};
  const data=STORES.map(st=>{state.storeMode='sel';state.stores=new Set([st.id]);
    const n=activeSKUs().map(pmMetrics).filter(p=>p.candidate).length;
    return {label:st.name.replace('HERO ',''),value:n,color:'#C77700',fx:'markdown candidates in this store (Expiry+Overstock+Slow)',
      onclick:()=>{state.storeMode='sel';state.stores=new Set([st.id]);syncSegs();refreshAll();toast('🏪 '+T('Filtered: ','Filter: ')+st.name);}};});
  state.storeMode=sv.sm;state.stores=new Set(sv.st);
  hbarChart('chart-store',data.sort((a,b)=>b.value-a.value));
}
function renderCluster_PM(){
  const cc={Premium:'#5C2D91','Urban Mall':'#0078D4',Suburban:'#008575',Resort:'#C77700'};
  const sv={sm:state.storeMode,st:new Set(state.stores)};
  const data=CLUSTERS.map(cl=>{state.storeMode='sel';state.stores=new Set(STORES.filter(s=>s.cluster===cl).map(s=>s.id));
    const v=activeSKUs().map(pmMetrics).filter(p=>p.candidate).reduce((a,p)=>a+p.recoverable,0);
    return {label:cl,value:Math.round(v),color:cc[cl],fx:'Σ recoverable value for candidates in cluster',
      onclick:()=>{state.storeMode='sel';state.stores=new Set(STORES.filter(s=>s.cluster===cl).map(s=>s.id));syncSegs();refreshAll();toast('🧭 '+T('Cluster: ','Cluster: ')+cl);}};});
  state.storeMode=sv.sm;state.stores=new Set(sv.st);
  barChart('chart-cluster',data,{pb:40});
}
function renderSeason_PM(){
  const buckets=[['≤10%',0.10],['10–20%',0.20],['20–30%',0.30],['30–40%',0.40],['40–50%',0.50],['>50%',1]];const vals=buckets.map(()=>0);
  activeSKUs().map(pmMetrics).filter(p=>p.candidate).forEach(p=>{let bi=buckets.findIndex(b=>p.depth<=b[1]);if(bi<0)bi=buckets.length-1;vals[bi]+=p.atRisk;});
  const cols=['#0A9ED4','#0078D4','#107C41','#C77700','#E8792B','#D13438'];
  const data=buckets.map((b,i)=>({label:b[0],value:Math.round(vals[i]),color:cols[i],fx:'Σ value at risk by markdown-depth bucket'}));
  barChart('chart-season',data,{h:196,pb:26});
}
function renderMatrix_PM(){
  const storeLbl=(state.storeMode==='sel'&&state.stores.size)?(state.stores.size===1?STORES.find(s=>state.stores.has(s.id)).name.replace('HERO ',''):state.stores.size+' stores'):T('All','Semua');
  const rec=p=>p.reason==='slow'?['Delist review','cross']:p.reason==='expiry'?['Markdown now','direct']:['Markdown / clear','flow'];
  const rows=activeSKUs().map(s=>({s,p:pmMetrics(s)})).filter(x=>x.p.candidate).sort((a,b)=>b.p.atRisk-a.p.atRisk).slice(0,14);
  G('chart-matrix').innerHTML=`<table class="tbl"><thead><tr>
    <th>SKU</th><th>Item</th><th>Category</th><th>Store</th><th>Reason</th><th>At-Risk U</th><th>Price</th><th>New Price</th><th>Depth</th><th>Elasticity</th><th>Recover</th><th>${T('Recommendation','Rekomendasi')}</th></tr></thead><tbody>
    ${rows.map(({s,p})=>`<tr style="cursor:pointer" onclick="drillSku('${s.id}')">
      <td>${s.id}</td><td style="text-align:left">${s.name}</td>
      <td style="text-align:left"><span class="badge" style="background:${CCOLOR[s.catId]}22;color:${CCOLOR[s.catId]}">${s.cat}</span></td>
      <td style="text-align:left">${storeLbl}</td>
      <td style="text-align:left">${p.reason}</td>
      <td data-fx="atRiskCell"><b>${fmt(p.riskUnits)}</b></td>
      <td>Rp ${fmt(Math.round(p.price))}</td>
      <td data-fx="newPriceCell"><b style="color:#107C41">Rp ${fmt(Math.round(p.newPrice))}</b></td>
      <td data-fx="depthCell">−${(p.depth*100).toFixed(0)}%</td>
      <td data-fx="elastCell">${p.elast.toFixed(2)}</td>
      <td data-fx="recoverCell"><b>Rp ${fmt(p.recoverable)}</b></td>
      <td style="text-align:left">${T(rec(p)[0],rec(p)[0])}</td></tr>`).join('')||`<tr><td colspan="12" style="text-align:center;color:var(--muted);padding:14px">${T('No markdown candidate in scope.','Tidak ada kandidat markdown di scope.')}</td></tr>`}
  </tbody></table>`;
}
function runSim_PM(){
  const dDem=state.sim.price/100, dDepth=state.sim.promo/100, dur=1+state.sim.seas/100,
        support=state.sim.viral/100, elFac=state.sim.lead/3, compCut=state.sim.safe/100*0.6;
  const cands=activeSKUs().map(pmMetrics).filter(p=>p.candidate);
  let recover=0,atRisk=0,cleared=0,riskU=0;
  cands.forEach(p=>{
    const ads=p.ads*(1+dDem);
    const depth=Math.min(0.6,p.depth+dDepth);
    const newPrice=p.price*(1-depth)*(1-compCut);              // competitor pressure compresses realised price
    const lift=Math.min(2.2,-p.elast*elFac*depth);
    const window=(p.reason==='expiry'?p.window:PM_WINDOW)*dur;
    const ru=Math.max(0,Math.round(p.riskUnits*(1+dDem*0.5)));
    const cl=Math.min(ru,Math.round(ads*lift*window));
    const supportRp=cl*(p.price-newPrice)*support;             // supplier offsets part of give-up
    recover+=cl*newPrice+supportRp; atRisk+=ru*p.price; cleared+=cl; riskU+=ru;
  });
  const sellRate=riskU>0?cleared/riskU*100:0;
  // burn-down mini line under levers
  const adsSum=Math.max(1,cands.reduce((a,p)=>a+p.ads*(1+dDem),0));
  const wLift=cands.length?cands.reduce((a,p)=>a+Math.min(2.2,-p.elast*elFac*(Math.min(0.6,p.depth+dDepth)))*p.ads,0)/adsSum:0.4;
  const startU=Math.max(1,riskU);const shelfDay=Math.max(3,Math.round(cands.reduce((a,p)=>a+(p.reason==='expiry'?p.window:PM_WINDOW)*p.riskUnits,0)/startU));const residual=Math.max(0,riskU-cleared);const hold=[],fc=[],labels=[];let md=startU;
  for(let i=0;i<18;i++){hold.push(i<shelfDay?startU:0);fc.push(Math.round(Math.max(residual,md)));labels.push('D+'+(i+1));md-=adsSum*wLift*dur;}
  multiLine('chart-sim',[{name:T('Hold','Tahan'),color:'#8A8886',data:hold,dash:'5 4'},{name:T('With markdown','Dengan markdown'),color:'#0078D4',data:fc}],labels);
  const baseK=computeK_PM();
  const dBase=baseK.recoverTot!==0?((recover/baseK.recoverTot)-1)*100:0;
  simRun={order:Math.round(recover),dDem:dBase,dMgn:sellRate,svc:cands.length,series:fc};
  G('sim-order').textContent='Rp '+fmt(Math.round(recover));
  const dd=G('sim-delta');dd.textContent=pct(dBase);dd.className=dBase>=0?'up':'down';
  const dm=G('sim-margin');dm.textContent=sellRate.toFixed(0)+'%';dm.className='up';
  G('sim-svc').textContent=fmt(cands.length);
}
function renderAction_PM(){
  const k=computeK_PM();
  const stTag={pending:'st-pending',approved:'st-approved',rejected:'st-rejected',cancelled:'st-cancelled',reopened:'st-reopened',sent:'st-sent'}[actionState];
  const stTxt={pending:T('Pending','Menunggu'),approved:'Approved',rejected:'Rejected',cancelled:T('Cancelled','Dibatalkan'),reopened:'Reopened',sent:T('Sent →','Terkirim →')}[actionState];
  const delist=k.cands.filter(x=>x.p.reason==='slow').length;
  G('actionbody').innerHTML=`
    <div class="action-card"><div class="ah"><span class="pri high">${T('HIGH PRIORITY','PRIORITAS TINGGI')}</span>
      <b>${T('Execute markdown & repricing plan','Jalankan rencana markdown & repricing')}</b><span class="status-tag ${stTag}">${stTxt}</span></div>
      <div class="tiny muted">${T('Agent flagged','Agent menandai')} <b style="color:#C77700">${fmt(k.candCount)}</b> ${T('candidates ·','kandidat ·')} <b style="color:#D13438">Rp ${fmt(k.atRiskTot)}</b> ${T('at risk ·','berisiko ·')} <b style="color:#5C2D91">${delist}</b> ${T('chronic → delist review.','kronis → review delist.')}</div>
      <div class="impact">
        <div><span class="muted tiny">${T('Value at Risk','Nilai Berisiko')}</span><b class="down" data-fx="pm_atrisk">Rp ${fmt(k.atRiskTot)}</b></div>
        <div><span class="muted tiny">${T('Recoverable','Terselamatkan')}</span><b class="up" data-fx="pm_recover">Rp ${fmt(k.recoverTot)}</b></div>
        <div><span class="muted tiny">${T('Avg Depth','Kedalaman')}</span><b data-fx="pm_depth">${k.depthW.toFixed(1)}%</b></div>
        <div><span class="muted tiny">Sell-through</span><b class="up" data-fx="pm_sellthru">${k.sellRate.toFixed(0)}%</b></div></div>
      <div class="agentic-row">
        <button class="abtn approve" onclick="agentic('approved')">✔ ${T('Approve','Setujui')}</button>
        <button class="abtn reject" onclick="agentic('rejected')">✕ ${T('Reject','Tolak')}</button>
        <button class="abtn cancel" onclick="agentic('cancelled')">⊘ ${T('Cancel','Batal')}</button>
        <button class="abtn reopen" onclick="agentic('reopened')">↻ ${T('Reopen','Buka lagi')}</button>
        <button class="btn indigo sm" style="margin-left:auto" onclick="togglePO()">🏷️ ${T('Generate Markdown Plan','Buat Rencana Markdown')}</button></div></div>
    <div id="po-preview"></div>`;
}
function togglePMPlan(){poOpen=!poOpen;const w=G('po-preview');if(!poOpen){w.innerHTML='';return;}
  const rec=p=>p.reason==='slow'?['Delist review','cross']:p.reason==='expiry'?['Markdown now','direct']:['Markdown / clear','flow'];
  const rows=activeSKUs().map(s=>({s,p:pmMetrics(s)})).filter(x=>x.p.candidate).sort((a,b)=>b.p.atRisk-a.p.atRisk).slice(0,12)
    .map(({s,p})=>({sku:s.id,name:s.name,cat:s.cat,reason:p.reason,risk:p.riskUnits,price:Math.round(p.price),newp:Math.round(p.newPrice),depth:(p.depth*100).toFixed(0)+'%',recover:p.recoverable,rec:rec(p)}));
  const delistN=rows.filter(r=>r.rec[1]==='cross').length;
  w.innerHTML=`<div class="tiny muted" style="margin:2px 0 8px">${T('Markdown plan — clear expiry/overstock before write-off. Slow-movers are a structural assortment decision, routed to Assortment Optimization for delist review. Aligned with the agent recommendation above.','Rencana markdown — habiskan expiry/overstock sebelum write-off. Slow-mover adalah keputusan assortment struktural, diteruskan ke Assortment Optimization untuk review delist. Selaras dengan rekomendasi agent di atas.')}</div>
    <div style="overflow:auto;border:1px solid var(--line);border-radius:11px"><table class="tbl"><thead><tr>
      <th>SKU</th><th>Item</th><th>Category</th><th>Reason</th><th>At-Risk U</th><th>Price</th><th>New Price</th><th>Depth</th><th>Recover</th><th>${T('Action','Aksi')}</th></tr></thead>
      <tbody>${rows.map(r=>`<tr><td>${r.sku}</td><td style="text-align:left">${r.name}</td><td style="text-align:left"><span class="badge" style="background:${CCOLOR[r.sku.split('-')[0]]}22;color:${CCOLOR[r.sku.split('-')[0]]}">${r.cat}</span></td>
        <td style="text-align:left">${r.reason}</td><td data-fx="atRiskCell">${fmt(r.risk)}</td><td>Rp ${fmt(r.price)}</td><td data-fx="newPriceCell"><b style="color:#107C41">Rp ${fmt(r.newp)}</b></td>
        <td data-fx="depthCell">−${r.depth}</td><td data-fx="recoverCell"><b>Rp ${fmt(r.recover)}</b></td>
        <td style="text-align:left"><span class="route ${r.rec[1]}">${r.rec[0]}</span></td></tr>`).join('')}</tbody></table></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:9px">
      <button class="btn teal sm" onclick="sendHandoff('${delistN+' '+T('delist candidate(s)','kandidat delist')}')">➤ ${T('Send delist candidates to Assortment Agent','Kirim kandidat delist ke Agent Assortment')} (${delistN})</button>
      <button class="btn sm" onclick='exportPMPlan(${JSON.stringify(rows)})'>⬇ ${T('Export to Excel','Export ke Excel')}</button></div>`;
}
function exportPMPlan(rows){const h=['SKU','Item','Category','Reason','At-Risk Units','Price','New Price','Depth','Recoverable','Action'];
  downloadCSV('AI360_Markdown_Plan.csv',[h,...rows.map(r=>[r.sku,r.name,r.cat,r.reason,r.risk,r.price,r.newp,r.depth,r.recover,r.rec[0]])]);toast('⬇ '+T('Exported','Diekspor'));}
function aiReply_PM(q){const k=computeK_PM();const ql=q.toLowerCase();const ch=CHALLENGE;
  if(ql.includes('elasticit')||(ch&&ql.includes('markdown'))){
    addMsg('ai',`${T('Markdown only recovers value if demand actually responds to price:','Markdown hanya menyelamatkan nilai jika demand benar-benar merespons harga:')}
      <div class="calcbox">avg elasticity = ${k.elastW.toFixed(2)}  (fresh ≈ −1.8, dry ≈ −1.0)
uplift ≈ −elasticity × depth
sell-through now = ${k.sellRate.toFixed(0)}% of at-risk stock</div>
      ${T('For inelastic SKUs a deep markdown just gives away margin without clearing stock. Transfer or bundle instead.','Untuk SKU inelastis, markdown dalam hanya membuang margin tanpa menghabiskan stok. Lebih baik transfer atau bundling.')}`,true);
  }else if(ql.includes('risk')||ql.includes('write')||ql.includes('expir')){
    const rows=k.cands.slice().sort((a,b)=>b.p.atRisk-a.p.atRisk).slice(0,4);
    addMsg('ai',`${T('Value at risk of write-off:','Nilai berisiko write-off:')} <b>Rp ${fmt(k.atRiskTot)}</b> · ${T('recoverable','terselamatkan')} <b>Rp ${fmt(k.recoverTot)}</b>
      <div class="calcbox">at risk = Σ at-risk units × price ; recoverable = Σ cleared × markdown price</div>
      <table class="mini-table"><thead><tr><th>Item</th><th>Reason</th><th>At-risk</th><th>Recover</th></tr></thead><tbody>
      ${rows.map(x=>`<tr><td>${x.s.name}</td><td>${x.p.reason}</td><td>Rp ${fmt(x.p.atRisk)}</td><td>Rp ${fmt(x.p.recoverable)}</td></tr>`).join('')||('<tr><td colspan=4>'+T('None in scope','Tidak ada di scope')+'</td></tr>')}</tbody></table>`,ch);
  }else if(ql.includes('competitor')||ql.includes('index')||ql.includes('price up')||ql.includes('reprice')){
    addMsg('ai',`${T('Competitor price index:','Indeks harga kompetitor:')} <b>${k.compW.toFixed(1)}</b> (100 = ${T('at market','setara pasar')})
      <div class="calcbox">index = our price ÷ market basket × 100</div>
      ${k.compW>=100?T('We are priced above market on this scope. Room to hold margin, but watch volume on elastic SKUs.','Kita di atas pasar untuk scope ini. Ada ruang jaga margin, tapi awasi volume di SKU elastis.'):T('We are below market. Consider selective price-ups on inelastic staples to recover margin.','Kita di bawah pasar. Pertimbangkan price-up selektif di staple inelastis untuk pulihkan margin.')}`,ch);
  }else if(ql.includes('plan')||ql.includes('action')||ql.includes('delist')||ql.includes('next')){
    addMsg('ai',`${T('Plan: markdown expiry/overstock now; route slow-movers to Assortment for delist review (a structural decision markdown alone cannot fix).','Rencana: markdown expiry/overstock sekarang; slow-mover diteruskan ke Assortment untuk review delist (keputusan struktural yang tak bisa diselesaikan markdown saja).')}
      <div style="margin-top:7px"><button class="btn indigo sm" onclick="togglePO();document.querySelector('[data-sec=action]').scrollIntoView({behavior:'smooth'})">🏷️ ${T('Open markdown plan','Buka rencana markdown')}</button></div>`,ch);
  }else if(ql.includes('explain')){
    addMsg('ai',T('Hover any number to see its formula, inputs and value. Candidates come straight from Inventory Risk states, so the numbers reconcile across agents.','Arahkan kursor ke angka mana pun untuk lihat formula, input, dan nilainya. Kandidat berasal langsung dari status Inventory Risk, jadi angkanya konsisten antar agent.'),ch);
  }else{
    addMsg('ai',T('I can explain value at risk, recoverable value, elasticity, competitor index, and the markdown/delist plan. Turn on Challenge mode to pressure-test the markdown.','Saya bisa jelaskan nilai berisiko, nilai terselamatkan, elastisitas, indeks kompetitor, dan rencana markdown/delist. Nyalakan Challenge mode untuk menguji markdown.'),ch);
  }
}
const CHIPS_PM=[['What is at risk of write-off?','Apa yang berisiko write-off?',0],['Show the markdown plan','Tampilkan rencana markdown',0],['Competitor price index','Indeks harga kompetitor',0],['Which SKUs to delist?','SKU mana yang di-delist?',0]];
const CHIPS_CH_PM=[['Challenge the markdown (elasticity)','Tantang markdown (elastisitas)',1],['Challenge deep markdown ROI','Tantang ROI markdown dalam',1],['Stress-test if demand drops','Stress-test kalau demand turun',1]];
/* ================= END PRICING & MARKDOWN ================= */


/* ================= ASSORTMENT OPTIMIZATION AGENT (shared invMetrics/pmMetrics) ================= */
Object.assign(FX,{
 assort_delist:{t:['Delist Candidates','Kandidat Delist'],f:'count( slow-mover  OR  (long-tail & GMROI < threshold) )',e:['SKUs to discontinue; includes slow-movers routed from Pricing & Markdown.','SKU untuk dihentikan; termasuk slow-mover dari Pricing & Markdown.']},
 assort_grow:{t:['Grow Candidates','Kandidat Grow'],f:'top SKUs by margin contribution (expand facings/space)',e:['Winners to give more space / distribution.','Juara yang diberi ruang/distribusi lebih.']},
 assort_gmroi:{t:['Avg GMROI','Rata-rata GMROI'],f:'annual gross margin ÷ average inventory at cost',e:['Gross Margin Return on Inventory Investment. >3 is strong.','Imbal margin atas investasi inventory. >3 kuat.']},
 assort_tail:{t:['Tail Share','Porsi Ekor'],f:'% of SKUs generating the bottom 20% of margin',e:['Long-tail concentration; high = many low-value SKUs.','Konsentrasi long-tail; tinggi = banyak SKU bernilai rendah.']},
 assort_capital:{t:['Capital Freed','Modal Bebas'],f:'Σ (delist SKUs) on-hand × unit cost',e:['Working capital released by delisting the tail.','Modal kerja yang dibebaskan dengan delist ekor.']},
 assort_impact:{t:['Margin Impact','Dampak Margin'],f:'grow uplift − net delist loss + capital reinvestment (per year)',e:['Annual margin impact of the optimized range.','Dampak margin tahunan dari range yang dioptimalkan.']},
 assort_dbase:{t:['Δ vs base','Δ vs base'],f:'( scenario impact ÷ base impact ) − 1',e:['Change in annual margin impact under levers.','Perubahan dampak margin tahunan di simulasi.']},
 gmroiCell:{t:['GMROI','GMROI'],f:'annual GM ÷ avg inventory at cost',e:['Return on inventory for this SKU.','Imbal inventory SKU ini.']},
 velCell:{t:['Velocity','Velocity'],f:'average daily sales (ADS) for this SKU',e:['Sales speed.','Kecepatan jual.']},
 contribCell:{t:['Contribution','Kontribusi'],f:'ADS × unit gross margin (daily)',e:['Daily margin this SKU contributes.','Margin harian dari SKU ini.']},
 capCell:{t:['Capital','Modal'],f:'on-hand units × unit cost',e:['Working capital tied in this SKU.','Modal kerja tertahan di SKU ini.']}
});
function assortMetrics(s){
  const m=invMetrics(s);const price=s.price,cost=price*(1-s.marginPct),marginU=price-cost;
  const velocity=m.ads;const dailyGM=velocity*marginU;const annualGM=dailyGM*365;
  // GMROI = annual GM ÷ avg inventory at cost. avg holding = current DoS + cycle/safety buffer (store health varies DoS).
  const avgInvDays=m.dos+(s.fresh?16:30);const gmroi=(365/avgInvDays)*(marginU/cost);
  const contribution=Math.round(dailyGM);const capitalTied=Math.round(m.onHandU*cost);
  return {m,price,cost,marginU,velocity,dailyGM,annualGM,gmroi,contribution,capitalTied,slow:m.state==='Slow-mover',fresh:s.fresh};
}
function assortClassify(list,opt={}){
  const gmroiCut=opt.gmroiCut==null?2.5:opt.gmroiCut;
  list.forEach(x=>{const g=x.a.gmroi;
    x.a.grow=g>=3.5;                                  // strong-return winners → expand
    x.a.tail=g<2.0;                                   // low-return long tail
    x.a.delist=x.a.slow||(g<gmroiCut&&!x.a.grow);     // slow-movers + weak GMROI
    x.a.tier=g>=3.5?'Star':g>=2.5?'Core':g>=1.5?'Slow':'Tail';});
}
function assortImpact(list,opt={}){
  const transfer=opt.transfer==null?0.55:opt.transfer, growInv=opt.growInv==null?1:opt.growInv,
        cannib=opt.cannib||0, execFrac=opt.execFrac==null?0.6:opt.execFrac, spaceBoost=opt.spaceBoost||0;
  const growList=list.filter(x=>x.a.grow);
  const cands=list.filter(x=>x.a.delist).sort((a,b)=>a.a.gmroi-b.a.gmroi);   // worst GMROI first
  const nAction=Math.max(0,Math.min(cands.length,Math.round(cands.length*execFrac)));
  const delistList=cands.slice(0,nAction);
  const capitalFreed=delistList.reduce((a,x)=>a+x.a.capitalTied,0);
  const growUplift=growList.reduce((a,x)=>a+x.a.annualGM*(0.15+spaceBoost)*growInv,0);
  const lost=delistList.reduce((a,x)=>a+x.a.annualGM,0);
  const retained=lost*transfer;const capitalBenefit=capitalFreed*0.20;
  const impact=Math.round((growUplift-(lost-retained)+capitalBenefit)*(1-cannib));
  return {impact,capitalFreed,growUplift,lost,retained,capitalBenefit,growList,delistList,candCount:cands.length};
}
function computeK_ASSORT(){
  const daily=genDaily();
  const list=activeSKUs().map(s=>({s,a:assortMetrics(s)}));
  assortClassify(list);const im=assortImpact(list);
  const n=list.length;
  const gmroiAvg=n?list.reduce((a,x)=>a+x.a.gmroi,0)/n:0;
  const tailShare=n?list.filter(x=>x.a.tail).length/n*100:0;
  return {assortSize:n,delistCount:im.delistList.length,growCount:im.growList.length,gmroiAvg,tailShare,
    capitalFreed:im.capitalFreed,marginImpact:im.impact,list,delistList:im.delistList,growList:im.growList,daily};
}
const KPIDEFS_ASSORT=[
  {key:'delist',color:'#D13438',lab:['Delist Candidates','Kandidat Delist'],fmt:k=>fmt(k.delistCount)+' SKU',delta:k=>T('discontinue tail','hentikan ekor'),dcls:()=>'down',
   f:'count( slow-mover OR (long-tail & GMROI < threshold) )',e:['SKUs to discontinue; includes slow-movers from Pricing & Markdown.','SKU untuk dihentikan; termasuk slow-mover dari Pricing & Markdown.'],val:k=>k.delistCount},
  {key:'grow',color:'#107C41',lab:['Grow Candidates','Kandidat Grow'],fmt:k=>fmt(k.growCount)+' SKU',delta:k=>T('expand winners','perbesar juara'),dcls:()=>'up',
   f:'top SKUs by margin contribution',e:['Winners to give more space / distribution.','Juara yang diberi ruang/distribusi lebih.'],val:k=>k.growCount},
  {key:'gmroi',color:'#5C2D91',lab:['Avg GMROI','Rata-rata GMROI'],fmt:k=>k.gmroiAvg.toFixed(2)+'x',delta:k=>k.gmroiAvg>=3?T('strong','kuat'):T('watch','pantau'),dcls:k=>k.gmroiAvg>=3?'up':'down',
   f:'annual gross margin ÷ average inventory at cost',e:['Gross Margin Return on Inventory Investment.','Imbal margin atas investasi inventory.'],val:k=>k.gmroiAvg},
  {key:'tail',color:'#C77700',lab:['Tail Share','Porsi Ekor'],fmt:k=>k.tailShare.toFixed(1)+'%',delta:k=>T('bottom 20% margin','20% margin terbawah'),dcls:()=>'down',
   f:'% of SKUs generating the bottom 20% of margin',e:['Long-tail concentration.','Konsentrasi long-tail.'],val:k=>k.tailShare},
  {key:'capital',color:'#0078D4',lab:['Capital Freed','Modal Bebas'],fmt:k=>'Rp '+fmt(k.capitalFreed),delta:k=>T('from delisting','dari delist'),dcls:()=>'up',
   f:'Σ (delist SKUs) on-hand × unit cost',e:['Working capital released by delisting the tail.','Modal kerja dibebaskan dari delist ekor.'],val:k=>k.capitalFreed},
  {key:'impact',color:'#008575',lab:['Margin Impact (yr)','Dampak Margin (thn)'],fmt:k=>'Rp '+fmt(k.marginImpact),delta:k=>T('optimized range','range optimal'),dcls:()=>'up',
   f:'grow uplift − net delist loss + capital reinvestment',e:['Annual margin impact of the optimized range.','Dampak margin tahunan range optimal.'],val:k=>Math.abs(k.marginImpact)},
];
function renderForecast_ASSORT(){
  const k=computeK_ASSORT();const addWeekly=k.marginImpact/52;
  const wks=Math.max(4,Math.min(16,state.horizon));const cur=[],opt=[],labels=[];let cum=0;
  for(let i=0;i<wks;i++){const ramp=Math.min(1,(i+1)/Math.max(4,wks*0.7));cum+=addWeekly*ramp;cur.push(0);opt.push(Math.round(cum));labels.push('W+'+(i+1));}
  multiLine('chart-forecast',[
    {name:T('Current (baseline)','Sekarang (baseline)'),color:'#8A8886',data:cur,dash:'5 4'},
    {name:T('Cumulative uplift','Uplift kumulatif'),color:'#107C41',data:opt},
  ],labels);
  G('forenote').textContent=T(`Cumulative margin uplift vs current range · horizon ${state.horizon}wk · scope: ${scopeShort()}`,`Uplift margin kumulatif vs range sekarang · horizon ${state.horizon}mgg · scope: ${scopeShort()}`);
  G('forecastStats').innerHTML=`<div class="m"><div class="k">${T('Delist','Delist')}</div><b data-fx="assort_delist">${fmt(k.delistCount)}</b></div>
    <div class="m"><div class="k">${T('Grow','Grow')}</div><b data-fx="assort_grow">${fmt(k.growCount)}</b></div>
    <div class="m"><div class="k">GMROI</div><b data-fx="assort_gmroi">${k.gmroiAvg.toFixed(2)}x</b></div>
    <div class="m"><div class="k">${T('Capital freed','Modal bebas')}</div><b data-fx="assort_capital">Rp ${fmt(k.capitalFreed)}</b></div>
    <div class="m"><div class="k">${T('Margin impact','Dampak margin')}</div><b data-fx="assort_impact">Rp ${fmt(k.marginImpact)}</b></div>`;
}
function renderDriver_ASSORT(){
  const list=activeSKUs().map(s=>({s,a:assortMetrics(s)}));assortClassify(list);const im=assortImpact(list);
  barChart('chart-driver',[
    {label:T('Grow uplift','Uplift grow'),value:Math.round(im.growUplift),color:'#107C41',fx:'Σ grow SKU annual GM × 15%'},
    {label:T('Delist loss','Rugi delist'),value:Math.round(im.lost),color:'#D13438',fx:'Σ delist SKU annual GM (before transfer)'},
    {label:T('Demand retained','Demand tertahan'),value:Math.round(im.retained),color:'#0A9ED4',fx:'delist loss × transfer rate (55%)'},
    {label:T('Capital benefit','Manfaat modal'),value:Math.round(im.capitalBenefit),color:'#5C2D91',fx:'capital freed × 20% annual return'},
    {label:T('Net impact','Dampak bersih'),value:Math.round(Math.abs(im.impact)),color:im.impact>=0?'#008575':'#D13438',fx:'grow uplift − net delist loss + capital benefit'},
  ],{pb:44});
}
function renderTrend_ASSORT(){
  const list=activeSKUs().map(s=>({s,a:assortMetrics(s)}));assortClassify(list);
  const pool=list.filter(x=>x.a.delist).sort((a,b)=>a.a.gmroi-b.a.gmroi).slice(0,5);
  const fb=list.slice().sort((a,b)=>a.a.contribution-b.a.contribution).slice(0,5);
  const use=pool.length?pool:fb;
  G('trendlist').innerHTML=use.map(x=>`<div class="trow"><span class="fireicon">${x.a.slow?'🐌':'📉'}</span>
    <div><div class="tn">${x.s.name}</div><div class="tc">${x.s.cat} · ${x.a.tier} · GMROI ${x.a.gmroi.toFixed(2)}x · ${fmt(x.a.velocity)}/d</div></div>
    <div class="tu down">Rp ${fmt(x.a.contribution)}/d</div></div>`).join('')||`<div class="tiny muted">${T('No delist candidate in scope.','Tidak ada kandidat delist di scope.')}</div>`;
}
function renderCat_ASSORT(){
  const data=CATS.map(c=>{const list=SKUS.filter(s=>s.catId===c.id).map(s=>({s,a:assortMetrics(s)}));assortClassify(list);
    const v=list.filter(x=>x.a.delist).length;
    return {label:c.name,value:v,color:CCOLOR[c.id],fx:'delist candidates within this category',
      onclick:()=>{state.itemMode='cat';state.cats=new Set([c.id]);syncSegs();refreshAll();toast('🗂️ '+T('Filtered: ','Filter: ')+c.name);}};});
  barChart('chart-cat',data,{pb:52});
}
function renderStore_ASSORT(){
  const sv={sm:state.storeMode,st:new Set(state.stores)};
  const data=STORES.map(st=>{state.storeMode='sel';state.stores=new Set([st.id]);const k=computeK_ASSORT();
    return {label:st.name.replace('HERO ',''),value:+k.tailShare.toFixed(1),color:'#C77700',fx:'% of SKUs in the bottom-20%-margin tail for this store',
      onclick:()=>{state.storeMode='sel';state.stores=new Set([st.id]);syncSegs();refreshAll();toast('🏪 '+T('Filtered: ','Filter: ')+st.name);}};});
  state.storeMode=sv.sm;state.stores=new Set(sv.st);
  hbarChart('chart-store',data.sort((a,b)=>b.value-a.value));
}
function renderCluster_ASSORT(){
  const cc={Premium:'#5C2D91','Urban Mall':'#0078D4',Suburban:'#008575',Resort:'#C77700'};
  const sv={sm:state.storeMode,st:new Set(state.stores)};
  const data=CLUSTERS.map(cl=>{state.storeMode='sel';state.stores=new Set(STORES.filter(s=>s.cluster===cl).map(s=>s.id));const k=computeK_ASSORT();
    return {label:cl,value:+k.gmroiAvg.toFixed(2),color:cc[cl],fx:'average GMROI for stores in this cluster',
      onclick:()=>{state.storeMode='sel';state.stores=new Set(STORES.filter(s=>s.cluster===cl).map(s=>s.id));syncSegs();refreshAll();toast('🧭 '+T('Cluster: ','Cluster: ')+cl);}};});
  state.storeMode=sv.sm;state.stores=new Set(sv.st);
  barChart('chart-cluster',data,{pb:40});
}
function renderSeason_ASSORT(){
  const list=activeSKUs().map(s=>({s,a:assortMetrics(s)}));assortClassify(list);
  const tiers=['Star','Core','Slow','Tail'];const cols={Star:'#107C41',Core:'#0078D4',Slow:'#C77700',Tail:'#D13438'};
  const data=tiers.map(t=>({label:t,value:list.filter(x=>x.a.tier===t).length,color:cols[t],fx:'number of SKUs in this performance tier'}));
  barChart('chart-season',data,{h:196,pb:26});
}
function renderMatrix_ASSORT(){
  const storeLbl=(state.storeMode==='sel'&&state.stores.size)?(state.stores.size===1?STORES.find(s=>state.stores.has(s.id)).name.replace('HERO ',''):state.stores.size+' stores'):T('All','Semua');
  const list=activeSKUs().map(s=>({s,a:assortMetrics(s)}));assortClassify(list);
  const rec=a=>a.grow?['Grow','direct']:a.delist?['Delist / review','cross']:a.tier==='Core'?['Keep','flow']:['Watch','flow'];
  const rows=list.slice().sort((a,b)=>b.a.contribution-a.a.contribution).slice(0,14);
  G('chart-matrix').innerHTML=`<table class="tbl"><thead><tr>
    <th>SKU</th><th>Item</th><th>Category</th><th>Store</th><th>Tier</th><th>Velocity</th><th>GMROI</th><th>Contribution/d</th><th>Capital</th><th>${T('Recommendation','Rekomendasi')}</th></tr></thead><tbody>
    ${rows.map(({s,a})=>`<tr style="cursor:pointer" onclick="drillSku('${s.id}')">
      <td>${s.id}</td><td style="text-align:left">${s.name}</td>
      <td style="text-align:left"><span class="badge" style="background:${CCOLOR[s.catId]}22;color:${CCOLOR[s.catId]}">${s.cat}</span></td>
      <td style="text-align:left">${storeLbl}</td>
      <td style="text-align:left"><b style="color:${a.tier==='Star'?'#107C41':a.tier==='Tail'?'#D13438':a.tier==='Core'?'#0078D4':'#C77700'}">${a.tier}</b></td>
      <td data-fx="velCell">${fmt(a.velocity)}/d</td>
      <td data-fx="gmroiCell" class="${a.gmroi>=3?'pos-ok':a.gmroi<1.5?'pos-low':''}"><b>${a.gmroi.toFixed(2)}x</b></td>
      <td data-fx="contribCell">Rp ${fmt(a.contribution)}</td>
      <td data-fx="capCell">Rp ${fmt(a.capitalTied)}</td>
      <td style="text-align:left"><span class="route ${rec(a)[1]}">${rec(a)[0]}</span></td></tr>`).join('')}
  </tbody></table>`;
}
function runSim_ASSORT(){
  const execFrac=Math.max(0.2,Math.min(1,0.6+state.sim.price/100)), spaceBoost=state.sim.promo/100,
        transfer=Math.max(0,Math.min(0.95,0.55+state.sim.seas/100)), gmroiCut=2.5+state.sim.viral/60*1.5,
        growInv=state.sim.lead/3, cannib=Math.max(0,(state.sim.safe-2)/100);
  const list=activeSKUs().map(s=>({s,a:assortMetrics(s)}));
  assortClassify(list,{gmroiCut});
  const im=assortImpact(list,{transfer,growInv,cannib,execFrac,spaceBoost});
  const addWeekly=im.impact/52;
  const wks=Math.max(4,Math.min(16,state.horizon));const cur=[],opt=[],labels=[];let cum=0;
  for(let i=0;i<wks;i++){const ramp=Math.min(1,(i+1)/Math.max(4,wks*0.7));cum+=addWeekly*ramp;cur.push(0);opt.push(Math.round(cum));labels.push('W+'+(i+1));}
  multiLine('chart-sim',[{name:T('Current','Sekarang'),color:'#8A8886',data:cur,dash:'5 4'},{name:T('Cumulative uplift','Uplift kumulatif'),color:'#107C41',data:opt}],labels);
  const baseK=computeK_ASSORT();const dBase=baseK.marginImpact!==0?((im.impact/baseK.marginImpact)-1)*100:0;
  simRun={order:im.impact,dDem:dBase,dMgn:im.capitalFreed,svc:im.delistList.length,series:opt};
  G('sim-order').textContent='Rp '+fmt(Math.round(im.impact));
  const dd=G('sim-delta');dd.textContent=pct(dBase);dd.className=dBase>=0?'up':'down';
  const dm=G('sim-margin');dm.textContent='Rp '+fmt(im.capitalFreed);dm.className='up';
  G('sim-svc').textContent=fmt(im.delistList.length);
}
function renderAction_ASSORT(){
  const k=computeK_ASSORT();
  const stTag={pending:'st-pending',approved:'st-approved',rejected:'st-rejected',cancelled:'st-cancelled',reopened:'st-reopened',sent:'st-sent'}[actionState];
  const stTxt={pending:T('Pending','Menunggu'),approved:'Approved',rejected:'Rejected',cancelled:T('Cancelled','Dibatalkan'),reopened:'Reopened',sent:T('Sent →','Terkirim →')}[actionState];
  G('actionbody').innerHTML=`
    <div class="action-card"><div class="ah"><span class="pri high">${T('HIGH PRIORITY','PRIORITAS TINGGI')}</span>
      <b>${T('Approve assortment optimization (delist tail, grow winners)','Setujui optimasi assortment (delist ekor, perbesar juara)')}</b><span class="status-tag ${stTag}">${stTxt}</span></div>
      <div class="tiny muted">${T('Agent proposes','Agent mengusulkan')} <b style="color:#D13438">${fmt(k.delistCount)}</b> ${T('delist &','delist &')} <b style="color:#107C41">${fmt(k.growCount)}</b> ${T('grow · frees','grow · membebaskan')} <b style="color:#0078D4">Rp ${fmt(k.capitalFreed)}</b> ${T('capital.','modal.')}</div>
      <div class="impact">
        <div><span class="muted tiny">${T('Margin impact','Dampak margin')}</span><b class="up" data-fx="assort_impact">Rp ${fmt(k.marginImpact)}</b></div>
        <div><span class="muted tiny">${T('Capital freed','Modal bebas')}</span><b class="up" data-fx="assort_capital">Rp ${fmt(k.capitalFreed)}</b></div>
        <div><span class="muted tiny">GMROI</span><b data-fx="assort_gmroi">${k.gmroiAvg.toFixed(2)}x</b></div>
        <div><span class="muted tiny">${T('Tail share','Porsi ekor')}</span><b class="down" data-fx="assort_tail">${k.tailShare.toFixed(1)}%</b></div></div>
      <div class="agentic-row">
        <button class="abtn approve" onclick="agentic('approved')">✔ ${T('Approve','Setujui')}</button>
        <button class="abtn reject" onclick="agentic('rejected')">✕ ${T('Reject','Tolak')}</button>
        <button class="abtn cancel" onclick="agentic('cancelled')">⊘ ${T('Cancel','Batal')}</button>
        <button class="abtn reopen" onclick="agentic('reopened')">↻ ${T('Reopen','Buka lagi')}</button>
        <button class="btn indigo sm" style="margin-left:auto" onclick="togglePO()">🧬 ${T('Generate Assortment Plan','Buat Rencana Assortment')}</button></div></div>
    <div id="po-preview"></div>`;
}
function toggleAssortPlan(){poOpen=!poOpen;const w=G('po-preview');if(!poOpen){w.innerHTML='';return;}
  const list=activeSKUs().map(s=>({s,a:assortMetrics(s)}));assortClassify(list);
  const rec=a=>a.grow?['Grow','direct']:a.delist?['Delist / review','cross']:a.tier==='Core'?['Keep','flow']:['Watch','flow'];
  const rows=list.filter(x=>x.a.grow||x.a.delist).sort((a,b)=>b.a.contribution-a.a.contribution).slice(0,12)
    .map(({s,a})=>({sku:s.id,name:s.name,cat:s.cat,tier:a.tier,gmroi:a.gmroi,vel:a.velocity,contrib:a.contribution,cap:a.capitalTied,rec:rec(a)}));
  const delistN=rows.filter(r=>r.rec[1]==='cross').length,growN=rows.filter(r=>r.rec[1]==='direct').length;
  w.innerHTML=`<div class="tiny muted" style="margin:2px 0 8px">${T('Assortment plan — delist the tail, grow winners. Publishing to D365 F&O (Released products) goes through the approval workflow. Aligned with the agent recommendation above.','Rencana assortment — delist ekor, perbesar juara. Publikasi ke D365 F&O (Released products) lewat workflow approval. Selaras dengan rekomendasi agent di atas.')}</div>
    <div style="overflow:auto;border:1px solid var(--line);border-radius:11px"><table class="tbl"><thead><tr>
      <th>SKU</th><th>Item</th><th>Category</th><th>Tier</th><th>Velocity</th><th>GMROI</th><th>Contribution/d</th><th>Capital</th><th>${T('Action','Aksi')}</th></tr></thead>
      <tbody>${rows.map(r=>`<tr><td>${r.sku}</td><td style="text-align:left">${r.name}</td><td style="text-align:left"><span class="badge" style="background:${CCOLOR[r.sku.split('-')[0]]}22;color:${CCOLOR[r.sku.split('-')[0]]}">${r.cat}</span></td>
        <td style="text-align:left">${r.tier}</td><td data-fx="velCell">${fmt(r.vel)}/d</td><td data-fx="gmroiCell" class="${r.gmroi>=3?'pos-ok':r.gmroi<1.5?'pos-low':''}"><b>${r.gmroi.toFixed(2)}x</b></td>
        <td data-fx="contribCell">Rp ${fmt(r.contrib)}</td><td data-fx="capCell">Rp ${fmt(r.cap)}</td>
        <td style="text-align:left"><span class="route ${r.rec[1]}">${r.rec[0]}</span></td></tr>`).join('')}</tbody></table></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:9px">
      <button class="btn teal sm" onclick="releaseOrHandoff('${growN+' '+T('grow','grow')+' · '+delistN+' '+T('delist','delist')}')">➤ ${T('Publish assortment to D365 F&O','Publikasikan assortment ke D365 F&O')}</button>
      <button class="btn sm" onclick='exportAssortPlan(${JSON.stringify(rows)})'>⬇ ${T('Export to Excel','Export ke Excel')}</button></div>`;
}
function exportAssortPlan(rows){const h=['SKU','Item','Category','Tier','Velocity','GMROI','Contribution/d','Capital','Action'];
  downloadCSV('AI360_Assortment_Plan.csv',[h,...rows.map(r=>[r.sku,r.name,r.cat,r.tier,r.vel,r.gmroi.toFixed(2)+'x',r.contrib,r.cap,r.rec[0]])]);toast('⬇ '+T('Exported','Diekspor'));}
function aiReply_ASSORT(q){const k=computeK_ASSORT();const ql=q.toLowerCase();const ch=CHALLENGE;
  if(ql.includes('gmroi')||(ch&&ql.includes('delist'))){
    addMsg('ai',`${T('Delisting frees capital, but only helps if demand transfers to the remaining range:','Delist membebaskan modal, tapi hanya membantu jika demand berpindah ke range yang tersisa:')}
      <div class="calcbox">GMROI = annual GM ÷ avg inventory at cost
avg GMROI in scope = ${k.gmroiAvg.toFixed(2)}x
capital freed by delisting = Rp ${fmt(k.capitalFreed)}</div>
      ${T('Challenge: if a tail SKU is a basket-builder (customers come for it), delisting can lose the whole basket. Check attachment/loyalty before cutting.','Challenge: kalau SKU ekor adalah basket-builder (pelanggan datang untuk itu), delist bisa kehilangan seluruh basket. Cek attachment/loyalty sebelum memangkas.')}`,true);
  }else if(ql.includes('delist')||ql.includes('cut')||ql.includes('tail')){
    const rows=k.delistList.slice().sort((a,b)=>a.a.gmroi-b.a.gmroi).slice(0,4);
    addMsg('ai',`${T('Delist candidates:','Kandidat delist:')} <b>${fmt(k.delistCount)}</b> · ${T('tail share','porsi ekor')} <b>${k.tailShare.toFixed(1)}%</b>
      <div class="calcbox">delist if  slow-mover  OR  (bottom-20%-margin tail  &  GMROI < 1.5)</div>
      <table class="mini-table"><thead><tr><th>Item</th><th>GMROI</th><th>Vel</th><th>Contrib/d</th></tr></thead><tbody>
      ${rows.map(x=>`<tr><td>${x.s.name}</td><td>${x.a.gmroi.toFixed(2)}x</td><td>${fmt(x.a.velocity)}</td><td>Rp ${fmt(x.a.contribution)}</td></tr>`).join('')||('<tr><td colspan=4>'+T('None in scope','Tidak ada')+'</td></tr>')}</tbody></table>`,ch);
  }else if(ql.includes('grow')||ql.includes('winner')||ql.includes('space')){
    addMsg('ai',`${T('Grow candidates:','Kandidat grow:')} <b>${fmt(k.growCount)}</b> ${T('winners to expand.','juara untuk diperbesar.')}
      <div class="calcbox">grow = top SKUs by daily margin contribution · +15% from more facings/space</div>
      ${T('Reinvest freed tail space into these to lift margin per shelf-metre.','Alihkan ruang ekor yang dibebaskan ke SKU ini untuk menaikkan margin per meter rak.')}`,ch);
  }else if(ql.includes('impact')||ql.includes('publish')||ql.includes('plan')||ql.includes('d365')||ql.includes('next')){
    addMsg('ai',`${T('Annual margin impact of the optimized range:','Dampak margin tahunan range optimal:')} <b>Rp ${fmt(k.marginImpact)}</b>
      <div class="calcbox">impact = grow uplift − net delist loss + capital reinvestment</div>
      ${T('Publishing to D365 F&O (Released products) requires approval by margin-impact authority (SoA).','Publikasi ke D365 F&O (Released products) butuh approval berdasarkan otoritas dampak margin (SoA).')}
      <div style="margin-top:7px"><button class="btn indigo sm" onclick="togglePO();document.querySelector('[data-sec=action]').scrollIntoView({behavior:'smooth'})">🧬 ${T('Open assortment plan','Buka rencana assortment')}</button></div>`,ch);
  }else if(ql.includes('explain')){
    addMsg('ai',T('Hover any number to see its formula. Delist candidates include the slow-movers routed here from Pricing & Markdown, so the range decision reconciles with the earlier agents.','Arahkan kursor ke angka mana pun untuk formula. Kandidat delist mencakup slow-mover yang dirutekan dari Pricing & Markdown, jadi keputusan range konsisten dengan agent sebelumnya.'),ch);
  }else{
    addMsg('ai',T('I can explain delist candidates, grow winners, GMROI, tail share, capital freed, margin impact, and publishing to D365 F&O. Turn on Challenge mode to pressure-test a delist.','Saya bisa jelaskan kandidat delist, grow juara, GMROI, porsi ekor, modal bebas, dampak margin, dan publikasi ke D365 F&O. Nyalakan Challenge mode untuk menguji delist.'),ch);
  }
}
const CHIPS_ASSORT=[['What should we delist?','Apa yang harus di-delist?',0],['Which winners to grow?','Juara mana untuk diperbesar?',0],['Show margin impact','Tampilkan dampak margin',0],['Open assortment plan','Buka rencana assortment',0]];
const CHIPS_CH_ASSORT=[['Challenge the delist (basket effect)','Tantang delist (efek basket)',1],['Challenge GMROI on fresh','Tantang GMROI di fresh',1],['Stress-test if demand does not transfer','Stress-test kalau demand tak berpindah',1]];
/* ================= END ASSORTMENT OPTIMIZATION ================= */


/* ================= AI EXPLANATION & SUMMARY AGENT (reads live from every agent) ================= */
Object.assign(FX,{
 ai_acc:{t:['Forecast Accuracy','Akurasi Forecast'],f:'from Agent 1 · 100% − MAPE',e:['Same value as Demand Forecasting.','Nilai sama dengan Demand Forecasting.']},
 ai_stockout:{t:['Stockout-Risk SKUs','SKU Risiko Stockout'],f:'from Agent 2 · count(Position < ROP)',e:['Same value as Inventory Risk.','Nilai sama dengan Inventory Risk.']},
 ai_po:{t:['Replenishment Value','Nilai Replenishment'],f:'from Agent 3 · Σ(Max − Position) × price',e:['Same value as Replenishment.','Nilai sama dengan Replenishment.']},
 ai_roi:{t:['Promo ROI','ROI Promo'],f:'from Agent 4 · incr margin ÷ net cost',e:['Same value as Promotion Effectiveness.','Nilai sama dengan Promotion Effectiveness.']},
 ai_recover:{t:['Markdown Recovery','Recovery Markdown'],f:'from Agent 5 · Σ cleared × markdown price',e:['Same value as Pricing & Markdown.','Nilai sama dengan Pricing & Markdown.']},
 ai_assort:{t:['Assortment Impact','Dampak Assortment'],f:'from Agent 6 · annual margin impact',e:['Same value as Assortment Optimization.','Nilai sama dengan Assortment Optimization.']},
 ai_total:{t:['Total Value','Total Nilai'],f:'promo×26 + markdown×12 + assortment + service (per year)',e:['Identified annual value across the pipeline.','Nilai tahunan teridentifikasi di seluruh pipeline.']},
 ai_dbase:{t:['Δ vs base','Δ vs base'],f:'( scenario total value ÷ base ) − 1',e:['Change in total pipeline value under levers.','Perubahan total nilai pipeline di simulasi.']},
 ai_margin:{t:['Margin Impact','Dampak Margin'],f:'assortment annual margin impact',e:['Annual margin from range optimization.','Margin tahunan dari optimasi range.']},
 ai_service:{t:['Service','Service'],f:'avoided lost-margin from preventing stockouts',e:['Value of protecting availability.','Nilai menjaga ketersediaan.']}
});
function computeK_AI(){
  const daily=genDaily();
  const df=computeK_DF(),inv=computeK_INV(),rep=computeK_REP(),promo=computeK_PROMO(),pm=computeK_PM(),assort=computeK_ASSORT();
  const list=activeSKUs().map(s=>({s,a:assortMetrics(s)}));const n=Math.max(1,list.length);
  const avgDailyGM=list.reduce((a,x)=>a+x.a.annualGM,0)/365/n;
  const basePromo=Math.round((promo.incrMargin||0)*26);      // ~26 bi-weekly campaigns/yr
  const baseMkdn=Math.round((pm.recoverTot||0)*12);          // ~12 markdown cycles/yr
  const baseAssort=Math.round(assort.marginImpact||0);       // already annual
  const baseSvc=Math.round(inv.stockout*avgDailyGM*30);      // 30 days avoided lost margin
  const totalValue=basePromo+baseMkdn+baseAssort+baseSvc;
  return {acc:df.acc,stockout:inv.stockout,orderValue:rep.orderValue,roi:promo.roi,recover:pm.recoverTot,marginImpact:assort.marginImpact,
    basePromo,baseMkdn,baseAssort,baseSvc,totalValue,capitalFreed:assort.capitalFreed,
    df,inv,rep,promo,pm,assort,daily};
}
const KPIDEFS_AI=[
  {key:'acc',color:'#0078D4',lab:['1 · Forecast Accuracy','1 · Akurasi Forecast'],fmt:k=>k.acc.toFixed(1)+'%',delta:k=>T('Demand Forecasting','Demand Forecasting'),dcls:()=>'up',
   f:'from Agent 1 · 100% − MAPE',e:['Identical to Demand Forecasting.','Sama dengan Demand Forecasting.'],val:k=>k.acc},
  {key:'stockout',color:'#D13438',lab:['2 · Stockout-Risk SKUs','2 · SKU Risiko Stockout'],fmt:k=>fmt(k.stockout),delta:k=>T('Inventory Risk','Inventory Risk'),dcls:()=>'down',
   f:'from Agent 2 · count(Position < ROP)',e:['Identical to Inventory Risk.','Sama dengan Inventory Risk.'],val:k=>k.stockout},
  {key:'orderValue',color:'#C77700',lab:['3 · Replenishment Value','3 · Nilai Replenishment'],fmt:k=>'Rp '+fmt(k.orderValue),delta:k=>T('Replenishment','Replenishment'),dcls:()=>'',
   f:'from Agent 3 · Σ(Max − Position) × price',e:['Identical to Replenishment.','Sama dengan Replenishment.'],val:k=>k.orderValue},
  {key:'roi',color:'#008575',lab:['4 · Promo ROI','4 · ROI Promo'],fmt:k=>k.roi.toFixed(2)+'x',delta:k=>T('Promotion','Promotion'),dcls:k=>k.roi>=1?'up':'down',
   f:'from Agent 4 · incr margin ÷ net cost',e:['Identical to Promotion Effectiveness.','Sama dengan Promotion Effectiveness.'],val:k=>k.roi},
  {key:'recover',color:'#5C2D91',lab:['5 · Markdown Recovery','5 · Recovery Markdown'],fmt:k=>'Rp '+fmt(k.recover),delta:k=>T('Pricing & Markdown','Pricing & Markdown'),dcls:()=>'up',
   f:'from Agent 5 · Σ cleared × markdown price',e:['Identical to Pricing & Markdown.','Sama dengan Pricing & Markdown.'],val:k=>k.recover},
  {key:'marginImpact',color:'#107C41',lab:['6 · Assortment Impact','6 · Dampak Assortment'],fmt:k=>'Rp '+fmt(k.marginImpact),delta:k=>T('Assortment','Assortment'),dcls:()=>'up',
   f:'from Agent 6 · annual margin impact',e:['Identical to Assortment Optimization.','Sama dengan Assortment Optimization.'],val:k=>Math.abs(k.marginImpact)},
];
const AGENT_META=[
  {key:'df',n:1,name:['Demand Forecasting','Demand Forecasting'],col:'#0078D4'},
  {key:'inv',n:2,name:['Inventory Risk','Inventory Risk'],col:'#D13438'},
  {key:'rep',n:3,name:['Replenishment','Replenishment'],col:'#C77700'},
  {key:'promo',n:4,name:['Promotion Effectiveness','Promotion Effectiveness'],col:'#008575'},
  {key:'pm',n:5,name:['Pricing & Markdown','Pricing & Markdown'],col:'#5C2D91'},
  {key:'assort',n:6,name:['Assortment Optimization','Assortment Optimization'],col:'#107C41'},
];
function renderForecast_AI(){
  const k=computeK_AI();const addWeekly=k.totalValue/52;
  const wks=Math.max(4,Math.min(16,state.horizon));const base=[],ai=[],labels=[];let cum=0;
  for(let i=0;i<wks;i++){const ramp=Math.min(1,(i+1)/Math.max(4,wks*0.7));cum+=addWeekly*ramp;base.push(0);ai.push(Math.round(cum));labels.push('W+'+(i+1));}
  multiLine('chart-forecast',[
    {name:T('No AI (baseline)','Tanpa AI (baseline)'),color:'#8A8886',data:base,dash:'5 4'},
    {name:T('With AI Retail 360','Dengan AI Retail 360'),color:'#107C41',data:ai},
  ],labels);
  G('forenote').textContent=T(`Cumulative value captured across the 6-agent pipeline · horizon ${state.horizon}wk · scope: ${scopeShort()}`,`Nilai kumulatif dari pipeline 6-agent · horizon ${state.horizon}mgg · scope: ${scopeShort()}`);
  G('forecastStats').innerHTML=`<div class="m"><div class="k">${T('Total value/yr','Total nilai/thn')}</div><b data-fx="ai_total">Rp ${fmt(k.totalValue)}</b></div>
    <div class="m"><div class="k">${T('Promotion','Promotion')}</div><b>Rp ${fmt(k.basePromo)}</b></div>
    <div class="m"><div class="k">${T('Markdown','Markdown')}</div><b>Rp ${fmt(k.baseMkdn)}</b></div>
    <div class="m"><div class="k">${T('Assortment','Assortment')}</div><b data-fx="ai_margin">Rp ${fmt(k.baseAssort)}</b></div>
    <div class="m"><div class="k">${T('Service','Service')}</div><b data-fx="ai_service">Rp ${fmt(k.baseSvc)}</b></div>`;
}
function renderDriver_AI(){
  const k=computeK_AI();
  barChart('chart-driver',[
    {label:T('Promotion','Promo'),value:k.basePromo,color:'#008575',fx:'incremental margin × ~26 campaigns/yr'},
    {label:T('Markdown','Markdown'),value:k.baseMkdn,color:'#5C2D91',fx:'markdown recovery × ~12 cycles/yr'},
    {label:T('Assortment','Assortment'),value:k.baseAssort,color:'#107C41',fx:'annual margin impact of optimized range'},
    {label:T('Service','Service'),value:k.baseSvc,color:'#0078D4',fx:'avoided lost margin from preventing stockouts'},
  ],{pb:40});
}
function renderTrend_AI(){
  const k=computeK_AI();
  const heads={df:k.acc.toFixed(1)+'% acc',inv:fmt(k.stockout)+' stockout',rep:'Rp '+fmt(k.orderValue),promo:k.roi.toFixed(2)+'x ROI',pm:'Rp '+fmt(k.recover),assort:'Rp '+fmt(k.marginImpact)};
  const ok={df:k.acc>=85,inv:k.stockout<=8,rep:true,promo:k.roi>=1,pm:k.recover>0,assort:k.marginImpact>0};
  G('trendlist').innerHTML=AGENT_META.map(m=>`<div class="trow" style="cursor:pointer" onclick="setAgent('${m.key}')"><span class="fireicon" style="background:${m.col}22;color:${m.col};border-radius:6px">${m.n}</span>
    <div><div class="tn">${T(m.name[0],m.name[1])}</div><div class="tc">${heads[m.key]}</div></div>
    <div class="tu ${ok[m.key]?'up':'down'}">${ok[m.key]?'✓':'!'}</div></div>`).join('');
}
function renderCat_AI(){
  const sv={im:state.itemMode,ct:new Set(state.cats)};
  const data=CATS.map(c=>{state.itemMode='cat';state.cats=new Set([c.id]);const k=computeK_AI();
    return {label:c.name,value:Math.round(k.totalValue),color:CCOLOR[c.id],fx:'total identified annual value for this category',
      onclick:()=>{state.itemMode='cat';state.cats=new Set([c.id]);syncSegs();refreshAll();toast('🗂️ '+T('Filtered: ','Filter: ')+c.name);}};});
  Object.assign(state,{itemMode:sv.im});state.cats=new Set(sv.ct);
  barChart('chart-cat',data,{pb:52});
}
function renderStore_AI(){
  const sv={sm:state.storeMode,st:new Set(state.stores)};
  const data=STORES.map(st=>{state.storeMode='sel';state.stores=new Set([st.id]);const k=computeK_AI();
    return {label:st.name.replace('HERO ',''),value:Math.round(k.totalValue),color:'#0078D4',fx:'total identified annual value for this store',
      onclick:()=>{state.storeMode='sel';state.stores=new Set([st.id]);syncSegs();refreshAll();toast('🏪 '+T('Filtered: ','Filter: ')+st.name);}};});
  state.storeMode=sv.sm;state.stores=new Set(sv.st);
  hbarChart('chart-store',data.sort((a,b)=>b.value-a.value));
}
function renderCluster_AI(){
  const cc={Premium:'#5C2D91','Urban Mall':'#0078D4',Suburban:'#008575',Resort:'#C77700'};
  const sv={sm:state.storeMode,st:new Set(state.stores)};
  const data=CLUSTERS.map(cl=>{state.storeMode='sel';state.stores=new Set(STORES.filter(s=>s.cluster===cl).map(s=>s.id));const k=computeK_AI();
    return {label:cl,value:Math.round(k.totalValue),color:cc[cl],fx:'total identified annual value for this cluster',
      onclick:()=>{state.storeMode='sel';state.stores=new Set(STORES.filter(s=>s.cluster===cl).map(s=>s.id));syncSegs();refreshAll();toast('🧭 '+T('Cluster: ','Cluster: ')+cl);}};});
  state.storeMode=sv.sm;state.stores=new Set(sv.st);
  barChart('chart-cluster',data,{pb:40});
}
function renderSeason_AI(){
  const conf={df:88,inv:92,rep:90,promo:82,pm:85,assort:80};   // illustrative model confidence per agent
  const data=AGENT_META.map(m=>({label:m.n+'·'+T(m.name[0],m.name[1]).split(' ')[0],value:conf[m.key],color:m.col,fx:'illustrative model confidence for this agent (sample)'}));
  barChart('chart-season',data,{h:196,pb:40});
}
function renderMatrix_AI(){
  const k=computeK_AI();
  const rows=[
    {m:AGENT_META[0],dec:['Forecast demand & flag trend','Forecast demand & tandai trend'],num:k.acc.toFixed(1)+'% acc',ho:['→ Replenishment','→ Replenishment']},
    {m:AGENT_META[1],dec:['Flag stockout / overstock / expiry','Tandai stockout / overstock / expiry'],num:fmt(k.stockout)+' at risk',ho:['→ Replenishment / Pricing','→ Replenishment / Pricing']},
    {m:AGENT_META[2],dec:['Build PO by 3 routes','Susun PO 3 rute'],num:'Rp '+fmt(k.orderValue),ho:['→ D365 F&O (approval)','→ D365 F&O (approval)']},
    {m:AGENT_META[3],dec:['Scale winners, stop losers','Perbesar juara, stop rugi'],num:k.roi.toFixed(2)+'x ROI',ho:['→ Pricing & Markdown','→ Pricing & Markdown']},
    {m:AGENT_META[4],dec:['Markdown at-risk, route slow-movers','Markdown berisiko, rutekan slow-mover'],num:'Rp '+fmt(k.recover),ho:['→ Assortment','→ Assortment']},
    {m:AGENT_META[5],dec:['Delist tail, grow winners','Delist ekor, perbesar juara'],num:'Rp '+fmt(k.marginImpact)+'/yr',ho:['→ D365 F&O (approval)','→ D365 F&O (approval)']},
  ];
  G('chart-matrix').innerHTML=`<table class="tbl"><thead><tr>
    <th>#</th><th>Agent</th><th>${T('Decision','Keputusan')}</th><th>${T('Key number','Angka kunci')}</th><th>${T('Handoff','Estafet')}</th><th>${T('Open','Buka')}</th></tr></thead><tbody>
    ${rows.map(r=>`<tr style="cursor:pointer" onclick="setAgent('${r.m.key}')">
      <td><b style="color:${r.m.col}">${r.m.n}</b></td>
      <td style="text-align:left"><b>${T(r.m.name[0],r.m.name[1])}</b></td>
      <td style="text-align:left">${T(r.dec[0],r.dec[1])}</td>
      <td style="text-align:left"><b>${r.num}</b></td>
      <td style="text-align:left">${T(r.ho[0],r.ho[1])}</td>
      <td style="text-align:left"><span class="route flow">${T('Open','Buka')}</span></td></tr>`).join('')}
  </tbody></table>`;
}
function runSim_AI(){
  const dDem=state.sim.price/100, svcT=state.sim.promo/100, promoInt=state.sim.seas/100,
        mkdnInt=state.sim.viral/100, growAgg=state.sim.lead/3, inflation=Math.max(0,(state.sim.safe-2)/100);
  const k=computeK_AI();
  const promoVal=k.basePromo*(1+dDem)*(1+promoInt);
  const svcVal=k.baseSvc*(1+svcT);
  const mkdnVal=k.baseMkdn*(1+mkdnInt);
  const assortVal=k.baseAssort*growAgg;
  const total=Math.round((promoVal+svcVal+mkdnVal+assortVal)*(1-inflation));
  const wks=Math.max(4,Math.min(16,state.horizon));const base=[],ai=[],labels=[];let cum=0;const addWeekly=total/52;
  for(let i=0;i<wks;i++){const ramp=Math.min(1,(i+1)/Math.max(4,wks*0.7));cum+=addWeekly*ramp;base.push(0);ai.push(Math.round(cum));labels.push('W+'+(i+1));}
  multiLine('chart-sim',[{name:T('No AI','Tanpa AI'),color:'#8A8886',data:base,dash:'5 4'},{name:T('With AI','Dengan AI'),color:'#107C41',data:ai}],labels);
  const dBase=k.totalValue!==0?((total/k.totalValue)-1)*100:0;
  simRun={order:total,dDem:dBase,dMgn:Math.round(assortVal),svc:Math.round((svcVal))+0,series:ai};
  G('sim-order').textContent='Rp '+fmt(total);
  const dd=G('sim-delta');dd.textContent=pct(dBase);dd.className=dBase>=0?'up':'down';
  const dm=G('sim-margin');dm.textContent='Rp '+fmt(Math.round(assortVal));dm.className='up';
  G('sim-svc').textContent='Rp '+fmt(Math.round(svcVal));
}
function renderAction_AI(){
  const k=computeK_AI();
  const stTag={pending:'st-pending',approved:'st-approved',rejected:'st-rejected',cancelled:'st-cancelled',reopened:'st-reopened',sent:'st-sent'}[actionState];
  const stTxt={pending:T('Pending','Menunggu'),approved:'Approved',rejected:'Rejected',cancelled:T('Cancelled','Dibatalkan'),reopened:'Reopened',sent:T('Sent →','Terkirim →')}[actionState];
  G('actionbody').innerHTML=`
    <div class="action-card"><div class="ah"><span class="pri high">${T('EXECUTIVE','EKSEKUTIF')}</span>
      <b>${T('Approve & publish the end-to-end AI Retail 360 plan','Setujui & publikasikan rencana AI Retail 360 end-to-end')}</b><span class="status-tag ${stTag}">${stTxt}</span></div>
      <div class="tiny muted">${T('Consolidated from 6 agents · identified annual value','Konsolidasi dari 6 agent · nilai tahunan teridentifikasi')} <b style="color:#107C41">Rp ${fmt(k.totalValue)}</b>. ${T('Reporting only — D365 commits already approved at Replenishment & Assortment.','Hanya pelaporan — commit D365 sudah di-approve di Replenishment & Assortment.')}</div>
      <div class="impact">
        <div><span class="muted tiny">${T('Total value/yr','Total nilai/thn')}</span><b class="up" data-fx="ai_total">Rp ${fmt(k.totalValue)}</b></div>
        <div><span class="muted tiny">${T('Capital freed','Modal bebas')}</span><b class="up">Rp ${fmt(k.capitalFreed)}</b></div>
        <div><span class="muted tiny">Promo ROI</span><b data-fx="ai_roi">${k.roi.toFixed(2)}x</b></div>
        <div><span class="muted tiny">${T('Forecast acc','Akurasi')}</span><b data-fx="ai_acc">${k.acc.toFixed(1)}%</b></div></div>
      <div class="agentic-row">
        <button class="abtn approve" onclick="agentic('approved')">✔ ${T('Approve','Setujui')}</button>
        <button class="abtn reject" onclick="agentic('rejected')">✕ ${T('Reject','Tolak')}</button>
        <button class="abtn cancel" onclick="agentic('cancelled')">⊘ ${T('Cancel','Batal')}</button>
        <button class="abtn reopen" onclick="agentic('reopened')">↻ ${T('Reopen','Buka lagi')}</button>
        <button class="btn indigo sm" style="margin-left:auto" onclick="togglePO()">🧠 ${T('Generate Executive Summary','Buat Ringkasan Eksekutif')}</button></div></div>
    <div id="po-preview"></div>`;
}
function toggleAISummary(){poOpen=!poOpen;const w=G('po-preview');if(!poOpen){w.innerHTML='';return;}
  const k=computeK_AI();
  const rows=[
    ['1',T('Demand Forecasting','Demand Forecasting'),k.acc.toFixed(1)+'% '+T('accuracy','akurasi'),T('Forecast + trend signal','Forecast + sinyal trend')],
    ['2',T('Inventory Risk','Inventory Risk'),fmt(k.stockout)+' '+T('at-risk SKUs','SKU berisiko'),T('Stockout / overstock / expiry','Stockout / overstock / expiry')],
    ['3',T('Replenishment','Replenishment'),'Rp '+fmt(k.orderValue),T('PO by 3 routes → D365 (approved)','PO 3 rute → D365 (approved)')],
    ['4',T('Promotion','Promotion'),k.roi.toFixed(2)+'x ROI',T('Scale winners / stop losers','Perbesar juara / stop rugi')],
    ['5',T('Pricing & Markdown','Pricing & Markdown'),'Rp '+fmt(k.recover),T('Recover at-risk value','Selamatkan nilai berisiko')],
    ['6',T('Assortment Optimization','Assortment Optimization'),'Rp '+fmt(k.marginImpact)+'/yr',T('Delist tail / grow winners → D365 (approved)','Delist ekor / grow juara → D365 (approved)')],
  ];
  w.innerHTML=`<div class="tiny muted" style="margin:2px 0 8px">${T('Executive board pack — consolidated decisions & value from all 6 agents. Every number reads live from the same shared engine, so it reconciles with each agent.','Board pack eksekutif — konsolidasi keputusan & nilai dari 6 agent. Setiap angka dibaca langsung dari engine yang sama, jadi konsisten dengan tiap agent.')}</div>
    <div style="overflow:auto;border:1px solid var(--line);border-radius:11px"><table class="tbl"><thead><tr>
      <th>#</th><th>Agent</th><th>${T('Key number','Angka kunci')}</th><th>${T('Decision','Keputusan')}</th></tr></thead>
      <tbody>${rows.map(r=>`<tr><td><b>${r[0]}</b></td><td style="text-align:left">${r[1]}</td><td style="text-align:left"><b>${r[2]}</b></td><td style="text-align:left">${r[3]}</td></tr>`).join('')}
      <tr style="background:#f4fbf5"><td></td><td style="text-align:left"><b>${T('TOTAL identified value / yr','TOTAL nilai teridentifikasi / thn')}</b></td><td style="text-align:left"><b style="color:#107C41">Rp ${fmt(k.totalValue)}</b></td><td style="text-align:left">${T('Approve to publish','Setujui untuk publikasi')}</td></tr></tbody></table></div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:9px">
      <button class="btn teal sm" onclick="sendHandoff('${T('board pack','board pack')+' · Rp '+fmt(k.totalValue)+'/yr'}')">➤ ${T('Publish executive summary','Publikasikan ringkasan eksekutif')}</button>
      <button class="btn sm" onclick='exportAISummary(${JSON.stringify(rows)})'>⬇ ${T('Export to Excel','Export ke Excel')}</button></div>`;
}
function exportAISummary(rows){const h=['#','Agent','Key number','Decision'];
  downloadCSV('AI360_Executive_Summary.csv',[h,...rows.map(r=>[r[0],r[1],r[2],r[3]])]);toast('⬇ '+T('Exported','Diekspor'));}
function aiReply_AI(q){const k=computeK_AI();const ql=q.toLowerCase();const ch=CHALLENGE;
  if(ql.includes('value')||ql.includes('worth')||ql.includes('roi')||ql.includes('money')){
    addMsg('ai',`${T('Identified annual value across the 6-agent pipeline:','Nilai tahunan teridentifikasi di pipeline 6-agent:')} <b>Rp ${fmt(k.totalValue)}</b>
      <div class="calcbox">Promotion  Rp ${fmt(k.basePromo)}
Markdown   Rp ${fmt(k.baseMkdn)}
Assortment Rp ${fmt(k.baseAssort)}
Service    Rp ${fmt(k.baseSvc)}</div>
      ${ch?T('Challenge: promo & markdown are annualized from cycle figures — validate cycle frequency before quoting to the board.','Challenge: promo & markdown disetahunkan dari angka per siklus — validasi frekuensi siklus sebelum dikutip ke board.'):T('Each line reads live from its agent, so it reconciles end-to-end.','Tiap baris dibaca langsung dari agentnya, jadi konsisten end-to-end.')}`,ch);
  }else if(ql.includes('explain')||ql.includes('how')||ql.includes('why')||ql.includes('chain')||ql.includes('reconcile')){
    addMsg('ai',`${T('How the pipeline reconciles:','Bagaimana pipeline konsisten:')}
      <div class="calcbox">1 Forecast → 2 Inventory risk → 3 Replenishment (PO→D365)
4 Promotion → 5 Markdown → 6 Assortment (→D365)
7 Summary reads all six via the SAME invMetrics engine</div>
      ${T('Example: Apple Fuji @ Kemang shows the same Position 52 / ROP 67 in every agent because they all derive from one shared calculation.','Contoh: Apple Fuji @ Kemang menampilkan Position 52 / ROP 67 yang sama di tiap agent karena semua berasal dari satu perhitungan bersama.')}`,ch);
  }else if(ql.includes('confidence')||ql.includes('accura')||ql.includes('trust')||ql.includes('verif')){
    addMsg('ai',`${T('Forecast accuracy','Akurasi forecast')} <b>${k.acc.toFixed(1)}%</b> · ${T('Promo ROI','ROI Promo')} <b>${k.roi.toFixed(2)}x</b>.
      ${T('Confidence varies by agent (see the Confidence chart). Promotion & assortment carry more assumptions, so treat those as directional and validate against actuals.','Confidence berbeda per agent (lihat chart Confidence). Promotion & assortment lebih banyak asumsi, jadi anggap directional dan validasi dengan aktual.')}`,ch);
  }else if(ql.includes('approve')||ql.includes('publish')||ql.includes('summary')||ql.includes('board')||ql.includes('next')){
    addMsg('ai',`${T('The executive summary consolidates all six agents. Publishing is reporting only — the D365 commits (PO, assortment) were already approved in their own workflows.','Ringkasan eksekutif mengonsolidasi enam agent. Publikasi hanya pelaporan — commit D365 (PO, assortment) sudah di-approve di workflow masing-masing.')}
      <div style="margin-top:7px"><button class="btn indigo sm" onclick="togglePO();document.querySelector('[data-sec=action]').scrollIntoView({behavior:'smooth'})">🧠 ${T('Open executive summary','Buka ringkasan eksekutif')}</button></div>`,ch);
  }else{
    addMsg('ai',T('I summarize and explain the whole pipeline: total value, per-agent headlines, the decision chain, confidence, and how the numbers reconcile. Ask about value, how it reconciles, or confidence.','Saya meringkas & menjelaskan seluruh pipeline: total nilai, headline tiap agent, rantai keputusan, confidence, dan bagaimana angkanya konsisten. Tanya soal nilai, konsistensi, atau confidence.'),ch);
  }
}
const CHIPS_AI=[['What is the total value?','Berapa total nilainya?',0],['How does it all reconcile?','Bagaimana semua konsisten?',0],['Show the executive summary','Tampilkan ringkasan eksekutif',0],['Confidence & what to verify','Confidence & yang perlu diverifikasi',0]];
const CHIPS_CH_AI=[['Challenge the annualized value','Tantang nilai yang disetahunkan',1],['Challenge the confidence levels','Tantang level confidence',1],['Which numbers need validation?','Angka mana yang perlu validasi?',1]];
/* ================= END AI EXPLANATION & SUMMARY ================= */


/* ---------- drawer ---------- */
function openDrawer(def,k){
  const lab=T(def.lab[0],def.lab[1]);
  G('drawer-title').textContent=lab;
  G('drawer-sub').textContent=T('Drill-down by store & category · ','Rincian per toko & kategori · ')+scopeShort();
  const sv={sm:state.storeMode,st:new Set(state.stores),im:state.itemMode,ct:new Set(state.cats),sk:new Set(state.skus)};
  const num=v=>Math.abs(Number(v)||0);
  // by store (keep item filter, vary store one-by-one)
  const storeRows=STORES.map(s=>{state.storeMode='sel';state.stores=new Set([s.id]);const kk=computeK();return {id:s.id,label:s.name.replace('HERO ',''),disp:def.fmt(kk),val:num(def.val(kk))};});
  state.storeMode=sv.sm;state.stores=new Set(sv.st);
  // by category (keep store scope, vary category)
  const catRows=CATS.map(c=>{state.itemMode='cat';state.cats=new Set([c.id]);const kk=computeK();return {id:c.id,label:c.name,disp:def.fmt(kk),val:num(def.val(kk)),color:CCOLOR[c.id]};});
  Object.assign(state,{storeMode:sv.sm,itemMode:sv.im});state.stores=new Set(sv.st);state.cats=new Set(sv.ct);state.skus=new Set(sv.sk);
  const maxS=storeRows.reduce((a,r)=>r.val>a.val?r:a,storeRows[0]), minS=storeRows.reduce((a,r)=>r.val<a.val?r:a,storeRows[0]);
  G('drawer-body').innerHTML=`
    <div class="formula" style="background:#F0FdFb;border:1px solid #bdeee9;border-radius:8px;padding:8px;font-family:ui-monospace;font-size:11px;color:#0a6b64;margin-bottom:8px">${def.f}</div>
    <div class="tiny muted" style="margin-bottom:12px">${T('Current','Sekarang')}: <b style="color:var(--ink)">${def.fmt(k)}</b> · ${scopeShort()} &nbsp;|&nbsp; ${T('Highest','Tertinggi')}: <b style="color:var(--ink)">${maxS.label} (${maxS.disp})</b> · ${T('Lowest','Terendah')}: <b style="color:var(--ink)">${minS.label} (${minS.disp})</b></div>
    <div class="panel" style="margin-bottom:10px"><div class="chart-h"><div class="t">${lab} — ${T('by Store','per Toko')}</div><span class="hint">${T('click a store to filter','klik toko untuk filter')}</span></div><div class="chartbody"><div id="drawer-chart"></div></div></div>
    <table class="tbl" style="margin-bottom:16px"><thead><tr><th>${T('Store','Toko')}</th><th>${lab}</th></tr></thead><tbody>${storeRows.map(r=>`<tr style="cursor:pointer" onclick="drillStore('${r.id}')"><td style="text-align:left">${r.label}</td><td>${r.disp}</td></tr>`).join('')}</tbody></table>
    <div class="panel" style="margin-bottom:10px"><div class="chart-h"><div class="t">${lab} — ${T('by Category','per Kategori')}</div><span class="hint">${T('click a category to filter','klik kategori untuk filter')}</span></div><div class="chartbody"><div id="drawer-chart2"></div></div></div>
    <table class="tbl"><thead><tr><th>${T('Category','Kategori')}</th><th>${lab}</th></tr></thead><tbody>${catRows.map(r=>`<tr style="cursor:pointer" onclick="drillCat('${r.id}')"><td style="text-align:left"><span class="badge" style="background:${r.color}22;color:${r.color}">${r.label}</span></td><td>${r.disp}</td></tr>`).join('')}</tbody></table>
    <div class="simbtns" style="margin-top:14px"><button class="btn sm" onclick='exportDrawer(${JSON.stringify({t:lab,s:storeRows.map(r=>[r.label,r.disp]),c:catRows.map(r=>[r.label,r.disp])})})'>⬇ ${T('Export to Excel','Export ke Excel')}</button></div>`;
  showOverlay();G('drawer').classList.add('show');
  setTimeout(()=>{hbarChart('drawer-chart',storeRows.map(r=>({label:r.label,value:r.val,color:def.color})));barChart('drawer-chart2',catRows.map(r=>({label:r.label,value:r.val,color:r.color})),{pb:52});},60);
}
function drillStore(id){closeAll();state.storeMode='sel';state.stores=new Set([id]);syncSegs();refreshAll();toast('🏪 '+((STORES.find(s=>s.id===id)||{}).name||''));}
function drillCat(id){closeAll();state.itemMode='cat';state.cats=new Set([id]);syncSegs();refreshAll();toast('🗂️ '+((CATS.find(c=>c.id===id)||{}).name||''));}
function exportDrawer(o){downloadCSV('AI360_'+o.t.replace(/[^a-z0-9]/gi,'_')+'.csv',[[o.t+' — by Store'],['Store',o.t],...o.s,[''],[o.t+' — by Category'],['Category',o.t],...o.c]);toast('⬇ '+T('Exported','Diekspor'));}

/* ---------- chat ---------- */
const CHIPS_INV=[['Top stockout-risk SKUs','SKU paling berisiko stockout',0],['Where is overstock capital tied up?','Di mana modal overstock terikat?',0],['Expiry-risk fresh items','Item fresh berisiko expiry',0],['Prepare transfer & markdown actions','Siapkan aksi transfer & markdown',0]];
const CHIPS_CH_INV=[['Challenge: what if lead time doubles?','Challenge: kalau lead time 2x?',1],['Challenge the overstock transfer','Tantang transfer overstock',1],['Stress-test expiry on a demand drop','Stress-test expiry saat demand turun',1]];
function renderChips(){const set=CHALLENGE?CHIPS.concat(CHIPS_CH):CHIPS;G('chips').innerHTML=set.map(c=>`<span class="pchip ${c[2]?'ch':''}" onclick="quick('${T(c[0],c[1]).replace(/'/g,"\\'")}')">${T(c[0],c[1])}</span>`).join('');}
function quick(t){G('chatin').value=t;sendChat();}
function toggleChallenge(){CHALLENGE=!CHALLENGE;G('chtoggle').classList.toggle('on',CHALLENGE);renderChips();
  addMsg('ai',CHALLENGE?T('Challenge mode ON. I will stress-test assumptions and show the downside math.','Mode Challenge AKTIF. Saya akan menantang asumsi dan menunjukkan hitungan sisi buruknya.'):T('Challenge mode off.','Mode Challenge nonaktif.'),CHALLENGE);}
function addMsg(who,html,challenge){const c=G('chat');const d=document.createElement('div');d.className='msg '+who+(challenge?' challenge':'');
  d.innerHTML=who==='ai'?`<div class="who">${challenge?'⚔ '+T('Challenge','Challenge'):'✦ AI Retail 360'}</div>${html}`:html;c.appendChild(d);c.scrollTop=c.scrollHeight;
  if(who==='ai'){const cid=d.querySelector('[data-chart]');if(cid)cid.__render&&cid.__render();}}
function sendChat(){const inp=G('chatin');const q=inp.value.trim();if(!q)return;addMsg('user',q);inp.value='';setTimeout(()=>aiReply(q),240);}
function explainInChat(name){document.querySelector('.col-chat').scrollIntoView({behavior:'smooth'});addMsg('user',T('Explain calculation: ','Jelaskan kalkulasi: ')+name);setTimeout(()=>aiReply('explain '+name),200);}
function aiReply_INV(q){const k=computeK();const ql=q.toLowerCase();const ch=CHALLENGE;
  if(ql.includes('lead')&&ch){
    addMsg('ai',`${T('If vendor lead time doubles, more SKUs fall below ROP:','Kalau lead time vendor 2x, makin banyak SKU di bawah ROP:')}
      <div class="calcbox">ROP = ADS × (Lead + Safety)
lead 2× roughly doubles the lead component
stockout-risk SKUs: ${k.stockout} → ~${Math.round(k.stockout*1.7)}+</div>
      ${T('Fresh (2–5d shelf-life) cannot simply hold more safety stock — it would expire. Dual-source or shorten the replenishment cycle instead.','Fresh (shelf-life 2–5 hari) tak bisa sekadar tambah safety stock — akan expiry. Dual-source atau perpendek siklus replenishment.')}`,true);
  }else if(ql.includes('stockout')||ql.includes('replenish')){
    const items=activeSKUs().map(s=>({s,m:invMetrics(s)})).filter(x=>x.m.state==='Stockout'||x.m.state==='Low').slice(0,4);
    addMsg('ai',`${T('Stockout-risk SKUs (Position below ROP):','SKU risiko stockout (Position di bawah ROP):')} <b>${k.stockout}</b>
      <div class="calcbox">risk if  Position (On Hand + Open PO) < ROP = ADS × (Lead+Safety)</div>
      <table class="mini-table"><thead><tr><th>Item</th><th>Pos</th><th>ROP</th><th>DoS</th></tr></thead><tbody>
      ${items.map(x=>`<tr><td>${x.s.name}</td><td>${fmt(x.m.position)}</td><td>${fmt(x.m.rop)}</td><td>${x.m.dos.toFixed(1)}d</td></tr>`).join('')||('<tr><td colspan=4>'+T('None in scope','Tidak ada di scope')+'</td></tr>')}</tbody></table>
      ${ch?T('<br>Challenge: several may share one vendor — one delay cascades. Diversify or pre-position at DC.','<br>Challenge: beberapa bisa 1 vendor — satu telat, semua kena. Diversifikasi atau pre-position di DC.'):''}`,ch);
  }else if(ql.includes('overstock')||ql.includes('capital')){
    addMsg('ai',`${T('Overstock ties up working capital:','Overstock mengikat modal kerja:')} <b>${k.overstock} SKU</b> ≈ <b>Rp ${fmt(k.overstockVal)}</b>
      <div class="calcbox">excess capital = Σ (Position − Max) × price
Max = ADS × (Lead + Safety + Review)</div>
      ${T('Recommend inter-store transfer to needier clusters, or slow the next PO.','Sarankan transfer antar toko ke cluster yang butuh, atau perlambat PO berikutnya.')}
      ${ch?T('<br>Challenge: transferring costs money too. Only transfer if destination demand × margin > transfer cost.','<br>Challenge: transfer juga ada biaya. Transfer hanya jika demand×margin tujuan > biaya transfer.'):''}`,ch);
  }else if(ql.includes('expiry')||ql.includes('expire')||ql.includes('waste')||ql.includes('fresh')){
    const items=activeSKUs().filter(s=>s.fresh).map(s=>({s,m:invMetrics(s)})).filter(x=>x.m.unitsExpiry>0).sort((a,b)=>a.s.expiry-b.s.expiry).slice(0,4);
    addMsg('ai',`${T('Expiry-risk (fresh) units in scope:','Unit risiko expiry (fresh) di scope:')} <b>${fmt(k.expiryUnits)} u</b>
      <div class="calcbox">at-risk = Σ max(0, Position − ADS × shelf-life)</div>
      <table class="mini-table"><thead><tr><th>Item</th><th>Shelf</th><th>At-risk</th></tr></thead><tbody>
      ${items.map(x=>`<tr><td>${x.s.name}</td><td>${x.s.expiry}d</td><td>${fmt(x.m.unitsExpiry)}</td></tr>`).join('')||('<tr><td colspan=3>'+T('None in scope','Tidak ada')+'</td></tr>')}</tbody></table>
      ${T('Recommend timed markdown before expiry, or transfer to higher-velocity stores.','Sarankan markdown terjadwal sebelum expiry, atau transfer ke toko yang lebih cepat laku.')}`,ch);
  }else if(ql.includes('days of supply')||ql.includes('dos')||ql.includes('coverage')){
    addMsg('ai',`${T('Average Days of Supply in scope:','Rata-rata Days of Supply di scope:')} <b>${k.avgDOS.toFixed(1)}d</b>
      <div class="calcbox">DoS = Position ÷ ADS · target band 7–21 days</div>
      ${T('Below 7d → replenish; above 21d → overstock candidate.','Di bawah 7h → replenish; di atas 21h → kandidat overstock.')}`,ch);
  }else if(ql.includes('transfer')||ql.includes('markdown')||ql.includes('action')){
    addMsg('ai',`${T('I prepared an action list: replenish stockouts, transfer overstock, markdown expiry.','Saya siapkan daftar aksi: replenish stockout, transfer overstock, markdown expiry.')}
      <div class="calcbox">Replenish = Max−Position · Transfer = Position−Max · Markdown = expiry units</div>
      <button class="btn indigo sm" onclick="togglePO();document.querySelector('[data-sec=action]').scrollIntoView({behavior:'smooth'})">📦 ${T('Open action list','Buka daftar aksi')}</button>`,ch);
  }else if(ql.includes('explain')){
    addMsg('ai',T('Hover any number to see its formula, inputs and current value. Every answer here also shows the math.','Arahkan kursor ke angka mana pun untuk lihat formula, input, dan nilainya. Tiap jawaban di sini juga menampilkan hitungannya.'),ch);
  }else{
    addMsg('ai',T('I can explain stockout, overstock, expiry risk, days of supply, and prepare transfer/markdown actions. Turn on Challenge mode to pressure-test.','Saya bisa jelaskan stockout, overstock, risiko expiry, days of supply, dan menyiapkan aksi transfer/markdown. Nyalakan Challenge mode untuk menguji.'),ch);
  }
}

/* ---------- agentic / history modals ---------- */
function showOverlay(){G('overlay').classList.add('show');}
function closeAll(){G('overlay').classList.remove('show');G('drawer').classList.remove('show');document.querySelectorAll('.modal').forEach(m=>m.classList.remove('show'));}
function openAgentic(){const k=computeK();G('agentic-body').innerHTML=`<div class="tiny muted" style="margin-bottom:10px">${T('Agent monitors signals, proposes actions, routes for approval, then tracks outcome.','Agent memantau sinyal, mengusulkan aksi, minta approval, lalu melacak hasil.')}</div>
  <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px">${['Monitor','Detect','Diagnose','Recommend','Simulate','Approve','Track'].map((s,i)=>`<span class="chipstep ${i<4?'done':i===4?'active':''}"><span class="n">${i+1}</span>${s}</span>`).join('')}</div>
  <div class="action-card"><div class="ah"><span class="pri high">AUTONOMOUS</span><b>${T('3 actions awaiting approval','3 aksi menunggu approval')}</b></div>
    <div class="tiny muted">${T('Replenish fresh, inter-store transfer, non-fresh order adjustment.','Replenish fresh, transfer antar toko, penyesuaian order non-fresh.')}</div>
    <div class="agentic-row"><button class="abtn approve" onclick="agentic('approved');closeAll()">✔ ${T('Approve all','Setujui semua')}</button><button class="abtn reject" onclick="agentic('rejected');closeAll()">✕ ${T('Reject','Tolak')}</button></div></div>`;
  showOverlay();G('modal-agentic').classList.add('show');}
function openHistory(){const logs=actionLog.length?actionLog:[{time:'—',action:T('Agent initialized','Agent diinisialisasi'),st:'reopened'}];
  G('history-body').innerHTML=`<div class="tiny muted" style="margin-bottom:8px">${T('Audit trail of agentic actions this session.','Jejak audit aksi agentik sesi ini.')}</div>
  ${logs.map(l=>{const cls={approved:'st-approved',rejected:'st-rejected',cancelled:'st-cancelled',reopened:'st-reopened',pending:'st-pending',sent:'st-sent'}[l.st];
  return `<div class="hist-item"><div style="flex:1"><div>${l.action}</div><div class="hd">${l.time}</div></div><span class="status-tag ${cls}">${l.st}</span></div>`;}).join('')}`;
  showOverlay();G('modal-history').classList.add('show');}

/* ---------- flow mini ---------- */
const AGENTS=['Demand Forecasting','Inventory Risk','Replenishment','Promotion Effectiveness','Pricing & Markdown','Assortment Optimization','AI Explanation & Summary','Workforce Agent'];
const NAVKEYS=['df','inv','rep','promo','pm','assort','ai','workforce'];
function renderAgentNav(){const keys=NAVKEYS;G('agentnav').innerHTML=AGENTS.map((a,i)=>{const key=keys[i];const built=['df','inv','rep','promo','pm','assort','ai'].includes(key);const active=(built&&key===state.agent);const rx=received[key];return `<div class="navitem ${active?'active':'lock'}" title="${a}" onclick="${built?`setAgent('${key}')`:`toast('${T('This agent mockup is built next','Mockup agent ini dibangun berikutnya')}')`}"><span class="n">${i+1}</span><span class="lbl">${a}</span>${rx?'<span class="rxbadge" title="'+T('Received a handoff','Menerima estafet')+'">●</span>':''}${built?'':'<span class=\"rt\">🔒</span>'}</div>`;}).join('');}

/* ---------- filters UI ---------- */
function renderCatList(){G('catlist').innerHTML=CATS.map(c=>`<label class="chk"><input type="checkbox" ${state.cats.has(c.id)?'checked':''} onchange="toggleCat('${c.id}',this.checked)"><span class="sw" style="background:${CCOLOR[c.id]}"></span><span>${c.name}</span><span class="tag">${c.fresh?'Fresh':''}</span></label>`).join('');}
function renderSkuList(){const q=(G('skusearch').value||'').toLowerCase();
  G('skulist').innerHTML=SKUS.filter(s=>!q||s.name.toLowerCase().includes(q)||s.cat.toLowerCase().includes(q)).map(s=>`<label class="chk"><input type="checkbox" ${state.skus.has(s.id)?'checked':''} onchange="toggleSku('${s.id}',this.checked)"><span class="sw" style="background:${CCOLOR[s.catId]}"></span><span>${s.name}</span><span class="tag">${s.cat}</span></label>`).join('');}
function renderStoreList(){G('storelist').innerHTML=STORES.map(s=>`<label class="chk"><input type="checkbox" ${state.stores.has(s.id)?'checked':''} onchange="toggleStore('${s.id}',this.checked)"><span>${s.name}</span><span class="tag">${s.cluster}</span></label>`).join('');}
function toggleCat(id,v){v?state.cats.add(id):state.cats.delete(id);refreshAll();}
function toggleSku(id,v){v?state.skus.add(id):state.skus.delete(id);refreshAll();}
function toggleStore(id,v){v?state.stores.add(id):state.stores.delete(id);refreshAll();}
function selAll(kind){if(kind==='cat'){if(state.cats.size)state.cats.clear();else CATS.forEach(c=>state.cats.add(c.id));renderCatList();}
  else{if(state.skus.size)state.skus.clear();else SKUS.forEach(s=>state.skus.add(s.id));renderSkuList();}refreshAll();}
function setItemMode(m,btn){state.itemMode=m;segActive('itemseg',btn);G('catwrap').classList.toggle('hidden',m!=='cat');G('itemwrap').classList.toggle('hidden',m!=='item');refreshAll();}
function setStoreMode(m,btn){state.storeMode=m;segActive('storeseg',btn);G('storewrap').classList.toggle('hidden',m!=='sel');refreshAll();}
function setPeriod(p,btn){state.period=p;segActive('viewseg',btn);refreshAll();}
function segActive(id,btn){G(id).querySelectorAll('button').forEach(b=>b.classList.remove('active'));btn.classList.add('active');}
function syncSegs(){
  ['itemseg','storeseg'].forEach(()=>{});
  const im={all:0,cat:1,item:2}[state.itemMode];G('itemseg').querySelectorAll('button').forEach((b,i)=>b.classList.toggle('active',i===im));
  G('catwrap').classList.toggle('hidden',state.itemMode!=='cat');G('itemwrap').classList.toggle('hidden',state.itemMode!=='item');
  const sm={all:0,sel:1}[state.storeMode];G('storeseg').querySelectorAll('button').forEach((b,i)=>b.classList.toggle('active',i===sm));
  G('storewrap').classList.toggle('hidden',state.storeMode!=='sel');
  renderCatList();renderSkuList();renderStoreList();
}
function renderFilterChips(){
  const chips=[];
  if(state.itemMode==='cat'&&state.cats.size)[...state.cats].forEach(id=>{const c=CATS.find(x=>x.id===id);chips.push(`<span class="fchip"><span class="sw" style="background:${CCOLOR[id]}"></span><b>${c.name}</b><span class="x" onclick="toggleCatChip('${id}')">✕</span></span>`);});
  if(state.itemMode==='item'&&state.skus.size)[...state.skus].forEach(id=>{const s=SKUS.find(x=>x.id===id);chips.push(`<span class="fchip"><span class="sw" style="background:${CCOLOR[s.catId]}"></span><b>${s.name}</b><span class="x" onclick="toggleSkuChip('${id}')">✕</span></span>`);});
  if(state.storeMode==='sel'&&state.stores.size)[...state.stores].forEach(id=>{const s=STORES.find(x=>x.id===id);chips.push(`<span class="fchip">🏪 <b>${s.name.replace('HERO ','')}</b><span class="x" onclick="toggleStoreChip('${id}')">✕</span></span>`);});
  chips.push(`<span class="fchip" style="background:#eef0ff;color:#4a52a8">👁 ${state.period.toUpperCase()}</span>`);
  if(chips.length>1)chips.push(`<span class="fchip clear" onclick="clearFilters()">✕ ${T('Clear all','Hapus semua')}</span>`);
  G('filterchips').innerHTML=chips.join('');
}
function toggleCatChip(id){state.cats.delete(id);syncSegs();refreshAll();}
function toggleSkuChip(id){state.skus.delete(id);syncSegs();refreshAll();}
function toggleStoreChip(id){state.stores.delete(id);syncSegs();refreshAll();}
function clearFilters(){state.itemMode='all';state.cats.clear();state.storeMode='all';state.stores.clear();syncSegs();refreshAll();toast(T('Filters cleared','Filter dihapus'));}
function scopeShort(){let it=state.itemMode==='all'?T('All items','Semua item'):state.itemMode==='cat'?(state.cats.size?state.cats.size+' cat':'All cat'):(state.skus.size?state.skus.size+' SKU':'All SKU');
  let st=state.storeMode==='all'?T('All stores','Semua toko'):(state.stores.size?state.stores.size+' store':'All store');return it+' · '+st;}

/* ---------- triggers ---------- */
function renderTriggers(){G('triglist').innerHTML=TRIGGERS.map(t=>`<label class="chk"><input type="checkbox" ${state.triggers[t[0]]?'checked':''} onchange="toggleTrig('${t[0]}',this.checked)"><span>${t[1]}</span>${t[2]?'':'<span class="tag">custom</span>'}</label>`).join('');
  G('trigcount').textContent=Object.values(state.triggers).filter(Boolean).length+'/17';}
function toggleTrig(k,v){state.triggers[k]=v;G('trigcount').textContent=Object.values(state.triggers).filter(Boolean).length+'/17';refreshAll();}

/* ---------- misc ---------- */
function toggleRail(){document.body.classList.toggle('collapsed');setTimeout(refreshCharts,240);}
function setLang(l){LANG=l;G('lang-en').classList.toggle('active',l==='en');G('lang-id').classList.toggle('active',l==='id');
  document.querySelectorAll('[data-en]').forEach(e=>e.textContent=e.getAttribute('data-'+l));document.documentElement.lang=l;renderAgentNav();renderChips();refreshAll();}
let toastT;function toast(m){const t=G('toast');t.innerHTML=m;t.classList.add('show');clearTimeout(toastT);toastT=setTimeout(()=>t.classList.remove('show'),2500);}
function resetAll(){state.itemMode='all';state.cats.clear();state.skus.clear();state.storeMode='all';state.stores.clear();state.period='daily';state.horizon=8;
  TRIGGERS.forEach(t=>state.triggers[t[0]]=!!t[2]);Object.assign(state.sim,{price:0,promo:0,seas:0,viral:0,lead:3,safe:2});scenarios=[];actionLog=[];actionState='pending';poOpen=false;received={};poWF=null;
  ['s-price','s-promo','s-seas','s-viral'].forEach(id=>G(id).value=0);G('s-lead').value=3;G('s-safe').value=2;G('horizon').value=8;G('horizonv').textContent='8 wk';
  G('viewseg').querySelectorAll('button').forEach((b,i)=>b.classList.toggle('active',i===0));
  syncSegs();renderTriggers();onSim();refreshAll();toast(T('↺ Reset done','↺ Reset selesai'));}

function refreshCharts(){renderForecast();renderDriver();renderCat();renderStore();renderCluster();renderSeason();renderMatrix();renderCompare();runSim();}
function refreshAll(){G('crumb').textContent=(LABELS[state.agent]?LABELS[state.agent].crumb:'Agent')+' · '+scopeShort();renderFilterChips();renderKPIs();renderTrend();renderAction();refreshCharts();}
window.addEventListener('resize',()=>{clearTimeout(window.__rz);window.__rz=setTimeout(refreshCharts,150);});

/* ---------- boot ---------- */
function boot(){renderAgentNav();renderCatList();renderSkuList();renderStoreList();renderTriggers();renderChips();
  addMsg('ai',T('Hi! I am the AI Retail 360 assistant. Pick an agent from the left rail. Ask anything about the active agent; every answer shows the math. Filters carry across agents.','Halo! Saya asisten AI Retail 360. Pilih agent di rail kiri. Tanya apa saja tentang agent aktif; tiap jawaban ada hitungannya. Filter ikut kebawa antar agent.'));
  setAgent('df');}
boot();


/* ===== Focused workspace controller ===== */
function markFilterSections(){
  const labels=[...document.querySelectorAll('.rail-scroll>.rail-label')];
  labels.forEach((label,i)=>{if(i>0){label.classList.add('filter-section');const next=label.nextElementSibling;if(next)next.classList.add('filter-section');}});
}
function toggleFilters(force){document.body.classList.toggle('filters-open',typeof force==='boolean'?force:!document.body.classList.contains('filters-open'));}
function toggleAI(force){const show=typeof force==='boolean'?force:document.body.classList.contains('ai-hidden');document.body.classList.toggle('ai-hidden',!show);document.body.classList.toggle('ai-open',show);setTimeout(refreshCharts,220);}
function setWorkspace(name,btn){
  document.body.dataset.workspace=name;
  document.querySelectorAll('.workspace-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.workspace===name));
  window.scrollTo({top:0,behavior:'smooth'});
  setTimeout(refreshCharts,60);
}
function renderDecisionSummary(){
  if(!document.getElementById('decision-title'))return;
  const k=computeK();let title='',copy='',impact='';
  switch(state.agent){
    case 'inv': title=`${fmt(k.stockout+k.overstock)} SKUs require attention`;copy=`${fmt(k.stockout)} stockout-risk · ${fmt(k.expiryUnits)} expiry-risk units · ${fmt(k.overstock)} overstock SKUs`;impact='Rp '+fmt(k.overstockVal);break;
    case 'rep': title=`${fmt(k.reorderCount)} SKUs should be reordered`;copy=`Order ${fmt(k.orderUnits)} units before the receiving cut-off.`;impact='Rp '+fmt(k.orderValue);break;
    case 'promo': title=`Optimize ${fmt(k.activeCount)} active promotions`;copy=`Scale profitable offers and redesign promotions below 1x ROI.`;impact='Rp '+fmt(k.incrMargin);break;
    case 'pm': title=`${fmt(k.candCount)} items need a price action`;copy=`Prioritize expiry and overstock before reviewing chronic slow movers.`;impact='Rp '+fmt(k.recoverTot);break;
    case 'assort': title=`Simplify the range and grow winners`;copy=`Review ${fmt(k.delistCount)} delist candidates and ${fmt(k.growCount)} growth candidates.`;impact='Rp '+fmt(k.marginImpact);break;
    case 'ai': title=`Executive opportunity across the decision pipeline`;copy=`Consolidated value from forecasting, inventory, commercial and assortment actions.`;impact='Rp '+fmt(k.totalValue);break;
    default: title=`${fmt(k.risk)} SKUs are at stockout risk`;copy=`Review the forecast, then send the highest-priority signal to replenishment.`;impact=fmt(k.fore7)+' units';
  }
  document.getElementById('decision-title').textContent=title;document.getElementById('decision-copy').textContent=copy;document.getElementById('decision-impact-value').textContent=impact;
}
const __focusedRefreshAll=refreshAll;
refreshAll=function(){__focusedRefreshAll();renderDecisionSummary();};
const __focusedSetAgent=setAgent;
setAgent=function(key){__focusedSetAgent(key);renderDecisionSummary();setWorkspace('overview');};
markFilterSections();document.body.dataset.workspace='overview';document.body.classList.add('ai-open');document.body.classList.remove('ai-hidden');renderDecisionSummary();
document.addEventListener('keydown',e=>{if(e.key==='Escape'){toggleAI(false);toggleFilters(false);}});

/* ===== Move filters from sidebar to centered top layer ===== */
function buildTopFilterLayer(){
  if(document.getElementById('top-filter-layer')) return;
  const railScroll=document.querySelector('.rail-scroll');
  if(!railScroll) return;
  const children=[...railScroll.children];
  const scopeLabel=children.find(el=>el.classList.contains('rail-label') && /Scope|Cakupan/i.test(el.textContent));
  const triggerLabel=children.find(el=>el.classList.contains('rail-label') && /Trigger/i.test(el.textContent));
  if(!scopeLabel||!triggerLabel) return;
  const scopeBody=scopeLabel.nextElementSibling;
  const triggerBody=triggerLabel.nextElementSibling;
  const layer=document.createElement('section');
  layer.id='top-filter-layer';layer.className='top-filter-layer';layer.setAttribute('aria-label','Scope and filters');
  layer.innerHTML='<div class="filter-layer-head"><div><div class="filter-layer-title">Scope & Filters</div><div class="filter-layer-sub">Refine the current decision workspace</div></div><button class="filter-layer-close" type="button" onclick="toggleFilters(false)" aria-label="Close filters">✕</button></div><div class="filter-layer-body"></div>';
  const body=layer.querySelector('.filter-layer-body');
  if(scopeBody){[...scopeBody.children].forEach(node=>body.appendChild(node));}
  if(triggerBody){
    const block=document.createElement('div');block.className='trigger-block';
    block.innerHTML='<div class="trigger-title"><span>Trigger calculation</span><span id="filter-trigger-count"></span></div>';
    [...triggerBody.children].forEach(node=>block.appendChild(node));body.appendChild(block);
  }
  [scopeLabel,scopeBody,triggerLabel,triggerBody].forEach(node=>node&&node.remove());
  document.body.appendChild(layer);
  layer.addEventListener('click',e=>e.stopPropagation());
}
const __topFilterToggle=toggleFilters;
toggleFilters=function(force){
  const open=typeof force==='boolean'?force:!document.body.classList.contains('filters-open');
  document.body.classList.toggle('filters-open',open);
  const button=document.querySelector('[onclick="toggleFilters()"]');if(button)button.setAttribute('aria-expanded',String(open));
};
buildTopFilterLayer();
document.addEventListener('click',e=>{if(document.body.classList.contains('filters-open')&&!e.target.closest('#top-filter-layer')&&!e.target.closest('[onclick="toggleFilters()"]'))toggleFilters(false);});

/* ===== Place Sales View inside the toolbar below workspace tabs ===== */
function moveSalesViewToToolbar(){
  const chips=document.getElementById('filterchips');
  const layer=document.getElementById('top-filter-layer');
  if(!chips||!layer||document.getElementById('inline-sales-view')) return;
  const groups=[...layer.querySelectorAll('.fgroup')];
  const salesGroup=groups.find(group=>/Sales View|Tampilan/i.test(group.textContent));
  if(!salesGroup) return;
  const toolbar=document.createElement('div');toolbar.className='scope-toolbar';
  chips.parentNode.insertBefore(toolbar,chips);toolbar.appendChild(chips);
  salesGroup.id='inline-sales-view';salesGroup.className='inline-sales-view';
  toolbar.insertBefore(salesGroup,chips);
}
moveSalesViewToToolbar();

/* ===== Store -> Category -> Item dropdown filters in marked area ===== */
function inlineFilterSummary(kind){
  if(kind==='store'){
    if(state.storeMode==='all'||!state.stores.size)return T('All stores','Semua toko');
    if(state.stores.size===1){const s=STORES.find(x=>state.stores.has(x.id));return s?s.name.replace('HERO ',''):T('1 store','1 toko');}
    return state.stores.size+' '+T('stores','toko');
  }
  if(kind==='category'){
    if(state.itemMode!=='cat'||!state.cats.size)return T('All categories','Semua kategori');
    if(state.cats.size===1){const c=CATS.find(x=>state.cats.has(x.id));return c?c.name:'1 category';}
    return state.cats.size+' '+T('categories','kategori');
  }
  if(state.itemMode!=='item'||!state.skus.size)return T('All items','Semua item');
  if(state.skus.size===1){const s=SKUS.find(x=>state.skus.has(x.id));return s?s.name:'1 item';}
  return state.skus.size+' '+T('items','item');
}
function closeInlineFilters(except){document.querySelectorAll('.inline-filter.open').forEach(x=>{if(x!==except)x.classList.remove('open');});}
function toggleInlineFilter(el){const willOpen=!el.classList.contains('open');closeInlineFilters(el);el.classList.toggle('open',willOpen);}
function applyInlineStoreAll(){state.storeMode='all';state.stores.clear();syncSegs();refreshAll();renderInlineFilters();}
function applyInlineStore(id,checked){state.storeMode='sel';checked?state.stores.add(id):state.stores.delete(id);if(!state.stores.size)state.storeMode='all';syncSegs();refreshAll();renderInlineFilters('store');}
function applyInlineCategoryAll(){state.itemMode='all';state.cats.clear();state.skus.clear();syncSegs();refreshAll();renderInlineFilters();}
function applyInlineCategory(id,checked){state.itemMode='cat';state.skus.clear();checked?state.cats.add(id):state.cats.delete(id);if(!state.cats.size)state.itemMode='all';syncSegs();refreshAll();renderInlineFilters('category');}
function applyInlineItemAll(){state.itemMode='all';state.skus.clear();state.cats.clear();syncSegs();refreshAll();renderInlineFilters();}
function applyInlineItem(id,checked){state.itemMode='item';state.cats.clear();checked?state.skus.add(id):state.skus.delete(id);if(!state.skus.size)state.itemMode='all';syncSegs();refreshAll();renderInlineFilters('item');}
function filterInlineItems(value){const q=value.trim().toLowerCase();document.querySelectorAll('#inline-item-options .menu-check').forEach(x=>x.hidden=!x.textContent.toLowerCase().includes(q));}
function inlineFilterHTML(kind,label,value,body){return `<div class="inline-filter" data-filter="${kind}"><button class="inline-filter-button" type="button" onclick="toggleInlineFilter(this.parentElement)" aria-haspopup="true"><span class="filter-copy"><span class="filter-label">${label}</span><span class="filter-value">${value}</span></span><span class="chevron">▾</span></button><div class="inline-filter-menu">${body}</div></div>`;}
function renderInlineFilters(keepOpen){
  const bar=G('inline-filter-bar');if(!bar)return;
  const storeBody=`<button class="menu-action ${state.storeMode==='all'?'selected':''}" onclick="applyInlineStoreAll()">All stores</button><div class="menu-separator"></div>${STORES.map(s=>`<label class="menu-check"><input type="checkbox" ${state.storeMode==='sel'&&state.stores.has(s.id)?'checked':''} onchange="applyInlineStore('${s.id}',this.checked)"><span>${s.name.replace('HERO ','')}</span><span class="tag">${s.cluster}</span></label>`).join('')}`;
  const catBody=`<button class="menu-action ${state.itemMode!=='cat'?'selected':''}" onclick="applyInlineCategoryAll()">All categories</button><div class="menu-separator"></div>${CATS.map(c=>`<label class="menu-check"><input type="checkbox" ${state.itemMode==='cat'&&state.cats.has(c.id)?'checked':''} onchange="applyInlineCategory('${c.id}',this.checked)"><span class="sw" style="background:${CCOLOR[c.id]}"></span><span>${c.name}</span><span class="tag">${c.fresh?'Fresh':''}</span></label>`).join('')}`;
  const itemBody=`<input class="menu-search" placeholder="Search item..." oninput="filterInlineItems(this.value)"><button class="menu-action ${state.itemMode!=='item'?'selected':''}" onclick="applyInlineItemAll()">All items</button><div class="menu-separator"></div><div id="inline-item-options">${SKUS.map(s=>`<label class="menu-check"><input type="checkbox" ${state.itemMode==='item'&&state.skus.has(s.id)?'checked':''} onchange="applyInlineItem('${s.id}',this.checked)"><span class="sw" style="background:${CCOLOR[s.catId]}"></span><span>${s.name}</span><span class="tag">${s.cat}</span></label>`).join('')}</div>`;
  const triggerBody=`${TRIGGERS.map(t=>`<label class="menu-check"><input type="checkbox" ${state.triggers[t[0]]?'checked':''} onchange="state.triggers['${t[0]}']=this.checked;refreshAll();renderInlineFilters('trigger')"><span>${t[1]}</span></label>`).join('')}`;
  bar.innerHTML=inlineFilterHTML('store',T('Store filter','Filter toko'),inlineFilterSummary('store'),storeBody)+inlineFilterHTML('category',T('Category','Kategori'),inlineFilterSummary('category'),catBody)+inlineFilterHTML('item',T('Item filter','Filter item'),inlineFilterSummary('item'),itemBody)+inlineFilterHTML('trigger','',T('Trigger Calc','Trigger Calc'),triggerBody);
  if(keepOpen){const el=bar.querySelector(`[data-filter="${keepOpen}"]`);if(el)el.classList.add('open');}
}
function buildInlineFilterBar(){
  if(G('inline-filter-bar'))return;
  const tabs=document.querySelector('.workspace-tabs');if(!tabs)return;
  const row=document.createElement('div');row.className='workspace-control-row';tabs.parentNode.insertBefore(row,tabs);row.appendChild(tabs);
  const bar=document.createElement('div');bar.id='inline-filter-bar';bar.className='inline-filter-bar';row.appendChild(bar);renderInlineFilters();
}
buildInlineFilterBar();
const __inlineRefreshAll=refreshAll;refreshAll=function(){__inlineRefreshAll();renderInlineFilters();};
document.addEventListener('click',e=>{if(!e.target.closest('.inline-filter'))closeInlineFilters();});
