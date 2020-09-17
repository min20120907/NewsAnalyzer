import os
import requests
import time
import csv
import jieba
from sklearn import preprocessing
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.naive_bayes import MultinomialNB
jieba.set_dictionary('dict.txt.big')

filename = '【AI訓練】-標題判讀 - 工作表1.csv'

data = []
# title = []
correct_category = []
correct_category_2 = []
correct_category_3 = [] 
with open(filename, newline='') as csvfile:
	
	rows = csv.reader(csvfile)
	
	for row in rows:
		title = row[0]
		seg_title = list(jieba.cut(title))
		correct_category.append(row[1])
		correct_category_2.append(row[2])
		correct_category_3.append(row[3])
		data.append(' '.join(seg_title))
		

# print(correct_category)

# print(data)
# print(correct_category)

labelEncoder = preprocessing.LabelEncoder()
correct_category = labelEncoder.fit_transform(correct_category)
# correct_category_2 = labelEncoder.fit_transform(correct_category_2)
# correct_category_3 = labelEncoder.fit_transform(correct_category_3)

# print(correct_category)

countVectorizer = CountVectorizer(stop_words=[',' , '，', '.', '。', '?', '？', '!', '！', '#', '＃', '/', '／', ':', '：', '(', '（', ')', '）', '『', '「', '【', '〖', '［', '』', '」', '】', '〗', '］', '[', ']', '-', '_', '＿', '——', '－', '-', '−', '我', '你','妳', '他', '她', '它', '祂', '是', '的', '了', '呢', '嗎', '問', '問題', '問卷', '什麼', '新聞', '分享', '討論', '這個', '那個', '哪個', '最', '爆', '傳', '驚魂', '這項', '曝', '這招', '那招', '什麼', '驚', '推'])
x_train_count = countVectorizer.fit_transform(data)

# print(x_train_count.shape)
# print(x_train_count)

tfidfTransformer = TfidfTransformer()
x_train_tfidf = tfidfTransformer.fit_transform(x_train_count)

# print(x_train_tfidf.shape)
# print(x_train_tfidf)

nbClassfier = MultinomialNB()
nbClassfier.fit(x_train_tfidf, correct_category)
# nbClassfier.fit(x_train_tfidf, correct_category_2)
# nbClassfier.fit(x_train_tfidf, correct_category_3)


x = input('Input a title or sentence:')

x = list(jieba.cut(x))
x = ' '.join(x)
print('After jieba text segmentation:', x)

x_count = countVectorizer.transform([x])
x_tfidf = tfidfTransformer.transform(x_count)

print('After countVectorizer:')
print(x_count)

print('After tfidfTransformer:')
print(x_tfidf)

predicted = nbClassfier.predict(x_tfidf)
print('預測結果=>', labelEncoder.inverse_transform(predicted))
