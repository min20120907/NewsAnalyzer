console.log("insert javascript executed");

window.addEventListener("load", areYouInFacebook);
var innerPost = document.getElementsByClassName("_1dwg _1w_m _q7o");
var linkPost = document.getElementsByClassName("_52c6");
var post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
var btn = [innerPost.length];
var ifrm = [innerPost.length];
var linkingPost = [innerPost.length];

for (var i = 0; i <= post.length - 1; i++) {
  btn[i] = document.createElement("BUTTON");
  btn[i].innerHTML = "CLICK ME"; // Insert text
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
    linkingPost[i]=innerPost[i].getElementsByClassName("_52c6")[0];
  }
  innerPost[i].getElementsByClassName("_5pcp _5lel _2jyu _232_")[0].append(btn[i]); // Append button to div
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
      //setTimeout(function () { console.log("appending..."); }, 5000);
      autoappend();
      ticking = false;
    });
  }
  ticking = true;
});

function autoappend() {

  for (var j = 0; j <= innerPost.length - 1; j++) {
    if (
      post[j].getAttribute("btn_added") == null
    ) {
      btn[j] = document.createElement("BUTTON");
      btn[j].innerHTML = "CLICK ME"; // Insert text
      btn[j].id = "btn_" + j;
      if (!innerPost[j].innerHTML.includes('class="_52c6"')) {
        btn[j].style.display = "none";
        linkingPost[j] = null;
      }
      if(innerPost[j].innerHTML.includes('class="_52c6"')){
        linkingPost[j]=innerPost[j].getElementsByClassName("_52c6")[0];
      }
      (function(j) {
        btn[j].onclick = function() {
          createIFrame(j);
          toggleOnOff(j);
        };
      })(j);
      innerPost[j].getElementsByClassName("_5pcp _5lel _2jyu _232_")[0].append(btn[j]); // Append button to div
      console.log("button" + j + "created");
      post[j].setAttribute("btn_added", false);
    }
  }
}

function toggleOnOff(operator_j) {
  if (
    document.getElementById("iframe_" + operator_j).style.display === "block"
  ) {
    document.getElementById("iframe_" + operator_j).style.display = "none";
  } else {
    document.getElementById("iframe_" + operator_j).style.display = "block";
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
  var searchUrl = "https://www.bing.com/search?q=" + bingQuery;
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
var operator_l = 1;
function createIFrame(operator_k){
    var checkTarget = document.getElementById("iframe_" + operator_k);
    if (checkTarget != 'undefined'){
        ifrm[operator_k] = document.createElement("iframe");
        //ifrm[operator_k].setAttribute("src", searchBing(getTitle(linkPost[operator_k].href)));
        if (innerPost[operator_k].innerHTML.includes('class="_52c6"')) {
          ifrm[operator_k].setAttribute("src", searchBing(getTitle(linkingPost[operator_k].href)));
        }
        ifrm[operator_k].id = "iframe_" + operator_k;
        innerPost[operator_k].getElementsByClassName("_5pcp _5lel _2jyu _232_")[0].appendChild(ifrm[operator_k]);
        ifrm[operator_k].style.display = "none";
        console.log("iFrame" + operator_k + "created");
    }else{
        console.log("iFrame" + operator_k + "already exists");
    }
}
