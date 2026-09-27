'use strict';
(function(root) {
  const states=['BUY','SELL','WATCH','CAUTION','AVOID'];
  const day=value=>/^\d{4}-\d{2}-\d{2}$/.test(value||'');
  const modes={nifty200:'Nifty 200',fno:'All F&O stocks',all:'All stocks'};

  function validate(data) {
    const members=data?.membership?.members,rows=data?.rows;
    if(data?.version!==1||!day(data.as_of)||!Number.isFinite(Date.parse(data.generated_at))||!data.market||
       !Array.isArray(members)||members.length<100||members.length>500||
       new Set(members.map(m=>m.symbol)).size!==members.length||data.fno_count!==members.length||
       !Array.isArray(rows)||data.extra_count!==rows.length||new Set(rows.map(r=>r.symbol)).size!==rows.length)
      throw new Error('Incomplete F&O snapshot');
    const symbols=new Set(members.map(m=>m.symbol));
    if(members.some(m=>!(/^[A-Z0-9&_-]+$/).test(m.symbol)||typeof m.name!=='string'))throw new Error('Invalid F&O membership');
    for(const row of rows) {
      if(!symbols.has(row.symbol)||!states.includes(row.status)||row.as_of!==data.as_of||
         !row.zones||!row.pivots||!Array.isArray(row.chart))throw new Error('Invalid F&O stock');
      if(row.status==='BUY'&&(!row.fresh_breakout||!row.entry_allowed||!data.market.new_entries_allowed))throw new Error('Invalid F&O buy gate');
    }
    return data;
  }

  function missing(member,asOf) {
    return {symbol:member.symbol,name:member.name,sector:'Sector unavailable',as_of:asOf,data_date:null,
      complete_for_session:false,status:'CAUTION',reason:'Price history unavailable.',close:null,atr:null,
      atr_pct:null,turnover_crore:null,structure:'UNKNOWN',fresh_breakout:false,exit_condition:false,
      sell_triggered_today:false,last_breakout_date:null,distance_to_breakout_pct:null,
      pivots:{high:[],low:[]},zones:{},chart:[],chart_swings:[],entry_checks:[],data_warnings:[],
      entry_allowed:false,entry_plan:null,volume_ratio:null,data_source:'Awaiting the first verified stock-price refresh.'};
  }

  function caution(row,asOf,reason) {
    return {...row,as_of:asOf,status:'CAUTION',reason,entry_allowed:false,fresh_breakout:false,
      complete_for_session:false,entry_plan:null,zones:{},refresh_warning:reason,
      entry_checks:(row.entry_checks||[]).map(c=>c.key==='data'?{...c,state:'fail'}:c),
      data_warnings:[...(row.data_warnings||[]),reason]};
  }

  function view(base,extra,mode,options={}) {
    if(mode==='nifty200')return base;
    if(!modes[mode])throw new Error('Unknown stock universe');
    validate(extra);
    const members=extra.membership.members,stocks=new Map(base.rows.map(r=>[r.symbol,r]));
    const additions=new Map(extra.rows.map(r=>[r.symbol,r]));
    const overdue=(options.now??Date.now())-Date.parse(extra.generated_at)>60*60*60*1000;
    const marketMatches=['data_date','close','sma200','reference_filter_passed','data_ready','new_entries_allowed']
      .every(key=>extra.market[key]===base.market[key]);
    let warning=options.loadError?'The F&O refresh could not be checked; these are the last saved extra-stock candles.':
      extra.as_of!==base.as_of?'The extra-stock scan has not caught up with the current Nifty session. The chart shows its actual saved dates.':
      !marketMatches?'The market check has changed; these extra stocks are waiting to be rescanned.':
      overdue?'The F&O refresh is overdue; these are the last saved extra-stock candles.':'';
    for(const member of members) {
      if(stocks.has(member.symbol))continue;
      const row=additions.get(member.symbol)||missing(member,base.as_of);
      stocks.set(member.symbol,warning?caution(row,base.as_of,warning):row);
    }
    const eligible=new Set(members.map(m=>m.symbol));
    const rows=[...stocks.values()].filter(r=>mode==='all'||eligible.has(r.symbol));
    return {...base,rows,universe_count:rows.length,complete_count:rows.filter(r=>r.complete_for_session).length,
      classifiable_count:rows.filter(r=>Object.keys(r.zones).length).length,
      counts:Object.fromEntries(states.map(s=>[s,rows.filter(r=>r.status===s).length])),
      priority_watchlist:undefined,
      data_audit:{...base.data_audit,universe_source:base.data_audit.universe_source+' NSE F&O membership adds '+
        (stocks.size-base.rows.length)+' other stocks; '+members.length+' F&O stocks in total. '+
        (extra.membership.verified?'Membership checked at ':'Saved membership last verified at ')+extra.membership.verified_at+'.',
        latest_recheck:base.data_audit.latest_recheck+' Extra-stock refresh: '+extra.generated_at+'. '+warning},
      limitations:[...base.limitations,'F&O filtering identifies eligible underlying shares. Charts and labels use daily share prices, not futures contracts or option premiums.']};
  }

  const api={validate,view,modes};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.HHHLUniverse=api;
})(typeof globalThis==='object'?globalThis:this);
