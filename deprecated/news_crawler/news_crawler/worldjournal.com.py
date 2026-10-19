import requests
from bs4 import BeautifulSoup
url='https://www.worldjournal.com/wj/story/121186/6807237'
ban_set={'上一則','下一則'}
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('worlfjournal.com ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('div',{"class":"wrapper-left"}).find('section',{"class":"article-content__wrapper"}).find('h1',{"class":"article-content__title"})
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find('section',{"class":"article-content__editor"}).find_all('p')
for content in contents:
    if content.text in ban_set:
        break
    else:
        print(content.text)