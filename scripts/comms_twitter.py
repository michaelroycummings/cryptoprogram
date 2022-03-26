## Internal Modules
from scripts.utils import DataLoc, MyLogger, catch_and_log_exception

## External Libraries
from threading import TIMEOUT_MAX
from typing import Union
from pandas.core.frame import DataFrame
import requests
import json
import multiprocessing  # used for multiprocessing Processes, Queues, the Manager
import queue  # used for Exception: queue.Empty
import pickle
import pandas as pd
import time
from pathlib import Path
import pytz
from datetime import datetime, timedelta, timezone
import os



class CommsTwitter():
    '''
    Understanding Tweets
    --------------------
    Tweet: data posted in a tweet object.
    Retweet: a parent tweet that contains nothing but another tweet embedded in the parent.
    Quoted tweet: a retweet with added data (e.g a retweet with the user's own comment on top)
    Reply: data posted within another tweet's object.


    Useful Links
    ------------
    Twitter Docs:
        - Tweet Object, all fields
          https://developer.twitter.com/en/docs/twitter-api/data-dictionary/object-model/tweet
        - Creating streaming rules
          https://developer.twitter.com/en/docs/twitter-api/tweets/filtered-stream/integrate/build-a-rule#list
    Twitter GitHub:
        - Sample Code
          https://github.com/twitterdev/Twitter-API-v2-sample-code
    '''

    def __init__(self, log_queue: Union[multiprocessing.Queue, None] = None):

        self.DataLoc = DataLoc()
        with open(self.DataLoc.File.CONFIG.value) as json_file:
            config = json.load(json_file)['CommsTwitter']
        self.output_data_loc = self.DataLoc.Folder.DATA_TWEETS.value
        self.base_url = config['base_url']
        self.api_key = config['api_key']
        self.api_secret_key = config['api_secret_key']
        self.bearer_token = config['bearer_token']
        self.twitter_fields = {
            'full': {
                'tweet.fields' : 'created_at,referenced_tweets,in_reply_to_user_id,author_id,id,text,source,conversation_id,public_metrics',
                'user.fields'  : 'name,id,username,verified,public_metrics',
                'media.fields' : 'url',
                'expansions'   : 'in_reply_to_user_id,referenced_tweets.id,referenced_tweets.id.author_id'
            },
        }
        self.MyLogger = MyLogger(log_queue=log_queue)
        self.logger = self.MyLogger.configure_logger(fileloc=self.DataLoc.Log.COMMS_TWITTER.value)
        self.request_counter = 0


    ########################################
    ####        Utility Functions       ####
    ########################################


    def bearer_oauth(self, r):
        """Method required by bearer token authentication."""
        r.headers["Authorization"] = f"Bearer {self.bearer_token}"
        r.headers["User-Agent"] = "v2UserMentionsPython"
        return r


    def call_endpoint(self, type: str, url: str, headers: dict = None, payload: dict = None, stream: bool = False, exception_str: str = 'Cannot get rules'):
        while True:
            self.request_counter += 1
            if self.request_counter % 10 == 0:
                print(f'Request counter: {self.request_counter}')
            if type == 'get':
                response = requests.get(url, auth=self.bearer_oauth, headers=headers, params=payload, stream=stream)
            elif type == 'post':
                response = requests.post(url, auth=self.bearer_oauth, headers=headers, json=payload)
            if response.status_code in [200, 201]:
                break
            else:
                if response.status_code == 429:
                    print('Waiting 15 min as rate limit has been reached...')
                    time.sleep(5*60)
                    print('Waiting left: 10 min')
                    time.sleep(5*60)
                    print('Waiting left: 5 min')
                    time.sleep(5*60 + 10)
                    print('Rate limit should be refreshed now... requesting data again.')
                else:
                    raise Exception(f'{exception_str}: {response.status_code} {response.text}')
        return response


    def get_user_id(self, user_handle: str):
        url = f'{self.base_url}/users/by/username/{user_handle}'
        response = self.call_endpoint(type='get', url=url)
        return response.json()['data']['id']


    def get_filename(self, query_name: str, dt: datetime, location: bool = False):
        filename = f'raw_tweets-{query_name}-{dt.strftime("%Y_%m_%d")}.pkl'
        if location:
            return f'{self.output_data_loc}/{filename}'
        else:
            return filename


    def get_downloaded_tweets(self, query_name: str, start: datetime, end: datetime):
        '''
        Parameters
        ----------
        query_name : str
            Must match a query_name in CommsTwitter otherwise there will be no downloaded tweet files for it.
        '''
        output_d = {}
        days = pd.date_range(start=start, end=end, freq='d')
        for day in days:
            fileloc = self.get_filename(query_name=query_name, dt=day, location=True)
            ## Get Raw, Formatted Tweet Data
            with open(fileloc, 'rb') as handle:
                d = pickle.load(handle)
                formatted_tweets = d['data']
                output_d.update(formatted_tweets)
        return output_d


    @staticmethod
    def parse_tweet_datetime(string: str):
        return datetime.strptime(string.replace('.000Z',''), '%Y-%m-%dT%H:%M:%S')


    @staticmethod
    def parse_user(d: dict) -> dict:
        return {
            'id': d['id'],
            'name': d['name'],
            'username': d['username'],
            'verified': d['verified'],
            'follower_count': d['public_metrics']['followers_count'],
            'following_count': d['public_metrics']['following_count'],
            'tweet_count': d['public_metrics']['tweet_count'],
            'listed_count': d['public_metrics']['listed_count'],
        }


    def parse_tweet(self, d: dict, all_user_data: dict) -> dict:
        return {
            'text': d['text'],  # includes entire text; does not truncate at 140 characters
            'source': d['source'],
            'created_at': self.parse_tweet_datetime(d['created_at']),
            'conversation_id': d['conversation_id'],
            'author_data': self.parse_user(all_user_data[d['author_id']]),
            'retweet_count': d['public_metrics']['retweet_count'],
            'reply_count': d['public_metrics']['reply_count'],
            'like_count': d['public_metrics']['like_count'],
            'quote_count': d['public_metrics']['quote_count'],
        }


    def parse_tweet_response(self, response):
        ## Get Data Objects to Minimize Repetitive Indexing
        try:  # querying the historical endpoint will usually return multiple tweets
            all_parent_tweet_data = {d['id']: d for d in response['data']}
        except TypeError:  # querying the stream endpoint will return one tweet at a time
            all_parent_tweet_data = {response['data']['id']: response['data']}
        all_tweet_data = {d['id']: d for d in response['includes'].get('tweets', [])}
        all_user_data = {d['id']: d for d in response['includes']['users']}
        parsed_all_tweets = {}

        ## Make Parsed Data Objects for this Patrent Tweet
        for parent_tweet_id, parent_tweet_data in all_parent_tweet_data.items():
            parsed_tweet = {
                'genesis': None,
                'reply': None,
                'retweet': None,
                'quote': None,
            }

            ## Add Data for Genesis Tweet
            reference_tweets = [d['type'] for d in parent_tweet_data.get('referenced_tweets', [])]
            if ('replied_to' in reference_tweets) or ('retweeted' in reference_tweets):
                pass  # replies and retweets have no genesis tweet
            else:
                parsed_tweet.update({'genesis': self.parse_tweet(parent_tweet_data, all_user_data=all_user_data)})

            ## Add Data for Referenced Tweets
            for ref in parent_tweet_data.get('referenced_tweets', []):
                tweet_relationship = ref['type']  # will be one of ['replied_to', 'retweeted', 'quoted']
                if tweet_relationship == 'replied_to':
                    ref_data = {
                        'conversation_id': ref['id'],
                        'in_reply_to_user_id': parent_tweet_data['in_reply_to_user_id'],
                    }
                    reply_tweet = self.parse_tweet(parent_tweet_data, all_user_data=all_user_data)  # Twitter puts reply data in the parent dict object and only puts 'id' and 'in_reply_to_id' in the replied_to dict object
                    reply_tweet.update(ref_data)
                    parsed_tweet.update({'reply': reply_tweet})
                elif tweet_relationship == 'retweeted':
                    ref_data = all_tweet_data[ref['id']]  # Twitter only returns text and expanded fields for quoted and retweeted tweets, not to the original message of reply tweets
                    parsed_tweet.update({'retweet': self.parse_tweet(ref_data, all_user_data=all_user_data)})
                elif tweet_relationship == 'quoted':
                    ref_data = all_tweet_data[ref['id']]  # Twitter only returns text and expanded fields for quoted and retweeted tweets, not to the original message of reply tweets
                    parsed_tweet.update({'quote': self.parse_tweet(ref_data, all_user_data=all_user_data)})
                else:
                    self.logger.critical(f'NEW REFERENCE TWEET TYPE FOUND: {tweet_relationship}. Type: {type(tweet_relationship)}.')
            ## Add this tweet to all tweets object
            parsed_all_tweets.update({parent_tweet_id: parsed_tweet})
        return parsed_all_tweets


    def make_query(self, query_name: str, pull_method: str, coin: Union[str, None] = None, start_dt: Union[datetime, None] = None, end_dt: Union[datetime, None] = None) -> list:
        '''
        Parameters
        ----------
        pull_method : str:
            Can be 'stream', 'historical'

        Twitter Query Limitations:
            If you are using the Standard product track at the Basic access level, your query can be 512 characters long.
            If you are using the Academic Research product track, your query can be 1024 characters long.
            Several operators are reserved for the Academic Research product track.

        NOTE: {'query': 'btc or bitcoin'} will grab tweets and retweets with BTC, btc, Bitcoin, bitcoin, #BTC, #Bitcoin, etc.
        '''
        if pull_method == 'historical':
            time_format = '%Y-%m-%dT%H:%M:%SZ'
            start = start_dt.strftime(time_format)
            end = end_dt.strftime(time_format)

            if query_name == 'by_crypto_leaders':
                queries = []
                from scripts.crypto_leaders import CryptoLeaders
                loc_info = CryptoLeaders()
                with open(f'{loc_info.output_data_loc}/{loc_info.production_filename}', 'rb') as handle:
                    d = pickle.load(handle)
                account_handles = [f'from:{account_handle}' for account_handle in d.keys()]
                for partial_handles in [account_handles[i:i + 25] for i in range(0, len(account_handles), 25)]:
                    query_string = ' OR '.join(partial_handles)
                    query = {
                        'query': query_string,
                        'start_time': start,
                        'end_time': end
                    }
                    queries.append(query)

            elif query_name == 'replyto_crypto_leaders':
                queries = []
                from scripts.crypto_leaders import CryptoLeaders
                loc_info = CryptoLeaders()
                with open(f'{loc_info.output_data_loc}/{loc_info.production_filename}', 'rb') as handle:
                    d = pickle.load(handle)
                account_handles = [f'to:{account_handle}' for account_handle in d.keys()]
                for partial_handles in [account_handles[i:i + 25] for i in range(0, len(account_handles), 25)]:
                    query_string = ' OR '.join(partial_handles)
                    query = {
                        'query': query_string,
                        'start_time': start,
                        'end_time': end
                    }
                    queries.append(query)

            elif query_name == 'ltc_walmart_fake_news':
                query = {
                    'query': '(ltc OR litecoin) walmart',
                    'start_time': '2021-09-13T13:00:00Z',
                    'end_time': '2021-09-13T23:00:00Z'
                }

        elif pull_method == 'stream':

            if query_name == 'by_crypto_leaders':
                queries = []
                from scripts.crypto_leaders import CryptoLeaders
                loc_info = CryptoLeaders()
                with open(f'{loc_info.output_data_loc}/{loc_info.production_filename}', 'rb') as handle:
                    d = pickle.load(handle)
                account_handles = [f'from:{account_handle}' for account_handle in d.keys()]
                for partial_handles in [account_handles[i:i + 25] for i in range(0, len(account_handles), 25)]:
                    query_string = ' OR '.join(partial_handles)
                    query = {"value": query_string}
                    queries.append(query)

            elif query_name == 'replyto_crypto_leaders':
                queries = []
                from scripts.crypto_leaders import CryptoLeaders
                loc_info = CryptoLeaders()
                with open(f'{loc_info.output_data_loc}/{loc_info.production_filename}', 'rb') as handle:
                    d = pickle.load(handle)
                account_handles = [f'to:{account_handle}' for account_handle in d.keys()]
                for partial_handles in [account_handles[i:i + 25] for i in range(0, len(account_handles), 25)]:
                    query_string = ' OR '.join(partial_handles)
                    query = {"value": query_string}
                    queries.append(query)

            elif query_name == 'eth-ltc-bch_mentions':
                query_string = 'eth OR ltc OR bch'
                queries = [{"value": query_string}]

            elif query_name == 'new_coin_listing':
                exchange_twitter_usernames = ['binance']
                partial_strings = [f'from:{account_handle}' for account_handle in exchange_twitter_usernames]
                query_string = ' OR '.join(partial_strings)
                queries = [{"value": query_string}]

        return queries


    ########################################
    ####      Historical: by Query      ####
    ########################################


    def get_specific_tweet(self, tweet_id: str):
        url = f'{self.base_url}/tweets/{tweet_id}'
        payload = {
            'tweet.fields': 'created_at,referenced_tweets,in_reply_to_user_id',
            'expansions': 'in_reply_to_user_id,referenced_tweets.id,referenced_tweets.id.author_id'
        }
        response = self.call_endpoint(type='get', url=url, payload=payload).json()
        return response


    def get_historical(self, query_params: dict):
        '''
        Twitter's 'search tweets' endpoint.
            NOTE: operators will not match on the content from the original Tweet that was quoted, but will match on the content included in the Quote Tweet.
            NOTE: Twitter allows querying of up to 1 week of recent tweets for non-academic accounts.
                Academic accounts get access to all tweet from March 2006 onwards.
        '''
        url = f'{self.base_url}/tweets/search/recent'
        payload = {
            'max_results': 100,
            'next_token': None,
        }
        payload.update(self.twitter_fields['full'])  # add query params to grab lots of data about each tweet
        payload.update(query_params)  # add query params to grab specific tweets from Twitter's vast 1-week database
        tweets_dict = {}
        while True:
            ## Query Twitter
            response = self.call_endpoint(type='get', url=url, payload=payload).json()

            ## Check for Empty, 200 Twitter Response
            if response.get('data', None) is None:
                print(f'Empty response from twitter: {response}.')
            else:
                ## Clean Data
                more_tweets = self.parse_tweet_response(response)
                tweets_dict.update(more_tweets)  # UPGRADE: ignoring 'referenced_tweets' and 'in_reply_to_user_id' for now

            next_page_token = response['meta'].get('next_token', None)  #         next_page_token = response['meta'].get('next_token', response['meta'].get('pagination_token', None))

            ## Query Again?
            if next_page_token is None:
                break
            else:
                payload.update({'next_token': next_page_token})
        return tweets_dict


    ########################################
    ####  Historical: by Specific User  ####
    ########################################


    def get_user_timeline(self, user_id: str):
        '''
        Explore one user's Timeline Tweets
            Twitter will give a max of 3200 historical tweets via pagination.
        '''
        ## Prep the Query
        url = f'{self.base_url}/users/{user_id}/tweets'
        payload = {
            'max_results': 100,
            'tweet.fields': 'created_at,referenced_tweets,in_reply_to_user_id',
            'pagination_token': None
        }
        tweets_dict = {}
        next_page_token = None
        while True:
            ## Query Twitter
            response = self.call_endpoint(type='get', url=url, payload=payload).json()

            ## Clean Data
            clean_datetime = lambda string: datetime.strptime(string.replace('.000Z',''), '%Y-%m-%dT%H:%M:%S')
            more_tweets = {d['id']: (clean_datetime(d['created_at']), d['text']) for d in response['data']}
            tweets_dict.update(more_tweets)  # UPGRADE: ignoring 'referenced_tweets' and 'in_reply_to_user_id' for now
            next_page_token = response['meta'].get('next_token', None)

            ## Query Again?
            if next_page_token is None:
                break
            else:
                payload.update({'pagination_token': next_page_token})
        return tweets_dict


    def get_user_mentions(self, user_id: str):
        ''' Explore one user's Mentions (tweets by other users) '''
        url = f'{self.base_url}/users/{user_id}/mentions'
        response = self.call_endpoint(type='get', url=url)
        return response.json()


    ########################################
    ####      Real-time: by Query       ####
    ########################################


    def get_streaming_rules(self):
        url = f'{self.base_url}/tweets/search/stream/rules'
        response = self.call_endpoint(type='get', url=url, exception_str='Cannot get rules')
        data = response.json()
        self.logger.info(f'CURRENT STREAMING RULES: {data}')
        return data


    def delete_streaming_rules(self, rules: dict = None):
        if rules is None:
            rules = self.get_streaming_rules()
        if rules is None or "data" not in rules:
            return None
        ids = list(map(lambda rule: rule["id"], rules["data"]))
        payload = {"delete": {"ids": ids}}
        url = f'{self.base_url}/tweets/search/stream/rules'
        response = self.call_endpoint(type='post', url=url, payload=payload, exception_str='Cannot delete rules')
        data = response.json()
        self.logger.info(f'DELETING STREAMING RULES: {data}')
        return data


    def set_streaming_rules(self, rules: list = None):
        payload = {"add": rules}
        url = f'{self.base_url}/tweets/search/stream/rules'
        response = self.call_endpoint(type='post', url=url, payload=payload, exception_str='Cannot add rules')
        data = response.json()
        self.logger.info(f'SETTING STREAMING RULES: {data}')
        return data


    def _query_endless_stream(self, tweet_queue: multiprocessing.Queue):  # , rest_seconds: int
        '''
        Twitter's 'filtered stream' endpoint.
            NOTE: filtered stream will match on both the content from the original Tweet that was quoted and the Quote Tweet's content.
        '''
        url = f'{self.base_url}/tweets/search/stream'
        payload = {}
        payload.update(self.twitter_fields['full'])
        response = self.call_endpoint(type='get', url=url, payload=payload, stream=True, exception_str='Cannot get stream')
        for response_line in response.iter_lines():  # this is basically a "while True" statement, but it rests until a tweet is pushed to it
            if response_line:  # if False, response_line equals an empty b-string (for some reason they sometimes send this)
                tweet_data = json.loads(response_line)
                tweet_queue.put(tweet_data)


    def _clean_endless_stream(self,
        terminate_streaming: bool, raw_tweet_queue: multiprocessing.Queue,
        formatted_tweet_queue: Union[multiprocessing.Queue, None] = None,
        formatted_tweet_dict: Union[dict, None] = None
        ):
        ## Check Inputs
        if formatted_tweet_queue is None and formatted_tweet_dict is None:
            error = f'One of the arguments "formatted_tweet_queue" and "formatted_tweet_dict" must be provided. They are both currently NoneType.'
            self.logger.critical(error)
            raise Exception(error)
        ## Listen for Raw Tweets and Format them
        while True:
            ## Terminate Process
            if bool(terminate_streaming.value) is True:  # is False for 0 and True for 1
                self.logger.info('Kill signal received, terminating process.')
                break
            ## Get New Tweets
            try:
                new_tweet = raw_tweet_queue.get(timeout=2)
                formatted_tweet = self.parse_tweet_response(new_tweet)
                if formatted_tweet_queue is not None:
                    formatted_tweet_queue.put(formatted_tweet)
                if formatted_tweet_dict is not None:
                    formatted_tweet_dict.update(formatted_tweet)
            except queue.Empty:
                pass
        return


    def get_stream(self, kill_queue: Union[multiprocessing.Queue, None] = None, formatted_tweet_queue: Union[multiprocessing.Queue, None] = None):
        ## Process-Shareable Variables
        terminate_streaming = multiprocessing.Value('i', 0)  # aka False
        tweet_queue = multiprocessing.Queue()
        ## Output Tweets can be accumulated in a dict and return at function termination,
        ## or can be added to a multiprocessing.Queue after each tweet is found
        if formatted_tweet_queue is None:
            manager = multiprocessing.Manager()
            formatted_tweet_dict = manager.dict()
        else:
            formatted_tweet_dict = None
        ## Function can be terminated via user input (if kill_queue is not given),
        ## or with a 'kill_signal' given to kill_queue
        if kill_queue is None:
            user_termination = True
        else:
            user_termination = False

        ## Create and Run Processes
        p_streamer = multiprocessing.Process(name='p_streamer', target=self._query_endless_stream, kwargs={'tweet_queue': tweet_queue})  # listens for tweets from twitter's API and adds them to the queue to be formatted
        p_collector = multiprocessing.Process(name='p_collector', target=self._clean_endless_stream, kwargs={  # listens for tweets from the queue, formats them, and adds them to a variable shared with the main process
            'terminate_streaming': terminate_streaming,
            'raw_tweet_queue': tweet_queue,
            'formatted_tweet_dict': formatted_tweet_dict,
            'formatted_tweet_queue': formatted_tweet_queue
        })
        self.logger.debug('Starting stream querying.')
        p_streamer.start()
        p_collector.start()

        ## Terminate Function
        if user_termination is True:
            ## End Tweet Streaming and Collection when user specifies
            while True:
                user_input = input('Type "kill" to end tweet streaming and processing, and return the collected tweets.\n\n')
                if user_input == 'kill':
                    self.logger.info('User-provided kill signal received, terminating process.')
                    break
        else:
            ## End Process when Kill Signal is Given
            while True:
                kill_signal = kill_queue.get(block=True)
                if kill_signal == 'kill_signal':
                    self.logger.info('Kill signal received, trying to terminate process.')
                    break

        ## Close Processes and Return Tweets
        p_streamer.kill()
        terminate_streaming.value = 1  # aka True; p_collector will terminate on its own
        p_collector.join()  # wait for p_collector to terminate
        if formatted_tweet_dict is not None:
            return dict(formatted_tweet_dict)
        else:
            self.logger.info('Process successfully terminated.')
            return  # program is using a queue and does not need an output from this function

    @catch_and_log_exception
    def download_tweets_stream(self, query_name: str, kill_queue: Union[multiprocessing.Queue, None] = None, formatted_tweet_queue: Union[multiprocessing.Queue, None] = None, save: bool = True):
        if kill_queue is not None:
            self.MyLogger.activate_mp_logger()  # allow logging to work for this method if it is called in a child process
            self.logger.debug('Process Started.')

        queries = self.make_query(query_name=query_name, pull_method='stream')

        ## Get tweets
        self.delete_streaming_rules()
        self.set_streaming_rules(rules=queries)
        start = pytz.timezone('US/Eastern').localize(datetime.now()).astimezone(pytz.utc)
        formatted_tweets = self.get_stream(kill_queue=kill_queue, formatted_tweet_queue=formatted_tweet_queue)
        end = pytz.timezone('US/Eastern').localize(datetime.now()).astimezone(pytz.utc)

        ## Save Data
        if save is True:
            fileloc = self.get_filename(query_name=query_name, dt=start, location=True)
            output_data = {
                'data': formatted_tweets,
                'query_name': query_name,
                'queries': queries,
                'start_time': start,
                'end_time': end,
            }
            with open(fileloc, 'wb') as handle:
                pickle.dump(output_data, handle, protocol=pickle.HIGHEST_PROTOCOL)
        return {'dict': output_data, 'fileloc': fileloc}


    def download_tweets_historical(self, query_name: str):
        '''
        Downloaded the last six full days (UTC midnight to midnight) of tweets.
            - AKA, it will never download today's tweets unless it is "tomorrow" in UTC time.
        '''
        all_formatted_tweets = {}
        end = datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
        start = end - timedelta(days=6)  # Twitter can get 7 days of historical data but to start from midnight, there are only 6 full days of data available
        for x in range(6):
            sub_start = start + timedelta(days=x)
            sub_end = sub_start + timedelta(days=1)
            queries = self.make_query(query_name=query_name, pull_method='historical', start_dt=sub_start, end_dt=sub_end)

            ## Confirm Data has not already been Downloaded
            filename = self.get_filename(query_name=query_name, dt=sub_start, location=False)
            fileloc = self.get_filename(query_name=query_name, dt=sub_start, location=True)
            if os.path.isfile(fileloc):
                print(f'Data present, not redownloading: {filename}.')
                ## Get Tweets
                with open(fileloc, 'rb') as handle:
                    formatted_tweets = pickle.load(handle)['data']
                all_formatted_tweets.update(formatted_tweets)
            else:
                print(f'Downloading tweets: {filename}.')
                ## Get Tweets
                formatted_tweets = {}
                for query in queries:
                    partial_query_tweets = self.get_historical(query_params=query)
                    formatted_tweets.update(partial_query_tweets)
                all_formatted_tweets.update(formatted_tweets)

                ## Save Data
                sub_data = {
                    'data': formatted_tweets,
                    'query_name': query_name,
                    'query': query,
                    'start_time': sub_start,
                    'end_time': sub_end,
                }
                with open(fileloc, 'wb') as handle:
                    pickle.dump(sub_data, handle, protocol=pickle.HIGHEST_PROTOCOL)
                print(f'New data saved: {filename}.')

        output_data = {
                'data': all_formatted_tweets,
                'query_name': query_name,
                'query': queries,
                'start_time': start,
                'end_time': end,
            }
        return {'dict': output_data, 'fileloc': None}


    ########################################
    ####          For the User          ####
    ########################################


    def download_tweets(self, query_name: str, pull_method: str):
        '''
        Purpose
        -------
        The main function a user uses to call all methods in this class and access Twitter data.

        Parameters
        ----------
        query_name : str
            Lookup value sent to self.make_query() to identify the query to use.
        pull_method : str
            The Twitter API endpoint to use to pull the data. Can be:
                - stream: downloads data via Twitter's streaming API.
                - historical: downloads data via Twitter's historical lookup API (1-week max of history).
                - user_timeline: gets all tweets that a user posts (can also do this via historical).
                - user_mentions: NOT READY but gets all tweets mentioning a user (can also do this via historical).

        Output
        ------
        Outputs a dict of the following format:
        {
            'dict': {
                'data': formatted_tweets,
                'query_name': query_name,
                'query': query,
                'start_time': start_dt,
                'end_time': end_dt
            },
            'fileloc': fileloc
        }
        '''
        ## Get Data from twitter
        if pull_method == 'stream':
            return self.download_tweets_stream(query_name=query_name)
        elif pull_method == 'historical':
            return self.download_tweets_historical(query_name=query_name)
        elif pull_method == 'user_timeline':
            pass
        else:
            raise Exception('"pull_method" argument must be one of ["stream", "historical", "user_timeline"].')
        return



if __name__ == '__main__':
    Comms = CommsTwitter()

    # d = Comms.download_tweets(query_name='by_crypto_leaders', pull_method='historical')
    # formatted_tweets = d['dict']
    # fileloc = d['fileloc']
    # pass
    # d2 = Comms.download_tweets(query_name='replyto_crypto_leaders', pull_method='historical')
    # formatted_tweets2 = d2['dict']
    # fileloc2 = d2['fileloc']
    # pass

    ## Grabbing Historical by Query
    # d = Comms.get_historical(query_params=Comms.make_query(query_name='ltc_walmart_fake_news'))


    ## Grabbing User Timeline
    # user_handle = '0xstark'
    # user_id = Comms.get_user_id(user_handle=user_handle)
    # output_dict = Comms.get_user_timeline(user_id=user_id)
    # output_df = pd.DataFrame.from_dict(output_dict, orient='index', columns=['datetime', 'text'])
    # with open('tweets_test_dict.pickle', 'wb') as handle:
    #     pickle.dump(output_dict, handle, protocol=pickle.HIGHEST_PROTOCOL)
    # with open('tweets_test_df.pickle', 'wb') as handle:
    #     pickle.dump(output_df, handle, protocol=pickle.HIGHEST_PROTOCOL)
    # # with open('teeeest_csv_tweets.pickle', 'rb') as handle:
    # #     b = pickle.load(handle)


    ## Grabbing Specific Tweet
    # Comms.get_specific_tweet(tweet_id=1437420294818250000)


    ## Streaming
    # query_name = 'new_coin_listing'
    # Comms.download_tweets(query_name=query_name, pull_method='stream')
