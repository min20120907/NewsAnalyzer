import requests
from bs4 import BeautifulSoup
url='https://www.mirrormedia.mg/story/20221118edi032/'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1',{"class":"story__title"})
ban_set={"更多內容，歡迎鏡週刊紙本雜誌、鏡週刊數位訂閱、了解內容授權資訊。"}
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find_all('p',attrs={"class":"g-story-paragraph"})
for content in contents:
    if '更多內容，歡迎鏡週刊紙本雜誌、鏡週刊數位訂閱、了解內容授權資訊。' in content.text: 
        break
    else:
        print(content.text)
