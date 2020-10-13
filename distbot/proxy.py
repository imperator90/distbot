from distbot.utils import logger, security_check

from typing import Dict, List, Union, Any
from collections import deque


class ProxyManager:
    def __init__(self, proxies: List[str], mode: Union['roundrobin', 'lifo', 'fifo'] = 'roundrobin',
                 max_error_count: int = 5, request_buffer_size: int = 25):
        self.proxies = proxies
        self.mode = mode
        self.max_error_count = max_error_count
        self.request_history = deque(maxlen=request_buffer_size)
        self.rr_proxy_iter = self.__rr_proxy_iter()
        self.removed_proxies = []

    @property
    def proxy(self) -> str:
        if self.mode == 'roundrobin':
            return next(self.rr_proxy_iter)
        if self.mode == 'fifo':
            return self.proxies[0]
        if self.mode == 'lifo':
            return self.proxies[-1]

    async def check_proxy_error(self, response, page, proxy) -> bool:
        """Check response for proxy-related errors. Return True if error detected."""
        if response.status >= 500:
            logger.error(f"Recoded proxy error status {response.status}")
            self.__handle_error(proxy)
            return True
        block_probability = await security_check(page, response)
        if block_probability > 1:
            logger.error(
                f"Recorded proxy security error. Block probability: {block_probability}")
            self.__handle_error(proxy)
            return True
        # record that page was navigated with no error.
        self.request_history.append(0)
        return False

    def __handle_error(self, proxy):
        # record proxy error.
        self.request_history.append(1)
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
        if self.proxies:
            while True:
                for p in self.proxies:
                    yield p
