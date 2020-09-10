
console.log("insert javascript executed");
//Detecting the page if it is facebook.
window.addEventListener("load", areYouInFacebook);
for (var i = 0; i < 5; i++) {
  var result = document.createElement("div");
  result.id = "results-" + i;
}

//Elements proclaiming.
//get posts by using style classes
posts = document.getElementsByClassName("rq0escxv l9j0dhe7 du4w35lb hybvsw6c ue3kfks5 pw54ja7n uo3d90p7 l82x9zwi ni8dbmo4 stjgntxs k4urcfbm sbcfpzgs");
innerPost = [];
//filter it with check whether has content
a = 0;
for (var r = 0; r < posts.length; r++) {
  if (posts[r].innerHTML.includes("oi732d6d ik7dh3pa d2edcug0 hpfvmrgz qv66sw1b c1et5uql a8c37x1j hop8lmos enqfppq2 e9vueds3 j5wam9gi knj5qynh m9osqain hzawbc8m")) {
    innerPost[a] = posts[r]; //if it is a post add it
    a++;
  }
}

link_posts = document.getElementsByClassName("oajrlxb2 g5ia77u1 qu0x051f esr5mh6w e9989ue4 r7d6kgcz rq0escxv nhd2j8a9 a8c37x1j p7hjln8o kvgmc6g5 cxmmr5t8 oygrvhab hcukyx3x jb3vyjys rz4wbd8a qt6c0cv9 a8nywdso i1ao9s8h esuyzwwr f1sip0of lzcic4wl gmql0nx0 p8dawk7l");
linkPost = [];
a = 0;
for (var i = 0; i < link_posts.length; i++) {
  //if it is link, then add it
  if (link_posts[i].tagName == "A") {
    linkPost[a] = link_posts[i];
    a++;
  }
}

var post = [];
for (var i = 0; i < innerPost.length; i++) {
  post[i] = innerPost[i].getElementsByClassName("oi732d6d ik7dh3pa d2edcug0 hpfvmrgz qv66sw1b c1et5uql a8c37x1j hop8lmos enqfppq2 e9vueds3 j5wam9gi knj5qynh m9osqain hzawbc8m")[0];
}

var btn = [innerPost.length];
var ifrm = [innerPost.length];
var g = [innerPost.length];
var table = [innerPost.length];
var tbody = [innerPost.length];
//var lpost = document.getElementsByClassName("_6m3 _--6");
//var operator_s = 0;
var entrSites = [
  "youthwant.com",
  "openfind.com",
  "timliao.com",
  "taconet.com",
  "gigigaga.com",
  "so-net.net",
  "don-net.com",
  "hongkong.com",
  "asiadog.com",
  "gotoya.com",
  "t2t.com",
  "moninet.com",
  "myweb.hinet.net",
  "udo.idv",
  "wutun.idv",
  "centurys.com.tw",
  "funf.tw",
  "portal.tw",
  "pig.tw",
  "taiwanurl.com",
  "263.net",
  "qq.com",
  "sohu.com",
  "china.com",
  "tom.com",
  "netease.com",
  "backchina.com",
  "gjj.cc",
  "qoos.com",
  "qknet.net",
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
  "likea.ezvivi.com",
  "facebook.com",
  "kknews.cc",
  "google.com",
  "yahoo.com",
  "hinet.net",
  "msn.com",
  "pchome.com",
  "yam.com",
  "sina.com",
  "cnet.com",
  "seed.net.",
  "url.com",
  "kingnet.com",
  "funp.com",
  "youthwant.com",
  "yahoo.com",
  "cn.yahoo.com",
  "openfind.com",
  "timliao.com",
  "taconet.com",
  "gigigaga.com",
  "so-net.net",
  "don-net.com",
  "hongkong.com",
  "asiadog.com",
  "gotoya.com",
  "t2t.com",
  "moninet.com",
  "myweb.hinet.nethome1kiroro",
  "udo.idv",
  "wutun.idv",
  "centurys.com.tw",
  "funf",
  "portal.tw",
  "pig.tw",
  "taiwanurl.com",
  "263.net",
  "qq.com",
  "sohu.com",
  "china.com",
  "tom.com",
  "china.com",
  "netease.com",
  "backchina.com",
  "gjj.cc",
  "qoos.com",
  "qknet.net"
];

/*for (var i = 0; i < entrSites.length; i++) {
  query_args = query_args.concat(" -site:" + entrSites[i]);
}*/
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
  if (!innerPost[i].innerHTML.includes('class="oajrlxb2 g5ia77u1 qu0x051f esr5mh6w e9989ue4 r7d6kgcz rq0escxv nhd2j8a9 a8c37x1j p7hjln8o kvgmc6g5 cxmmr5t8 oygrvhab hcukyx3x jb3vyjys rz4wbd8a qt6c0cv9 a8nywdso i1ao9s8h esuyzwwr f1sip0of lzcic4wl gmql0nx0 p8dawk7l"')) {
    btn[i].style.display = "none";
  }
  if (innerPost[i].innerHTML.includes('class="oajrlxb2 g5ia77u1 qu0x051f esr5mh6w e9989ue4 r7d6kgcz rq0escxv nhd2j8a9 a8c37x1j p7hjln8o kvgmc6g5 cxmmr5t8 oygrvhab hcukyx3x jb3vyjys rz4wbd8a qt6c0cv9 a8nywdso i1ao9s8h esuyzwwr f1sip0of lzcic4wl gmql0nx0 p8dawk7l"')) {
    g[i] = document.createElement('div');
    g[i].id = "website_" + i;
  }
  innerPost[i].getElementsByClassName("oi732d6d ik7dh3pa d2edcug0 hpfvmrgz qv66sw1b c1et5uql a8c37x1j hop8lmos enqfppq2 e9vueds3 j5wam9gi knj5qynh m9osqain hzawbc8m")[0].appendChild(btn[i]); // appendChild button to div
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
      //get posts by using style classes
      posts = document.getElementsByClassName("rq0escxv l9j0dhe7 du4w35lb hybvsw6c ue3kfks5 pw54ja7n uo3d90p7 l82x9zwi ni8dbmo4 stjgntxs k4urcfbm sbcfpzgs");
      innerPost = [];
      //filter it with check whether has content
      a = 0;
      for (var r = 0; r < posts.length; r++) {
        if (posts[r].innerHTML.includes("oi732d6d ik7dh3pa d2edcug0 hpfvmrgz qv66sw1b c1et5uql a8c37x1j hop8lmos enqfppq2 e9vueds3 j5wam9gi knj5qynh m9osqain hzawbc8m")) {
          innerPost[a] = posts[r]; //if it is a post add it
          a++;
        }
      }

      link_posts = document.getElementsByClassName("oajrlxb2 g5ia77u1 qu0x051f esr5mh6w e9989ue4 r7d6kgcz rq0escxv nhd2j8a9 a8c37x1j p7hjln8o kvgmc6g5 cxmmr5t8 oygrvhab hcukyx3x jb3vyjys rz4wbd8a qt6c0cv9 a8nywdso i1ao9s8h esuyzwwr f1sip0of lzcic4wl gmql0nx0 p8dawk7l");
      linkPost = [];
      a = 0;
      for (var i = 0; i < link_posts.length; i++) {
        //if it is link, then add it
        if (link_posts[i].tagName == "A") {
          linkPost[a] = link_posts[i];
          a++;
        }
      }
      var posts = [];
      for (var i = 0; i < innerPost.length; i++) {
        posts[i] = innerPost[i].getElementsByClassName("oi732d6d ik7dh3pa d2edcug0 hpfvmrgz qv66sw1b c1et5uql a8c37x1j hop8lmos enqfppq2 e9vueds3 j5wam9gi knj5qynh m9osqain hzawbc8m")[0];
      }
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
      posts[j].getAttribute("btn_added") == null
    ) {
      btn[j] = document.createElement("BUTTON");

      btn[j].innerHTML = "more"; // Insert text
      btn[j].setAttribute("class", "btn btn-warning");

      btn[j].id = "btn_" + j;
      if (!innerPost[j].innerHTML.includes('class="oajrlxb2 g5ia77u1 qu0x051f esr5mh6w e9989ue4 r7d6kgcz rq0escxv nhd2j8a9 a8c37x1j p7hjln8o kvgmc6g5 cxmmr5t8 oygrvhab hcukyx3x jb3vyjys rz4wbd8a qt6c0cv9 a8nywdso i1ao9s8h esuyzwwr f1sip0of lzcic4wl gmql0nx0 p8dawk7l"')) {
        btn[j].style.display = "none";
      }
      if (innerPost[j].innerHTML.includes('class="oajrlxb2 g5ia77u1 qu0x051f esr5mh6w e9989ue4 r7d6kgcz rq0escxv nhd2j8a9 a8c37x1j p7hjln8o kvgmc6g5 cxmmr5t8 oygrvhab hcukyx3x jb3vyjys rz4wbd8a qt6c0cv9 a8nywdso i1ao9s8h esuyzwwr f1sip0of lzcic4wl gmql0nx0 p8dawk7l"')) {
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
      innerPost[j].getElementsByClassName("oi732d6d ik7dh3pa d2edcug0 hpfvmrgz qv66sw1b c1et5uql a8c37x1j hop8lmos enqfppq2 e9vueds3 j5wam9gi knj5qynh m9osqain hzawbc8m")[0].appendChild(btn[j]); // appendChild button to div
      console.log("button" + j + "created");
      posts[j].setAttribute("btn_added", false);
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
  if (!googleQuery.includes("中天新聞")) {
    var searchUrl = "https://www.googleapis.com/customsearch/v1?key=AIzaSyBOXrA4oFgl1SNyxm9sA_vTzaAVYorQDug&cx=9f8b720f1b3abf296&q=" + googleQuery.substring(0, 17);
  } else {
    var searchUrl = "https://www.googleapis.com/customsearch/v1?key=AIzaSyBOXrA4oFgl1SNyxm9sA_vTzaAVYorQDug&cx=9f8b720f1b3abf296&q=" + googleQuery.substring(googleQuery.length - 18, googleQuery.length);
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
      async: true,
      headers: {
        "x-requested-with": "xhr"
      },
      mode: 'json',
      cache: 'default',
      success: function (text) {
        g[operator_n] = text;
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
  loadFileToElement(searchGoogle(innerPost[operator_k].getElementsByClassName("qzhwtbm6 knvmm38d")[3].innerText), operator_k);
  var search_result = [];
  for (var i = 0; i < 10; i++) {
    var result = document.createElement("div");
    result.id = "results-" + i;
    var item = g[operator_k].items[i];
    // in production code, item.htmlTitle should have the HTML entities escaped.

    var link = document.createElement('a');
    link.href = item.link;
    link.innerText = item.title;
    result.appendChild(link);
    search_result[i] = result;
  }

  //var icos = [document.createElement("img"), document.createElement("img"), document.createElement("img"), document.createElement("img"), document.createElement("img")]; //old icon functions
  var icos = [];
  for (var i = 0; i < 10; i++) {
    icos.push(document.createElement("img"));
  }
  var getLocation = function (href) {
    var l = document.createElement("a");
    l.href = href;
    return l;
  };


  for (var operator_r = 0; operator_r < 10; operator_r++) {	//set the icons on the search_results


    var string1 = "http://i.olsh.me//icon?url=" + getLocation(search_result[operator_r].getElementsByTagName("A")[0].href).hostname + "&size=80..120..200";
    icos[operator_r].src = string1;


    icos[operator_r].width = 24;	//set width as 24
    icos[operator_r].height = 24;	//set height as 24
    icos[operator_r].style.position = "relative";
  }


  var tr_ele = [];
  for (var i = 0; i < 10; i++)
    tr_ele[i] = document.createElement("tr");

  if (checkTarget == null) {
    //if (search_result[operator_k] != null) {
    ifrm[operator_k] = document.createElement("div");
    for (var operator_m = 0; operator_m < search_result.length; operator_m++) {
      search_result[operator_m].insertBefore(icos[operator_m], search_result[operator_m].firstChild);
      //tr_ele[operator_m].appendChild(icos[operator_m]);
      tr_ele[operator_m].appendChild(search_result[operator_m]);
      tbody[operator_k].appendChild(tr_ele[operator_m]);
      table[operator_k].appendChild(tbody[operator_k]);
    }
    ifrm[operator_k].appendChild(table[operator_k]);
    ifrm[operator_k].id = "iframe_" + operator_k;
    innerPost[operator_k].getElementsByClassName("oi732d6d ik7dh3pa d2edcug0 hpfvmrgz qv66sw1b c1et5uql a8c37x1j hop8lmos enqfppq2 e9vueds3 j5wam9gi knj5qynh m9osqain hzawbc8m")[0].appendChild(ifrm[operator_k]);
    ifrm[operator_k].setAttribute("style", "display: block");
    console.log("iFrame" + operator_k + "created");
    //}
  } else {
    console.log("iFrame" + operator_k + "already exists");
    toggleOnOff(operator_k);
  }
  return { search_result: search_result, icos: icos };

}
