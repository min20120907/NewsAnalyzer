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
contents=objsoup.find('div',{"class":"article-content AdAsia"})
contents=contents.find_all('p')
contents_list=[]
print("文章內容: ")
for content in contents:
    contents_list.append(content)
for content in contents_list:
    if "Photo Credit: BBC News" in content.text:
        pass
    elif "Photo Credit: Getty Images / BBC News" in content.text:
        pass
    elif "每月一杯咖啡的金額，支持優質觀點的誕生，享有更好的閱讀體驗。" in content.text:
        pass
    elif "本文經《BBC News 中文》授權轉載，原文發表於此"==content.text:
        break
    else:
        print(content.text)