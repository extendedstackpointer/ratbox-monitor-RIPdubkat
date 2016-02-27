import sys, json, argparse, time, socket, errno
import multiprocessing
import modules.connect as connect
import modules.irc as irchandlers

# constants
message_type = ['SERVER_NOTICE', 'NUMERIC', 'PRIVMSG_NOTICE']

def getjson(fpath):
    try:
        fh = open(fpath, "r")
    except:
        print("Failed to open JSON file for parsing at: %s!\nCheck path and permissions.\nBailing out!" % fpath, file=sys.stderr)
        sys.exit(-1)

    try:
        ret = json.loads(fh.read())
    except:
        print("JSON parsing error in file at: %s\nBailing out!" % fpath, file=sys.stderr)
        fh.close()
        sys.exit(-1)

    fh.close()
    return ret

def send_now(sk, msg):
    if msg is None:
        return
    print("sending: %s" % msg, file=sys.stderr)
    sk.send(msg)
    return

def slow_dumpq(sk, sq):
    while not sq.empty():
        amsg = sq.get()
        if amsg is None or not amsg:
            break
        time.sleep(1)
        send_now(sk, amsg)
        del amsg
    return

def fast_dumpq(sk, sq):
    while not sq.empty():
        amsg = sq.get()

        if amsg is None:
            break

        # gracefully handle exit
        if amsg == "died.":
            del sq
            sk.close()
            return
        send_now(sk, amsg)
        del amsg
    return

def fixlines(sockbuff):
    str = sockbuff.decode('utf-8')
    clean = str[0:str.rfind('\n')+1]
    remainder = bytes(str[str.rfind('\n')+1:], 'utf-8')
    return clean, remainder


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ratbox-monitor is a re-write intended to replace Drone Connection Monitor a.ka. dronemon.pl by powuh")
    parser.add_argument("-c", "--conf",help="specify a config file", dest="config_file", required=True)
    parser.add_argument("-t", "--thread-count", help="The number of worker threads to spawn", dest="worker_count", metavar='N', default=1, type=int, required=True)
    parser.add_argument("-b", "--benchmark",help="test performance of regex matching abased on benchmark.json data and exit", dest="benchmark_file", required=False)
    parser.add_argument("-v", "--version",help="show version and exit", required=False)
    args = parser.parse_args()

# deal with config and dat files
# --------------------------------------------------------------------------------


    # load persistent data from disk
    conf = getjson(args.config_file)

    # make sure user isn't braindead
    if "REMOVE_THIS_LINE_FROM_DRONEMON.CONF" in conf:
        print("Please read the README and edit the entire config file properly.\nExiting...", file=sys.stderr)
        sys.exit(-1)

    users = getjson(conf['USERFILE'])

# main loop
# --------------------------------------------------------------------------------

    #s = connect.do_connect('69.31.127.6', 9999, True )
    s = connect.do_connect('198.47.99.99', 6667, False)
    #manager = multiprocessing.Manager()
    send_q = multiprocessing.Queue(5000)

    if not s:
        sys.exit(-1)


    # we're offically connected so spin up handlers and register
    irchandlers.is_connected = True
    irchandlers.init(send_q)

    # fix this to derive values from config file
    irchandlers.irc_register('justatest','esp', '0','0','derp')

    rawbuf = bytes()
    while True:

        if not send_q.empty():
            # send_q.put(None)
            fast_dumpq(s, send_q)
            if not s:
                del send_q
                break

        try:
            if len(rawbuf) > 0:
                rawbuf += s.recv(1280)
            else:
                rawbuf = s.recv(1280)
        except socket.error as e:
            err = e.args[0]
            if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                continue
            else:
                print("Hes dead jim.", file=sys.stderr)
                irchandlers.is_connected=False
                sys.exit(0)

        # fix issues with newline versus socket recv() buffer
        cleanlines, left = fixlines(rawbuf)

        splitbuf = cleanlines.split('\n')
        for i in range( len(splitbuf) ):
            splitbuf[i] = splitbuf[i].strip('\r')
            irchandlers.irc_dispatch(send_q, splitbuf[i])

        # let recv() append to the remainder of the socket buffer
        rawbuf = left

    sys.exit(0)


