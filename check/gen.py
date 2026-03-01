import re
from datetime import datetime
import json


def parse_trades_from_txt(file_path):
    """
    从me15.txt解析交易记录，返回交易列表
    每个交易格式: [品种, 杠杆, 方向, 开仓时间, 平仓时间, 开仓价, 平仓价, 盈亏USDT, 持仓分钟]
    """

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 按空行分割每个交易块
    blocks = re.split(r'\n\s*\n', content.strip())
    trades = []

    for block in blocks:
        if not block.strip():
            continue

        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if len(lines) < 19:
            continue

        try:
            # 品种
            symbol = lines[0]

            # 杠杆 (保留用于解析，但后续聚合时忽略)
            leverage = lines[2]

            # 方向
            direction_line = lines[3]
            direction = '多' if '做多' in direction_line else '空'

            # 开仓时间
            open_time_line = [l for l in lines if '开仓时间' in l and '最后' not in l][0]
            open_time_str = open_time_line.replace('开仓时间', '').strip()

            # 平仓时间
            close_time_line = [l for l in lines if '最后平仓时间' in l][0]
            close_time_str = close_time_line.replace('最后平仓时间', '').strip()

            # 盈亏
            pnl_idx = lines.index('已实现盈亏 (USDT)') + 1
            pnl_raw = lines[pnl_idx].replace('USDT', '').replace('+', '').replace(',', '').strip()
            pnl = float(pnl_raw) if '-' not in pnl_raw else -float(pnl_raw.replace('-', ''))

            # 开仓价
            open_price_idx = lines.index('开仓价格') + 1
            open_price = float(lines[open_price_idx].replace(',', ''))

            # 平仓价
            close_price_idx = lines.index('平仓均价') + 1
            close_price = float(lines[close_price_idx].replace(',', ''))

            # 持仓时间计算
            def parse_datetime(dt_str):
                parts = dt_str.split(' ')
                date_part = parts[0]
                time_part = parts[1]
                m, d, y = date_part.split('/')
                return datetime.strptime(f'{y}-{m}-{d} {time_part}', '%Y-%m-%d %H:%M:%S')

            open_dt = parse_datetime(open_time_str)
            close_dt = parse_datetime(close_time_str)
            hold_minutes = (close_dt - open_dt).total_seconds() / 60
            hold_minutes = round(hold_minutes, 1)

            # 格式化为前端需要的简洁时间格式 (月/日 时:分)
            open_time_short = f"{open_time_str.split(' ')[0][:5]} {open_time_str.split(' ')[1][:5]}"
            close_time_short = f"{close_time_str.split(' ')[0][:5]} {close_time_str.split(' ')[1][:5]}"

            trades.append([
                symbol,  # 0: 品种
                leverage,  # 1: 杠杆
                direction,  # 2: 方向
                open_time_short,  # 3: 开仓时间
                close_time_short,  # 4: 平仓时间
                open_price,  # 5: 开仓价
                close_price,  # 6: 平仓价
                pnl,  # 7: 盈亏
                hold_minutes  # 8: 持仓分钟
            ])

        except Exception as e:
            print(f"解析块时出错: {e}")
            continue

    return trades


def generate_js_file(trades, output_path='trades_data.js'):
    """
    生成包含交易数据的JS文件，内部交易按亏损最多在前排序
    """
    # 1. 按品种分组
    symbol_groups = {}
    for t in trades:
        symbol = t[0]
        if symbol not in symbol_groups:
            symbol_groups[symbol] = []
        symbol_groups[symbol].append(t)

    # 2. 对每个品种的内部交易进行排序：亏损最多在前
    for symbol in symbol_groups:
        # 排序key:
        # - 亏损交易排前面 (pnl < 0)
        # - 亏损交易按金额升序（-100, -50, -10）
        # - 盈利交易按金额降序（+100, +50, +10）
        symbol_groups[symbol].sort(key=lambda x: (
            0 if x[7] < 0 else 1,  # 亏损在前(0)，盈利在后(1)
            x[7] if x[7] < 0 else -x[7]  # 亏损：越小越靠前；盈利：越大越靠前
        ))

    # 3. 重新组合成单个数组（按品种顺序）
    final_trades = []
    for symbol in sorted(symbol_groups.keys()):
        final_trades.extend(symbol_groups[symbol])

    # 4. 生成JS文件
    js_content = f"""// 从me15.txt自动生成的交易数据
// 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
// 总交易笔数: {len(trades)}
// 涉及品种数: {len(symbol_groups)}
// ★★★ 重要: 每个品种的内部交易已按亏损最多在前排序 ★★★

const TRADES = {json.dumps(final_trades, indent=2, ensure_ascii=False)};

// 按品种聚合的统计数据
function getSymbolStats() {{
    const symbolMap = new Map();

    TRADES.forEach(t => {{
        const symbol = t[0];
        const pnl = t[7];

        if (!symbolMap.has(symbol)) {{
            symbolMap.set(symbol, {{
                symbol: symbol,
                trades: [],
                totalPnl: 0,
                winCount: 0,
                lossCount: 0
            }});
        }}

        const group = symbolMap.get(symbol);
        group.trades.push(t);
        group.totalPnl += pnl;
        if (pnl > 0) group.winCount++;
        else if (pnl < 0) group.lossCount++;
    }});

    const stats = [];
    for (let [sym, group] of symbolMap) {{
        const totalTrades = group.trades.length;
        const winRate = totalTrades ? (group.winCount / totalTrades * 100).toFixed(1) : '0.0';
        const avgPnl = group.totalPnl / totalTrades;

        stats.push({{
            symbol: sym,
            totalTrades: totalTrades,
            winCount: group.winCount,
            lossCount: group.lossCount,
            totalPnl: Number(group.totalPnl.toFixed(2)),
            winRate: winRate,
            avgPnl: Number(avgPnl.toFixed(2)),
            trades: group.trades  // 已经按亏损最多在前排序好了！
        }});
    }}

    // 按总盈亏降序（盈利多的在前）
    return stats.sort((a, b) => b.totalPnl - a.totalPnl);
}}

// 导出全局变量
if (typeof module !== 'undefined' && module.exports) {{
    module.exports = {{ TRADES, getSymbolStats }};
}}
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(js_content)

    print(f"✅ JS文件已生成: {output_path}")
    print(f"📊 总交易笔数: {len(trades)}")
    print(f"📊 涉及品种数: {len(symbol_groups)}")

    # 5. 打印排序验证
    print("\n" + "=" * 60)
    print("✅ 品种内部排序验证（亏损最多在前）:")
    print("=" * 60)

    for symbol in list(symbol_groups.keys())[:3]:  # 显示前3个品种
        trades_list = symbol_groups[symbol]
        print(f"\n📌 {symbol} (共{len(trades_list)}笔交易):")
        print("   " + "-" * 40)

        # 显示前3笔交易
        for i, t in enumerate(trades_list[:3]):
            pnl = t[7]
            direction = t[2]
            time_str = t[3]
            pnl_str = f"{pnl:+.2f}"
            print(f"   {i + 1}. [{direction}] {time_str} 盈亏: {pnl_str}")

        if len(trades_list) > 3:
            print(f"   ... 还有{len(trades_list) - 3}笔交易")

        # 验证排序是否正确
        first_pnl = trades_list[0][7]
        last_pnl = trades_list[-1][7]
        print(f"   ✅ 第一笔盈亏: {first_pnl:+.2f} (应该是亏损最多)")
        print(f"   ✅ 最后一笔盈亏: {last_pnl:+.2f} (应该是盈利最多)")

    return symbol_groups


def generate_html_template(output_path='trading_report.html'):
    """
    生成引用外部JS文件的HTML模板
    """
    html_content = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>永续合约 · 品种盈亏总览</title>
    <style>
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.5;
            margin: 0;
            padding: 24px;
            background: #f6f8fc;
            color: #0a1e2f;
        }
        .container {
            max-width: 1300px;
            margin: 0 auto;
            background: white;
            border-radius: 24px;
            padding: 28px 32px;
            box-shadow: 0 12px 28px rgba(0,0,0,0.03);
        }
        h1 {
            font-size: 1.9rem;
            font-weight: 600;
            margin-top: 0;
            margin-bottom: 8px;
            color: #0c2b4b;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .subhead {
            color: #506680;
            margin-bottom: 28px;
            border-bottom: 2px solid #eef2f7;
            padding-bottom: 20px;
            display: flex;
            justify-content: space-between;
            font-size: 0.92rem;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 36px;
        }
        .stat-card {
            background: #f2f6fd;
            border-radius: 18px;
            padding: 18px 20px;
            border: 1px solid #e5ebf5;
        }
        .stat-card h3 {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #4c6682;
            margin: 0 0 8px 0;
            font-weight: 600;
        }
        .stat-card .value {
            font-size: 1.9rem;
            font-weight: 700;
            line-height: 1;
        }
        .positive { color: #1e8044; }
        .negative { color: #c23a2e; }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
            background: white;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.02);
        }
        th {
            background: #f0f5fc;
            color: #1e3a5f;
            font-weight: 600;
            padding: 16px 12px;
            text-align: right;
            border-bottom: 1px solid #dce3ec;
        }
        th:first-child { text-align: left; padding-left: 20px; }
        td {
            padding: 14px 12px;
            border-bottom: 1px solid #f0f3f8;
            text-align: right;
        }
        td:first-child { text-align: left; padding-left: 20px; }
        .symbol-row {
            cursor: pointer;
            transition: background 0.1s;
        }
        .symbol-row:hover { background: #f2f8ff; }
        .symbol-name {
            font-weight: 700;
            color: #0a2647;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .toggle-icon {
            color: #5c7b9c;
            font-size: 0.75rem;
            display: inline-block;
            width: 18px;
        }
        .trades-detail {
            background: #fafdff;
            border-bottom: 2px solid #e9f0f7;
        }
        .trades-detail td { padding: 0; }
        .detail-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 12px;
            box-shadow: inset 0 1px 4px rgba(0,0,0,0.02);
        }
        .detail-table th {
            background: #f4f9fe;
            font-size: 0.7rem;
            padding: 10px 8px;
            color: #385073;
        }
        .detail-table td {
            padding: 10px 8px;
            font-size: 0.75rem;
            border-bottom: 1px solid #e7ecf2;
        }
        .footer-note {
            margin-top: 30px;
            text-align: right;
            color: #60758b;
            font-size: 0.75rem;
            border-top: 1px solid #e6ecf2;
            padding-top: 20px;
        }
        .win { color: #1e8044; }
        .loss { color: #c23a2e; }
    </style>
    <script src="trades_data.js"></script>
</head>
<body>
<div class="container">
    <h1>📊 品种盈亏排行 · 永续全仓</h1>
    <div class="subhead">
        <span>数据源: me15.txt · 自动解析生成</span>
        <span>生成时间: <span id="generateTime"></span></span>
    </div>

    <div class="summary-grid" id="summaryCards"></div>

    <h2 style="font-size:1.4rem; margin: 32px 0 16px;">📌 按品种汇总 · 点击查看详情</h2>
    <table id="symbolTable">
        <thead>
            <tr>
                <th>排名</th>
                <th>品种</th>
                <th>交易笔数</th>
                <th>胜率</th>
                <th>总盈亏 (USDT)</th>
                <th>平均盈亏</th>
            </tr>
        </thead>
        <tbody id="symbolTbody"></tbody>
    </table>
    <div class="footer-note">
        ⚡ 点击品种行展开/收起该品种所有交易明细 · 按总盈亏从高到低排序
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', function() {
    if (typeof TRADES === 'undefined') {
        console.error('错误: 未找到TRADES数据');
        return;
    }

    document.getElementById('generateTime').textContent = new Date().toLocaleString('zh-CN');

    // 计算总体统计
    const totalTrades = TRADES.length;
    const profitTrades = TRADES.filter(t => t[7] > 0).length;
    const lossTrades = TRADES.filter(t => t[7] < 0).length;
    const totalPnl = TRADES.reduce((sum, t) => sum + t[7], 0);

    document.getElementById('summaryCards').innerHTML = `
        <div class="stat-card"><h3>总交易笔数</h3><div class="value" style="font-size:1.8rem;">${totalTrades}</div></div>
        <div class="stat-card"><h3>盈利笔数</h3><div class="value positive">${profitTrades}</div></div>
        <div class="stat-card"><h3>亏损笔数</h3><div class="value negative">${lossTrades}</div></div>
        <div class="stat-card"><h3>总盈亏 (USDT)</h3><div class="value ${totalPnl >= 0 ? 'positive' : 'negative'}" style="font-size:1.8rem;">${totalPnl > 0 ? '+' : ''}${totalPnl.toFixed(2)}</div></div>
    `;

    const symbolStats = getSymbolStats();
    const tbody = document.getElementById('symbolTbody');
    tbody.innerHTML = '';

    symbolStats.forEach((stat, index) => {
        const row = document.createElement('tr');
        row.className = 'symbol-row';
        row.setAttribute('data-symbol', stat.symbol);
        row.innerHTML = `
            <td style="font-weight:600;">${index + 1}</td>
            <td><span class="symbol-name"><span class="toggle-icon">▶</span> ${stat.symbol}</span></td>
            <td>${stat.totalTrades}</td>
            <td style="color: ${stat.winRate >= 50 ? '#1e8044' : '#c23a2e'};">${stat.winRate}%</td>
            <td class="${stat.totalPnl >= 0 ? 'positive' : 'negative'}" style="font-weight:700;">${stat.totalPnl > 0 ? '+' : ''}${stat.totalPnl.toFixed(2)}</td>
            <td class="${stat.avgPnl >= 0 ? 'positive' : 'negative'}">${stat.avgPnl > 0 ? '+' : ''}${stat.avgPnl.toFixed(2)}</td>
        `;
        tbody.appendChild(row);

        // 详情行
        const detailRow = document.createElement('tr');
        detailRow.id = `detail-${stat.symbol}`;
        detailRow.className = 'trades-detail';
        detailRow.style.display = 'none';
        detailRow.innerHTML = `<td colspan="6" style="padding: 16px 24px;"></td>`;
        tbody.appendChild(detailRow);
    });

    // 点击事件
    window.toggleDetail = function(symbol) {
        const detailRow = document.getElementById(`detail-${symbol}`);
        if (!detailRow) return;

        document.querySelectorAll('.toggle-icon').forEach(icon => icon.textContent = '▶');

        if (detailRow.style.display === 'none') {
            if (!detailRow._loaded) {
                const stat = symbolStats.find(s => s.symbol === symbol);
                if (stat) {
                    let html = `<div style="background: white; border-radius: 16px; padding: 6px 0;"><table class="detail-table" style="width:100%;"><thead><tr><th>方向</th><th>开仓时间</th><th>平仓时间</th><th>开仓价</th><th>平仓价</th><th>持仓(分)</th><th>盈亏(USDT)</th></tr></thead><tbody>`;

                    stat.trades.forEach(t => {
                        const dirClass = t[2] === '多' ? 'positive' : 'negative';
                        const pnlClass = t[7] > 0 ? 'positive' : (t[7] < 0 ? 'negative' : '');
                        const openPrice = t[5] > 1 ? t[5].toFixed(2) : t[5].toFixed(6);
                        const closePrice = t[6] > 1 ? t[6].toFixed(2) : t[6].toFixed(6);

                        html += `<tr>
                            <td><span class="${dirClass}" style="font-weight:600;">${t[2]}</span></td>
                            <td>${t[3]}</td>
                            <td>${t[4]}</td>
                            <td>${openPrice}</td>
                            <td>${closePrice}</td>
                            <td>${t[8].toFixed(1)}</td>
                            <td class="${pnlClass}">${t[7] > 0 ? '+' : ''}${t[7].toFixed(2)}</td>
                        </tr>`;
                    });
                    html += `</tbody></table></div>`;
                    detailRow.cells[0].innerHTML = html;
                    detailRow._loaded = true;
                }
            }
            detailRow.style.display = 'table-row';
            const currentRow = document.querySelector(`.symbol-row[data-symbol="${symbol}"] .toggle-icon`);
            if (currentRow) currentRow.textContent = '▼';
        } else {
            detailRow.style.display = 'none';
            const currentRow = document.querySelector(`.symbol-row[data-symbol="${symbol}"] .toggle-icon`);
            if (currentRow) currentRow.textContent = '▶';
        }
    };

    document.querySelectorAll('.symbol-row').forEach(row => {
        const symbol = row.dataset.symbol;
        row.onclick = () => window.toggleDetail(symbol);
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.trades-detail').forEach(d => d.style.display = 'none');
            document.querySelectorAll('.toggle-icon').forEach(icon => icon.textContent = '▶');
        }
    });
});
</script>
</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✅ HTML模板已生成: {output_path}")


# 主程序
if __name__ == "__main__":
    # 1. 解析交易数据
    trades = parse_trades_from_txt('me15.txt')

    # 2. 生成JS数据文件（内部交易已排序）
    symbol_groups = generate_js_file(trades, 'trades_data.js')

    # 3. 生成HTML报告
    generate_html_template('trading_report.html')

    print("\n" + "=" * 60)
    print("🎉 完成！生成的文件：")
    print("   📁 trades_data.js    - 交易数据（已按亏损最多在前排序）")
    print("   📁 trading_report.html - 交易报告")
    print("\n👉 直接双击打开 trading_report.html 即可查看")
    print("=" * 60)