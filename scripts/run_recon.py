## Internal Modules
from scripts.utils import DataLoc
from scripts.utils import MyLogger

## External Libraries
from pathlib import Path
from os.path import basename
import os
import json


class RunRecon():
    '''
    Meant to be run by a user to start recon of the strategies listed in this function.

    UPGRADE:
        - run function will need to use CronTab or multiprocessing/multithreading
          once multiple strategies need recon simultaneously.
    '''

    def __init__(self):
        self.DataLoc = DataLoc()
        with open(self.DataLoc.File.CONFIG.value) as json_file:
            config = json.load(json_file)[self.__class__.__name__]
        self.logger = MyLogger().configure_logger(fileloc=self.DataLoc.Log.RUN_RECON.value)


    def run(self):
        ''' Meant to be run by a user to start recon of the strategies listed in this function. '''
        scripts_folder_loc = DataLoc().Folder.SCRIPTS.value

        ## Launch ReconCoinListing
        print('Running Recon for Strategy: CoinListing.', flush=True)
        run_script_command = f'cd {Path(scripts_folder_loc).parent} && python -m {basename(Path(scripts_folder_loc))}.recon_coin_listing'
        try:
            os.system(run_script_command)
        except Exception as e:
            message = 'Recon stopped running do to below error.'
            self.logger.exception(message)
            print(f'{message} /n{e}')
        print('Recon ended.', flush=True)

        return


if __name__ == '__main__':
    RunRecon.run()