function areYouInFacebook() {
    if (window.location.hostname == "www.facebook.com"){
        return true;
    } else {
        return false;
    }
}

window.addEventListener("load", areYouInFacebook);
