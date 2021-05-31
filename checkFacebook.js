let checkFacebook = class{
    static areYouInFacebook() {	//areYouInFacebook
        if (window.location.hostname == "www.facebook.com") {
            return true;
        } else {
            return false;
        }
    }
}