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
