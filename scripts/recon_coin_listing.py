## Internal Modules
from scripts.comms_dex_pancakeswapv2 import CommsDEXPancakeSwapV2
from scripts.strat_coin_listing import StratCoinListing
from scripts.utils import catch_and_log_exception

## External Libraries
from typing import Union
import multiprocessing
import queue  # for Exception: queue.Empty
import time
import json
import pickle
import time
import numpy as np
from datetime import datetime, timedelta


class ReconCoinListing(StratCoinListing):
    '''
    A ReconClass is a subclass of the StrategyClass, and is used to:
        - collect data related to the strategy's execution
        - paper trade or perform other strategy testing calculations
    for the Strategy that the class does recon for.
    '''

    def __init__(self, log_queue: Union[multiprocessing.Queue, None] = multiprocessing.Queue()):
        super().__init__(log_queue=log_queue)
        self.run_strat = None  # disable trading via recon class
        with open(self.DataLoc.File.CONFIG.value) as json_file:
            config = json.load(json_file)[self.__class__.__name__]
        self.logger_strat_coin_listing = self.logger  # sometimes logging to the strategy class makes more sense
        self.logger = self.MyLogger.configure_logger(fileloc=self.DataLoc.Log.RECON_COIN_LISTING.value)


    def save_exchange_data(self, symbol: str, exchanges_listing_coin: dict, datetime_pulled: datetime):
        ''' Records the CEXs and DEXs listing a symbol at a given datetime. '''
        str_datetime = datetime_pulled.strftime('%Y-%m-%d-%H-%M-%S')
        file_name = f'exchange_data_{symbol}_{str_datetime}.pkl'
        file_loc = f'{self.DataLoc.Folder.DATA_RECON_COIN_LISTING.value}/{file_name}'
        output_data = {
            'data': exchanges_listing_coin,
            'datetime': datetime_pulled
        }
        with open(file_loc, 'wb') as pfile:
            pickle.dump(output_data, pfile, protocol=pickle.HIGHEST_PROTOCOL)


    def save_downloaded_price_data(self, output_data: dict, exchange_name: str, start_dt: datetime, end_dt: datetime, symbol_1: str, symbol_2: str, add_to_existing: bool = True):
        '''
        Records price data for an exchange and spot trading pair for a small length of time
        before and after the underlying asset has been newly listed on an exchange.
        '''
        start_strf = start_dt.strftime("%Y-%m-%d-%H-%M-%S")
        end_strf = end_dt.strftime("%Y-%m-%d-%H-%M-%S")
        file_name = f'{exchange_name}_{symbol_1}_{symbol_2}_{start_strf}_{end_strf}.pkl'
        file_loc = f'{self.DataLoc.Folder.DATA_RECON_COIN_LISTING.value}/{file_name}'

        ## Add Existing Data
        if add_to_existing is True:
            try:
                with open(file_loc, 'rb') as handle:
                    saved_data = pickle.load(handle)
                output_data.update(saved_data)
            except EOFError:  # empty file
                pass
            except FileNotFoundError:
                pass

        ## Save New and Existing Data
        with open(file_loc, 'wb') as pfile:
            pickle.dump(output_data, pfile, protocol=pickle.HIGHEST_PROTOCOL)


    def grab_price_data_pancakeswapv2(self, exchange_name: str, exchange_data: dict):
        '''
        Queries price data for PancakeswapV2 for a spot trading pair, for 4 hours before
        and 4 hours after the underlying asset has been newly listed on an exchange,
        and while waiting to query more data, periodically saves the queried data.
        '''
        self.MyLogger.activate_mp_logger()
        global CommsDEXPancakeSwapV2
        CommsDEXPancakeSwapV2 = CommsDEXPancakeSwapV2(blockchain_net='mainnet')
        symbol_underlying = exchange_data['underlying']
        symbol_quote = exchange_data['quote']
        now = datetime.utcnow()
        now_block = CommsDEXPancakeSwapV2.get_latest_block_number()

        ## Start and End of Data Pull
        start_dt = now - timedelta(seconds=(4800 * CommsDEXPancakeSwapV2.average_block_seconds))
        end_dt = now + timedelta(seconds=(4 * 60 * 60))

        ## Start ad End Blocks of Data Pull
        start_block = int(np.floor(now_block - 4800))  # query 4800 blocks; can query a max of 5000 blocks back from binance-provided node
        end_block = int(np.ceil(now_block  + (4 * 60 * 60 / CommsDEXPancakeSwapV2.average_block_seconds)))  # 4 hours of data after event
        query_period_in_blocks = 1000  # query data every 1000 blocks

        self.logger.debug(f'Downloading price data from PancakeSwapV2 for symbol "{symbol_underlying}/{symbol_quote}" between start "{start_dt}" and end "{end_dt}".')

        ## Grab Data at Specific Intervals, then sleep
        sub_end_block = start_block - 1
        for sub_start_block in range(start_block, end_block, query_period_in_blocks):
            sub_end_block = sub_start_block + query_period_in_blocks

            while True:
                ## Download Data
                latest_block = CommsDEXPancakeSwapV2.get_latest_block_number()
                if sub_end_block <= latest_block:
                    output_data = CommsDEXPancakeSwapV2.get_historical_trades(symbol_1=symbol_underlying, symbol_2=symbol_quote, start_block=sub_start_block, end_block=sub_end_block)
                    break
                ## If sub_end_block isn't ready yet, sleep for the estimated time needed to get to sub_end_block
                else:
                    time.sleep(abs(sub_end_block - latest_block) * CommsDEXPancakeSwapV2.average_block_seconds)

            ## Save Price Data in case program crashes or something
            self.save_downloaded_price_data(
                output_data=output_data, exchange_name=exchange_name,
                start_dt=start_dt, end_dt=end_dt,
                symbol_1=exchange_data['underlying'], symbol_2=exchange_data['quote'],
                add_to_existing=True
            )
            ## Sleep for query_period_in_blocks number of blocks
            time.sleep(query_period_in_blocks * CommsDEXPancakeSwapV2.average_block_seconds)
        return


    @catch_and_log_exception
    def grab_price_data_all_exchanges(self, new_listing_queue: multiprocessing.Queue):
        '''
        Queries a queue of symbols that are newly listed, finds all exchanges and pairs on each exchange
        that exist for the symbol, then make a new process to download price data, for each pair on each
        exchange.

        UPGRADE
        -------
         - Currently, only PancakeswapV2 has a dedicated function to query the necessary data.
        '''
        self.MyLogger.activate_mp_logger()
        self.logger.debug('Process started.')
        process_target_index = {
            'pancakeswapv2': self.grab_price_data_pancakeswapv2,
            # 'uniswapv2':
            # 'uniswapv3':
            # 'binance':
        }
        while True:
            try:
                new_listing_symbol = new_listing_queue.get(block=True, timeout=5)
                ## Check for Kill Signal
                if new_listing_symbol == 'kill_signal':
                    self.logger.info('Kill signal received, terminating process.')
                    break

                ## Find exchanges that list coin before new listing
                output = self.CommsBlockchainDataProviders.CoinGecko.get_exchanges_listing_coin(symbol=new_listing_symbol)
                exchanges_listing_coin = output['data']
                exchange_data_datetime = output['datetime']
                self.logger.info(f'Exchanges found to host trading for the new coin listing "{new_listing_symbol}" grabbed at "{exchange_data_datetime}"". Exchanges: {[exchange_data["exchange_name"] for exchange_data in exchanges_listing_coin]}.')

                ## Save List of Exchanges currently listing the Newly Listed Symbol
                self.save_exchange_data(symbol=new_listing_symbol, exchanges_listing_coin=exchanges_listing_coin, datetime_pulled=exchange_data_datetime)

                ## Download Price Data from all Exchanges listing the Symbol
                processes = {}
                for exchange_data in exchanges_listing_coin:
                    exchange_name = exchange_data['exchange_name']
                    symbol_underlying = exchange_data['underlying']
                    symbol_quote = exchange_data['quote']
                    process_name = f'p_data_downloader_{exchange_name}_{symbol_underlying}_v_{symbol_quote}'
                    process_target = process_target_index.get(exchange_name, None)
                    if process_target is not None:
                        process_object = multiprocessing.Process(
                            name=process_name,
                            target=process_target,
                            kwargs={'exchange_name': exchange_name, 'exchange_data': exchange_data}
                        )
                        processes.update({process_name: process_object})
                for process_name, process_object in processes.items():
                    process_object.start()
                for process_name, process_object in processes.items():
                    process_object.join()
            except queue.Empty:
                pass  # queue.get() already waits 5 seconds
        return


    def run(self):
        '''
        Runs Recon on the CoinListing Strategy by launching three multiprocesses:
            - p_tweet_stream_and_formatter:
                Uses the CommsTwitter class to listen for news of new coin listings,
                and adds these tweets to a multiprocessing queue.
                The listings are usually announced on twitter 6+ hours before they are actually listed on the exchange.
            - p_listing_parser:
                Takes raw tweet text from a multiprocessing queue, decides if text
                mentions a new coin listing, and if so, adds the symbol to another
                multiprocessing queue.
            - p_data_downloader:
                Takes symbols from a multiprocessing queue and queries and saves
                price data for that symbol as well as a list of all exchanges
                that currently list that symbol.
        '''
        ## Start Multiprocessing Logger
        p_mp_logger = multiprocessing.Process(
            name='p_mp_logger',
            target=self.MyLogger.log_all_mps,
            kwargs={'my_loggers':self.MyLogger.configure_loggers_helper()}
        )
        p_mp_logger.start()
        self.logger.debug('Recon started.')

        kill_queue = multiprocessing.Queue()
        formatted_tweet_queue = multiprocessing.Queue()
        new_listing_queue = multiprocessing.Queue()

        ## Stream Tweets
        p_tweet_stream_and_formatter = multiprocessing.Process(
            name='p_tweet_stream_and_formatter',
            target=self.CommsTwitter.download_tweets_stream,
            kwargs={
                'query_name': 'new_coin_listing',
                'kill_queue': kill_queue,
                'formatted_tweet_queue': formatted_tweet_queue,
                'save': False,
            }
        )  # listens for tweets from twitter's API, formats them, and adds them to the formatted_tweet_queue to be analysed for new coin listing info
        ## Look for New Listings in Tweets
        p_listing_parser = multiprocessing.Process(
            name='p_listing_parser',
            target=self.listen_for_new_listing,
            kwargs={
                'formatted_tweet_queue': formatted_tweet_queue,
                'new_listing_queue': new_listing_queue,
            }
        )
        ## Download Market Data for Pairs containing the New Listing Coin
        p_data_downloader = multiprocessing.Process(
            name='p_data_downloader',
            target=self.grab_price_data_all_exchanges,
            kwargs={
                'new_listing_queue': new_listing_queue,
            }
        )

        ## Start Processes
        p_tweet_stream_and_formatter.start()
        p_listing_parser.start()
        p_data_downloader.start()

        ## Check for Kill Signal
        while True:
            with open(self.DataLoc.File.CONFIG.value) as f:
                kill_signal = json.load(f)[self.__class__.__name__]['kill_signal']
            if kill_signal is True:
                self.logger.info('Kill signal found, closing child processes.')
                kill_signal = 'kill_signal'

                ## Send Kill Signal to Processes
                kill_queue.put(kill_signal)              # kills p_tweet_stream_and_formatter
                formatted_tweet_queue.put(kill_signal)   # kills p_listing_parser
                new_listing_queue.put(kill_signal)       # kills p_data_downloader

                ## Wait for Processes to Terminate
                p_tweet_stream_and_formatter.join()
                p_listing_parser.join()
                p_data_downloader.join()
                p_mp_logger.kill()

                ## Stop Checking for Kill Signal
                break
            else:
                time.sleep(5)
        self.logger.info('All child processes are closed, ending recon.')
        return


if __name__ == '__main__':
    ReconCoinListing().run()
