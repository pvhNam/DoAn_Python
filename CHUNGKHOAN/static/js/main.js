const API_URL = '/api/latest-prices';

function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(num);
}
function formatVol(num) {
    return new Intl.NumberFormat('en-US').format(num);
}

async function renderTable() {
    try {
        const response = await fetch(API_URL);
        const stocks = await response.json();
        const tableBody = document.getElementById('stock-table-body');
        
        if(stocks.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="7" style="text-align: center;">Chưa có dữ liệu</td></tr>';
            return;
        }

        tableBody.innerHTML = ''; 

        stocks.forEach(stock => {
            const price = parseFloat(stock.close);
            const change = parseFloat(stock.change_amount);
            const percent = parseFloat(stock.change_percent);
            
            let colorClass = 'row-ref';
            let arrow = '';
            let sign = '';
            
            if (change > 0) { colorClass = 'row-up'; arrow = '▲'; sign = '+'; }
            else if (change < 0) { colorClass = 'row-down'; arrow = '▼'; }

            const rowHtml = `
                <tr class="${colorClass}">
                    <td class="symbol">${stock.symbol}</td>
                    <td class="price-cell">${formatNumber(price)}</td>
                    <td class="change">${sign}${formatNumber(change)} ${arrow}</td>
                    <td class="percent">${sign}${formatNumber(percent)}%</td>
                    <td class="text-right">${formatVol(stock.volume)}</td>
                    <td class="text-right">${formatNumber(stock.high)}</td>
                    <td class="text-right">${formatNumber(stock.low)}</td>
                </tr>
            `;
            tableBody.insertAdjacentHTML('beforeend', rowHtml);
        });
    } catch (error) { console.error("Lỗi:", error); }
}

document.addEventListener('DOMContentLoaded', () => {
    renderTable();
    setInterval(renderTable, 5000); // Cập nhật mỗi 5 giây
});