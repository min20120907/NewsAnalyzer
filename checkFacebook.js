let checkFacebook = class{
    static areYouInFacebook() {	//areYouInFacebook
        if (window.location.hostname.includes("facebook.com")) {
            return true;
        } else {
            return false;
        }
    }
}