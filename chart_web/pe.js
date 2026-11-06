/* Historical forward P/E: plot provider observations without filling missing dates. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const canvas = $('pe-chart'), ctx = canvas.getContext('2d');
  const format = value => `${value.toFixed(2)}×`;
  let result = null, bars = [], pending = false, error = '', request = 0, controller;
  let selected = null, pointerY = 50, positions = [], cursorDate = null;

  async function load(symbol, range) {
    const id = ++request;
    if (controller) controller.abort();
    controller = new AbortController();
    pending = true; result = null; error = ''; selected = null;
    $('pe-title').textContent = `Historical Forward P/E · ${symbol}`;
    $('pe-source').textContent = 'Yahoo Finance · Loading valuation observations…';
    render();
    try {
      const response = await fetch(`/api/forward-pe?${new URLSearchParams({ticker:symbol, range})}`, {signal:controller.signal});
      const payload = await response.json();
      if (id !== request) return;
      if (!response.ok) throw new Error(payload.error || 'Could not retrieve historical forward P/E.');
      result = payload;
      $('pe-source').textContent = `${payload.source} · Retrieved ${new Date(payload.fetchedAt).toLocaleString()}${payload.cached ? ' · Cached' : ''}`;
    } catch (exc) {
      if (id !== request || exc.name === 'AbortError') return;
      error = exc.message;
      $('pe-source').textContent = 'Valuation data unavailable · Price chart remains available';
    } finally {
      if (id === request) {pending = false; render();}
    }
  }

  function dateX(date, left, right) {
    // Match the candle containing this date, or the preceding trading candle
    // for weekend/holiday observation dates. Never move it into a later period.
    let lo = 0, hi = bars.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (bars[mid].date <= date) lo = mid + 1;
      else hi = mid;
    }
    return left + (Math.max(0, lo - 1) + .5) / bars.length * (right - left);
  }

  function render() {
    const width = canvas.clientWidth, height = canvas.clientHeight, dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#fffefa'; ctx.fillRect(0, 0, width, height);
    $('pe-tooltip').hidden = true; positions = [];
    const first = bars[0]?.date, last = bars.at(-1)?.endDate;
    const points = (result?.points || []).filter(p => p.date >= first && p.date <= last);
    let message = '';
    if (pending) message = 'Loading historical forward P/E…';
    else if (error) message = error;
    else if (!result) message = 'Load a ticker to view its available valuation history.';
    else if (!result.points.length) message = result.message;
    else if (!points.length) message = 'No reported forward P/E observations in the visible range. Zoom out or choose a longer history.';
    $('pe-empty').textContent = message; $('pe-empty').hidden = !message;
    $('pe-retry').hidden = !error;
    const latest = points.at(-1);
    $('pe-latest').textContent = latest ? format(latest.value) : '—';
    $('pe-asof').textContent = latest ? `As of ${latest.date} · ${latest.frequency}` : 'No observation in view';
    $('pe-readout').textContent = points.length ? `${points.length} reported observations in view · ${points[0].date} — ${latest.date} · No values inferred between observations` : 'Only reported observations are shown; missing dates are not filled.';
    if (!points.length || !bars.length || pending || error) return;
    const left = 14, right = width - (width < 500 ? 64 : 86), top = 22, bottom = height - 36;
    const values = points.map(p => p.value), min = Math.min(...values), max = Math.max(...values);
    const pad = (max - min || Math.max(max * .1, 1)) * .15;
    const low = Math.max(0, min - pad), high = max + pad;
    const y = value => bottom - (value - low) / (high - low) * (bottom - top);
    function text(value, x, py, color = '#7d8b80', align = 'left') {
      ctx.fillStyle = color; ctx.font = '10px -apple-system, BlinkMacSystemFont, sans-serif'; ctx.textAlign = align; ctx.fillText(value, x, py);
    }
    function line(x1, y1, x2, y2, color = '#e8ece3', dash = []) {
      ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash(dash);
      ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]);
    }
    for (let i = 0; i <= 4; i++) {
      const value = low + (high - low) * i / 4, py = y(value);
      line(left, py, right, py); text(format(value), right + 9, py + 3);
    }
    const ticks = Math.max(2, Math.floor((right - left) / 150));
    for (let i = 0; i < ticks; i++) {
      const bar = bars[Math.round(i * (bars.length - 1) / (ticks - 1))];
      text(bar.date, dateX(bar.date, left, right), height - 12, '#7d8b80', i === 0 ? 'left' : i === ticks - 1 ? 'right' : 'center');
    }
    positions = points.map(p => ({...p, x:dateX(p.date, left, right), y:y(p.value)}));
    for (let i = 1; i < positions.length; i++) {
      const previous = positions[i - 1], p = positions[i];
      line(previous.x, previous.y, p.x, p.y, '#8cae9b', [3, 5]);
    }
    for (const p of positions) {
      ctx.beginPath(); ctx.fillStyle = '#23715c'; ctx.arc(p.x, p.y, 4, 0, Math.PI * 2); ctx.fill();
    }
    if (cursorDate && cursorDate >= first && cursorDate <= last) {
      const x = dateX(cursorDate, left, right); line(x, top, x, bottom, '#7c8c80', [3, 3]);
    }
    const point = positions.find(p => p.date === selected);
    if (point) {
      line(point.x, top, point.x, bottom, '#7c8c80', [3, 3]);
      line(left, point.y, right, point.y, '#7c8c80', [3, 3]);
      ctx.fillStyle = '#203c36'; ctx.fillRect(right + 2, point.y - 10, width - right - 4, 20);
      text(format(point.value), right + 8, point.y + 4, '#ffffff');
      const tooltip = $('pe-tooltip');
      tooltip.textContent = `${point.date} · Forward P/E ${format(point.value)} · ${point.frequency} observation`;
      tooltip.hidden = false;
      tooltip.style.left = `${Math.max(4, Math.min(width - tooltip.offsetWidth - 4, point.x + 14))}px`;
      tooltip.style.top = `${Math.max(4, Math.min(height - tooltip.offsetHeight - 4, pointerY + 14))}px`;
      $('pe-readout').textContent = `${point.date} · Forward P/E ${format(point.value)} · Reported ${point.frequency} observation`;
    }
  }

  canvas.addEventListener('pointermove', event => {
    if (!positions.length) return;
    const rect = canvas.getBoundingClientRect(), x = event.clientX - rect.left;
    pointerY = event.clientY - rect.top;
    selected = x < 14 || x > canvas.clientWidth - (canvas.clientWidth < 500 ? 64 : 86) ? null : positions.reduce((a, b) => Math.abs(b.x - x) < Math.abs(a.x - x) ? b : a).date;
    render();
  });
  canvas.addEventListener('pointerleave', () => {selected = null; render();});
  canvas.addEventListener('blur', () => {selected = null; render();});
  canvas.addEventListener('keydown', event => {
    if (!positions.length || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const index = positions.findIndex(p => p.date === selected);
    selected = positions[Math.max(0, Math.min(positions.length - 1, index < 0 ? 0 : index + (event.key === 'ArrowLeft' ? -1 : 1)))].date;
    render();
  });
  new ResizeObserver(render).observe(canvas);
  window.PEChart = {load, setRange(visibleBars, date) {bars = visibleBars; cursorDate = date; render();}};
})();
