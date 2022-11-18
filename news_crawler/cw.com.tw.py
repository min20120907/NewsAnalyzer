import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
ua=UserAgent()
usar=ua.random 
headers={'user-agent':usar}
url='https://www.cw.com.tw/article/5123601'
res=requests.get(url,headers=headers)
if res.status_code==requests.codes.ok:
    print('cw.com.tw ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('div',{"class":"article__head"}).find('h1')
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find('div',{"class":"article__content py20"}).find_all('p')
for content in contents:
    print(content.text)
