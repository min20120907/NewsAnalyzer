import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
ua=UserAgent()
usar=ua.random
headers={'user-agent':usar}
url='https://cn.wsj.com/articles/%E4%BF%84%E7%BE%85%E6%96%AF%E7%A8%B1%E5%8F%AF%E8%83%BD%E6%94%BB%E6%93%8A%E5%9C%A8%E7%83%8F%E5%85%8B%E8%98%AD%E6%88%B0%E7%88%AD%E4%B8%AD%E6%8A%95%E5%85%A5%E4%BD%BF%E7%94%A8%E7%9A%84%E7%BE%8E%E5%9C%8B%E5%95%86%E6%A5%AD%E8%A1%9B%E6%98%9F-121666916107'
res=requests.get(url,headers=headers)
if res.status_code==requests.codes.ok:
    print('wsj.com ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1',{"class":"wsj-article-headline"})
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find('div',{"class":"wsj-snippet-body"}).find_all('p')
for content in contents:
    print(content.text)