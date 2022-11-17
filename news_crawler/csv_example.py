import csv
l1 = ['a', 'b', 'c', 'd', 'e']
l2 = ['f', 'g', 'i', 'j','k']
l3 = ['l', 'm', 'n', 'o', 'p']
l4 = ['q', 'r', 's', 't','u']
l5 = ['v', 'w', 'x', 'y', 'z']
# create five list
#ip() 函式壓縮我們的 5 個列表並將它們更改為row。
r=zip(l1, l2, l3, l4, l5)
#使用 open() 函式開啟我們的 CSV，並使用 csv.writer() 函式使我們的 CSV 檔案準備好寫入
with open('sample csv','w') as s:
    w=csv.writer(s)
    for row in r :
        w.writerow(row)