# Pyppeteer Spider
A stealthy asynchronous spider capable of running Chrome, Headless Chrome, Chromium, and Headless Chromium.

Spiders can optionally be ran with multiple browsers and/or multiple browser tabs.
All request will be cyclically distributed among browsers/tabs.

Automation detection prevention scripts will be automatically invoked every time a page is navigated. If a browser is running in headless mode,
headless mode detection preventions scripts will also be invoked.
All detection prevention scripts are largely adapted from [puppeteer-extra](https://github.com/berstend/puppeteer-extra) and [Eval Sangaline's blog post](https://intoli.com/blog/not-possible-to-block-chrome-headless/).

This package is built using [Pyppeteer](https://github.com/miyakogi/pyppeteer) which is the Python bindings for [Puppeteer](https://github.com/puppeteer/puppeteer).

## Installing
`pip install pyppeteer_spider`

## Usage
Spiders can be created through the PyppeteerSpider class, which has the signature:
```
PyppeteerSpider(
    browser_page_count: int = 1, # Number of tabs per browser.
    browser_count: int = 1, # Number of browsers.
    default_nav_timeout: int = 30000,  # Default maximum navigation timeout. Units: ms
    max_consec_browser_errors: int = 4, # Max allowable consecutive browser errors before browser will be replaced.
    incognito: bool = False, # Run browser in incognito mode.
    headless: bool = False, # Run browser in headless mode.
    delete_cookies: bool = False, # Clear all cookies before each request.
    disable_cache: bool = False, # Disable cache for each request.
    disable_images: bool = False, # Load pages without images.
    browser_memory_limit: Optional[int] = None, # Max memory browser can use. Units: mb
    default_viewport: Optional[Dict[str, int]] = None, # Change default viewport size. Example: {width: 1280, height: 800}. Default is full page.
    js_injection_scripts: Optional[List[str]] = None, # JavaScript functions that will be invoked on every page navigation.
    request_abort_types: Optional[List[str]] = None, # Content types of requests that should be aborted. Example: 'image', 'font', 'stylesheet', 'script'
    blocked_urls: Optional[List[str]] = None, # URL patterns to block. Wildcards ('*') are allowed.
    proxy_addr: Optional[Union[List[str],str]] = None, # Address of proxy server.
    user_data_dir: Optional[Union[List[str],str]] = None, # Path to Chrome profile directory. Default will use temp directory.
    browser_executable: Optional[str] = None, # Path to Chrome or Chromium executable. If None, Chromium will be downloaded.
    user_agent_type: Union['Linux', 'Darwin', 'Windows'] = platform.system(), # Select a user agent type. Default will be current system.
    log_level: int = logging.INFO,
    log_file_path: Optional[Union[str,pathlib.Path]] = None)
```

URLs should be navigated to via the spider's *get* function. *get* will return the navigated page and optionally a response object.
Pages returned by *get* will not be used again by the spider until spider.set_idle(page) is called. This is so the spider does not use the
page for another navigation task while you are still processing the page in your scraping script.

## Examples

##### Extract urls and html from Amazon.
```
from pyppeteer_spider.spider import PyppeteerSpider

spider = await PyppeteerSpider().launch()
page = await spider.get('https://www.amazon.com/')
urls = [await page.evaluate("(ele) => ele.getAttribute('href')",ele)
        for ele in await page.xpath("//a[@href]")]
html = await page.content()
await spider.set_idle(page)
await spider.shutdown()
```

##### Extract profile data from LinkedIn.
```
from pyppeteer_spider.spider import PyppeteerSpider

spider = await PyppeteerSpider().launch()
page = await spider.get('https://www.linkedin.com/search/results/people/?keywords=Software%20Engineer&origin=SUGGESTION')
# scroll to the page so all content loads.
await spider.scroll_page(page)
# hover all profile elements.
profile_xpath = '//li[contains(@class,"search-result")]'
await spider.hover_elements(ele_xpath=profile_xpath) # Note: hovering elements is very rarely necessary.
# extract data of from all profiles.
for profile_ele in await page.xpath(profile_xpath):
    person_name_ele = await profile_ele.xpath('.//span[@class="name actor-name"]')
    if person_name_ele:
        person_name = await page.evaluate("(ele) => ele.innerText",person_name_ele[0])
    profile_url_ele = await profile_ele.xpath('.//a[contains(@class,"search-result")]')
    if profile_url_ele:
        profile_url = await page.evaluate("(ele) => ele.getAttribute('href')",profile_url_ele[0])
await spider.set_idle(page)
await spider.shutdown()
```

##### Asynchronously scrape a list of urls using 3 browsers with 4 tabs each.
```
from pyppeteer_spider.spider import PyppeteerSpider
from pathlib import Path

async def do_scrape(url, spider):
    page = await spider.get(url)
    urls = [await page.evaluate("(ele) => ele.getAttribute('href')",ele)
            for ele in await page.xpath("//a[@href]")]
    html = await page.content()
    await spider.set_idle(page)

with Path("urls.txt").open(mode='r') as infile:
    urls = set([line.strip() for line in infile])
spider = await PyppeteerSpider(browser_page_count=4,
                                browser_count=3).launch()
await asyncio.gather(*[asyncio.create_task(do_scrape(url, spider))
                        for url in urls])
await spider.shutdown()
```