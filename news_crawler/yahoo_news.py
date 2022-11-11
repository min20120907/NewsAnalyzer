import requests
from bs4 import BeautifulSoup
url='https://news.google.com/'+'./articles/CBMi2QFodHRwczovL3R3Lm5ld3MueWFob28uY29tLyVFNSVCOSVCNCVFOSVBMyVBRiVFOSU4QyVBMiVFNSU4NSVBOCVFNSU4RCU4NyVFNyVBOSVCQS0lRTUlOEMlOTclRTklOUYlOTMlRTklQTMlOUIlRTUlQkQlODgtJUU1JTk2JUFFJUU2JTk3JUE1MjUlRTklODAlQTMlRTclOTklQkMtJUU5JUE5JTlBJUU0JUJBJUJBJUU2JTg4JTkwJUU2JTlDJUFDJUU2JTlCJTlELTA0MDA0NTU2Mi5odG1s0gHhAWh0dHBzOi8vdHcubmV3cy55YWhvby5jb20vYW1waHRtbC8lRTUlQjklQjQlRTklQTMlQUYlRTklOEMlQTIlRTUlODUlQTglRTUlOEQlODclRTclQTklQkEtJUU1JThDJTk3JUU5JTlGJTkzJUU5JUEzJTlCJUU1JUJEJTg4LSVFNSU5NiVBRSVFNiU5NyVBNTI1JUU5JTgwJUEzJUU3JTk5JUJDLSVFOSVBOSU5QSVFNCVCQSVCQSVFNiU4OCU5MCVFNiU5QyVBQyVFNiU5QiU5RC0wNDAwNDU1NjIuaHRtbA?hl=zh-TW&gl=TW&ceid=TW%3Azh-Hant'

res=requests.get(url)
if res.status_code==requests.codes.ok:
    print('ok')
objsoup=BeautifulSoup(res.text,'lxml')
# Find all of the text between paragraph tags and strip out the html
title=objsoup.find('header',{"class":"caas-header"}).find('h1')
ban_set={"更多 TVBS 報導"}
print("新聞標題: ",title.text)
content_body=objsoup.find('div',{"class":"caas-body"})
print("文章內容: ")
for content in content_body:
    if  content.text in ban_set:
        pass
    else:
        print(content.getText())
