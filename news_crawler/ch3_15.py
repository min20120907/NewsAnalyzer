import urllib.request
url='http://www.tku.edu.tw/'

htmlfile=urllib.request.urlopen(url,timeout=2.0) #請求獲得網頁物件
print(type(htmlfile))
#print(htmlfile) 
#print(htmlfile.read()) #可以看到是二進位字串顯示
#print(htmlfile.read().decode('utf-8')) #正確顯示

print("version",htmlfile.version)
print('address',htmlfile.geturl())
print('下載',htmlfile.status)
for header in htmlfile.getheaders():
    print(header)