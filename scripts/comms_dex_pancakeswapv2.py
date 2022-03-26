## Internal Modules
from scripts.comms_blockchain_bsc import CommsBlockchainBSC
from scripts.utils import MyLogger
from scripts.order_class import OrderClass
from scripts.comms_blockchain_data_providers import CommsBlockchainDataProviders

## External Libraries
from typing import Union
import json
import math
import pickle
from datetime import datetime, timedelta, timezone
from web3 import Web3
from web3.exceptions import BadFunctionCallOutput, ContractLogicError


class CommsDEXPancakeSwapV2(CommsBlockchainBSC):
    '''
    Methods (does not include parent class)
    -------
    set_contract_objects
    get_pool_address
    get_pool_contract
    get_token_addresses_from_pool
    get_reserves
    get_current_price
    get_historical_trades
    get_sell_amount
    get_buy_amount
    create_swap_txn
    place_order



    PancakeSwapV2 Functions
    ---------------------
    swapTokensForTokens: allows a trader to specify an exact number of input tokens he is willing to give and the minimum number of output tokens he is willing to receive in return.
    swapTokensForExactTokens: reverse of swapTokensForTokens; it lets a trader specify the number of output tokens he wants, and the maximum number of input tokens he is willing to pay for them.
    getAmountIn: Returns the minimum input asset amount required to buy the given output asset amount (accounting for fees) given reserves.
    getAmountOut: Given an input asset amount, returns the maximum output amount of the other asset (accounting for fees) given reserves.

    Contract Docs
    ---------------
    PancakeSwap V2 useless ass shell docs:
        https://docs.pancakeswap.finance/code/smart-contracts/pancakeswap-exchange/
    UniSwap V2:
        https://docs.uniswap.org/protocol/V2/reference/smart-contracts/library
        https://docs.uniswap.org/protocol/V2/reference/smart-contracts/factory
        https://docs.uniswap.org/protocol/V2/reference/smart-contracts/router-01#swaptokensforexacttokens

    Common Errors
    -------------
    'transaction underpriced'
        - 'code': 3200
    'insufficient funds for gas * price + value'
        'code': -32000

    Misc
    ----
    Example: description of a bot someone wanted for PancakeSwap w/ strategy outlined XD
        https://www.freelancer.ca/projects/ethereum/pancakeswap-new-liquidity-check-module/?ngsw-bypass=&w=f
    '''

    def __init__(self, blockchain_net: str):
        super().__init__(blockchain_net=blockchain_net)  # instantiate CommsBlockchainBSC
        self.logger = MyLogger().configure_logger(fileloc=self.DataLoc.Log.COMMS_BLOCKCHAIN_BSC.value)
        ## Communication with the Blockchain
        self.set_contract_objects()
        ''' Sets the following instance attributes:
            self.address_factory
            self.contract_factory
            self.address_router
            self.contract_router
        '''
        return


    def set_contract_objects(self):
        '''
        Sets address and contract instance attributes to communicate with the PancakeSwap V2 smart contract system.
        '''
        with open(self.DataLoc.File.CONTRACT_ADDRESS.value) as json_file:
            addresses = json.load(json_file)[self.blockchain_name][self.blockchain_net]['pancakeswapv2']
        with open(self.DataLoc.File.ABI.value) as json_file:
            abis = json.load(json_file)[self.blockchain_name]['mainnet']['pancakeswapv2']  # testnet abi's are hopefully the same
        ## Create Factory Contract Object
        address_factory = Web3.toChecksumAddress(addresses['factory'])
        abi_factory = abis['factory']
        contract_factory = self.w3.eth.contract(address=address_factory, abi=abi_factory)
        ## Create Router Contract Object
        address_router = Web3.toChecksumAddress(addresses['router'])
        abi_router = abis['router']
        contract_router = self.w3.eth.contract(address=address_router, abi=abi_router)
        ## Set Instance Attributes
        self.address_factory = address_factory
        self.contract_factory = contract_factory
        self.address_router = address_router
        self.contract_router = contract_router
        return


    def get_pool_address(self, token_contract_address_a: str, token_contract_address_one: str):
        ''' Doesn't matter which way you put the two addresses in, it'll return the same pool address '''
        pool_address = self.contract_factory.functions.getPair(token_contract_address_a, token_contract_address_one).call()
        if pool_address == '0x0000000000000000000000000000000000000000':
            error = f'No PancakeSwapV2 pool exists for these addresses: [{token_contract_address_a}, {token_contract_address_one}].'
            self.logger.info(error)
            return None
        else:
            return pool_address


    def get_pool_contract(self, pool_address: str):
        with open(self.DataLoc.File.ABI.value) as json_file:
            abis = json.load(json_file)[self.blockchain_name]['mainnet']['pancakeswapv2']
        universal_pool_abi = abis['pair']
        return self.w3.eth.contract(address=pool_address, abi=universal_pool_abi)


    def get_token_addresses_from_pool(self, pool_contract: str):
        return (pool_contract.functions.token0().call(), pool_contract.functions.token1().call())


    def get_reserves(self, pool_contract):
        '''
        Returns the amount of token_a and token_b that make up the liquidity pool.
        '''
        decimals = 10 ** pool_contract.functions.decimals().call()
        reserves = pool_contract.functions.getReserves().call()
        output = {
            pool_contract.functions.token0().call(): (reserves[0] / decimals),
            pool_contract.functions.token1().call(): (reserves[1] / decimals),
        }
        return output


    def get_current_price(self, buy_token_contract_address: str, sell_token_contract_address: str):
        '''
        This is the price you would get for an infinitesimally small input amount.
        To get the actual output amount for a given input amount, aka to account for pool liquidity / slippage, use the "get_amount_returned" function.
        '''
        reserves = self.get_reserves(self.get_pool_contract(self.get_pool_address(
            token_contract_address_a=buy_token_contract_address,
            token_contract_address_one=sell_token_contract_address
        )))
        price_in_sell = reserves[sell_token_contract_address] / reserves[buy_token_contract_address]
        return price_in_sell


    def get_historical_trades(
        self, symbol_1: str, symbol_2: str,
        start: Union[datetime, None] = None, end: Union[datetime, None] = None,
        start_block: Union[int, None] = None, end_block: Union[int, None] = None,
        save: bool = False
    ):
        '''
        Function
        --------
        1. Takes two symbols, a start and end date, and queries all Pancakeswap Pools
           with those two tokens to find all the swap events in that period.
        2. Then gets the full transaction hash each swap event was a part of.
        3. Then compares the "transfer" event amounts in the transaction hash
           to the amounts in and out of the swap event to figure out which token
           was bought/sold.
        4. Then records the buy/sell tokens and amounts to an output_data variable.
        '''
        output_data = {}
        ## Get Contract Addresses and Objects
        symbol_1_address = self.get_token_address(symbol=symbol_1)
        symbol_2_address = self.get_token_address(symbol=symbol_2)
        pool_address = self.get_pool_address(symbol_1_address, symbol_2_address)
        pool_contract = self.get_pool_contract(pool_address=pool_address)
        decimals = pool_contract.functions.decimals().call()

        ## Get all Swap Events from Pool Contract between datetimes
        if start_block is None:
            from_block = self.CommsBlockchainDataProviders.BscScan.get_block_id_by_datetime(dt=start, closest='before')
        else:
            from_block = start_block
        if end_block is None:
            to_block= self.CommsBlockchainDataProviders.BscScan.get_block_id_by_datetime(dt=end, closest='after')
        else:
            to_block = end_block
        event_filter = pool_contract.events.Swap.createFilter(fromBlock=from_block, toBlock=to_block)
        unparsed_swaps = event_filter.get_all_entries()

        ## Parse the Transaction Log associated with each Swap Event
        txn_hashes = {d.transactionHash: d.args for d in unparsed_swaps}
        for txn_hash, swap_event in txn_hashes.items():
            ## Prep Data for Finding the Swapped Amounts and Direction (buy/sell which token)
            txn_receipt = self.w3.eth.get_transaction_receipt(txn_hash)
            parsed_receipt = self.parse_transaction_receipt(txn_receipt=txn_receipt)
            symbol_1_amount = [d.get('value', d.get('wad')) for d in parsed_receipt.values() if d['event'] == 'Transfer' and d['address'] == symbol_1_address][0]
            symbol_2_amount = [d.get('value', d.get('wad')) for d in parsed_receipt.values() if d['event'] == 'Transfer' and d['address'] == symbol_2_address][0]
            ## Assign Swapped Amounts and Direction
            amount_in = max([swap_event['amount0In'], swap_event['amount1In']])  # max() removes the zero value
            amount_out = max([swap_event['amount0Out'], swap_event['amount1Out']])  # max() removes the zero value
            buy_symbol = symbol_1 if (symbol_1_amount == amount_out) else symbol_2 if (symbol_2_amount == amount_out) else None
            sell_symbol = symbol_1 if (symbol_1_amount == amount_in) else symbol_2 if (symbol_2_amount == amount_in) else None
            ## Get Other Data
            block_number = txn_receipt['blockNumber']
            block_datetime =  datetime.fromtimestamp(self.w3.eth.getBlock(block_number)['timestamp'], tz=timezone.utc)
            gas_price = self.w3.eth.getTransaction(txn_hash)['gasPrice']
            gas_used = txn_receipt['gasUsed']
            ## Record to Output Variable
            output_data.update({
                txn_hash.hex(): {
                    'block_number': block_number,
                    'txn_index': txn_receipt['transactionIndex'],
                    'block_datetime': block_datetime,
                    'buy_symbol': buy_symbol,
                    'sell_symbol': sell_symbol,
                    'buy_amount': self.from_dex_number(amount_out, decimals=decimals),
                    'sell_amount': self.from_dex_number(amount_in, decimals=decimals),
                    'gas_used': gas_used,
                    'gas_price': gas_price,
                }
            })
        ## Save Data
        if save is True:
            start_strf = start.strftime("%Y-%m-%d-%H-%M-%S")
            end_strf = end.strftime("%Y-%m-%d-%H-%M-%S")
            file_name = f'pancakeswapv2_{symbol_1}_{symbol_2}_{start_strf}_{end_strf}.pkl'
            file_loc = f'{self.DataLoc.Folder.DEX_PRICES.value}/{file_name}'
            with open(file_loc, 'wb') as pfile:
                pickle.dump(output_data, pfile, protocol=pickle.HIGHEST_PROTOCOL)
        return output_data


    def get_sell_amount(self, pool_contract, buy_token_contract_address: str, sell_token_contract_address: str, slippage: float, buy_amount: float = 0):
        '''
        Parameters
        ----------
        slippage : float
            Quote this amount in decimal form. E.g. 2% slippage should be given as 0.02
            NOTE: 0.02 is recommended by reddit people to not be front run

        Returns the actual output amount for a given input amount.
            - This function takes into account pool liquidity.
            - I think DEX people refer to slippage as the difference in observed price and returned price, due to pool liquidity
              (aka the order book depth in the traditional order book model).
              This is not what slippage is, because it is known that this difference will occur when observing the market,
              and occurs without the action of any other trades.
              Slippage is this difference, but due to other trades being filled before your own.

        Smart Contract Functions
        ------------------------
        getAmountsIn:

        Misc
        ----
        The calculation is {out_token buy amount} =  ({out_token reserve amount} * {in_token sell amount}) / ({in_token sell amount} + {in_token reserve amount})
        '''
        decimals = pool_contract.functions.decimals().call()
        slippage_adjusted_buy_amount = buy_amount * (1 + slippage)  # adding (+) slippage because more input is needed to account for slippage
        ## How many input / sell tokens are needed to purchase a given amount of output / buy tokens
        sell_amount = self.contract_router.functions.getAmountsIn(
            self.to_dex_number(slippage_adjusted_buy_amount, decimals=decimals),
            [sell_token_contract_address, buy_token_contract_address]  # [SELL, BUY]
            ).call()  # returns [amount_in, amount_out]
        return self.from_dex_number(sell_amount[0], decimals=decimals)


    def get_buy_amount(self, pool_contract, buy_token_contract_address: str, sell_token_contract_address: str, slippage: float = 0.02, sell_amount: float = 0):
        '''
        Parameters
        ----------
        slippage : float
            Quote this amount in decimal form. E.g. 2% slippage should be given as 0.02
            NOTE: 0.02 is recommended by reddit people to not be front run

        Smart Contract Functions
        ------------------------
        getAmountsOut:
            outputs [amount_in, amount_out], where
            amount_in is a provided argument
            amount_out is the number of buy-tokens returned from selling amount_in number of sell-tokens, accounting for pool liquidity AND DEX swap fees but not accounting for layer 1 miner fees.
        '''
        decimals = pool_contract.functions.decimals().call()
        slippage_adjusted_sell_amount = sell_amount * (1 - slippage)  # subtracting (-) slippage because expecting less output is needed to account for slippage
        buy_amount = self.contract_router.functions.getAmountsOut(
            self.to_dex_number(slippage_adjusted_sell_amount, decimals=decimals),
            [sell_token_contract_address, buy_token_contract_address]  # [SELL, BUY]
            ).call()  # returns [amount_in, amount_out]
        return self.from_dex_number(buy_amount[1], decimals=decimals)


    def create_swap_txn(self, pool_contract, buy_token_contract_address: str, sell_token_contract_address: str, sell_quantity: float, price_in_sell: Union[float, None] = None, slippage : Union[float, None] = None):
        '''
        swapExactTokensForTokens
            - Receive an as many output tokens as possible for an exact amount of input tokens.
            - This function is used because any strategy will be working with a pre-defined, finite amount of funds.
            - To make a limit order with the function swapExactTokensForTokens,
              min_amount_out is calculated as {min_amount_out = amount_in / price} and does not consider the size of pool reserves.
              Aka, self.get_buy_amount is not used as this would assume achieving a lower price due to the AMM output calculation.
        '''
        ## Market Order
        if price_in_sell is None:  # use slippage from market price
            min_buy_quantity = self.get_buy_amount(
                pool_contract=pool_contract, slippage=slippage, sell_amount=sell_quantity,
                buy_token_contract_address=buy_token_contract_address,
                sell_token_contract_address=sell_token_contract_address
            )
        ## Limit Order
        else:
            min_buy_quantity = sell_quantity / price_in_sell  # entire must be filled at this price. Accounting for AMM output calculation (m*n=k), that means market price will have to be much better than limit price to have entire filled at an average fill price of the limit price

        ## Get Data
        decimals = pool_contract.functions.decimals().call()
        nonce = self.get_nonce()
        decimal_sell_quantity = self.to_dex_number(sell_quantity, decimals=decimals)
        decimal_min_buy_quantity = self.to_dex_number(min_buy_quantity, decimals=decimals)
        gas_price = int(self.w3.eth.gasPrice * 1.4)  # self.w3.eth.generate_gas_price()

        ## Create Transaction Inputs
        txn_inputs = {
            'from'      : self.address_wallet,
            'value'     : decimal_sell_quantity,
            'gas'       : 250000,  # 250000 looks to be much larger than any DEX uses on average
            'gasPrice'  : gas_price,  # stated in Wei  # from gas price calculator function set to w3 object in self.connect function
            'nonce'     : nonce,
        }

        ## Create Swap Transaction
        decimals = pool_contract.functions.decimals().call()
        txn = self.contract_router.functions.swapExactTokensForTokens(
            decimal_sell_quantity,       # amount of sell token to sell
            decimal_min_buy_quantity,    # min amount of buy token to receive
            [sell_token_contract_address, buy_token_contract_address],
            self.address_wallet, # my crypto bank account
            math.floor((datetime.utcnow() + timedelta(minutes=5)).timestamp()),
        ).buildTransaction(txn_inputs)

        ## Sign Transaction
        signed_txn = self.w3.eth.account.sign_transaction(txn, self.private_key)

        ## Return Info
        txn_inputs.update({
            'sell_quantity': sell_quantity,
            'min_buy_quantity': min_buy_quantity,
        })
        return signed_txn, txn_inputs


    def place_order(self, order: OrderClass):
        ## Record Order Placement Attempt
        self.logger.info(f'Placing order: {order}.')

        ## Get Order Info
        order_type      = order['order_type']
        buy_symbol      = order['buy_symbol']
        sell_symbol     = order['sell_symbol']
        buy_token_name  = order['notes'].get('buy_token_name', None)
        sell_token_name = order['notes'].get('sell_token_name', None)
        sell_quantity     = order['quantity_to_sell']
        buy_quantity      = order['quantity_to_buy']
        price_in_sell   = order['price_in_sell']
        slippage        = order['slippage']

        ## Check for Shit Order
        if order_type != 'spot':
            error = f'Only spot orders can be placed on PancakeSwapV2. Order: {order}.'
            self.logger.critical(error)  # critical because my code is shit
            raise Exception(error)

        ## Get Contract Addresses
        buy_token_contract_address  = self.CommsBlockchainDataProviders.get_contract_address(symbol=buy_symbol,  token_name=buy_token_name,  blockchain_name=self.blockchain_name, blockchain_net=self.blockchain_net, save=True, override=False)
        sell_token_contract_address = self.CommsBlockchainDataProviders.get_contract_address(symbol=sell_symbol, token_name=sell_token_name, blockchain_name=self.blockchain_name, blockchain_net=self.blockchain_net, save=True, override=False)
        pool_contract = self.get_pool_contract(self.get_pool_address(buy_token_contract_address, sell_token_contract_address))

        ## Convert Quantity if necessary
        if sell_quantity == 0:  # if True, sell_quantity is non-zero
            sell_quantity = self.contract_router.functions.getAmountsIn(
                (buy_quantity * slippage),  # THIS MAY HAVE TO BE AN INT  # amount_out, aka amount of tokens to receive after swap
                [sell_token_contract_address, buy_token_contract_address]  # [{sell_token}, {buy_token}] in example: https://github.com/manuelhb14/cake_uni_transaction_bot/
            )
        # else buy_quantity must equal zero, and sell_quantity is specified

        ## Create Signed Transaction
        signed_txn, txn_info = self.create_swap_txn(
            pool_contract=pool_contract,
            buy_token_contract_address=buy_token_contract_address,
            sell_token_contract_address=sell_token_contract_address,
            sell_quantity=sell_quantity,
            price_in_sell=price_in_sell,
            slippage=slippage
        )

        ## Send Transaction to Blockchain (place order)
        txn_hash = self.w3.eth.sendRawTransaction(signed_txn.rawTransaction)

        ## Record Order and Return Transaction Info
        self.logger.info(f'Transaction sent to blockchain: {txn_info}.')
        txn_info.update({'txn_hash': txn_hash})
        return txn_info



########################


    def x(self):
        latest = self.w3.eth.blockNumber
        transferEvents = self.contract_router.events.Transfer.createFilter(fromBlock=latest-1, toBlock=latest)
        ahh = transferEvents.get_all_entries()
        return ahh


    # def get_all_pairs(self, min_volume: float = None):
    #     '''
    #     Gets a list of all liquidity pools (pairs) open in PancakeSwap.

    #     Parameters
    #     ----------
    #     min_volume : float
    #         If not None, filters the list of liquidity pools for those with greater / equal volume to the requested volume.
    #     '''
    #     return


    # def check_for_pair(self, pair: str, stats: bool = False) -> Union[bool, None, dict]:
    #     '''
    #     Checks if the given pair has an open liquidity pool on PancakeSwap

    #     Parameters
    #     ----------
    #     pair : str
    #         In the format {UNDERLYING_ASSET/QUOTE_ASSET}. E.g. "BTC/USDT"
    #     stats : bool
    #         If True, and if pair exists, returns the following stats: price, pool volume, 24 hour volume.
    #         Otherwise, returns None.
    #     '''




if __name__ == '__main__':

    with open('hah.pkl', 'rb') as handle:
        d = pickle.load(handle)

    Comms = CommsDEXPancakeSwapV2(blockchain_net='mainnet')
    Comms.get_historical_trades(
        symbol_1='MBOX', symbol_2='WBNB',
        start_block=12095191, end_block=12097191
    )

    '''
    ------------------------------------------------------------------------------------------------------------------------------------------
    Test Code: Beginning
    ------------------------------------------------------------------------------------------------------------------------------------------
    '''
    print('Begin Testing')

    Comms = CommsDEXPancakeSwapV2(blockchain_net='testnet')

    symbol_1 = 'WBNB'  # 'CAKE'
    symbol_2 = 'HEDGE'  # 'BUSD'

    symbol_1_address = Comms.get_token_address(symbol=symbol_1)
    symbol_2_address = Comms.get_token_address(symbol=symbol_2)
    print('Contract Addresses'); print(f'{symbol_1}: {symbol_1_address}'); print(f'{symbol_2}: {symbol_2_address}'); print('Now check pancakeswapv2 logs'); print()

    pool_symbol_address = Comms.get_pool_address(symbol_1_address, symbol_2_address)
    print('Pool Address'); print(pool_symbol_address); print()

    pool_contract = Comms.get_pool_contract(pool_address=pool_symbol_address)
    print('Pool Contract'); print(pool_contract); print(type(pool_contract)); print()

    reserves = Comms.get_reserves(pool_contract)  # reserve0, reserve1, blockTimestampLast
    print('Reserves'); print(reserves); print(type(reserves)); print()

    current_price = Comms.get_current_price(buy_token_contract_address=symbol_1_address, sell_token_contract_address=symbol_2_address)
    print('Current Price'); print(f'{current_price} {symbol_1}/{symbol_2}'); print()

    end = datetime.utcnow()
    start = end - timedelta(seconds=10)
    historical_trades = Comms.get_historical_trades(symbol_1=symbol_1, symbol_2=symbol_2, start=start, end=end, save=False)
    print(f'Historical trades:\n {historical_trades}'); print()

    sell_one_symbol_2 = Comms.get_sell_amount(pool_contract=pool_contract, buy_token_contract_address=symbol_1_address, sell_token_contract_address=symbol_2_address, slippage=0, buy_amount=1)
    sell_one_symbol_1 = Comms.get_sell_amount(pool_contract=pool_contract, buy_token_contract_address=symbol_2_address, sell_token_contract_address=symbol_1_address, slippage=0, buy_amount=1)
    print(f'Amounts out in the PancakeSwap {symbol_1}-{symbol_2} pool'), print(f'1 {symbol_2} gives {sell_one_symbol_2} {symbol_1}'); print(f'1 {symbol_1} gives {sell_one_symbol_1} {symbol_2}'); print()

    buy_one_symbol_2 = Comms.get_buy_amount(pool_contract=pool_contract, buy_token_contract_address=symbol_2_address, sell_token_contract_address=symbol_1_address, slippage=0, sell_amount=1)
    buy_one_symbol_1 = Comms.get_buy_amount(pool_contract=pool_contract, buy_token_contract_address=symbol_1_address, sell_token_contract_address=symbol_2_address, slippage=0, sell_amount=1)
    print(f'Amounts out in the PancakeSwap {symbol_1}-{symbol_2} pool'), print(f'{buy_one_symbol_2} {symbol_2} costs 1 {symbol_1}'); print(f'{buy_one_symbol_1} {symbol_1} costs 1 {symbol_2}'); print()

    swap = Comms.create_swap_txn(pool_contract=pool_contract, buy_token_contract_address=symbol_1_address, sell_token_contract_address=symbol_2_address, sell_amount=23, price_in_sell=None, slippage=0.02)
    print(f'Swap for {symbol_1}-{symbol_2} pool'), print(swap); print()

    order = 'obviously not going to place an order in the test'
    print('Not testing "place_order" function right now.') # txn_info = Comms.place_order(order=order)

    '''
    ------------------------------------------------------------------------------------------------------------------------------------------
    Test Code: End
    ------------------------------------------------------------------------------------------------------------------------------------------
    '''

    ##################################################
    #####    MISC: Test Gas Price Generators    ######
    ##################################################
    # import time
    # Comms = CommsDEXPancakeSwapV2(blockchain_net='testnet')
    # x1 = time.time()
    # for _ in range(1):
    #     Comms.w3.eth.generate_gas_price()
    # x2 = time.time()
    # for _ in range(5):
    #     Comms.w3.eth.generate_gas_price()
    # x3 = time.time()
    # for _ in range(5):
    #     Comms.w3.eth.generate_gas_price()
    # x4 = time.time()
    # print(x2-x1)
    # print(x3-x2)
    # print(x4-x3)
    # time.sleep(1000)

    ## Other Gas Shit
    # from web3.gas_strategies.time_based import construct_time_based_gas_price_strategy
    # w3 = Web3(Web3.HTTPProvider(‘link’))
    # w3.eth.set_gas_price_strategy(construct_time_based_gas_price_strategy(max_wait_seconds=60, sample_size=120, probability=95))


    ##################################################
    #####         To Do: some shit to do        ######
    ##################################################

    # get function to find price: https://docs.uniswap.org/protocol/V2/concepts/core-concepts/oracles
    # read about frunt running: https://www.reddit.com/r/UniSwap/comments/m5l875/front_running_bot_is_getting_way_way_way/
    # due to front running, and due to exponential price increase shit, make twap function
    ### make get_price function using on_chain data - could also use TheGraph but if they go down ur fucked for what. Using the TheGraph comes with advantage of not having to do a few calculations yourself aka on computer you pay for.


    ## get decimal places
    ## fix getamountsout with the decimal

    ## Exceptions to capture:
    ##  web3.exceptions.BadFunctionCallOutput: can mean youre using a token address that doesnt have a working token
