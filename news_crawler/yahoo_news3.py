import requests
from bs4 import BeautifulSoup
#法新社
url='https://tw.tv.yahoo.com/%E4%BF%84%E7%BE%85%E6%96%AF%E5%85%A5%E4%BE%B5%E7%83%8F%E5%85%8B%E8%98%AD%E6%95%B2%E9%9F%BF%E8%AD%A6%E9%90%98-%E5%8F%B0%E7%81%A3%E6%95%85%E5%AE%AE%E6%BC%94%E7%B7%B4%E6%88%B0%E7%88%AD%E6%87%89%E8%AE%8A-034833441.html'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('yahoo.com ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1',{"class":"Fz(24px) Fw(b)"})
print("新聞標題: ",title.text)
contents=objsoup.find('div',{"class":"Mt(12px) Fz(16px) Lh(1.5) C(#464e56) Whs(pl)"})
print("文章內容: ")
print(contents.text)
   