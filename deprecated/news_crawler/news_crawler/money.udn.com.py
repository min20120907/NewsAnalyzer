import requests
from bs4 import BeautifulSoup
url='https://money.udn.com/money/story/5607/6763523?from=edn_maintab_index'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('money udn ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('div',{"class":"article-layout-wrapper"}).find('h1')
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find('section',{"class":"article-body__editor"}).find_all('p')
for content in contents:
    print(content.text.replace(' ','').strip())