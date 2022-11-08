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
htmlfile.encoding='utf-8' #亂碼時,加上這個就好,使用utf-8編碼
#print(type(htmlfile)) #印出網頁源代碼,因為得到一個物件,我這邊要取出物件中的文字
#print(objsoup.prettify()) #印出美化後的網頁源代碼

def domain_check(domain,news_url):
    match domain:
        case 'yahoo.com':
            #如果條件match,就執行以下事情
            #抓文章標題以及內文
            res=requests.get(news_url)
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
        case 'chinatimes.com':
            res=requests.get(news_url)
            res.encoding='utf-8'
            res=requests.get(url)
            if res.status_code==requests.codes.ok:
                print('ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"article-title"})
            #印出title的文字
            print('新聞標題: ',title.text)
            print("文章內容: ")
            contents=objsoup.find_all('p')
            for content in contents:
                print(content.text)
        case 'udn.com':
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            title=objsoup.find('h1',{"class":"article-content__title"})
            #印出title的文字
            print("新聞標題: ",title.text)
            contents=objsoup.find_all('div',{"class":"article-content__paragraph"})
            contents_list=[]
            print("文章內容: ")
            for content in contents:
                contents_list.append(content)
                print(str(content.text.strip(' ')).replace('\n',' '))
        case 'cna.com.tw':
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            # Find all of the text between paragraph tags and strip out the html
            title=objsoup.find('h1')
            print("新聞標題: ",title.text)
            contents=objsoup.find_all('p')
            print("文章內容: ")
            for content in contents:
                print(content.text)
        case 'setn.com':
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            # Find all of the text between paragraph tags and strip out the html
            title=objsoup.find('h1',{"class":"news-title-3"})
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find_all('p')
            for content in contents:
                print(content.text)
        case 'ltn.com.tw':
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            # Find all of the text between paragraph tags and strip out the html
            title=objsoup.find('h1')
            #印出title的文字
            print("新聞標題: ",title.text)
            #contents=objsoup.find('div',{"class":"text boxTitle boxText"})
            contents=objsoup.find_all('p')
            print("文章內容: ")
            for content in contents:
                print(content.text)
        case 'ettoday.net':
            res=requests.get(news_url)
            res.encoding='utf-8'
            if res.status_code==requests.codes.ok:
                print('ok')
            objsoup=BeautifulSoup(res.text,'lxml')
            # Find all of the text between paragraph tags and strip out the html
            title=objsoup.find('h1',{"class":"title"})
            print("新聞標題: ",title.text)
            print("文章內容: ")
            contents=objsoup.find('div',attrs={"class":"story"})
            tests=contents.find_all('p')
            for test in tests:
                if(test.text=="省錢大作戰！超夯優惠等你GO"):
                    break
                else:
                    print(test.text)
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
    news_url=res.request.url #特定新聞媒體的url
    #解析domain    
    tld_result = tldextract.extract(news_url)
    domain = '{}.{}'.format(tld_result.domain, tld_result.suffix)
    domain_check(domain,news_url)
