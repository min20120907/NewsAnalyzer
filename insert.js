//$('head').append('<link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.3.1/css/bootstrap.min.css" integrity="sha384-ggOyR0iXCbMQv3Xipma34MD+dH/1fQ784/j6cY/iJTQUOhcWr7x9JvoRxT2MZw1T" crossorigin="anonymous">');

console.log("insert javascript executed");

window.addEventListener("load", areYouInFacebook);
var innerPost = document.getElementsByClassName("_1dwg _1w_m _q7o");
var linkPost = document.getElementsByClassName("_52c6");
var post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
var btn = [innerPost.length];
var ifrm = [innerPost.length];
var linkingPost = [innerPost.length];
var g = [innerPost.length];
var span = [innerPost.length];
for (var i = 0; i <= post.length - 1; i++) {
  btn[i] = document.createElement("BUTTON");
  span[i] = document.createElement("span");
  span[i].setAttribute("class", "glyphicon glyphicon-link");
  btn[i].innerHTML = "平衡一下"; // Insert text
  btn[i].setAttribute("class","btn btn-primary");
  btn[i].appendChild(span[i]);
  btn[i].id = "btn_" + i;
  (function(i) {
    btn[i].onclick = function() {
      createIFrame(i);
      toggleOnOff(i);
    };
  })(i);
  post[i].setAttribute("btn_added", false);
}

for (var i = 0; i <= innerPost.length - 1; i++) {
  if (!innerPost[i].innerHTML.includes('class="_52c6"')) {
    btn[i].style.display = "none";
    linkingPost[i] = null;
  }      if(innerPost[i].innerHTML.includes('class="_52c6"')){
    g[i] = document.createElement('div');
    g[i].id = "website_"+i;
    linkingPost[i]=innerPost[i].getElementsByClassName("_52c6")[0];
  }
  innerPost[i].getElementsByClassName("_5pcp _5lel _2jyu _232_")[0].appendChild(btn[i]); // appendChild button to div
  console.log("button" + i + "created");
  post[i].setAttribute("btn_added", false);
}
var num = post.length - 1;
var ticking = false;
var last_known_scroll_position = 0;

window.addEventListener("scroll", function(e) {
  last_known_scroll_position = window.scrollY;

  if (!ticking) {
    window.requestAnimationFrame(function() {
      post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
      //setTimeout(function () { console.log("appendChilding..."); }, 5000);
      autoappendChild();
      ticking = false;
    });
  }
  ticking = true;
});

function autoappendChild() {

  for (var j = 0; j <= innerPost.length - 1; j++) {

    if (
      post[j].getAttribute("btn_added") == null
    ) {
      btn[j] = document.createElement("BUTTON");
      span[j] = document.createElement("span");
      span[j].setAttribute("class", "glyphicon glyphicon-link");
      btn[j].innerHTML = "平衡一下"; // Insert text
      btn[j].setAttribute("class","btn btn-primary");
      btn[j].appendChild(span[j]);
      btn[j].id = "btn_" + j;
      if (!innerPost[j].innerHTML.includes('class="_52c6"')) {
        btn[j].style.display = "none";
        linkingPost[j] = null;
      }
      if(innerPost[j].innerHTML.includes('class="_52c6"')){
        g[j] = document.createElement('div');
        g[j].id = "website_"+j;
        linkingPost[j]=innerPost[j].getElementsByClassName("_52c6")[0];
      }
      (function(j) {
        btn[j].onclick = function() {
          createIFrame(j);
          toggleOnOff(j);
        };
      })(j);
      innerPost[j].getElementsByClassName("_5pcp _5lel _2jyu _232_")[0].appendChild(btn[j]); // appendChild button to div
      console.log("button" + j + "created");
      post[j].setAttribute("btn_added", false);
    }
  }
}

function toggleOnOff(operator_j) {
  if (
    document.getElementById("iframe_" + operator_j).height == "100%" && document.getElementById("iframe_" + operator_j).width == "100%" 
  ) {
    document.getElementById("iframe_" + operator_j).height == 0 && document.getElementById("iframe_" + operator_j).width ==0; 
  } else {
    document.getElementById("iframe_" + operator_j).height == "100%" && document.getElementById("iframe_" + operator_j).width =="100%"; 
  }
}

function areYouInFacebook() {
  if (window.location.hostname == "www.facebook.com") {
    return true;
  } else {
    return false;
  }
}

function searchBing(bingQuery) {
  var searchUrl = "https://www.google.com/search?q=" + bingQuery;
  return searchUrl;
}


function getTitle(inputURL){
    var request = new XMLHttpRequest();
    request.addEventListener("load", function(evt){
        console.log(evt);
    }, false);
    inputURL = inputURL.split("https://l.facebook.com/l.php?u=").pop();
    request.open('GET',  "https://textance.herokuapp.com/title/"+inputURL, false);
    request.send();
    if (request.readyState==4 && request.status==200)
    {
        return request.responseText;
    }
    
}

function loadFileToElement(filename, operator_n)
{
 
  
  
  $(document).ready(function(){
  $.ajax({ type: "GET",   
  url: "https://cors-anywhere.herokuapp.com/"+filename,   
  async: false,
  headers: {
    "x-requested-with": "xhr" 
  }
,
  mode: 'cors',
  cache: 'default',
  success : function(text)
  {
    g[operator_n].innerHTML=text;
  }
});
});
} 

var operator_l = 1;
function createIFrame(operator_k){
    
    var checkTarget = document.getElementById("iframe_" + operator_k);
	loadFileToElement(searchBing(getTitle(linkingPost[operator_k].href)),operator_k);
    var search_result =g[operator_k].getElementsByClassName("LC20lb");
	search_result[operator_k].setAttribute("scope","row");
    if (checkTarget != 'undefined'){
        ifrm[operator_k] = document.createElement("div");
        if (innerPost[operator_k].innerHTML.includes('class="_52c6"')) {
          for (var operator_m = 0; operator_m<5;operator_m++){
           ifrm[operator_k].appendChild(search_result[operator_m]);
          }

        }
	
        ifrm[operator_k].id = "iframe_" + operator_k;
        innerPost[operator_k].getElementsByClassName("_5pcp _5lel _2jyu _232_")[0].appendChild(ifrm[operator_k]);
        //ifrm[operator_k].style.display = "none";
        //ifrm[operator_k].style.height = "auto";
        console.log("iFrame" + operator_k + "created");
    }else{
        console.log("iFrame" + operator_k + "already exists");
    }
}
