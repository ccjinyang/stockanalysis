/* Daily-bar volume approximation: allocate volume by overlap with price bins.
   This conserves total volume. Candle direction is not trade aggressor direction. */
(function (root) {
  'use strict';
  function aggregate(bars, interval = 'daily') {
    if (interval === 'daily') return bars.map(b => ({...b, endDate: b.date}));
    if (!['weekly', 'monthly'].includes(interval)) throw new Error('Unsupported candle interval');
    const groups = new Map();
    for (const bar of bars) {
      const date = new Date(`${bar.date}T00:00:00Z`);
      if (interval === 'weekly') date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
      else date.setUTCDate(1);
      const key = date.toISOString().slice(0, 10);
      const current = groups.get(key);
      if (!current) groups.set(key, {...bar, endDate: bar.date});
      else {
        current.high = Math.max(current.high, bar.high);
        current.low = Math.min(current.low, bar.low);
        current.close = bar.close;
        current.volume += bar.volume;
        current.endDate = bar.date;
      }
    }
    return [...groups.values()];
  }
  function profile(bars, count = 100) {
    if (!bars.length) return {bins: [], poc: null, total: 0};
    const low = Math.min(...bars.map(b => b.low));
    const high = Math.max(...bars.map(b => b.high));
    const step = (high - low || Math.max(low * .001, .01)) / count;
    const bins = Array.from({length: count}, (_, i) => ({low: low + i * step, high: low + (i + 1) * step, volume: 0}));
    for (const bar of bars) {
      if (bar.high === bar.low) {
        bins[Math.min(count - 1, Math.max(0, Math.floor((bar.low - low) / step)))].volume += bar.volume;
        continue;
      }
      for (const bin of bins) {
        const overlap = Math.max(0, Math.min(bar.high, bin.high) - Math.max(bar.low, bin.low));
        bin.volume += bar.volume * overlap / (bar.high - bar.low);
      }
    }
    const poc = bins.reduce((a, b) => b.volume > a.volume ? b : a);
    return {bins, poc: (poc.low + poc.high) / 2, total: bars.reduce((s, b) => s + b.volume, 0)};
  }
  root.ChartMath = {profile, aggregate};
  if (typeof module !== 'undefined') module.exports = root.ChartMath;
})(typeof window !== 'undefined' ? window : globalThis);
