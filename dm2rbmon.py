import sys
import json


def json_pstr(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,indent=4, separators=(',', ': '))


def regex2json(regexpfile, regexpjson):
    reg = []
    fh = open(regexpfile, "r")

    for line in fh:
        line = line.rstrip('\n')
        if line[0] == '#':
            continue
        tmp = line.split(maxsplit=6)
        if tmp[0] == '' or len(tmp) != 7:
            continue
        tmp2 = dict()
        tmp2['expire'] = int(tmp[0])
        tmp2['added'] = tmp[1]
        tmp2['modded'] = tmp[2]
        tmp2['action'] = tmp[3]
        tmp2['action_time'] = tmp[4]
        tmp2['regexp'] = tmp[5]
        tmp2['reason'] = tmp[6]
        reg.append(tmp2)
        del tmp2
    fh.close()

    fh = open(regexpjson, "w")
    fh.write(json_pstr(reg))
    fh.close()
    return


def nregex2json():
    return


def qurve2json():
    return

def stats2json():
    return

def user2json():
    return

def version2json():
    return

if __name__ == "__main__":
    if len(sys.argv) !=4:
        sys.exit(-1) # fail
    if sys.argv[1] == "-r":
        regex2json(sys.argv[2], sys.argv[3])
    elif sys.argv[1] =="-n":
        nregex2json()
    elif sys.argv[1] =="-q":
        qurve2json()
    elif sys.argv[1] =="-s":
        stats2json()
    elif sys.argv[1] =="-u":
        user2json()
    elif sys.argv[1] =="-v":
        version2json()