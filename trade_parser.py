import re
import json
from datetime import datetime
from collections import defaultdict

from datetime import datetime

def is_datetime_string(s, fmt='%Y-%m-%d %H:%M:%S'):
    """检查字符串是否是指定格式的日期时间"""
    try:
        datetime.strptime(s, fmt)
        return True
    except ValueError:
        return False
def parse_amount(text):
    """解析金额，处理逗号和USDT后缀"""
    # 匹配数字部分（可能包含逗号、负号、小数点）
    match = re.search(r'([-\d,.]+)', text)
    if match:
        # 移除逗号，转换为浮点数
        amount_str = match.group(1).replace(',', '')
        return float(amount_str)
    return 0.0

def parse_trade_file(filename):
    """解析交易文件，按品种分组"""

    # 读取文件
    with open(filename, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines()]

    # 按空行分割交易记录
    trades = []
    current_trade = []
    n= 0
    for line in lines:
        if n < 2:
            current_trade.append(line)
        elif n == 2:
            trades.append(current_trade)
            current_trade = []
            n = 0
            current_trade.append(line)

        if is_datetime_string(line):
            n+=1

    trades.append(current_trade)

    # 解析每个交易
    parsed_trades = []
    for trade_lines in trades:
        try:
            trade = {
                '开仓方向': 'SELL' if trade_lines[0] == 'S' else 'BUY',
                '品种': trade_lines[1],
                '开仓价格': float(re.search(r'([\d.]+)', trade_lines[6]).group(1)),
                '盈亏': parse_amount(trade_lines[8]),  # 改用新函数
                '平仓价格': float(re.search(r'([\d.]+)', trade_lines[12]).group(1)),
                '开仓时间': trade_lines[16],
                '平仓时间': trade_lines[18],
                '持仓时间': calculate_duration(trade_lines[16], trade_lines[18])
            }

            # 计算收益率
            if trade['开仓方向'] == 'SELL':
                # 做空收益率 = (开仓价 - 平仓价) / 开仓价
                trade['收益率'] = (trade['开仓价格'] - trade['平仓价格']) / trade['开仓价格'] * 100
            else:
                # 做多收益率 = (平仓价 - 开仓价) / 开仓价
                trade['收益率'] = (trade['平仓价格'] - trade['开仓价格']) / trade['开仓价格'] * 100

            trade['是否盈利'] = trade['盈亏'] > 0
            trade['pnl_abs'] = abs(trade['盈亏'])

            parsed_trades.append(trade)

        except Exception as e:
            # print(f"解析交易时出错: {e}")
            # print(f"问题数据: {trade_lines}")
            import traceback
            traceback.print_exc()
            pass

    return parsed_trades


def parse_quantity(text):
    """解析数量，处理逗号分隔"""
    match = re.search(r'([\d,.]+)', text)
    if match:
        return float(match.group(1).replace(',', ''))
    return 0


def parse_unit(text):
    """解析单位"""
    match = re.search(r'([A-Za-z0-9]+)$', text)
    if match:
        return match.group(1)
    return ''


def calculate_duration(open_time_str, close_time_str):
    """计算持仓时间（分钟）"""
    try:
        open_time = datetime.strptime(open_time_str, '%Y-%m-%d %H:%M:%S')
        close_time = datetime.strptime(close_time_str, '%Y-%m-%d %H:%M:%S')
        duration_seconds = (close_time - open_time).total_seconds()
        return int(duration_seconds / 60)  # 返回分钟数
    except Exception as e:
        print(e)
        return 0


def group_trades_by_symbol(trades):
    """按品种分组交易"""
    symbol_dict = defaultdict(list)

    for trade in trades:
        symbol = trade['品种']
        symbol_dict[symbol].append(trade)

    # 对每个品种的交易按时间排序
    for symbol in symbol_dict:
        symbol_dict[symbol].sort(key=lambda x: x['开仓时间'])

    return symbol_dict


def generate_symbol_summary(symbol_trades):
    """生成品种统计摘要"""
    total_trades = len(symbol_trades)
    profitable_trades = sum(1 for t in symbol_trades if t['是否盈利'])
    losing_trades = total_trades - profitable_trades

    total_pnl = sum(t['盈亏'] for t in symbol_trades)
    avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

    win_rate = profitable_trades / total_trades * 100 if total_trades > 0 else 0


    # 按交易方向统计
    buy_trades = [t for t in symbol_trades if t['开仓方向'] == 'BUY']
    sell_trades = [t for t in symbol_trades if t['开仓方向'] == 'SELL']

    buy_win_rate = sum(1 for t in buy_trades if t['是否盈利']) / len(buy_trades) * 100 if buy_trades else 0
    sell_win_rate = sum(1 for t in sell_trades if t['是否盈利']) / len(sell_trades) * 100 if sell_trades else 0

    # 平均持仓时间
    avg_duration = sum(t['持仓时间'] for t in symbol_trades) / total_trades if total_trades > 0 else 0

    # 找出最佳和最差交易
    best_trade = max(symbol_trades, key=lambda x: x['盈亏']) if symbol_trades else None
    worst_trade = min(symbol_trades, key=lambda x: x['盈亏']) if symbol_trades else None

    summary = {
        'symbol': symbol_trades[0]['品种'] if symbol_trades else '',
        'total_trades': total_trades,
        'profitable_trades': profitable_trades,
        'losing_trades': losing_trades,
        'win_rate': round(win_rate, 2),
        'total_pnl': round(total_pnl, 2),
        'avg_pnl': round(avg_pnl, 2),
        'buy_trades': len(buy_trades),
        'sell_trades': len(sell_trades),
        'buy_win_rate': round(buy_win_rate, 2),
        'sell_win_rate': round(sell_win_rate, 2),
        'buy_total_pnl': round(sum(t['盈亏'] for t in buy_trades), 2) if buy_trades else 0,
        'sell_total_pnl': round(sum(t['盈亏'] for t in sell_trades), 2) if sell_trades else 0,
        'avg_duration_minutes': round(avg_duration, 1),
        'best_trade': {
            'pnl': round(best_trade['盈亏'], 2) if best_trade else 0,
            '收益率': round(best_trade['收益率'], 2) if best_trade else 0,
            'date': best_trade['开仓时间'] if best_trade else ''
        } if best_trade else None,
        'worst_trade': {
            'pnl': round(worst_trade['盈亏'], 2) if worst_trade else 0,
            '收益率': round(worst_trade['收益率'], 2) if worst_trade else 0,
            'date': worst_trade['开仓时间'] if worst_trade else ''
        } if worst_trade else None
    }

    return summary


def export_to_json(trades, output_dir='output'):
    """导出为JSON格式"""
    import os

    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 按品种分组
    symbol_dict = group_trades_by_symbol(trades)

    # 导出每个品种的详细交易记录
    for symbol, symbol_trades in symbol_dict.items():
        symbol_file = os.path.join(output_dir, f'{symbol}_trades.json')

        symbol_data = {
            'symbol': symbol,
            'total_records': len(symbol_trades),
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': generate_symbol_summary(symbol_trades),
            'trades': symbol_trades
        }

        with open(symbol_file, 'w', encoding='utf-8') as f:
            json.dump(symbol_data, f, ensure_ascii=False, indent=2, default=str)

        print(f"已导出: {symbol_file} ({len(symbol_trades)} 笔交易)")

    # 导出所有品种的汇总
    all_symbols_file = os.path.join(output_dir, 'all_symbols_summary.json')

    all_symbols_data = {
        'total_trades': len(trades),
        'unique_symbols': len(symbol_dict),
        'symbols': list(symbol_dict.keys()),
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    # 添加每个品种的摘要
    symbols_summary = []
    for symbol, symbol_trades in symbol_dict.items():
        summary = generate_symbol_summary(symbol_trades)
        symbols_summary.append(summary)

    # 按总盈亏排序
    symbols_summary.sort(key=lambda x: x['total_pnl'], reverse=True)
    all_symbols_data['symbols_summary'] = symbols_summary

    with open(all_symbols_file, 'w', encoding='utf-8') as f:
        json.dump(all_symbols_data, f, ensure_ascii=False, indent=2)

    print(f"已导出汇总文件: {all_symbols_file}")


    return symbol_dict


def export_to_csv(symbol_dict, output_dir):
    """导出为CSV格式"""
    import csv

    # 导出每个品种的CSV
    for symbol, symbol_trades in symbol_dict.items():
        csv_file = os.path.join(output_dir, f'{symbol}_trades.csv')

        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            if symbol_trades:
                fieldnames = [
                    'symbol', 'direction', 'open_time', 'close_time',
                    'duration_minutes', 'open_price', 'close_price',
                    'return_rate', 'pnl', '是否盈利', 'closed_position',
                    'margin_mode', 'contract_type'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for trade in symbol_trades:
                    row = {
                        'symbol': trade['symbol'],
                        'direction': trade['direction'],
                        'open_time': trade['open_time'],
                        'close_time': trade['close_time'],
                        'duration_minutes': trade['duration'],
                        'open_price': trade['open_price'],
                        'close_price': trade['close_price'],
                        'return_rate': round(trade['return_rate'], 2),
                        'pnl': trade['pnl'],
                        '是否盈利': trade['是否盈利'],
                        'closed_position': trade['closed_position'],
                        'margin_mode': trade['margin_mode'],
                        'contract_type': trade['contract_type']
                    }
                    writer.writerow(row)

        print(f"已导出CSV: {csv_file}")

    # 导出所有品种汇总CSV
    summary_csv_file = os.path.join(output_dir, 'all_symbols_summary.csv')

    all_summaries = []
    for symbol, symbol_trades in symbol_dict.items():
        summary = generate_symbol_summary(symbol_trades)
        all_summaries.append(summary)

    all_summaries.sort(key=lambda x: x['total_pnl'], reverse=True)

    with open(summary_csv_file, 'w', newline='', encoding='utf-8') as f:
        if all_summaries:
            fieldnames = [
                'symbol', 'total_trades', 'profitable_trades', 'losing_trades',
                'win_rate', 'total_pnl', 'avg_pnl', 'total_volume',
                'buy_trades', 'sell_trades', 'buy_win_rate', 'sell_win_rate',
                'buy_total_pnl', 'sell_total_pnl', 'avg_duration_minutes'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for summary in all_summaries:
                writer.writerow(summary)

    print(f"已导出汇总CSV: {summary_csv_file}")


def generate_trading_report(trades):
    """生成交易报告"""
    total_trades = len(trades)
    profitable_trades = sum(1 for t in trades if t['是否盈利'])
    losing_trades = total_trades - profitable_trades
    total_pnl = sum(t['盈亏'] for t in trades)
    win_rate = profitable_trades / total_trades * 100 if total_trades > 0 else 0

    # 按品种统计
    symbol_dict = group_trades_by_symbol(trades)

    print("=" * 80)
    print("交易数据解析报告")
    print("=" * 80)
    print(f"总计交易笔数: {total_trades}")
    print(f"盈利交易: {profitable_trades} 笔")
    print(f"亏损交易: {losing_trades} 笔")
    print(f"胜率: {win_rate:.2f}%")
    print(f"总盈亏: {total_pnl:.2f} USDT")
    print(f"交易品种数: {len(symbol_dict)} 种")
    print()

    # 打印品种盈亏排行
    print("品种盈亏排行 (前20):")
    print("-" * 80)
    print(f"{'排名':<4} {'品种':<15} {'交易笔数':<8} {'胜率':<8} {'总盈亏':<10} {'平均盈亏':<10}")
    print("-" * 80)

    symbol_stats = []
    for symbol, symbol_trades in symbol_dict.items():
        total_pnl_symbol = sum(t['盈亏'] for t in symbol_trades)
        profitable_symbol = sum(1 for t in symbol_trades if t['是否盈利'])
        win_rate_symbol = profitable_symbol / len(symbol_trades) * 100
        avg_pnl_symbol = total_pnl_symbol / len(symbol_trades)

        symbol_stats.append({
            'symbol': symbol,
            'trades': len(symbol_trades),
            'win_rate': win_rate_symbol,
            'total_pnl': total_pnl_symbol,
            'avg_pnl': avg_pnl_symbol
        })

    # 按总盈亏排序
    symbol_stats.sort(key=lambda x: x['total_pnl'], reverse=True)

    for i, stat in enumerate(symbol_stats, 1):
        print(
            f"{i:<4} {stat['symbol']:<15} {stat['trades']:<8} {stat['win_rate']:<8.1f}% {stat['total_pnl']:<10.2f} {stat['avg_pnl']:<10.2f}")

    print()

    # 打印交易频率最高的品种
    print("交易频率最高的品种 (前10):")
    print("-" * 80)
    symbol_stats.sort(key=lambda x: x['trades'], reverse=True)

    for i, stat in enumerate(symbol_stats[:10], 1):
        print(f"{i:<4} {stat['symbol']:<15} {stat['trades']:<8} 笔交易")

    return symbol_dict


def main(input_file):
    """主函数
        input_file =  你的输入文件名
    """
    output_dir = "trading_data_" + input_file.split('.')[0]
    print("开始解析交易文件...")
    try:
        # 解析交易文件
        trades = parse_trade_file(input_file)
        print(f"成功解析 {len(trades)} 笔交易记录")

        # 生成报告
        symbol_dict = generate_trading_report(trades)

        # 导出为JSON和CSV
        print("\n开始导出数据...")
        export_to_json(trades, output_dir)

        # 生成HTML可视化报告（可选）
        generate_html_report(symbol_dict, output_dir)

        # 导出为CSV格式（可选）
        # export_to_csv(symbol_dict, output_dir)

        print(f"\n所有数据已导出到 '{output_dir}' 目录")

    except FileNotFoundError:
        import traceback
        traceback.print_exc()
        print(f"错误: 找不到文件 {input_file}")
    except Exception as e:
        print(f"处理过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()


def generate_html_report(symbol_dict, output_dir):
    """生成HTML可视化报告"""
    import os

    html_file = os.path.join(output_dir, 'trading_report.html')

    # 计算总体统计
    all_trades = []
    for trades in symbol_dict.values():
        all_trades.extend(trades)

    total_trades = len(all_trades)
    profitable_trades = sum(1 for t in all_trades if t['是否盈利'])
    losing_trades = total_trades - profitable_trades
    total_pnl = sum(t['盈亏'] for t in all_trades)
    avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
    win_rate = profitable_trades / total_trades * 100 if total_trades > 0 else 0

    # 计算每个品种的统计
    symbol_stats = []
    for symbol, symbol_trades in symbol_dict.items():
        total_pnl_symbol = sum(t['盈亏'] for t in symbol_trades)
        profitable_symbol = sum(1 for t in symbol_trades if t['是否盈利'])
        win_rate_symbol = profitable_symbol / len(symbol_trades) * 100
        avg_pnl_symbol = total_pnl_symbol / len(symbol_trades)
        sorted_trades = sorted(symbol_trades, key=lambda x: x['盈亏'], reverse=True)

        symbol_stats.append({
            'symbol': symbol,
            'trades': len(symbol_trades),
            'win_rate': win_rate_symbol,
            'total_pnl': total_pnl_symbol,
            'avg_pnl': avg_pnl_symbol,
            'trades_data': sorted_trades  # 包含详细交易数据
        })

    # 按总盈亏排序
    symbol_stats.sort(key=lambda x: x['total_pnl'], reverse=True)

    # 生成HTML内容
    html_content = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>交易数据分析报告</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1, h2, h3 {
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }
        .summary-box {
            background: #e8f5e9;
            border-left: 5px solid #4CAF50;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .stat-card {
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .stat-card h3 {
            color: #666;
            font-size: 14px;
            margin: 0 0 10px 0;
            border: none;
        }
        .stat-card .value {
            font-size: 24px;
            font-weight: bold;
            color: #4CAF50;
        }
        .stat-card .negative {
            color: #f44336;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background: #4CAF50;
            color: white;
        }
        .symbol-row {
            cursor: pointer;
            background: #f8f9fa;
        }
        .symbol-row:hover {
            background-color: #e9ecef !important;
        }
        .trades-detail {
            background: #f9f9f9;
        }
        .trades-detail table {
            margin: 0;
            background: white;
            border: 1px solid #ddd;
        }
        .trades-detail th {
            background: #f8f9fa;
            color: #495057;
            font-size: 11px;
            padding: 8px;
        }
        .trades-detail td {
            padding: 8px;
            font-size: 11px;
            border-bottom: 1px solid #eee;
        }
        tr:hover {
            background: #f5f5f5;
        }
        .positive {
            color: #4CAF50;
            font-weight: bold;
        }
        .negative {
            color: #f44336;
            font-weight: bold;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            color: #666;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 交易数据分析报告</h1>
        <p>生成时间: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>

        <div class="summary-box">
            <h2>总体统计</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <h3>总交易笔数</h3>
                    <div class="value">""" + str(total_trades) + """</div>
                </div>
                <div class="stat-card">
                    <h3>胜率</h3>
                    <div class="value">""" + f"{win_rate:.1f}%" + """</div>
                </div>
                <div class="stat-card">
                    <h3>总盈亏</h3>
                    <div class="value """ + (
        "positive" if total_pnl >= 0 else "negative") + """">""" + f"{total_pnl:+.2f} USDT" + """</div>
                </div>
                <div class="stat-card">
                    <h3>平均每笔盈亏</h3>
                    <div class="value """ + (
                       "positive" if avg_pnl >= 0 else "negative") + """">""" + f"{avg_pnl:+.2f} USDT" + """</div>
                </div>
            </div>
        </div>

        <h2>品种盈亏排行</h2>
        <table id="symbols-table">
            <thead>
                <tr>
                    <th>排名</th>
                    <th>品种</th>
                    <th>交易笔数</th>
                    <th>胜率</th>
                    <th>总盈亏</th>
                    <th>平均盈亏</th>
                </tr>
            </thead>
            <tbody>"""

    # 生成品种行
    for i, stat in enumerate(symbol_stats, 1):
        html_content += f"""
                <tr class="symbol-row" onclick="toggleTrades(this, '{stat['symbol']}')">
                    <td>{i}</td>
                    <td>{stat['symbol']} <small style="color: #666;">(点击查看详情)</small></td>
                    <td>{stat['trades']}</td>
                    <td>{stat['win_rate']:.1f}%</td>
                    <td class="{'positive' if stat['total_pnl'] >= 0 else 'negative'}">{stat['total_pnl']:+.2f}</td>
                    <td class="{'positive' if stat['avg_pnl'] >= 0 else 'negative'}">{stat['avg_pnl']:+.2f}</td>
                </tr>
                <tr id="trades-{stat['symbol']}" class="trades-detail" style="display: none;">
                    <td colspan="6" style="padding: 0;">
                        <div style="padding: 15px;">
                            <h4 style="margin-top: 0;">{stat['symbol']} 交易详情 ({stat['trades']} 笔)</h4>
                            <table>
                                <thead>
                                    <tr>
                                        <th>序号</th>
                                        <th>方向</th>
                                        <th>开仓时间</th>
                                        <th>平仓时间</th>
                                        <th>开仓价</th>
                                        <th>平仓价</th>
                                        <th>收益率</th>
                                        <th>盈亏</th>
                                        <th>持仓时间(分钟)</th>
                                    </tr>
                                </thead>
                                <tbody>"""

        # 生成该品种的详细交易行
        for j, trade in enumerate(stat['trades_data'], 1):
            html_content += f"""
                                    <tr>
                                        <td>{j}</td>
                                        <td><span class="{'positive' if trade['开仓方向'] == 'BUY' else 'negative'}">{trade['开仓方向']}</span></td>
                                        <td>{trade['开仓时间']}</td>
                                        <td>{trade['平仓时间']}</td>
                                        <td>{trade['开仓价格']:.6f}</td>
                                        <td>{trade['平仓价格']:.6f}</td>
                                        <td>{trade['收益率']:.2f}%</td>
                                        <td class="{'positive' if trade['盈亏'] >= 0 else 'negative'}">{trade['盈亏']:+.2f}</td>
                                        <td>{trade['持仓时间']}</td>
                                    </tr>"""

        html_content += """
                                </tbody>
                            </table>
                        </div>
                    </td>
                </tr>"""

    html_content += """
            </tbody>
        </table>

        <h2>数据文件</h2>
        <p>详细交易数据已导出为以下格式：</p>
        <ul>
            <li>每个品种的详细交易记录 (JSON格式)</li>
            <li>每个品种的交易统计 (CSV格式)</li>
            <li>所有品种汇总 (JSON格式)</li>
        </ul>

        <div class="footer">
            <p>报告生成系统 | 交易数据分析工具</p>
            <p>© 2024 交易分析平台</p>
        </div>
    </div>

    <script>
        function toggleTrades(row, symbol) {
            var detailRow = document.getElementById('trades-' + symbol);
            if (detailRow.style.display === 'none') {
                detailRow.style.display = 'table-row';
                row.style.backgroundColor = '#e3f2fd';
            } else {
                detailRow.style.display = 'none';
                row.style.backgroundColor = '';
            }
        }

        // 添加键盘支持
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                var allDetails = document.querySelectorAll('.trades-detail');
                allDetails.forEach(function(detail) {
                    detail.style.display = 'none';
                });
                var allRows = document.querySelectorAll('.symbol-row');
                allRows.forEach(function(row) {
                    row.style.backgroundColor = '';
                });
            }
        });
    </script>
</body>
</html>"""

    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"已生成HTML报告: {html_file}")


if __name__ == "__main__":
    import os

    main('txt_storage/D.txt')