const fs = require('fs');
const got = require('got');
const jsdom = require("jsdom");
var ping = require('ping');
const { JSDOM } = jsdom;
const vgmUrl = 'https://dorm.nctu.edu.tw/smsauth/12/pc.php?declare=true&params=pwd&orgi=http://210.71.78.162/&force_modify_password=';
var hosts = ['8.8.8.8'];

hosts.forEach(function (host) {
    ping.sys.probe(host, function (isAlive) {
        while (true) {
            var msg = isAlive ? 'host ' + host + ' is alive' : 'host ' + host + ' is dead';
            console.log(msg);
            if (!isAlive) {
                got(vgmUrl).then(response => {
                    const dom = new JSDOM(response.body);
                    console.log(dom.window.document.querySelector('title').textContent);
                    var name_s = "0812244";
                    var pwd_s = "TWUmatth893&12980ew";
                    var name = dom.window.document.getElementById("password_name");
                    var pwd = dom.window.document.getElementById("password_pwd");
                    var submit = dom.window.document.getElementById("password_submitBtn");
                    dom.window.document.getElementById("password_name").value = name_s;
                    dom.window.document.getElementById("password_pwd").value = pwd_s;
                    dom.window.document.addEventListener('click', function () {
                        console.log('test');
                    });
                    var evt = dom.window.document.createEvent("HTMLEvents");
                    evt.initEvent("click", false, true);
                    submit.dispatchEvent(evt);
                }).catch(err => {
                    console.log(err);
                });
            }
        }
    });
});