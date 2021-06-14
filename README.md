# News Analyzer

## Goal

The goal is to demonstrate technologies that can be used to improve prevention of the spread of fake news on Facebook, these technologies including a simple interface to compare source news with other related articles, text recognize system such as JIEBA, and a transparent user report system that will also allow public and professionals of a variety of fields to help submit and examine reports for fake or biased news if they want to.

## Installation
### Client
 Go to chrome store with the link below and press "add to chrome" button.  
### Server
With server side, we have the features as following below, and all the scripts are storing inside python folder:  
 1. CSV keywords analyzing tool (local): kw_analyzing_[algo].py
 2. Flask keyword extracting server (HTTPS): news_extract.py  
#### Prequirements
 - Python 3.8
 - Flask
 - Jieba
 - PyTorch
 - KeyBERT
#### Prerequirements Installation
    pip3 install -r requirements.txt


## Extension Link
https://chrome.google.com/webstore/detail/news-analyzer/hedmeapammhcjoelaceokinbhgjiiifk?hl=zh-TW&authuser=0

## Presentation
https://docs.google.com/presentation/d/13tSNQkl2zfKoES5x7gSMWOmaYE6C3uziWJS8KeCy4Ro/edit#slide=id.p2

## IMPORTANT NOTICE!!!!
**This application is using free licence of Google Custom Search API, please use it wisely, because there are currently 12,700 queries per day.**  
And this project is focus on the users in Taiwan or other Mandarin speaking countries, other locale would be differ in the results, if you would like to contribute this project feel free to pull the request.

## Official Webpage
**Coming Soon...**

## Platforms

Open source on GitHub.

Platform: Web Application, Chromium Extention

Browser Client Languages: HTML, CSS, JavaScript

Middle Tier Languages and Libraries: Python; Flask, BERT, JIEBA

Backend Database Management System: mySQL or MariaDB, yet to be determined

## Functions

The functions listed here are partly logical, not necessarily physically implemented under the exact name or being made as a single physical function.

**`UI_Elements()`**    
- getChildNodesByClassName(DOM object, string): DOM array  
- fetch_posts(void): DOM object   Calls getChildNodesByClassName()  
- FacebookLinkParse(URL): URL  
- queryOf(string): string   
- getLink(integer): DOM object  Calls FacebookLinkParse() and queryOf()

*UI_Elements(Creates linkpost objects)：*  
- append_button(void): DOM object  Calls getLink() 

*UI_Elements(Creates resultFrame and button objects):*  
- createElementFromHTML(string): DOM object  

**`button()`**
- onclick(void): void  If there exists a sibling resultFrame object,Triggers sibling resultFrame object to react,and throws exception,else creates a sibling resultFrame object 
 
**`insert.js()`**  
- detectLoad(action): boolean  
- delay(integer): promise  
- detectScroll(action): DOM object  

**`checkFacebook.js()`**
- areYouInFacebook(string): boolean  

**`background.js()`**  
- executeScript(file): boolean  
- resultFrame(Creates a table object):  

**`resultFrmae()`**
- toggleOnOff(void): CSS text  If there exists a sibling table object,triggers sibling table object to react,and throws exception.  

**`exception.js()`**  
- TargetExistedException(string, string): error object  

**`table()`**  
- fetch_results(void): DOM objects  
- Creates an icon object:  
- search_google(string, DOM object): string    Calls fetch_results()  
- keyword_extract(string, DOM object): string  Calls search_google()  



*Database: Manipulation, Calculation and Administration Functions*  
Weight(), Hide(), Show()  

*Webpage: Interface Preperation Functions*  
ShowReport(), ShowRating(), ShowBugs(), ShowSubmissions()  

*Webpage: Interface Trigger (User Interaction) Functions*  
Upvote(), Downvote()  



## Database Attributes

#### Reported_Links
Reported_ID(INT AUTO_INCREAMENT),
___
Reported_URL(VARCHAR, 2048),\
Domain(VARCHAR, 2048),

```
FakeReport(SMALLINT),
BiasedReport(SMALLINT),
OutdatedReport(SMALLINT)
```
^If report number too large, automatically hidden^\
OverallScore(SMALLINT, 0~5),\
Rated_Pinned(SMALLINT, 0=Normal, 1=Pinned, 2=Hidden),\
FirstReportDate(DATE)

#### Contributed_Links
_Contribution_ID(INT AUTO_INCREAMENT)_,\
Contribution_URL(VARCHAR, 2048), \
Pinned(TINYINT),\
ContributedDate(DATE)

#### Rating
Rating_ID(INT AUTO_INCREAMENT),
___
Reported_ID(INT),
___
Page_Reli(SMALLINT),\
Cf_Poss(SMALLINT),\
Phi_Poss(SMALLINT),\
Outdated(SMALLINT),\
Domain_Reli(SMALLINT),\
RatedDate(DATE)

#### Keywords
Keyword_ID (INT, AUTO_INCREMENT),
___
Title(VARCHAR,100),\
Keyword1(VARCHAR,20),\
Keyword2(VARCHAR,20),\
Keyword3(VARCHAR,20)

#### Bug_Report
Bug_ID(INT, AUTO_INCREMENT),
___
DATE(DATETIME),\
COMMENT(VARCHAR,1000),\
IMAGE(IMAGE)

## Contact Information
If you have any bugs or any issues on this chrome extension feel free to establish issues or pull request on Github, or send a email to me: jefflin.je598@gmail.com, and if it is possible, giving us some donation or Google Custom Search API key will be much appreciated!  
  
  
XMR:47Dt6wfBx37W3VNVFofU1cM1RmBoXfBvvNivdcc8cpWpejuubuyGqeKL45JHHJ9wVc4DN7B8zkVyM1WMctd8imMG5YXnU6d  
ETH:0x62C8d6Dbb39141Db60C0BD60C4c2111079438E04  
XCH:xch1uezmv85upf8geynz7qpqad37m9ju8p7ug3ucm87f64lhvjr4tdns4rwntc
