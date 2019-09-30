console.log("insert javascript executed");
var post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
var btn = [post.length];
for (var i = 0; i <= post.length - 1; i++) {
	btn[i] = document.createElement("BUTTON")
	btn[i].innerHTML = "CLICK ME";                   // Insert text
}

for (var i = 0; i <= post.length; i++){
	post[i].append(btn[i]);     // Append button to div
	console.log("button"+i+"created");
}

