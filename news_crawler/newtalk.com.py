import requests
from bs4 import BeautifulSoup
url2='https://newtalk.tw/news/view/2022-11-04/841383'
res=requests.get(url2)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
# Find all of the text between paragraph tags and strip out the html
title=objsoup.find('h1',{"class":"content_title"})
print("新聞標題: ",title.text)
VALID_TAGS = ['p']
print("文章內容: ")
contents=objsoup.find('div',{"id":"news_content"}).find_all('p')
for content in contents:
    print(content.text)

    
