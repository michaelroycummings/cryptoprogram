## Internal Modules
from scripts.utils import DataLoc, MyLogger, catch_and_log_exception
from scripts.comms_twitter import CommsTwitter
from scripts.comms_dex_pancakeswapv2 import CommsDEXPancakeSwapV2
from scripts.comms_blockchain_data_providers import CommsBlockchainDataProviders

## External Libraries
from logging import log
from typing import Union
import json
import queue
import re
import multiprocessing


class StratCoinListing():
    def __init__(self, log_queue: Union[multiprocessing.Queue, None] = multiprocessing.Queue()):
        '''
        Parameters
        ----------
        mp : bool
            If any instances of this class will be in a child process, a multiprocessing.Queue() object should be passed to this argument.
            Else, pass NoneType.
        '''
        self.class_name = 'ReconCoinListing'
        self.user_handle = 'binance'
        self.DataLoc = DataLoc()
        with open(self.DataLoc.File.CONFIG.value) as json_file:
            config = json.load(json_file)[self.class_name]
        self.CommsTwitter = CommsTwitter(log_queue=log_queue)
        self.CommsBlockchainDataProviders = CommsBlockchainDataProviders(blockchain_net='mainnet', log_queue=log_queue)
        self.MyLogger = MyLogger(log_queue=log_queue)
        self.logger = self.MyLogger.configure_logger(fileloc=self.DataLoc.Log.STRAT_COIN_LISTING.value)


    def is_tweet_new_listing(self, text):
        match = re.search('Binance will list .*?\((\w*?)\)', text)  # .*? is any character; \( is an open parentheses; (\w*?) is in another set of parentheses to group it seperately; \) is a close parentheses
        if match is not None:
            symbol = match.group(1)
        else:
            symbol = None
        return symbol

    @catch_and_log_exception
    def listen_for_new_listing(self, formatted_tweet_queue: multiprocessing.Queue, new_listing_queue: multiprocessing.Queue):
        self.MyLogger.activate_mp_logger()
        self.logger.debug('Process started.')
        while True:
            try:
                formatted_tweet = formatted_tweet_queue.get(block=True, timeout=5)
                ## Check for Kill Signal
                if formatted_tweet == 'kill_signal':
                    self.logger.info('Kill signal received, terminating process.')
                    break
                ## Look for New Listing Info in Tweet Text
                formatted_tweet = list(formatted_tweet.values())[0]
                genesis_text = formatted_tweet['genesis']['text']  # the text of genesis (account holder's) tweet
                symbol = self.is_tweet_new_listing(text=genesis_text)
                if symbol is not None:
                    self.logger.info(f'New listing found for symbol "{symbol}".')
                    new_listing_queue.put(symbol)
            except queue.Empty:
                pass
        return



    def run_strat(self, tweet_queue: multiprocessing.Queue, order_queue: multiprocessing.Queue):
        self.logger.debug('Strategy started.')
        while True:
            ## Get Tweet
            try:
                tweet = tweet_queue.get(block=True, timeout=3600)
            except queue.Empty:
                self.logger.debug(f'Found no {self.user_handle} tweet for 3600 seconds...')
            ## Parse Tweet
            symbol = self.is_tweet_new_listing(text=tweet)
            ## Send Order
            if symbol is not None:
                order_queue.put(
                    self.make_order(
                        underlying=symbol,
                        quote='usdt',
                        order_type='market',
                        side='buy',
                        asset='spot',
                        quantity=0.00001234,
                        price=0,
                        exchanges='cex'
                    )
                )
            ## Check for Exit Signal
            elif tweet == 'exit signal code: 8m3hxg087mg4hc58g4c5ehc5g34o34':
                return
            pass  ## queue.get(block=True) alleviates need for time.sleep() argument; we want every queued tweet to be processed asap