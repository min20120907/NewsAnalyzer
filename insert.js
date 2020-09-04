
console.log("insert javascript executed");
//Detecting the page if it is facebook.
window.addEventListener("load", areYouInFacebook);

//Elements proclaiming.
var innerPost = document.getElementsByClassName("_1dwg _1w_m _q7o");
var linkPost = document.getElementsByClassName("_52c6");
var post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
var btn = [innerPost.length];
var ifrm = [innerPost.length];
var g = [innerPost.length];
var table = [innerPost.length];
var tbody = [innerPost.length];
//var lpost = document.getElementsByClassName("_6m3 _--6");
//var operator_s = 0;
var entrSites=[
 "youthwant.com" ,
 "openfind.com" ,
 "timliao.com" ,
 "taconet.com" ,
 "gigigaga.com" ,
 "so-net.net" ,
 "don-net.com" ,
 "hongkong.com" ,
 "asiadog.com" ,
 "gotoya.com" ,
 "t2t.com" ,
 "moninet.com" ,
 "myweb.hinet.net" ,
 "udo.idv" ,
 "wutun.idv" ,
 "centurys.com.tw" ,
 "funf.tw" ,
 "portal.tw" ,
 "pig.tw" ,
 "taiwanurl.com" ,
 "263.net" ,
 "qq.com" ,
 "sohu.com" ,
 "china.com" ,
 "tom.com" ,
"netease.com" ,
"backchina.com" ,
"gjj.cc" ,
"qoos.com" ,
"qknet.net" ,
"facebook.com",
"kknews.cc",
"www.buzzhand.com",
"www1.daliulian.net",
"www.teepr.com",
"bomb01.com",
"cocomy",
"coco01.net",
 "cocotw.net",
"cocomy.net",
 "daliulian.net",
 "e04.tv",
 "how01.com",
"juksy.com",
"orange01",
"push01.com",
"read01",
"thegreatdaily",
"tw.gigacircle",
"tw.ptt01",
"twgreatdaily",
"whatfunny",
"momdata.blogspot.com",
"onefunnyjoke.com",
"gmter.com",
"gigacircle.com",
"share001.net",
 "shareba.com",
 "metalballs.com",
 "ptt01",
 "fun-vdo.com",
"sos.tw",
"zuopy.com",
 "eznewlife",
"ezvivi.com",
"youthwant.com.tw",
 "viralane.com",
 "newstube01",
 "eazon.com",
 "mama.tw",
"cocomy",
"baoxiaovideo.tv",
"apple01.net",
"likea.ezvivi.com"
];
for (var i = 0; i <= post.length - 1; i++) {
  btn[i] = document.createElement("BUTTON");
  btn[i].innerHTML = "more"; // Insert text
  btn[i].setAttribute("class", "btn btn-warning");

  btn[i].id = "btn_" + i;
  (function (i) {
    btn[i].onclick = function () {
	  console.log(i);
	  createIFrame(i);
    };
  })(i);
  post[i].setAttribute("btn_added", false);
}

for (var i = 0; i <= innerPost.length - 1; i++) {
  if (!innerPost[i].innerHTML.includes('class="_52c6"')) {
    btn[i].style.display = "none";
  }
  if (innerPost[i].innerHTML.includes('class="_52c6"')) {
    g[i] = document.createElement('div');
    g[i].id = "website_" + i;
  }
  innerPost[i].getElementsByClassName("_5pcp _5lel _2jyu _232_")[0].appendChild(btn[i]); // appendChild button to div
  console.log("button" + i + "created");
  post[i].setAttribute("btn_added", false);
}

var num = post.length - 1;
var ticking = false;
var last_known_scroll_position = 0;

window.addEventListener("scroll", function (e) {
  last_known_scroll_position = window.scrollY;

  if (!ticking) {
    window.requestAnimationFrame(function () {
      post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
      //setTimeout(function () { console.log("appendChilding..."); }, 5000);
      autoappendChild();
      ticking = false;
    });
  }
  ticking = true;
});

function autoappendChild() {	//autoappendChild

  for (var j = 0; j <= innerPost.length - 1; j++) {

    if (
      post[j].getAttribute("btn_added") == null
    ) {
      btn[j] = document.createElement("BUTTON");
	  
      btn[j].innerHTML = "more"; // Insert text
      btn[j].setAttribute("class", "btn btn-warning");

      btn[j].id = "btn_" + j;
      if (!innerPost[j].innerHTML.includes('class="_52c6"')) {
        btn[j].style.display = "none";
      }
      if (innerPost[j].innerHTML.includes('class="_52c6"')) {
        g[j] = document.createElement('div');
        g[j].id = "website_" + j;
      }
      (function (j) {
        btn[j].onclick = function () {
          createIFrame(j);
		  console.log(j);
		  //console.log("operator_s = "+ operator_s);
        };
      })(j);
      innerPost[j].getElementsByClassName("_5pcp _5lel _2jyu _232_")[0].appendChild(btn[j]); // appendChild button to div
      console.log("button" + j + "created");
      post[j].setAttribute("btn_added", false);
    }
  }
}

function toggleOnOff(operator_j) {	//toggleOnOff
  if (ifrm[operator_j].style.display == "none") {
    ifrm[operator_j].setAttribute("style", "display: block");
  } else {
    ifrm[operator_j].setAttribute("style", "display: none");
  }
}

function areYouInFacebook() {	//areYouInFacebook
  if (window.location.hostname == "www.facebook.com") {
    return true;
  } else {
    return false;
  }
}

function searchGoogle(googleQuery) {	//searchGoogle
if(!googleQuery.includes("中天新聞")){
  var searchUrl = "https://www.google.com/search?q=" + googleQuery.substring(0, 17) + "  -site:facebook.com -site:kknews.cc -site:google.com -site:yahoo.com -site:hinet.net -site:msn.com -site:pchome.com -site:yam.com -site:sina.com -site:cnet.com -site:seed.net. -site:url.com -site:kingnet.com -site:funp.com -site:youthwant.com -site:yahoo.com -site:cn.yahoo.com -site:openfind.com -site:timliao.com -site:taconet.com -site:gigigaga.com -site:so-net.net -site:don-net.com -site:hongkong.com -site:asiadog.com -site:gotoya.com -site:t2t.com -site:moninet.com -site:myweb.hinet.nethome1kiroro -site:udo.idv -site:wutun.idv -site:centurys.com.tw -site:funf -site:portal.tw -site:pig.tw -site:taiwanurl.com -site:263.net -site:qq.com -site:sohu.com -site:china.com -site:tom.com -site:china.com -site:netease.com -site:backchina.com -site:gjj.cc -site:qoos.com -site:qknet.net";
  }else{
  	var searchUrl = "https://www.google.com/search?q=" + googleQuery.substring(googleQuery.length-18,googleQuery.length ) + "  -site:facebook.com -site:kknews.cc -site:google.com -site:yahoo.com -site:hinet.net -site:msn.com -site:pchome.com -site:yam.com -site:sina.com -site:cnet.com -site:seed.net. -site:url.com -site:kingnet.com -site:funp.com -site:youthwant.com -site:yahoo.com -site:cn.yahoo.com -site:openfind.com -site:timliao.com -site:taconet.com -site:gigigaga.com -site:so-net.net -site:don-net.com -site:hongkong.com -site:asiadog.com -site:gotoya.com -site:t2t.com -site:moninet.com -site:myweb.hinet.nethome1kiroro -site:udo.idv -site:wutun.idv -site:centurys.com.tw -site:funf -site:portal.tw -site:pig.tw -site:taiwanurl.com -site:263.net -site:qq.com -site:sohu.com -site:china.com -site:tom.com -site:china.com -site:netease.com -site:backchina.com -site:gjj.cc -site:qoos.com -site:qknet.net";
  }
  
  return searchUrl;
}

function createElementFromHTML(htmlString) {	//createElementFromHTML
  var div = document.createElement('div');
  div.innerHTML = htmlString.trim();

  // Change this to div.childNodes to support multiple top-level nodes
  return div.firstChild; 
}

function loadFileToElement(filename, operator_n) {



  $(document).ready(function () {
    $.ajax({
      type: "GET",
      url: "https://morning-woodland-98584.herokuapp.com/" + filename,
      async: false,
      headers: {
        "x-requested-with": "xhr"
      },
      mode: 'cors',
      cache: 'default',
      success: function (text) {
        g[operator_n].innerHTML = text;
      }
    });
  });
}




function createIFrame(operator_k) {
  table[operator_k] = document.createElement("table");
  table[operator_k].id = "table_" + operator_k;
  table[operator_k].setAttribute("class", "table table-striped");

  tbody[operator_k] = document.createElement("tbody");

  table[operator_k].appendChild(tbody[operator_k]);


  var checkTarget = document.getElementById("iframe_" + operator_k); //some error 
  loadFileToElement(searchGoogle(innerPost[operator_k].getElementsByClassName("_6m3 _--6")[0].childNodes[1].childNodes[0].innerText), operator_k);
  var search_result = g[operator_k].getElementsByClassName("LC20lb");
  var icos = [document.createElement("img"), document.createElement("img"), document.createElement("img"), document.createElement("img"), document.createElement("img")]; //old icon functions
  for (var operator_q = 0; operator_q < search_result.length; operator_q++) {	//filter the entrance websites
    for (var operator_p = 0; operator_p < entrSites.length; operator_p++) {
      if (search_result[operator_q].innerHTML.includes(entrSites[operator_p])) {
        search_result[operator_q] = search_result[operator_q + 1];
      }
    }
  }
  
	var getLocation = function(href) {
		var l = document.createElement("a");
		l.href = href;
		return l;
  };
  
 
  for (var operator_r = 0; operator_r < 5; operator_r++) {	//set the icons on the search_results
  
	
    var string1 = search_result[operator_r].parentNode.href;
    var string2 = "http://"+ getLocation(string1).hostname;
    //string2.replace(window.location.href, "");
	string2 = string2 + "/favicon.ico";
    icos[operator_r].src = string2;
	
	
    icos[operator_r].width = 12;	//set width as 12
    icos[operator_r].height = 12;	//set height as 12
  }
 

  var tr_ele = [];

  tr_ele[0] = document.createElement("tr");
  tr_ele[1] = document.createElement("tr");
  tr_ele[2] = document.createElement("tr");
  tr_ele[3] = document.createElement("tr");
  tr_ele[4] = document.createElement("tr");

  if (checkTarget == null) {
    //if (search_result[operator_k] != null) {
      ifrm[operator_k] = document.createElement("div");
      for (var operator_m = 0; operator_m < search_result.length; operator_m++) {
	tr_ele[operator_m].appendChild(icos[operator_m]);
        tr_ele[operator_m].appendChild(search_result[operator_m].parentNode);
        tbody[operator_k].appendChild(tr_ele[operator_m]);
        table[operator_k].appendChild(tbody[operator_k]);
      }
      ifrm[operator_k].appendChild(table[operator_k]);
      ifrm[operator_k].id = "iframe_" + operator_k;
      innerPost[operator_k].getElementsByClassName("_5pcp _5lel _2jyu _232_")[0].appendChild(ifrm[operator_k]);
      ifrm[operator_k].setAttribute("style", "display: block");
      console.log("iFrame" + operator_k + "created");
    //}
  } else {
    console.log("iFrame" + operator_k + "already exists");
    toggleOnOff(operator_k);
  }
  return {search_result: search_result, icos: icos};
  
}
