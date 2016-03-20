# this module consists of irc_dispatch(), cmd_dispatch(), and a series of handler functions stored in lists
# additional modules can be added by adhering to the procedure template and adding them to the list
# ideally this should actually be a class

# handler function structure
# this maps each type of message with a list of handler functions for that message type
# when it occurs in a specific position within the server message.
#
# dispatch should be able to iterate over these.
# example structure:
# hander_dict{
#     0 : {
#         'PING' : [
#             handler1(),
#             handler2(),
#             handler3(),
#             ...
#         ]
#     }
#     1 : {
#         'PRIVMSG' : [
#             hander1(),
#             handler2(),
#             handler3(),
#             ...
#         ]
#     }
# }

from __future__ import print_function
import sys, time, re, multiprocessing

# handlers
handler_dict = dict()
cmd_dict = dict()

# client hash
mgr = multiprocessing.Manager()
client_dict = mgr.dict()

# application and network states
st = False

# parsed config file
conf = None

# utility functions
# --------------------------------------------------------------------------------
def is_int(val):
    try:
        v = int(val)
    except ValueError:
        return False
    return True

# put raw IRC proto into send queue for worker thread to push onto socket
def write_sock(strfmsg):
    global st
    msg = bytes( strfmsg, 'utf-8')
    st['queue'].put( msg )
    return


# send a CTCP response
def ctcp_reply(target, cmd):
    write_sock(str.format("PRIVMSG %s :\x01%s\x01\r\n") % (target, cmd) )
    return True



# send a privmsg
def irc_privmsg(target, data):
    write_sock(str.format("PRIVMSG %s :%s\r\n") % (target, data))
    return True

def irc_setumode(mynick, modelist):
    write_sock(
        str.format("MODE %s %s\r\n" % (mynick, modelist) )
    )
    return True

# to register after connecting
def irc_register(nick, username, extra1, extra2, gecos ):
    write_sock(str.format("NICK %s\r\n" % nick))
    write_sock(str.format("USER %s %s %s :%s\r\n" % (username, extra1, extra2, gecos)) )
    return True

# determine sender of privmsg and respond directly
# msgstr should either be #chan or nick!user@host format
def get_sender(senderstr):
    pmsg = senderstr.split()
    if len(pmsg) < 3:
        return
    if pmsg[2][0] == '#':
        return pmsg[2]
    else:
        return pmsg[0][1:pmsg[0].find('!')]
    return False

def strip_colors(text):
    regex = re.compile("\x1f|\x02|\x03|\x16|\x0f(?:\d{1,2}(?:,\d{1,2})?)?", re.UNICODE)
    ret = regex.sub('', text)
    return ret

# basic irc handlers
# --------------------------------------------------------------------------------


def hndl_serverping(msg, parsedmsg):
    write_sock(str.format("PONG %s\r\n" % parsedmsg[1].lstrip(':')))
    return True


# end of MOTD a.k.a. succesfully connected to irc and registered
def hndl_376(msg, parsedmsg):
    global st
    global conf
    st['bot']['registered'] = True
    irc_setumode( parsedmsg[2], "+iw")

    # join DM channel
    if conf['CHANKEY'] != "null":
        write_sock(str.format("JOIN %s %s\r\n" % (conf['IRCCHAN'], conf['CHANKEY']) ) )
    else:
        write_sock(str.format("JOIN %s\r\n" % conf['IRCCHAN']))

    # attempt to oper up!
    write_sock(str.format("OPER %s %s\r\n" % (conf['OPERNICK'], conf['OPERPASS']) ) )
    return True

# successfully opered up message
def hndl_381(msg, parsedmsg):
    global st
    st['bot']['opered'] = True
    irc_setumode( parsedmsg[2], "+CZbdfiklnorsuwxyz")

    # build client hash
    write_sock("ETRACE -full\r\n")

    return True

# there was a quit message but we didn't issue a QUIT command to the server
# def hndl_quit(msg, parsedmsg):
#     global st
#
#     if st['bot']['selfquit']:
#         # we selfquit so insert poison pill into Queue to kill child worker and exit this process
#         st['queue'].put(None)
#         return True
#     else:
#         #
#     return True

# parse ETRACE response into client_hash
def hndl_708(msg, parsedmsg):
    global client_dict
    global st
    if len(parsedmsg) < 11:
        return False
    # target = parsedmsg[2]
    # usertype = parsedmsg[3]
    # userclass = parsedmsg[4]
    # nick = parsedmsg[5]
    # username = parsedmsg[6]
    # hostname = parsedmsg[7]
    # ip = parsedmsg[8]
    # gecos = msg[msg.rfind(':')+1:]
    # searchstr = nick + '!' + username + '@' + hostname + '#' + gecos

    if st['bot']['debug_mode']:
        print("searchstr: " + parsedmsg[5] + '!' + parsedmsg[6] + '@' + parsedmsg[7] + '#' + msg[msg.rfind(':')+1:], file=sys.stderr)

    aclient = {
        'type' : parsedmsg[3],
        'userclass' : parsedmsg[4],
        'username' : parsedmsg[6],
        'hostname' : parsedmsg[7],
        'ip' : parsedmsg[8],
        'gecos' : msg[msg.rfind(':')+1:],
        'searchstr' : parsedmsg[5] + '!' + parsedmsg[6] + '@' + parsedmsg[7] + '#' + msg[msg.rfind(':')+1:]
    }

    if parsedmsg[5] not in client_dict:
        client_dict[parsedmsg[5]] = aclient

    return True

# end of ETRACE
def hndl_262(msg, parsedmsg):
    global client_dict
    irc_privmsg(conf['IRCCHAN'],str.format('-> got %d clients hashed.' % len(client_dict)) )
    return True

def hndl_pong(msg, parsedmsg):
    global st
    t = time.time()
    st['socket']['lag'] = (t - st['socket']['lastping'])
    return True

def hndl_error(msg, parsedmsg):
    global st
    st['socket']['connected'] = False
    return
# cmd handlers for privmsg
# --------------------------------------------------------------------------------


def cmd_die(msg, parsedmsg):
    global st
    st['bot']['selfquit'] = True
    msg = msg.split(maxsplit=4)
    if len(msg) == 5:
        write_sock( str.format("QUIT :%s\r\n" % msg[4]) )
    else:
        write_sock( "QUIT :killroy was here!\r\n" )
    return True

def cmd_check(msg, parsedmsg):
    sender, x, target, pmsg = msg.split(maxsplit=3)

    # strip leading : from actual message sent
    pmsg = pmsg[1:]

    if pmsg[0] == ".":
        cmd_dispatch(msg)
    return True

def cmd_raw(msg, parsedmsg):
    sender, x, target, cmd, cmdargs = msg.split(maxsplit=4)
    write_sock(str.format( "%s\r\n" % cmdargs))
    return True

def cmd_etrace(msg, parsedmsg):
    sender, x, target, cmd = msg.split(maxsplit=3)
    c = cmd.split()
    if len(c) == 2:
        cmdargs = c[1]
        write_sock(str.format("ETRACE %s\r\n" % cmdargs))
    else:
        write_sock(str.format("ETRACE\r\n"))
    return True

def cmd_lag(msg, parsedmsg):
    global st
    sender_nick = parsedmsg[0][1:][0:parsedmsg[0][1:].find('!')]
    #sender_nick = sender[1:sender.find('!')]
    msg = str.format("lag: %d seconds\r\n" % st['socket']['lag'])
    irc_privmsg( sender_nick, msg )
    return True

def cmd_rsearch(msg, parsedmsg):
    global st
    global client_dict
    sender, x, target, cmd = msg.split(maxsplit=3)
    sender = get_sender(msg)

    c = cmd.split()
    if len(c) == 2:
        cmdargs = c[1]
    else:
        return False

    try:
        srch = re.compile(cmdargs)
    except:
        irc_privmsg()
    for k in client_dict.keys():
        m = re.match(srch, client_dict[k]['searchstr'])
        if m:
            irc_privmsg(sender, str.format('client matched -> %s' % client_dict[k]['searchstr']))
    return True

# dispatch code
# --------------------------------------------------------------------------------

# dispatch various server messages to their registered handlers
def irc_dispatch(rawmsg):
    global st
    if st['bot']['debug_mode'] and len (rawmsg) > 0:
        print("-> %s" % rawmsg.rstrip('\n'), file=sys.stderr)

    global handler_dict
    rawmsg = strip_colors(rawmsg)
    parsedmsg = rawmsg.split()

    for i in range( len( parsedmsg ) ):

        # do we have a bucket for this?
        if i in handler_dict:

            # do we have triggers for this in the bucket?
            if parsedmsg[i] in handler_dict[i]:
                #we do so grab handler function list and call them all in succession
                handlerlist = handler_dict[i][ parsedmsg[i] ]
                for n in range( len( handlerlist) ):
                    handlerlist[n](rawmsg, parsedmsg)

        #step
        else:
            continue
    return


# handle commands by PRIVMSG
def cmd_dispatch(rawmsg):
    global cmd_dict
    parsedmsg = rawmsg.split(maxsplit=4)

    sender = parsedmsg[0]
    target = parsedmsg[2]
    cmd = parsedmsg[3][1:]

    #print("cmd: %s\nparsedmsglen: %d\nargs: %s" % (cmd, len(parsedmsg), parsedmsg[-1]), file=sys.stderr)
    #return

    if cmd[0] == ":":
        cmd = cmd[1:]

    # we don't have a handler for this. skip!
    if cmd not in cmd_dict:
        return False

    # found a handler list.  call em.
    if cmd in cmd_dict:
        pmsg = rawmsg.split()
        handlerlist = cmd_dict[cmd]
        for i in range( len(handlerlist)):
            handlerlist[i](rawmsg, pmsg)

    return True

# handle various notices
def notice_dispatch(msg, parsedmsg):
    global conf
    global st

    # update client_dict for nick changes
    if len(parsedmsg) > 7 and parsedmsg[6] == 'Nick' and parsedmsg[7] == 'change:':
        fromnick = parsedmsg[9]
        tonick = parsedmsg[11]
        hndl_nickchange(fromnick, tonick)
        return True
    # update client_dict for new client connect
    elif len(parsedmsg) > 7 and parsedmsg[6] == 'CLICONN':
        nick = parsedmsg[7]
        return hndl_cliconn(nick, msg, parsedmsg)
    # update client_dict for client exit
    elif len(parsedmsg) > 7 and parsedmsg[6] == 'CLIEXIT':
        nick = parsedmsg[7]
        return hndl_cliexit(nick)
    # update client_dict for user opering up
    elif len(parsedmsg) > 11 and parsedmsg[11] == 'operator':
        nick = parsedmsg[6]
        return hndl_user2oper(nick)
    else:
        return True
    return True

def hndl_nickchange(fromnick, tonick):
    global st
    global client_dict
    if not fromnick in client_dict:
        if st['bot']['debug_mode']:
            irc_privmsg(conf['IRCCHAN'], str.format('Detected nick change but I don\'t have a record for \0x2%s\x02' % fromnick))
            return
    else:
        if st['bot']['debug_mode']:
            irc_privmsg(conf['IRCCHAN'], str.format('Detected nick change: \x02%s -> %s\x02 - Updating client hash...' % (fromnick, tonick)))
        oldrec = client_dict[fromnick]
        oldrec['searchstr'] = tonick + '!' + oldrec['username'] + '@' + oldrec['hostname'] + '#' + oldrec['gecos']
        client_dict[tonick] = oldrec
        del client_dict[fromnick]
    return True

# currently assumes ratbox umode +C
def hndl_cliconn(nick, msg, parsedmsg):
    global client_dict
    global st

    if st['bot']['debug_mode']:
        print("CLICONN: %s" % nick, file=sys.stderr)

    ctcp_reply(nick, "VERSION")

#-> :irc.logick.net NOTICE * :*** Notice -- CLICONN esp_ esp pop.pop.ret 255.255.255.255 opers <hidden> <hidden> 0 this is a realname.
    pmsg = msg.split(maxsplit=15)
    if not nick in client_dict:
        aclient = {
            'type' : 'User',
            'userclass' : parsedmsg[11],
            'username' : parsedmsg[8],
            'hostname' : parsedmsg[9],
            'ip' : parsedmsg[10],
            'gecos' : pmsg[-1],
            'searchstr' : parsedmsg[7] + '!' + parsedmsg[8] + '@' + parsedmsg[9] + '#' + pmsg[-1]
        }

        client_dict[nick] = aclient
        return True
    else:
        return False

    return True

def hndl_cliexit(nick):
    global client_dict
    if nick in client_dict:
        del client_dict[nick]
    else:
        return False
    return True

def hndl_user2oper(nick):
    global client_dict
    if nick in client_dict:
        client_dict[nick]['type'] = 'Oper'
    else:
        return False
    return True

# add a handler to the function list for a given irc message
def add_irc_handler(bucket, trigger, func):
    global handler_dict

    #bucket doesn't exist so create it empty
    if bucket not in handler_dict:
        handler_dict[bucket] = dict()

    #trigger does not exist in the bucket so create it empty
    if trigger not in handler_dict[bucket]:
        handler_dict[bucket][trigger] = list()

    #insert the handler function
    handler_dict[bucket][trigger].append(func)

    return

def add_cmd_handler(cmd, func):
    if cmd not in cmd_dict:
        cmd_dict[cmd] = list()
    cmd_dict[cmd].append(func)
    return True

# initialize module and handlers
# NOTE:  these handlers are APPENDED to the list for the msgtype and are not meant to be added and removed dynamically
# --------------------------------------------------------------------------------
def init(config, state, debug_mode=False):
    # register on irc
    global st
    global conf
    global handler_dict
    global cmd_dict

    handler_dict = dict()
    cmd_dict = dict()
    st = state
    conf = config

    st['bot']['debug_mode'] = debug_mode

    # server notices
    add_irc_handler(0,'PING', hndl_serverping)
    add_irc_handler(0, 'PONG', hndl_pong)
    add_irc_handler(1, 'NOTICE', notice_dispatch)
    add_irc_handler(0, 'ERROR', hndl_error)
    add_irc_handler(1, 'PRIVMSG', cmd_check)

    # numerics
    add_irc_handler(1,'376', hndl_376)
    add_irc_handler(1, '381', hndl_381)
    add_irc_handler(1, '708', hndl_708)
    add_irc_handler(1, '262', hndl_262)

    # cmd dispatch
    add_cmd_handler(".die", cmd_die)
    add_cmd_handler(".raw", cmd_raw)
    add_cmd_handler(".etrace", cmd_etrace)
    add_cmd_handler(".lag", cmd_lag)
    add_cmd_handler(".rsearch", cmd_rsearch)
    return True
