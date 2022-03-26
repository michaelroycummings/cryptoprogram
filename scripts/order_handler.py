## Internal Modules
from scripts.utils import DataLoc, MyLogger
from scripts.comms_dex_pancakeswapv2 import CommsDEXPancakeSwapV2
from scripts.comms_cex_binance import CommsCEXBinance
from scripts.comms_blockchain_bsc import CommsBlockchainBSC

## External Libraries
from typing import Union
import multiprocessing
import json
import queue
from web3.exceptions import TransactionNotFound


class OrderHandler():

    def __init__(self, order_queue: queue.Queue, log_queue: Union[multiprocessing.Queue, None] = None):
        self.DataLoc = DataLoc()
        with open(self.DataLoc.File.CONFIG.value) as json_file:
            config = json.load(json_file)['OrderHandler']
        self.queue_unplaced_orders = order_queue
        self.queue_unconfirmed_cex_orders = None
        self.queue_unconfirmed_dex_orders = None
        self.CommsCEXBinance = CommsCEXBinance()
        self.CommsDEXPancakeSwap = CommsDEXPancakeSwapV2()
        self.MyLogger = MyLogger(log_queue=log_queue)
        self.logger = self.MyLogger.configure_logger(fileloc=self.DataLoc.Log.ORDER_HANDLER.value)


    def handle(self):
        while True:
            # order = self.order_queue.get(block=True, timeout=3600)
            ### TEST CODE ###
            from order_class import OrderClass
            order = OrderClass().make_order(
                underlying='BNB',
                quote='USDT',
                order_type='limit',
                side='buy',
                asset='spot',
                quantity=0.00025,
                price=497.0,
                exchanges='cex'
            )
            ### TEST CODE ###
            print('*** THIS IS THE ORDER THAT WAS CREATED FOR THE TEST ***')
            print(order)
            exchanges = order['exchanges']
            if 'binance' in exchanges:
                self.CommsCEXBinance.place_order(order)
            elif 'pancakeswap' in exchanges:
                self.CommsDEXPancakeSwap.place_order(order)
            ### TEST CODE ###
            break
            ### TEST CODE ###


    def confirm_order_cex(self, blockchain_net: str):
        '''
        UPGRADE:
            - Maybe I should make this its own class... it will likely be on its own thread.
        '''
        CommsBlockchains = {
            'binance_smart_chain': CommsBlockchainBSC(blockchain_net=blockchain_net)
        }
        while True:
            ## Unpack Unconfirmed Transaction Data
            unconfirmed = self.queue_unconfirmed_dex_orders.get()
            order = unconfirmed['order']
            txn_hash = unconfirmed['txn_hash']
            blockchain_name = unconfirmed['blockchain_name']
            ## Get Transaction receipt
            try:
                txn_receipt = CommsBlockchains[blockchain_name].w3.eth.wait_for_transaction_receipt(
                    txn_hash,
                    timeout=timeout,
                    poll_latency=0.1  # default is 0.1 seconds
                )
            ## Place a New Order
            except TransactionNotFound:
                self.logger.info(f'Transaction is waiting in the mempool for too long; sending a new order. Old order: {order}')
                order.update({
                    'attempt_count': order['attempt_count'] + 1
                })
                self.queue_unplaced_orders.put(order)

            ## Log the successful Order Completion
            self.logger.info(f'DEX transaction added to blockchain: {txn_receipt} for order {order}.')



if __name__ == '__main__':
    OrderHandler(order_queue=queue.Queue()).handle()