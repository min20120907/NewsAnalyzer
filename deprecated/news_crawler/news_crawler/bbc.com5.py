import requests
from bs4 import BeautifulSoup
url='https://www.bbc.com/zhongwen/trad/chinese-news-63555655'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('bbc.com ok')
objsoup=BeautifulSoup(res.text,'lxml')
ban_set={"© 2022 BBC. BBC對外部網站內容不負責任。 閱讀了解我們對待外部鏈接的做法。","圖像來源，Reuters"}
title=objsoup.find('strong',{"class":"ewk8wmc0 bbc-uky4hn eglt09e1"})
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find_all('p')
for content in contents:
    if  content.text in ban_set:
        pass
    else:
        print(content.text)