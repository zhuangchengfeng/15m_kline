from binance.um_futures import UMFutures
from config import Config




proxies = {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890"
}
with open(Config.API_KEY_SECRET_FILE_PATH, 'r') as f:
    data = f.readlines()

clean_list = [item.strip() for item in data]

client = UMFutures(key=clean_list[0], secret=clean_list[1], proxies=proxies)

