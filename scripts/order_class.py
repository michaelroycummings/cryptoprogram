## Internal Modules
from scripts.utils import DataLoc, MyLogger

## External Libraries
from typing import List
import json


class OrderClass():

    def __init__(self):
        self.DataLoc = DataLoc()
        with open(self.DataLoc.File.CONFIG.value) as json_file:
            config = json.load(json_file)['OrderClass']
        self.logger = MyLogger().configure_logger(fileloc=self.DataLoc.Log.ORDER_CLASS.value)
        self.cexs = config['cexs']
        self.dexs = config['dexs']


    def make_order(self, buy_symbol: str, sell_symbol: str, order_type: str, asset: str, exchanges: List[str], quantity_to_buy: float = 0, quantity_to_sell: float = 0, price_in_sell: float = 0, notes: dict = {}):
        '''
        Parameters
        ----------
        buy_symbol : str
            The symbol of the asset to buy.
        sell_symbol : str
            The symbol of the asset to sell.
        order_type : str
            Can be 'market', 'limit'.  # UPGRADE: more order types means overriding: https://ccxt.readthedocs.io/en/latest/manual.html#overriding-unified-api-params
        asset : str
            Can be 'spot', 'future', 'perp'.
        quantity_to_buy : float
            The number of units of buy_symbol to trade.
        quantity_to_sell : float
            The number of units of sell_symbol to trade.
        price_in_sell : float
            The limit price, quoted in sell_symbol units. Ignored downstream if order_type is market.
        exchanges : List[str]
            Exchanges that the order can be places on.
        notes : dict
            Includes any fields that are not necessary for every order type and strategy.
            Examples:
                buy_token_name / sell_token_name for helping to find the contract address of a new symbol

        Functionality
        -------------
        - To achieve a specific quantity for both quantity_to_buy and quantity_to_sell, specify one and include a price_in_sell denomination.
          Do NOT include both quantities as this + the price argument can contradict and the code is set to throw an error.
        - Is lazy with exchange parsing: if no known exchanges are passed, no error will be thrown.  # speed
        '''
        ## Check Bad Inputs - Order Type
        if order_type not in ['market', 'limit']:
            error = f'Requested "order_type" not recognised: {order_type}. Type: {type(order_type)}.'
            self.logger.debug(error)
            raise Exception(error)
        # if side not in ['buy', 'sell']:
        #     error = f'Requested "side" not recognised: {side}. Type: {type(side)}.'
        #     self.logger.debug(error)
        #     raise Exception(error)
        ## Check Bad Inputs - Asset
        if asset not in ['spot', 'future', 'perp']:
            error = f'Requested "asset" not recognised: {asset}. Type: {type(asset)}.'
            self.logger.debug(error)
            raise Exception(error)
        ## Check Bad Inputs - Exchanges
        if not isinstance(exchanges, list):
            if isinstance(exchanges, str):
                exchanges = [exchanges]
            else:
                error = f'Requested "exchanges" is not a list nor a string: {exchanges}. Type: {type(exchanges)}.'
                self.logger.debug(error)
                raise Exception(error)
        ## Check Bad Inputs - Quantity
        if (quantity_to_buy == 0) and (quantity_to_sell == 0):
            error = f'Both "quantity_to_buy" and "quantity_to_sell" cannot have a zero value. quantity_to_buy: {quantity_to_buy}. quantity_to_sell: {quantity_to_sell}. Type: {[type(quantity) for quantity in [quantity_to_buy, quantity_to_sell]]}.'
            self.logger.debug(error)
            raise Exception(error)
        elif (quantity_to_buy != 0) and (quantity_to_sell != 0):
            error = f'Both "quantity_to_buy" and "quantity_to_sell" cannot have non_zero values. quantity_to_buy: {quantity_to_buy}. quantity_to_sell: {quantity_to_sell}. Type: {[type(quantity) for quantity in [quantity_to_buy, quantity_to_sell]]}.'
            self.logger.debug(error)
            raise Exception(error)
        ## Check Bad Inputs - Price
        if order_type == 'limit' and price_in_sell == 0:
            error = f'Requested "price" cannot be zero for a limit order.'
            self.logger.debug(error)
            raise Exception(error)
        ## Check Bad Inputs - Notes
        if not isinstance(notes, dict):
            error = f'Requested "notes" is not dict: {notes}. Type: {type(notes)}.'
            self.logger.debug(error)
            raise Exception(error)
        ## Clean Inputs
        buy_symbol = buy_symbol.upper()
        sell_symbol = sell_symbol.upper()
        if 'cex' in exchanges:
            exchanges.extend(self.cexs)
        if 'dex' in exchanges:
            exchanges.extend(self.dexs)

        ## Return Order
        order = {
            'buy_symbol'       : buy_symbol,   # upper case
            'sell_symbol'      : sell_symbol,  # upper case
            'order_type'       : order_type,
            'asset'            : asset,
            'quantity_to_buy'  : quantity_to_buy,
            'quantity_to_sell' : quantity_to_sell,
            'price_in_sell'    : price_in_sell,    # quoted in sell asset per buy asset. E.g. selling USDT for BTC, the price would be x USDT/BTC
            'exchanges'        : exchanges,
            'notes'            : notes,
            'attempt_count'    : 0  # first attempt; following python numbering where zero is the first item (attempt, in this case)
        }
        self.logger.debug(f'Order made: {order}.')
        return order