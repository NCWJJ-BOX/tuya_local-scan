/**
 * Tuya Energy Dashboard — Frontend
 * Real-time energy monitoring with auto-polling
 */

// ───── DPS Mapping for energy monitoring plugs (category "cz") ─────
const DPS_MAP = {
    1:  'switch',        // Boolean: on/off
    9:  'countdown',     // Integer: seconds
    17: 'add_ele',       // Accumulated energy (scale varies)
    18: 'cur_current',   // Current in mA
    19: 'cur_power',     // Power in 0.1W
    20: 'cur_voltage',   // Voltage in 0.1V
    38: 'relay_status',  // Enum: memory/on/off
    39: 'light_mode',    // Enum: relay/pos/none
    40: 'child_lock',    // Boolean
};

// Scale factors for display
function parsePower(raw)   { return raw != null ? (raw / 10).toFixed(1) : null; }
function parseVoltage(raw) { return raw != null ? (raw / 10).toFixed(1) : null; }
function parseCurrent(raw) { return raw != null ? raw : null; }
function parseEnergy(raw)  { return raw != null ? (raw / 100).toFixed(2) : null; }

// ───── State ─────
let devices = [];
let socket = null;
let pollTimer = null;
let pollInterval = 5000;
// Sparkline history: deviceId -> array of {t, power}
const sparkData = {};
const SPARK_MAX = 30;

// ───── Init ─────
document.addEventListener('DOMContentLoaded', () => {
    initSocket();
    loadDevices();
    setPollInterval(pollInterval);
});

function initSocket() {
    socket = io();

    socket.on('connect', () => console.log('[WS] Connected'));

    socket.on('init_devices', (data) => {
        devices = data.devices || [];
        renderDevices();
    });

    socket.on('scan_started', () => {
        showStatus('Scanning local network...');
        document.getElementById('btn-scan').classList.add('loading');
    });

    socket.on('scan_complete', (data) => {
        hideStatus();
        document.getElementById('btn-scan').classList.remove('loading');
        devices = data.devices || [];
        renderDevices();
        showToast(`Found ${data.found} device(s)`, 'success');
    });

    socket.on('scan_error', (data) => {
        hideStatus();
        document.getElementById('btn-scan').classList.remove('loading');
        showToast(`Scan failed: ${data.error}`, 'error');
    });

    socket.on('device_updated', (dev) => {
        const idx = devices.findIndex(d => d.id === dev.id);
        if (idx >= 0) devices[idx] = dev;
        renderDevices();
    });

    socket.on('device_removed', (data) => {
        devices = devices.filter(d => d.id !== data.id);
        renderDevices();
    });

    socket.on('devices_imported', (data) => {
        devices = data.devices || [];
        renderDevices();
        showToast(`Imported ${data.imported} device(s)`, 'success');
    });

    socket.on('device_status', (data) => {
        const idx = devices.findIndex(d => d.id === data.id);
        if (idx >= 0) {
            if (data.success) {
                devices[idx].dps = data.dps || {};
                devices[idx].online = true;
                // Track sparkline data
                const power = parsePower(data.dps['19'] ?? data.dps[19]);
                if (power !== null) {
                    if (!sparkData[data.id]) sparkData[data.id] = [];
                    sparkData[data.id].push({ t: Date.now(), power: parseFloat(power) });
                    if (sparkData[data.id].length > SPARK_MAX) sparkData[data.id].shift();
                }
            } else {
                devices[idx].online = false;
            }
            updateDeviceCard(devices[idx]);
            updateSummary();
        }
    });

    socket.on('device_state_changed', (data) => {
        const dev = devices.find(d => d.id === data.id);
        if (dev && dev.local_key) {
            setTimeout(() => socket.emit('request_status', { id: data.id }), 500);
        }
    });
}

// ───── Polling ─────
function setPollInterval(ms) {
    pollInterval = parseInt(ms);
    if (pollTimer) clearInterval(pollTimer);
    const badge = document.getElementById('live-badge');
    if (pollInterval > 0) {
        pollTimer = setInterval(() => {
            socket.emit('request_all_status');
        }, pollInterval);
        badge.classList.remove('paused');
    } else {
        badge.classList.add('paused');
    }
}

// ───── API ─────
async function apiGet(url) { return (await fetch(url)).json(); }
async function apiPost(url, data = {}) { return (await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })).json(); }
async function apiPatch(url, data) { return (await fetch(url, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })).json(); }
async function apiDelete(url) { return (await fetch(url, { method: 'DELETE' })).json(); }

async function loadDevices() {
    try {
        const data = await apiGet('/api/devices');
        if (data.success) { devices = data.devices; renderDevices(); }
    } catch (e) { console.error('Failed to load devices:', e); }
}

async function startScan() { try { await apiPost('/api/scan'); } catch (e) { showToast('Scan failed', 'error'); } }

function refreshAllStatus() {
    const btn = document.getElementById('btn-refresh');
    btn.classList.add('loading');
    socket.emit('request_all_status');
    setTimeout(() => btn.classList.remove('loading'), 3000);
}

// ───── Render ─────
function renderDevices() {
    const grid = document.getElementById('devices-grid');
    const empty = document.getElementById('empty-state');

    if (devices.length === 0) {
        grid.classList.add('hidden');
        empty.classList.remove('hidden');
    } else {
        empty.classList.add('hidden');
        grid.classList.remove('hidden');
        grid.innerHTML = devices.map(d => buildEnergyCard(d)).join('');
        // Draw sparklines
        devices.forEach(d => drawSparkline(d.id));
    }
    updateSummary();
}

function updateDeviceCard(dev) {
    const card = document.getElementById(`card-${dev.id}`);
    if (card) {
        card.outerHTML = buildEnergyCard(dev);
        drawSparkline(dev.id);
    }
}

function buildEnergyCard(dev) {
    const dps = dev.dps || {};
    const hasKey = !!dev.local_key;
    const isOn = dps['1'] === true || dps[1] === true;
    const isOnline = dev.online;

    // Parse energy values
    const power   = parsePower(dps['19'] ?? dps[19]);
    const voltage = parseVoltage(dps['20'] ?? dps[20]);
    const current = parseCurrent(dps['18'] ?? dps[18]);
    const energy  = parseEnergy(dps['17'] ?? dps[17]);

    // Status badge
    let badge;
    if (!hasKey) badge = '<span class="device-badge badge-nokey"><span class="badge-dot"></span>No Key</span>';
    else if (isOnline) badge = '<span class="device-badge badge-online"><span class="badge-dot"></span>Online</span>';
    else badge = '<span class="device-badge badge-offline"><span class="badge-dot"></span>Offline</span>';

    // Power bar percentages (rough max values)
    const powerPct = power ? Math.min((parseFloat(power) / 3000) * 100, 100) : 0;
    const voltagePct = voltage ? Math.min((parseFloat(voltage) / 250) * 100, 100) : 0;
    const currentPct = current ? Math.min((current / 15000) * 100, 100) : 0;
    const energyPct = energy ? Math.min((parseFloat(energy) / 100) * 100, 100) : 0;

    const model = dev.model || dev.product_id || '';

    return `
    <div class="energy-card ${isOn ? 'is-on' : 'is-off'}" id="card-${dev.id}">
        <div class="energy-card-header">
            <div class="energy-card-info">
                <div class="energy-card-name">${escapeHtml(dev.name || 'Unknown')}</div>
                <div class="energy-card-meta">
                    ${badge}
                    <span class="energy-card-model">${escapeHtml(model)}</span>
                </div>
            </div>
            <button class="power-toggle ${isOn ? 'is-on' : ''}"
                    onclick="toggleDevice('${dev.id}')"
                    ${!hasKey ? 'disabled' : ''}
                    title="${isOn ? 'ON — Click to turn OFF' : 'OFF — Click to turn ON'}">
            </button>
        </div>

        <div class="energy-metrics">
            <div class="metric-box">
                <div class="metric-label" style="color:var(--power-color)">
                    <span class="metric-dot metric-dot-power"></span>POWER
                </div>
                <div class="metric-value power-val">
                    ${power !== null ? power : '—'}<span class="metric-unit">W</span>
                </div>
                <div class="power-bar-wrap"><div class="power-bar power-bar-power" style="width:${powerPct}%"></div></div>
            </div>
            <div class="metric-box">
                <div class="metric-label" style="color:var(--voltage-color)">
                    <span class="metric-dot metric-dot-voltage"></span>VOLTAGE
                </div>
                <div class="metric-value voltage-val">
                    ${voltage !== null ? voltage : '—'}<span class="metric-unit">V</span>
                </div>
                <div class="power-bar-wrap"><div class="power-bar power-bar-voltage" style="width:${voltagePct}%"></div></div>
            </div>
            <div class="metric-box">
                <div class="metric-label" style="color:var(--current-color)">
                    <span class="metric-dot metric-dot-current"></span>CURRENT
                </div>
                <div class="metric-value current-val">
                    ${current !== null ? current : '—'}<span class="metric-unit">mA</span>
                </div>
                <div class="power-bar-wrap"><div class="power-bar power-bar-current" style="width:${currentPct}%"></div></div>
            </div>
            <div class="metric-box">
                <div class="metric-label" style="color:var(--energy-color)">
                    <span class="metric-dot metric-dot-energy"></span>ENERGY
                </div>
                <div class="metric-value energy-val">
                    ${energy !== null ? energy : '—'}<span class="metric-unit">kWh</span>
                </div>
                <div class="power-bar-wrap"><div class="power-bar power-bar-energy" style="width:${energyPct}%"></div></div>
            </div>
        </div>

        <div class="sparkline-wrap">
            <canvas id="spark-${dev.id}" class="sparkline-canvas"></canvas>
        </div>

        <div class="energy-card-footer">
            <span class="energy-card-ip">${dev.ip || '—'} · v${dev.version}</span>
            <div class="energy-card-actions">
                <button class="action-btn" onclick="openDetailModal('${dev.id}')" title="Details">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
                    </svg>
                </button>
                <button class="action-btn" onclick="openEditModal('${dev.id}')" title="Edit">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                </button>
                <button class="action-btn" onclick="refreshDevice('${dev.id}')" title="Refresh">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"/>
                        <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
                    </svg>
                </button>
                <button class="action-btn action-delete" onclick="deleteDevice('${dev.id}')" title="Delete">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                    </svg>
                </button>
            </div>
        </div>
    </div>`;
}

// ───── Sparkline Drawing ─────
function drawSparkline(deviceId) {
    const canvas = document.getElementById(`spark-${deviceId}`);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const data = sparkData[deviceId] || [];

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const w = rect.width, h = rect.height;
    ctx.clearRect(0, 0, w, h);

    if (data.length < 2) {
        ctx.fillStyle = 'rgba(255,255,255,0.03)';
        ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = 'rgba(255,255,255,0.1)';
        ctx.font = '10px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('Collecting data...', w / 2, h / 2 + 3);
        return;
    }

    const values = data.map(d => d.power);
    const max = Math.max(...values, 1);
    const min = Math.min(...values, 0);
    const range = max - min || 1;
    const pad = 2;

    // Gradient fill
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, 'rgba(245, 158, 11, 0.15)');
    grad.addColorStop(1, 'rgba(245, 158, 11, 0)');

    ctx.beginPath();
    ctx.moveTo(0, h);
    for (let i = 0; i < values.length; i++) {
        const x = (i / (values.length - 1)) * w;
        const y = h - pad - ((values[i] - min) / range) * (h - pad * 2);
        if (i === 0) ctx.lineTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.lineTo(w, h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Line
    ctx.beginPath();
    for (let i = 0; i < values.length; i++) {
        const x = (i / (values.length - 1)) * w;
        const y = h - pad - ((values[i] - min) / range) * (h - pad * 2);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = 'rgba(245, 158, 11, 0.7)';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Latest dot
    const lastX = w;
    const lastY = h - pad - ((values[values.length - 1] - min) / range) * (h - pad * 2);
    ctx.beginPath();
    ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
    ctx.fillStyle = 'var(--power-color)';
    ctx.fill();
}

// ───── Summary ─────
function updateSummary() {
    let totalPower = 0, totalVoltage = 0, voltageCount = 0, totalEnergy = 0;
    let onlineCount = 0;

    devices.forEach(d => {
        if (d.online) onlineCount++;
        const dps = d.dps || {};
        const p = parsePower(dps['19'] ?? dps[19]);
        const v = parseVoltage(dps['20'] ?? dps[20]);
        const e = parseEnergy(dps['17'] ?? dps[17]);
        if (p !== null) totalPower += parseFloat(p);
        if (v !== null) { totalVoltage += parseFloat(v); voltageCount++; }
        if (e !== null) totalEnergy += parseFloat(e);
    });

    document.getElementById('total-power').textContent = totalPower.toFixed(1) + ' W';
    document.getElementById('avg-voltage').textContent = voltageCount > 0 ? (totalVoltage / voltageCount).toFixed(1) + ' V' : '— V';
    document.getElementById('total-energy').textContent = totalEnergy.toFixed(2) + ' kWh';
    document.getElementById('stat-online').textContent = onlineCount;
    document.getElementById('stat-total').textContent = devices.length;
}

// ───── Device Actions ─────
async function toggleDevice(deviceId) {
    const dev = devices.find(d => d.id === deviceId);
    if (!dev || !dev.local_key) { showToast('No local_key set', 'error'); return; }
    try {
        const result = await apiPost(`/api/control/${deviceId}/toggle`);
        if (result.success) showToast(`${dev.name}: ${result.action === 'on' ? 'ON' : 'OFF'}`, 'success');
        else showToast(`${dev.name}: ${result.error}`, 'error');
    } catch (e) { showToast(`Toggle failed`, 'error'); }
}

async function refreshDevice(deviceId) { socket.emit('request_status', { id: deviceId }); }

async function deleteDevice(deviceId) {
    const dev = devices.find(d => d.id === deviceId);
    if (!confirm(`Delete "${dev?.name || deviceId}"?`)) return;
    try { await apiDelete(`/api/devices/${deviceId}`); showToast('Removed', 'info'); }
    catch (e) { showToast('Delete failed', 'error'); }
}

// ───── Detail Modal ─────
function openDetailModal(deviceId) {
    const dev = devices.find(d => d.id === deviceId);
    if (!dev) return;
    document.getElementById('modal-title').textContent = dev.name;

    const dps = dev.dps || {};
    const power = parsePower(dps['19'] ?? dps[19]);
    const voltage = parseVoltage(dps['20'] ?? dps[20]);
    const current = parseCurrent(dps['18'] ?? dps[18]);
    const energy = parseEnergy(dps['17'] ?? dps[17]);
    const isOn = dps['1'] === true || dps[1] === true;

    let dpsRows = Object.entries(dps).map(([k, v]) => {
        const name = DPS_MAP[k] || `dps_${k}`;
        let display = v;
        if (typeof v === 'boolean') display = v ? '✅ ON' : '❌ OFF';
        return `<div class="detail-row"><span class="detail-key">${name} (DPS ${k})</span><span class="detail-val">${display}</span></div>`;
    }).join('') || '<p style="color:var(--text-muted);font-size:13px">No data — refresh first</p>';

    document.getElementById('modal-body').innerHTML = `
        <div class="detail-section">
            <div class="detail-section-title">Energy Readings</div>
            <div class="detail-row"><span class="detail-key">Power</span><span class="detail-val" style="color:var(--power-color)">${power ?? '—'} W</span></div>
            <div class="detail-row"><span class="detail-key">Voltage</span><span class="detail-val" style="color:var(--voltage-color)">${voltage ?? '—'} V</span></div>
            <div class="detail-row"><span class="detail-key">Current</span><span class="detail-val" style="color:var(--current-color)">${current ?? '—'} mA</span></div>
            <div class="detail-row"><span class="detail-key">Energy</span><span class="detail-val" style="color:var(--energy-color)">${energy ?? '—'} kWh</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">Device Info</div>
            <div class="detail-row"><span class="detail-key">Device ID</span><span class="detail-val">${dev.id}</span></div>
            <div class="detail-row"><span class="detail-key">IP Address</span><span class="detail-val">${dev.ip || '—'}</span></div>
            <div class="detail-row"><span class="detail-key">Protocol</span><span class="detail-val">v${dev.version}</span></div>
            <div class="detail-row"><span class="detail-key">Model</span><span class="detail-val">${dev.model || '—'}</span></div>
            <div class="detail-row"><span class="detail-key">MAC</span><span class="detail-val">${dev.mac || '—'}</span></div>
            <div class="detail-row"><span class="detail-key">Local Key</span><span class="detail-val">${dev.local_key ? dev.local_key.substring(0, 8) + '…' : '❌ Not set'}</span></div>
        </div>
        <div class="detail-section">
            <div class="detail-section-title">All DPS Values</div>
            ${dpsRows}
        </div>
        ${dev.local_key ? `
        <div class="detail-section">
            <div class="detail-section-title">Controls</div>
            <div class="detail-controls">
                <button class="btn btn-success btn-sm" onclick="quickControl('${dev.id}','on')">Turn ON</button>
                <button class="btn btn-danger btn-sm" onclick="quickControl('${dev.id}','off')">Turn OFF</button>
                <button class="btn btn-secondary btn-sm" onclick="refreshDevice('${dev.id}')">Refresh</button>
            </div>
        </div>` : ''}
    `;
    document.getElementById('device-modal').classList.remove('hidden');
}

function closeModal() { document.getElementById('device-modal').classList.add('hidden'); }

async function quickControl(deviceId, action) {
    try {
        const result = await apiPost(`/api/control/${deviceId}/${action}`);
        if (result.success) { showToast(`${action.toUpperCase()} OK`, 'success'); setTimeout(() => refreshDevice(deviceId), 500); }
        else showToast(result.error, 'error');
    } catch (e) { showToast(`Failed: ${e}`, 'error'); }
}

// ───── Edit Modal ─────
function openEditModal(deviceId) {
    const dev = devices.find(d => d.id === deviceId);
    if (!dev) return;
    document.getElementById('edit-id').value = dev.id;
    document.getElementById('edit-name').value = dev.name;
    document.getElementById('edit-type').value = dev.type;
    document.getElementById('edit-ip').value = dev.ip || '';
    document.getElementById('edit-key').value = dev.local_key || '';
    document.getElementById('edit-version').value = dev.version || '3.5';
    document.getElementById('edit-modal').classList.remove('hidden');
}

function closeEditModal() { document.getElementById('edit-modal').classList.add('hidden'); }

async function saveDeviceEdit(e) {
    e.preventDefault();
    const id = document.getElementById('edit-id').value;
    const data = {
        name: document.getElementById('edit-name').value,
        type: document.getElementById('edit-type').value,
        ip: document.getElementById('edit-ip').value,
        local_key: document.getElementById('edit-key').value,
        version: document.getElementById('edit-version').value
    };
    try {
        const result = await apiPatch(`/api/devices/${id}`, data);
        if (result.success) { showToast('Saved', 'success'); closeEditModal(); }
        else showToast(result.error, 'error');
    } catch (e) { showToast('Save failed', 'error'); }
}

// ───── Status / Toast ─────
function showStatus(text) { document.getElementById('status-text').textContent = text; document.getElementById('status-bar').classList.remove('hidden'); }
function hideStatus() { document.getElementById('status-bar').classList.add('hidden'); }

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = message;
    container.appendChild(toast);
    setTimeout(() => { toast.classList.add('toast-exit'); setTimeout(() => toast.remove(), 300); }, 3000);
}

function escapeHtml(str) { const d = document.createElement('div'); d.textContent = str; return d.innerHTML; }
