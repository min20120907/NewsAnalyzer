CREATE TABLE news_titles_contents (
  ID INT PRIMARY KEY,
  news_title VARCHAR(255) NOT NULL,
  news_content TEXT NOT NULL,
  news_link VARCHAR(255) NOT NULL,
  news_title_kw VARCHAR(255),
  news_content_kw VARCHAR(255),
  sentiment_analysis VARCHAR(255),
  createdDate DATETIME NOT NULL,
  post_title VARCHAR(255),
  post_kw VARCHAR(255),
  fcc_result VARCHAR(255)
);
