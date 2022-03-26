## Internal Modules
from scripts.utils import DataLoc, MyLogger, StoredAddressInfo

## External Libraries
from typing import Union, List
import multiprocessing
import requests
import json
import re
from datetime import datetime
from web3 import Web3, contract


class CommsBlockchainDataProviders():
    '''
    Notes on APIs
    -------------
        1. Etherscan and BscScan are useless for finding contract address with symbol and vise versa
    '''

    def __init__(self, blockchain_net: str, log_queue: Union[multiprocessing.Queue, None] = None):
        '''
        Parameters
        ----------
        blockchain_net : str
            Can be 'mainnet', 'testnet'.
        '''
        self.DataLoc = DataLoc()
        with open(self.DataLoc.File.CONFIG.value) as json_file:
            config = json.load(json_file)['CommsBlockchainDataProviders']
        self.config = config
        ## Logger
        self.MyLogger = MyLogger(log_queue=log_queue)
        self.logger = self.MyLogger.configure_logger(fileloc=self.DataLoc.Log.COMMS_BLOCKCHAIN_DATA_PROVIDERS.value)
        ## Connections
        urls = config['urls']
        api_keys = config['api_keys']
        self.CoinMarketCap = CoinMarketCap(
            url=urls['coinmarketcap'],
            api_key=api_keys['coinmarketcap'],
            logger=self.logger
        )
        self.CoinGecko = CoinGecko(
            url=urls['coingecko'],
            logger=self.logger,
            config=config,
            blockchain_net=blockchain_net,
            DataLoc = self.DataLoc
        )
        self.BscScan = BscScan(url=urls['bscscan'][blockchain_net], api_key=api_keys['bscscan'], logger=self.logger)


    def create_name_formats(self, token_name: str):
        '''
        Data Providers will have different and possible changing naming formats for tokens,
        so this function takes a name and makes many different variations, so that this program
        can match a name to the data Provider's format.
        -
        E.g. 'basic attention token' vs 'basic_attention_token' vs 'basic-attention-token' vs 'Basic Attention Token'
        '''
        words_lower = [word.lower() for word in re.split(r'\s|-|_', token_name)]
        words_upper = [word.upper() for word in words_lower]
        words_capitalized = [word.capitalize() for word in words_lower]
        name_formats = []
        for words_list in [words_lower, words_upper, words_capitalized]:
            name_formats.extend([
                '_'.join(words_list),
                '-'.join(words_list),
                ' '.join(words_list)
            ])
        return name_formats


    def get_contract_address(self, symbol:str, token_name: Union[str, None], blockchain_name: str, blockchain_net: str, save: bool = True, override: bool = False):
        '''
        Parameters
        ----------
        symbol : str
            E.g. ETH
        token_name : str
            Name can have capitals, '-', or '_'. All this is parsed in self.create_name_formats().
            E.g. 'Ethereum'.
        blockchain_name : str
            Options: 'eth', 'bsc'
        blockchain_net:
            Options: 'mainnet'
        save : bool
            If True, saved the contract address found to the token addresses json file.
        override : bool
            If False, returns the saved contract address if one is available for this symbol and blockchain.
            Elif True, finds and uses the contract address provided by the blockchain data providers, even if one is already saved.
                     , and if save=True, saves over the current contract address if one exists.
        '''
        symbol = symbol.upper()

        ## Override or Not
        if override is False:
            saved_address = StoredAddressInfo.get_token_address(symbol=symbol, blockchain_name=blockchain_name, blockchain_net=blockchain_net, DataLoc=self.DataLoc)
            if saved_address is not None:  # this is important for removing '' and NoneType addresses from the token_addresses file
                return saved_address
            else:
                save = True

        ## Get name possibilities
        if token_name is None:
            name_formats = ['']
        else:
            name_formats = self.create_name_formats(token_name=token_name)
        suggested_addresses = []
        ## (1) Get Address - CoinMarketCap
        possible_address = self.CoinMarketCap.get_contract_address(symbol=symbol, name_formats=name_formats)
        suggested_addresses.append(possible_address)
        ## (2) Get Address - CoinGecko
        possible_address = self.CoinGecko.get_contract_address(symbol=symbol, blockchain_name=blockchain_name)
        suggested_addresses.append(possible_address)

        ## Ensure there is no consensus on the contract address
        if len(set(suggested_addresses)) == 1:
            contract_address = suggested_addresses[0]
            self.logger.debug(f'Contract address found; saving={save}, overriding saved address={override}. Blockchain name: {blockchain_name}. Blockchain net: {blockchain_net}. Symbol: {symbol}. Token name: {token_name}. Contract address: {contract_address}.')
        else:
            contract_address = None
            self.logger.debug(f'NO CONTRACT ADDRESS FOUND. Blockchain name: {blockchain_name}. Blockchain net: {blockchain_net}. Symbol: {symbol}. Token name: {token_name}. Suggested addresses: {suggested_addresses}.')

        ## Save or Not
        if save is True:
            with open(self.DataLoc.File.TOKEN_ADDRESS.value) as json_file:
                token_addresses = json.load(json_file)
            token_addresses[blockchain_name][blockchain_net][symbol] = contract_address
            with open(self.DataLoc.File.TOKEN_ADDRESS.value, 'w', encoding='utf-8') as json_file:
                json.dump(token_addresses, json_file, ensure_ascii=False, indent=4)
        return contract_address


    # def onetime_get_all_layer2_addresses(self):
    #     '''
    #     Get all layer 2 token addresses from Eth, Bsc chains and save in a pickle file.

    #     Data Sources
    #     ------------
    #     Ethereum addresses:
    #         TrustWallet's github file: @
    #     Binance Smart Chain addresses:
    #         Binance's Smart Chain API: @https://docs.binance.org/smart-chain/guides/bsc-intro.html
    #     '''
    #     ## Get Ethereum Blockchain Addresses
    #     url_eth = 'https://raw.githubusercontent.com/trustwallet/assets/blob/master/blockchains/ethereum/tokenlist.json'
    #     response = requests.get(url_eth)
    #     data = json.loads(response.text)
    #     addresses_eth = {d['symbol']: {
    #         'name': d['name'],
    #         'address': d['address'],
    #     } for d in data}
    #     ## Get Binance Smart Chain Addresses
    #     addresses_bsc = {}  # honestly not sure... no one seems to care about this
    #     ## Stamp Data with source info and save the file
    #     output_dict = {
    #         'storage_info': {
    #             'eth': {
    #                 'mainnet': {
    #                     'data_source_name': "A list of addresses in a json file from TrustWallet's GitHub",
    #                     'data_source_url': url_eth,
    #                 }
    #             },
    #             'bsc': {
    #                 'mainnet': {},
    #             },
    #         },
    #         'addresses': {
    #             'eth': {
    #                 'mainnet': addresses_eth,
    #             },
    #             'bsc': {
    #                 'mainnet': addresses_bsc,
    #             }
    #         }
    #     }
    #     with open('token_addresses_unchecked.pkl', 'wb') as fp:
    #         pickle.dump(output_dict, fp, protocol=pickle.HIGHEST_PROTOCOL)
    #     ## Check Addresses
    #     self.check_all_addresses(input_filename='token_addresses_unchecked.pkl', output_filename='token_addresses.pkl')
    #     return


    # def check_all_addresses(self, input_filename='token_addresses_unchecked.pkl', output_filename='token_addresses.pkl'):
    #     with open(input_filename, 'rb') as fp:
    #         data = pickle.load(fp)
    #         for blockchain_name in data['addresses']:
    #             for blockchain_net in blockchain_name:
    #                 for symbol, d in blockchain_net:
    #                     token_name = d['name']
    #                     token_address = data['address']
    #                     suggested_address = self.get_contract_address(symbol=symbol, token_name=token_name)
    #                     if token_address != suggested_address:
    #                         self.logger.critical(f'Chainging contract address for {symbol} on {blockchain_name}-{blockchain_net}. Old address: {token_address}. New address: {suggested_address}.')
    #                         data[blockchain_name][blockchain_net][symbol] = suggested_address
    #                     else:
    #                         pass  # stored contract address matches what sources are saying.


    # def download_all_token_addresses(self, blockchain_token: str, blockchain_net: str, output_file: str):
    #     '''
    #     Parameters
    #     ----------
    #     blockchain_token : str
    #         Options: 'eth', 'bsc'
    #     blockchain_net:
    #         Options: 'mainnet'
    #     output_file : str
    #         -
    #     '''
    #     if blockchain_token == 'eth' and blockchain_net == 'mainnet':
    #         pass
    #     return



class CoinMarketCap():
    '''
    Links to Endpoints
    ------------------
        https://coinmarketcap.com/api/documentation/v1/#operation/getV1CryptocurrencyMap
    '''

    def __init__(self, url: str, api_key: str, logger):
        ## Url's
        self.logger = logger
        self.url = url  # pro is free
        self.api_key = api_key


    def parse_address_from_response(self, list_of_dicts: List, symbol: str, name_formats: Union[List, None] = None):
        if name_formats is not None:
            parsed_once = [d['platform'] for d in list_of_dicts if ((d['symbol'] == symbol) and (d['slug'] in name_formats or d['name'] in name_formats))]
        else:
            parsed_once = [d['platform'] for d in list_of_dicts if d['symbol'] == symbol]
        possible_address = [d['token_address'] for d in parsed_once if isinstance(d, dict)]
        return possible_address


    # @try5times
    def get_contract_address(self, symbol: str, name_formats: List):
        ## Clean Inputs
        symbol = symbol.upper()

        ## Get Symbol Data
        url = f'{self.url}/v1/cryptocurrency/map'
        payload = {'symbol': symbol, 'CMC_PRO_API_KEY':self.api_key}
        response = requests.get(url, params=payload).json()
        self.logger.debug
        data = response['data']

        ## If one token returned, get contract address of the one token returned
        if len(data) == 1:
            possible_address = data[0]['platform']['token_address']
        ## Otherwise, mutiple tokens are returned, so try to find the correct one
        else:
            ## Try 1: match by token name + double check symbol
            possible_address = self.parse_address_from_response(list_of_dicts=data, symbol=symbol, name_formats=name_formats)
            if len(possible_address) == 1:
                possible_address = possible_address[0]
            else:
                ## Try 2: just grab the first one
                possible_address = self.parse_address_from_response(list_of_dicts=data, symbol=symbol, name_formats=None)  # just grab the first one... what else can I do
                possible_address = possible_address[0]
        possible_address = Web3.toChecksumAddress(possible_address)
        return possible_address



class CoinGecko():
    '''
    Links to Endpoints
    ------------------
        https://www.coingecko.com/api/documentations/v3#/contract/get_coins__id__contract__contract_address_
    '''

    def __init__(self, url: str, logger, config: dict, blockchain_net: str, DataLoc):
        ## Url's
        self.logger = logger
        self.url = url
        self.config = config
        self.blockchain_net = blockchain_net
        self.DataLoc = DataLoc
        self.exchange_name_converter = {
            'Binance': 'binance',
            'PancakeSwap (v2)': 'pancakeswapv2',
            'Uniswap (v2)': 'uniswapv2',
            'Uniswap (v3)': 'uniswapv3',
        }

    # @try5times
    def get_id(self, symbol: str):
        url = f'{self.url}/coins/list'
        response = requests.get(url).json()
        for token_d in response:
            if token_d['symbol'] == symbol:
                return token_d['id']

    # @try5times
    def get_contract_address(self, symbol: str, blockchain_name: str):
        ## Get CoinGecko ID
        id = self.get_id(symbol=symbol.lower())
        ## Get Symbol Data
        url = f'{self.url}/coins/{id}'
        payload = {
            'id': id,
            'tickers': False,
            'market_data': False,
            'community_data': False,
            'developer_data': False,
            'sparkline': False
        }
        response = requests.get(url, params=payload).json()
        ## Get Blockchain Name that CoinGecko Recognises
        convert = self.config['blockchain_name_conversion']['coingecko']
        try:
            coingecko_blockchain_name = convert[blockchain_name]
        except KeyError:
            error = f'Config file does not have coingecko blockchain name conversion for the blockchain "{blockchain_name}". File: {self.DataLoc.File.CONFIG.value}. Indexing: ["CommsBlockchainDataProviders"]["blockchain_name_conversion"]["coingecko"]["{blockchain_name}"].'
            self.logger.critical(error)
            raise Exception(error)
        possible_address = response['platforms'][coingecko_blockchain_name]
        possible_address = Web3.toChecksumAddress(possible_address)
        return possible_address


    def func_parse_exchange_details(self, symbol: str, d: dict):
        ''' Used by endpoint f'{self.url}/coins/{id}' via self.get_exchanges_listing_coin() '''
        try:
            unparsed_exchange_name = d['market']['name']
        except:
            self.logger.exception(f'CoinGecko is ass and is missing the exchange name in its exchange data for symbol "{symbol}". Exchange data: {d}.')
            return None
        try:
            exchange_name = self.exchange_name_converter[unparsed_exchange_name]
        except KeyError:
            self.logger.info(f'No functionality for exchange "{d["market"]["name"]}", which hosts symbol "{symbol}", which is experiencing a new coin listing.')
            return None
        underlying_asset = d['base']
        if len(underlying_asset) > 8:  # hopefully no blockchain has addresses under 8 characters...
            possibly_symbol = StoredAddressInfo.get_token_from_address(contract_address=underlying_asset, blockchain_net=self.blockchain_net, DataLoc=self.DataLoc)
            if possibly_symbol is not None:
                underlying_asset = possibly_symbol
        quote_asset = d['target']
        if len(quote_asset) > 8:
            quote_asset = StoredAddressInfo.get_token_from_address(contract_address=quote_asset, blockchain_net=self.blockchain_net, DataLoc=self.DataLoc)
            if possibly_symbol is not None:
                quote_asset = possibly_symbol
        try:
            exchange_data = {
                'exchange_name': exchange_name,
                'underlying': underlying_asset,
                'quote': quote_asset,
                'volume_in_coin': d['volume'],
                'volume_in_usd': d['converted_volume']['usd'],
                'trust_score': d['trust_score'],
                'bid_ask_spread_percentage': d['bid_ask_spread_percentage'],
                'last_traded_at': d['last_traded_at'],
                'last_fetch_at': d['last_fetch_at'],
            }
            return exchange_data
        except KeyError:
            self.logger.exception(f'CoinGecko is ass and is missing data for exchange "{exchange_name}". Exchange data: {d}.')
            return None


    def get_exchanges_listing_coin(self, symbol: str):
        ## Get CoinGecko ID
        id = self.get_id(symbol=symbol.lower())
        ## Get Symbol Data
        url = f'{self.url}/coins/{id}'
        payload = {
            'id': id,
            'tickers': False,
            'market_data': False,
            'community_data': False,
            'developer_data': False,
            'sparkline': False
        }
        response = requests.get(url, params=payload).json()
        exchanges_listing_coin = [self.func_parse_exchange_details(symbol=symbol, d=d) for d in response['tickers']]
        exchanges_listing_coin = [d for d in exchanges_listing_coin if d is not None]
        return {'data': exchanges_listing_coin, 'datetime': datetime.utcnow()}


class BscScan:
    def __init__(self, url: str, logger, api_key: str):
        ## Url's
        self.logger = logger
        self.url = url
        self.api_key = api_key


    def get_abi(self, contract_address: str) -> str:
        payload = {
            'module': 'contract',
            'action': 'getabi',
            'address': contract_address,
            'apikey': self.api_key,
        }
        response = requests.get(self.url, params=payload).json()
        return response['result']


    def get_block_id_by_datetime(self, dt: datetime, closest: str):
        '''
        Returns the block id.

        Parameters
        ----------
        closest : str
            Can be 'before', 'after'
        '''
        if closest not in ['before', 'after']:
            error = f'The "closest" argument must be given one of ["before", "after"]. Was given "{closest}" instead. Type {type(closest)}.'
            self.logger.critical(error)
            raise Exception(error)
        payload = {
            'module': 'block',
            'action': 'getblocknobytime',
            'timestamp': round(dt.timestamp()),
            'closest': closest,
            'apikey': self.api_key,
        }
        response = requests.get(self.url, params=payload).json()
        return int(response['result'])




if __name__ == '__main__':
    # CommsBlockchainDataProviders(blockchain_net='mainnet').get_contract_address(symbol='MBOX', token_name='mobox', blockchain_name='eth', blockchain_net='main')

    # x = CommsBlockchainDataProviders(blockchain_net='mainnet').CoinMarketCap.get_contract_address(symbol='MBOX', name_formats=[])
    y = CommsBlockchainDataProviders(blockchain_net='mainnet').CoinGecko.get_exchanges_listing_coin(symbol='MBOX')

    # ## Testing
    # a = CommsBlockchainDataProviders(blockchain_net='mainnet'
    #     ).create_name_formats(token_name='thE-basIC Attention_Token')
    # b = CoinMarketCap(url="https://pro-api.coinmarketcap.com", api_key="ec677cc5-e6c9-4144-8787-78e3c0334485", logger=CommsBlockchainDataProviders().logger
    #     ).get_contract_address(symbol='bat', name_formats=CommsBlockchainDataProviders().create_name_formats(token_name='basIC Attention_Token'))
    # c = CoinGecko(url="https://api.coingecko.com/api/v3", logger=CommsBlockchainDataProviders().logger
    #     ).get_contract_address(symbol='bat')
    # d = CommsBlockchainDataProviders(
    #     ).get_contract_address(symbol='bat', token_name='basIC Attention_Token')
