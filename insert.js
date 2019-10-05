
console.log("insert javascript executed");

window.addEventListener("load", areYouInFacebook);
var innerPost = document.getElementsByClassName("_1dwg _1w_m _q7o");
var linkPost = document.getElementsByClassName("_52c6");
var post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
var btn = [post.length];
var ifrm = [post.length];

for(var a = 0; a < innerPost.length; a++){
    for(var b = 0; b< linkPost.length;b++){
        if(!innerPost[a].contains(linkPost[b])){
            btn[a].style.display = "none";
        }
    }
}

for (var i = 0; i <= post.length - 1; i++) {
    btn[i] = document.createElement("BUTTON")
    btn[i].innerHTML = "CLICK ME";                   // Insert text
    ifrm[i] = document.createElement("iframe");
    ifrm[i].setAttribute("src", "https://www.bing.com/");
	ifrm[i].id = "iframe_" + i;
	btn[i].id = "btn_" + i;
    (function(i){ 
        btn[i].onclick = function() {
        toggleOnOff(i);
        }
    })(i);
    post[i].setAttribute("btn_added", false);
    post[i].setAttribute("ifrm_added", false);
}

for (var i = 0; i <= post.length - 1; i++) {
    post[i].append(btn[i]);     // Append button to div
    console.log("button" + i + "created");
    post[i].append(ifrm[i]);     // Append button to div
    ifrm[i].style.display = "none";
    console.log("iFrame" + i + "created");
    post[i].setAttribute("btn_added", false);
    post[i].setAttribute("ifrm_added", false);
    //console.log("iFrame's id: "+ ifrm[i].id);
}
var num = post.length - 1;
var ticking = false;
var last_known_scroll_position = 0;

window.addEventListener('scroll', function (e) {
    last_known_scroll_position = window.scrollY;

    if (!ticking) {
        window.requestAnimationFrame(function () {
		
            post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
            //setTimeout(function () { console.log("appending..."); }, 5000);
            autoappend();

            ticking = false;
        });
    }
    ticking = true;
    });

function autoappend() {

    for (var j = 0; j <= post.length - 1; j++) {
        if (post[j].getAttribute("btn_added") == null && post[j].getAttribute("ifrm_added") == null) {
            btn[j] = document.createElement("BUTTON");
            btn[j].innerHTML = "CLICK ME";                   // Insert text
            ifrm[j] = document.createElement("iframe");
			ifrm[j].id = "iframe_" + j;
			btn[j].id = "btn_" + j;
            ifrm[j].setAttribute("src", "https://www.bing.com/");
            
            (function(j){ 
                btn[j].onclick = function() {
                toggleOnOff(j);
                }
            })(j);
            post[j].append(btn[j]);     // Append button to div
            console.log("button" + j + "created");
            post[j].append(ifrm[j]);     // Append button to div
            ifrm[j].style.display = "none";
            console.log("iFrame" + j + "created");
            post[j].setAttribute("btn_added", false);
            post[j].setAttribute("ifrm_added", false);
        }
    }

}

function toggleOnOff(operator_j) {

    if (document.getElementById("iframe_"+operator_j).style.display === "block") {
        document.getElementById("iframe_"+operator_j).style.display = "none";
    } else {
        document.getElementById("iframe_"+operator_j).style.display = "block";
    }

}

function areYouInFacebook() {
    if (window.location.hostname == "www.facebook.com"){
        return true;
    } else {
        return false;
    }
}
