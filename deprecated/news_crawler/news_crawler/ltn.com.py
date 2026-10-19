import requests
from bs4 import BeautifulSoup
url2='https://news.ltn.com.tw/news/world/breakingnews/4112774'
res=requests.get(url2)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1')
ban_set={"請繼續往下閱讀...","不用抽 不用搶 現在用APP看新聞 保證天天中獎"}
print("新聞標題: ",title.text)
contents=objsoup.find('div',{"class":"text boxTitle boxText"}).find_all('p')
print("文章內容: ")
for content in contents:
    if content.text in ban_set:
        break
    else:
        print(content.text)
