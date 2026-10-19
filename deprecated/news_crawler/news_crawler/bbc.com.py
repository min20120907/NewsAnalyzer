import requests
import csv
from bs4 import BeautifulSoup
def csvfile_handler(title,content_str):
    with open('output_test2.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['news_title', 'news_content'])    
        writer.writerow([title.text,content_str])

content_str=''
url='https://www.bbc.com/zhongwen/trad/world-61021569'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('bbc.com ok')
objsoup=BeautifulSoup(res.text,'lxml')
ban_set={"© 2022 BBC. BBC對外部網站內容不負責任。 閱讀了解我們對待外部鏈接的做法。","圖像來源，Reuters"}
title=objsoup.find('h1',{"class":"bbc-1tk77pb e1p3vdyi0"})
print("新聞標題: ",title.text)
print("文章內容: ")
contents=objsoup.find_all('p')
for content in contents:
    if  content.text in ban_set:
        pass
    else:
        print(content.text)
        content_str+=content.text
print(content_str)
csvfile_handler(title,content_str)

