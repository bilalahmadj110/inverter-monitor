// Savings page: pulls /savings/data, renders KPIs + month detail + projection,
// edits tariff config, runs the AI Q&A box, and computes what-if bills.
// Single-file vanilla JS so it boots without a build step on the Pi.

(function () {
    'use strict';

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';

    // --- helpers ---------------------------------------------------------------
    const fmtPKR = (n) => {
        const v = Math.round(Number(n) || 0);
        return v.toLocaleString('en-PK');
    };
    const fmtKWh = (n) => Number(n || 0).toFixed(2);
    const fmtRate = (n) => Number(n || 0).toFixed(2);
    const $ = (id) => document.getElementById(id);

    async function getJSON(url) {
        const res = await fetch(url, { credentials: 'same-origin' });
        return res.json();
    }
    async function postJSON(url, body) {
        const res = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify(body || {}),
        });
        return { status: res.status, body: await res.json().catch(() => ({})) };
    }

    // --- main render -----------------------------------------------------------
    async function load() {
        let payload;
        try {
            payload = await getJSON('/savings/data');
        } catch (e) {
            console.error('failed to load /savings/data', e);
            return;
        }
        renderKPIs(payload);
        renderMonth(payload.month);
        renderProjection(payload.projection);
        renderPayback(payload.payback, payload.config);
        renderHistory(payload.lifetime?.months || []);
        fillConfigForm(payload.config);
        renderSlabsEditor(payload.config);
    }

    function renderKPIs(p) {
        const t = p.today || {};
        const m = p.month || {};
        const lt = p.lifetime || {};
        const pb = p.payback || {};

        $('kpi-today').textContent = fmtPKR(t.savings_pkr);
        $('kpi-today-kwh').textContent = fmtKWh(t.solar_kwh);
        $('kpi-today-rate').textContent = fmtRate(t.marginal_rate_pkr_per_kwh);

        $('kpi-month').textContent = fmtPKR(m.savings_pkr);
        $('kpi-lifetime').textContent = fmtPKR(lt.total_savings_pkr);
        $('kpi-lifetime-days').textContent = lt.days_elapsed ?? '—';
        $('kpi-lifetime-kwh').textContent = fmtKWh(lt.total_solar_kwh);

        if (pb.status === 'ok') {
            $('kpi-payback').textContent = `${pb.payback_months} mo`;
            $('kpi-payback-detail').textContent = `${pb.payback_years} yrs at Rs ${fmtPKR(pb.avg_daily_savings_pkr)}/day`;
        } else if (pb.status === 'set_install_cost') {
            $('kpi-payback').textContent = '—';
            $('kpi-payback-detail').textContent = 'Set install cost below';
        } else {
            $('kpi-payback').textContent = '—';
            $('kpi-payback-detail').textContent = 'Need savings data to estimate';
        }
    }

    function renderMonth(m) {
        if (!m) return;
        $('month-label').textContent = m.month;
        $('m-solar').textContent = fmtKWh(m.energy?.solar_kwh);
        $('m-grid').textContent = fmtKWh(m.energy?.grid_kwh);
        $('m-load').textContent = fmtKWh(m.energy?.load_kwh);
        $('m-bill-without').textContent = fmtPKR(m.bill_without_solar?.total);
        $('m-bill-with').textContent = fmtPKR(m.bill_with_solar?.total);
        $('m-saved').textContent = fmtPKR(m.savings_pkr);
        $('bill-breakdown').innerHTML = renderBillBreakdown(m.bill_with_solar);
    }

    function renderBillBreakdown(bill) {
        if (!bill) return '<div class="text-white/50">no data</div>';
        const lines = (bill.energy_lines || []).map(l => `
            <div class="row"><span class="k">${l.label} · ${l.units} kWh @ Rs ${l.rate}</span><span class="v">Rs ${fmtPKR(l.amount)}</span></div>
        `).join('');
        return `
            ${lines}
            <div class="row"><span class="k">FPA</span><span class="v">Rs ${fmtPKR(bill.fpa)}</span></div>
            <div class="row"><span class="k">Quarterly Adjustment</span><span class="v">Rs ${fmtPKR(bill.qta)}</span></div>
            <div class="row"><span class="k">FC Surcharge</span><span class="v">Rs ${fmtPKR(bill.fc_surcharge)}</span></div>
            <div class="row"><span class="k">NJ Surcharge</span><span class="v">Rs ${fmtPKR(bill.nj_surcharge)}</span></div>
            <div class="row"><span class="k">GST</span><span class="v">Rs ${fmtPKR(bill.gst)}</span></div>
            <div class="row"><span class="k">Electricity Duty</span><span class="v">Rs ${fmtPKR(bill.electricity_duty)}</span></div>
            <div class="row"><span class="k">Extra Tax</span><span class="v">Rs ${fmtPKR(bill.extra_tax)}</span></div>
            <div class="row"><span class="k">TV Fee</span><span class="v">Rs ${fmtPKR(bill.tv_fee)}</span></div>
            <div class="row"><span class="k font-semibold">Total</span><span class="v font-semibold">Rs ${fmtPKR(bill.total)}</span></div>
            <div class="row"><span class="k">Effective rate</span><span class="v">Rs ${fmtRate(bill.effective_rate_per_unit)} /kWh</span></div>
            ${bill.min_bill_applied ? '<div class="text-amber-300 text-xs mt-1">Minimum-bill floor applied.</div>' : ''}
        `;
    }

    function renderProjection(p) {
        if (!p) return;
        $('p-elapsed').textContent = p.days_elapsed;
        $('p-remaining').textContent = p.days_remaining;
        $('p-grid-now').textContent = fmtKWh(p.grid_kwh_so_far);
        $('p-daily-rate').textContent = fmtKWh(p.daily_grid_rate_kwh);
        $('p-grid-end').textContent = fmtKWh(p.projected_month_end_grid_kwh);
        $('p-bill').textContent = fmtPKR(p.projected_bill_total_pkr);

        const cur = p.current_slab || {};
        const proj = p.projected_slab || {};
        $('p-current-slab').textContent = cur.current_label
            ? `${cur.current_label} (Rs ${cur.current_rate}/kWh)` : '—';
        $('p-projected-slab').textContent = proj.current_label
            ? `${proj.current_label} (Rs ${proj.current_rate}/kWh)` : '—';

        const pill = $('proj-pill');
        const cliff = p.cliff_alert;
        if (cliff) {
            pill.className = 'pill warn';
            pill.innerHTML = `<i class="fas fa-triangle-exclamation"></i> Will cross slab`;
            $('cliff-alert').classList.remove('hidden');
            $('cliff-text').innerHTML = `
                You're at <b>${fmtKWh(p.grid_kwh_so_far)} kWh</b> grid usage this month
                (<b>${cliff.current_slab}</b>, Rs ${cur.current_rate}/kWh).
                At your current daily pace you'll cross into <b>${cliff.next_slab}</b> at
                Rs ${proj.current_rate}/kWh — a jump of <b>Rs ${cliff.rate_jump_pkr_per_kwh}/kWh</b>.
                Cut grid usage by <b>${fmtKWh(cliff.expected_overshoot_kwh)} kWh</b>
                over the next ${p.days_remaining} days to stay in the cheaper slab.
            `;
        } else {
            pill.className = 'pill ok';
            pill.innerHTML = `<i class="fas fa-check"></i> Stable`;
            $('cliff-alert').classList.add('hidden');
        }
    }

    function renderPayback(pb, cfg) {
        if (!pb) return;
        $('install-cost').value = cfg?.install_cost_pkr || '';
        $('system-start-date').value = cfg?.system_start_date || '';
        const out = $('payback-result');
        if (pb.status === 'ok') {
            out.innerHTML = `
                At Rs <b>${fmtPKR(pb.avg_daily_savings_pkr)}/day</b> in average savings,
                your <b>Rs ${fmtPKR(pb.install_cost_pkr)}</b> install pays back in
                <b>${pb.payback_months} months</b> (~${pb.payback_years} years).
            `;
        } else if (pb.status === 'set_install_cost') {
            out.innerHTML = `<span class="text-white/60">Enter your install cost above to see payback.</span>`;
        } else {
            out.innerHTML = `<span class="text-white/60">Not enough savings history yet — check back after a few days of data.</span>`;
        }
    }

    function renderHistory(months) {
        const tbody = $('month-history');
        if (!months.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="py-3 text-center text-white/50">No history yet.</td></tr>';
            return;
        }
        tbody.innerHTML = months.slice().reverse().map(m => `
            <tr class="border-b border-white/5">
                <td class="py-2">${m.month}</td>
                <td class="text-right py-2 text-yellow-200">${fmtKWh(m.solar_kwh)}</td>
                <td class="text-right py-2 text-blue-200">${fmtKWh(m.grid_kwh)}</td>
                <td class="text-right py-2 text-purple-200">${fmtKWh(m.load_kwh)}</td>
                <td class="text-right py-2 text-emerald-200">Rs ${fmtPKR(m.savings_pkr)}</td>
            </tr>
        `).join('');
    }

    // --- config form -----------------------------------------------------------
    function fillConfigForm(c) {
        if (!c) return;
        $('cfg-consumer-type').value = c.consumer_type || 'unprotected';
        $('cfg-sanctioned-load').value = c.sanctioned_load_kw ?? 3.3;
        $('cfg-fpa').value = c.fpa_per_unit ?? 0;
        $('cfg-qta').value = c.qtr_adjustment_per_unit ?? 0;
        $('cfg-fc').value = c.fc_surcharge_per_unit ?? 0;
        $('cfg-nj').value = c.nj_surcharge_per_unit ?? 0;
        $('cfg-gst').value = c.gst_percent ?? 0;
        $('cfg-ed').value = c.electricity_duty_percent ?? 0;
        $('cfg-extra-tax').value = c.extra_tax_percent ?? 0;
        $('cfg-tv').value = c.tv_fee_pkr ?? 0;
        $('cfg-min-below5').value = c.min_bill_below_5kw ?? 0;
        $('cfg-min-5plus').value = c.min_bill_5kw_or_above ?? 0;
    }

    function renderSlabsEditor(c) {
        if (!c) return;
        const renderSlabRows = (slabs, prefix) => slabs.map((s, i) => `
            <div class="slab-row" data-prefix="${prefix}" data-idx="${i}">
                <input type="text" data-field="label" value="${s.label || ''}" placeholder="label">
                <input type="number" data-field="up_to" value="${s.up_to ?? ''}" placeholder="up to (blank = ∞)">
                <input type="number" step="0.01" data-field="rate" value="${s.rate ?? ''}" placeholder="rate">
                <button class="del-slab text-red-300 hover:text-red-100 text-sm" title="remove"><i class="fas fa-trash"></i></button>
            </div>
        `).join('');

        $('protected-slabs').innerHTML = renderSlabRows(c.protected_slabs || [], 'p') +
            `<button id="add-protected-slab" class="text-blue-300 hover:text-blue-100 text-sm mt-1"><i class="fas fa-plus"></i> add slab</button>`;
        $('unprotected-slabs').innerHTML = renderSlabRows(c.unprotected_slabs || [], 'u') +
            `<button id="add-unprotected-slab" class="text-blue-300 hover:text-blue-100 text-sm mt-1"><i class="fas fa-plus"></i> add slab</button>`;

        $('add-protected-slab').onclick = () => addSlab('p');
        $('add-unprotected-slab').onclick = () => addSlab('u');
        document.querySelectorAll('.del-slab').forEach(b => {
            b.onclick = (ev) => ev.target.closest('.slab-row').remove();
        });
    }

    function addSlab(prefix) {
        const container = prefix === 'p' ? $('protected-slabs') : $('unprotected-slabs');
        const addBtn = container.querySelector('button');
        const row = document.createElement('div');
        row.className = 'slab-row';
        row.dataset.prefix = prefix;
        row.innerHTML = `
            <input type="text" data-field="label" value="new" placeholder="label">
            <input type="number" data-field="up_to" value="" placeholder="up to (blank = ∞)">
            <input type="number" step="0.01" data-field="rate" value="0" placeholder="rate">
            <button class="del-slab text-red-300 hover:text-red-100 text-sm"><i class="fas fa-trash"></i></button>
        `;
        container.insertBefore(row, addBtn);
        row.querySelector('.del-slab').onclick = (ev) => ev.target.closest('.slab-row').remove();
    }

    function readSlabs(prefix) {
        const rows = document.querySelectorAll(`.slab-row[data-prefix="${prefix}"]`);
        const slabs = [];
        rows.forEach(r => {
            const label = r.querySelector('[data-field="label"]').value.trim();
            const upToRaw = r.querySelector('[data-field="up_to"]').value.trim();
            const rate = parseFloat(r.querySelector('[data-field="rate"]').value);
            if (Number.isFinite(rate)) {
                slabs.push({
                    label: label || null,
                    up_to: upToRaw === '' ? null : Number(upToRaw),
                    rate: rate,
                });
            }
        });
        return slabs;
    }

    function readConfigForm() {
        return {
            consumer_type: $('cfg-consumer-type').value,
            sanctioned_load_kw: Number($('cfg-sanctioned-load').value) || 0,
            fpa_per_unit: Number($('cfg-fpa').value) || 0,
            qtr_adjustment_per_unit: Number($('cfg-qta').value) || 0,
            fc_surcharge_per_unit: Number($('cfg-fc').value) || 0,
            nj_surcharge_per_unit: Number($('cfg-nj').value) || 0,
            gst_percent: Number($('cfg-gst').value) || 0,
            electricity_duty_percent: Number($('cfg-ed').value) || 0,
            extra_tax_percent: Number($('cfg-extra-tax').value) || 0,
            tv_fee_pkr: Number($('cfg-tv').value) || 0,
            min_bill_below_5kw: Number($('cfg-min-below5').value) || 0,
            min_bill_5kw_or_above: Number($('cfg-min-5plus').value) || 0,
            protected_slabs: readSlabs('p'),
            unprotected_slabs: readSlabs('u'),
        };
    }

    function toast(msg, kind) {
        const el = $('config-toast');
        el.textContent = msg;
        el.className = 'ml-2 self-center text-sm ' + (kind === 'err' ? 'text-red-300' : 'text-emerald-300');
        setTimeout(() => { el.textContent = ''; el.className = 'ml-2 self-center text-sm'; }, 3000);
    }

    $('save-config').onclick = async () => {
        const cfg = readConfigForm();
        const { status, body } = await postJSON('/savings/config', cfg);
        if (status === 200 && body.success) {
            toast('Saved. Recalculating…', 'ok');
            await load();
        } else {
            toast(body.error || 'Save failed', 'err');
        }
    };

    $('reset-config').onclick = async () => {
        if (!confirm('Reset tariff config to LESCO defaults? Install cost and start date will be wiped too.')) return;
        const { status, body } = await postJSON('/savings/config/reset', {});
        if (status === 200) {
            toast('Reset.', 'ok');
            await load();
        } else {
            toast(body.error || 'Reset failed', 'err');
        }
    };

    $('save-payback').onclick = async () => {
        const patch = {
            install_cost_pkr: Number($('install-cost').value) || 0,
            system_start_date: $('system-start-date').value || null,
        };
        const { status, body } = await postJSON('/savings/config', patch);
        if (status === 200 && body.success) {
            await load();
        } else {
            alert(body.error || 'Save failed');
        }
    };

    // --- what-if calculator ----------------------------------------------------
    $('whatif-calc').onclick = async () => {
        const units = Number($('whatif-units').value) || 0;
        const { status, body } = await postJSON('/savings/preview', { units });
        if (status === 200) {
            $('whatif-result').innerHTML = `
                <div class="mb-2 text-white">For <b>${fmtKWh(body.units)} kWh</b>:</div>
                ${renderBillBreakdown(body)}
            `;
        } else {
            $('whatif-result').textContent = 'Calculation failed.';
        }
    };

    // --- AI Q&A ----------------------------------------------------------------
    async function checkAI() {
        const s = await getJSON('/ai/status');
        const pill = $('ai-status-pill');
        if (s.available) {
            pill.className = 'pill ok';
            pill.textContent = 'ready';
        } else if (!s.has_api_key) {
            pill.className = 'pill warn';
            pill.textContent = 'set OPENAI_API_KEY';
            $('ai-help').textContent = 'Set OPENAI_API_KEY in your .env to enable AI-powered Q&A.';
            $('ai-ask').disabled = true;
            $('ai-question').disabled = true;
        } else {
            pill.className = 'pill warn';
            pill.textContent = 'install openai SDK';
            $('ai-help').textContent = 'Run `pip install openai` and restart the app to enable Q&A.';
            $('ai-ask').disabled = true;
            $('ai-question').disabled = true;
        }
    }

    function appendMsg(text, kind) {
        const div = document.createElement('div');
        div.className = 'ai-msg ' + kind;
        div.textContent = text;
        $('ai-thread').appendChild(div);
        div.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }

    async function askAI() {
        const q = $('ai-question').value.trim();
        if (!q) return;
        $('ai-question').value = '';
        appendMsg(q, 'user');
        const thinking = document.createElement('div');
        thinking.className = 'ai-msg ai skeleton';
        thinking.textContent = 'Thinking…';
        $('ai-thread').appendChild(thinking);
        try {
            const { status, body } = await postJSON('/ai/ask', { question: q });
            thinking.remove();
            if (status === 200 && body.ok) {
                appendMsg(body.answer, 'ai');
                const u = body.usage || {};
                $('ai-meta').textContent = `model: ${body.model} · prompt ${u.prompt_tokens} (cached ${u.cached_tokens}) · completion ${u.completion_tokens} · total ${u.total_tokens}`;
            } else {
                appendMsg(body.error || 'Request failed.', 'ai');
            }
        } catch (e) {
            thinking.remove();
            appendMsg('Network error: ' + e.message, 'ai');
        }
    }

    $('ai-ask').onclick = askAI;
    $('ai-question').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); askAI(); }
    });

    // --- boot ------------------------------------------------------------------
    load();
    checkAI();
})();
