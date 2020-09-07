from distbot.spider import Spider
from pprint import pformat
import asyncio


async def main():
    spider = await Spider().launch()
    page = await spider.get('https://www.amazon.com/')
    urls = set([await page.evaluate("(ele) => ele.getAttribute('href')", ele)
                for ele in await page.xpath("//a[@href]")])
    print(f"Extracted {len(urls)} urls from {page.url}: {pformat(urls)}")
    await spider.shutdown()

asyncio.run(main())
