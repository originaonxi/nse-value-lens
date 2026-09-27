'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {explain}=require('../public/hhhl-reason');
const reason={
  sell:'Close is below the last confirmed swing low: exit condition for an existing long.',
  watch:'Higher highs and higher lows confirmed; wait for a fresh closing breakout.',
  structure:'Two rising confirmed highs and two rising confirmed lows are not present.',
  price:'Price is below the strategy minimum of Rs 50.',
  liquidity:'20-session average traded value is below Rs 10 crore.',
  volatility:"ATR is outside the strategy's 0.5%-6% price range.",
  market:'Fresh HH/HL breakout, but Nifty is below its 200-session average.',
  marketData:'Fresh HH/HL breakout, but the benchmark data gate is incomplete.',
  late:'Price is already above resistance; no fresh breakout today. Do not chase.',
  buy:'Fresh confirmed HH/HL breakout; eligible for a next-session paper entry only.'
};
const row=changes=>({status:'WATCH',reason:reason.watch,close:105,data_date:'2026-09-25',zones:{breakout_above:110,structure_exit_below:100},chart:[{high:109,close:105}],...changes});
const pivot=price=>({price,confirmed_on:'2026-09-24'});

test('an ongoing SELL explains the exact close and exit, even below the minimum stock price',()=>{
  const text=explain(row({status:'SELL',reason:reason.sell,close:40,zones:{structure_exit_below:45},sell_triggered_today:false}));
  assert.match(text,/₹40\.00.*below.*₹45\.00.*STRUCTURE EXIT/);
  assert.match(text,/existing holding/);
  assert.doesNotMatch(text,/new.*sell|minimum|short|today/i);
});
test('mixed structure states the actual directions rather than claiming both highs and lows fell',()=>{
  const text=explain(row({status:'AVOID',reason:reason.structure,pivots:{high:[pivot(130),pivot(120)],low:[pivot(90),pivot(100)]}}));
  assert.match(text,/highs fell from ₹130\.00 to ₹120\.00/);
  assert.match(text,/lows rose from ₹90\.00 to ₹100\.00/);
  assert.match(text,/both highs and lows to rise/);
});
test('equal highs are not described as rising or falling',()=>{
  const text=explain(row({reason:reason.structure,pivots:{high:[pivot(120),pivot(120)],low:[pivot(90),pivot(100)]}}));
  assert.match(text,/highs stayed at ₹120\.00/);
});
test('unconfirmed future turning points are not used in the explanation',()=>{
  const text=explain(row({reason:reason.structure,pivots:{high:[pivot(130),{price:120,confirmed_on:'2026-09-28'}],low:[pivot(90),pivot(100)]}}));
  assert.doesNotMatch(text,/₹120\.00/);
});
test('WATCH distinguishes an intraday crossing from a closing breakout, including an equal close',()=>{
  const text=explain(row({close:110,chart:[{high:112,close:110}]}));
  assert.match(text,/went above ₹110\.00 during the session/);
  assert.match(text,/without finishing above it/);
  assert.match(text,/other buying checks must also pass/);
  assert.doesNotMatch(text,/made a fresh close/);
});
test('WATCH without an intraday crossing uses the closing trigger',()=>{
  const text=explain(row({}));
  assert.match(text,/₹105\.00.*₹110\.00 \(CLOSING TRIGGER\)/);
  assert.doesNotMatch(text,/went above/);
});
test('a rising chart can be AVOID because the price screen is the recorded cause',()=>{
  const text=explain(row({status:'AVOID',reason:reason.price,close:40,structure:'HH / HL'}));
  assert.match(text,/₹40\.00.*₹50\.00 minimum/);
  assert.doesNotMatch(text,/fall|pattern/);
});
test('liquidity explains low, missing and threshold-rounded averages without inventing a value',()=>{
  assert.match(explain(row({reason:reason.liquidity,turnover_crore:8})),/₹8\.00 crore.*₹10\.00 crore/);
  assert.match(explain(row({reason:reason.liquidity,turnover_crore:null})),/unavailable/);
  assert.doesNotMatch(explain(row({reason:reason.liquidity,turnover_crore:10})),/₹10\.00 crore, below.*₹10\.00/);
});
test('volatility explains low and high ranges and preserves precision near a threshold',()=>{
  assert.match(explain(row({reason:reason.volatility,atr_pct:.499})),/0\.499%.*below/);
  assert.match(explain(row({reason:reason.volatility,atr_pct:7})),/7%.*above/);
  assert.match(explain(row({reason:reason.volatility,atr_pct:null})),/unavailable/);
});
test('market-blocked CAUTION identifies the separate Nifty check despite a stock breakout',()=>{
  const text=explain(row({status:'CAUTION',reason:reason.market,close:115}),{close:23000,sma200:24000});
  assert.match(text,/fresh close at ₹115\.00 above ₹110\.00/);
  assert.match(text,/Nifty closed at 23,000\.00, below.*24,000\.00/);
  assert.match(text,/blocks a new buy/);
});
test('an equal Nifty close is not falsely described as below its average',()=>{
  assert.match(explain(row({reason:reason.market}),{close:24000,sma200:24000}),/equal to/);
});
test('missing Nifty history is not mistaken for a falling market',()=>{
  const text=explain(row({reason:reason.marketData,close:115}),{data_ready:false,reference_filter_passed:true});
  assert.match(text,/Nifty price history.*incomplete/);
  assert.doesNotMatch(text,/Nifty.*below/);
});
test('late CAUTION does not claim a fresh breakout simply because close is above resistance',()=>{
  const text=explain(row({reason:reason.late,close:115,fresh_breakout:false}));
  assert.match(text,/already above ₹110\.00/);
  assert.match(text,/no fresh crossing/);
});
test('BUY remains conditional on the next opening price and uses the actual band',()=>{
  const text=explain(row({status:'BUY',reason:reason.buy,close:115,entry_plan:{opening_price_band:[112,118]}}));
  assert.match(text,/market and stock checks pass/);
  assert.match(text,/only at the next session's open between ₹112\.00 and ₹118\.00/);
});
test('data problems give the specific recorded cause rather than interpreting unreliable candles',()=>{
  const cases=[
    ['Price history unavailable.',/Price history is unavailable/],
    ['No complete candle for the requested session.',/no complete price candle/],
    ['Missing price sessions in the structure lookback.',/trading days are missing/],
    ['Insufficient history or confirmed swing pivots.',/not yet enough price records/],
    ['No positive trading volume in the latest candle.',/no positive recorded trading volume/]
  ];
  for(const [recorded,expected] of cases){
    const text=explain(row({reason:recorded,status:'CAUTION',close:20,exit_condition:true}));
    assert.match(text,expected);assert.doesNotMatch(text,/exit rule|blocks a new buy/);
  }
});
test('unknown reasons are retained rather than replaced by a guessed classification',()=>{
  const source=row({reason:'New scanner condition'}),copy=structuredClone(source);
  assert.equal(explain(source),'New scanner condition');assert.deepEqual(source,copy);
});
