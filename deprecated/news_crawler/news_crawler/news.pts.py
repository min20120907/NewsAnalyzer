import requests
from bs4 import BeautifulSoup
url2='https://news.pts.org.tw/article/608215'
res=requests.get(url2)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1',{"class":"article-title"})
#印出title的文字
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find_all('p')
for content in contents:
    print(content.text)
