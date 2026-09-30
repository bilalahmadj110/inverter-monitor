/* FESCO Bill page — fetches /fesco/* and renders into the template's slots.

   No frameworks; vanilla DOM. CSRF token read from <meta name="csrf-token">.
   Handles: cycle picker, meter-reading editor, bootstrap form. */

(function () {
  'use strict';

  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const $ = (id) => document.getElementById(id);
  const fmtPkr = (n) => (n == null) ? '—' :
    new Intl.NumberFormat('en-PK', { maximumFractionDigits: 2 }).format(n);
  const fmtKwh = (n) => (n == null) ? '—' : Number(n).toFixed(0);
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const fmtDate = (iso) => {
    if (!iso) return '—';
    const [y, m, d] = iso.split('-');
    return `${d} ${MONTHS[parseInt(m, 10) - 1]} ${y}`;
  };

  async function fetchJSON(url, options = {}) {
    const opts = { credentials: 'same-origin', ...options };
    if (opts.method && opts.method !== 'GET') {
      opts.headers = { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken, ...(opts.headers || {}) };
    }
    const r = await fetch(url, opts);
    if (!r.ok) throw new Error(`${url} → ${r.status}`);
    return r.json();
  }

  // -------------------------- Bootstrap pane --------------------------

  function buildBootstrapRows() {
    const container = $('bootstrap-rows');
    container.innerHTML = '';
    lastNMonthLabels(12).forEach((label) => {
      const row = document.createElement('div');
      row.className = 'boot-row';
      row.innerHTML = `
        <input type="text" value="${label}" data-field="label" class="input sm" readonly>
        <input type="number" min="0" step="1" data-field="units" class="input sm num" placeholder="kWh">
        <input type="number" step="0.01" data-field="bill" class="input sm num" placeholder="PKR">
        <input type="number" step="0.01" data-field="paid" class="input sm num" placeholder="PKR">
      `;
      container.appendChild(row);
    });
  }

  function lastNMonthLabels(n) {
    const today = new Date();
    const labels = [];
    // Most-recent CLOSED cycle is the prior calendar month.
    let y = today.getFullYear();
    let m = today.getMonth();
    for (let i = 0; i < n; i++) {
      m = m - 1;
      if (m < 0) { m = 11; y -= 1; }
      labels.unshift(`${MONTHS[m]}${String(y).slice(-2)}`);
    }
    return labels;
  }

  async function submitBootstrap(ev) {
    ev.preventDefault();
    const rows = [];
    document.querySelectorAll('#bootstrap-rows > div').forEach((row) => {
      const label = row.querySelector('[data-field="label"]').value;
      const units = parseFloat(row.querySelector('[data-field="units"]').value);
      const bill = parseFloat(row.querySelector('[data-field="bill"]').value);
      const paid = parseFloat(row.querySelector('[data-field="paid"]').value);
      if (!isNaN(units)) {
        rows.push({
          cycle_label: label,
          units_actual: units,
          bill_amount_actual: isNaN(bill) ? null : bill,
          payment_amount: isNaN(paid) ? null : paid,
        });
      }
    });
    if (rows.length === 0) {
      alert('Enter at least one row.');
      return;
    }
    await fetchJSON('/fesco/bootstrap', { method: 'POST', body: JSON.stringify({ rows }) });
    location.reload();
  }

  // -------------------------- Bill rendering --------------------------

  const kv = (k, v) => `<div class="kv"><div class="k">${k}</div><div class="v">${v}</div></div>`;

  function renderHeader(payload) {
    const h = payload.header;
    $('header-strip').innerHTML = [
      kv('Consumer ID', h.consumer_id || '—'),
      kv('Tariff', h.tariff_code || '—'),
      kv('Sanctioned load', h.load_kw ? `${h.load_kw} kW` : '—'),
      kv('Meter', h.meter_no || '—'),
      kv('Reading date', fmtDate(h.reading_date)),
      kv('Due date', fmtDate(h.due_date)),
      `<div class="kv-note">Connected ${fmtDate(h.connection_date)} · ${h.discom_name || 'FESCO'}</div>`,
    ].join('');
  }

  function renderStatusBanner(payload) {
    const cycle = payload.cycle;
    const isOpen = cycle.status === 'open';
    const isActual = !isOpen && cycle.units_actual != null;
    const status = payload.status || {};
    const tone = isActual ? 'banner-ok' : 'banner-warn';
    const icon = isActual ? 'fa-check-circle' : 'fa-bolt';
    const badgeLabel = isActual ? 'Actual bill' : 'Estimated';
    let detail = '';
    if (isOpen && payload.forecast) {
      detail = `cycle in progress · day ${payload.forecast.days_elapsed} of ${payload.forecast.total_days}`;
      const lastYr = payload.forecast.same_month_last_year_units;
      if (lastYr != null) detail += ` · ${payload.forecast.same_month_last_year_label} last year: ${lastYr} units`;
    } else if (!isOpen && !isActual) {
      detail = 'awaiting the paper bill · record the meter units to lock it in';
    } else if (isActual) {
      detail = 'meter units recorded from the paper bill';
    }

    let statusLine = '';
    if (status.status) {
      const flip = status.flip_prediction;
      let flipText = '';
      if (flip && flip.flips_to) {
        flipText = ` · flips ${flip.flips_to} ${flip.at_cycle}${flip.condition ? ' (' + flip.condition + ')' : ''}`;
      }
      const t = status.status === 'protected' ? 'tone-ok' : 'tone-warn';
      statusLine = `<div class="banner-sub"><span class="${t}">Status: <b>${status.status.toUpperCase()}</b></span>${flipText}</div>`;
    }

    let calLine = '';
    const cal = payload.calibration || {};
    if (cal.factor != null) {
      const pct = ((cal.factor - 1) * 100).toFixed(1);
      const dir = cal.factor >= 1 ? 'more' : 'less';
      calLine = `<div class="banner-sub">Meter vs inverter: the bill shows <b>${Math.abs(pct)}% ${dir}</b> than the inverter's estimate (×${cal.factor}, ${cal.cycles.length} cycle${cal.cycles.length === 1 ? '' : 's'}).</div>`;
    } else if (!isOpen && !isActual) {
      calLine = `<div class="banner-sub">Record the units from the paper bill (pencil in the table below) to see how far the inverter's estimate sits from the meter.</div>`;
    }

    $('status-banner').className = `banner ${tone}`;
    $('status-banner').innerHTML = `
      <i class="fas ${icon} ${isOpen ? 'pulse-est' : ''}"></i>
      <div>
        <div class="banner-title">${badgeLabel} <span class="muted" style="font-weight:500">· ${detail}</span></div>
        ${statusLine}
        ${calLine}
      </div>
    `;
  }

  const row = (k, v) => `<div class="row"><span class="k">${k}</span><span class="v">${v}</span></div>`;

  function renderCharges(payload) {
    const b = payload.bill_breakdown;
    $('fesco-charges').innerHTML = [
      row(`Cost of electricity (${fmtKwh(b.units)} units)`, `Rs ${fmtPkr(b.energy_charge)}`),
      row('Fixed charges', `Rs ${fmtPkr(b.fix_charges)}`),
      row('FPA', `Rs ${fmtPkr(b.fpa)}`),
      row('FC surcharge', `Rs ${fmtPkr(b.fc_surcharge)}`),
      row('Quarterly tariff adjustment', `Rs ${fmtPkr(b.qta)}`),
    ].join('');
    $('govt-charges').innerHTML = [
      row('Electricity duty', `Rs ${fmtPkr(b.electricity_duty)}`),
      row('TV fee', `Rs ${fmtPkr(b.tv_fee)}`),
      row('GST', `Rs ${fmtPkr(b.gst)}`),
    ].join('');
  }

  function renderSlab(payload) {
    const b = payload.bill_breakdown;
    const lines = (b.energy_lines || []).map((l) =>
      `<div class="slab-line"><b>${fmtKwh(l.units)} units</b> × Rs ${l.rate} <span class="muted">(${l.label})</span> = <b>Rs ${fmtPkr(l.amount)}</b></div>`
    ).join('');
    let cliff = '';
    if (b.slab_info && b.slab_info.units_to_next_slab != null && b.slab_info.units_to_next_slab > 0) {
      cliff = `<div class="tone-warn" style="font-size:12.5px; margin-top:8px"><i class="fas fa-triangle-exclamation"></i> ${b.slab_info.units_to_next_slab.toFixed(0)} units to the next slab</div>`;
    }
    $('slab-breakdown').innerHTML = lines + cliff;
  }

  function renderPayable(payload) {
    const b = payload.bill_breakdown;
    const lp = payload.lp_surcharge || {};
    const h = payload.header;
    $('payable-block').innerHTML = `
      <div class="pay-main">
        <span class="pay-l">Payable within due date <b>${fmtDate(h.due_date)}</b></span>
        <span class="pay-v">Rs ${fmtPkr(b.total)}</span>
      </div>
      <div class="pay-sub"><span>L.P. surcharge after the due date (4%)</span><span>+ Rs ${fmtPkr(lp.phase_1_pkr)}</span></div>
      <div class="pay-sub"><span>L.P. surcharge after ${fmtDate(h.lp_phase_2_date)} (8%)</span><span>+ Rs ${fmtPkr(lp.phase_2_pkr)}</span></div>
    `;
  }

  function renderHistory(payload) {
    const tbody = $('history-body');
    tbody.innerHTML = (payload.history || []).map((r) => {
      const billCol = r.bill_amount != null && r.bill_amount < 0
        ? `<span class="tone-bad">${fmtPkr(r.bill_amount)} (refund)</span>`
        : fmtPkr(r.bill_amount);
      const meterCol = r.units_actual != null
        ? `<span>${fmtKwh(r.units_actual)}</span>`
        : `<span class="muted" title="not recorded yet">—</span>`;
      const estCol = r.units_estimated != null ? fmtKwh(r.units_estimated) : '<span class="muted">—</span>';
      return `<tr data-label="${r.label}">
        <td><b>${r.label}</b></td>
        <td class="num meter-cell">${meterCol}</td>
        <td class="num muted">${estCol}</td>
        <td class="num ${r.is_actual ? '' : 'muted'}">${billCol}</td>
        <td class="num muted">${fmtPkr(r.paid)}</td>
        <td class="num"><button type="button" class="record-actual icon-btn sm" title="Record the units and amount from the paper bill"><i class="fas fa-pencil"></i></button></td>
      </tr>`;
    }).join('');
    tbody.querySelectorAll('.record-actual').forEach((btn) => {
      btn.addEventListener('click', () => openActualEditor(btn.closest('tr')));
    });
    const cal = payload.calibration || {};
    const line = $('calibration-line');
    if (line) {
      line.textContent = cal.factor != null
        ? `Calibration ×${cal.factor} from ${cal.cycles.map((c) => `${c.label} ${c.actual}/${c.estimated}`).join(', ')}. Nothing applies this automatically; it shows how far the inverter-derived units sit from the meter.`
        : 'Meter = units printed on the FESCO bill; Inverter est. = grid kWh derived from the inverter\'s readings. Record a bill to compare them.';
    }
  }

  function openActualEditor(tr) {
    const label = tr.dataset.label;
    const rowData = (window.__billHistory || []).find((r) => r.label === label) || {};
    const cell = tr.querySelector('.meter-cell');
    const prev = cell.innerHTML;
    cell.innerHTML = `
      <div style="display:flex; flex-direction:column; align-items:flex-end; gap:6px">
        <input type="number" min="0" step="1" value="${rowData.units_actual ?? ''}" placeholder="units" data-f="units" class="input sm num" style="width:6.5rem">
        <input type="number" step="0.01" value="${rowData.is_actual && rowData.bill_amount != null ? rowData.bill_amount : ''}" placeholder="bill PKR" data-f="bill" class="input sm num" style="width:6.5rem">
        <div style="display:flex; gap:10px">
          <button type="button" data-act="save" class="link-btn">Save</button>
          <button type="button" data-act="clear" class="link-btn muted" title="Remove the recorded meter figure">Clear</button>
          <button type="button" data-act="cancel" class="link-btn muted">Cancel</button>
        </div>
      </div>`;
    cell.querySelector('[data-f="units"]').focus();
    cell.querySelector('[data-act="cancel"]').onclick = () => { cell.innerHTML = prev; };
    const submit = async (clear) => {
      const units = clear ? null : parseFloat(cell.querySelector('[data-f="units"]').value);
      const bill = clear ? null : parseFloat(cell.querySelector('[data-f="bill"]').value);
      if (!clear && !Number.isFinite(units)) { alert('Enter the units from the bill.'); return; }
      const body = { units_actual: units };
      if (clear || Number.isFinite(bill)) body.bill_amount_actual = clear ? null : bill;
      try {
        await fetchJSON(`/fesco/cycle/${encodeURIComponent(label)}/actual`, { method: 'POST', body: JSON.stringify(body) });
        location.reload();
      } catch (e) {
        alert(`Save failed: ${e.message}`);
      }
    };
    cell.querySelector('[data-act="save"]').onclick = () => submit(false);
    cell.querySelector('[data-act="clear"]').onclick = () => submit(true);
  }

  function populateCyclePicker(allCycles, currentLabel) {
    const sel = $('cycle-picker');
    sel.innerHTML = '';
    allCycles.forEach((c) => {
      const opt = document.createElement('option');
      opt.value = c.cycle_label;
      opt.textContent = `${c.cycle_label}${c.status === 'open' ? ' (open)' : ''}`;
      if (c.cycle_label === currentLabel) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.onchange = () => {
      const url = new URL(window.location.href);
      url.searchParams.set('cycle', sel.value);
      window.location.href = url.toString();
    };
  }

  // -------------------------- Init --------------------------

  async function init() {
    const params = new URLSearchParams(window.location.search);
    const requestedLabel = params.get('cycle');

    let cyclesResp;
    try {
      cyclesResp = await fetchJSON('/fesco/cycles');
    } catch (e) {
      console.error(e);
      return;
    }

    if (cyclesResp.cycles.length === 0) {
      $('bootstrap-pane').classList.remove('hidden');
      $('bill-pane').classList.add('hidden');
      $('cycle-picker').classList.add('hidden');
      buildBootstrapRows();
      $('bootstrap-form').addEventListener('submit', submitBootstrap);
      return;
    }

    $('bootstrap-pane').classList.add('hidden');
    $('bill-pane').classList.remove('hidden');

    const url = requestedLabel ? `/fesco/bill?cycle=${encodeURIComponent(requestedLabel)}` : '/fesco/bill';
    const billResp = await fetchJSON(url);

    $('bill-title').textContent = `FESCO Bill — ${billResp.cycle.cycle_label}`;
    $('bill-subtitle').textContent = `${fmtDate(billResp.cycle.start_date)} → ${fmtDate(billResp.cycle.end_date)}`;
    populateCyclePicker(cyclesResp.cycles, billResp.cycle.cycle_label);
    renderHeader(billResp);
    renderStatusBanner(billResp);
    renderCharges(billResp);
    renderSlab(billResp);
    renderPayable(billResp);
    window.__billHistory = billResp.history || [];
    renderHistory(billResp);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
