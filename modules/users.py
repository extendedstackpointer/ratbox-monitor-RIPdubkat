import sys,json


def getusers(usrpath):
    try:
        fh = open(usrpath, "r")
    except:
        print("Failed to open user file for parsing at: %s!\nCheck path and permissions.\nBailing out!" % usrpath, file=sys.stderr)
        sys.exit(-1)

    try:
        ret = json.loads(fh.read())
    except:
        print("JSON parsing error in file at: %s\nBailing out!" % conpath, file=sys.stderr)
        fh.close()
        sys.exit(-1)
    fh.close()
    return ret