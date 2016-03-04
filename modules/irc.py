# this module consists of irc_dispatch(), cmd_dispatch(), and a series of handler functions stored in lists
# additional modules can be added by adhering to the procedure template and adding them to the list
# ideally this should actually be a class

# handler function structure
# this maps each type of message with a list of handler functions for that message type
# dispatch should be able to iterate over these.
# example structure:
# hander_dict{
#     'NUMERIC' : {
#         '376' : [
#             handler1(),
#             handler2(),
#             handler3()
#         ]
#     }
# }
from __future__ import print_function
import sys, re

handler_dict = {
    'SERVER_NOTICE' : {},
    'SERVER_REQUEST' : {},
    'NUMERIC' : {}
}

cmd_dict = {}

client_dict = dict()

# states
is_connected = False
is_registered = False
is_opered = False
selfquit = False
debug = False
sendq = None
conf = None

# utility functions
# --------------------------------------------------------------------------------
def is_int(val):
    try:
        v = int(val)
    except ValueError:
        return False
    return True


def get_clients():
    global client_dict
    return client_dict


def write_sock(strfmsg):
    global sendq
    msg = bytes( strfmsg, 'utf-8')
    sendq.put( msg )
    return


# send a CTCP response
def ctcp_reply(target, cmd, data):
    write_sock(
        str.format("PRIVMSG %s :\x01%s\x01 %s") % (target, cmd, data)
    )
    return True


# send a privmsg
def irc_privmsg(target, data):
    write_sock(
        str.format("PRIVMSG %s :%s") % (target, data)
    )
    return True

def irc_setumode(mynick, modelist):
    write_sock(
        str.format("MODE %s %s\r\n" % (mynick, modelist) )
    )
    return True

# to register after connecting
def irc_register(nick, username, extra1, extra2, gecos ):
    global is_connected
    is_connected=True
    #global sendq
    write_sock(str.format("NICK %s\r\n" % nick))
    write_sock(str.format("USER %s %s %s :%s\r\n" % (username, extra1, extra2, gecos)) )

    return True

# basic irc handlers
# --------------------------------------------------------------------------------


def generic_notice(sq, parsedmsg):
    return True


def hndl_serverping(sq, parsedmsg):
    write_sock(str.format("PONG %s\r\n" % parsedmsg[1].lstrip(':')))
    return True


# end of MOTD a.k.a. succesfully connected to irc and registered
def hndl_376(sq, parsedmsg):
    global is_registered
    global conf
    global is_opered
    is_registered=True
    is_opered = True
    write_sock(str.format("MODE %s +iwg\r\n" % parsedmsg[2]))
    write_sock(str.format("OPER %s %s\r\n" % (conf['OPERNICK'], conf['OPERPASS']) ) )
    return True

# successfully opered up message
def hndl_381(sq, parsedmsg):
    global is_opered
    is_opered = True
    irc_setumode( parsedmsg[2], "+CZbdfiklnorsuwxyz")
    return True

# there was a quit message but we didn't issue a QUIT command to the server
def hndl_died(sq, parsedmsg):
    global selfquit
    global is_connected
    global sendq
    if not selfquit:
        # poison the queue so it handles the disco in managing process
        sendq.put(None)
        sys.exit(0)
    else:
        # adjust data sets for a client quit
        is_connected = False
        return True
    is_connected = False
    return True

# cmd handlers for privmsg
# --------------------------------------------------------------------------------


def cmd_quit(sender, target, msg):
    global selfquit
    selfquit = True
    msg = msg.split(maxsplit=4)
    if len(msg) == 5:
        write_sock( str.format("QUIT :%s\r\n" % msg[4]) )
    else:
        write_sock( str.format("QUIT :killroy was here!\r\n"))
    return True

# dispatch code
# --------------------------------------------------------------------------------

# handle various server messages
def irc_dispatch(sq, rawmsg):
    global handler_dict
    parsedmsg = rawmsg.split(maxsplit=3)
    if len(parsedmsg) < 2:
        return

    print("line - %s" % rawmsg, file=sys.stderr)

    if is_int( parsedmsg[1] ):
        # its a numeric so iterate through all handlers registered to it
        numericlist = handler_dict['NUMERIC']
        if parsedmsg[1] in numericlist:
            for i in range(len(numericlist[parsedmsg[1]])):
                numericlist[parsedmsg[1]][i](sq, parsedmsg)
    elif parsedmsg[0][0] is not ':' and '!' not in parsedmsg[0]:
        # its a server request and we need to answer
        # EG: PING needs a PONG
        reqlist = handler_dict['SERVER_REQUEST']
        if parsedmsg[0] in reqlist:
            for i in range(len(reqlist[parsedmsg[0]])):
                reqlist[parsedmsg[0]][i](sq, parsedmsg)
    elif parsedmsg[0][0] == ':' and '!' in parsedmsg[0] and parsedmsg[1] =='PRIVMSG':
        # send PRIVMSG to cmd_dispatch()
        print("send PM to cmd dispatch", file=sys.stderr)
        cmd_dispatch(rawmsg)
    else:
        # treat everything else as a server notice
        snlist = handler_dict['SERVER_NOTICE']
        if parsedmsg[1] in snlist:
            for i in range( len(snlist[parsedmsg[1]]) ):
                snlist[parsedmsg[1]][i](sq, rawmsg)
    return


# handle commands by PRIVMSG
def cmd_dispatch(rawmsg):
    parsedpm = rawmsg.split(maxsplit=4)
    sender = re.split("\!|\@", parsedpm[0].lstrip(':'))
    target = parsedpm[2]
    realmsg = parsedpm[3].lstrip(':').split(maxsplit=1)
    if realmsg[0] in cmd_dict:
        for i in range( len(cmd_dict[realmsg[0]]) ):
            cmd_dict[realmsg[0]][i]( sender, target, rawmsg )
    return True

# add a handler to the function list for a given irc message
def add_irc_handler(msgclass, msgtype, function):
    global handler_dict

    if msgtype not in handler_dict[msgclass]:
        # no handlers exist for that msgtype so make a new one with empty list
        handler_dict[msgclass][msgtype] = list()

    handler_dict[msgclass][msgtype].append(function)
    return

def add_cmd_handler(trigger, cmd, function):
    if cmd not in cmd_dict:
        cmd_dict[cmd] = list()

    cmd_dict[cmd].append(function)
    return True

# initialize module and handlers
# NOTE:  these handlers are APPENDED to the list for the msgtype and are not meant to be added and removed dynamically
# --------------------------------------------------------------------------------
def init(sq, config):
    # register on irc
    global sendq
    sendq = sq

    global conf
    conf = config

    # server requests such as PING
    add_irc_handler('SERVER_REQUEST','PING', hndl_serverping)
    add_irc_handler('SERVER_REQUEST', 'NOTICE', generic_notice)
    add_irc_handler('SERVER_REQUEST', 'ERROR', hndl_died)

    # server notices
    add_irc_handler('SERVER_NOTICE', 'QUIT', hndl_died)

    # numerics
    add_irc_handler('NUMERIC','376', hndl_376)
    add_irc_handler('NUMERIC', '381', hndl_381)

    # cmd dispatch
    add_cmd_handler(".", ".die", cmd_quit)
    return True
