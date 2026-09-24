(function(){
  'use strict';
  let brief,selected,scanDate;
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const strip=document.getElementById('market-context-strip'),stock=document.getElementById('market-context-stock');
  function showStock(symbol,date){selected=symbol;scanDate=date;if(!stock||!brief)return;const r=brief.rows.find(r=>r.symbol===symbol);stock.hidden=false;
    if(date!==brief.as_of){stock.textContent='The market briefing uses a different price session. Open the full briefing to check its dates.';return;}
    const old=Date.now()-Date.parse(brief.generated_at)>30*3600000;
    stock.innerHTML='<strong>US + India context'+(old?' · older briefing':'')+'</strong><p>'+esc(r?.context||'insufficient')+' · event risk '+esc(r?.event_risk||'unknown')+'. '+esc(r?.why||'No assessment available.')+'</p><p><a href="market-brief.html?symbol='+encodeURIComponent(symbol)+'#stocks">Read '+esc(symbol)+' context and sources →</a></p><small>Published '+esc(brief.generated_at)+' · this assessment does not change technical eligibility.</small>';
  }
  window.MarketContext={showStock};
  if(!strip)return;
  fetch((document.body.dataset.source||'')+'market_brief.json?refresh='+Date.now(),{cache:'no-store'}).then(async r=>{if(!r.ok)throw Error();brief=await r.json();if(!Array.isArray(brief.rows)||brief.rows.length!==200)throw Error();const old=Date.now()-Date.parse(brief.generated_at)>30*3600000;strip.classList.toggle('context-warning',old||brief.state!=='fresh'||r.headers.get('X-Swing-Source')==='local-fallback');strip.innerHTML='<strong>US + India context</strong> · India '+esc(brief.macro?.India?.choice||'unknown')+' · US '+esc(brief.macro?.US?.choice||'unknown')+' · '+brief.judged_count+'/200 Jev assessments. <a href="market-brief.html">Read the sourced briefing →</a><br><small>Price session '+esc(brief.as_of)+' · '+(old?'Older publication. ':'')+'Partial source coverage may limit conclusions; no change to entry rules.</small>';if(selected)showStock(selected,scanDate);}).catch(()=>{strip.innerHTML='Market context is unavailable. <a href="market-brief.html">Check briefing status →</a>';});
})();
