import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import re
from tldextract import tldextract
from urllib import request
from requests import get
#設定fake-useragent
#假的user-agent,產生 headers
ua=UserAgent()
usar=ua.random #產生header 字串
headers={'user-agent':usar}
url='https://news.google.com/topstories?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'

htmlfile=requests.get(url,headers=headers,timeout=3)#他這邊請求website後,得到一個物件

if htmlfile.status_code==requests.codes.ok:
    print("成功連線到google news")
htmlfile.encoding='utf-8'

#開始使用bs4 解析
objsoup=BeautifulSoup(htmlfile.text,"lxml")


#找到所有google新聞的link
url_link_list=[]
h3_all_links=objsoup.find_all('h3',{"class":"ipQwMb ekueJc RD0gLb"})
for h3_all_link in h3_all_links:
    #print(h3_all_link.text)
    url_link_list.append(h3_all_link.find('a')['href'])
#    print(h3_all_link.find('a')['href'])
#把link拿出來看看
#print(url_link_list)
url_link_list_remove_dot=[]
for link in url_link_list:
    url_link_list_remove_dot.append(link.replace('./','',1))
#print(url_link_list_remove_dot)

#解決短網址問題
def shortlink_converter(url):
    resp = requests.get(url)
    return resp.url
    

#連到多家新聞媒體
for link in url_link_list_remove_dot:
    url='https://news.google.com/'+str(link)
    original_url=shortlink_converter(url)
    res=requests.get(original_url,headers=headers,timeout=2) 
    if res.status_code==requests.codes.ok:
        print('ok')
    

    #判斷連到的是哪個domain,以抓去特定媒體的內文tag
    #靠腰不是連過去後再抓嗎
    news_url=res.request.url #特定新聞媒體的url
    #解析domain    
    te_result = tldextract.extract(news_url)
    domain = '{}.{}'.format(te_result.domain, te_result.suffix)
    print(domain)
