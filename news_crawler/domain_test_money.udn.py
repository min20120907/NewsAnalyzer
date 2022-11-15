from tldextract import tldextract
test_url='https://money.udn.com/money/story/5607/6763523?from=edn_maintab_index'
list1=[test_url]
for url in list1:
    te_result = tldextract.extract(url)
    domain = '{}.{}'.format(te_result.domain, te_result.suffix)
    print('{}'.format(domain))
