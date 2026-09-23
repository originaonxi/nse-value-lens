'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {points,segments}=require('../public/hhhl-chart');
const p=(date,kind,price,label='HH')=>({pivot_date:date,confirmed_on:date,kind,price,label});
test('chart discards off-screen and not-yet-confirmed pivots',()=>{
  const events=[p('2026-09-01','high',100),p('2026-09-02','low',95,'HL'),{...p('2026-09-03','high',110),confirmed_on:'2026-09-06'}];
  const result=points({chart:[{date:'2026-09-02'},{date:'2026-09-03'}],chart_swings:events,data_date:'2026-09-05'});
  assert.deepEqual(result,[events[1]]);
});
test('zigzag alternates extremes and retains the more extreme same-type pivot',()=>{
  const a=p('2026-09-01','low',95),b=p('2026-09-02','high',100),c=p('2026-09-03','high',105),d=p('2026-09-04','low',96);
  assert.deepEqual(segments([a,b,c,d]),[[a,c,d]]);
});
test('outside-bar high and low do not invent an intraday ordering',()=>{
  const a=p('2026-09-01','low',95),b=p('2026-09-02','high',100);
  const both=[p('2026-09-03','high',110),p('2026-09-03','low',90)];
  const c=p('2026-09-04','high',105),d=p('2026-09-05','low',96);
  assert.deepEqual(segments([a,b,...both,c,d]),[[a,b],[c,d]]);
});

test('active rule pivots retain both last highs and lows independently of the zigzag',()=>{
  const high1=p('2026-09-01','high',100),high2=p('2026-09-03','high',105),low1=p('2026-09-02','low',90,'HL'),low2=p('2026-09-04','low',95,'HL');
  const row={chart:[high1,low1,high2,low2].map(x=>({date:x.pivot_date})),chart_swings:[high1,low1,high2,low2],data_date:'2026-09-08',pivots:{high:[high1,high2],low:[low1,low2]}};
  assert.deepEqual(require('../public/hhhl-chart').activePoints(row).map(x=>x.sequence),['H1','L1','H2','L2']);
  assert.equal(require('../public/hhhl-chart').levelStart(row,'high'),'2026-09-03');
  high2.confirmed_on='2026-09-09';
  assert.equal(require('../public/hhhl-chart').levelStart(row,'high'),null);
});
test('chart window limits visible bars without changing full-history pivot metadata',()=>{
  const row={chart:Array.from({length:140},(_,i)=>({date:String(i)})),pivots:{high:[],low:[]}};
  const view=require('../public/hhhl-chart').windowRow(row,70);
  assert.equal(view.chart.length,70);assert.equal(view.chart[0].date,'70');assert.equal(row.chart.length,140);
});
