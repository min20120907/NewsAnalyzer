import requests
from bs4 import BeautifulSoup
url2='https://www.bbc.com/zhongwen/trad/world-63314791'
res=requests.get(url2)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1',{"class":"bbc-1tk77pb e1p3vdyi0"})
#印出title的文字
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find_all('p')
for content in contents:
    if "© 2022 BBC. BBC對外部網站內容不負責任。 閱讀了解我們對待外部鏈接的做法。" in content.text:
        pass
    elif "圖像來源，" in content.text:
        pass
    else:
        print(content.text)
