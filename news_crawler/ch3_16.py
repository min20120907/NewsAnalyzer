from urllib import parse
s='台灣積體電路製造'
url_code=parse.quote(s) #將中文轉成url 編碼
print("url編碼:",url_code)
code=parse.unquote(url_code)
print("中文編碼:",code)