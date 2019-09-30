
console.log("insert javascript executed");
var post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
var btn = [post.length];
var ifrm = [post.length];
for (var i = 0; i <= post.length - 1; i++) {
	btn[i] = document.createElement("BUTTON")
    btn[i].innerHTML = "CLICK ME";                   // Insert text
    ifrm[i] = document.createElement("iframe");
    ifrm[i].setAttribute("src", "http://google.com/");
    btn[i].onclick = function(){toggleOnOff()}; 
}

for (var i = 0; i <= post.length - 1; i++){
	post[i].append(btn[i]);     // Append button to div
    console.log("button"+i+"created");
    post[i].append(ifrm[i]);     // Append button to div
    ifrm[i].style.display = "none";
    console.log("iFrame"+i+"created");
}
var num = post.length - 1;
var ticking = false;
window.addEventListener('scroll', function(e) {
    last_known_scroll_position = window.scrollY;
    if (!ticking) {
      window.requestAnimationFrame(function() {
        setTimeout(function(){ console.log("appending..."); }, 500);
        autoappend();
        
        ticking = false;
      });
    }
    ticking = true;
  });

function autoappend(){
    
for (var j = 0; j <= post.length - 1; j++) {
	btn[j] = document.createElement("BUTTON")
    btn[j].innerHTML = "CLICK ME";                   // Insert text
    ifrm[j] = document.createElement("iframe");
    ifrm[j].setAttribute("src", "http://google.com/");
    btn[j].onclick = function(){toggleOnOff()}; 
}
for (var i = 0; i <= post.length - 1; i++){
	post[i].append(btn[i]);     // Append button to div
    console.log("button"+i+"created");
    post[i].append(ifrm[i]);     // Append button to div
    ifrm[i].style.display = "none";
    console.log("iFrame"+i+"created");
}
}

function toggleOnOff() {
    for(var j = 0; j<ifrm.length;j++){
    if (ifrm[j].style.djsplay === "block") {
        ifrm[j].style.djsplay = "none";
    } else {
        ifrm[j].style.display = "block";
    }
  }
}
