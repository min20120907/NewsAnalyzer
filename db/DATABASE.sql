CREATE DATABASE NewsAnalyzer;

CREATE TABLE Reported_Links
(
    Reported_ID      INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    Reported_URL     TEXT(2048),               
    Domain           TEXT(2048), 
    FakeReport       SMALLINT,             
    BiasedReport     SMALLINT, 
    OutdatedReport   SMALLINT,
/*If report number too large, automatically hidden*/
    OverallScore     SMALLINT    DEFAULT 0,/* still didn't set the 0-5*/
    Rated_Pinned     SMALLINT    DEFAULT 1,/*still didn't set the 0-2, 0=Normal, 1=Pinned, 2=Hidden*/
    
    FirstReportDate  DATE 
);
CREATE TABLE Contributed_Links
(
Contribution_ID      INT NOT NULL    AUTO_INCREMENT PRIMARY KEY,
Contribution_URL     TEXT(2048), 
Pinned               TINYINT,
ContributedDate      DATE
);

CREATE TABLE Rating
(
    Rating_ID        INT  NOT NULL  AUTO_INCREMENT PRIMARY KEY, 
    Reported_ID      INT NOT NULL,/* <Foreign key>*/
    Page_Reli        SMALLINT,
    Cf_Poss  SMALLINT, 
    Phi_Poss SMALLINT,
    Outdated SMALLINT,
    Domain_Reli SMALLINT,
    RatedDate DATE
);
CREATE TABLE Keywords
(
    Keyword_ID INT NOT NULL AUTO_INCREMENT PRIMARY KEY, 
    Title TEXT(100),
    Keyword1 TEXT(20),
    Keyword2 TEXT(20),
    Keyword3 TEXT(20)
);
CREATE TABLE Bug_Report
(
    Bug_ID INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    Bug_DATE DATETIME,
    COMMENT TEXT(1000),
    Bug_IMAGE LONGBLOB
);