from distbot.utils import logger, security_check

from typing import Dict, List, Union, Any
from collections import deque
from zipfile import ZipFile


async def block_probability(response, page):
    bp = await security_check(page, response)
    if response and response.status >= 500:
        bp += 1
    return bp


class ProxyManager:
    def __init__(self, proxies: List[str], mode: Union['roundrobin', 'lifo', 'fifo'] = 'roundrobin',
                 max_error_count: int = 5, request_buffer_size: int = 25):
        self.proxies = proxies
        self.mode = mode
        self.max_error_count = max_error_count
        self.request_history = deque(maxlen=request_buffer_size)
        self.rr_proxy_iter = self.__rr_proxy_iter()
        self.removed_proxies = []

    def get_next_proxy(self) -> str:
        if self.mode == 'roundrobin':
            return next(self.rr_proxy_iter)
        if self.mode == 'fifo':
            return self.proxies[0]
        if self.mode == 'lifo':
            return self.proxies[-1]

    async def check_proxy_error(self, response, page, proxy) -> int:
        """Check response for proxy-related errors. Return True if error detected."""
        bp = await block_probability(response, page)
        if bp > 1:
            logger.error(
                f"Recorded proxy security error. Block probability: {bp}")
            # record proxy error.
            self.request_history.append(1)
            self.__check_remove(proxy)
        else:
            # record that page was navigated with no error.
            self.request_history.append(0)
        return bp

    def __check_remove(self, proxy):
        # check if proxy now meets removal conditions.
        if len(self.request_history) == self.request_history.maxlen and sum(self.request_history) >= self.max_error_count:
            logger.error(
                f"Proxy {proxy} request histroy buffer exceeded max error count ({self.max_error_count})")
            # remove proxy from proxy list and add it removed_proxies so we can reuse it if all proxies get removed.
            self.proxies.remove(proxy)
            self.removed_proxies.append(proxy)
            # if we are all out of proxies, try using the ones that were removed.
            if not len(self.proxies):
                logger.error(
                    f"No proxies remaining. Resorting to previously removed proxies: {self.removed_proxies}")
                self.proxies = self.removed_proxies.copy()
                self.removed_proxies.clear()

    def __rr_proxy_iter(self):
        if len(self.proxies):
            while True:
                for p in self.proxies:
                    yield p


def make_auth_proxy_extension(proxy_host, proxy_port, proxy_user, proxy_pass, save_path):
    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """

    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
              singleProxy: {
                scheme: "http",
                host: "%(host)s",
                port: parseInt(%(port)d)
              },
              bypassList: ["foobar.com"]
            }
          };
    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%(user)s",
                password: "%(pass)s"
            }
        };
    }
    chrome.webRequest.onAuthRequired.addListener(
                callbackFn,
                {urls: ["<all_urls>"]},
                ['blocking']
    );
        """ % {
        "host": proxy_host,
        "port": proxy_port,
        "user": proxy_user,
        "pass": proxy_pass,
    }

    with ZipFile(save_path, 'w+') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)
