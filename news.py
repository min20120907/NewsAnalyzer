import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
from tldextract import tldextract
#設定fake-useragent
#假的user-agent,產生 headers
ua=UserAgent()
usar=ua.random #產生header 字串
headers={'user-agent':usar}
url='https://news.google.com/topstories?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

htmlfile=requests.get(url,headers=headers,timeout=3)#他這邊請求website後,得到一個物件

if htmlfile.status_code==requests.codes.ok:
    print("成功連線到google news")
htmlfile.encoding='utf-8' #亂碼時,加上這個就好,使用utf-8編碼
#print(type(htmlfile)) #印出網頁源代碼,因為得到一個物件,我這邊要取出物件中的文字
#print(objsoup.prettify()) #印出美化後的網頁源代碼

#domain check
def domain_check(domain):
    match domain:
        case 'yahoo.com':
            #如果條件match,就執行以下事情
            #抓文章標題以及內文
            res.encoding='utf-8'
            #開始使用bs4 解析
            objsoup2=BeautifulSoup(res.text,"lxml")
            # Find all of the text between paragraph tags and strip out the html
            content_body=objsoup.find('div',{"class":"caas-body"})
            for content in content_body:
                #過濾掉 更多 TVBS 報導
                if "更多 TVBS 報導" in content.getText():
                    print('')
                else:
                    print(content.getText())
            return ...
        case 'chinatimes.com':
            res.encoding='utf-8'
            return ...
        case 'udn.com':
            res.encoding='utf-8'
            return ...
        case 'cna.com.tw':
            res.encoding='utf-8'
            return ...
        case 'setn.com':
            res.encoding='utf-8'
            return ...
        case 'ltn.com.tw':
            res.encoding='utf-8'
            return ...
        case _:
            return "url missing!"

#開始使用bs4 解析
objsoup=BeautifulSoup(htmlfile.text,"lxml")

#取得objsoup所有的文字
#print(objsoup.get_text())

#找到所有h3標籤
#all_h3_tag=objsoup.find_all('h3')
#for texts in all_h3_tag:
#    print(texts.text)
    #pass


#找到所有google新聞的link
url_link_list=[]
h3_all_links=objsoup.find_all('h3',{"class":"ipQwMb ekueJc RD0gLb"})
for h3_all_link in h3_all_links:
    url_link_list.append(h3_all_link.find('a')['href'])
#    print(h3_all_link.find('a')['href'])

#前往每一個link抓標題以及內文
#先前往抓到的第一篇好了 yahoo新聞
#print(url_link_list[0])
#news1=requests.get(url_link_list[0],headers=headers,timeout=3)#他這邊請求website後,得到一個物件

#連到多家新聞媒體
for link in url_link_list:
    url='https://news.google.com/'+str(link)
    res=requests.get(url,headers=headers,timeout=2) #對這個link進行連線
    if res.status_code==requests.codes.ok:
        print('ok')
    news_url=res.request.url #特定新聞媒體的url

    #判斷連到的是哪個domain,以抓去特定媒體的內文tag
    #解析domain    
    te_result = tldextract.extract(news_url)
    domain = '{}.{}'.format(te_result.domain, te_result.suffix)

    domain_check(domain) #給domain check 檢查一下

    #解析htmlfile
    def parse_htmlfile():
        objsoup=BeautifulSoup(res.text,'lxml')
