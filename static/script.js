const API_URL = '/api/data';
let phChart = null;
let currentData = [];

// Inicializa al cargar el DOM
document.addEventListener('DOMContentLoaded', () => {
    // Configurar fechas por defecto (Últimos 7 días)
    const today = new Date();
    const lastWeek = new Date();
    lastWeek.setDate(today.getDate() - 7);
    
    document.getElementById('endDate').value = today.toISOString().split('T')[0];
    document.getElementById('startDate').value = lastWeek.toISOString().split('T')[0];

    document.getElementById('filterBtn').addEventListener('click', fetchData);
    document.getElementById('exportBtn').addEventListener('click', exportToCSV);
    
    // Cargar datos iniciales
    fetchData();
});

async function fetchData() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    
    try {
        let url = API_URL;
        const params = new URLSearchParams();
        if (startDate) params.append('start_date', startDate);
        if (endDate) params.append('end_date', endDate);
        
        if(params.toString().length > 0) {
            url += '?' + params.toString();
        }

        const btn = document.getElementById('filterBtn');
        const originalText = btn.innerText;
        btn.innerText = 'Cargando...';
        btn.disabled = true;

        const response = await fetch(url);
        currentData = await response.json();
        
        btn.innerText = originalText;
        btn.disabled = false;

        updateTable(currentData);
        updateChart(currentData);
        
        // Ocultar tooltip al recargar datos
        document.getElementById('chartTooltipData').classList.add('hidden');
        
    } catch (error) {
        console.error('Error fetching data:', error);
        alert('Error al consultar datos de la base de datos.');
        const btn = document.getElementById('filterBtn');
        btn.innerText = 'Consultar Datos';
        btn.disabled = false;
    }
}

function updateTable(data) {
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';
    
    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="2" style="text-align: center; color: var(--text-muted)">No hay registros en el rango seleccionado</td></tr>';
        return;
    }

    data.forEach((row, index) => {
        const tr = document.createElement('tr');
        
        // Formatear timestamp
        const dateObj = new Date(row.timestamp);
        const formattedDate = dateObj.toLocaleString('es-MX', { 
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute:'2-digit', second:'2-digit'
        });

        // Determinar clase de PH
        let phClass = 'ph-normal';
        if (row.PH < 6.5 || row.PH > 8.5) {
            phClass = 'ph-high';
        }
        
        tr.innerHTML = `
            <td>${formattedDate}</td>
            <td class="${phClass}">${row.PH.toFixed(2)}</td>
        `;
        
        // Al hacer clic en un registro de la tabla
        tr.addEventListener('click', () => {
            // Resaltar fila seleccionada
            document.querySelectorAll('tbody tr').forEach(r => r.classList.remove('selected'));
            tr.classList.add('selected');
            
            showTooltip(formattedDate, row.PH);
            
            // Destacar punto en la gráfica (Opción avanzada: dispara el tooltip de Chart.js)
            if (phChart) {
                // Configurar el tooltip activo en chart.js
                // Buscamos el index en los datos del chart invertidos si fuera necesario, 
                // pero ya mostramos el custom tooltip superior.
            }
        });
        
        tbody.appendChild(tr);
    });
}

function updateChart(data) {
    const ctx = document.getElementById('phChart').getContext('2d');
    
    const chartData = data.map(row => ({
        x: row.timestamp, // Eje X: Timestamp
        y: row.PH         // Eje Y: PH
    }));

    let minPh = 0;
    let maxPh = 14;
    if (chartData.length > 0) {
        const phValues = chartData.map(d => d.y);
        minPh = Math.max(0, Math.floor(Math.min(...phValues)) - 1);
        maxPh = Math.min(14, Math.ceil(Math.max(...phValues)) + 1);
    }

    if (phChart) {
        phChart.destroy();
    }

    // Configuración para colores en armonía con Solenis
    const gradient = ctx.createLinearGradient(0, 0, 0, 400); // Gradiente vertical
    gradient.addColorStop(0, 'rgba(0, 200, 149, 0.3)'); // Solenis Green
    gradient.addColorStop(1, 'rgba(0, 200, 149, 0.0)');

    phChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'PH',
                data: chartData,
                borderColor: '#00C895', // Solenis Green
                backgroundColor: gradient,
                borderWidth: 3,
                pointBackgroundColor: '#FFFFFF',
                pointBorderColor: '#00C895',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 7,
                pointHoverBackgroundColor: '#00C895',
                pointHoverBorderColor: '#ffffff',
                fill: true,
                tension: 0.1 // Suavizado
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'x', // Eje X es Timestamp y Eje Y es PH
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            },
            onClick: (e, elements) => {
                if (elements.length > 0) {
                    const idx = elements[0].index;
                    const point = chartData[idx];
                    
                    const dateObj = new Date(point.x);
                    const formattedDate = dateObj.toLocaleString('es-MX', { 
                        year: 'numeric', month: '2-digit', day: '2-digit',
                        hour: '2-digit', minute:'2-digit', second:'2-digit'
                    });
                    
                    showTooltip(formattedDate, point.y);
                    
                    // Sincronizar tabla si se da clic en la grafica
                    const tbody = document.getElementById('tableBody');
                    if (tbody && tbody.children[idx]) {
                        document.querySelectorAll('tbody tr').forEach(r => r.classList.remove('selected'));
                        tbody.children[idx].classList.add('selected');
                        tbody.children[idx].scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    padding: 14,
                    backgroundColor: '#FFFFFF',
                    titleColor: '#64748B',
                    bodyColor: '#051C2C',
                    borderColor: '#E2E8F0',
                    borderWidth: 1,
                    cornerRadius: 8,
                    displayColors: false,
                    callbacks: {
                        label: function(context) {
                            return `PH: ${context.raw.y.toFixed(2)}`;
                        },
                        title: function(context) {
                             const date = new Date(context[0].raw.x);
                             return date.toLocaleString('es-MX', { 
                                 year: 'numeric', month: 'short', day: '2-digit',
                                 hour: '2-digit', minute:'2-digit'
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
                        displayFormats: {
                            minute: 'HH:mm',
                            hour: 'DD MMM HH:mm',
                            day: 'DD MMM'
                        }
                    },
                    title: {
                        display: true,
                        text: 'MOMENTO DE LECTURA ( TIMESTAMP )',
                        color: '#64748B',
                        font: { size: 12, weight: 600, family: 'Inter' }
                    },
                    grid: {
                        color: '#E2E8F0', // border-color light mode
                        drawBorder: false,
                        tickLength: 8
                    },
                    ticks: {
                        color: '#64748B',
                        font: { size: 11, family: 'Inter' }
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'NIVEL DE PH',
                        color: '#64748B',
                        font: { size: 12, weight: 600, family: 'Inter' },
                        padding: {top: 0, bottom: 10}
                    },
                    min: minPh,
                    max: maxPh,
                    grid: {
                        color: '#E2E8F0',
                        drawBorder: false,
                        tickLength: 8
                    },
                    ticks: {
                        color: '#64748B',
                        stepSize: 1,
                        font: { size: 11, family: 'Inter' }
                    }
                }
            }
        }
    });
}

function showTooltip(timeStr, phValue) {
    const tooltip = document.getElementById('chartTooltipData');
    document.getElementById('selectedTime').innerText = timeStr;
    document.getElementById('selectedPh').innerText = Number(phValue).toFixed(2);
    
    tooltip.classList.remove('hidden');
    
    // Feedback visual sutil (micro-animación)
    tooltip.style.transform = 'scale(1.02)';
    tooltip.style.borderColor = 'rgba(0, 200, 149, 0.8)';
    setTimeout(() => {
        tooltip.style.transform = 'scale(1)';
        tooltip.style.borderColor = 'rgba(0, 200, 149, 0.2)';
    }, 200);
}

function exportToCSV() {
    if (!currentData || currentData.length === 0) {
        alert('No hay datos para exportar.');
        return;
    }
    
    // Create CSV header
    let csvContent = 'Fecha y Hora (Timestamp),PH\n';
    
    // Add row data
    currentData.forEach(row => {
        const dateObj = new Date(row.timestamp);
        const formattedDate = dateObj.toLocaleString('es-MX', { 
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute:'2-digit', second:'2-digit'
        }).replace(',', ''); // Quitar coma si lo incluye el toLocaleString
        
        csvContent += `${formattedDate},${row.PH}\n`;
    });
    
    // Trigger download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', 'Reporte_PH_Solenis.csv');
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
