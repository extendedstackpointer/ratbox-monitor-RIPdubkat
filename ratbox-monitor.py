from __future__ import print_function
import sys, json, argparse, time, socket, select, ssl
import multiprocessing
from modules.connect import do_connect
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

def cleanup():
    global state
    global senderproc
    # global workers
    print("dying...")

    # poison pill the worker processes and join them
    for c in range( state['worker_count'] + 1 ):
        state['queue'].put(None)
    # for i in range( state['worker_count'] ):
    #     workers[i].join()

    state['socket']['socket'].close()
    state['queue'].close()
    state['queue'].join_thread()

    senderproc.join()
    return

def init_state():
    global conf
    global send_q
    global state
    stat= {
        'bot' : {
            'registered' : False,
            'opered' : False,
            'selfquit' : False,
            'debug_mode' : True,
            'nick' : conf['IRCNICK'],
            'user' : conf['IRCUSER'],
            'gecos' : conf['IRCNAME'],
        },
        'socket' : {
            'socket' : 0,
            'connected' : False,
            'lag' : 0,
            'lastping': -1,
        },
        'queue' : send_q,
        'worker_count' : 0
    }

    # if conf['USE_SSL']:
    #     stat['socket']['socket'] = ssl.SSLSocket
    # else:
    #     stat['socket']['socket'] = socket.socket
    state = stat
    return

def writer( st ):
    while True:
        if st['bot']['selfquit']:
            return

        # check server connectivity and latency every 10 seconds
        t = time.time()
        if ((state['socket']['lastping']) == -1 or (t - state['socket']['lastping']) >= 300) and state['socket']['connected']:
            try:
                state['socket']['socket'].send(bytes(str.format("PING :%d\r\n" % t), 'utf-8'))
                state['socket']['lastping'] = t
            except:
                state['socket']['connected'] = False

        # sleep so as to not race when we don't have work to do
        if st['queue'].empty() and not st['bot']['selfquit']:
            time.sleep(1/100000)
            continue

        # # Items in queue.  check for poison pill
        if not st['queue'].empty():
            amsg = st['queue'].get()
            if amsg is None:
                #print("got poison pill.  Exiting worker...", file=sys.stderr)
                return

        # No poison pill.  We have work to do so do it!
        if st['socket']['connected']:
            if amsg == "died":
                return
            else:
                try:
                    st['socket']['socket'].send(amsg)
                except:
                    st['socket']['connected'] = False

                if st['bot']['debug_mode']:
                    print("<- %s" % amsg, file=sys.stderr)
        else:
            print("Not connected!", file=sys.stderr)
            continue
    return

def reconnect( retry_time=10 ):
    global state
    global conf
    global senderproc
    global send_q

    print("He's dead jim.", file=sys.stderr)

    # poison worker threads and tear them down
    # wc = state['worker_count']
    # for n in range( wc ):
    #     state['queue'].put(None)
    # for n in range( wc ):
    #     workers[n].join()

    state['queue'].put(None)
    senderproc.join()

    # empty the send_q:
    while not state['queue'].empty():
        a = state['queue'].get()
        del a

    # reset states
    state['socket']['connected'] = False
    state['socket']['lag'] = 0
    state['socket']['lastping'] = 0
    state['bot']['registered'] = False
    state['bot']['opered'] = False

    # attempt rebuild the socket until success
    while True:

        state['socket']['socket'].close()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # if we used SSL we need to rebuild SSL context as well
        if conf['USE_SSL']:
            sock = ssl.wrap_socket(s)
        else:
            sock = s
        state['socket']['socket'] = sock

        if state['bot']['debug_mode']:
            print("Retrying...", file=sys.stderr)

        try:
            state['socket']['socket'].connect( (conf['IRCSERVER'], int(conf['IRCPORT'])) )
        except ssl.SSLError:
            time.sleep(retry_time)
            continue
        except socket.error:
            time.sleep(retry_time)
            continue
        except ValueError:
            time.sleep(retry_time)
            continue
        # no errors from connect() if we get here so break the loop
        break

    state['socket']['socket'].setblocking(False)
    state['socket']['connected'] = True
    print("We're back baby!", file=sys.stderr)

    # re-initialize worker threads with new state
    # for n in range( wc ):
    #     del workers[n]
    # for n in range( wc ):
    #     workers.append(multiprocessing.Process( target=helper, args=(state,)))
    # for n in range( wc ):
    #     workers[n].start()

    senderproc = multiprocessing.Process(target=writer, args=(state,))
    senderproc.start()

    # re-register
    irchandlers.init(conf,state,state['bot']['debug_mode'])
    irchandlers.irc_register(conf['IRCNICK'],conf['IRCUSER'], '0','0',conf['IRCNAME'])

    return

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ratbox-monitor is a re-write intended to replace Drone Connection Monitor a.ka. dronemon.pl by powuh")
    parser.add_argument("-c", "--conf",help="specify a config file", dest="config_file", required=True)
    parser.add_argument("-t", "--thread-count", help="The number of helper threads to spawn", dest="worker_count", metavar='N', default=1, type=int, required=False)
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

# setup the socket, state machine, queues, and irc connection
# --------------------------------------------------------------------------------

    send_q = multiprocessing.Queue()

    # multiprocessing friendly state machine proxy object:
    manager = multiprocessing.Manager()
    state = manager.dict()
    init_state()

    state['socket']['socket'] = do_connect(conf['IRCSERVER'], int(conf['IRCPORT']), conf['USE_SSL'])

    if not state['socket']['socket']:
        reconnect(retry_time=10 )

    state['socket']['connected'] = True


    # we're offically connected so spin up handlers and register
    irchandlers.init( conf, state )

    irchandlers.irc_register(conf['IRCNICK'],conf['IRCUSER'], '0','0',conf['IRCNAME'])

    # set statically for now:
    state['bot']['debug_mode'] = True

# child processes
# --------------------------------------------------------------------------------
    # async socket writer.  ONLY RUN ONE OF THESE AT A TIME OR SSL WILL EXPLODE
    senderproc = multiprocessing.Process(target=writer, args=(state,))
    senderproc.start()

    #kick off helper(s)
    # if not args.worker_count:
    #     # we always have an async socket writer but always want a free CPU core so -2
    #     state['worker_count'] = multiprocessing.cpu_count() - 2
    # state['worker_count'] = args.worker_count
    # workers = list()
    # for i in range( state['worker_count'] ):
    #     workers.append( multiprocessing.Process( target=helper, args=(state,)) )
    # for i in range( len(workers) ):
    #     workers[i].start()



# main loop
# --------------------------------------------------------------------------------

    rawbuf = bytes()
    while True:

        # bail out on .die
        if state['bot']['selfquit']:
            break

        if not state['socket']['connected']:
            reconnect(retry_time=2)

        try:
            readable, writable, excepts = select.select( [ state['socket']['socket'] ], [], [] )
        except ValueError:
            reconnect(retry_time=2)

        if state['socket']['socket'] in readable:
            if len(rawbuf) > 0:
                rawbuf += state['socket']['socket'] .recv(1024)
            else:
                rawbuf = state['socket']['socket'] .recv(1024)

            if type(state['socket']['socket']) == ssl.SSLSocket:
                dataleft = state['socket']['socket'].pending()
                while dataleft:
                    rawbuf += state['socket']['socket'].recv(dataleft)
                    dataleft = state['socket']['socket'].pending()


        if rawbuf:
            # fix issues with newline versus socket recv() buffer
            cleanlines, left = fixlines(rawbuf)
            splitbuf = cleanlines.split('\n')

            for i in range( len(splitbuf) ):
                splitbuf[i] = splitbuf[i].strip('\r')
                irchandlers.irc_dispatch(splitbuf[i])

            # let recv() append to the remainder of the last socket buffer
            rawbuf = left


    cleanup()
    sys.exit(0)


