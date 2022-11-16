import requests
from bs4 import BeautifulSoup
url='https://tw.news.yahoo.com/%E8%94%A3%E8%90%AC%E5%AE%89-%E5%BA%A6%E5%B7%AE%E9%BB%9E%E8%A2%AB%E5%A4%AA%E5%A4%AA%E7%9F%B3%E8%88%AB%E4%BA%98%E5%88%86%E6%89%8B-%E5%8B%B8%E5%92%8C%E9%97%9C%E9%8D%B5%E4%BA%BA%E6%98%AF-%E4%BB%96-135443409.html'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('yahoo.com ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('header',{"class":"caas-header"}).find('h1')
ban_set={"更多 TVBS 報導"}
print("新聞標題: ",title.text)
contents=objsoup.find('div',{"class":"caas-body"}).find_all('p')
print("文章內容: ")
for content in contents:
    if  content.text in ban_set:
        pass
    else:
        print(content.text)
   