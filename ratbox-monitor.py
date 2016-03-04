from __future__ import print_function
import sys, json, argparse, time, socket, errno, select, ssl
import multiprocessing
import modules.connect as connect
import modules.irc as irchandlers


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

def fixlines(sockbuff):
    st = sockbuff.decode('utf-8')
    clean = st[0:st.rfind('\n')+1]
    remainder = bytes(st[st.rfind('\n')+1:], 'utf-8')
    return clean, remainder

def cleanup(sock, q):
    sock.close()
    print("dying...")
    q.put(None)
    sys.exit(0)

# empty the sendq onto the socket when full, checking every 1/100000 second for work
def sendq_worker( sk, sq, ):
    while True:
        if sq.empty():
            #sleep so as to not race during idle
            time.sleep(1/100000)
            continue
        if sk and not sq.empty():
            amsg = sq.get()
            if amsg is None or amsg == "died":
                return
            print("sent: %s" % amsg, file=sys.stderr)
            sk.send(amsg)
    return

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

    s = connect.do_connect(conf['IRCSERVER'], int(conf['IRCPORT']), True)

    inputs = [ s ]
    #manager = multiprocessing.Manager()
    send_q = multiprocessing.Queue(5000)

    if not s:
        sys.exit(-1)

    # we're offically connected so spin up handlers and register
    irchandlers.is_connected = True
    irchandlers.init(send_q, conf, debug_mode=True )

    irchandlers.irc_register(conf['IRCNICK'],conf['IRCUSER'], '0','0',conf['IRCNAME'])

    #kick off sendq helper
    sqchild = multiprocessing.Process( target=sendq_worker, args=(s,send_q,))
    sqchild.start()


    rawbuf = bytes()
    while irchandlers.is_connected:

        try:
            readable, writable, excepts = select.select( inputs, [], [] )
            if s in readable:
                if len(rawbuf) > 0:
                    rawbuf += s.recv(1024)
                else:
                    rawbuf = s.recv(1024)

                if type(s) == ssl.SSLSocket:
                    dataleft = s.pending()
                    while dataleft:
                        rawbuf += s.recv(dataleft)
                        dataleft = s.pending()

            else:
                break
        except OSError:
            break

        except socket.error as e:
            err = e.args[0]
            if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                raise
            continue

        except ssl.SSLError as e:
            if e.errno != ssl.SSL_ERROR_WANT_READ:
                raise
            continue

        if rawbuf:
            # fix issues with newline versus socket recv() buffer
            cleanlines, left = fixlines(rawbuf)
            splitbuf = cleanlines.split('\n')

            for i in range( len(splitbuf) ):
                splitbuf[i] = splitbuf[i].strip('\r')
                irchandlers.irc_dispatch(splitbuf[i])

            # let recv() append to the remainder of the last socket buffer
            rawbuf = left

    cleanup(s, send_q)
    sqchild.join_thread()
    sqchild.join()
    sys.exit(0)


