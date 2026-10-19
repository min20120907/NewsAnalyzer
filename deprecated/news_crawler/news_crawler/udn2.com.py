import requests
from bs4 import BeautifulSoup
url='https://udn.com/news/story/6809/6737700'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1',{"class":"article-content__title"})
#印出title的文字
print("新聞標題: ",title.text)
contents=objsoup.find('div',{"class":"article-content__paragraph"}).find_all('p')
print("文章內容: ")
for content in contents:
    print(content.text.strip())
