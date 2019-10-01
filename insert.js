
console.log("insert javascript executed");
var post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
var btn = [post.length];
var ifrm = [post.length];
for (var i = 0; i <= post.length - 1; i++) {
    btn[i] = document.createElement("BUTTON")
    btn[i].innerHTML = "CLICK ME";                   // Insert text
    ifrm[i] = document.createElement("iframe");
    ifrm[i].setAttribute("src", "http://google.com/");
    btn[i].onclick = function () { toggleOnOff() };
}

for (var i = 0; i <= post.length - 1; i++) {
    post[i].append(btn[i]);     // Append button to div
    console.log("button" + i + "created");
    post[i].append(ifrm[i]);     // Append button to div
    ifrm[i].style.display = "none";
    console.log("iFrame" + i + "created");
    //console.log("iFrame's id: "+ ifrm[i].id);
}
var num = post.length - 1;
var ticking = false;
var last_known_scroll_position = 0;

window.addEventListener('scroll', function (e) {
    last_known_scroll_position = window.scrollY;
    if (!ticking) {
        window.requestAnimationFrame(function () {
            setTimeout(function () { console.log("appending..."); }, 5000);
            autoappend();

            ticking = false;
        });
    }
    ticking = true;
});

function autoappend() {

    for (var j = 0; j <= post.length - 1; j++) {
        if (post[j].getAttribute("btn_added") !=true && post[j].getAttribute("ifrm_added") != true) {
            btn[j] = document.createElement("BUTTON");
            btn[j].innerHTML = "CLICK ME";                   // Insert text
            ifrm[j] = document.createElement("iframe");
            ifrm[j].setAttribute("src", "http://google.com/");
            btn[j].onclick = function () { toggleOnOff(j) };
            post[j].setAttribute("btn_added", true);
            post[j].setAttribute("ifrm_added", true);
        }
    }
    for (var i = 0; i <= post.length - 1; i++) {
        if (post[i].getAttribute("btn_added") == false && post[i].getAttribute("ifrm_added") == false) {
            post[i].append(btn[i]);     // Append button to div
            console.log("button" + i + "created");
            post[i].append(ifrm[i]);     // Append button to div
            ifrm[i].style.display = "none";
            console.log("iFrame" + i + "created");
        }
    }

}

function toggleOnOff(j) {
    
        if (ifrm[j].style.djsplay === "block") {
            ifrm[j].style.djsplay = "none";
        } else {
            ifrm[j].style.display = "block";
        }
    
}
