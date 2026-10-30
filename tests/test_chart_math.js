'use strict';
const assert = require('node:assert/strict');
const {profile, aggregate} = require('../chart_web/math.js');
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-7 * Math.max(1, b), `${a} != ${b}`);
// Volume spanning two bins must be apportioned by overlap, not duplicated.
let p = profile([{low: 10, high: 20, volume: 100}, {low: 10, high: 15, volume: 100}], 2);
close(p.bins[0].volume, 150); close(p.bins[1].volume, 50); close(p.poc, 12.5);
// Flat days, including a bar exactly at the upper boundary, conserve volume.
p = profile([{low: 10, high: 10, volume: 50}, {low: 20, high: 20, volume: 70}], 20);
close(p.bins.reduce((s, b) => s + b.volume, 0), 120);
close(p.bins.at(-1).volume, 70);
p = profile([{low: 10, high: 10, volume: 80}], 100);
close(p.total, 80); close(p.bins.reduce((s, b) => s + b.volume, 0), 80);
assert.deepEqual(profile([]), {bins: [], poc: null, total: 0});
// A broad set of uneven decimal ranges should conserve total volume.
const bars = Array.from({length: 1000}, (_, i) => ({low: 10 + i / 317, high: 11.1 + i / 231, volume: 1000 + i * 17}));
p = profile(bars, 110);
close(p.bins.reduce((s, b) => s + b.volume, 0), p.total);
assert.ok(p.poc >= bars[0].low && p.poc <= bars.at(-1).high);
console.log('Volume profile tests passed.');
const daily = [
  {date:'2024-12-27', open:10, high:14, low:9, close:13, volume:100},
  {date:'2024-12-30', open:13, high:16, low:12, close:15, volume:200},
  {date:'2024-12-31', open:15, high:17, low:11, close:12, volume:300},
  {date:'2025-01-02', open:12, high:15, low:10, close:14, volume:400},
  {date:'2025-01-06', open:14, high:19, low:13, close:18, volume:500},
];
const before = JSON.stringify(daily);
const weekly = aggregate(daily, 'weekly');
assert.equal(weekly.length, 3);
assert.deepEqual(weekly[1], {date:'2024-12-30',endDate:'2025-01-02',open:13,high:17,low:10,close:14,volume:900});
const monthly = aggregate(daily, 'monthly');
assert.equal(monthly.length, 2);
assert.deepEqual(monthly[0], {date:'2024-12-27',endDate:'2024-12-31',open:10,high:17,low:9,close:12,volume:600});
assert.equal(monthly[1].volume, 900);
assert.equal(aggregate(daily, 'daily').length, 5);
assert.equal(JSON.stringify(daily), before);
assert.deepEqual(aggregate([], 'monthly'), []);
assert.throws(() => aggregate(daily, 'yearly'));
console.log('Daily/weekly/monthly candle aggregation tests passed.');
