console.log("insert javascript executed");
var post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
var btn = [post.length];
var controlFrame = document.getElementById("googleFrame");
controlFrame.style.display = "none";
for (var i = 0; i <= post.length - 1; i++) {
	btn[i] = document.createElement("BUTTON")
    btn[i].innerHTML = "CLICK ME";                   // Insert text
    btn[i].onclick = x(); 
}

for (var i = 0; i <= post.length - 1; i++){
	post[i].append(btn[i]);     // Append button to div
    console.log("button"+i+"created");
}
var num = post.length - 1;

post.length.addEventListener("change", autoappend);

function autoappend(){
	for (var j = 0; j <= post.length - 1; j++){
		post[i].append(btn[j]);     // Append button to div
		console.log("button"+j+"created");
	}
	j = post.length - 1;
}

function x(){
    for (var i = 0; i <= post.length - 1; i++) {
    var ifrm = document.createElement("iframe");
    ifrm.setAttribute("src", "http://google.com/");
    }
}

function toggleOnOff() {
    if (controlFrame.style.display === "block") {
      controlFrame.style.display = "none";
    } else {
      controlFrame.style.display = "block";
    }
  }
