<?php
 
$data = $_POST;
 
$dbhost = 'http://shipaicraft.asuscomm.com';
$dbuser = 'min20120907';
$dbpasswd = '輸入密碼';
$dbname = 'NewsAnalyzer';
$dsn = "mysql:host=".$dbhost.";dbname=".$dbname;
 
try
{
    $conn = new PDO($dsn,$dbuser,$dbpasswd);
    $conn->exec("SET CHARACTER SET utf8");
    $conn->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
}
catch(PDOException $e)
{
    echo "Connection failed: ".$e->getMessage();
}
 
$sql = "INSERT INTO `Contributed_Links`(Contribution_URL, Context) VALUES(:Contribution_URL, :Context)";
 
$dataArr = array(
':Contribution_URL' => $data['Contribution_URL'],
':Context' => $data['Context']);
 
try
{
    $sth = $conn->prepare($sql);    
    if($sth)
    {
        $result = $sth->execute($dataArr);
        if($result)//true or false
        {
        $result = 'success';
        echo json_encode($result);
        return;
        }
        else
        {
        $result = 'failed';
        echo json_encode($result);
        return;
        }
    }
}
catch(PDOException $e)
{
    echo "執行預存程序失敗. ".$e->getMessage();
}
?>