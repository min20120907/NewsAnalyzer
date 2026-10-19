import requests
from bs4 import BeautifulSoup
url='https://www.epochtimes.com/b5/22/11/20/n13869734.htm'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('epochtimes.com ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1',{"class":"title"})
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find('div',{"id":"artbody"}).find_all('p')
for content in contents:
    print(content.text)
