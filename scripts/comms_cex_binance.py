## Internal Modules
from scripts.utils import DataLoc, MyLogger, handle_ccxt_error
from scripts.order_class import OrderClass

## External Libraries
import ccxt
import json


class CommsCEXBinance():

    def __init__(self):
        self.DataLoc = DataLoc()
        with open(self.DataLoc.File.CONFIG.value) as json_file:
            config = json.load(json_file)[self.__class__.__name__]
        self.logger = MyLogger().configure_logger(fileloc=self.DataLoc.Log.COMMS_CEX_BINANCE.value)
        api_key_info = {k: config[k] for k in ['apiKey', 'secret']}
        self.ex_spot  = ccxt.binance(api_key_info)       # I think you want to have ONLY one instance of this to track rate limits
        self.ex_coinm = ccxt.binancecoinm(api_key_info)  # ''
        self.ex_usdxm  = ccxt.binanceusdm(api_key_info)
        self.future_quote_fiat = ['usd']
        self.future_quote_stablecoins = ['usdt']


    def _print_annoying_shit(self):
        self.ex_spot.load_markets()
        market = self.ex_spot.market('BNB/USDT')
        usable_quantity = self.ex_spot.amount_to_precision('BNB/USDT', 0.001)
        print(usable_quantity)
        print(market['limits']['amount']['min'])
        print(market['limits']['amount']['max'])
        print(market['precision'])
        print(market['precision']['amount'])  # max number of decimal places I can use
        print(market['limits']['cost']['min'])


    def make_path(self, order: dict):
        '''
        Makes on or two orders to buy and sell the requested assets using pairs that actually exist.
            Only use SYMBOL/USDT pairs because theyre the most liquid and most abundant and I'm not doing arb right now.
            For limit order's split the difference between the market price and limit price equally between the two hops.
        '''
        buy_symbol       = order['buy_symbol']
        sell_symbol      = order['sell_symbol']
        order_type       = order['order_type']
        price_in_sell    = order['price_in_sell']
        quantity_to_buy  = order['quantity_to_buy']
        quantity_to_sell = order['quantity_to_sell']

        ## Convert quantity_to_sell to quantity_to_buy
        market_price = None  # so that it's not updated twice, downstream
        if quantity_to_buy == 0:  # CEXs expect quantity in buy_symbol units, so I can't directly specify quantity_to_sell
            if order_type == 'market':
                market_price = self.get_market_price()
                quantity_to_buy = quantity_to_sell / market_price
            else:
                quantity_to_buy = quantity_to_sell / price_in_sell

        ## Make Binance Orders Path
        if sell_symbol == ['usdt', 'usd']:  # only one traded needed
            price_in_quote_asset = price_in_sell  # sell_symbol is quote symbol so price_in_sell is fine to use
            orders_path = [
                {
                    'symbol' : f'{buy_symbol}/{sell_symbol}',
                    'type'   : order_type,
                    'side'   : 'buy',
                    'amount' : quantity_to_buy,
                    'price'  : price_in_quote_asset
                }
            ]
        elif buy_symbol in ['usdt', 'usd']:  # only one traded needed
            if order_type == 'market':
                if market_price is None:
                    market_price = self.get_market_price(pair=f'{sell_symbol}/{buy_symbol}')
                price_in_quote_asset = market_price  # Binance expects price in quote asset
            elif order_type == 'limit':
                price_in_quote_asset = 1 / price_in_sell  # Binance expects price in quote asset
            else:
                error = f'{self.__class__.__name__} can only handle market and limit orders. Order: {order}.'
                self.logger.critical(error)
                raise Exception(error)
            orders_path = [
                {
                    'symbol' : f'{sell_symbol}/{buy_symbol}',
                    'type'   : order_type,
                    'side'   : 'sell',
                    'amount' : quantity_to_buy,
                    'price'  : price_in_quote_asset
                }
            ]
        else:  # two trades needed
            if order_type == 'market':
                trade_1_price_in_quote_asset = self.get_market_price(pair=f'{sell_symbol}/USDT')  # Binance expects price in quote asset which is USDT
                trade_2_price_in_quote_asset = self.get_market_price(pair=f'{buy_symbol}/USDT')   # Binance expects price in quote asset which is USDT
                quantity_of_USDT_to_buy = self.get_market_price(pair=f'{buy_symbol}/USDT') * quantity_to_buy
            elif order_type == 'limit':  # split the "limit price difference from market price" equally between the two trades
                if market_price is None:
                    market_price = self.get_market_price(pair=f'{buy_symbol}/{sell_symbol}')
                sell_symbol_value_of_market_price_minus_limit_price = market_price - price_in_sell  # this will hopefully always be positive... if I thought about this properly
                usdt_value_of_market_price_minus_limit_price = sell_symbol_value_of_market_price_minus_limit_price * self.get_market_price(pair=f'{sell_symbol}/USDT')
                trade_1_price_in_quote_asset = self.get_market_price(pair=f'{sell_symbol}/USDT') - usdt_value_of_market_price_minus_limit_price / 2  # Binance expects price in quote asset which is USDT
                trade_2_price_in_quote_asset = self.get_market_price(pair=f'{buy_symbol}/USDT') - usdt_value_of_market_price_minus_limit_price / 2   # Binance expects price in quote asset which is USDT
                quantity_of_USDT_to_buy = price_in_sell * quantity_to_buy
            else:
                error = f'{self.__class__.__name__} can only handle market and limit orders. Order: {order}.'
                self.logger.critical(error)
                raise Exception(error)
            orders_path = [
                {
                    'symbol' : f'{sell_symbol}/USDT',
                    'type'   : order_type,
                    'side'   : 'sell',
                    'amount' : quantity_of_USDT_to_buy,
                    'price'  : trade_1_price_in_quote_asset
                },
                {
                    'symbol' : f'{buy_symbol}/USDT',
                    'type'   : order_type,
                    'side'   : 'buy',
                    'amount' : quantity_to_buy,
                    'price'  : trade_2_price_in_quote_asset
                }
            ]
        return orders_path


    @handle_ccxt_error
    def place_order(self, order: OrderClass):
        ## Record Order Placement Attempt
        self.logger.info(f'Placing order: {order}.')

        ## Prep Order Path
        order_type = order['order_type']
        binance_orders = self.make_path_of_orders(order)

        ## Determine exchange api endpoint to use:
        if order_type == 'spot':
            exchange_endpoint = lambda order_kwargs: self.ex_spot.create_order(**order_kwargs)
        elif order_type == 'perp':
            if any([asset in self.future_quote_fiat for asset in [order['buy_symbol'], order['sell_symbol']]]):
                exchange_endpoint = lambda order_kwargs: self.ex_usdxm.create_order(**order_kwargs)
            else:
                exchange_endpoint = lambda order_kwargs: self.ex_usdxm.create_order(**order_kwargs)

        ## Place Order
        self.logger.debug(f'About to execute the following order path\n{binance_orders}')
        for order_kwargs in binance_orders:
            order_feedback = exchange_endpoint(order_kwargs)

        ## Record Order Placement
        self.logger.info(f'Order placed: {order_feedback}.')


if __name__ == '__main__':
    CommsCEXBinance()._print_annoying_shit()