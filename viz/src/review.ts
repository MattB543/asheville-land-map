/**
 * Parcel review feed (review.html?city=<key>): two ranked lists of parcel cards built offline by
 * data/scripts/build_review_feed.py —
 *   - "Likely data issues": parcels whose record looks wrong or misleading, by review score;
 *   - "Biggest opportunities": Vacant / Underdeveloped / Parking Lot parcels, by land value.
 * The JSON is a small top-level data file (cities/<key>.json `reviewFilename`), fetched like the
 * other data files (API proxy on deployed hosts; local-first copy in viz/public/ under `npm run dev`).
 * Cards render in batches as you scroll, so a 300-item list stays fast.
 */
import { CITIES, formatCityLabel } from './cities';
import {
  LOCAL_REVIEW_PATH, PARKING_ENABLED, REVIEW_DATASET_URL, SELECTED_CITY, UNDERUTILIZED_ENABLED, resolveLocalFirst,
} from './config';

type TabKey = 'issues' | 'opportunities';

interface ReviewItem {
  rank: number;
  score?: number;
  parcel_id: string;
  category?: string;
  refined?: string;
  use_desc?: string;
  land: number;
  impr: number;
  total: number;
  land_psf?: number;
  nbr_psf?: number;
  psf_ratio?: number;
  z?: number;
  lot_sqft?: number;
  lot_acres?: number;
  impr_share?: number;
  signals: string[];
  reasons: string[];
  note?: string;
  link?: string;
  center: [number, number];
  outline?: number[][];
  estimated_land?: boolean;
  issue_score?: number;
  issue_signals?: string[];
  /** Opportunities: why the parcel is listed (vacant / underdeveloped / parking / token_building /
   *  storm_writedown). Token buildings and write-downs carry the 'underdeveloped' signal too. */
  opportunity_type?: string;
}

interface SignalMeta { label: string; description: string; count: number }

interface ReviewDoc {
  city: string;
  city_label?: string;
  generated: string;
  source?: string;
  n_parcels: number;
  units?: { currency?: string; area?: 'sqft' | 'm2' };
  remnants?: { hidden: boolean; count: number; note?: string };
  method?: { issues?: string; land_psf?: string; opportunities?: string; k?: number; z_flag?: number };
  signals: Record<string, SignalMeta>;
  city_medians?: { land_psf?: number; lot_sqft?: number; land?: number; total?: number; impr_share?: number };
  link_template?: string | null;
  issues: { flagged: number; items: ReviewItem[] };
  opportunities: { eligible: number; land_total?: number; land_median?: number; top_by_land?: number;
    token_buildings?: number; storm_writedowns?: number; items: ReviewItem[] };
}

const BATCH = 20;
const SQFT_PER_M2 = 10.763910417;
const SQFT_PER_ACRE = 43560;

/** Chip labels for the opportunity reasons (issue signals take theirs from the JSON). */
const OPP_LABELS: Record<string, string> = {
  vacant: 'Vacant',
  underdeveloped: 'Underdeveloped',
  parking: 'Surface parking',
  token_building: 'Token building',
  storm_writedown: 'Helene write-down',
  check_data: 'Check the data',
};
/** Opportunity types with their own chip (instead of the generic map class). */
const OPP_TYPES_WITH_CHIP = new Set(['token_building', 'storm_writedown']);

// ---- DOM ----
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const feedEl = $<HTMLDivElement>('feed');
const sentinelEl = $<HTMLDivElement>('sentinel');
const moreWrap = $<HTMLDivElement>('moreWrap');
const moreBtn = $<HTMLButtonElement>('moreBtn');
const emptyEl = $<HTMLDivElement>('empty');
const searchEl = $<HTMLInputElement>('fSearch');
const categoryEl = $<HTMLSelectElement>('fCategory');
const signalEl = $<HTMLSelectElement>('fSignal');
const signalLabelEl = $<HTMLSpanElement>('fSignalLabel');
const resetEl = $<HTMLButtonElement>('fReset');
const resultCountEl = $<HTMLSpanElement>('resultCount');
const explainerBody = $<HTMLDivElement>('explainerBody');
const tabButtons = Array.from(document.querySelectorAll<HTMLButtonElement>('.rv-tab'));

const cityKey = SELECTED_CITY;
const cityLabel = formatCityLabel(cityKey);
const appUrl = `/app.html?city=${encodeURIComponent(cityKey)}`;

// ---- state ----
let doc: ReviewDoc | null = null;
let tab: TabKey = new URL(location.href).searchParams.get('tab') === 'opportunities' ? 'opportunities' : 'issues';
let filtered: ReviewItem[] = [];
let shown = 0;
let cur = '$';
let metric = false;

// ---- formatting ----
const esc = (s: unknown): string =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

function money(v: number | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  const s = a >= 1e9 ? `${(a / 1e9).toFixed(1)}B` : a >= 1e6 ? `${(a / 1e6).toFixed(1)}M`
    : Math.round(a).toLocaleString('en-US');
  return `${v < 0 ? '-' : ''}${cur}${s}`;
}

function rate(psf: number | undefined): string {
  if (psf == null || !Number.isFinite(psf)) return '—';
  const v = metric ? psf * SQFT_PER_M2 : psf;
  if (v === 0) return `${cur}0`;
  const s = v >= 100 ? Math.round(v).toLocaleString('en-US') : v >= 0.1 ? v.toFixed(2) : v.toFixed(3);
  return `${cur}${s}`;
}
const rateUnit = () => (metric ? '/m²' : '/sqft');
/** "$/sqft" (or "€/m²") for labels. */
const perUnit = () => `${cur}${rateUnit()}`;

function area(sqft: number | undefined): string {
  if (sqft == null || !Number.isFinite(sqft)) return '—';
  if (metric) {
    const m2 = sqft / SQFT_PER_M2;
    return m2 >= 10000 ? `${(m2 / 10000).toFixed(2)} ha` : `${Math.round(m2).toLocaleString('en-US')} m²`;
  }
  return sqft >= SQFT_PER_ACRE ? `${(sqft / SQFT_PER_ACRE).toFixed(sqft >= 10 * SQFT_PER_ACRE ? 1 : 2)} acres`
    : `${Math.round(sqft).toLocaleString('en-US')} sqft`;
}

/** The lot size in the other unit, for the stat's sub-line. */
function areaAlt(sqft: number | undefined): string {
  if (sqft == null || !Number.isFinite(sqft)) return '';
  if (metric) return `${Math.round(sqft).toLocaleString('en-US')} sqft`;
  return sqft >= SQFT_PER_ACRE ? `${Math.round(sqft).toLocaleString('en-US')} sqft`
    : `${(sqft / SQFT_PER_ACRE).toFixed(3)} acres`;
}

const pct = (x: number | undefined) => (x == null || !Number.isFinite(x) ? '—' : `${Math.round(x * 100)}%`);

function times(r: number | undefined): string {
  if (r == null || !Number.isFinite(r) || r <= 0) return r === 0 ? '0×' : '';
  if (r >= 1) return r >= 10 ? `${Math.round(r).toLocaleString('en-US')}×` : `${r.toFixed(1)}×`;
  const inv = 1 / r;
  return `1/${inv >= 10 ? Math.round(inv).toLocaleString('en-US') : inv.toFixed(1)}`;
}

function span(m: number): string {
  if (metric) return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
  const ft = m * 3.28084;
  return ft >= 2640 ? `${(ft / 5280).toFixed(1)} mi` : `${Math.round(ft).toLocaleString('en-US')} ft`;
}

const normId = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');

// ---- thumbnails ----
function bbox(outline: number[][]): [number, number, number, number] | null {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  for (const ring of outline) {
    for (let i = 0; i + 1 < ring.length; i += 2) {
      const x = ring[i], y = ring[i + 1];
      if (x < minx) minx = x;
      if (x > maxx) maxx = x;
      if (y < miny) miny = y;
      if (y > maxy) maxy = y;
    }
  }
  return Number.isFinite(minx) ? [minx, miny, maxx, maxy] : null;
}

function thumbSvg(it: ReviewItem): { svg: string; caption: string } {
  const outline = it.outline ?? [];
  const bb = bbox(outline);
  if (!bb) return { svg: '', caption: '' };
  const [minx, miny, maxx, maxy] = bb;
  const w = maxx - minx, h = maxy - miny;
  const s = Math.max(w, h, 1e-6);
  const pad = s * 0.14;
  const vx = minx - (s - w) / 2 - pad, vy = -maxy - (s - h) / 2 - pad, vs = s + 2 * pad;
  const d = outline.map((ring) => {
    let p = '';
    for (let i = 0; i + 1 < ring.length; i += 2) p += `${i ? 'L' : 'M'}${ring[i]} ${-ring[i + 1]}`;
    return p + 'Z';
  }).join('');
  return {
    svg: `<svg viewBox="${vx} ${vy} ${vs} ${vs}" preserveAspectRatio="xMidYMid meet" aria-hidden="true">`
      + `<path class="rv-shape" d="${d}" fill-rule="evenodd" vector-effect="non-scaling-stroke"/></svg>`,
    caption: `↔ ${span(w)}`,
  };
}

// ---- links ----
function mapUrl(it: ReviewItem): string {
  const [lng, lat] = it.center;
  // Zoom 18 frames an ordinary lot; zoom out for big ones so the whole parcel (~360 px across) is in
  // view. MapLibre's 512 px tiles: metres per pixel = 78271.52 * cos(lat) / 2^z.
  const bb = it.outline ? bbox(it.outline) : null;
  const extent = bb ? Math.max(bb[2] - bb[0], bb[3] - bb[1]) : 0;
  let z = 18;
  if (extent > 0) {
    const fit = Math.log2((78271.52 * Math.cos((lat * Math.PI) / 180) * 360) / extent);
    z = Math.max(14, Math.min(18, Math.floor(fit * 2) / 2));
  }
  return `${appUrl}#map=${z}/${lat.toFixed(6)}/${lng.toFixed(6)}/0/0`;
}

function recordUrl(it: ReviewItem): string | null {
  if (it.link) return it.link;
  const t = doc?.link_template;
  return t ? t.replace('{parcel_id}', encodeURIComponent(it.parcel_id)) : null;
}

// ---- cards ----
const ICON_COPY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
const ICON_PIN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-7-6.1-7-11.5A7 7 0 0 1 19 9.5C19 14.9 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/></svg>';
const ICON_INFO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="9.5"/><line x1="12" y1="11" x2="12" y2="16.5"/><circle cx="12" cy="7.6" r="0.6" fill="currentColor"/></svg>';

function chipLabel(sig: string): string {
  return doc?.signals[sig]?.label ?? OPP_LABELS[sig] ?? sig;
}

function refinedTag(r: string | undefined): string {
  if (!r) return '';
  const cls = r === 'Parking Lot' ? 'Parking' : r;
  return `<span class="rv-tag rv-tag--${esc(cls)}">${esc(r)}</span>`;
}

function cardHtml(it: ReviewItem): string {
  const th = thumbSvg(it);
  const classBits = [it.category, it.use_desc && it.use_desc !== it.category ? it.use_desc : null]
    .filter(Boolean).map((s) => `<span>${esc(s)}</span>`).join('<span class="rv-sep">·</span>');
  const tags = refinedTag(it.refined) + (it.estimated_land ? '<span class="rv-tag rv-tag--est">Estimated land</span>' : '');

  const metricHtml = tab === 'issues'
    ? `<div class="rv-metric" title="Review score, 0-100: how extreme the signals are x how much value is at stake">
         <div class="rv-metric-val">${Math.round(it.score ?? 0)}</div>
         <div class="rv-metric-lbl">Review score</div>
         <div class="rv-meter"><i style="width:${Math.max(4, Math.min(100, it.score ?? 0))}%"></i></div>
       </div>`
    : `<div class="rv-metric">
         <div class="rv-metric-val">${money(it.land)}</div>
         <div class="rv-metric-lbl">Land value</div>
       </div>`;

  const oppType = tab === 'opportunities' && OPP_TYPES_WITH_CHIP.has(it.opportunity_type ?? '')
    ? it.opportunity_type! : null;
  const reasons = it.reasons.map((t, i) => {
    const sig = (i === 0 && oppType) || it.signals[i] || '';
    return `<li class="rv-reason"><span class="rv-chip sig-${esc(sig)}"><span class="rv-dot"></span>${esc(chipLabel(sig))}</span>`
      + `<span>${esc(t)}</span></li>`;
  }).join('');

  const share = it.impr_share;
  const ratio = it.psf_ratio;
  const ratioCls = ratio == null ? '' : ratio >= 2 ? 'rv-ratio--hi' : ratio <= 0.5 ? 'rv-ratio--lo' : '';
  const ratioHtml = ratio != null && Number.isFinite(ratio) && ratio > 0 && it.nbr_psf
    ? `<span class="rv-ratio ${ratioCls}" title="Land $/sqft vs the median of its nearest neighbours">${times(ratio)}</span>` : '';
  const landFlag = it.land <= 0 && it.impr > 0;
  const stats = `
    <dl class="rv-stats">
      <div class="rv-stat${landFlag ? ' rv-stat--flag' : ''}"><dt>Land</dt><dd>${money(it.land)}</dd>
        <small>${it.estimated_land ? 'our estimate' : share != null ? `${pct(1 - share)} of value` : '&nbsp;'}</small></div>
      <div class="rv-stat"><dt>Improvements</dt><dd>${money(it.impr)}</dd>
        <small>${share != null ? `${pct(share)} of value` : '&nbsp;'}</small></div>
      <div class="rv-stat"><dt>Total value</dt><dd>${money(it.total)}</dd><small>land + impr.</small></div>
      <div class="rv-stat"><dt>Land ${perUnit()}</dt><dd>${rate(it.land_psf)}${ratioHtml}</dd>
        <small>${it.nbr_psf != null ? `neighbours ${rate(it.nbr_psf)}` : '&nbsp;'}</small></div>
      <div class="rv-stat"><dt>Lot</dt><dd>${area(it.lot_sqft)}</dd><small>${areaAlt(it.lot_sqft) || '&nbsp;'}</small></div>
    </dl>`;

  const note = it.note ? `<div class="rv-note">${ICON_INFO}<span>${esc(it.note)}</span></div>` : '';
  const rec = recordUrl(it);
  const seeIssue = tab === 'opportunities' && it.issue_score != null
    ? `<button type="button" class="btn btn-ghost btn-sm" data-goto-issue="${esc(it.parcel_id)}">See the data issue</button>` : '';
  const actions = `
    <div class="rv-actions">
      <a class="btn btn-primary btn-sm" href="${esc(mapUrl(it))}" target="_blank" rel="noopener">${ICON_PIN}View on map</a>
      ${rec ? `<a class="btn btn-ghost btn-sm" href="${esc(rec)}" target="_blank" rel="noopener">Property record ↗</a>` : ''}
      ${seeIssue}
    </div>`;

  return `
  <article class="rv-card">
    <div class="rv-thumb-col">
      <div class="rv-thumb">${th.svg}<span class="rv-rank">#${it.rank}</span></div>
      ${th.caption ? `<div class="rv-thumb-cap">${esc(th.caption)}</div>` : ''}
    </div>
    <div class="rv-body">
      <div class="rv-head">
        <div class="rv-idline">
          <div class="rv-pid">${esc(it.parcel_id)}<button type="button" class="rv-copy" data-copy="${esc(it.parcel_id)}" title="Copy parcel ID" aria-label="Copy parcel ID ${esc(it.parcel_id)}">${ICON_COPY}</button></div>
          <div class="rv-class">${classBits}${tags}</div>
        </div>
        ${metricHtml}
      </div>
      <ul class="rv-reasons">${reasons}</ul>
      ${stats}
      ${note}
      ${actions}
    </div>
  </article>`;
}

// ---- filters / rendering ----
function items(): ReviewItem[] {
  return doc ? doc[tab].items : [];
}

function fillSelect(sel: HTMLSelectElement, allLabel: string, opts: [string, string, number][]): void {
  const prev = sel.value;
  sel.innerHTML = `<option value="">${esc(allLabel)}</option>`
    + opts.map(([v, l, n]) => `<option value="${esc(v)}">${esc(l)} (${n})</option>`).join('');
  sel.value = opts.some(([v]) => v === prev) ? prev : '';
}

function buildFilterOptions(): void {
  const list = items();
  const cats = new Map<string, number>();
  for (const it of list) cats.set(it.category ?? 'Uncategorized', (cats.get(it.category ?? 'Uncategorized') ?? 0) + 1);
  fillSelect(categoryEl, `All categories (${list.length})`,
    [...cats.entries()].sort((a, b) => b[1] - a[1]).map(([c, n]) => [c, c, n]));

  const sigs = new Map<string, number>();
  if (tab === 'issues') {
    signalLabelEl.textContent = 'Signal';
    for (const it of list) for (const s of it.signals) sigs.set(s, (sigs.get(s) ?? 0) + 1);
    fillSelect(signalEl, 'All signals', [...sigs.entries()].sort((a, b) => b[1] - a[1])
      .map(([s, n]) => [s, chipLabel(s), n]));
  } else {
    signalLabelEl.textContent = 'Type';
    for (const it of list) {
      if (it.refined) sigs.set(`refined:${it.refined}`, (sigs.get(`refined:${it.refined}`) ?? 0) + 1);
      if (OPP_TYPES_WITH_CHIP.has(it.opportunity_type ?? ''))
        sigs.set(`type:${it.opportunity_type}`, (sigs.get(`type:${it.opportunity_type}`) ?? 0) + 1);
      if (it.issue_score != null) sigs.set('flagged', (sigs.get('flagged') ?? 0) + 1);
    }
    const oppLabel = (k: string) => k === 'flagged' ? 'Also a likely data issue'
      : k.startsWith('type:') ? OPP_LABELS[k.slice(5)] ?? k.slice(5) : k.slice(8);
    fillSelect(signalEl, 'All', [...sigs.entries()]
      .map(([k, n]): [string, string, number] => [k, oppLabel(k), n])
      .sort((a, b) => (a[0] === 'flagged' ? 1 : b[0] === 'flagged' ? -1 : b[2] - a[2])));
  }
}

function applyFilters(): void {
  const q = normId(searchEl.value);
  const cat = categoryEl.value;
  const sig = signalEl.value;
  filtered = items().filter((it) => {
    if (q && !normId(it.parcel_id).includes(q)) return false;
    if (cat && (it.category ?? 'Uncategorized') !== cat) return false;
    if (sig) {
      if (tab === 'issues') return it.signals.includes(sig);
      if (sig === 'flagged') return it.issue_score != null;
      if (sig.startsWith('type:')) return it.opportunity_type === sig.slice(5);
      return `refined:${it.refined}` === sig;
    }
    return true;
  });
  resetEl.hidden = !(q || cat || sig);
  shown = 0;
  feedEl.innerHTML = '';
  if (!filtered.length) {
    feedEl.innerHTML = `<div class="rv-empty"><h2>No parcels match</h2><p>Nothing on this list matches these filters.</p>`
      + `<button type="button" class="btn btn-ghost" data-reset>Clear filters</button></div>`;
  }
  renderMore();
}

function renderMore(): void {
  const next = filtered.slice(shown, shown + BATCH);
  if (next.length) feedEl.insertAdjacentHTML('beforeend', next.map(cardHtml).join(''));
  shown += next.length;
  moreWrap.hidden = shown >= filtered.length;
  if (next.length && shown < filtered.length) {
    io.unobserve(sentinelEl);
    io.observe(sentinelEl);
  }
  const total = items().length;
  resultCountEl.innerHTML = filtered.length === total
    ? `<strong>${total}</strong> parcels`
    : `<strong>${filtered.length}</strong> of ${total} parcels`;
}

// ---- explainer ----
function explainerHtml(): string {
  if (!doc) return '';
  const med = doc.city_medians ?? {};
  const context = med.land_psf != null
    ? `<p class="rv-fine">Citywide, the median parcel's land is ${rate(med.land_psf)}${rateUnit()}, on a ${area(med.lot_sqft)} lot.</p>` : '';
  const remnants = doc.remnants?.hidden && doc.remnants.count
    ? `<p class="rv-fine">${doc.remnants.count} sliver remnants (under 500 sqft) are hidden on this city's map, so they are left out here too.</p>` : '';
  if (tab === 'issues') {
    const sigs = Object.entries(doc.signals).filter(([, m]) => m.count > 0)
      .map(([k, m]) => `<li class="sig-${esc(k)}"><span class="rv-dot"></span><span><b>${esc(m.label)}.</b> ${esc(m.description)}</span>`
        + `<span class="rv-li-count">${m.count.toLocaleString('en-US')}</span></li>`).join('');
    return `
      <p>Every parcel is checked for signs that its record is wrong or would mislead on the map. Each warning
        signal gets a <b>severity</b> and the <b>dollars at stake</b>. The review score (0&ndash;100) combines them,
        so parcels that are both extreme and valuable come first. A $300k sliver outranks a $5k oddity.</p>
      <p>Land ${perUnit()} is compared with the ${doc.method?.k ?? 15} nearest parcels, with nearby parcels of the same
        broad use, and after allowing for lot size. A parcel is flagged only if it is out of line on all three.</p>
      <ul>${sigs}</ul>
      <p class="rv-fine">Counts are parcels flagged citywide; the list shows the ${doc.issues.items.length} highest scores
        of ${doc.issues.flagged.toLocaleString('en-US')}. A flag is a prompt to check the record, not proof of an error.</p>
      ${context}${remnants}`;
  }
  const lt = doc.opportunities.land_total;
  const o = doc.opportunities;
  const extras = [
    o.token_buildings ? `<b>${o.token_buildings}</b> <span class="rv-chip sig-token_building"><span class="rv-dot"></span>token buildings</span>, where the county values a standing building at next to nothing and puts the value on the land` : '',
    o.storm_writedowns ? `<b>${o.storm_writedowns}</b> <span class="rv-chip sig-storm_writedown"><span class="rv-dot"></span>Helene write-downs</span>, where a building's value was written off after Hurricane Helene` : '',
  ].filter(Boolean);
  return `
    <p>Parcels the map classes as <b>Vacant</b>, <b>Underdeveloped</b> (buildings worth little next to the land), or
      surface <b>Parking Lot</b>, with the <b>largest land value first</b>.</p>
    <p>${o.eligible.toLocaleString('en-US')} parcels qualify${lt ? `, holding ${money(lt)} of land` : ''};
      the list shows the top ${o.top_by_land ?? o.items.length} by land value${extras.length ? `, plus ${extras.join(', and ')}` : ''}.</p>
    <p class="rv-fine">Parcels that are also on the data-issues list are marked <span class="rv-chip sig-check_data"><span class="rv-dot"></span>Check the data</span>.
      A bad record can make a parcel look underused.</p>
    ${context}${remnants}`;
}

// ---- tabs ----
function setTab(next: TabKey, opts: { keepSearch?: boolean } = {}): void {
  tab = next;
  for (const b of tabButtons) {
    const on = b.dataset.tab === tab;
    b.classList.toggle('is-active', on);
    b.setAttribute('aria-selected', String(on));
  }
  feedEl.setAttribute('aria-labelledby', `tab-${tab}`);
  const u = new URL(location.href);
  if (tab === 'issues') u.searchParams.delete('tab');
  else u.searchParams.set('tab', tab);
  history.replaceState(null, '', u.toString());
  if (!opts.keepSearch) searchEl.value = '';
  categoryEl.value = '';
  signalEl.value = '';
  explainerBody.innerHTML = explainerHtml();
  buildFilterOptions();
  applyFilters();
}

// ---- states ----
function showEmpty(title: string, text: string, lede: string,
  action?: { label: string; href?: string; reload?: boolean }): void {
  document.body.classList.add('rv-no-feed');
  feedEl.innerHTML = '';
  moreWrap.hidden = true;
  emptyEl.hidden = false;
  $('emptyTitle').textContent = title;
  $('emptyText').textContent = text;
  const a = $<HTMLAnchorElement>('emptyAction');
  a.textContent = action?.label ?? 'Back to the map';
  a.href = action?.href ?? appUrl;
  if (action?.reload) a.addEventListener('click', (e) => { e.preventDefault(); location.reload(); });
  $('lede').textContent = lede;
  explainerBody.innerHTML = '<p>The review feed ranks parcels whose records look wrong or misleading, and the biggest '
    + 'vacant or underused ones. It is built offline for each city.</p>';
}

// ---- boot ----
async function init(): Promise<void> {
  $('cityLabel').textContent = cityLabel;
  // On a phone the method note would push the first card a screen down: start it collapsed.
  if (window.matchMedia('(max-width: 900px)').matches) $<HTMLDetailsElement>('explainer').open = false;
  document.title = `Parcel review · ${cityLabel} | AVL GO`;
  $<HTMLAnchorElement>('backToMap').href = appUrl;
  // Header nav: Value / Underused / Parking open the map on that view, for this city.
  const viewOn: Record<string, boolean> = { land: true, underutilized: UNDERUTILIZED_ENABLED, parking: PARKING_ENABLED };
  for (const a of document.querySelectorAll<HTMLAnchorElement>('a[data-app-view]')) {
    const view = a.dataset.appView ?? 'land';
    a.href = view === 'land' ? appUrl : `${appUrl}&view=${encodeURIComponent(view)}`;
    a.hidden = !viewOn[view];
  }

  const city = CITIES[cityKey];
  cur = city?.currencySymbol ?? '$';
  metric = city?.unitSystem === 'metric';

  if (!REVIEW_DATASET_URL) {
    showEmpty('No review feed for this city yet',
      `${cityLabel}'s parcels haven't been scored for review yet. The map itself is unaffected.`,
      'No review feed is available for this city yet.');
    return;
  }
  try {
    const url = await resolveLocalFirst(LOCAL_REVIEW_PATH, REVIEW_DATASET_URL);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    doc = (await res.json()) as ReviewDoc;
  } catch (err) {
    console.error('[Review] Could not load the review feed:', err);
    showEmpty("Couldn't load the review feed",
      `The review feed for ${cityLabel} didn't load (${(err as Error).message}). Try again in a moment.`,
      'The review feed could not be loaded.', { label: 'Try again', href: location.href, reload: true });
    return;
  }

  if (doc.units?.currency) cur = doc.units.currency;
  if (doc.units?.area) metric = doc.units.area === 'm2';
  $('count-issues').textContent = `top ${doc.issues.items.length} of ${doc.issues.flagged.toLocaleString('en-US')} flagged`;
  $('count-opportunities').textContent = `top ${doc.opportunities.items.length} by land value`;
  const gen = new Date(doc.generated);
  const genTxt = Number.isNaN(gen.getTime()) ? doc.generated
    : gen.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  $('lede').innerHTML = `Parcels worth a second look, out of <strong>${doc.n_parcels.toLocaleString('en-US')}</strong>`
    + ` on the map. Updated ${esc(genTxt)}.`;
  setTab(tab, { keepSearch: true });
}

// ---- events ----
for (const b of tabButtons) {
  b.addEventListener('click', () => {
    const next = b.dataset.tab as TabKey;
    if (doc && next !== tab) setTab(next);
  });
}
searchEl.addEventListener('input', () => doc && applyFilters());
categoryEl.addEventListener('change', () => doc && applyFilters());
signalEl.addEventListener('change', () => doc && applyFilters());
const resetFilters = () => {
  searchEl.value = '';
  categoryEl.value = '';
  signalEl.value = '';
  applyFilters();
};
resetEl.addEventListener('click', resetFilters);
moreBtn.addEventListener('click', renderMore);

feedEl.addEventListener('click', (e) => {
  const t = e.target as HTMLElement;
  const copy = t.closest<HTMLButtonElement>('[data-copy]');
  if (copy) {
    void navigator.clipboard?.writeText(copy.dataset.copy ?? '').then(() => {
      copy.classList.add('is-done');
      setTimeout(() => copy.classList.remove('is-done'), 1200);
    }).catch(() => { /* clipboard blocked: nothing to do */ });
    return;
  }
  const goto = t.closest<HTMLButtonElement>('[data-goto-issue]');
  if (goto) {
    setTab('issues');
    searchEl.value = goto.dataset.gotoIssue ?? '';
    applyFilters();
    window.scrollTo({ top: 0, behavior: 'smooth' });
    return;
  }
  if (t.closest('[data-reset]')) resetFilters();
});

// Load the next batch shortly before the end of the list comes into view. renderMore() re-observes
// the sentinel, so a batch that still leaves it in range triggers the next one.
const io = new IntersectionObserver((entries) => {
  if (entries.some((e) => e.isIntersecting) && doc && shown < filtered.length) renderMore();
}, { rootMargin: '800px 0px' });
io.observe(sentinelEl);

void init();
