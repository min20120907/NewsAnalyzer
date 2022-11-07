import requests
from bs4 import BeautifulSoup
url='https://news.google.com/'+'./articles/CBMi2QFodHRwczovL3R3Lm5ld3MueWFob28uY29tLyVFNSVCOSVCNCVFOSVBMyVBRiVFOSU4QyVBMiVFNSU4NSVBOCVFNSU4RCU4NyVFNyVBOSVCQS0lRTUlOEMlOTclRTklOUYlOTMlRTklQTMlOUIlRTUlQkQlODgtJUU1JTk2JUFFJUU2JTk3JUE1MjUlRTklODAlQTMlRTclOTklQkMtJUU5JUE5JTlBJUU0JUJBJUJBJUU2JTg4JTkwJUU2JTlDJUFDJUU2JTlCJTlELTA0MDA0NTU2Mi5odG1s0gHhAWh0dHBzOi8vdHcubmV3cy55YWhvby5jb20vYW1waHRtbC8lRTUlQjklQjQlRTklQTMlQUYlRTklOEMlQTIlRTUlODUlQTglRTUlOEQlODclRTclQTklQkEtJUU1JThDJTk3JUU5JTlGJTkzJUU5JUEzJTlCJUU1JUJEJTg4LSVFNSU5NiVBRSVFNiU5NyVBNTI1JUU5JTgwJUEzJUU3JTk5JUJDLSVFOSVBOSU5QSVFNCVCQSVCQSVFNiU4OCU5MCVFNiU5QyVBQyVFNiU5QiU5RC0wNDAwNDU1NjIuaHRtbA?hl=zh-TW&gl=TW&ceid=TW%3Azh-Hant'
url2='https://udn.com/news/story/6809/6737700'
res=requests.get(url2)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
title=objsoup.find('h1',{"class":"article-content__title"})
#印出title的文字
print("新聞標題: ",title.text)
contents=objsoup.find_all('div',{"class":"article-content__paragraph"})
contents_list=[]
print("文章內容: ")
for content in contents:
    contents_list.append(content)
    print(str(content.text.strip(' ')).replace('\n',' '))
