from flask import Flask, redirect, url_for, request, make_response
from News import News
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 資料庫參數設定,注意這邊的設定要依據使用者而定
db_settings = {
    "host":"127.0.0.1",
    "port":3306,
    "user":"tengsnake",
    "password":"1234",
    "db":"NewsAnalyzer",
    "charset":"utf8"
}

@app.route('/extract', methods = ['GET'])
def extract():
    # create news objects
    a = News(request.args.get('title'))
    # submit the News object to the mysql server
    a.submitSQL(db_settings)
    response = a.toHTML()

    # return the results to the Flask server
    return response
    
if __name__ == '__main__':
    app.run(host="0.0.0.0",port="5005",  ssl_context=('/etc/letsencrypt/archive/na.shipaicraft.com/fullchain1.pem', '/etc/letsencrypt/archive/na.shipaicraft.com/privkey1.pem'), debug = True)


