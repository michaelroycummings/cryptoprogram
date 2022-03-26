## Internal Modules
from scripts.utils import DataLoc, MyLogger
from scripts.order_class import OrderClass
from scripts.comms_twitter import CommsTwitter
from scripts.strat_coin_listing import StratCoinListing

## External Libraries
import queue



def run_trader():
    '''
    Activity Flow
    -------------
    Strategy - Coin Listing:
        Twitter API  ]---(tweets)--->  CommsTwitter  ]---(tweet)--->  StratCoinListing  ---(order specs)--->  OrderClass  ---(order dict)--->  order_queue
    Order Handler
        order_queue  ]---(order dict)--->  OrderHandler  ---(order dict)---> CommsBinance     ---(order request via REST endpoint)--->  Binance
                                                         ---(order dict)---> CommsPancakeSwap ---(order request via REST endpoint)--->  PancakeSwap
    '''

    ## Create Order Queue
    order_queue = queue.Queue()

    ## Start Strategies
    tweet_queue = queue.Queue()
    exit_signal = 'exit signal code: 8m3hxg087mg4hc58g4c5ehc5g34o34'
    # It may be an extremely retarded idea to allow anyone on twitter terminate this function if they know the exit code.
    # Is the speediness of checking one queue worth it?
    thread1 = StratCoinListing(order_queue=order_queue, tweet_queue=tweet_queue).run_strat()