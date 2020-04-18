from pyppeteer_spider.utils import get_logger
import pyppeteer.launcher

from typing import Optional, Dict, Union
from pprint import pformat
import pathlib
from pathlib import Path
import logging

# Remove Pyppeteer's default arguments that we don't want to use for scraping.
unwanted_default_args = ['--disable-popup-blocking', '--disable-extensions']
for arg in unwanted_default_args:
    if arg in pyppeteer.launcher.DEFAULT_ARGS:
        pyppeteer.launcher.DEFAULT_ARGS.remove(arg)


def get_launch_options(headless: bool, incognito: bool, disable_images: bool,
                       user_data_dir: Optional[str],
                       default_viewport: Optional[Dict[str, int]],
                       browser_executable: Optional[Union[pathlib.Path, str]],
                       browser_memory_limit: Optional[int],
                       proxy_addr: Optional[str],
                       logger: logging.Logger) -> Dict[str, str]:
    """Add flags to launch command based on user settings."""
    launch_args = [
        # If disable-web-security is set, links within iframes are collected as those of parent frames. If it's not, the source attributes of the iframes are collected as links.
        '--disable-web-security',
        '--no-sandbox',
        '--start-maximized'
    ]
    if incognito:
        launch_args.append('--incognito')
    if disable_images:
        #launch_args.append('--disable-images')
        launch_args.append('--blink-settings=imagesEnabled=false')
    if proxy_addr:
        launch_args.append(f'--proxy-server={proxy_addr}')
    if browser_memory_limit:
        launch_args.append(
            f'--js-flags="--max_old_space_size={browser_memory_limit}"')
    if user_data_dir:
        if Path(user_data_dir).is_dir():
            launch_args.append(f'--user-data-dir={str(user_data_dir)}')
        else:
            logger.error(
                f"user_data_dir is not a valid directory! --user-data-dir will not be added to browser launch."
            )
    launch_options = {
        'headless': headless,
        'ignoreHTTPSErrors': True,
        'args': launch_args
    }
    launch_options[
        'defaultViewport'] = default_viewport if default_viewport else {}
    if browser_executable:
        if Path(browser_executable).is_file():
            launch_options['executablePath'] = str(browser_executable)
        else:
            logger.error(
                f"""Path '{str(browser_executable)}' does not contain a valid file.
                'executablePath' will not be added to launch options.""")
    logger.info(
        f"Constructed browser launch options:\n{pformat(launch_options)}")
    return launch_options
