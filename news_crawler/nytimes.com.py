import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
ua=UserAgent()
usar=ua.random 
headers={'user-agent':usar}
url='https://cn.nytimes.com/china/20221117/china-affirms-ties-with-russia-but-signals-it-is-becoming-more-guarded-about-the-war/zh-hant/'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('nytimes.com ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('div',{"class":"article-header"}).find('h1')
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find_all('div',{"class":"article-paragraph"})
for content in contents:
    print(content.text)