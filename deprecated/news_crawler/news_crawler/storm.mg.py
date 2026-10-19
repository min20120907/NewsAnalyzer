import requests
from bs4 import BeautifulSoup
url2='https://www.storm.mg/article/4575743'
res=requests.get(url2)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1',{"id":"article_title"})
ban_set={'[啟動LINE推播] 每日重大新聞通知'}
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find('div',{"id":"CMS_wrapper"}).find_all('p')
for content in contents:
    if content.text in ban_set:
        pass
    elif '更多風傳媒報導' in content.text:
        break
    else:
        print(content.text)
