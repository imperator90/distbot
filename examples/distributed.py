from distbot.spider import Spider
from datetime import datetime
from random import sample
from pathlib import Path
import asyncio
import csv
import sys


def load_urls(url_count=100_000):
    """Get random urls from the Alexa top 1,000,000 list."""
    print("Loading urls..")
    with Path("alexatop1m.csv").open(mode='r') as i:
        urls = ['http://'+r[1] for r in csv.reader(i)]
    print(f"Returning {url_count} random urls.")
    return sample(urls, url_count)


async def fetch(url, spider):
    """Navigate to page at 'url' and log page title, response status code, url, time navigated."""
    # default waitUntil is 'load', which will wait until the page is fully-loaded.
    # domcontentloaded will wait for the initial HTML document has been completely loaded and parsed,
    # without waiting for stylesheets, images, and subframes to finish loading.
    resp, page = await spider.get(url, response=True, waitUntil='domcontentloaded')
    log_str = f'{datetime.now()}\t{resp.status}\t{page.url}'
    title = await page.xpath('//title')
    if title:
        title = await page.evaluate('(ele) => ele.innerText', title[0])
        log_str += f'\t{title.strip()}'
    with Path("pages.tsv").open(mode='a+') as o:
        o.write(f'{log_str}\n')
    # return page to idle queue so the next task can use it.
    await spider.set_idle(page)


async def main(browsers=2, pages=2):
    urls = load_urls()
    launch_options = {
        "headless": True,
        "ignoreHTTPSErrors": True,
        "defaultViewport": {},
        # "executablePath": "/usr/bin/google-chrome-stable",
        "defaultNavigationTimeout": 45_000,
        "args": [
            "--disable-web-security",
            "--no-sandbox",
            "--start-maximized",
            "--blink-settings=imagesEnabled=false",
        ]
    }
    spider = Spider()
    for _ in range(browsers):
        await spider.add_browser(pages=pages, launch_options=launch_options)
    await asyncio.gather(
        *[asyncio.create_task(fetch(url, spider)) for url in urls])
    await spider.shutdown()
    print('Finished.')

if __name__ == "__main__":
    # check for command line arguments: number of browsers, number of pages per browser.
    if len(sys.argv) == 3:
        asyncio.run(main(sys.argv[1], sys.argv[2]))
    else:
        asyncio.run(main())
