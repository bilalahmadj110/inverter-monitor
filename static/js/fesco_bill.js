/* FESCO Bill page — fetches /fesco/* and renders into the template's slots.

   No frameworks; vanilla DOM. CSRF token read from <meta name="csrf-token">.
   Reused for: cycle picker, edit modal, bootstrap form, banner dismissal. */

(function () {
  'use strict';

  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const $ = (id) => document.getElementById(id);
  const fmtPkr = (n) => (n == null) ? '—' :
    new Intl.NumberFormat('en-PK', { maximumFractionDigits: 2 }).format(n);
  const fmtKwh = (n) => (n == null) ? '—' : Number(n).toFixed(0);
  const fmtDate = (iso) => {
    if (!iso) return '—';
    const [y, m, d] = iso.split('-');
    return `${d} ${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][parseInt(m, 10) - 1]} ${y}`;
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
    const months = lastNMonthLabels(12);
    months.forEach((label) => {
      const row = document.createElement('div');
      row.className = 'grid grid-cols-12 gap-2';
      row.innerHTML = `
        <input type="text" value="${label}" data-field="label" class="col-span-3 bg-white/10 border border-white/20 text-white rounded px-2 py-1.5 text-sm" readonly>
        <input type="number" min="0" step="1" data-field="units" class="col-span-3 bg-white/10 border border-white/20 text-white rounded px-2 py-1.5 text-sm" placeholder="kWh">
        <input type="number" step="0.01" data-field="bill" class="col-span-3 bg-white/10 border border-white/20 text-white rounded px-2 py-1.5 text-sm" placeholder="PKR">
        <input type="number" step="0.01" data-field="paid" class="col-span-3 bg-white/10 border border-white/20 text-white rounded px-2 py-1.5 text-sm" placeholder="PKR">
      `;
      container.appendChild(row);
    });
  }

  function lastNMonthLabels(n) {
    const ABBR = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const today = new Date();
    const labels = [];
    // Most-recent CLOSED cycle is the prior calendar month.
    let y = today.getFullYear();
    let m = today.getMonth(); // 0-based; -1 = previous month
    for (let i = 0; i < n; i++) {
      m = m - 1;
      if (m < 0) { m = 11; y -= 1; }
      labels.unshift(`${ABBR[m]}${String(y).slice(-2)}`);
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
    await fetchJSON('/fesco/bootstrap', {
      method: 'POST',
      body: JSON.stringify({ rows }),
    });
    location.reload();
  }

  // -------------------------- Bill rendering --------------------------

  function renderHeader(payload) {
    const h = payload.header;
    $('header-strip').innerHTML = `
      <div><div class="text-white/50 text-xs">Consumer ID</div><div class="text-white">${h.consumer_id || '—'}</div></div>
      <div><div class="text-white/50 text-xs">Tariff</div><div class="text-white">${h.tariff_code || '—'}</div></div>
      <div><div class="text-white/50 text-xs">Load</div><div class="text-white">${h.load_kw || '—'} kW</div></div>
      <div><div class="text-white/50 text-xs">Meter</div><div class="text-white">${h.meter_no || '—'}</div></div>
      <div><div class="text-white/50 text-xs">Reading date</div><div class="text-white">${fmtDate(h.reading_date)}</div></div>
      <div><div class="text-white/50 text-xs">Due date</div><div class="text-white">${fmtDate(h.due_date)}</div></div>
      <div class="col-span-2 md:col-span-4 text-xs text-white/40">
        Connection: ${fmtDate(h.connection_date)} · ${h.discom_name || 'FESCO'}
      </div>
    `;
  }

  function renderStatusBanner(payload) {
    const cycle = payload.cycle;
    const isOpen = cycle.status === 'open';
    const isActual = !isOpen && cycle.units_actual != null;
    const status = payload.status || {};
    let badgeBg = isActual ? 'bg-emerald-500/20 border-emerald-500/40' : 'bg-amber-500/20 border-amber-500/40';
    let badgeIcon = isActual ? 'fa-check-circle text-emerald-300' : 'fa-bolt text-amber-300';
    let badgeLabel = isActual ? 'ACTUAL' : 'ESTIMATED';
    let detail = '';
    if (isOpen && payload.forecast) {
      detail = `cycle in progress · ${payload.forecast.days_elapsed} of ${payload.forecast.total_days} days elapsed`;
      const lastYr = payload.forecast.same_month_last_year_units;
      if (lastYr != null) {
        detail += ` · vs ${payload.forecast.same_month_last_year_label}: ${lastYr}`;
      }
    } else if (!isOpen && !isActual) {
      detail = 'awaiting bill — record actuals to lock in';
    }

    let statusLine = '';
    if (status.status) {
      const flip = status.flip_prediction;
      let flipText = '';
      if (flip && flip.flips_to) {
        flipText = ` · flips ${flip.flips_to} ${flip.at_cycle}${flip.condition ? ' (' + flip.condition + ')' : ''}`;
      }
      const tone = status.status === 'protected' ? 'text-emerald-300' : 'text-amber-300';
      statusLine = `<div class="text-xs ${tone} mt-1">Status: <strong>${status.status.toUpperCase()}</strong>${flipText}</div>`;
    }

    $('status-banner').className = `rounded-xl p-4 mb-4 border ${badgeBg}`;
    $('status-banner').innerHTML = `
      <div class="flex items-start gap-3">
        <i class="fas ${badgeIcon} mt-0.5 ${isOpen ? 'pulse-est' : ''}"></i>
        <div>
          <div class="text-white text-sm"><strong>${badgeLabel}</strong> · ${detail}</div>
          ${statusLine}
        </div>
      </div>
    `;
  }

  function renderCharges(payload) {
    const b = payload.bill_breakdown;
    const fesco = $('fesco-charges');
    fesco.innerHTML = `
      <div class="flex justify-between"><span class="text-white/70">Cost of electricity (${fmtKwh(b.units)} units)</span><span class="text-white">${fmtPkr(b.energy_charge)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">Fix charges</span><span class="text-white">${fmtPkr(b.fix_charges)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">FPA</span><span class="text-white">${fmtPkr(b.fpa)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">FC surcharge</span><span class="text-white">${fmtPkr(b.fc_surcharge)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">QTR tariff adj</span><span class="text-white">${fmtPkr(b.qta)}</span></div>
    `;
    const govt = $('govt-charges');
    govt.innerHTML = `
      <div class="flex justify-between"><span class="text-white/70">Electricity duty</span><span class="text-white">${fmtPkr(b.electricity_duty)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">TV fee</span><span class="text-white">${fmtPkr(b.tv_fee)}</span></div>
      <div class="flex justify-between"><span class="text-white/70">GST</span><span class="text-white">${fmtPkr(b.gst)}</span></div>
    `;
  }

  function renderSlab(payload) {
    const b = payload.bill_breakdown;
    const lines = (b.energy_lines || []).map((l) =>
      `<div class="text-white">${fmtKwh(l.units)} units × Rs ${l.rate} (${l.label}) = Rs ${fmtPkr(l.amount)}</div>`
    ).join('');
    let cliff = '';
    if (b.slab_info && b.slab_info.units_to_next_slab != null && b.slab_info.units_to_next_slab > 0) {
      cliff = `<div class="text-amber-300 text-xs mt-2">⚠ ${b.slab_info.units_to_next_slab.toFixed(0)} units to next slab cliff</div>`;
    }
    $('slab-breakdown').innerHTML = lines + cliff;
  }

  function renderPayable(payload) {
    const b = payload.bill_breakdown;
    const lp = payload.lp_surcharge || {};
    const h = payload.header;
    $('payable-block').innerHTML = `
      <div class="flex items-center justify-between text-lg">
        <span class="text-white/80">Payable within due date (${fmtDate(h.due_date)})</span>
        <span class="text-white font-bold">Rs ${fmtPkr(b.total)}</span>
      </div>
      <div class="flex items-center justify-between text-sm mt-1">
        <span class="text-white/50">L.P. surcharge after due date (4%)</span>
        <span class="text-white/70">+ Rs ${fmtPkr(lp.phase_1_pkr)}</span>
      </div>
      <div class="flex items-center justify-between text-sm">
        <span class="text-white/50">L.P. surcharge after ${fmtDate(h.lp_phase_2_date)} (8%)</span>
        <span class="text-white/70">+ Rs ${fmtPkr(lp.phase_2_pkr)}</span>
      </div>
    `;
  }

  function renderHistory(payload) {
    const tbody = $('history-body');
    const rows = (payload.history || []).map((row) => {
      const billCol = row.bill_amount != null && row.bill_amount < 0
        ? `<span class="text-rose-400">${fmtPkr(row.bill_amount)} (refund)</span>`
        : fmtPkr(row.bill_amount);
      const editPencil = row.is_actual
        ? `<button class="text-white/30 hover:text-white" data-edit-label="${row.label}"><i class="fas fa-pen"></i></button>`
        : `<button class="text-amber-300 hover:text-amber-100" data-edit-label="${row.label}" title="Awaiting actual"><i class="fas fa-pen-to-square"></i></button>`;
      return `<tr class="border-t border-white/5">
        <td class="py-1.5 text-white">${row.label}</td>
        <td class="py-1.5 text-right text-white">${fmtKwh(row.units)}</td>
        <td class="py-1.5 text-right text-white">${billCol}</td>
        <td class="py-1.5 text-right text-white/70">${fmtPkr(row.paid)}</td>
        <td class="py-1.5 text-right">${editPencil}</td>
      </tr>`;
    }).join('');
    tbody.innerHTML = rows;
    tbody.querySelectorAll('[data-edit-label]').forEach((btn) => {
      btn.addEventListener('click', () => openEditModal(btn.dataset.editLabel));
    });
  }

  function renderRecordActualBtn(payload) {
    const btn = $('record-actual-btn');
    if (payload.cycle.status === 'open') {
      btn.classList.remove('hidden');
      $('record-actual-label').textContent = payload.cycle.cycle_label;
      btn.onclick = () => openEditModal(payload.cycle.cycle_label);
    } else {
      btn.classList.add('hidden');
    }
  }

  function populateCyclePicker(allCycles, currentLabel) {
    const sel = $('cycle-picker');
    sel.innerHTML = '';
    allCycles.forEach((c) => {
      const opt = document.createElement('option');
      opt.value = c.cycle_label;
      const tag = c.status === 'open' ? ' (open)' : '';
      opt.textContent = `${c.cycle_label}${tag}`;
      if (c.cycle_label === currentLabel) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.onchange = () => {
      const next = sel.value;
      const url = new URL(window.location.href);
      url.searchParams.set('cycle', next);
      window.location.href = url.toString();
    };
  }

  // -------------------------- Edit modal --------------------------

  function openEditModal(label) {
    $('edit-modal').classList.remove('hidden');
    $('edit-label').value = label;
    fetchJSON(`/fesco/bill?cycle=${encodeURIComponent(label)}`).then((p) => {
      $('edit-reading-date').value = p.cycle.end_date || p.header.reading_date;
      $('edit-units').value = p.cycle.units_actual ?? '';
      $('edit-bill').value = p.cycle.bill_amount_actual ?? '';
      $('edit-paid').value = p.cycle.payment_amount ?? '';
      $('edit-fpa').value = p.cycle.fpa_per_unit_actual ?? '';
      $('edit-notes').value = p.cycle.notes ?? '';
    });
  }

  function closeEditModal() {
    $('edit-modal').classList.add('hidden');
  }

  async function submitEdit(ev) {
    ev.preventDefault();
    const label = $('edit-label').value;
    const reading = $('edit-reading-date').value;
    // We need start_date too; pull it from the existing cycle to preserve.
    const existing = await fetchJSON(`/fesco/bill?cycle=${encodeURIComponent(label)}`);
    const body = {
      cycle_label: label,
      start_date: existing.cycle.start_date,
      end_date: reading,
      status: 'closed',
      units_actual: parseInt($('edit-units').value, 10),
      bill_amount_actual: parseFloat($('edit-bill').value),
      payment_amount: $('edit-paid').value ? parseFloat($('edit-paid').value) : null,
      fpa_per_unit_actual: $('edit-fpa').value ? parseFloat($('edit-fpa').value) : null,
      notes: $('edit-notes').value || null,
    };
    await fetchJSON('/fesco/cycle', { method: 'POST', body: JSON.stringify(body) });
    closeEditModal();
    location.reload();
  }

  // -------------------------- Init --------------------------

  async function init() {
    const params = new URLSearchParams(window.location.search);
    const requestedLabel = params.get('cycle');

    let cyclesResp, billResp;
    try {
      cyclesResp = await fetchJSON('/fesco/cycles');
    } catch (e) {
      console.error(e);
      return;
    }

    if (cyclesResp.cycles.length === 0) {
      $('bootstrap-pane').classList.remove('hidden');
      $('bill-pane').classList.add('hidden');
      buildBootstrapRows();
      $('bootstrap-form').addEventListener('submit', submitBootstrap);
      return;
    }

    $('bootstrap-pane').classList.add('hidden');
    $('bill-pane').classList.remove('hidden');

    const url = requestedLabel ? `/fesco/bill?cycle=${encodeURIComponent(requestedLabel)}` : '/fesco/bill';
    billResp = await fetchJSON(url);

    $('bill-title').textContent = `FESCO Bill — ${billResp.cycle.cycle_label}`;
    $('bill-subtitle').textContent = `${fmtDate(billResp.cycle.start_date)} → ${fmtDate(billResp.cycle.end_date)}`;
    populateCyclePicker(cyclesResp.cycles, billResp.cycle.cycle_label);
    renderHeader(billResp);
    renderStatusBanner(billResp);
    renderCharges(billResp);
    renderSlab(billResp);
    renderPayable(billResp);
    renderHistory(billResp);
    renderRecordActualBtn(billResp);

    $('edit-close').addEventListener('click', closeEditModal);
    $('edit-form').addEventListener('submit', submitEdit);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
