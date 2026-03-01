当前版本功能，监听三个detect.py自定义信号，将有信号的品种保存至信号列表 在币安软件上按下+键 读取列表自动输入品种名字后方便看K线，省去一个一个输名字看品种太麻烦
同时拥有保存历史功能，在json文件里能看到每次信号的开仓信息，report.py负责更新信号的亏损和盈利情况

### 正常运行请把config.py的SCAN_INTERVALS_DEBUG 设置为False 即可每15分钟运行一次  DEBUG模式下 每分钟运行一次###
run.py  函数主入口

alert_manager.py  蜂鸣管理器，负责有信号产生时发出声音

analyse.py  负责产生回测报告和更新JSON 每个品种的mark_price 最新价格,用于判断历史数据

collector.py 负责并发获取和处理币安K线数据，已配置7890clash代理、断线延迟重连。

config.py  项目大多数参数配置文件,涵盖很多变量

detect.py  负责检测信号和自定义信号监听功能

ema_atr_manager.py  负责计算ema和atr等指标

keyboard_handler.py  负责键盘事件 + 键 在币安输入下一个品种 - 键 切换上一个品种  1080P分辨率电脑端币安 坐标可在config自定义

mouse_operator.py  鼠标事件

really.py  负责计算账户本金一些功能，需要提供key和secret

signal_manger.py 信号管理器

signal_recorder.py  负责记录信号，转为json处理

symbol_manager.py  负责过滤合约品种列表

tools.py  一些辅助工具和脚本

trade_parser.py  个人使用

具体使用方法：运行run以后，在活动窗口为币安或tradingview时，按下+键可方便快速查询品种K线
signal_data用来存放信号文件和计算几个小时后的涨跌幅，可回测信号的胜率


