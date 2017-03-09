#!/usr/bin/env python
import requests
import json
import argparse
import sys
from multiprocessing.pool import ThreadPool
from concurrent.futures import ThreadPoolExecutor
import urllib
import itertools
import math

# Page size for the /repositories endpoint.
REPOSITORIES_PAGE_SIZE = 100

# Number of threads to use for parallel fetching
NUM_THREADS = 5

# Default count
DEFAULT_COUNT = 10

# Maximum count. Must be smaller than REPOSITORIES_PAGE_SIZE.
MAX_COUNT = 30


class ExitCodes(object):
    GENERIC_ERROR = 1
    INVALID_ARGS = 2
    INVALID_ARG_VALUES = 3
    NETWORK_ERROR = 4
    GITHUB_GENERIC_ERROR = 5
    GITHUB_RESOURCE_NOT_FOUND = 6
    GITHUB_RATE_LIMIT = 7


class GithubApiException(Exception):
    def __init__(self, http_status_code):
        super(GithubApiException, self).__init__()
        self.http_status_code = http_status_code


class GithubApiRateException(GithubApiException):
    def __init__(self):
        super(GithubApiRateException, self).__init__(403)


def github_request(api_url):
    """Perform a GET request against the GitHub API"""
    url = "https://api.github.com" + api_url

    # Recommended header for GitHub API queries
    headers = {"Accept": "application/vnd.github.v3+json"}

    # requests.get raises exceptions derived from requests.exceptions.RequestException
    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        return json.loads(r.content)
    elif r.status_code == 403:
        raise GithubApiRateException()
    else:
        raise GithubApiException(r.status_code)


def parse_arguments(args):
    """Parse command-line arguments (not including the program name)"""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List repos")
    desc_parser = subparsers.add_parser("desc", help="Show repo details")

    list_parser.add_argument('language', nargs='?')
    list_parser.add_argument('-n', '--count', type=int, default=DEFAULT_COUNT)
    desc_parser.add_argument('ids', nargs='+', type=int)
    try:
        return parser.parse_args(args)
    except SystemExit:
        # Re-raise SystemExit with the correct error code
        # parse_args has already printed an appropriate error message.
        exit(ExitCodes.INVALID_ARGS)


def format_repo_list(api_repo_list):
    """Format repo info into a JSON string"""
    # Which fields we want to keep
    fields = ['id', 'full_name', 'html_url', 'pushed_at', 'language']
    output_repo_list = []
    for api_repo_info in api_repo_list:
        output_repo_info = {f: api_repo_info[f] for f in fields if f in api_repo_info}
        output_repo_list.append(output_repo_info)

    # Pretty print the resulting JSON array
    return json.dumps(output_repo_list, indent=4)


def repo_binary_search(count):
    """Get a repo list with no filter. Performs binary search on the /repositories API.
    This implementation is not used, since it exhausts the GitHub rate limit very quickly."""

    min_since = 0
    max_since = 128000000
    # Double our max bound until we're sure it's large enough
    while len(github_request("/repositories?since={0}".format(max_since))) >= count:
        max_since = 2 * max_since

    while True:
        pivot_since = int((min_since + max_since) / 2.0)
        results = github_request("/repositories?since={0}".format(pivot_since))
        len_results = len(results)
        if count <= len_results < REPOSITORIES_PAGE_SIZE:
            # We know this is the last page, and there are enough entries
            break
        elif len_results < count:
            max_since = pivot_since
        else:  # len_results == REPOSITORIES_PAGE_SIZE
            min_since = pivot_since

    return results[-count:]


class Ghtool(object):
    def __init__(self, output_stream=sys.stdout, error_stream=sys.stderr):
        self.output_stream = output_stream
        self.error_stream = error_stream

    def exit_with_message(self, error_code, message):
        print >> self.error_stream, message
        exit(error_code)

    def handle_desc(self, ids):
        p = ThreadPool(NUM_THREADS)

        def worker_function(id):
            return github_request("/repositories/{0}".format(id))

        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            results_iterator = executor.map(worker_function, ids)

        results_list = []
        # Access the results one by one, so we can properly handle exceptions.
        for i in itertools.count():
            try:
                # This line will re-raise any exceptions encountered by the worker threads
                results_list.append(next(results_iterator))
            except StopIteration:
                break
            except GithubApiException as e:
                if e.http_status_code == 404:
                    error_msg = "Repository not found: {0}".format(ids[i])
                    self.exit_with_message(ExitCodes.GITHUB_RESOURCE_NOT_FOUND, error_msg)
                else:
                    raise sys.exc_info()

        print >> self.output_stream, format_repo_list(results_list)

    def handle_list(self, count, language_filter=None):
        if not (0 < count <= MAX_COUNT):
            self.exit_with_message(ExitCodes.INVALID_ARG_VALUES,
                                   "Invalid argument value: count must be between 1 and {0}".format(MAX_COUNT))

        if language_filter is not None:
            url = "/search/repositories?q=language:{0}&sort=updated".format(urllib.quote(language_filter))
            try:
                repo_list = github_request(url)["items"][0:count]
            except GithubApiException as e:
                # Handle exception for unknown language
                if e.http_status_code == 422:
                    self.exit_with_message(ExitCodes.INVALID_ARG_VALUES,
                                           "GitHub API does not recognize language '{0}'".format(language_filter))
                # Re-raise error
                else:
                    raise sys.exc_info()

        else:  # No language filter
            # GitHub does not allow an empty 'q' parameter, so we need to add a dummy filter predicate which always evaluates to true.
            # Here the filter predicate is stars >= 0, which is true for every repository
            url = "/search/repositories?q=stars:>=0&sort=updated"
            repo_list = github_request(url)["items"][0:count]
            # TODO: warn user if "incomplete results" flag is seen.
            # Binary search implementation:
            # repo_list = repo_binary_search(count)

        print >> self.output_stream, format_repo_list(repo_list)

    def main(self, argv):
        arguments = parse_arguments(argv)
        try:
            if arguments.command == "list":
                self.handle_list(arguments.count, arguments.language)
            elif arguments.command == "desc":
                self.handle_desc(arguments.ids)
        except requests.exceptions.RequestException:
            self.exit_with_message(ExitCodes.NETWORK_ERROR, "Network error: could not connect to GitHub")
        except GithubApiRateException as e:
            self.exit_with_message(ExitCodes.GITHUB_RATE_LIMIT, "GitHub rate limit exceeded")
        except GithubApiException as e:
            self.exit_with_message(ExitCodes.GITHUB_GENERIC_ERROR, "GitHub API response has an unexpected error status")


if __name__ == "__main__":
    ghtool = Ghtool()
    ghtool.main(sys.argv[1:])
