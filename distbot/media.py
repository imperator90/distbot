import re

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
     r"(?i)automated\saccess")
]
