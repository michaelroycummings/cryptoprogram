# New Coin Listing Trader

**Development state**: *code and documentation for the below scripts are stable.*
- `run_recon.py`
- `run_coin_listing.py`
- `comms_blockchain_bsc.py`
- `comms_blockchain_data_providers.py`
- `comms_cex_binance.py`
- `comms_dex_pancakeswapv2.py`
- `utils.py `
         
           
## Functionality

### Strategies

#### New Coin Listing

Strategy based on anecdotal observations a delay between the announcement that Binance will list a new coin, and price action of that coin's current markets (mostly for low-volume coins or coins only listed on DEXs).

The `recon_coin_listing.py` script looks for new coin listing announcements on twitter, then records price data for 4 hours before and after the announcement, for each CEX and DEX that currently lists the coin.

Currenty has capability for:
- **New coin listing announcements on Twitter**: Binance
- **Price data recording**: PancakeswapV2

Will add capability for:
- **New coin listing announcements on Twitter**: OKX, Coinbase, Crypto.com, FTX, Huobi
- **Price data recording**: UniswapV3, UniswapV2, Sushiswap
      
      
### Querying Data

Currently iteracts with:
- Binance Smart Chain
- PancakeswapV2 smart contracts
- BscScan, CoinMarketCap, CoinGecko

Will add functionality for:
- Ethereum blockchain
- UniswapV3, UniswapV2, Sushiswap smart contracts
- Etherscan
      
      
      
      
## Understanding the Code

As the trading program grows, this section will provide an overview of data flow between scripts, allowing users to jump straight to the section of interest, and get a better understanding of class methods' operations via the docstrings.

### Runtime Flow

`run_recon.py` will run all the recon strategy scripts. Check out `
                    
### Config Files
- `contract_addresses.json` is a manual-entry-only file that stores addresses for the contracts whose functions are used in this program. Some addresses are for tokens (aka wbnb) and will also be found in `token_addresses.json`
- `abi.json` is a manual-entry-only file that stores the abi config information for smart contracts in the `contract_addresses.json` config file.
    - Could change this to automated-entry with no forseeable downside.
- `token_addresses.json` is an automated-entry file that stores token addresses.
- `wallets.json` (...heh) is manual-entry-only file storing the public keys that the program will se to trade with.
    - Safu, automated private key use is complex, requires multiple remote boxes, and is not yet the focus of the project.
