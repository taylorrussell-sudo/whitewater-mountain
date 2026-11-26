(() => {
  'use strict';

  document.title = 'Whitewater · Mountain Conditions';

  const timeFormat = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Vancouver', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
  const dayFormat = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Vancouver', month: 'short', day: 'numeric',
  });
  const date = value => new Date(typeof value === 'number' ? value * 1000 : value);
  const time = value => value == null ? '—' : timeFormat.format(date(value));
  const rounded = value => Number(value.toFixed(1));
  const units = (value, unit) => Number.isFinite(value) ? `${rounded(value)} ${unit}` : 'Unavailable';
  const temperature = value => Number.isFinite(value) ? fmt(rounded(value)) : 'Unavailable';
  const lower = value => value[0].toLowerCase() + value.slice(1);
  const rendered = new WeakMap();
  const escape = text => String(text).replace(/[&<>"']/g, char =>
    ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'})[char]);
  const link = (url, label) => url?.startsWith('https://')
    ? `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(label)}</a>`
    : escape(label);
  const credit = source => source
    ? `${link(source.link, source.credit)} · ${link(source.licence, 'Licence')}` : '';
  const sourceStatus = source => ({
    fresh: 'Fresh', stale: 'Stale', unavailable: 'Unavailable', disabled: 'Collection disabled',
  })[source?.status] ?? 'Unavailable';
  const fresh = source => source?.status === 'fresh' ? source.data : null;
  const outcomes = {
    queued: 'Queued', checking: 'Checking…', updated: 'Check succeeded',
    failed: 'Check failed', backoff: 'Skipped · source backoff',
    provider_blocked: 'Skipped · provider blocked', provider_cooldown: 'Skipped · provider cooldown',
    recently_checked: 'Skipped · recently checked', interrupted: 'Interrupted',
  };
  const sourceNames = {
    ifs: 'ECMWF IFS HRES', hrdps: 'Canadian HRDPS', nelson_cs: 'Nelson CS',
    freezing_profile: 'NOAA GFS', whitewater: 'Whitewater resort', southridge: 'Southridge',
  };

  const html = (id, value) => {
    const element = $(id);
    if (rendered.get(element) !== value) {
      element.innerHTML = value;
      rendered.set(element, value);
    }
  };
  const text = (id, value) => {
    if ($(id).textContent !== value) $(id).textContent = value;
  };
  const row = (label, value) => `<div class="row"><span>${label}</span><strong>${value}</strong></div>`;
  const metric = (label, value, note = '', status) =>
    `<div class="metric"><strong${value === 'Unavailable' ? ' class="missing"' : ''}>${value}</strong>
     <span>${label}</span>${note ? `<small>${note}</small>` : ''}${status ? `<span> · ${status}</span>` : ''}</div>`;
  const box = (label, value) => `<div><strong>${value}</strong><span>${label}</span></div>`;
  const hour = 3600;
  const timeSeries = (point, field) => new Map(
    (point?.times ?? []).map((at, index) => [at, point.values[field][index]]));

  function nextValue(point, field, anchor) {
    for (const [at, value] of timeSeries(point, field)) {
      if (at >= anchor && Number.isFinite(value)) return {at, value};
    }
    return {};
  }

  function snowDays(point, start) {
    const snow = timeSeries(point, 'snowfall');
    return Array.from({length: 7}, (_, day) => {
      const values = Array.from({length: 24}, (_, i) => snow.get(start + (day * 24 + i + 1) * hour));
      return values.every(Number.isFinite) ? sum(values) : null;
    });
  }

  function inversion(source, anchor) {
    const model = fresh(source);
    const lodge = timeSeries(model?.points.lodge, 'temperature_2m');
    const valley = timeSeries(model?.points.nelson, 'temperature_2m');
    const samples = [...lodge].filter(([at]) => at >= anchor).map(([at, value]) =>
      stationSamples('forecast', at / hour, valley.get(at), value));
    return forecastInversion(samples, 1);
  }

  function renderLiveInversion(ifs, hrdps, anchor) {
    const forecast = inversion(ifs, anchor);
    const shortRange = inversion(hrdps, anchor);
    const panel = $('inversion-timing');
    const context = $('inversion-ski-context');
    const range = bounds => bounds ? bounds.map(at => time(at * hour)).join(' – ') : 'unavailable';
    const validTime = pair => pair ? `Peak · ${time(pair.hour * hour)}` : null;
    const primary = forecast.pair;
    html('temperature-plot', temperaturePlot(null, primary));
    html('inversion-comparison',
      inversionIndicator(primary, true, {source: 'ECMWF IFS HRES', validTime: validTime(primary)}) +
      inversionIndicator(shortRange.pair, true, {source: 'Canadian HRDPS', validTime: validTime(shortRange.pair)}));
    panel.hidden = !(primary?.delta > 0);
    const duration = forecast.duration ? `${forecast.duration.join('–')} h` : 'unavailable';
    text('inversion-timing', panel.hidden ? '' :
      `IFS onset ${range(forecast.onset)} · Dissipation ${range(forecast.dissipation)} · Duration ${duration}`);
    const ski = inversionSkiContext(primary, null, 'forecast');
    context.hidden = !ski;
    html('inversion-ski-context', ski ? `<p>IFS · ${ski.thermal} ${ski.skyNote}</p>` : '');
  }

  function crossingsText(crossings) {
    if (!crossings) return 'Unavailable';
    if (!crossings.length) return 'No crossing detected in sampled layers';
    return crossings.map(({lower_m, upper_m}) => lower_m === upper_m
      ? `${Math.round(lower_m)} m`
      : `${Math.round(lower_m)}–${Math.round(upper_m)} m`).join(', ');
  }

  function renderFreezing(source, anchor) {
    const data = fresh(source);
    const current = data?.crossings[data.times.indexOf(anchor)] ?? null;
    html('profile', profile(current, 'main'));
    html('profile-valid', `GFS derived · ${crossingsText(current)}${current ? ` · Valid ${time(anchor)}` : ''}${source ? `<br>${credit(source)}` : ''}`);
    const rows = data?.times.map((at, i) => at >= anchor
      ? `<tr><th scope="row">${time(at)}</th><td>${crossingsText(data.crossings[i])}</td></tr>` : '').join('');
    html('freezechart', rows ? `<details><summary>Hourly crossings · ${time(data.times.at(-1))} horizon</summary>
      <table class="live-table"><thead><tr><th scope="col">Valid time</th><th scope="col">Detected 0°C levels</th></tr></thead>
      <tbody>${rows}</tbody></table></details><p class="smallnote">${credit(source)}</p>` :
      `<p>${sourceStatus(source)}</p>${source ? `<p class="smallnote">${credit(source)}</p>` : ''}`);
  }

  function renderWeather(weather) {
    const sources = weather?.sources ?? {};
    const {ifs, hrdps, nelson_cs: nelson, freezing_profile: freezing} = sources;
    const anchor = Math.floor(Date.parse(weather?.as_of) / (1000 * hour)) * hour;
    const lodge = fresh(ifs)?.points.lodge;
    const hrdpsData = fresh(hrdps);
    const shortPoint = hrdpsData?.points.lodge;
    const reading = fresh(nelson);
    const temp = nextValue(lodge, 'temperature_2m', anchor);
    const wind = nextValue(lodge, 'wind_speed_10m', anchor);
    const shortTemp = nextValue(shortPoint, 'temperature_2m', anchor);
    const shortWind = nextValue(shortPoint, 'wind_speed_10m', anchor);
    const snow = fresh(ifs)?.lodge_snowfall_windows;
    const next = snow?.totals_cm;
    const peak = snow?.max_rolling_24h;
    const daily = snowDays(lodge, snow?.start);
    const chartDays = Array.from({length: 7}, (_, i) => `Day ${i + 1}`);
    const chart = bars({snow: daily.map(value => value === null ? null : rounded(value))}, chartDays);
    const lodgeTemps = timeSeries(lodge, 'temperature_2m');

    html('metrics', [
      metric('Nelson CS · measured', temperature(reading?.temperature_c), reading ?
        `<br>Valid ${time(reading.valid_at)}` : '', sourceStatus(nelson)),
      metric('Lodge · IFS forecast', temperature(temp.value), temp.at ? `<br>Valid ${time(temp.at)}` : '', sourceStatus(ifs)),
      metric('Lodge wind · IFS forecast', units(wind.value, 'km/h'), wind.at ? `<br>Valid ${time(wind.at)}` : '', sourceStatus(ifs)),
      metric('Snow · IFS next 24 h', units(next?.[24], 'cm'), Number.isFinite(next?.[24]) ?
        `<br>Ends ${time(snow.start + 24 * hour)}` : '', sourceStatus(ifs)),
      metric('Reported snow · last 24 h', 'Unavailable'),
      metric('Lodge · measured', 'Unavailable'),
    ].join(''));
    const rings = `<div class="powderpair">${ring(null, false, 'LAST 24 HOURS', 'Whitewater')}
      ${ring(peak?.cm ?? null, true, 'PEAK 24H', 'IFS HRES')}</div>`;
    html('powdercards', rings);
    html('powdercards2', rings);
    text('powdersummary', peak ? `IFS peak · ${time(peak.start)} – ${time(peak.end)}`
      : 'Peak forecast unavailable. A complete 72-hour window is required.');
    html('overviewchart', chart);
    html('powderchart', chart);
    html('dailystrip', daily.map((value, i) => {
      const start = snow?.start + i * 24 * hour;
      const firstTemp = lodgeTemps.get(start);
      return `<div><span>${Number.isFinite(start) ? dayFormat.format(date(start)) : chartDays[i]}</span>
        <strong>${Number.isFinite(firstTemp) ? temperature(firstTemp) : '—'}</strong>
        <span>${Number.isFinite(value) ? units(value, 'cm') : '—'} snow</span></div>`;
    }).join(''));
    html('ifs-credit', ifs ? `${credit(ifs)} · 24 h blocks from ${time(snow?.start)} · Temperature at start.` : '');
    const short = hrdpsData?.lodge_snowfall_windows;
    html('hrdps-summary', `<strong>Canadian HRDPS Continental · Short range</strong> · ${sourceStatus(hrdps)}
      ${shortPoint ? `<br>Lodge ${temperature(shortTemp.value)}${shortTemp.at ? ` · valid ${time(shortTemp.at)}` : ''}
      · Wind ${units(shortWind.value, 'km/h')}${shortWind.at && shortWind.at !== shortTemp.at ? ` · valid ${time(shortWind.at)}` : ''}
      · Next 24 h snow ${units(short?.totals_cm[24], 'cm')}${Number.isFinite(short?.totals_cm[24]) ?
      ` · ends ${time(short.start + 24 * hour)}` : ''}` : ''}
      ${hrdps ? `<br>${credit(hrdps)}` : ''}`);
    const shortRows = shortPoint?.times.map((at, index) => at >= anchor
      ? `<tr><th scope="row">${time(at)}</th>
        <td>${temperature(shortPoint.values.temperature_2m[index])}</td>
        <td>${units(shortPoint.values.wind_speed_10m[index], 'km/h')}</td>
        <td>${units(shortPoint.values.snowfall[index], 'cm')}</td></tr>` : '').join('');
    html('hrdps-hourly', shortRows ? `<details class="tight"><summary>Canadian HRDPS · Hourly lodge forecast</summary>
      <table class="live-table"><thead><tr><th scope="col">Valid</th><th scope="col">Air</th>
      <th scope="col">Wind</th><th scope="col">Snow per hour</th></tr></thead><tbody>${shortRows}</tbody></table>
      <p class="smallnote">${credit(hrdps)} · Snow ends at the listed hour.</p></details>` :
      `<p class="smallnote">Canadian HRDPS hourly forecast · ${sourceStatus(hrdps)}</p>`);
    html('totals', [24, 48, 72].map(hours => box(`Next ${hours} h`, units(next?.[hours], 'cm'))).join(''));
    html('totals2', [
      box('Next 7 days', units(daily.every(Number.isFinite) ? sum(daily) : null, 'cm')),
      box('Peak 24 h / 72 h', units(peak?.cm, 'cm')),
      box('Reported 24 h', 'Unavailable'),
    ].join(''));
    text('timing', peak ? `Peak forecast valid ${time(peak.start)} – ${time(peak.end)}. Complete-hour totals start ${time(snow.start)}.`
      : 'Forecast timing unavailable.');
    html('powder-credit', ifs ? `${credit(ifs)} · ${sourceStatus(ifs)} · Adapted snowfall windows` : '');
    html('quality', row('Lodge temperature', temperature(temp.value)) + row('Lodge wind', units(wind.value, 'km/h')));
    html('dangerOverview', '<p class="warn">Avalanche ratings unavailable.</p>');
    text('nordictemp', 'Unavailable');
    renderFreezing(freezing, anchor);
    renderLiveInversion(ifs, hrdps, anchor);
  }

  function sourceDetails(weather, refresh) {
    html('live-sources', Object.entries(sourceNames).map(([key, name]) => {
      const source = weather?.sources[key];
      const data = source?.data;
      const coverage = data?.points?.lodge.coverage.temperature_2m ?? data?.coverage?.crossings;
      let valid = data?.valid_at ? time(data.valid_at) : '—';
      if (coverage?.first_valid_at) valid = `${time(coverage.first_valid_at)} – ${time(coverage.last_valid_at)}`;
      if (key === 'whitewater' || key === 'southridge') {
        return `<li><strong>${name}</strong><small>Unavailable · collection disabled pending permission</small>
          ${source ? link(source.link, 'Official source') : ''}</li>`;
      }
      const outcome = outcomes[refresh?.outcomes?.[key]];
      const provider = {blocked: 'Provider blocked', cooldown: 'Provider cooldown'}[source?.provider_state];
      return `<li><strong>${name}</strong><small>${sourceStatus(source)}${provider ? ` · ${provider}` : ''}</small>
        <small>Last checked ${time(source?.checked_at)}</small>
        <small>Last successful check ${time(source?.last_success_at)}</small>
        <small>Valid ${valid}</small>
        ${source?.next_attempt_at ? `<small>Next scheduled check ${time(source.next_attempt_at)}</small>` : ''}
        ${source?.last_error ? `<small>Last error · ${escape(source.last_error)}</small>` : ''}
        ${outcome ? `<small>Manual refresh · ${outcome}</small>` : ''}
        ${data?.attribution ? `<small>${escape(data.attribution)}</small>` : ''}
        ${source ? credit(source) : ''}</li>`;
    }).join(''));
  }

  const refreshButton = $('refresh-button');
  let weather, refresh, posting = false, timer, requestError = '', pollGeneration = 0;
  const busy = () => ['queued', 'running'].includes(refresh?.state);

  async function read(path) {
    const response = await fetch(path, {cache: 'no-store', signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error('Service unavailable');
    return response.json();
  }

  function showStatus() {
    const enabled = weather && Object.values(weather.sources).some(source => source.status !== 'disabled');
    refreshButton.disabled = !enabled || !refresh || posting || busy() || refresh.retry_in > 0;
    const products = Object.entries(sourceNames).slice(0, 4);
    text('live-summary', weather ? products.map(([key, name]) =>
      `${name} ${lower(sourceStatus(weather.sources[key]))}`).join(' · ') :
      'Weather service unavailable');
    const counts = Object.entries(refresh?.outcomes ?? {});
    const status = posting ? 'Requesting refresh…' : requestError || ({
      queued: 'Refresh queued.', running: 'Refreshing weather…',
      complete: 'Refresh finished.', failed: 'Refresh interrupted.',
    })[refresh?.state] || '';
    const details = counts.map(([key, outcome]) => `${sourceNames[key]} ${lower(outcomes[outcome])}`);
    // Keep countdown announcements out of the live region.
    refreshButton.textContent = refresh?.retry_in > 0 && !busy()
      ? `Refresh Data (${refresh.retry_in}s)` : 'Refresh Data';
    text('refresh-status', [status, ...details].filter(Boolean).join(' · '));
    sourceDetails(weather, refresh);
  }

  async function poll() {
    if (posting) return;
    const generation = ++pollGeneration;
    const [weatherResult, refreshResult] = await Promise.allSettled([read('/v1/weather'), read('/v1/refresh')]);
    if (generation !== pollGeneration) return;
    weather = weatherResult.status === 'fulfilled' ? weatherResult.value : null;
    refresh = refreshResult.status === 'fulfilled' ? refreshResult.value : null;
    if (busy()) {
      requestError = '';
    }
    renderWeather(weather);
    showStatus();
    timer = setTimeout(poll, busy() || refresh?.retry_in > 0 ? 1000 : 15000);
  }

  refreshButton.addEventListener('click', async () => {
    if (refreshButton.disabled) return;
    clearTimeout(timer);
    pollGeneration++;
    posting = true;
    requestError = '';
    showStatus();
    try {
      const response = await fetch('/v1/refresh', {
        method: 'POST', headers: {'X-Mountain-Refresh': '1'}, signal: AbortSignal.timeout(5000),
      });
      const body = await response.json();
      if (body.refresh) refresh = body.refresh;
      if (!response.ok && ![409, 429].includes(response.status)) throw new Error('Refresh unavailable');
    } catch {
      requestError = 'Could not request a refresh.';
    } finally {
      posting = false;
      showStatus();
      await poll();
    }
  });

  renderWeather(null);
  poll();
})();
