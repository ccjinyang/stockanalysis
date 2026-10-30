'use strict';
const $ = id => document.getElementById(id);
const canvas = $('chart'), ctx = canvas.getContext('2d');
const compact = n => new Intl.NumberFormat('en', {notation: 'compact', maximumFractionDigits: 2}).format(n);
const price = n => Number(n).toLocaleString('en', {minimumFractionDigits: 2, maximumFractionDigits: 2});
let data = null, rawData = null, start = 0, end = 0, hover = null, hoverY = null, drag = null, geometry = null, busy = false;
let activeTicker = 'AMZN', activeRange = '5y', requestId = 0, controller;
const colors = {ink: '#203c36', muted: '#7d8b80', grid: '#e8ece3', up: '#23715c', down: '#bf6058', profile: '#a5c9bd', gold: '#ae8540'};
const intervalName = () => $('interval').value;
const periodLabel = b => b.date === b.endDate ? b.date : `${b.date} — ${b.endDate}`;

function rememberView() {
  if (!data) return;
  const url = new URL(location.href);
  url.searchParams.set('ticker', data.symbol); url.searchParams.set('range', activeRange);
  url.searchParams.set('interval', intervalName());
  history.replaceState(null, '', url);
}

function setCandles() {
  if (!rawData) return;
  const interval = intervalName();
  data = {...rawData, bars: ChartMath.aggregate(rawData.bars, interval)};
  hover = null; hoverY = null; drag = null;
  $('exchange').textContent = `${data.exchange} · ${{daily:'1D', weekly:'1W', monthly:'1M'}[interval]} · ${data.currency}`;
  $('recent-caption').textContent = `Latest 10 available ${interval} candles · boundary periods may be partial`;
  $('recent').replaceChildren(...data.bars.slice(-10).reverse().map(b => {
    const tr = document.createElement('tr');
    for (const value of [periodLabel(b), ...['open', 'high', 'low', 'close'].map(k => price(b[k])), b.volume.toLocaleString('en')]) {
      const td = document.createElement('td'); td.textContent = value; tr.append(td);
    }
    return tr;
  }));
}

function status(text, error = false) {
  $('status').textContent = text;
  $('status').classList.toggle('error', error);
}

async function load(ticker = $('ticker').value, range = $('range').value, preserve = false) {
  const id = ++requestId;
  if (controller) controller.abort();
  controller = new AbortController();
  busy = true;
  $('load').disabled = true;
  status(`Fetching ${ticker.toUpperCase()} daily history…`);
  try {
    const response = await fetch(`/api/chart?${new URLSearchParams({ticker, range})}`, {signal: controller.signal});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Unable to load this ticker.');
    if (id !== requestId) return;
    const previousDate = data?.bars[start]?.date;
    const count = end - start, wasAtEnd = end === data?.bars.length;
    rawData = result;
    setCandles();
    activeTicker = result.symbol; activeRange = range;
    $('ticker').value = result.symbol; $('range').value = range;
    if (preserve && previousDate) {
      start = Math.max(0, data.bars.findIndex(b => b.date >= previousDate));
      end = Math.min(data.bars.length, start + count);
      if (wasAtEnd) {end = data.bars.length; start = Math.max(0, end - count);}
    } else {start = 0; end = data.bars.length;}
    hover = null;
    const latest = rawData.bars.at(-1), previous = rawData.bars.at(-2);
    const change = latest.close - previous.close, pct = change / previous.close * 100;
    $('symbol').textContent = result.symbol;
    $('company').textContent = result.name;
    $('price').textContent = price(latest.close);
    $('change').textContent = `${change >= 0 ? '+' : ''}${price(change)} (${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%) · ${latest.date}`;
    $('change').className = change >= 0 ? 'positive' : 'negative';
    $('day-volume').textContent = compact(latest.volume);
    const prior = rawData.bars.slice(-21, -1), average = prior.reduce((s, b) => s + b.volume, 0) / prior.length;
    $('volume-ratio').textContent = average ? `${(latest.volume / average).toFixed(2)}× previous ${prior.length}-day average` : 'Prior daily volume unavailable';
    $('empty').hidden = true; $('empty').style.display = 'none';
    for (const button of ['export', 'zoom-in', 'zoom-out', 'reset']) $(button).disabled = false;
    status(`${result.source} · Last bar ${latest.date} (${result.timezone}) · Retrieved ${new Date(result.fetchedAt).toLocaleString()}${result.cached ? ' · Cached' : ''} · May be delayed; newest bar may be incomplete.`);
    rememberView();
    render();
  } catch (error) {
    if (error.name !== 'AbortError') status(`${error.message}${data ? ` Still displaying ${data.symbol}; chart has not changed.` : ''}`, true);
  } finally {
    if (id === requestId) {busy = false; $('load').disabled = false;}
  }
}

function text(value, x, y, color = colors.muted, align = 'left', size = 10) {
  ctx.fillStyle = color; ctx.font = `${size}px -apple-system, BlinkMacSystemFont, sans-serif`;
  ctx.textAlign = align; ctx.fillText(value, x, y);
}
function line(x1, y1, x2, y2, color, dash = []) {
  ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash(dash);
  ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]);
}

function render() {
  $('candle-tooltip').hidden = true;
  const width = canvas.clientWidth, height = canvas.clientHeight, dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#fffefa'; ctx.fillRect(0, 0, width, height);
  if (!data) return;
  const bars = data.bars.slice(start, end), n = bars.length;
  if (!n) return;
  const left = 14, right = width - (width < 500 ? 64 : 86), top = 22, bottom = height - 125;
  const volTop = bottom + 34, volBottom = height - 30;
  const plotWidth = right - left, plotHeight = bottom - top;
  const log = $('log').checked, transform = v => log ? Math.log(v) : v, inverse = v => log ? Math.exp(v) : v;
  let lo = transform(Math.min(...bars.map(b => b.low))), hi = transform(Math.max(...bars.map(b => b.high)));
  const pad = (hi - lo || .1) * .07; lo -= pad; hi += pad;
  const y = v => bottom - (transform(v) - lo) / (hi - lo) * plotHeight;
  const dx = plotWidth / n, x = i => left + (i + .5) * dx;
  // Keep the daily allocation model when candles are grouped into weeks/months.
  const profile = ChartMath.profile(rawData.bars.filter(b => b.date >= bars[0].date && b.date <= bars.at(-1).endDate), 110);
  const maxBin = Math.max(...profile.bins.map(b => b.volume), 1);
  const volMax = Math.max(...bars.map(b => b.volume), 1);
  geometry = {left, right, top, bottom, volBottom, dx, width, height};
  for (let i = 0; i <= 6; i++) {
    const value = inverse(lo + (hi - lo) * i / 6), py = y(value);
    line(left, py, right, py, colors.grid);
    text(price(value), right + 9, py + 3);
  }
  for (const bin of profile.bins) {
    ctx.fillStyle = colors.profile;
    ctx.globalAlpha = .58;
    ctx.fillRect(left, y(bin.high), bin.volume / maxBin * plotWidth * .29, Math.max(.6, y(bin.low) - y(bin.high) - .7));
  }
  ctx.globalAlpha = 1;
  const pocY = y(profile.poc);
  line(left, pocY, right, pocY, colors.gold, [5, 4]);
  text(`POC ${price(profile.poc)}`, left + 6, pocY - 7, colors.gold);
  ctx.save(); ctx.beginPath(); ctx.rect(left, top, plotWidth, plotHeight); ctx.clip();
  bars.forEach((b, i) => {
    const px = x(i), color = b.close >= b.open ? colors.up : colors.down;
    line(px, y(b.high), px, y(b.low), color);
    ctx.fillStyle = color;
    ctx.fillRect(px - Math.max(1, dx * .65) / 2, Math.min(y(b.open), y(b.close)), Math.max(1, dx * .65), Math.max(1, Math.abs(y(b.open) - y(b.close))));
  });
  ctx.restore();
  const last = data.bars.at(-1);
  if (last.close > inverse(lo) && last.close < inverse(hi)) {
    const py = y(last.close);
    line(left, py, right, py, colors.ink, [2, 4]);
    ctx.fillStyle = colors.ink; ctx.fillRect(right + 2, py - 10, width - right - 4, 20);
    text(price(last.close), right + 8, py + 4, '#ffffff');
  }
  line(left, volTop - 12, right, volTop - 12, colors.grid);
  text(`${intervalName().toUpperCase()} VOLUME`, left + 4, volTop - 19, colors.muted, 'left', 9);
  bars.forEach((b, i) => {
    ctx.fillStyle = b.close >= b.open ? '#a5bfb0' : '#d5b5ad';
    const h = b.volume / volMax * (volBottom - volTop);
    ctx.fillRect(x(i) - Math.max(1, dx * .7) / 2, volBottom - h, Math.max(1, dx * .7), h);
  });
  text(compact(volMax), right + 9, volTop + 5);
  const ticks = Math.max(2, Math.floor(plotWidth / 150));
  for (let t = 0; t < ticks; t++) {
    const i = Math.round(t * (n - 1) / (ticks - 1));
    text(bars[i].date, x(i), height - 10, colors.muted, t === 0 ? 'left' : t === ticks - 1 ? 'right' : 'center');
  }
  if (hover !== null && hover >= start && hover < end) {
    const b = data.bars[hover], px = x(hover - start);
    line(px, top, px, volBottom, '#7c8c80', [3, 3]);
    if (hoverY !== null && hoverY >= top && hoverY <= volBottom) {
      line(left, hoverY, right, hoverY, '#7c8c80', [3, 3]);
      if (hoverY <= bottom) {
        const cursorPrice = inverse(lo + (bottom - hoverY) / plotHeight * (hi - lo));
        ctx.fillStyle = colors.ink;
        ctx.fillRect(right + 2, hoverY - 10, width - right - 4, 20);
        text(price(cursorPrice), right + 8, hoverY + 4, '#ffffff');
      }
    }
    ctx.beginPath(); ctx.fillStyle = colors.ink; ctx.arc(px, y(b.close), 3.5, 0, Math.PI * 2); ctx.fill();
    $('readout').textContent = `${periodLabel(b)}   O ${price(b.open)}   H ${price(b.high)}   L ${price(b.low)}   C ${price(b.close)}   VOL ${b.volume.toLocaleString('en')}`;
    if (hoverY !== null && hoverY >= top && hoverY <= volBottom) {
      const tooltip = $('candle-tooltip');
      $('tooltip-date').textContent = `${intervalName()[0].toUpperCase() + intervalName().slice(1)} · ${periodLabel(b)}`;
      for (const key of ['open', 'high', 'low', 'close']) $('tooltip-' + key).textContent = `${price(b[key])} ${data.currency}`;
      $('tooltip-volume').textContent = `${b.volume.toLocaleString('en')} shares`;
      tooltip.hidden = false;
      const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
      tooltip.style.left = `${Math.max(4, Math.min(width - tw - 4, px + tw + 18 > right ? px - tw - 14 : px + 14))}px`;
      tooltip.style.top = `${Math.max(4, Math.min(height - th - 4, hoverY + 14))}px`;
    }
  } else {
    $('readout').textContent = `${data.symbol} · ${n.toLocaleString()} ${intervalName()} candles · ${data.currency} · ${log ? 'Logarithmic' : 'Linear'} price scale`;
  }
  $('dates').textContent = `${bars[0].date} — ${bars.at(-1).endDate}`;
  $('total-volume').textContent = compact(profile.total);
  $('poc').textContent = `${price(profile.poc)} ${data.currency}`;
}

function zoom(factor, anchor = .5) {
  if (!data) return;
  const oldCount = end - start, min = Math.min(20, data.bars.length);
  const count = Math.min(data.bars.length, Math.max(min, Math.round(oldCount * factor)));
  const center = start + oldCount * anchor;
  start = Math.max(0, Math.min(data.bars.length - count, Math.round(center - count * anchor)));
  end = start + count; hover = null; render();
}
function reset() {if (data) {start = 0; end = data.bars.length; hover = null; render();}}
$('search').addEventListener('submit', event => {event.preventDefault(); load();});
$('log').addEventListener('change', render);
$('interval').addEventListener('change', () => {
  if (!rawData) return;
  setCandles(); start = 0; end = data.bars.length; rememberView(); render();
});
$('zoom-in').addEventListener('click', () => zoom(.7));
$('zoom-out').addEventListener('click', () => zoom(1.4));
$('reset').addEventListener('click', reset);
canvas.addEventListener('dblclick', reset);
canvas.addEventListener('wheel', event => {
  if (!data || !geometry) return;
  event.preventDefault();
  const {left, right} = geometry;
  const anchor = Math.max(0, Math.min(1, (event.clientX - canvas.getBoundingClientRect().left - left) / (right - left)));
  zoom(event.deltaY < 0 ? .85 : 1.18, anchor);
}, {passive: false});
canvas.addEventListener('pointerdown', event => {
  if (!data || !geometry) return;
  drag = {x: event.clientX, start, count: end - start, dx: geometry.dx};
  canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener('pointermove', event => {
  if (!data || !geometry) return;
  if (drag) {
    start = Math.max(0, Math.min(data.bars.length - drag.count, drag.start - Math.round((event.clientX - drag.x) / drag.dx)));
    end = start + drag.count; hover = null;
  } else {
    const rect = canvas.getBoundingClientRect();
    const px = event.clientX - rect.left;
    hoverY = event.clientY - rect.top;
    hover = px < geometry.left || px > geometry.right || hoverY < geometry.top || hoverY > geometry.volBottom ? null : Math.min(end - 1, start + Math.floor((px - geometry.left) / geometry.dx));
  }
  render();
});
canvas.addEventListener('pointerup', () => {drag = null;});
canvas.addEventListener('pointercancel', () => {drag = null;});
canvas.addEventListener('pointerleave', () => {if (!drag) {hover = null; render();}});
canvas.addEventListener('keydown', event => {
  if (!data || !['+', '=', '-', 'ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
  event.preventDefault();
  if (event.key === '+' || event.key === '=') zoom(.7);
  else if (event.key === '-') zoom(1.4);
  else if (event.key === 'Home') reset();
  else {
    const count = end - start, delta = Math.max(1, Math.round(count * .1)) * (event.key === 'ArrowLeft' ? -1 : 1);
    start = Math.max(0, Math.min(data.bars.length - count, start + delta)); end = start + count; hover = null; render();
  }
});
$('export').addEventListener('click', () => {
  if (!data) return;
  hover = null; render();
  const output = document.createElement('canvas'), dpr = window.devicePixelRatio || 1;
  output.width = canvas.width; output.height = canvas.height + Math.round(100 * dpr);
  const c = output.getContext('2d'); c.fillStyle = '#fffefa'; c.fillRect(0, 0, output.width, output.height);
  c.drawImage(canvas, 0, Math.round(52 * dpr));
  c.scale(dpr, dpr); c.fillStyle = colors.ink; c.font = '16px sans-serif';
  c.fillText(`${data.symbol} · ${intervalName()} OHLCV · ${data.currency}`, 16, 29);
  c.font = '10px sans-serif';
  c.fillText(`${$('dates').textContent} · Est. profile: uniform volume over each daily low–high · Yahoo Finance`, 16, output.height / dpr - 28);
  c.fillText(`Retrieved ${data.fetchedAt} · Latest daily bar may be incomplete`, 16, output.height / dpr - 12);
  output.toBlob(blob => {
    if (!blob) return;
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.download = `${data.symbol}-${intervalName()}-volume.png`; link.href = url; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
});
new ResizeObserver(render).observe(canvas);
setInterval(() => {if ($('auto').checked && !busy && data && !document.hidden) load(activeTicker, activeRange, true);}, 300000);
async function init() {
  const params = new URLSearchParams(location.search);
  try {
    const response = await fetch('/api/health'), config = await response.json();
    $('ticker').value = params.get('ticker') || config.defaultTicker;
    const range = params.get('range');
    if ([...$('range').options].some(o => o.value === range)) $('range').value = range;
    const interval = params.get('interval');
    if (['daily', 'weekly', 'monthly'].includes(interval)) $('interval').value = interval;
  } catch {status('Cannot connect to chart service.', true); return;}
  load();
}
init();
