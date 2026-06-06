const API_URL = '/api/instrument_data';
const API_UNITS_URL = '/api/instrument_units';
let instrumentChart = null;
let currentData = [];
let limitMin = 6.0;
let limitMax = 8.0;

// Colors for chart
const CHART_COLOR = '#00C895';
const CHART_BG_START = 'rgba(0, 200, 149, 0.28)';
const CHART_BG_END = 'rgba(0, 200, 149, 0.0)';

// ─────────────────────────────────────────────
// Inicialización
// ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    // Cargar limites iniciales desde la API
    await fetchLimits();

    const today = new Date();
    const lastWeek = new Date();
    lastWeek.setDate(today.getDate() - 7);
    document.getElementById('endDate').value   = today.toISOString().split('T')[0];
    document.getElementById('startDate').value = lastWeek.toISOString().split('T')[0];

    document.getElementById('filterBtn').addEventListener('click', fetchData);
    document.getElementById('exportBtn').addEventListener('click', exportToCSV);
    document.getElementById('refreshBtn').addEventListener('click', fetchData);
    document.getElementById('unitFilter').addEventListener('change', fetchData);

    document.getElementById('startDate').addEventListener('change', validateDateRange);
    document.getElementById('endDate').addEventListener('change', validateDateRange);

    // Poblar combo de unidades primero, luego consultar
    await fetchUnits();
    await fetchData();
});

// ─────────────────────────────────────────────
// Cargar parámetros de límite
// ─────────────────────────────────────────────
async function fetchLimits() {
    try {
        const res = await fetch('/api/parametros');
        if (res.ok) {
            const params = await res.json();
            limitMin = params.MIN_PH_DESC ?? limitMin;
            limitMax = params.MAX_PH_DESC ?? limitMax;
        }
    } catch (e) {
        console.warn('No se pudieron cargar los parámetros de límite:', e);
    }
}

// ─────────────────────────────────────────────
// Cargar catálogo de unidades
// ─────────────────────────────────────────────
async function fetchUnits() {
    try {
        const response = await fetch(API_UNITS_URL);
        if (response.ok) {
            const units = await response.json();
            const select = document.getElementById('unitFilter');
            select.innerHTML = '<option value="">Todas las unidades</option>';
            units.forEach(unit => {
                const opt = document.createElement('option');
                opt.value = unit;
                opt.textContent = unit;
                select.appendChild(opt);
            });
        }
    } catch (err) {
        console.error('Error fetching units:', err);
    }
}

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
            alert.textContent = '⚠️ El rango no puede superar 2 meses.';
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
    alert.classList.add('hidden');
    btn.disabled = false;
    return true;
}

// ─────────────────────────────────────────────
// Fetch de datos
// ─────────────────────────────────────────────
async function fetchData() {
    if (!validateDateRange()) return;

    const startDate = document.getElementById('startDate').value;
    const endDate   = document.getElementById('endDate').value;
    const selectedUnit = document.getElementById('unitFilter').value;

    const btn = document.getElementById('filterBtn');
    btn.innerHTML = '<span class="spinner"></span> Cargando...';
    btn.disabled = true;

    try {
        const params = new URLSearchParams();
        if (startDate) params.append('start_date', startDate);
        if (endDate)   params.append('end_date', endDate);
        if (selectedUnit) params.append('unit', selectedUnit);

        let response = null;
        try {
            response = await fetch(`${API_URL}?${params.toString()}`);
            if (!response.ok) {
                const errText = await response.text();
                let errMsg = `Error del servidor (${response.status})`;
                try {
                    const errJson = JSON.parse(errText);
                    errMsg = errJson.detail || errMsg;
                } catch (_) {}
                throw new Error(errMsg);
            }
            currentData = await response.json();
        } catch (fetchErr) {
            if (fetchErr.message.startsWith('Error del servidor') || fetchErr.message === 'Failed to fetch') {
                showError(fetchErr.message === 'Failed to fetch'
                    ? 'No se pudo conectar al servidor. Verifica tu conexión.'
                    : fetchErr.message);
                return;
            }
            showError(`Error inesperado: ${fetchErr.message}`);
            return;
        }

        const banner = document.getElementById('simulatedBanner');
        // El servidor FastAPI de Solenis tiene un mecanismo de simulación si Supabase falla
        // Si no hay supabase, devuelve datos mock pero response.ok sigue siendo True.
        // Así que decidimos si mostrar el banner en base a si el backend no cuenta con supabase.
        // Pero para simplificar, si se conecta exitosamente a la API local ocultamos el banner.
        banner.classList.add('hidden');

        updateTable(currentData);
        updateChart(currentData, selectedUnit);
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
        const s = new Date(start + 'T12:00:00').toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
        const e = new Date(end   + 'T12:00:00').toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' });
        range.textContent = `${s} → ${e}`;
    }
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
        const dateObj = new Date(row.created_at);
        const formattedDate = dateObj.toLocaleString('es-MX', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });

        const unitStr = row.unit || '—';
        const isPhDescarga = unitStr.toLowerCase().includes('descarga') || unitStr.toLowerCase() === 'ph';
        const isOut = isPhDescarga && (row.extracted_value < limitMin || row.extracted_value > limitMax);
        const valClass = isOut ? 'ph-high' : 'ph-normal';

        tr.innerHTML = `
            <td class="td-timestamp">${formattedDate}</td>
            <td class="${valClass}">${row.extracted_value.toFixed(2)}</td>
            <td class="td-evento"><span class="evento-badge" style="background:rgba(59,130,246,0.08);color:#1d4ed8;border-color:rgba(59,130,246,0.25)">${unitStr}</span></td>
        `;

        tr.addEventListener('click', () => {
            document.querySelectorAll('tbody tr').forEach(r => r.classList.remove('selected'));
            tr.classList.add('selected');
            showTooltip(formattedDate, row.extracted_value, unitStr);
        });
        tbody.appendChild(tr);
    });
}

// ─────────────────────────────────────────────
// Actualizar gráfica
// ─────────────────────────────────────────────
function updateChart(data, selectedUnit) {
    const ctx = document.getElementById('instrumentChart').getContext('2d');
    const chartData = data.map(row => ({ x: row.created_at, y: row.extracted_value }));

    let minY = 0, maxY = 14;
    if (chartData.length > 0) {
        const vals = chartData.map(d => d.y);
        minY = Math.max(0, Math.floor(Math.min(...vals)) - 1);
        maxY = Math.ceil(Math.max(...vals)) + 1;
    }

    // Dibujar los límites solo si la unidad es pH_Descarga
    const drawLimits = selectedUnit.toLowerCase().includes('descarga') || selectedUnit.toLowerCase() === 'ph';
    if (drawLimits) {
        minY = Math.min(minY, Math.floor(limitMin) - 1);
        maxY = Math.max(maxY, Math.ceil(limitMax) + 1);
    }

    if (instrumentChart) instrumentChart.destroy();

    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, CHART_BG_START);
    gradient.addColorStop(1, CHART_BG_END);

    // Configuración de anotaciones (líneas de límite)
    const annotations = {};
    if (drawLimits) {
        annotations.limitMax = {
            type: 'line',
            yMin: limitMax,
            yMax: limitMax,
            borderColor: 'rgba(239,68,68,0.7)',
            borderWidth: 2,
            borderDash: [6, 4],
            label: {
                display: true,
                content: `Máx: ${limitMax}`,
                position: 'end',
                backgroundColor: 'rgba(239,68,68,0.1)',
                color: '#ef4444',
                font: { size: 11, weight: '700', family: 'Inter' },
                padding: 4
            }
        };
        annotations.limitMin = {
            type: 'line',
            yMin: limitMin,
            yMax: limitMin,
            borderColor: 'rgba(239,68,68,0.7)',
            borderWidth: 2,
            borderDash: [6, 4],
            label: {
                display: true,
                content: `Mín: ${limitMin}`,
                position: 'end',
                backgroundColor: 'rgba(239,68,68,0.1)',
                color: '#ef4444',
                font: { size: 11, weight: '700', family: 'Inter' },
                padding: 4
            }
        };
    }

    instrumentChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: selectedUnit || 'Valor',
                data: chartData,
                borderColor: CHART_COLOR,
                backgroundColor: gradient,
                borderWidth: 2.5,
                pointBackgroundColor: CHART_COLOR,
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
                    const unitStr = data[idx]?.unit || '';
                    const dateObj = new Date(point.x);
                    const formattedDate = dateObj.toLocaleString('es-MX', {
                        year: 'numeric', month: '2-digit', day: '2-digit',
                        hour: '2-digit', minute: '2-digit', second: '2-digit'
                    });
                    showTooltip(formattedDate, point.y, unitStr);
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
                annotation: { annotations },
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
                        label: ctx => `Valor: ${ctx.raw.y.toFixed(2)} ${data[ctx.dataIndex]?.unit || ''}`,
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
                        display: true, text: 'MARCA DE TIEMPO (CREATED_AT)',
                        color: '#64748B', font: { size: 12, weight: 600, family: 'Inter' }
                    },
                    grid: { color: '#E2E8F0', drawBorder: false },
                    ticks: { color: '#64748B', font: { size: 11, family: 'Inter' } }
                },
                y: {
                    title: {
                        display: true, text: `LECTURA DE INSTRUMENTO (${selectedUnit || 'VALOR'})`,
                        color: '#64748B', font: { size: 12, weight: 600, family: 'Inter' },
                        padding: { top: 0, bottom: 10 }
                    },
                    min: minY, max: maxY,
                    grid: { color: '#E2E8F0', drawBorder: false },
                    ticks: { color: '#64748B', font: { size: 11, family: 'Inter' } }
                }
            }
        }
    });
}

// ─────────────────────────────────────────────
// Tooltip
// ─────────────────────────────────────────────
function showTooltip(timeStr, value, unitStr) {
    const tooltip = document.getElementById('chartTooltipData');
    document.getElementById('selectedTime').innerText = timeStr;
    const phEl = document.getElementById('selectedPh');
    phEl.innerText = `${Number(value).toFixed(2)} ${unitStr}`;

    const isPhDescarga = unitStr.toLowerCase().includes('descarga') || unitStr.toLowerCase() === 'ph';
    const isOut = isPhDescarga && (value < limitMin || value > limitMax);
    phEl.className = 'ph-value' + (isOut ? ' ph-value-danger' : '');

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
    let csvContent = 'Fecha y Hora,Valor,Unidad\n';
    currentData.forEach(row => {
        const dateObj = new Date(row.created_at);
        const formattedDate = dateObj.toLocaleString('es-MX', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        }).replace(',', '');
        csvContent += `${formattedDate},${row.extracted_value},${row.unit || ''}\n`;
    });
    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', 'Reporte_Instrumentos_Solenis.csv');
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

    document.getElementById('resultsHeader').style.display = 'none';
}
