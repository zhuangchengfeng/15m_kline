当前版本功能，监听三个detect.py自定义信号，将有信号的品种保存至信号列表 在币安软件上按下+键 读取列表自动输入品种名字后方便看K线，省去一个一个输名字看品种太麻烦
同时拥有保存历史功能，在json文件里能看到每次信号的开仓信息，report.py负责更新信号的亏损和盈利情况

run.py  函数主入口

alert_manager.py  蜂鸣管理器，负责有信号产生时发出声音

collector.py 负责并发获取和处理币安K线数据，已配置7890clash代理、断线延迟重连。

config.py  项目部分参数配置文件

detect.py  负责检测信号和自定义信号功能，同时对信号产生保存为JSON

keyboard_handler.py  负责键盘事件 + 键 在币安输入下一个品种 - 键 切换上一个品种  1080P分辨率电脑端币安 坐标可在config自定义

mouse_operator.py  鼠标事件

report.py  负责产生回测报告和更新JSON 每个品种的mark_price 最新价格,用于判断历史数据

signal_manger.py 信号管理器

signal_recorder.py  负责json处理

symbol_manager.py  负责过滤合约品种列表

test.py 
