'use strict';
(function(root) {
  function points(row) {
    const dates=new Set((row.chart||[]).map(b=>b.date));
    let events=row.chart_swings;
    if(!Array.isArray(events)) {
      events=[];
      for(const kind of ['high','low']) {
        const pivots=row.pivots?.[kind]||[];
        pivots.forEach((p,i)=>{
          const previous=pivots[i-1]?.price;
          const label=previous==null?(kind==='high'?'H':'L'):
            p.price===previous?(kind==='high'?'EH':'EL'):
            kind==='high'?(p.price>previous?'HH':'LH'):(p.price>previous?'HL':'LL');
          events.push({...p,kind,label});
        });
      }
    }
    return events.filter(p=>dates.has(p.pivot_date)&&p.confirmed_on<=row.data_date)
      .sort((a,b)=>a.pivot_date.localeCompare(b.pivot_date)||a.kind.localeCompare(b.kind));
  }
  function segments(events) {
    // A daily outside bar can confirm both extremes; its intraday ordering is unknown.
    const counts=new Map();
    events.forEach(p=>counts.set(p.pivot_date,(counts.get(p.pivot_date)||0)+1));
    const result=[];let current=[];
    for(const p of events) {
      if(counts.get(p.pivot_date)>1) {
        if(current.length>1) result.push(current);
        current=[];continue;
      }
      const last=current.at(-1);
      if(!last||last.kind!==p.kind) current.push(p);
      else if((p.kind==='high'&&p.price>last.price)||(p.kind==='low'&&p.price<last.price)) current[current.length-1]=p;
    }
    if(current.length>1) result.push(current);
    return result;
  }
  const api={points,segments};
  if(typeof module==='object'&&module.exports) module.exports=api;
  else root.HHHLChart=api;
})(typeof globalThis==='object'?globalThis:this);
