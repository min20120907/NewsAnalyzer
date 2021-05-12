# News Analyzer
## Project Members

Leader 408850013 林倉裕\
Member 408850310 蔡沛騰\
Member 408850492 柯智懷\
Member 408854015 林中南

## Goal

The goal is to demonstrate technologies that can be used to improve prevention of the spread of fake news on Facebook, these technologies including a simple interface to compare source news with other related articles, text recognize system such as JIEBA, and a transparent user report system that will also allow public and professionals of a variety of fields to help submit and examine reports for fake or biased news if they want to.

## Platforms

Open source on GitHub.

Platform: Web Application, Chromium Extention

Browser Client Languages: HTML, CSS, JavaScript

Middle Tier Languages and Libraries: Python; Flask, BERT, JIEBA

Backend Database Management System: mySQL or MariaDB, yet to be determined

## Functions

The functions listed here are partly logical, not necessarily physically implemented under the exact name or being made as a single physical function.

*Extension: Interface Preperation Functions*
DetectWebsite(), Append(), Search()

*Extension: Middle Tier Functions*
TextRecognization()

*Extension: Interface Trigger (User Interaction) Functions*
Toggle(), Expand(), ObviousReport(), Rate(), BugReport(), Contribute()

*Database: Manipulation, Calculation and Administration Functions*
Weight(), Hide(), Show()

*Webpage: Interface Preperation Functions*
ShowReport(), ShowRating(), ShowBugs(), ShowSubmissions()

*Webpage: Interface Trigger (User Interaction) Functions*
Upvote(), Downvote()



## Database Attributes

#### Reported_Links
_Reported_ID(INT AUTO_INCREAMENT)_,\
Reported_URL(VARCHAR, 2048),\
Domain(VARCHAR, 2048), \

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
_Rating_ID(INT AUTO_INCREAMENT)_,
___
_Reported_ID(INT)_,
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
