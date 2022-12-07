import requests
from bs4 import BeautifulSoup
url='https://www.rti.org.tw/news/view/id/2152378'
url2='https://www.rti.org.tw/news/view/id/2150127'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('section',{"class":"news-detail-box"}).find('h1')
title=title.text.replace(' 用Podcast訂閱本節目 ','').strip()
print("新聞標題: ",title.text.replace(' 用Podcast訂閱本節目 ','').strip())
print(type(title))
print("文章內容: ")
contents=objsoup.find('article').find_all('p')
for content in contents:
    print(content.text)