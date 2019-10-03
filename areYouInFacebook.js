function areYouInFacebook() {
    if (window.location.hostname == "www.facebook.com"){
        console.log("yes");
    } else {
        console.log("no");
    }
}

window.addEventListener("load", areYouInFacebook);
