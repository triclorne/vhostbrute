import sys
import os
from argparse import ArgumentParser
from os.path import isfile

import requests
import threading
import multiprocessing
import time

is_py2 = sys.version[0] == '2'
if is_py2:
    import Queue as queue
    from urlparse import urlparse, parse_qs
else:
    import queue as queue
    from urllib.parse import urlparse, parse_qs
from difflib import SequenceMatcher

# parser = ArgumentParser(usage='%prog url [options]', description='Virtual host bruteforcer')
parser = ArgumentParser()
parser.add_argument('-u', '--url', type=str, default=None, help='URL to bruteforce')
parser.add_argument('-s', '--scheme', type=str, default='http', help='Scheme to bruteforce')
parser.add_argument('-r', '--remoteip', type=str, default=None, help='Remote IP for bruteforce')
parser.add_argument('-b', '--base', type=str, default=None, help='Domain to base request')
parser.add_argument('-n', '--notfound', type=str, default=None, help='Wrong vhost for not found request')
parser.add_argument('-m', '--method', type=int, default=1, help='Method of bruteforce see readme')
parser.add_argument('-t', '--threads', type=int, default=0, help='Count of threads (default: maxcpu)')
parser.add_argument('-d', '--vhosts', type=str, default='vhosts.list', help='Domain dictionary file')
parser.add_argument('-z', '--zones', type=str, default=None, help='Zones dictionary file')
parser.add_argument('-v', '--verbose', type=int, default=False, help='Show debug information')
parser.add_argument('-', '--allow-redirects', type=int, default=False, help='Show debug information')
parser.add_argument('-e', '--easy', type=int, default=True, help='Easy method to find virtual hosts (default: true)')
parser.add_argument('-o', '--outfile', type=str, default=None, help='File to save finded virtual host')

# requests warning off
requests.packages.urllib3.disable_warnings()
# default parameters
killapp = False
# urls
get_url = False
scheme = "http"
remote_ip = False
brute_url = False
base_url = False
notfound_url = False
# create queue
q = queue.Queue()
# User Agent for requests
ua = 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/46.0.2490.80 Safari/537.36'
headers = {'User-Agent': ua}
# set verify https to false (win fix)
verify = False
# threads
threads = multiprocessing.cpu_count()
# vhosts and zones dictionary
vhost_file = 'vhosts.list'
zone_file = None
# default responses
nf_response = b_response = None
nf_length = b_length = 0
# find
easy = True
# v
verbose = False
outfile = None
finded = 0
allow_redirects = False


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def print_error(text, show_help=True):
    print(text)
    if show_help:
        parser.print_help()
    sys.exit(1)


def check_params(params):
    global scheme, get_url, brute_url, base_url, notfound_url, threads, vhost_file, \
        zone_file, verbose, easy, outfile, allow_redirects
    if isfile(params.vhosts) is False:
        print_error("File %s with virtual hosts doesn't exist" % params.vhosts)
    vhost_file = params.vhosts
    if params.remoteip is None and params.url is None:
        print_error("You must specify url or remote ip for brute")
    if params.scheme != "https":
        scheme = "http"
    if params.threads:
        threads = params.threads
    if params.verbose:
        verbose = params.verbose
    if params.easy is not True:
        easy = False
    if params.outfile:
        outfile = params.outfile
    if params.allow_redirects:
        allow_redirects = True
    base_url = notfound_url = brute_url = params.url
    if params.base:
        base_url = params.base
    if params.notfound:
        notfound_url = params.notfound
    # check specified parameters by method
    if params.method == 2:
        if params.zones is None:
            print_error("You must specify zone file for this type of brute")
        if isfile(params.zones) is False:
            print_error("File %s with zones doesn't exist" % params.zones)
        zone_file = params.zones
        if base_url is None:
            base_url = params.url if params.remoteip is None else params.remoteip
        get_url = scheme + "://" + base_url
        prepare()
    elif params.method == 3:
        print_error("Not yet implemented")
    else:
        if params.url is None or params.remoteip is None:
            print_error("You must specify url *and* remote ip to attack")
        get_url = scheme + "://" + params.remoteip
        prepare(brute_url)


def prepare(url=None):
    global q, vhost_file, zone_file
    vhosts = []
    with open(vhost_file, "r") as vhost:
        for v in vhost:
            v = v.rstrip("\n")
            vhosts.append(v)
    if zone_file:
        with open(zone_file, "r") as zone:
            for z in zone:
                z = z.rstrip("\n")
                for v in vhosts:
                    q.put(v + "." + z)
    else:
        if url is None:
            for v in vhosts:
                q.put(v)
        else:
            for v in vhosts:
                q.put(v + "." + url)


def base_requests():
    global get_url, base_url, ua
    # base
    global b_response, b_length, notfound_url
    h = {"Host": base_url, "User-Agent": ua}
    b_response, b_length = get_base(h)
    # not found
    global nf_response, nf_length
    h = {"Host": str(int(time.time())), "User-Agent": ua}
    nf_response, nf_length = get_base(h)


def get_base(head):
    global get_url, verify
    try:
        response = requests.get(get_url, headers=head, verify=verify)
        resp = response.text.strip()
        length = len(resp)
        return resp, length
    except requests.exceptions.TooManyRedirects:
        print_error("Cannot get base url. Too many redirects.", False)
        pass
    except requests.exceptions.RequestException as e:
        # fatal error
        print(e)


def vhost_found(vhost):
    global finded
    print("Virutal host %s is found!" % vhost)
    finded += 1


def compare():
    global q, ua, get_url, base_url, b_length, easy, verbose, verify, nf_length, allow_redirects
    while True:  # working with queue all time while script is running
        vhost = q.get()
        try:
            response = requests.get(
                    get_url, headers={'Host': vhost, "User-Agent": ua}, verify=verify, allow_redirects=allow_redirects)
            if response.status_code == 301 or response.status_code == 302:
                redirect = urlparse(response.headers["Location"])
                if redirect.netloc == base_url or redirect.netloc == base_url:
                    if verbose:
                        print('Got %d redirect on %s vhost to %s. Skipping...' % (
                            response.status_code, vhost, response.headers["Location"]))
                    q.task_done()
                    continue
            if verbose:
                print("Trying %s..." % vhost)
            curr_response = response.text.strip()
            curr_length = len(curr_response)
            if verbose:
                print("%s response: baselen - %s | nflen - %s | curr - %s" % (vhost, b_length, nf_length, curr_length))
            if abs(curr_length - b_length) >= 10 and abs(curr_length - nf_length) >= 10 and easy is True:
                vhost_found(vhost)
                q.task_done()
                continue
            diff_base = similar(curr_response, b_response)
            diff_nf = similar(curr_response, nf_response)
            if diff_base <= 0.8 and diff_nf <= 0.8:
                vhost_found(vhost)
            elif verbose:
                print("%s not found" % vhost)
            q.task_done()
        except requests.exceptions.Timeout:
            q.task_done()
            if verbose:
                print("Request to vhost %s failed: Timed out" % vhost)
            pass
        # Maybe set up for a retry, or continue in a retry loop
        except requests.exceptions.TooManyRedirects:
            q.task_done()
            print("Request to vhost %s failed: Too many redirects" % vhost)
            pass
        except requests.exceptions.RequestException as e:
            q.task_done()
            # fatal error
            print(e)


def main():
    args = parser.parse_args()
    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(0)
    check_params(args)
    base_requests()
    print("Starting bruteforce with %d threads" % threads)
    # create certain threads for multiple API requests
    for i in range(threads):  # count of threads depends on CPU cores
        t = threading.Thread(target=compare)
        t.daemon = True
        t.start()
    q.join()
    print("Brute successfully completed. Found %d virtual host" % finded)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Program is terminated!")
        killapp = True
        raise
    except Exception:
        sys.exit(1)