// ==================== 全局变量 ====================
let currentView = 'symbol';        // 'symbol' 或 'time'
let currentFilter = 'all';         // 'all', 'win', 'loss'
let tradeNotes = {};               // 备注存储
let currentNoteKey = null;         // 当前编辑的备注key
let originalSymbolStats = [];      // 原始品种统计数据
let filteredSymbolStats = [];       // 过滤后的品种统计数据
let allTimeTrades = [];            // 所有按时间排序的交易
let filteredTimeTrades = [];        // 过滤后的时间视图交易

// ==================== 分页相关变量 ====================
let currentPage = 1;
const PAGE_SIZE = 20;  // 每页显示20个品种
let isLoadingMore = false;

// ==================== 亏损阈值 ====================
let minLossAmount = 2;   // 默认2

// ==================== 初始化 ====================
document.addEventListener('DOMContentLoaded', function() {
    if (typeof TRADES_BY_SYMBOL === 'undefined' || typeof TRADES_BY_TIME === 'undefined') {
        console.error('错误: 未找到交易数据');
        document.getElementById('tableContainer').innerHTML = '<p style="color:red;padding:20px;">数据加载失败，请检查 trades_data.js 文件</p>';
        return;
    }

    // 加载备注
    try {
        const saved = localStorage.getItem('tradeNotes_v2');
        if (saved) tradeNotes = JSON.parse(saved);
    } catch(e) {}

    document.getElementById('generateTime').textContent = new Date().toLocaleString('zh-CN');

    // 初始化数据
    originalSymbolStats = getSymbolStats();
    allTimeTrades = [...TRADES_BY_TIME];

    // 更新日期范围显示
    updateDateRange();

    // 渲染汇总卡片
    updateSummaryCards();

    // 应用筛选并渲染当前视图
    applyFilterAndRender();

    // 绑定事件
    document.getElementById('viewBySymbol').onclick = () => switchView('symbol');
    document.getElementById('viewByTime').onclick = () => switchView('time');
    document.getElementById('filterAll').onclick = () => setFilter('all');
    document.getElementById('filterWin').onclick = () => setFilter('win');
    document.getElementById('filterLoss').onclick = () => setFilter('loss');
    document.getElementById('clearAllNotes').onclick = clearAllNotes;

    // ========== 阈值控件绑定 ==========
    const minLossInput = document.getElementById('minLossAmount');
    const applyBtn = document.getElementById('applyThreshold');
    if (minLossInput && applyBtn) {
        applyBtn.onclick = () => {
            let val = parseFloat(minLossInput.value);
            if (isNaN(val)) val = 0;
            minLossAmount = val;
            currentPage = 1;
            applyFilterAndRender();
        };
        minLossInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') applyBtn.click();
        });
    }

    // 监听滚动加载
    setupInfiniteScroll();

    // ESC关闭弹窗
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('noteModal');
            if (modal.style.display === 'flex') closeNoteModal();
        }
    });

    document.getElementById('noteModal').addEventListener('click', function(e) {
        if (e.target === this) closeNoteModal();
    });
});

// 设置无限滚动
function setupInfiniteScroll() {
    window.addEventListener('scroll', function() {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const windowHeight = window.innerHeight;
        const documentHeight = document.documentElement.scrollHeight;

        if (scrollTop + windowHeight >= documentHeight - 200) {
            loadMore();
        }
    });
}

// 加载更多数据
function loadMore() {
    if (isLoadingMore) return;

    if (currentView === 'symbol') {
        const totalPages = Math.ceil(filteredSymbolStats.length / PAGE_SIZE);
        if (currentPage >= totalPages) return;

        isLoadingMore = true;
        currentPage++;
        renderSymbolView(true);
        setTimeout(() => { isLoadingMore = false; }, 500);
    } else {
        const totalPages = Math.ceil(filteredTimeTrades.length / PAGE_SIZE);
        if (currentPage >= totalPages) return;

        isLoadingMore = true;
        currentPage++;
        renderTimeView(true);
        setTimeout(() => { isLoadingMore = false; }, 500);
    }
}

// 更新顶部汇总卡片
function updateSummaryCards() {
    const totalTrades = TRADES_BY_SYMBOL.length;
    const profitTrades = TRADES_BY_SYMBOL.filter(t => t[6] > 0).length;
    const lossTrades = TRADES_BY_SYMBOL.filter(t => t[6] < 0).length;
    const totalPnl = TRADES_BY_SYMBOL.reduce((sum, t) => sum + t[6], 0) - 125.26;
       const maxProfit = Math.max(...TRADES_BY_SYMBOL.map(t => t[6]));
    const maxLoss = Math.min(...TRADES_BY_SYMBOL.map(t => t[6]));

    document.getElementById('summaryCards').innerHTML = `
        <div class="stat-card"><h3>总交易笔数</h3><div class="value">${totalTrades}</div></div>
        <div class="stat-card"><h3>盈利笔数</h3><div class="value positive">${profitTrades}</div></div>
        <div class="stat-card"><h3>亏损笔数</h3><div class="value negative">${lossTrades}</div></div>
        <div class="stat-card"><h3>总盈亏(含去年10,11,12月手续费)</h3><div class="value ${totalPnl >= 0 ? 'positive' : 'negative'}">${totalPnl > 0 ? '+' : ''}${totalPnl.toFixed(2)}</div></div>
        <div class="stat-card"><h3>🏆 最大盈利</h3><div class="value positive">+${maxProfit.toFixed(2)}</div></div>
        <div class="stat-card"><h3>💔 最大亏损</h3><div class="value negative">${maxLoss.toFixed(2)}</div></div>
    `;
}

// 切换视图
function switchView(view) {
    currentView = view;
    currentPage = 1;
    document.getElementById('viewBySymbol').classList.toggle('active', view === 'symbol');
    document.getElementById('viewByTime').classList.toggle('active', view === 'time');
    applyFilterAndRender();
}

// 设置筛选
function setFilter(filter) {
    currentFilter = filter;
    currentPage = 1;
    document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`filter${filter === 'all' ? 'All' : filter === 'win' ? 'Win' : 'Loss'}`).classList.add('active');
    applyFilterAndRender();
}

// ==================== 核心过滤函数 ====================
function applyFilterAndRender() {
    // 1. 先按方向筛选原始交易
    let filteredByDir = [];
    if (currentFilter === 'all') {
        filteredByDir = allTimeTrades;
    } else {
        const isWin = currentFilter === 'win';
        filteredByDir = allTimeTrades.filter(t => isWin ? t[6] > 0 : t[6] < 0);
    }

    // 2. 按绝对值阈值过滤
    let finalTrades = filteredByDir;
    if (minLossAmount > 0) {
        finalTrades = filteredByDir.filter(t => {
            return Math.abs(t[6]) >= minLossAmount;
        });
    }
    filteredTimeTrades = finalTrades;

    // 3. 重新聚合品种视图
    const symbolMap = new Map();
    finalTrades.forEach(t => {
        const symbol = t[0];
        if (!symbolMap.has(symbol)) {
            symbolMap.set(symbol, { trades: [], totalPnl: 0, winCount: 0, lossCount: 0 });
        }
        const group = symbolMap.get(symbol);
        group.trades.push(t);
        group.totalPnl += t[6];
        if (t[6] > 0) group.winCount++;
        else if (t[6] < 0) group.lossCount++;
    });
    filteredSymbolStats = [];
    for (let [symbol, group] of symbolMap) {
        const totalTrades = group.trades.length;
        const winRate = totalTrades ? (group.winCount / totalTrades * 100).toFixed(1) : '0.0';
        const avgPnl = group.totalPnl / totalTrades;
        filteredSymbolStats.push({
            symbol: symbol,
            totalTrades: totalTrades,
            winCount: group.winCount,
            lossCount: group.lossCount,
            totalPnl: Number(group.totalPnl.toFixed(2)),
            winRate: winRate,
            avgPnl: Number(avgPnl.toFixed(2)),
            trades: group.trades
        });
    }
    filteredSymbolStats.sort((a, b) => b.totalPnl - a.totalPnl);

    // 4. 更新筛选信息
    const totalDisplay = currentView === 'symbol'
        ? filteredSymbolStats.reduce((s, stat) => s + stat.totalTrades, 0)
        : filteredTimeTrades.length;
    document.getElementById('filterInfo').textContent = `显示: ${totalDisplay} 笔交易 | 阈值: ≥${minLossAmount} USDT`;

    // 5. 渲染当前视图
    if (currentView === 'symbol') {
        renderSymbolView(false);
    } else {
        renderTimeView(false);
    }
}

// 更新交易日期范围显示
function updateDateRange() {
    if (!allTimeTrades || allTimeTrades.length === 0) {
        const dateRangeSpan = document.getElementById('dateRange');
        if (dateRangeSpan) dateRangeSpan.textContent = '无数据';
        return;
    }

    // 提取所有完整日期（t[10] 是完整开仓时间）
    const dates = allTimeTrades.map(t => {
        const dateTimeStr = t[10];
        if (!dateTimeStr) return null;
        return dateTimeStr.split(' ')[0];
    }).filter(d => d !== null);

    if (dates.length === 0) {
        const dateRangeSpan = document.getElementById('dateRange');
        if (dateRangeSpan) dateRangeSpan.textContent = '无法解析日期';
        return;
    }

    const sortedDates = [...dates].sort();
    const startDate = sortedDates[0];
    const endDate = sortedDates[sortedDates.length - 1];

    const start = new Date(startDate);
    const end = new Date(endDate);
    const diffTime = Math.abs(end - start);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;

    const dateRangeSpan = document.getElementById('dateRange');
    if (dateRangeSpan) {
        dateRangeSpan.textContent = `${startDate} 至 ${endDate} (共 ${diffDays} 天)`;
    }
}

// 生成交易唯一标识
function getTradeKey(trade) {
    return `${trade[0]}_${trade[2]}_${trade[1]}_${trade[4]}`.replace(/\s+/g, '_');
}

// 保存备注
function saveNotesToStorage() {
    localStorage.setItem('tradeNotes_v2', JSON.stringify(tradeNotes));
}

// 打开备注弹窗
window.openNoteModal = function(tradeKey, displayName, currentNote) {
    currentNoteKey = tradeKey;
    document.getElementById('modalTitle').textContent = `编辑备注 - ${displayName}`;
    document.getElementById('noteText').value = currentNote || '';
    document.getElementById('noteModal').style.display = 'flex';
};

window.closeNoteModal = function() {
    document.getElementById('noteModal').style.display = 'none';
    currentNoteKey = null;
};

window.saveNote = function() {
    if (!currentNoteKey) return;
    const note = document.getElementById('noteText').value.trim();
    if (note) {
        tradeNotes[currentNoteKey] = note;
    } else {
        delete tradeNotes[currentNoteKey];
    }
    saveNotesToStorage();
    closeNoteModal();
    applyFilterAndRender();
};

function clearAllNotes() {
    if (confirm('确定清除所有备注吗？')) {
        tradeNotes = {};
        saveNotesToStorage();
        applyFilterAndRender();
    }
}

// ==================== 品种视图渲染 ====================
function renderSymbolView(isLoadMore = false) {
    const container = document.getElementById('tableContainer');

    if (!isLoadMore) {
        container.innerHTML = '';
        currentPage = 1;
    }

    const startIdx = 0;
    const endIdx = currentPage * PAGE_SIZE;
    const currentPageData = filteredSymbolStats.slice(startIdx, endIdx);
    const hasMore = endIdx < filteredSymbolStats.length;

    if (!isLoadMore) {
        const table = document.createElement('table');
        table.id = 'symbolTable';
        table.innerHTML = `<thead>
            <th>排名</th><th>品种</th><th>交易笔数</th><th>胜率</th><th>总盈亏 (USDT)</th><th>平均盈亏</th>
        </thead><tbody id="symbolTbody"></tbody>`;
        container.appendChild(table);
    }

    const tbody = document.getElementById('symbolTbody');
    if (!tbody) return;

    currentPageData.forEach((stat, idx) => {
        const existingRow = document.querySelector(`.symbol-row[data-symbol="${stat.symbol}"]`);
        if (existingRow && isLoadMore) return;

        const globalIdx = startIdx + idx;
        const row = document.createElement('tr');
        row.className = 'symbol-row';
        row.setAttribute('data-symbol', stat.symbol);
        row.innerHTML = `
            <td style="font-weight:600;">${globalIdx + 1}</td>
            <td><span class="symbol-name"><span class="toggle-icon">▶</span> ${stat.symbol}</span></td>
            <td>${stat.totalTrades}</td>
            <td style="color: ${stat.winRate >= 50 ? '#1e8044' : '#c23a2e'};">${stat.winRate}%</td>
            <td class="${stat.totalPnl >= 0 ? 'positive' : 'negative'}">${stat.totalPnl > 0 ? '+' : ''}${stat.totalPnl.toFixed(2)}</td>
            <td class="${stat.avgPnl >= 0 ? 'positive' : 'negative'}">${stat.avgPnl > 0 ? '+' : ''}${stat.avgPnl.toFixed(2)}</td>
        `;
        tbody.appendChild(row);

        const detailRow = document.createElement('tr');
        detailRow.id = `detail-${stat.symbol}`;
        detailRow.className = 'trades-detail';
        detailRow.style.display = 'none';
        detailRow.innerHTML = `<td colspan="6" style="padding: 12px 20px;"></td>`;
        tbody.appendChild(detailRow);
    });

    if (hasMore && !isLoadMore) {
        addLoadingIndicator(container, 'symbol');
    } else if (hasMore && isLoadMore) {
        updateLoadingIndicator('symbol', hasMore);
    } else {
        removeLoadingIndicator();
    }

    document.querySelectorAll('.symbol-row').forEach(row => {
        row.onclick = () => toggleSymbolDetail(row.dataset.symbol);
    });
}

function toggleSymbolDetail(symbol) {
    const detailRow = document.getElementById(`detail-${symbol}`);
    if (!detailRow) return;

    document.querySelectorAll('.trades-detail').forEach(d => {
        if (d.id !== `detail-${symbol}`) {
            d.style.display = 'none';
            const sym = d.id.replace('detail-', '');
            const icon = document.querySelector(`.symbol-row[data-symbol="${sym}"] .toggle-icon`);
            if (icon) icon.textContent = '▶';
        }
    });

    if (detailRow.style.display === 'none') {
        const stat = filteredSymbolStats.find(s => s.symbol === symbol);
        if (stat) {
            renderTradeDetails(detailRow, stat);
        }
        detailRow.style.display = 'table-row';
        const icon = document.querySelector(`.symbol-row[data-symbol="${symbol}"] .toggle-icon`);
        if (icon) icon.textContent = '▼';
    } else {
        detailRow.style.display = 'none';
        const icon = document.querySelector(`.symbol-row[data-symbol="${symbol}"] .toggle-icon`);
        if (icon) icon.textContent = '▶';
    }
}

function renderTradeDetails(detailRow, stat) {
    let html = `<div style="padding: 4px 0;"><table class="detail-table" style="width:100%;"><thead>
        <th>方向</th><th>开仓时间</th><th>平仓时间</th><th>开仓价</th><th>平仓价</th><th>持仓(分)</th><th>盈亏</th><th>备注</th>
    </thead><tbody>`;

    stat.trades.forEach(t => {
        const dirClass = t[1] === '多' ? 'positive' : 'negative';
        const pnlClass = t[6] > 0 ? 'positive' : (t[6] < 0 ? 'negative' : '');
        const openPrice = t[4] > 1 ? t[4].toFixed(2) : t[4].toFixed(6);
        const closePrice = t[5] > 1 ? t[5].toFixed(2) : t[5].toFixed(6);
        const tradeKey = getTradeKey(t);
        const note = tradeNotes[tradeKey] || '';

        // 使用完整日期 t[10]，如果不存在则使用简短日期 t[2]
        const displayOpenTime = t[10] ? t[10] : t[2];

        html += `<tr onclick="openNoteModal('${tradeKey}', '${stat.symbol} ${displayOpenTime} ${t[1]}', \`${note.replace(/`/g, '\\`')}\`)">
            <td><span class="${dirClass}">${t[1]}</span></td>
            <td>${displayOpenTime}</td>
            <td>${t[3]}</td>
            <td>${openPrice}</td>
            <td>${closePrice}</td>
            <td>${t[7].toFixed(1)}</td>
            <td class="${pnlClass}">${t[6] > 0 ? '+' : ''}${t[6].toFixed(2)}</td>
            <td class="note-cell">${note ? '<span class="note-badge">📝 ' + note.substring(0, 15) + (note.length > 15 ? '...' : '') + '</span>' : '✏️ 点击添加'}</td>
        </tr>`;
    });
    html += `</tbody></table></div>`;
    detailRow.cells[0].innerHTML = html;
}

// ==================== 时间视图渲染 ====================
function renderTimeView(isLoadMore = false) {
    const container = document.getElementById('tableContainer');

    if (!isLoadMore) {
        container.innerHTML = '';
        currentPage = 1;

        const table = document.createElement('table');
        table.className = 'time-view-table';
        table.style.width = '100%';
        table.innerHTML = `<thead>
            <th>时间</th><th>品种</th><th>方向</th><th>开仓总金额</th><th>开仓价</th><th>平仓价</th><th>盈亏</th><th>收益率</th><th>持仓(分)</th><th>备注</th>
        </thead><tbody id="timeViewTbody"></tbody>`;
        container.appendChild(table);
    }

    const tbody = document.getElementById('timeViewTbody');
    if (!tbody) return;

    const startIdx = (currentPage - 1) * PAGE_SIZE;
    const endIdx = currentPage * PAGE_SIZE;
    const currentPageData = filteredTimeTrades.slice(startIdx, endIdx);
    const hasMore = endIdx < filteredTimeTrades.length;

    currentPageData.forEach(t => {
        // 数据格式: [品种, 方向, 开仓时间(简), 平仓时间(简), 开仓价, 平仓价, 盈亏, 持仓分钟, 收益率, 开仓总金额, 完整日期]
        const dirClass = t[1] === '多' ? 'positive' : 'negative';
        const pnlClass = t[6] > 0 ? 'positive' : (t[6] < 0 ? 'negative' : '');
        const openPrice = t[4] > 1 ? t[4].toFixed(2) : t[4].toFixed(6);
        const closePrice = t[5] > 1 ? t[5].toFixed(2) : t[5].toFixed(6);
        const tradeKey = getTradeKey(t);
        const note = tradeNotes[tradeKey] || '';
        const ret = t[8] || 0;
        const totalAmount = t[9] || 0;

        // 使用完整日期 t[10]，如果不存在则使用简短日期 t[2]
        const displayTime = t[10] ? t[10] : t[2];

        const row = document.createElement('tr');
        row.onclick = () => openNoteModal(tradeKey, `${t[0]} ${displayTime} ${t[1]}`, note);
        row.innerHTML = `
            <td style="white-space:nowrap;">${displayTime}</td>
            <td><strong>${t[0]}</strong></td>
            <td><span class="${dirClass}">${t[1]}</span></td>
            <td>${totalAmount.toFixed(2)}</td>
            <td>${openPrice}</td>
            <td>${closePrice}</td>
            <td class="${pnlClass}">${t[6] > 0 ? '+' : ''}${t[6].toFixed(2)}</td>
            <td class="${ret > 0 ? 'positive' : (ret < 0 ? 'negative' : '')}">${ret > 0 ? '+' : ''}${ret.toFixed(1)}%</td>
            <td>${t[7].toFixed(1)}</td>
            <td class="note-cell">${note ? '<span class="note-badge">📝 ' + note.substring(0, 12) + (note.length > 12 ? '...' : '') + '</span>' : '✏️'}</td>
        `;
        tbody.appendChild(row);
    });

    if (hasMore && !isLoadMore) {
        addLoadingIndicator(container, 'time');
    } else if (hasMore && isLoadMore) {
        updateLoadingIndicator('time', hasMore);
    } else {
        removeLoadingIndicator();
    }
}

// ==================== 加载提示组件 ====================
function addLoadingIndicator(container, viewType) {
    if (document.getElementById('loadingIndicator')) return;

    const loadingDiv = document.createElement('div');
    loadingDiv.id = 'loadingIndicator';
    loadingDiv.className = 'loading-indicator';
    loadingDiv.style.cssText = 'text-align:center;padding:20px;color:#666;font-size:14px;';
    loadingDiv.innerHTML = `
        <div>📀 正在加载更多...</div>
        <div style="font-size:12px;margin-top:5px;">滚动到底部自动加载</div>
    `;
    container.appendChild(loadingDiv);
}

function updateLoadingIndicator(viewType, hasMore) {
    const loadingDiv = document.getElementById('loadingIndicator');
    if (loadingDiv) {
        if (hasMore) {
            loadingDiv.innerHTML = `
                <div>📀 加载完成，继续滚动加载更多...</div>
                <div style="font-size:12px;margin-top:5px;">已加载 ${currentPage * PAGE_SIZE} 条</div>
            `;
        } else {
            loadingDiv.innerHTML = `
                <div>✅ 已加载全部数据 (共 ${currentView === 'symbol' ? filteredSymbolStats.length : filteredTimeTrades.length} 条)</div>
            `;
        }
    }
}

function removeLoadingIndicator() {
    const loadingDiv = document.getElementById('loadingIndicator');
    if (loadingDiv) {
        loadingDiv.remove();
    }
}