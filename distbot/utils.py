from pyppeteer.page import Page
import pyppeteer.errors
import html_text

from typing import Optional, Union
from pathlib import Path
from time import time
import logging.handlers
import logging
import asyncio
import sys
import re


async def scroll(page: Page, timeout: int = 5):
    """Scroll to the bottom of page."""
    logging.info(f"Scrolling page: {page.url}")
    # page height before scroll command.
    last_height = await page.evaluate("() => document.body.scrollHeight")
    # time last change in page height was detected.
    t_last_scroll = time()
    try:
        # loop for {timeout} seconds.
        while time()-t_last_scroll < timeout:
            # command page to scroll.
            await page.evaluate(
                f"window.scrollTo(0, document.body.scrollHeight);")
            # sleep to allow page to scroll/load.
            await asyncio.sleep(1)
            # height will have increased if page actually scrolled.
            current_height = await page.evaluate(
                "() => document.body.scrollHeight")
            if current_height != last_height:
                logging.info(
                    f"Scrolled page from {last_height} to {current_height} ({page.url})")
                t_last_scroll = time()
                last_height = current_height
        logging.info(f"Page scroll finished: {page.url}")
    except Exception as e:
        logging.exception(
            f"Page ({page.url}) not scrollable. Error: {e}")


async def hover(page: Page, ele_xpath: str):
    """Hover over all elements at ele_xpath."""
    try:
        await page.waitForXPath(ele_xpath, timeout=45_000)
    except pyppeteer.errors.TimeoutError as e:
        logging.exception(
            f"Hover failed. No elements found at XPath {ele_xpath}. Error: {e}")
        return
    last_ele_count = 0
    while True:
        eles = await page.xpath(ele_xpath)
        ele_count = len(eles)
        if ele_count <= last_ele_count:
            logging.info(f"No more elements to hover at {ele_xpath}.")
            return
        for i in range(last_ele_count, ele_count):
            logging.info(f"Hovering element {i} ({ele_xpath})")
            await eles[i].hover()
            # perform short sleep to allow hover-triggered content to load.
            await asyncio.sleep(0.66)
        last_ele_count = ele_count


def get_logger(logger_name: str, log_save_path: Optional[Union[str, Path]] = None, log_level: int = logging.INFO) -> logging.Logger:
    """Create a logger with an optional log file."""
    formatter = logging.Formatter(
        '[%(name)s][%(levelname)s]%(asctime)s: %(message)s')
    sh = logging.StreamHandler()  # sys.stdout
    sh.setLevel(log_level)
    sh.setFormatter(formatter)
    # logging.basicConfig(stream=sh)
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)
    logger.addHandler(sh)
    if log_save_path is not None:
        log_save_path = Path(log_save_path)
        if not log_save_path.is_file():
            try:
                log_save_path.parent.mkdir(exist_ok=True, parents=True)
            except (FileNotFoundError, PermissionError) as e:
                logger.error(
                    f"Error creating log directory '{log_save_path.parent}'. No log will be saved. Error: {e}"
                )
                return logger
        fh = logging.handlers.RotatingFileHandler(log_save_path,
                                                  maxBytes=10_000_000,
                                                  backupCount=2)
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger


logger = get_logger(
    "distbot", log_save_path=Path('distbot_logs/distbot.log'))


user_agents = {
    "Linux": [
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:78.0) Gecko/20100101 Firefox/78.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.89 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.113 Safari/537.36",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36"
    ],
    "Windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36 Edge/18.18363",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.113 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36"
    ],
    "Darwin": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.100 Safari/537.36"
    ]
}

bad_domains = [
    "google-analytics.com",
    "api.mixpanel.com",
    "stats.g.doubleclick.net",
    "mc.yandex.ru",
    "use.typekit.net",
    "beacon.tapfiliate.com",
    "js-agent.newrelic.com",
    "api.segment.io",
    "woopra.com",
    "maps.googleapis.com"
    "analytics.js",
    "static.olark.com",
    "static.getclicky.com",
    "fast.fonts.com",
    "youtube.com\/embed",
    "cdn.heapanalytics.com",
    "googleads.g.doubleclick.net",
    "pagead2.googlesyndication.com",
    "fullstory.com/rec",
    "navilytics.com/nls_ajax.php",
    "log.optimizely.com/event",
    "hn.inspectlet.com",
    "tpc.googlesyndication.com",
    "partner.googleadservices.com",
    "hm.baidu.com"
]

error_regs = [
    re.compile(r) for r in
    (r"(?i)(not|aren't).{1,10}robot",
     r"(?i)verify your identity",
     r"(?i)(click|select|check).{1,20}box",
     r"(?i)(verify|check|confirm).{1,40}human",
     r"(?i)(enter|type).{1,20}characters",
     r"(?i)(select|click|choose).{1,30}(image|picture)",
     r"(?i)(not|don't|can't).{1,20}(access|permission|permitted).{1,20}server",
     r"(?i)access.{1,20}denied",
     r"(?i)browser.{1,50}(cookies|javascript)",
     r"(?i)something.{1,20}(isn't|is\snot).{1,20}(right|normal)",
     r"(?i)(traffic|activity).{1,50}(unusual|suspicious)",
     r"(?i)(unusual|suspicious).{1,50}(traffic|activity)",
     r"(?i)dns.{1,30}(failed|error)",
     r"(?i)error.{1,10}not\sfound",
     r"(?i)retriev.{1,5}the url",
     r"(?i)ip\saddress.{1,20}(banned|blocked|permitted)",
     r"(?i)automated\saccess",
     r"https://securepubads\.g\.doubleclick\.net")
]


async def security_check(page, response):
    html = await page.content()
    text = html_text.extract_text(html)
    error_level = len([r for r in error_regs if r.search(text)])
    if len(text) < 1000:
        error_level += 1
    if response and not response.ok:
        error_level += 1
    return error_level


def set_default_flags():
    import pyppeteer.launcher
    pyppeteer.launcher.DEFAULT_ARGS = [
        # Disable reporting to UMA, but allows for collection.
        '--metrics-recording-only',
        # Disable various background network services, including extension updating, safe browsing service, upgrade detector, translate, UMA.
        '--disable-background-networking',
        # Disable syncing to a Google account.
        '--disable-sync',
        # Mute any audio.
        '--mute-audio',
        # Disable the default browser check, do not prompt to set it as such.
        '--no-default-browser-check',
        # Skip first run wizards.
        '--no-first-run',
        # Disable timers being throttled in background pages/tabs.
        '--disable-background-timer-throttling',
        # Disables client-side phishing detection.
        '--disable-client-side-phishing-detection',
        # Disable popup blocking.
        '--disable-popup-blocking',
        # Avoid potential instability of using Gnome Keyring or KDE wallet. crbug.com/571003
        '--password-store=basic',
        # Use mock keychain on Mac to prevent blocking permissions dialogs
        '--use-mock-keychain',
        # Disable PlzNavigate (https://docs.google.com/document/d/1rzDdDcEzulaqgHA6jzMIlZ_5Mu5C76v3iqwylqUOqNQ/edit)
        '--disable-browser-side-navigation',
        # Reloading a page that came from a POST normally prompts the user.
        '--disable-prompt-on-repost',
        # Suppresses hang monitor dialogs in renderer processes.
        '--disable-hang-monitor',
        # By default, an https page cannot run JavaScript, CSS or plug-ins from http URLs.
        # This provides an override to get the old insecure behavior.
        "--allow-running-insecure-content",
        # Disable crashdump collection (reporting is already disabled in Chromium)
        '--disable-breakpad',
        # Disable installation of default apps on first run.
        '--disable-default-apps',
        # https://github.com/GoogleChrome/puppeteer/issues/1834
        '--disable-dev-shm-usage',
        # Disables OOPIF. https://www.chromium.org/Home/chromium-security/site-isolation
        '--disable-features=site-per-process',
        # Disables Domain Reliability Monitoring.
        '--disable-domain-reliability',
        # Prevent other pages from starting to load before navigation.
        "--prerender=disabled",
        # Don't send hyperlink auditing pings.
        "--no-pings",
        # Whether or not the browser should warn if the profile is on a network share.
        # This flag is only relevant for Windows currently.
        "--no-network-profile-warning",
        # Disables all experiments set on about:flags. Does not disable about:flag itself.
        "--no-experiments",
        # Disables the suggestions service.
        "--disable-suggestions-service",
        # Disable prerendering based on local browsing history.
        "--disable-prerender-local-predictor",
        # Disable speculative TCP/IP preconnection.
        "--disable-preconnect",
        # Disables CNAME lookup of the host when generating the Kerberos SPN for a
        # Negotiate challenge. See HttpAuthHandlerNegotiate::CreateSPN for more background.
        # "--disable-auth-negotiate-cname-lookup"
    ]