def process_news(self, news_url):
    cases = {
        'yahoo.com': {
            'main': ['header', {"class": "caas-header"}],
            'content': ['div', {"class": "caas-body"}],
            'alt_main': ['h1', {"data-test-locator": "headline"}],
            'alt2_main': ['h1', {"class": "Fz(24px) Fw(b)"}],
            'alt2_content': ['div', {"class": "Mt(12px) Fz(16px) Lh(1.5) C(#464e56) Whs(pl)"}]
        },
        'rfi.fr': {
            'main': ['article', {}, 'h1'],
            'content': ['article', {}, 'div', {"class": "t-content__body u-clearfix"}]
        },
        'rti.org.tw': {
            'main': ['section', {"class": "news-detail-box"}],
            'content': ['article', {}]
        },
        'storm.mg': {
            'main': ['h1', {"id": "article_title"}],
            'content': ['div', {"id": "CMS_wrapper"}]
        },
        'bbc.com': {
            'main': ['h1', {"class": "bbc-1tk77pb e1p3vdyi0"}],
            'alt_main': ['strong', {"class": "ewk8wmc0 bbc-uky4hn eglt09e1"}]
        },
        'mirrormedia.mg': {
            'main': ['h1', {"class": "story__title"}],
            'content': ['p', {"class": "g-story-paragraph"}]
        },
        'cw.com.tw': {
            'main': ['div', {"class": "article__head"}],
            'content': ['div', {"class": "article__content py20"}]
        },
        'epochtimes.com': {
            'main': ['h1', {"class": "title"}],
            'content': ['div', {"id": "artbody"}]
        },
        'nytimes.com': {
            'main': ['div', {"class": "article-header"}],
            'content': ['div', {"class": "article-paragraph"}]
        },
        'wsj.com': {
            'main': ['h1', {"class": "wsj-article-headline"}],
            'content': ['div', {"class": "wsj-snippet-body"}]
        }
    }
    content_str = ''
    res = requests.get(news_url, headers=headers)
    res.encoding = 'utf-8'
    if res.status_code != requests.codes.ok:
        return "url missing!"
    objsoup = BeautifulSoup(res.text, 'lxml')
    site_config = cases.get(news_url.split('.')[1], {})
    main = site_config.get('main', [])
    content = site_config.get('content', [])
    title = objsoup.find(*main) or objsoup.find(*site_config.get('alt_main', [])) or objsoup.find(*site_config.get('alt2_main', []))
    contents = objsoup.find(*content).find_all('p') if content else objsoup.find_all('p')
    for ct in contents:
        content_str += ct.text
    news_title_kw, news_content_kw, sentiments_analysis = self.kw(title.text, content_str)
    self.update_instances(title, content_str, news_url, news_title_kw, news_content_kw, sentiments_analysis)
