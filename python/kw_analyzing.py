from keybert import KeyBERT
import jieba
from textblob import TextBlob
import csv
model = KeyBERT('LaBSE')
def extract(title):
    keywords = []
    splitted_title = " ".join(jieba.cut(title))
    # print("The Title is:\n",splitted_title)
    keywords = model.extract_keywords(splitted_title,stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推']) 
    return keywords

# Main Program #
# setting device on GPU if available, else CPU
colnames = ['新聞來源', '新聞標題','關鍵字1','關鍵字2','關鍵字3']
# open the file in universal line ending mode 
with open('../db/AI_keywords.csv', 'rU') as infile:
  # read the file as a dictionary for each row ({header : value})
  reader = csv.DictReader(infile)
  data = {}
  for row in reader:
    for header, value in row.items():
      try:
        data[header].append(value)
      except KeyError:
        data[header] = [value]
titles= data['新聞標題']
for a in titles:
    keywords = extract(a)
    print(keywords)
