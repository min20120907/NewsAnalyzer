import requests
import pandas as pd
import csv
from bs4 import BeautifulSoup
main_title=[]
news_content=[]
string1=''
url='https://www.bbc.com/zhongwen/trad/world-61021569'
res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('bbc.com ok')
objsoup=BeautifulSoup(res.text,'lxml')
ban_set={"© 2022 BBC. BBC對外部網站內容不負責任。 閱讀了解我們對待外部鏈接的做法。","圖像來源，Reuters"}
title=objsoup.find('h1',{"class":"bbc-1tk77pb e1p3vdyi0"})
print("新聞標題: ",title.text)
main_title.append(title.text)
print(main_title)
print("文章內容: ")
contents=objsoup.find_all('p')


for content in contents:
    if  content.text in ban_set:
        pass
    else:
        #print(content.text)
        news_content.append(content.text)
        string1+=content.text
print(string1)


# 開啟輸出的 CSV 檔案
with open('output.csv', 'w', newline='') as csvfile:
  # 建立 CSV 檔寫入器
  writer = csv.writer(csvfile)

  # 寫入一列資料
  writer.writerow(['news_title', 'news_content'])
  # 寫入另外幾列資料
  writer.writerow([title.text,string1])
  #writer.writerow([])