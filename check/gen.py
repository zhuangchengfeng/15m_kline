import re
from datetime import datetime
import json
import os

# 定义一个交易唯一标识的函数（用于去重）
def trade_signature(trade_data):
    """根据交易关键字段生成唯一签名"""
    # trade_data 是解析过程中收集的中间数据，包含 symbol, direction, open_time_str, open_price, close_price 等
    # 这里我们使用从原始块中提取的字段，因为解析函数中已经提取了这些信息
    # 为了通用，我们在解析时生成签名
    return None  # 实际在 parse_trades_from_txt 中生成

def parse_trades_from_txt(file_path):
    """
    从me15.txt解析交易记录，返回交易列表（已去重）
    每个交易格式: [品种, 杠杆, 方向, 开仓时间, 平仓时间, 开仓价, 平仓价, 盈亏USDT, 持仓分钟, 开仓完整时间, 收益率, 开仓总金额]
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 按空行分割每个交易块
    blocks = re.split(r'\n\s*\n', content.strip())
    trades = []
    trade_blocks_for_sort = []
    seen_signatures = set()   # 用于去重

    for block in blocks:
        if not block.strip():
            continue

        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if len(lines) < 19:
            continue

        try:
            symbol = lines[0]
            leverage = lines[2]
            direction_line = lines[3]
            direction = '多' if '做多' in direction_line else '空'

            open_time_line = [l for l in lines if '开仓时间' in l and '最后' not in l][0]
            open_time_str = open_time_line.replace('开仓时间', '').strip()

            close_time_line = [l for l in lines if '最后平仓时间' in l][0]
            close_time_str = close_time_line.replace('最后平仓时间', '').strip()

            pnl_idx = lines.index('已实现盈亏 (USDT)') + 1
            pnl_raw = lines[pnl_idx].replace('USDT', '').replace('+', '').replace(',', '').strip()
            pnl = float(pnl_raw) if '-' not in pnl_raw else -float(pnl_raw.replace('-', ''))

            # 收益率解析（处理 -- 的情况）
            ret_idx = lines.index('收益率') + 1
            ret_raw = lines[ret_idx].replace('%', '').replace('+', '').replace(',', '').strip()
            # 如果收益率是 "--" 或其他非数字，设置为 0
            if ret_raw == '' or ret_raw == '--' or ret_raw == '-':
                ret = 0.0
            else:
                try:
                    ret = float(ret_raw)
                except ValueError:
                    ret = 0.0

            open_price_idx = lines.index('开仓价格') + 1
            open_price = float(lines[open_price_idx].replace(',', ''))

            close_price_idx = lines.index('平仓均价') + 1
            close_price = float(lines[close_price_idx].replace(',', ''))

            # 获取已平仓量
            amount = 0
            for i, line in enumerate(lines):
                if '已平仓量' in line:
                    amount_str = lines[i + 1].split(' ')[0].replace(',', '')
                    amount = float(amount_str)
                    break
            total_amount = amount * open_price

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

            open_time_short = f"{open_time_str.split(' ')[0][:5]} {open_time_str.split(' ')[1][:5]}"
            close_time_short = f"{close_time_str.split(' ')[0][:5]} {close_time_str.split(' ')[1][:5]}"

            # 生成唯一签名（用于去重）
            signature = f"{symbol}_{direction}_{open_time_str}_{open_price}_{close_price}"
            if signature in seen_signatures:
                # 重复交易，跳过
                continue
            seen_signatures.add(signature)

            trades.append([
                symbol,           # 0: 品种
                leverage,         # 1: 杠杆
                direction,        # 2: 方向
                open_time_short,  # 3: 开仓时间
                close_time_short, # 4: 平仓时间
                open_price,       # 5: 开仓价
                close_price,      # 6: 平仓价
                pnl,              # 7: 盈亏
                hold_minutes,     # 8: 持仓分钟
                open_dt,          # 9: 完整开仓时间(用于排序)
                ret,              # 10: 收益率
                total_amount      # 11: 开仓总金额
            ])

            trade_blocks_for_sort.append((open_dt, block))

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"解析块时出错: {e}")
            continue

    return trades, trade_blocks_for_sort


def sort_txt_by_open_time(file_path):
    """按开仓时间排序txt文件，最新的在底部（同时去重）"""
    trades, trade_blocks = parse_trades_from_txt(file_path)
    # 按开仓时间排序
    trade_blocks.sort(key=lambda x: x[0])
    # 写入去重后的块
    with open(file_path, 'w', encoding='utf-8') as f:
        for i, (_, block) in enumerate(trade_blocks):
            f.write(block)
            if i < len(trade_blocks) - 1:
                f.write('\n\n')
    print(f"✅ TXT文件已去重并按开仓时间排序（最新的在底部）")
    return len(trade_blocks)


def generate_js_file(trades, output_path='static/trades_data.js'):
    """生成包含交易数据的JS文件"""
    os.makedirs('static', exist_ok=True)

    # 按开仓时间排序
    trades_sorted = sorted(trades, key=lambda x: x[9])

    # 按品种分组
    symbol_groups = {}
    for t in trades_sorted:
        symbol = t[0]
        if symbol not in symbol_groups:
            symbol_groups[symbol] = []
        symbol_groups[symbol].append(t)

    # 每个品种内部排序：亏损最多在前
    for symbol in symbol_groups:
        symbol_groups[symbol].sort(key=lambda x: (
            0 if x[7] < 0 else 1,
            x[7] if x[7] < 0 else -x[7]
        ))

    # 按品种顺序组合
    final_trades_by_symbol = []
    for symbol in sorted(symbol_groups.keys()):
        final_trades_by_symbol.extend(symbol_groups[symbol])

    # 清理 datetime 对象，转换为字符串
    def clean_trade(t):
        cleaned = list(t)
        if isinstance(cleaned[9], datetime):
            cleaned[9] = cleaned[9].strftime('%Y-%m-%d %H:%M:%S')
        return cleaned

    # 保留前12个字段（包括总金额），去掉杠杆字段（索引1）
    # 按品种分组的数据
    final_trades_clean = []
    for t in final_trades_by_symbol:
        cleaned = clean_trade(t)
        final_trades_clean.append([
            cleaned[0], cleaned[2], cleaned[3], cleaned[4],
            cleaned[5], cleaned[6], cleaned[7], cleaned[8],
            cleaned[10], cleaned[11],
            cleaned[9]  # 添加完整日期
        ])

    # 按时间顺序（最新的在前）
    time_sorted_trades = sorted(trades_sorted, key=lambda x: x[9], reverse=True)
    time_sorted_clean = []
    for t in time_sorted_trades:
        cleaned = clean_trade(t)
        # 数据格式: [品种, 方向, 开仓时间, 平仓时间, 开仓价, 平仓价, 盈亏, 持仓分钟, 收益率, 开仓总金额, 完整开仓日期]
        time_sorted_clean.append([
            cleaned[0],  # 品种
            cleaned[2],  # 方向
            cleaned[3],  # 开仓时间（简短）
            cleaned[4],  # 平仓时间（简短）
            cleaned[5],  # 开仓价
            cleaned[6],  # 平仓价
            cleaned[7],  # 盈亏
            cleaned[8],  # 持仓分钟
            cleaned[10],  # 收益率
            cleaned[11],  # 开仓总金额
            cleaned[9]  # 完整开仓时间 (YYYY-MM-DD HH:MM:SS)
        ])

    js_content = f"""// 从me15.txt自动生成的交易数据
// 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
// 总交易笔数: {len(trades)}
// 涉及品种数: {len(symbol_groups)}

// 数据格式: [品种, 方向, 开仓时间, 平仓时间, 开仓价, 平仓价, 盈亏, 持仓分钟, 收益率, 开仓总金额]

// 按品种分组的数据（每个品种内亏损最多在前）
const TRADES_BY_SYMBOL = {json.dumps(final_trades_clean, indent=2, ensure_ascii=False)};

// 按时间顺序的数据（最新的在前）
const TRADES_BY_TIME = {json.dumps(time_sorted_clean, indent=2, ensure_ascii=False)};

// 获取所有交易（默认按品种分组）
function getAllTrades() {{
    return TRADES_BY_SYMBOL;
}}

// 按品种聚合的统计数据
function getSymbolStats() {{
    const symbolMap = new Map();

    TRADES_BY_SYMBOL.forEach(t => {{
        const symbol = t[0];
        const pnl = t[6];
        const totalAmount = t[9];

        if (!symbolMap.has(symbol)) {{
            symbolMap.set(symbol, {{
                symbol: symbol,
                trades: [],
                totalPnl: 0,
                totalAmount: 0,
                winCount: 0,
                lossCount: 0
            }});
        }}

        const group = symbolMap.get(symbol);
        group.trades.push(t);
        group.totalPnl += pnl;
        group.totalAmount += totalAmount;
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
            totalAmount: Number(group.totalAmount.toFixed(2)),
            winRate: winRate,
            avgPnl: Number(avgPnl.toFixed(2)),
            trades: group.trades
        }});
    }}

    return stats.sort((a, b) => b.totalPnl - a.totalPnl);
}}

if (typeof module !== 'undefined' && module.exports) {{
    module.exports = {{ TRADES_BY_SYMBOL, TRADES_BY_TIME, getSymbolStats }};
}}
"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(js_content)

    print(f"✅ JS文件已生成: {output_path}")
    print(f"📊 总交易笔数: {len(trades)}")
    print(f"📊 涉及品种数: {len(symbol_groups)}")
    return symbol_groups


def generate_html_report(output_path='trading_report.html', dev_mode=False,file_name=''):
    """
    生成HTML报告
    dev_mode=True: 生成引用外部CSS/JS的版本（方便调试）
    dev_mode=False: 生成内嵌CSS/JS的版本（单文件，方便分享）
    """
    with open('templates/index.html', 'r', encoding='utf-8') as f:
        html_content = f.read()

    if dev_mode:
        html_content = html_content.replace(
            '<link rel="stylesheet" href="style.css">',
            '<link rel="stylesheet" href="templates/style.css">'
        ).replace(
            '<script src="app.js"></script>',
            '<script src="templates/app.js"></script>'
        ).replace(
            '<script src="../static/trades_data.js"></script>',
            f'<script src="static/trades_data{file_name}.js"></script>'
        )
        # 开发版文件名加 _dev
        if output_path.endswith('.html'):
            dev_path = output_path.replace('.html', '_dev.html')
        else:
            dev_path = output_path + '_dev.html'
        with open(dev_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"✅ 开发版HTML已生成: {dev_path}")
    else:
        with open('templates/style.css', 'r', encoding='utf-8') as f:
            css_content = f.read()
        with open('templates/app.js', 'r', encoding='utf-8') as f:
            js_content = f.read()
        final_html = html_content.replace(
            '<link rel="stylesheet" href="style.css">',
            f'<style>\n{css_content}\n</style>'
        ).replace(
            '<script src="app.js"></script>',
            f'<script>\n{js_content}\n</script>'
        ).replace(
            '<script src="../static/trades_data.js"></script>',
            f'<script src="static/trades_data{file_name}.js"></script>'
        )
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_html)
        print(f"✅ 生产版HTML已生成: {output_path} (内嵌CSS/JS，单文件)")


# 主程序
if __name__ == "__main__":
    for i in ['me15.txt']:
        txt_path = i
        if not os.path.exists(txt_path):
            print(f"❌ 找不到文件: {txt_path}")
            exit(1)

        # 1. 排序并去重txt文件
        total_trades = sort_txt_by_open_time(txt_path)
        print(f"📊 TXT文件排序完成，共{total_trades}笔交易")

        # 2. 解析交易数据（去重后）
        trades, _ = parse_trades_from_txt(txt_path)

        # 3. 找出最新开仓时间（用于文件名）
        if trades:
            latest_dt = max(trades, key=lambda x: x[9])[9]  # x[9] 是完整开仓时间 datetime 对象
            file_time_str = latest_dt.strftime('%Y-%m-%d')
            base_filename = f"{file_time_str}_{i}report.html"
        else:
            base_filename = "report.html"

        # 4. 生成JS数据文件
        symbol_groups = generate_js_file(trades, f'static/trades_data{i}.js')

        # 5. 生成两个版本的HTML（生产版和开发版）
        # generate_html_report(base_filename, dev_mode=False)  # 生产版
        generate_html_report(base_filename, dev_mode=True,file_name=i)   # 开发版
