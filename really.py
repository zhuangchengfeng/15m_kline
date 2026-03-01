import logging
from binance.um_futures import UMFutures
from binance.lib.utils import config_logging
from binance.error import ClientError
import math
from config import Config
config_logging(logging, logging.INFO)



def xxt():
    try:

        proxies = {
            "http": "http://127.0.0.1:7890",
            "https": "http://127.0.0.1:7890"
        }
        with open(Config.API_KEY_SECRET_FILE_PATH, 'r') as f:
            data = f.readlines()

        clean_list = [item.strip() for item in data]
        rsa_client = UMFutures(key=clean_list[0], secret=clean_list[1],proxies=proxies)

        response = rsa_client.account(recvWindow=4000)
        wallet_balance = float(response['totalWalletBalance'])
        result = math.log(Config.TARGET / wallet_balance) / math.log(Config.RATIO)
        return round(result,0)
        # logging.info(response)
    #
    except ClientError as error:
        logging.error(
            "Found error. status: {}, error code: {}, error message: {}".format(
                error.status_code, error.error_code, error.error_message
            )
        )

if __name__ == '__main__':

    xxt()