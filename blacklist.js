let blacklist = class {
    static isBlackList(URL) {
        /* IE only */
        let fso = ActiveXObject(Scripting.FileSystemObject);
        let whiteListData = fso.createtextfile("blacklist.txt",1,false);
        while(!whiteListData.AtEndOfStream) {
            if(URL == whiteListData.ReadLine()) {
                return true;
            }
        }
        return false;
    }
}
