## Internal Modules
from scripts.utils import DataLoc, MyLogger, handle_ccxt_error, get_token_address
from scripts.comms_blockchain_data_providers import CommsBlockchainDataProviders
from scripts.order_class import OrderClass

## External Libraries
from typing import Union
import json
import datetime
from web3 import Web3, IPCProvider
from web3.middleware import geth_poa_middleware
import sys


class CommsDEXUniSwapV2():
    '''
    UniSwap V2 Functions
    ---------------------
    swapTokensForTokens: allows a trader to specify an exact number of input tokens he is willing to give and the minimum number of output tokens he is willing to receive in return.
    swapTokensForExactTokens: reverse of swapTokensForTokens; it lets a trader specify the number of output tokens he wants, and the maximum number of input tokens he is willing to pay for them.
    getAmountIn: Returns the minimum input asset amount required to buy the given output asset amount (accounting for fees) given reserves.
    getAmountOut: Given an input asset amount, returns the maximum output amount of the other asset (accounting for fees) given reserves.

    Blockchain Docs
    ---------------
    UniSwap V2:
        https://docs.uniswap.org/protocol/V2/reference/smart-contracts/library
        https://docs.uniswap.org/protocol/V2/reference/smart-contracts/factory
        https://docs.uniswap.org/protocol/V2/reference/smart-contracts/router-01#swaptokensforexacttokens

    Misc
    ----
    Great article on standard ERC-20 contract functions
        https://towardsdatascience.com/access-ethereum-data-using-web3-py-infura-and-the-graph-d6fb981c2dc9
    ETH Gas Suggestor:
        https://ethgasstation.info/

    REEEEAAAD HERE BROOO
        - https://ethereum.stackexchange.com/questions/103180/will-i-have-to-change-how-i-set-raw-transaction-gas-price-for-eip-1559
        - https://ethereum.stackexchange.com/questions/106380/sending-transactions-after-london-fork-considering-eip-1559/106514#106514
    '''

    def __init__(self):
        self.blockchain_name = 'ethereum'
        self.blockchain_net = 'mainnet'
        self.DataLoc = DataLoc()
        ## Open Shit
        with open(self.DataLoc.File.CONFIG.value) as json_file:
            config_external = json.load(json_file)['external']
        with open(self.DataLoc.File.TOKEN_ADDRESS.value) as json_file:
            self.token_addresses = json.load(json_file)[self.blockchain_name][self.blockchain_net]
        with open(self.DataLoc.File.NODES.value) as json_file:
            self.nodes = json.load(json_file)[self.blockchain_name][self.blockchain_net]
        ## Logger
        self.logger = MyLogger().configure_logger(fileloc=self.DataLoc.Log.COMMS_DEX_UNISWAPV2.value)
        ## Comms Objects
        self.CommsBlockchainDataProviders = CommsBlockchainDataProviders()
        ## Connect to Blockchain
        self.w3 = self.connect(infura_project_id=config_external['infura_project_id'])
        self.set_contract_objects()
        ''' Sets the following instance attributes:
            self.address_factory
            self.contract_factory
            self.address_router
            self.contract_router
            self.address_library
            self.contract_library
        '''

    def connect(self, infura_project_id: str = None):
        for node in self.nodes:
            w3 = Web3(Web3.HTTPProvider(f'{node}/{infura_project_id}'))
            # w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            is_connected = w3.isConnected()
            if is_connected is True:
                self.logger.debug(f'Connected to {self.blockchain_name} - {self.blockchain_net}. Node: {node}.')
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
        Sets address and contract instance attributes to communicate with the UniSwap V2 smart contract system.
        '''
        with open(self.DataLoc.File.NONTOKEN_ADDRESS.value) as json_file:
            addresses = json.load(json_file)[self.blockchain_name][self.blockchain_net]['uniswap_v2']
        with open(self.DataLoc.File.ABI.value) as json_file:
            abis = json.load(json_file)['uniswap_v2']
        ## Create Factory Contract Object
        address_factory = Web3.toChecksumAddress(addresses['factory'])
        abi_factory = abis['factory']
        contract__factory = self.w3.eth.contract(address=address_factory, abi=abi_factory)
        ## Create Router Contract Object
        address_router = Web3.toChecksumAddress(addresses['router'])
        abi_router = abis['router']
        contract_router = self.w3.eth.contract(address=address_router, abi=abi_router)
        ## Create Library Contract Object
        # address_library = Web3.toChecksumAddress(addresses['library'])
        # abi_library = abis['library']
        # contract_library = self.w3.eth.contract(address=address_library, abi=abi_library)
        ## Set Instance Attributes
        self.address_factory = address_factory
        self.contract_factory = contract__factory
        self.address_router = address_router
        self.contract_router = contract_router
        # self.address_library = address_library
        # self.contract_library = contract_library
        return


    def get_token_address(self, symbol:str, token_name: Union[str, None] = None):
        '''
        Parameters
        ----------
        symbol : str
            E.g. ETH
        token_name : str
            These are helpful in finding the contract address online, if you know it is not saved in the program / is a new token.
        '''
        token_address = get_token_address(symbol=symbol, blockchain_name=self.blockchain_name, blockchain_net=self.blockchain_net, DataLoc=self.DataLoc)
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


    def get_reserves(self, token_a_contract_address: str, token_b_contract_address: str):
        '''
        Returns the amount of token_a and token_b that make up the liquidity pool.
        '''
        token_a_pool_quantity, token_b_pool_quantity = self.library_contract.functions.getReserves(
            self.address_factory, token_a_contract_address, token_b_contract_address
        )
        return token_a_pool_quantity, token_b_pool_quantity


    def get_current_price(self, underlying_token_contract_address: str, quote_token_contract_address: str):
        '''
        This is the price you would get for an infinitesimally small input amount.
        To get the actual output amount for a given input amount, aka to account for pool liquidity / slippage, use the "get_amount_returned" function.
        '''
        underlying_token_pool_quantity, quote_token_pool_quantity = self.get_reserves(
            token_a_contract_address=underlying_token_contract_address,
            token_b_contract_address=quote_token_contract_address
        )
        return underlying_token_pool_quantity / quote_token_pool_quantity


    def get_sell_amount(self, buy_token_contract_address: str, sell_token_contract_address: str, slippage: float, buy_amount: float = 0):
        '''
        Parameters
        ----------
        slippage : float
            Example: 0.02 allows for 2% slippage.
            Example: 1.03 allows for 103% slippage.
        Returns the actual output amount for a given input amount.
            - This function takes into account pool liquidity.
            - I think DEX people refer to slippage as the difference in observed price and returned price, due to pool liquidity
              (aka the order book depth in the traditional order book model).
              This is not what slippage is, because it is known that this difference will occur when observing the market,
              and occurs without the action of any other trades.
              Slippage is this difference, but due to other trades being filled before your own.

        Misc
        ----
        The calculation is {out_token buy amount} =  ({out_token reserve amount} * {in_token sell amount}) / ({in_token sell amount} + {in_token reserve amount})
        '''
        slippage = slippage + 1  # 0.02 is recommended by reddit people to not be front run
        ## How many input / sell tokens are needed to purchase a given amount of output / buy tokens
        sell_amount = self.contract_router.functions.getAmountsIn(
            (buy_amount * slippage),  # THIS MAY HAVE TO BE AN INT amount of tokens to receive after swap
            [sell_token_contract_address, buy_token_contract_address]  # sell token goes before buy token in the github example from https://github.com/manuelhb14/cake_uni_transaction_bot/
        ).call()
        return sell_amount


    def get_buy_amount(self, buy_token_contract_address: str, sell_token_contract_address: str, slippage: float, sell_amount: float = 0):
        slippage = slippage + 1  # 0.02 is recommended by reddit people to not be front run
        ## How many output / buy tokens are returned from selling a given amount of input / sell tokens
        ## (accounting for fees)????? Docs say it accounts for fees... what fees.
        buy_amount = self.contract_router.functions.getAmountsOut(
            int(sell_amount * slippage),                               # THIS MAY HAVE TO BE AN INT # amount in
            [sell_token_contract_address, buy_token_contract_address]  # [SELL, BUY]
            ).call()
        return buy_amount


    def swap(self, buy_token_contract_address: str, sell_token_contract_address: str, amount_in: float, price: Union[float, None] = None, slippage : Union[float, None] = None):
        '''
        The function swapExactTokensForTokens is used because any strategy will be working with a known, finite amount of funds.
            - To make a limit order with the function swapExactTokensForTokens, the price MUST be quoted in sell_tokens / buy_tokens.
              E.g. to buy apples, quote $50 dollars per apple.
              E.g. to sell apples, quote $0.2 apples per dollar.
              Otherwise, {min_amount_out = amount_in / price} won't work. You could always quote it the opposite way and change the calculation to {min_amount_out = amount_in * price}
        '''
        ## Calculate Shit
        if slippage is None:
            slippage = 11  # slippage is 1000% to make sure order fills

        ## Market Order
        if price is None:  # use slippage from market price
            market_price = self.get_market_price(buy_token_contract_address, sell_token_contract_address)
            min_amount_out = self.contract_router.functions.getAmountsOut(  # given an input asset amount, returns the maximum output amount of the other asset (accounting for fees) given reserves.
            (amount_in * slippage),                                    # THIS MAY HAVE TO BE AN INT  # amount_in
            [sell_token_contract_address, buy_token_contract_address]  # [{sell_token}, {buy_token}] in example: https://github.com/manuelhb14/cake_uni_transaction_bot/
        )
        ## Limit Order
        else:
            slippage = 1.00  # if slippage is zero, then amount_in and min_amount_out perfectly describe the limit price
            min_amount_out = amount_in / price  # entire must be filled at this price. Accounting for AMM, that means market price will have to be much better than limit price to have entire filled at an average fill price of the limit price

        ## Perform Swap
        swap_ouput = self.contract_router.functions.swapExactTokensForTokens(  # receive an as many output tokens as possible for an exact amount of input tokens.
            amount_in,       # amount of sell token to sell
            min_amount_out,  # min amount of buy token to receive
            [sell_token_contract_address, buy_token_contract_address],
            self.vault_address, # my crypto bank account
            datetime.utcfromtimestamp(datetime.utcnow() + datetime.timedelta(minutes=5)),
        )
        return swap_ouput


    def place_order(self, order: OrderClass):
        ## Record Order Placement Attempt
        self.logger.info(f'Placing order: {order}.')

        ## Get Order Info
        order_type      = order['order_type']
        buy_symbol      = order['buy_symbol']
        sell_symbol     = order['sell_symbol']
        buy_token_name  = order['notes'].get('buy_token_name', None)
        sell_token_name = order['notes'].get('sell_token_name', None)
        amount_in       = order['quantity_to_sell']
        amount_out      = order['quantity_to_buy']
        price_in_sell   = order['price_in_sell']
        slippage        = order['slippage']

        ## Check for Shit Order
        if order_type != 'spot':
            error = f'Only spot orders can be placed on UniswapV2. Order: {order}.'
            self.logger.critical(error)
            raise Exception(error)

        ## Get Token Contract Addresses
        buy_token_contract_address  = self.CommsBlockchainDataProviders.get_contract_address(symbol=buy_symbol,  token_name=buy_token_name,  blockchain_name=self.blockchain_name, blockchain_net=self.blockchain_net, save=True, override=False)
        sell_token_contract_address = self.CommsBlockchainDataProviders.get_contract_address(symbol=sell_symbol, token_name=sell_token_name, blockchain_name=self.blockchain_name, blockchain_net=self.blockchain_net, save=True, override=False)

        ## Convert Quantity if necessary
        if amount_in == 0:  # if True, amount_out is non-zero
            amount_in = self.contract_router.functions.getAmountsIn(
                (amount_out * slippage),  # THIS MAY HAVE TO BE AN INT  # amount_out, aka amount of tokens to receive after swap
                [sell_token_contract_address, buy_token_contract_address]  # [{sell_token}, {buy_token}] in example: https://github.com/manuelhb14/cake_uni_transaction_bot/
            )

        ## Place Order
        order_feedback = self.swap(
            buy_token_contract_address=buy_token_contract_address,
            sell_token_contract_address=sell_token_contract_address,
            amount_in=amount_in,
            price=price_in_sell,
            slippage=slippage
        )
        ## Record Order Placement
        self.logger.info(f'Order placed: {order_feedback}.')



if __name__ == '__main__':
    comms = CommsDEXUniSwapV2()
    ### TEST CODE ####
    symbol_1 = 'WBTC'
    symbol_2 = 'USDT'
    symbol_1_address = comms.get_token_address(symbol=symbol_1)
    symbol_2_address = comms.get_token_address(symbol=symbol_2)
    print('Contract Addresses'); print(f'{symbol_1}: {symbol_1_address}'); print(f'{symbol_2}: {symbol_2_address}'); print('Now check uniswapv2 logs')
    print()
    # cake_reserves, wbnb_reserves = comms.get_reserves(token_a_contract_address=cake_address, token_b_contract_address=wbnb_address)
    # print(f'Reserves in the UniSwap {symbol_1}-{symbol_2} pool'), print(f' WBTC: {cake_reserves}'); print(f'USDT: {wbnb_reserves}')
    # print()
    symbol_1_for_symbol_2 = comms.get_buy_amount(buy_token_contract_address=symbol_2_address, sell_token_contract_address=symbol_1_address, slippage=0, sell_amount=1000000)
    symbol_2_for_symbol_1 = comms.get_buy_amount(buy_token_contract_address=symbol_1_address, sell_token_contract_address=symbol_2_address, slippage=0, sell_amount=1000000)
    print(f'Amounts out in the UniSwap {symbol_1}-{symbol_2} pool'), print(f'{symbol_1_for_symbol_2[0]} {symbol_1} -> {symbol_1_for_symbol_2[1]} {symbol_2}'); print(f'{symbol_2_for_symbol_1[0]} {symbol_2} -> {symbol_2_for_symbol_1[1]} {symbol_1}');
    print()
    symbol_1_for_symbol_2 = comms.get_buy_amount(buy_token_contract_address=symbol_2_address, sell_token_contract_address=symbol_1_address, slippage=0, sell_amount=1000000000)
    symbol_2_for_symbol_1 = comms.get_buy_amount(buy_token_contract_address=symbol_1_address, sell_token_contract_address=symbol_2_address, slippage=0, sell_amount=1000000000)
    print(f'Amounts out in the UniSwap {symbol_1}-{symbol_2} pool'), print(f'{symbol_1_for_symbol_2[0]} {symbol_1} -> {symbol_1_for_symbol_2[1]} {symbol_2}'); print(f'{symbol_2_for_symbol_1[0]} {symbol_2} -> {symbol_2_for_symbol_1[1]} {symbol_1}');
    print()
    symbol_1_for_symbol_2 = comms.get_buy_amount(buy_token_contract_address=symbol_2_address, sell_token_contract_address=symbol_1_address, slippage=0, sell_amount=1000000000000)
    symbol_2_for_symbol_1 = comms.get_buy_amount(buy_token_contract_address=symbol_1_address, sell_token_contract_address=symbol_2_address, slippage=0, sell_amount=1000000000000)
    print(f'Amounts out in the UniSwap {symbol_1}-{symbol_2} pool'), print(f'{symbol_1_for_symbol_2[0]} {symbol_1} -> {symbol_1_for_symbol_2[1]} {symbol_2}'); print(f'{symbol_2_for_symbol_1[0]} {symbol_2} -> {symbol_2_for_symbol_1[1]} {symbol_1}');
    print()
    symbol_1_for_symbol_2 = comms.get_buy_amount(buy_token_contract_address=symbol_2_address, sell_token_contract_address=symbol_1_address, slippage=0, sell_amount=1000000000000000)
    symbol_2_for_symbol_1 = comms.get_buy_amount(buy_token_contract_address=symbol_1_address, sell_token_contract_address=symbol_2_address, slippage=0, sell_amount=1000000000000000)
    print(f'Amounts out in the UniSwap {symbol_1}-{symbol_2} pool'), print(f'{symbol_1_for_symbol_2[0]} {symbol_1} -> {symbol_1_for_symbol_2[1]} {symbol_2}'); print(f'{symbol_2_for_symbol_1[0]} {symbol_2} -> {symbol_2_for_symbol_1[1]} {symbol_1}');
    print()
    symbol_1_for_symbol_2 = comms.get_buy_amount(buy_token_contract_address=symbol_2_address, sell_token_contract_address=symbol_1_address, slippage=0, sell_amount=1000000000000000000)
    symbol_2_for_symbol_1 = comms.get_buy_amount(buy_token_contract_address=symbol_1_address, sell_token_contract_address=symbol_2_address, slippage=0, sell_amount=1000000000000000000)
    print(f'Amounts out in the UniSwap {symbol_1}-{symbol_2} pool'), print(f'{symbol_1_for_symbol_2[0]} {symbol_1} -> {symbol_1_for_symbol_2[1]} {symbol_2}'); print(f'{symbol_2_for_symbol_1[0]} {symbol_2} -> {symbol_2_for_symbol_1[1]} {symbol_1}');
    print()
    symbol_1_for_symbol_2 = comms.get_buy_amount(buy_token_contract_address=symbol_2_address, sell_token_contract_address=symbol_1_address, slippage=0, sell_amount=1000000000000000000000)
    symbol_2_for_symbol_1 = comms.get_buy_amount(buy_token_contract_address=symbol_1_address, sell_token_contract_address=symbol_2_address, slippage=0, sell_amount=1000000000000000000000)
    print(f'Amounts out in the UniSwap {symbol_1}-{symbol_2} pool'), print(f'{symbol_1_for_symbol_2[0]} {symbol_1} -> {symbol_1_for_symbol_2[1]} {symbol_2}'); print(f'{symbol_2_for_symbol_1[0]} {symbol_2} -> {symbol_2_for_symbol_1[1]} {symbol_1}');
    print()
    ### TEST CODE ####



    # get function to find price: https://docs.uniswap.org/protocol/V2/concepts/core-concepts/oracles
    # read about frunt running: https://www.reddit.com/r/UniSwap/comments/m5l875/front_running_bot_is_getting_way_way_way/
    # due to front running, and due to exponential price increase shit, make twap function
    ### make get_price function using on_chain data - could also use TheGraph but if they go down ur fucked for what. Using the TheGraph comes with advantage of not having to do a few calculations yourself aka on computer you pay for.