'use strict';
(function(root) {
  const numeric=value=>typeof value==='number'&&Number.isFinite(value);
  const number=value=>value.toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
  const money=value=>'\u20b9'+number(value);

  function structureReason(row) {
    const describe=kind=>{
      const pair=(row.pivots?.[kind]||[]).filter(p=>numeric(p.price)&&p.confirmed_on<=row.data_date).slice(-2);
      if(pair.length!==2)return null;
      const [first,last]=pair.map(p=>p.price),name=kind==='high'?'highs':'lows';
      if(first===last)return name+' stayed at '+money(last);
      return name+(last>first?' rose':' fell')+' from '+money(first)+' to '+money(last);
    };
    const highs=describe('high'),lows=describe('low');
    return highs&&lows
      ? 'The last two confirmed '+highs+', and the '+lows+'. This strategy needs both highs and lows to rise together.'
      : 'The chart does not have the two confirmed rising highs and two confirmed rising lows this strategy requires.';
  }

  // Explain the scanner's recorded reason; do not recalculate or change its state.
  function explain(row,market={}) {
    const trigger=row.zones?.breakout_above,exit=row.zones?.structure_exit_below;
    const fallback=row.reason||'A detailed reason is unavailable for this snapshot.';
    const hasTrigger=numeric(row.close)&&numeric(trigger);
    const breakout=hasTrigger
      ? 'The stock has higher confirmed highs and lows, and made a fresh close at '+money(row.close)+' above '+money(trigger)+' (CLOSING TRIGGER). '
      : '';
    switch(row.reason) {
      case 'Price history unavailable.':
        return 'Price history is unavailable, so the scanner cannot draw a reliable chart or check this setup.';
      case 'No complete candle for the requested session.':
        return 'The latest session has no complete price candle. The available chart is not up to date enough to confirm a signal.';
      case 'Missing price sessions in the structure lookback.':
        return 'Some recent trading days are missing from the price history, so the scanner cannot reliably check the chart pattern.';
      case 'Insufficient history or confirmed swing pivots.':
        return 'There are not yet enough price records or confirmed turning points to check for two higher highs and two higher lows.';
      case 'No positive trading volume in the latest candle.':
        return 'The latest candle has no positive recorded trading volume, so the scanner cannot use it to confirm a signal.';
      case 'Close is below the last confirmed swing low: exit condition for an existing long.':
        return numeric(row.close)&&numeric(exit)
          ? 'The latest close of '+money(row.close)+' is below the last confirmed low at '+money(exit)+' (STRUCTURE EXIT). This triggers the strategy\'s exit rule for an existing holding.'
          : fallback;
      case 'Price is below the strategy minimum of Rs 50.':
        return numeric(row.close)?'The closing price of '+money(row.close)+' is below this strategy\'s '+money(50)+' minimum.':fallback;
      case '20-session average traded value is below Rs 10 crore.':
        return numeric(row.turnover_crore)
          ? 'Average daily trading value over the last 20 sessions '+(row.turnover_crore<10?'is '+money(row.turnover_crore)+' crore, below ':'falls below ')+'the '+money(10)+' crore this strategy requires. Trading activity does not pass its buying check.'
          : 'The 20-session average trading value is unavailable, so the strategy\'s trading-activity check cannot pass.';
      case "ATR is outside the strategy's 0.5%-6% price range.":
        return numeric(row.atr_pct)
          ? 'The average daily price range (ATR) is '+row.atr_pct.toLocaleString('en-IN',{maximumFractionDigits:4})+'% of the price, '+(row.atr_pct<.5?'below':'above')+' this strategy\'s allowed range of 0.5% to 6%.'
          : 'The average daily price range (ATR) is unavailable, so the scanner cannot check whether price swings fit this strategy.';
      case 'Fresh HH/HL breakout, but the benchmark data gate is incomplete.':
        return breakout+'The Nifty price history needed for the 200-session market check is incomplete, so the strategy blocks a new buy.';
      case 'Fresh HH/HL breakout, but Nifty is below its 200-session average.': {
        const comparison=numeric(market.close)&&numeric(market.sma200)
          ? 'Nifty closed at '+number(market.close)+', '+(market.close===market.sma200?'equal to':'below')+' its 200-session average of '+number(market.sma200)
          : 'Nifty has not closed above its 200-session average';
        return breakout+comparison+', so the strategy blocks a new buy.';
      }
      case 'Fresh confirmed HH/HL breakout; eligible for a next-session paper entry only.': {
        const band=row.entry_plan?.opening_price_band;
        const opening=Array.isArray(band)&&band.length===2&&band.every(numeric)
          ? ' A paper entry is eligible only at the next session\'s open between '+money(band[0])+' and '+money(band[1])+'.'
          : ' Any paper entry still depends on the next session\'s opening-price check.';
        return breakout+'The market and stock checks pass.'+opening;
      }
      case 'Price is already above resistance; no fresh breakout today. Do not chase.':
        return hasTrigger
          ? 'The close of '+money(row.close)+' is already above '+money(trigger)+' (CLOSING TRIGGER), but there was no fresh crossing above it in the latest session. This strategy requires a new breakout, so this is not a new buy signal.'
          : fallback;
      case 'Higher highs and higher lows confirmed; wait for a fresh closing breakout.': {
        if(!hasTrigger)return fallback;
        const latest=row.chart?.at(-1);
        const wick=numeric(latest?.high)&&latest.high>trigger&&row.close<=trigger;
        return 'The last two confirmed highs and lows are rising (HH/HL). '+
          (wick?'Price went above '+money(trigger)+' during the session, but closed at '+money(row.close)+' without finishing above it. '
            :'The close of '+money(row.close)+' has not finished above '+money(trigger)+' (CLOSING TRIGGER). ')+
          'The scanner is waiting for a fresh close above that level; the other buying checks must also pass.';
      }
      case 'Two rising confirmed highs and two rising confirmed lows are not present.':
        return structureReason(row);
      default:
        return fallback;
    }
  }
  const api={explain};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.HHHLReason=api;
})(typeof globalThis==='object'?globalThis:this);
