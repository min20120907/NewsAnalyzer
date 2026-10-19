import requests
from bs4 import BeautifulSoup
url2='https://www.thenewslens.com/article/175883'
res=requests.get(url2)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1',{"class":"article-title"})
#印出title的文字
print("新聞標題: ",title.text)
contents=objsoup.find('div',{"class":"article-content AdAsia"}).find_all('p')
ban_set={"Photo Credit: BBC News","Photo Credit: Getty Images / BBC News","每月一杯咖啡的金額，支持優質觀點的誕生，享有更好的閱讀體驗。","本文經《BBC News 中文》授權轉載，原文發表於此","【加入關鍵評論網會員】每天精彩好文直送你的信箱，每週獨享編輯精選、時事精選、藝文週報等特製電子報。還可留言與作者、記者、編輯討論文章內容。立刻點擊免費加入會員！"}
print("文章內容: ")
for content in contents:
    if content.text in ban_set:
        pass
    else:
        print(content.text)