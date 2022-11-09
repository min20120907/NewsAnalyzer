import requests
from bs4 import BeautifulSoup
url2='https://www.ettoday.net/news/20221107/2374934.htm'
res=requests.get(url2)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
# Find all of the text between paragraph tags and strip out the html
title=objsoup.find('h1',{"class":"title"})
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find('div',attrs={"class":"story"})
tests=contents.find_all('p')
for test in tests:
    if(test.text=="省錢大作戰！超夯優惠等你GO"):
        break
    else:
        print(test.text)
