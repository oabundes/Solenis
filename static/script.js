const API_URL = '/api/data';
let phChart = null;
let currentData = [];

// Etiquetas y colores por evento (ahora en TEXTO)
const EVENTO_LABELS = {
    'DESCARGA': 'Descarga',
    'INICIA':   'Inicia',
    'TERMINA':  'Termina'
};

const EVENTO_COLORS = {
    'DESCARGA': { bg: 'rgba(0,200,149,0.12)',   text: '#007a5a', border: '#00C895' },
    'INICIA':   { bg: 'rgba(59,130,246,0.12)',  text: '#1d4ed8', border: '#3b82f6' },
    'TERMINA':  { bg: 'rgba(245,158,11,0.12)',  text: '#92400e', border: '#f59e0b' }
};

// ─────────────────────────────────────────────
// Inicialización
// ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const today = new Date();
    const lastWeek = new Date();
    lastWeek.setDate(today.getDate() - 7);
    document.getElementById('endDate').value   = today.toISOString().split('T')[0];
    document.getElementById('startDate').value = lastWeek.toISOString().split('T')[0];

    document.getElementById('filterBtn').addEventListener('click', fetchData);
    document.getElementById('exportBtn').addEventListener('click', exportToCSV);
    document.getElementById('refreshBtn').addEventListener('click', fetchData);

    document.getElementById('startDate').addEventListener('change', validateDateRange);
    document.getElementById('endDate').addEventListener('change', validateDateRange);

    fetchData();
});

// ─────────────────────────────────────────────
// Validación de rango
// ─────────────────────────────────────────────
function validateDateRange() {
    const start = document.getElementById('startDate').value;
    const end   = document.getElementById('endDate').value;
    const alert = document.getElementById('rangeAlert');
    const btn   = document.getElementById('filterBtn');

    if (start && end) {
        const diff = (new Date(end) - new Date(start)) / (1000 * 60 * 60 * 24);
        if (diff > 62) {
            alert.classList.remove('hidden');
            btn.disabled = true;
            return false;
        }
        if (diff < 0) {
            alert.textContent = '⚠️ La fecha final no puede ser anterior a la inicial.';
            alert.classList.remove('hidden');
            btn.disabled = true;
            return false;
        }
    }
    alert.textContent = '⚠️ El rango no puede superar 2 meses.';
    alert.classList.add('hidden');
    btn.disabled = false;
    return true;
}

// ─────────────────────────────────────────────
// Obtener eventos seleccionados — ahora retorna TEXTO
// ─────────────────────────────────────────────
function getSelectedEventos() {
    const checked = document.querySelectorAll('input[name="evento"]:checked');
    return Array.from(checked).map(cb => cb.value); // "DESCARGA", "INICIA", "TERMINA"
}

// ─────────────────────────────────────────────
// Fetch de datos
// ─────────────────────────────────────────────
async function fetchData() {
    if (!validateDateRange()) return;

    const selectedEventos = getSelectedEventos();
    const eventoAlert = document.getElementById('eventoAlert');
    eventoAlert.classList.add('hidden');

    const startDate = document.getElementById('startDate').value;
    const endDate   = document.getElementById('endDate').value;
    const btn = document.getElementById('filterBtn');
    btn.innerHTML = '<span class="spinner"></span> Cargando...';
    btn.disabled = true;

    try {
        const params = new URLSearchParams();
        if (startDate) params.append('start_date', startDate);
        if (endDate)   params.append('end_date', endDate);
        // Solo agregar filtro de evento si hay algo seleccionado
        if (selectedEventos.length > 0) {
            selectedEventos.forEach(ev => params.append('evento', ev));
        } // envía "DESCARGA", "INICIA", "TERMINA"

        let usedSimulated = false;
        try {
            const response = await fetch(`${API_URL}?${params.toString()}`);
            if (!response.ok) {
                const errText = await response.text();
                let errMsg = `Error del servidor (${response.status})`;
                try {
                    const errJson = JSON.parse(errText);
                    errMsg = errJson.detail || errMsg;
                } catch (_) {}
                throw new Error(errMsg);
            }
            currentData = JSON.parse(await response.text());
        } catch (fetchErr) {
            if (fetchErr.message.startsWith('Error del servidor') || fetchErr.message === 'Failed to fetch') {
                showError(fetchErr.message === 'Failed to fetch'
                    ? 'No se pudo conectar al servidor. Verifica tu conexión.'
                    : fetchErr.message);
                return;
            }
            // Otro error inesperado
            showError(`Error inesperado: ${fetchErr.message}`);
            return;
        }

        const banner = document.getElementById('simulatedBanner');
        banner.classList.add('hidden');

        updateTable(currentData);
        updateChart(currentData);
        updateResultsHeader(currentData, startDate, endDate);
        document.getElementById('chartTooltipData').classList.add('hidden');

    } catch (error) {
        console.error('Error:', error);
        showError(error.message);
    } finally {
        btn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"/>
            </svg>
            Consultar`;
        btn.disabled = false;
    }
}

// ─────────────────────────────────────────────
// Header de resultados
// ─────────────────────────────────────────────
function updateResultsHeader(data, start, end) {
    const header = document.getElementById('resultsHeader');
    const count  = document.getElementById('resultCount');
    const range  = document.getElementById('resultRange');

    header.style.display = 'flex';
    count.textContent = `${data.length} registro${data.length !== 1 ? 's' : ''}`;

    if (start && end) {
        const s = new Date(start).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
        const e = new Date(end).toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
        range.textContent = `${s} → ${e}`;
    }
}

// ─────────────────────────────────────────────
// Generar datos simulados (evento como texto)
// ─────────────────────────────────────────────
function generateSimulatedData(startDate, endDate, selectedEventos) {
    const data = [];
    const start = new Date(startDate);
    const end   = new Date(endDate);
    end.setHours(23, 59, 59);

    const msPerDay = 1000 * 60 * 60 * 24;
    const days = Math.round((end - start) / msPerDay) + 1;
    const pointsPerDay = 8;
    let basePh = 7.0;

    for (let d = 0; d < days; d++) {
        for (let p = 0; p < pointsPerDay; p++) {
            const ts = new Date(start.getTime() + d * msPerDay + (p / pointsPerDay) * msPerDay);
            if (ts > end) break;
            basePh += (Math.random() - 0.49) * 0.3;
            basePh = Math.max(5.5, Math.min(9.5, basePh));
            const evento = selectedEventos[Math.floor(Math.random() * selectedEventos.length)];
            data.push({ timestamp: ts.toISOString(), evento, PH: parseFloat(basePh.toFixed(2)) });
        }
    }
    return data;
}

// ─────────────────────────────────────────────
// Actualizar tabla
// ─────────────────────────────────────────────
function updateTable(data) {
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';

    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;color:var(--text-muted);padding:32px 0">
            <div style="font-size:2rem;margin-bottom:8px">🔍</div>
            No hay registros en el rango seleccionado
        </td></tr>`;
        return;
    }

    data.forEach((row, index) => {
        const tr = document.createElement('tr');
        const dateObj = new Date(row.timestamp);
        const formattedDate = dateObj.toLocaleString('es-MX', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });

        // evento es texto: "DESCARGA", "INICIA", "TERMINA"
        const evKey    = (row.evento || '').toString().toUpperCase();
        const evLabel  = EVENTO_LABELS[evKey] || evKey || '—';
        const evColors = EVENTO_COLORS[evKey] || { bg: '#F1F5F9', text: '#64748B', border: '#CBD5E1' };
        const phClass  = (row.PH < 6.5 || row.PH > 8.5) ? 'ph-high' : 'ph-normal';

        tr.innerHTML = `
            <td class="td-timestamp">${formattedDate}</td>
            <td class="${phClass}">${row.PH.toFixed(2)}</td>
            <td class="td-evento"><span class="evento-badge" style="background:${evColors.bg};color:${evColors.text};border-color:${evColors.border}">${evLabel}</span></td>
        `;

        tr.addEventListener('click', () => {
            document.querySelectorAll('tbody tr').forEach(r => r.classList.remove('selected'));
            tr.classList.add('selected');
            showTooltip(formattedDate, row.PH, evLabel);
        });
        tbody.appendChild(tr);
    });
}

// ─────────────────────────────────────────────
// Actualizar gráfica
// ─────────────────────────────────────────────
function updateChart(data) {
    const ctx = document.getElementById('phChart').getContext('2d');
    const chartData = data.map(row => ({ x: row.timestamp, y: row.PH }));

    let minPh = 0, maxPh = 14;
    if (chartData.length > 0) {
        const vals = chartData.map(d => d.y);
        minPh = Math.max(0, Math.floor(Math.min(...vals)) - 1);
        maxPh = Math.min(14, Math.ceil(Math.max(...vals)) + 1);
    }

    if (phChart) phChart.destroy();

    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(0, 200, 149, 0.28)');
    gradient.addColorStop(1, 'rgba(0, 200, 149, 0.0)');

    phChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'PH',
                data: chartData,
                borderColor: '#00C895',
                backgroundColor: gradient,
                borderWidth: 2.5,
                pointBackgroundColor: ctx => {
                    const evKey = (data[ctx.dataIndex]?.evento || '').toString().toUpperCase();
                    return EVENTO_COLORS[evKey]?.border || '#00C895';
                },
                pointBorderColor: '#FFFFFF',
                pointBorderWidth: 2,
                pointRadius: 5,
                pointHoverRadius: 8,
                fill: true,
                tension: 0.15
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'nearest', axis: 'x', intersect: false },
            onClick: (e, elements) => {
                if (elements.length > 0) {
                    const idx = elements[0].index;
                    const point = chartData[idx];
                    const evKey = (data[idx]?.evento || '').toString().toUpperCase();
                    const evLabel = EVENTO_LABELS[evKey] || evKey;
                    const dateObj = new Date(point.x);
                    const formattedDate = dateObj.toLocaleString('es-MX', {
                        year: 'numeric', month: '2-digit', day: '2-digit',
                        hour: '2-digit', minute: '2-digit', second: '2-digit'
                    });
                    showTooltip(formattedDate, point.y, evLabel);
                    const tbody = document.getElementById('tableBody');
                    if (tbody && tbody.children[idx]) {
                        document.querySelectorAll('tbody tr').forEach(r => r.classList.remove('selected'));
                        tbody.children[idx].classList.add('selected');
                        tbody.children[idx].scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    padding: 14,
                    backgroundColor: '#FFFFFF',
                    titleColor: '#64748B',
                    bodyColor: '#051C2C',
                    borderColor: '#E2E8F0',
                    borderWidth: 1,
                    cornerRadius: 10,
                    displayColors: false,
                    callbacks: {
                        label: ctx => `PH: ${ctx.raw.y.toFixed(2)}`,
                        afterLabel: ctx => {
                            const evKey = (data[ctx.dataIndex]?.evento || '').toString().toUpperCase();
                            const evLabel = EVENTO_LABELS[evKey] || evKey;
                            return evLabel ? `Evento: ${evLabel}` : '';
                        },
                        title: ctx => {
                            const date = new Date(ctx[0].raw.x);
                            return date.toLocaleString('es-MX', {
                                year: 'numeric', month: 'short', day: '2-digit',
                                hour: '2-digit', minute: '2-digit'
                            });
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        tooltipFormat: 'PP pp',
                        displayFormats: { minute: 'HH:mm', hour: 'DD MMM HH:mm', day: 'DD MMM' }
                    },
                    title: {
                        display: true, text: 'MOMENTO DE LECTURA (TIMESTAMP)',
                        color: '#64748B', font: { size: 12, weight: 600, family: 'Inter' }
                    },
                    grid: { color: '#E2E8F0', drawBorder: false },
                    ticks: { color: '#64748B', font: { size: 11, family: 'Inter' } }
                },
                y: {
                    title: {
                        display: true, text: 'NIVEL DE PH',
                        color: '#64748B', font: { size: 12, weight: 600, family: 'Inter' },
                        padding: { top: 0, bottom: 10 }
                    },
                    min: minPh, max: maxPh,
                    grid: { color: '#E2E8F0', drawBorder: false },
                    ticks: { color: '#64748B', stepSize: 1, font: { size: 11, family: 'Inter' } }
                }
            }
        }
    });
}

// ─────────────────────────────────────────────
// Tooltip
// ─────────────────────────────────────────────
function showTooltip(timeStr, phValue, eventoLabel) {
    const tooltip = document.getElementById('chartTooltipData');
    document.getElementById('selectedTime').innerText = timeStr;
    const phEl = document.getElementById('selectedPh');
    phEl.innerText = Number(phValue).toFixed(2);
    phEl.className = 'ph-value' + ((phValue < 6.5 || phValue > 8.5) ? ' ph-value-danger' : '');
    tooltip.classList.remove('hidden');
    tooltip.style.transform = 'scale(1.02)';
    setTimeout(() => { tooltip.style.transform = 'scale(1)'; }, 200);
}

// ─────────────────────────────────────────────
// Exportar CSV
// ─────────────────────────────────────────────
function exportToCSV() {
    if (!currentData || currentData.length === 0) {
        alert('No hay datos para exportar.');
        return;
    }
    let csvContent = 'Fecha y Hora,PH,Evento\n';
    currentData.forEach(row => {
        const dateObj = new Date(row.timestamp);
        const formattedDate = dateObj.toLocaleString('es-MX', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        }).replace(',', '');
        const evKey   = (row.evento || '').toString().toUpperCase();
        const evLabel = EVENTO_LABELS[evKey] || evKey || '';
        csvContent += `${formattedDate},${row.PH},${evLabel}\n`;
    });
    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', 'Reporte_PH_Solenis.csv');
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);     
}

// ─────────────────────────────────────────────
// Error visual
// ─────────────────────────────────────────────
function showError(msg) {
    const tbody = document.getElementById('tableBody');
    const isConnection = msg.includes('conectar') || msg.includes('servidor');
    tbody.innerHTML = `<tr><td colspan="3" style="text-align:center;color:var(--danger-color);padding:32px 16px">
        <div style="font-size:2rem;margin-bottom:8px">${isConnection ? '🔌' : '⚠️'}</div>
        <div style="font-weight:700;margin-bottom:4px">${isConnection ? 'Error de conexión' : 'Error'}</div>
        <div style="font-size:0.82rem;color:var(--text-muted);max-width:260px;margin:0 auto">${msg}</div>
    </td></tr>`;

    // También ocultar el contador de resultados
    document.getElementById('resultsHeader').style.display = 'none';
}
