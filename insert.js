
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
var entrSites = [	//Database for the entrance websites
  "yahoo.com",
  "msn.com",
  "facebook.com"
];
for (var i = 0; i <= post.length - 1; i++) {
  btn[i] = document.createElement("BUTTON");
  btn[i].innerHTML = "平衡一下"; // Insert text
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
	  
      btn[j].innerHTML = "平衡一下"; // Insert text
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
  var searchUrl = "https://www.google.com/search?q=" + googleQuery;
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
      url: "https://cors-anywhere.herokuapp.com/" + filename,
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
 // var icos = g[operator_k].getElementsByClassName("xA33Gc");
  for (var operator_q = 0; operator_q < search_result.length; operator_q++) {	//filter the entrance websites
    for (var operator_p = 0; operator_p < entrSites.length; operator_p++) {
      if (search_result[operator_q].innerHTML.includes(search_result[operator_p])) {
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
    var string2 = "https://"+ getLocation(string1).hostname;
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
    if (search_result[operator_k] != null) {
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
    }
  } else {
    console.log("iFrame" + operator_k + "already exists");
    toggleOnOff(operator_k);
  }
  return {search_result: search_result, icos: icos};
  
}
