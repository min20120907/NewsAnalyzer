import pymysql
import datetime

Now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# 資料庫參數設定
db_settings = {
    "host":"127.0.0.1",
    "port":3306,
    "user":"phpmyadmin",
    "password":"jefflin123",
    "db":"result",
    "charset":"utf8"
}
db = pymysql.connect(**db_settings)
#建立操作游標
cursor = db.cursor()
#SQL語法
sql = "INSERT INTO csvfileresult(ID,news_title,news_content,createdDate) VALUES ('0','russia','russia','"+ str(Now) +"')"
#執行語法

try:
  cursor.execute(sql)
  #提交修改
  db.commit()
  print('success')
except:
  #發生錯誤時停止執行SQL
  db.rollback()
  print('error')

#關閉連線
db.close()

#輸出：success
# 與資料庫的連線建立完成後，要進行相關的操作，
# 需要建立Cursor(指標)物件來執行，這邊使用Python的with陳述式，當資料庫存取完成後，自動釋放連線
