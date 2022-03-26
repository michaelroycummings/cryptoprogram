## External Libraries
from typing import Union, List
import logging
import logging.handlers
import time
import ccxt
from functools import wraps
from enum import Enum
from pathlib import Path
import json
import os
import multiprocessing
from web3 import Web3



def catch_and_log_exception(function):  # cannot assign static or class method AND does not need self. This function works fine despite IDE error
    '''
    A decorator that catches and logs an exception before allow the exception to continue on.
    '''
    @wraps(function)
    def catch_and_log_exception_wrapper(self, *args, **kwargs):
        try:
            return function(self, *args, **kwargs)
        except Exception:
            self.logger.exception(f'Error found when running {function}.')
            raise
    return catch_and_log_exception_wrapper


def try5times(function):
    '''
    A retry decorator. Upon five failed attempts, returns the exception found on the fifth attempt at running the function.
    '''
    @wraps(function)
    def try5times_wrapper(self, *args, **kwargs):
        for repeat in range(5):
            try:
                return function(self, *args, **kwargs)
            except Exception:
                self.logger.exception(f'Error found when running {function}.')
                if repeat < 2:
                    time.sleep(0.5)
                elif repeat < 4:
                    time.sleep(2)
                else:  # repeat == 4 == 5th try
                    self.logger.critical(f'{function} failed to work after 5 attempts.')
                    raise
    return try5times_wrapper



class Folder(Enum):
    parent = Path(__file__).resolve().parents[1]
    SCRIPTS                 = os.path.join(parent, 'scripts')
    CONFIG                  = os.path.join(parent, 'config')
    DATA                    = os.path.join(parent, 'data')
    DATA_RECON_COIN_LISTING = os.path.join(parent, 'data', 'recon_coin_listing')
    DATA_TWEETS             = os.path.join(parent, 'data', 'tweets')
    DATA_DEX_PRICES         = os.path.join(parent, 'data', 'dex_prices')
    LOGS                    = os.path.join(parent, 'logs')
class File(Enum):
    CONFIG           = os.path.join(Folder.CONFIG.value, 'config.json')
    TOKEN_ADDRESS    = os.path.join(Folder.CONFIG.value, 'token_address.json')
    CONTRACT_ADDRESS = os.path.join(Folder.CONFIG.value, 'contract_address.json')
    ABI              = os.path.join(Folder.CONFIG.value, 'abi.json')
class Log(Enum):
    with open(File.CONFIG.value) as json_file:
        config = json.load(json_file)
    MY_LOGGER                = os.path.join(Folder.LOGS.value, config['MyLogger']['log_file_name'])
    ORDER_CLASS              = os.path.join(Folder.LOGS.value, config['OrderClass']['log_file_name'])
    ORDER_HANDLER            = os.path.join(Folder.LOGS.value, config['OrderHandler']['log_file_name'])
    COMMS_BLOCKCHAIN_BSC     = os.path.join(Folder.LOGS.value, config['CommsBlockchainBSC']['log_file_name'])
    COMMS_CEX_BINANCE        = os.path.join(Folder.LOGS.value, config['CommsCEXBinance']['log_file_name'])
    COMMS_DEX_UNISWAPV3      = os.path.join(Folder.LOGS.value, config['CommsDEXUniSwapV3']['log_file_name'])
    COMMS_DEX_UNISWAPV2      = os.path.join(Folder.LOGS.value, config['CommsDEXUniSwapV2']['log_file_name'])
    COMMS_DEX_PANCAKESWAPV2  = os.path.join(Folder.LOGS.value, config['CommsDEXPancakeSwapV2']['log_file_name'])
    COMMS_TWITTER            = os.path.join(Folder.LOGS.value, config['CommsTwitter']['log_file_name'])
    COMMS_BLOCKCHAIN_DATA_PROVIDERS = os.path.join(Folder.LOGS.value, config['CommsBlockchainDataProviders']['log_file_name'])
    STRAT_COIN_LISTING       = os.path.join(Folder.LOGS.value, config['StratCoinListing']['log_file_name'])
    RECON_COIN_LISTING       = os.path.join(Folder.LOGS.value, config['ReconCoinListing']['log_file_name'])
    RUN_RECON                = os.path.join(Folder.LOGS.value, config['RunRecon']['log_file_name'])
class DataLoc():
    '''
    Stores the absolute location of all folder, file, and log-file locations needed for this script.
    '''
    def __init__(self):
        self.Folder = Folder
        self.File = File
        self.Log = Log
        ## Make sure all Folders mentioned, Exist
        for folder_loc in Folder:
            os.makedirs(folder_loc.value, exist_ok=True)



class MyLogger():

    def __init__(self, log_queue: Union[multiprocessing.Queue, None] = None):
        self.log_queue = log_queue


    @staticmethod
    def maybe_configure_logger(fileloc: str, log_queue: Union[multiprocessing.Queue, None] = None):
        '''
        Parameters
        ----------
        fileloc : str
            The Path (in str format) that the log file will be saved to

        Future Additions
        ----------------
        Maybe put all logs into json file and use a Log Explorer: https://www.datadoghq.com/blog/python-logging-best-practices/
        Multiprocess logging without having to pass a log_queue to everything: https://stackoverflow.com/questions/60830938/python-multiprocessing-logging-via-queuehandler
        '''
        logger = logging.getLogger(fileloc)
        logger.setLevel(logging.DEBUG)
        ## Create and Add Handler to Logger
        # if class_name != '':
        #     if logger.hasHandlers():  # this stops the same log message from being added multiple and increasing number of times
        #         logger.handlers.clear()
        ## Create / add Queueing Handler
        if log_queue is not None:
            queueing_handler = logging.handlers.QueueHandler(log_queue)
            logger.addHandler(queueing_handler)
        ## Create / add File Handler
        file_handler = logging.FileHandler(fileloc)
        file_handler.setFormatter(logging.Formatter(f'%(asctime)s \t %(levelname)s \t %(filename)s - %(funcName)s: \t %(message)s', datefmt='%y-%m-%d %H:%M:%S'))
        logger.addHandler(file_handler)
        return logger


    def configure_logger(self, fileloc: str, add2self: bool = True):
        '''
        Parameters
        ----------
        fileloc : str
            The Path (in str format) that the log file will be saved to

        Future Additions
        ----------------
        Maybe put all logs into json file and use a Log Explorer: https://www.datadoghq.com/blog/python-logging-best-practices/
        Multiprocess logging without having to pass a log_queue to everything: https://stackoverflow.com/questions/60830938/python-multiprocessing-logging-via-queuehandler
        '''
        logger = logging.getLogger(fileloc)
        logger.setLevel(logging.DEBUG)
        ## Create and Add Handler to Logger
        # if class_name != '':
        #     if logger.hasHandlers():  # this stops the same log message from being added multiple and increasing number of times
        #         logger.handlers.clear()
        ## Create / add File Handler
        file_handler = logging.FileHandler(fileloc)
        file_handler.setFormatter(logging.Formatter(f'%(asctime)s \t %(levelname)s \t %(filename)s - %(funcName)s: \t %(message)s', datefmt='%y-%m-%d %H:%M:%S'))
        logger.addHandler(file_handler)
        if add2self is True:
            self.logger = logger
        return logger


    def activate_mp_logger(self):
        '''
        Run this method in the function that the child process calls. Aka if you make a new process for function X, make sure this method runs at the start of function X.
            - no logging will occur unless another process is made that ...
        '''
        h = logging.handlers.QueueHandler(self.log_queue)
        self.logger.addHandler(h)
        self.logger.setLevel(logging.DEBUG)
        return

    @staticmethod
    def configure_loggers_helper():
        '''
        This method MUST be called from the parent process that is calling all the other processes. Idk why.. just has to. Maybe because loggers cant be pickled or some shit.
        '''
        ## Only Get Loggers whose name has ".log" in it - a signature of my loggers
        return [logging.getLogger(name) for name in logging.root.manager.loggerDict if '.log' in name]


    def configure_all_loggers(self, my_loggers: List[logging.Logger]):
        '''
        Get the `my_loggers` parameter from self.configure_loggers_helper().
        '''
        ## Set Up all Loggers in the Process that will Log Everything
        for logger in my_loggers:
            self.configure_logger(fileloc=logger.name, add2self=False)
        return

    @catch_and_log_exception
    def log_all_mps(self, my_loggers):
        ## Log Process Started
        self.logger = self.configure_logger(DataLoc().Log.MY_LOGGER.value)
        self.logger.debug('Process Started.')
        ## Log from Other Processes
        self.configure_all_loggers(my_loggers)
        while True:
            record = self.log_queue.get(block=True)
            logger = logging.getLogger(record.name)
            logger.handle(record)
        return  # this process must be killed via process.kill()



class StoredAddressInfo():

    def __init__(self):
        pass

    @staticmethod
    def get_token_address(symbol:str, blockchain_name: str, blockchain_net: str, DataLoc: DataLoc):
        with open(DataLoc.File.TOKEN_ADDRESS.value) as json_file:
            token_addresses = json.load(json_file)
        try:
            address = token_addresses[blockchain_name][blockchain_net][symbol]
            address = Web3.toChecksumAddress(address)  # just in case
        except KeyError:
            address = None
        if address == '':
            address = None
        return address


    @staticmethod
    def get_token_from_address(contract_address: str, blockchain_net: str, DataLoc: DataLoc):
        checksum_address = Web3.toChecksumAddress(contract_address)
        with open(DataLoc.File.TOKEN_ADDRESS.value) as json_file:
            token_addresses = json.load(json_file)
        list_of_dicts = [d[blockchain_net] for d in token_addresses.values()]
        address_lookup_all_chains = {address: symbol for d in list_of_dicts for symbol, address in d.items()}
        try:
            symbol = address_lookup_all_chains[checksum_address]  # very, very, very unlikely that two blockchains have any coin occupying the same address string.
        except KeyError:
            symbol = None
        if symbol == '':
            symbol = None
        return symbol



def handle_ccxt_error(function):
    ''' Logs errors that the exchange returns '''
    @wraps(function)
    def handle_ccxt_error_wrapper(self, *args, **kwargs):
        count = 0
        while True:
            count += 1
            try:
                return function(self, *args, **kwargs)
            except ccxt.NetworkError as e:
                self.logger.exception(f'NetworkError when running function: {function}.')
                if count >= 5:
                    raise
                else:
                    time.sleep(0.25)
            except ccxt.ExchangeError as e:
                self.logger.exception(f'ExchangeError when running function: {function}.')
                raise
    return handle_ccxt_error_wrapper


def update_kill_signal(kill: bool, recon: bool, strat: bool):
    '''
    This function sets / resets the kill signal for all Recon and / or Strat scripts by
    changing the "kill_signal" variable in the config.json file to "kill_signal / an empty string.
    '''
    ## Check Input
    if isinstance(kill, bool) is False:
        print(f'Provide a "boolean value to the "kill" parameter. "True" to kill scripts, "False" to ensure scripts are not killed when run.')
    ## Script Names
    recon_scripts = ['ReconCoinListing']
    strat_scripts = ['StratCoinListing']
    ## Get Config File
    fileloc = DataLoc().File.CONFIG.value
    with open(fileloc) as f:
        old_config = json.load(f)
    new_config = old_config
    ## Update Config File
    if recon is True:
        print(f'Updating Recon kill signals to "{True}".')
        for script_name in recon_scripts:
            new_config[script_name]['kill_signal'] = True
    if strat is True:
        print(f'Updating Strat kill signals to "{True}".')
        for script_name in strat_scripts:
            new_config[script_name]['kill_signal'] = True
    ## Save Updated Config Data to File
    try:
        with open(fileloc, 'w') as json_file:
            json.dump(new_config, json_file)
        print('Successful update of config file.')
    except:  # do not let config file become erased due to error while saving to config file
        with open(fileloc, 'w') as json_file:
            json.dump(old_config, json_file)
        print('Failed update of config file, returning file to version before the update was attempted.')
    return
