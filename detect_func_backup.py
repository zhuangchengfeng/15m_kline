
def detect_rg_pattern_signals(df, close_col='close', open_col='open', low_col='low'):
    """
    检测RED_GREEN_K线组合信号

    规则：
    1. 寻找阴阳K线组合（当前为阴线，前一根为阳线）
    2. 当发现一个阴阳组合时，向前查找最近的一个阴阳组合
    3. 如果之前的阴线最低点 > 当前阴线最低点，产生信号

    参数：
    df: DataFrame，包含OHLC数据
    close_col: 收盘价列名
    open_col: 开盘价列名
    low_col: 最低价列名

    返回：
    signals: 包含信号的DataFrame
    """

    # 复制数据避免修改原数据
    df = df.copy()

    # 确保数据按时间升序排列（旧数据在前，新数据在后）
    df = df.sort_values('open_time').reset_index(drop=True)

    # 判断K线阴阳（True为阳线，False为阴线）
    df['is_yang'] = df[close_col] > df[open_col]

    # 找出阴阳组合：
    df['is_yin_yang_pattern'] = (df['is_yang']) & (~df['is_yang']).shift(1)
    # 找出所有阴阳组合的位置
    pattern_indices = df[df['is_yin_yang_pattern']].index.tolist()
    # 初始化信号列
    df['signal'] = 0  # 0表示无信号，1表示有信号
    df['prev_pattern_low'] = np.nan  # 记录前一个模式的最低点
    df['current_pattern_low'] = np.nan  # 记录当前模式的最低点

    if len(pattern_indices) >= 2:
        # 只取最后两个索引
        prev_idx = pattern_indices[-2] - 1  # 倒数第二个模式
        current_idx = pattern_indices[-1] - 1  # 最后一个模式（最新的）

        prev_low = df.loc[prev_idx, low_col]
        current_low = df.loc[current_idx, low_col]
        # 判断条件
        if prev_low < current_low:
            return True
        else:
            return False
    else:
        return False

