## Internal Modules
from scripts.utils import DataLoc, MyLogger, StoredAddressInfo
from scripts.comms_blockchain_data_providers import CommsBlockchainDataProviders

## External Libraries
from typing import Union
import json
from datetime import datetime
from web3 import Web3, middleware
from web3.middleware import geth_poa_middleware
from web3.gas_strategies.time_based import fast_gas_price_strategy, medium_gas_price_strategy


class CommsBlockchainBSC():
    '''
    Methods
    -------
    connect
    set_contract_objects
    to_dex_number
    from_dex_number
    get_nonce
    set_gas_price_strategy
    get_latest_block_number
    get_block_by_datetime
    get_token_address
    swap_wbnb
    _parse_log_attribute_dict
    parse_transaction_receipt

    Attributes
    ----------
    self.DataLoc
    self.CommsBlockchainDataProviders
    self.logger
    self.blockchain_name
    self.blockchain_net
    self.average_block_seconds
    self.nodes
    self.address_wallet
    self.private_key (lol)
    self.w3  (the object to communicate with the blockchain)
    self.address_wbnb
    self.contract_wbnb

    Blockchain Docs
    ---------------
    https://cryptomarketpool.com/resources-for-the-binance-smart-chain/
    https://testnet.bscscan.com/tokentxns

    Blockchain Nodes
    ----------------
    https://docs.binance.org/smart-chain/developer/rpc.html
    https://moralis.io/

    '''

    def __init__(self, blockchain_net: str):
        self.DataLoc = DataLoc()
        self.logger = MyLogger().configure_logger(fileloc=self.DataLoc.Log.COMMS_BLOCKCHAIN_BSC.value)

        ## Clean Input
        if blockchain_net not in ['mainnet', 'testnet']:
            error = f'Instance started with incorrect "blockchain_net" argument: {blockchain_net}. Type: {type(blockchain_net)}.'
            self.logger.critical(error)
            raise Exception(error)
        self.blockchain_name = 'binance_smart_chain'
        self.blockchain_net = blockchain_net  # mainnet or testnet

        ## Open and Apply Config Data
        with open(self.DataLoc.File.CONFIG.value) as json_file:
            config = json.load(json_file)['CommsBlockchainBSC']
            self.average_block_seconds = config['average_block_seconds']
            self.nodes = config['nodes'][self.blockchain_net]
        with open(self.DataLoc.File.TOKEN_ADDRESS.value) as json_file:
            self.token_addresses = json.load(json_file)[self.blockchain_name][self.blockchain_net]
        ## FIXME: This needs to be way safer...
        with open(f'{self.DataLoc.Folder.CONFIG.value}/wallets.json') as json_file:
            keys = json.load(json_file)[self.blockchain_name][self.blockchain_net]['trading']
            self.address_wallet = keys['public_key']
            self.private_key = keys['private_key']

        ## Comms Objects
        self.CommsBlockchainDataProviders = CommsBlockchainDataProviders(blockchain_net=blockchain_net)

        ## Connect to Blockchain
        self.w3 = self.connect()
        self.set_contract_objects()
        ''' Sets the following instance attributes:
            self.address_wbnb
            self.contract_wbnb
        '''
        self.loaded_abis = {}
        return


    def connect(self):
        ## Connect to Blockchain
        for node in self.nodes:
            w3 = Web3(Web3.HTTPProvider(node))
            is_connected = w3.isConnected()
            if is_connected is True:
                self.logger.debug(f'Connected to {self.blockchain_name} - {self.blockchain_net}. Node: {node}.')
                ## Inject-geth is needed for middleware onion shit to work on POA blockchains like Binance Smart Chain
                w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                break
            else:
                error = f'Could not connect to {self.blockchain_name} - {self.blockchain_net}. Node: {node}. Status: {is_connected}. Type: {type(is_connected)}.'
                self.logger.debug(error)
        if not is_connected:
            error = f'Binance nodes exhausted. Unable to connect to all nodes... fuck. {self.blockchain_name} - {self.blockchain_net}.'
            self.logger.debug(error)
            raise Exception(error)  # sys.exit()
        return w3


    def set_contract_objects(self):
        '''
        Sets address and contract instance attributes to communicate with contracts on the Binance Smart Chain.
        '''
        with open(self.DataLoc.File.CONTRACT_ADDRESS.value) as json_file:
            addresses = json.load(json_file)[self.blockchain_name][self.blockchain_net]
        with open(self.DataLoc.File.ABI.value) as json_file:
            abis = json.load(json_file)[self.blockchain_name]['mainnet']  # testnet abi's are hopefully the same
        ## Create WBNB Contract Object
        address_wbnb = Web3.toChecksumAddress(addresses['wbnb'])
        abi_wbnb = abis[address_wbnb]
        contract_wbnb = self.w3.eth.contract(address=address_wbnb, abi=abi_wbnb)
        ## Set Instance Attributes
        self.address_wbnb = address_wbnb
        self.contract_wbnb = contract_wbnb
        return


    @staticmethod
    def to_dex_number(number: float, decimals: int) -> int:
        return int(round(number, (decimals-1)) * (10 ** decimals))


    @staticmethod
    def from_dex_number(number: float, decimals: int) -> int:
        return number / (10 ** decimals)


    def get_nonce(self):
        return self.w3.eth.get_transaction_count(self.address_wallet)


    def set_gas_price_strategy(self, strategy_name: str):
        ''' Meant to be called only by self.get_gas_price() '''
        ## Set Gas Price Calculator
        if strategy_name == 'premade_fast':
            self.w3.eth.set_gas_price_strategy(fast_gas_price_strategy)
        elif strategy_name == 'premade_medium':
            self.w3.eth.set_gas_price_strategy(medium_gas_price_strategy)
        ## Make calculation less resource intensive (I think)
        if strategy_name in ['premade_fast', 'premade_medium']:
            ## Reason for below 3 middleware lines of code: Due to the overhead of sampling the recent blocks it is recommended that a caching solution be used to reduce the amount of chain data that needs to be re-fetched for each request.
            self.w3.middleware_onion.add(middleware.time_based_cache_middleware)
            self.w3.middleware_onion.add(middleware.latest_block_based_cache_middleware)
            self.w3.middleware_onion.add(middleware.simple_cache_middleware)
        return self


    def get_gas_price(self, strategy_name: str, multiplier: Union[float, None] = None):
        '''
        Attributes
        ----------
        multiplier : str
            As a percentage. E.g. 0.1 means a 10% increase on the current gas price.
        '''
        if strategy_name == 'simple':
            gas_price = int(self.w3.eth.gasPrice * (1 + multiplier))
        elif strategy_name == 'premade_fast':
            gas_price = self.w3.eth.generate_gas_price()
            if gas_price is None:
                self.set_gas_price_strategy(strategy_name=strategy_name)
        return gas_price


    def get_latest_block_number(self):
        return self.w3.eth.block_number


    def get_block_by_datetime(self, dt: datetime, closest: str):
        '''
        Parameters
        ----------
        closest : str
            Can be 'before', 'after'
        '''
        block_id = self.CommsBlockchainDataProviders.BscScan.get_block_id_by_datetime(dt=dt, closest=closest)
        return self.w3.eth.get_block(block_id, full_transactions=False)


    def get_token_address(self, symbol:str, token_name: Union[str, None] = None):
        '''
        Parameters
        ----------
        symbol : str
            E.g. ETH
        token_name : str
            These are helpful in finding the contract address online, if you know it is not saved in the program / is a new token.
        '''
        token_address = StoredAddressInfo.get_token_address(symbol=symbol, blockchain_name=self.blockchain_name, blockchain_net=self.blockchain_net, DataLoc=self.DataLoc)
        if token_address is None:
            token_address = self.CommsBlockchainDataProviders.get_contract_address(
                symbol=symbol, token_name=token_name,
                blockchain_name=self.blockchain_name, blockchain_net=self.blockchain_net,
                save=True, override=True
            )
            if token_address is None:
                error = f'Requested "symbol" has no address in {self.DataLoc.File.TOKEN_ADDRESS.value} and address could not be found online. Symbol: {symbol}. Type: {type(symbol)}.'
                self.logger.critical(error)
                raise Exception(error)
        return token_address


    def swap_wbnb(self, quantity: float, to_wbnb: bool):
        '''
        Uses the WBNB contract to:
            - if to_wbnb is True: lock BNB and mint BEP-20 conforming WBNB
            - if to_wbnb is False: burn WBNB and unlock BNB
        '''
        ## Get Data
        decimals = 18  # Binance Smart Chain layer 1 uses 18 decimals for BNB amounts
        decimal_quantity = self.to_dex_number(number=quantity, decimals=decimals)
        nonce = self.w3.eth.get_transaction_count(self.address_wallet)

        ## Make Transaction
        if to_wbnb is True:
            txn_inputs = {
                'value': decimal_quantity,
                'gas': 300000,  # usually between 25,000 to 50,000
                'gasPrice': self.get_gas_price(strategy_name='simple', multiplier=0.2),
                'nonce': nonce,
            }
            txn = self.contract_wbnb.functions.deposit().buildTransaction(txn_inputs)
        elif to_wbnb is False:
            txn_inputs = {
                'gas': 300000,  # usually between 25,000 to 50,000
                'gasPrice': self.get_gas_price(strategy_name='simple', multiplier=0.2),
                'nonce': nonce,
            }
            txn = self.contract_wbnb.functions.withdraw(decimal_quantity).buildTransaction(txn_inputs)
        else:
            error = f'Parameter "to_wbnb" must be of type bool. Argument given: {to_wbnb}. Type: {type(to_wbnb)}.'
            self.logger.critical(error)  # critical because this means my code is ass
            raise Exception(error)

        ## Sign and Send Transaction
        signed_txn = self.w3.eth.account.sign_transaction(txn, self.private_key)
        txn_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)

        ## Return Transaction Info
        txn_info = txn_inputs
        txn_info.update({
            'to_wbnb': to_wbnb,
            'quantity_to_convert': decimal_quantity,
            'txn_hash': txn_hash,
        })
        return txn


    @staticmethod
    def _parse_log_attribute_dict(d):
        parsed_dict = {
            'event': d['event'],
            'address': d['address']
        }
        parsed_dict.update(d['args'])
        return {d['logIndex']: parsed_dict}


    def parse_transaction_receipt(self, txn_receipt: dict):
        '''
        https://dashboard.tenderly.co/tx/main/
        https://ethereum.stackexchange.com/questions/94954/how-to-understand-uniswaps-events
        https://medium.com/coinmonks/unlocking-the-secrets-of-an-ethereum-transaction-3a33991f696c
        https://medium.com/linum-labs/everything-you-ever-wanted-to-know-about-events-and-logs-on-ethereum-fec84ea7d0a5
        '''
        output_dict = {}
        loaded_abis = {}
        get_event_signature = lambda event_abi: f"{event_abi['name']}({','.join([param['type'] for param in event_abi['inputs']])})"

        # ## Decode Input Data
        # txn_data = self.w3.eth.get_transaction(txn_hash)
        # # decoded_input_data = self.contract_router.decode_function_input(txn_data["input"])

        # ## Decode Logs
        # txn_receipt = self.w3.eth.get_transaction_receipt(txn_hash)
        txn_index = txn_receipt['transactionIndex']
        for log in txn_receipt.logs:

            ## Get Contract Object
            contract_address = log['address']
            try:
                abi = self.loaded_abis[contract_address]
            except KeyError:
                abi = CommsBlockchainDataProviders(blockchain_net='mainnet').BscScan.get_abi(contract_address=contract_address)
                self.loaded_abis[contract_address] = abi
            contract = self.w3.eth.contract(address=contract_address, abi=abi)

            ## Get Contract Events
            events = [abi for abi in contract.abi if abi['type'] == 'event']
            event_sig_hexs = {
                Web3.toHex(Web3.keccak(text=get_event_signature(event))): event
                for event in events
            }

            ## Decode each Topic in Txn Logs
            for topic in log['topics']:
                topic_event_sig_hex = Web3.toHex(topic)
                ## Find the Contract Event that can decode the Topic data
                matching_event = event_sig_hexs.get(topic_event_sig_hex, None)
                if matching_event is not None:
                    ## Decode the Topic Data via "matching" Contract Event
                    decoded_receipt_data = contract.events[matching_event['name']]().processReceipt(txn_receipt)
                    if len(decoded_receipt_data) != 0:
                        ## Extract the Relevant Info from each Parsed Topic and add to output_dict
                        for parsed_event in decoded_receipt_data:  # should only be one, just in case
                            output_dict.update(self._parse_log_attribute_dict(parsed_event))
                    else:
                        print('wtf!!!')
                        self.logger.warning(f"'Weird finding: an event whose signature matched the og's topic, decoded the topic into an empty variable. Decoded topic: {decoded_receipt_data}. Type: {type(decoded_receipt_data)}.")
        return output_dict


    # def get_blocks_between_datetimes(self, start: datetime, end: datetime, start_closest: str, end_closest: str):
    #     '''
    #     Parameters
    #     ----------
    #     start_closest / end_closest : str
    #         Can be 'before', 'after'
    #     '''
    #     return





if __name__ == '__main__':

    Comms = CommsBlockchainBSC(blockchain_net='mainnet')
    # x = Comms.get_block_by_datetime(dt=datetime(2021,1,1), closest='before')
    y = Comms.get_and_parse_transaction_data(txn_hash='0x67ba333d8a7a694eadf990d9d1afd2b093ee5dbdcf88123d191b9a1ed450a908')
    z = 1

    ### TEST CODE ####
    Comms = CommsBlockchainBSC(blockchain_net='testnet')
    symbol_1 = 'WBNB'  # 'CAKE'
    symbol_2 = 'HEDGE'  # 'BUSD'

    print(f'Start Nonce: {Comms.get_nonce()}'); print()

    print('My Wallet Balance')
    print('BNB:'); print(Comms.w3.eth.get_balance(Comms.address_wallet));
    print('WBNB:'); print(Comms.contract_wbnb.functions.balanceOf(Comms.address_wallet).call()); print()

    symbol_1_address = Comms.get_token_address(symbol=symbol_1)
    symbol_2_address = Comms.get_token_address(symbol=symbol_2)
    print('Contract Addresses'); print(f'{symbol_1}: {symbol_1_address}'); print(f'{symbol_2}: {symbol_2_address}'); print('Now check pancakeswapv2 logs'); print()

    swapped = Comms.swap_wbnb(quantity=0.0000076974863, to_wbnb=True)
    print('Swap BNB for WBNB'); print(swapped); print()

    print(f'End Nonce: {Comms.get_nonce()}'); print()


    # ### TEST CODE ####
