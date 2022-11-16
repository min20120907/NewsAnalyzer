import requests
from bs4 import BeautifulSoup
url='https://tw.news.yahoo.com/%E9%A6%AC%E5%85%8B%E5%AE%8F%E5%B0%87%E8%A6%8B%E7%BF%92%E8%BF%91%E5%B9%B3-%E7%B1%B2%E6%96%BD%E5%A3%93%E4%BF%84%E5%9C%8B%E5%9B%9E%E7%83%8F%E5%85%8B%E8%98%AD%E6%88%B0%E7%88%AD%E8%AB%87%E5%88%A4%E6%A1%8C-023502832.html'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('yahoo.com ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1',{"data-test-locator":"headline"})
print("新聞標題: ",title.text)
contents=objsoup.find('div',{"class":"caas-body"}).find_all('p')
print("文章內容: ")
for content in contents:
    print(content.text)
   