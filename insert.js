
console.log("insert javascript executed");
var btn = document.createElement("BUTTON");   // Create a <button> element
btn.innerHTML = "CLICK ME";                   // Insert text
var post = document.getElementsByClassName("_5pcp _5lel _2jyu _232_");
for (var i = 0; i<post.length;i++){
post[i].append(btn);     // Append button to div
console.log("button"+i+"created");
}

