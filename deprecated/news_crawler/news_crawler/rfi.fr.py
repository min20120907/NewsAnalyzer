import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
ua=UserAgent()
usar=ua.random 
headers={'user-agent':usar}
url='https://www.rfi.fr/tw/國際/20221110-英國對烏追加提供約1千枚地空導彈-英防相-俄羅斯正在慢慢輸掉戰爭'
try:
    res= requests.get(url,headers=headers)
except requests.exceptions.RequestException as e:  # This is the correct syntax
    raise SystemExit(e)
if res.status_code==requests.codes.ok:
    print("rfi.fr ok")
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('article').find('h1')
ban_set={'下載法廣應用程序跟蹤國際時事'}
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find('article').find('div',{"class":"t-content__body u-clearfix"}).find_all('p')
for content in contents:
    if content.text in ban_set:
        pass
    else:
        print(content.text)
