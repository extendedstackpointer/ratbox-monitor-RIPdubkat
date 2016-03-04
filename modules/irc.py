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
import sys

handler_dict = dict()
cmd_dict = dict()
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


def generic_notice(msg, parsedmsg):
    return True

def hndl_serverping(msg, parsedmsg):
    write_sock(str.format("PONG %s\r\n" % parsedmsg[1].lstrip(':')))
    return True


# end of MOTD a.k.a. succesfully connected to irc and registered
def hndl_376(msg, parsedmsg):
    global is_registered
    global conf
    global is_opered
    is_registered=True
    is_opered = True
    write_sock(str.format("MODE %s +iwg\r\n" % parsedmsg[2]))
    write_sock(str.format("OPER %s %s\r\n" % (conf['OPERNICK'], conf['OPERPASS']) ) )
    return True

# successfully opered up message
def hndl_381(msg, parsedmsg):
    global is_opered
    is_opered = True
    irc_setumode( parsedmsg[2], "+CZbdfiklnorsuwxyz")
    return True

# there was a quit message but we didn't issue a QUIT command to the server
def hndl_died(msg, parsedmsg):
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


def cmd_quit(msg, parsedmsg):
    global selfquit
    selfquit = True
    msg = msg.split(maxsplit=4)
    if len(msg) == 5:
        write_sock( str.format("QUIT :%s\r\n" % msg[4]) )
    else:
        write_sock( str.format("QUIT :killroy was here!\r\n"))
    return True

def cmd_check(msg, parsedmsg):
    sender, x, target, pmsg = msg.split(maxsplit=3)

    # strip leading : from actual message sent
    if pmsg[0] == ":":
        pmsg = pmsg[1:]

    if pmsg[0] == ".":
        cmd_dispatch(msg)
    return True

def cmd_raw(msg, parsedmsg):
    sender, x, target, cmd, cmdargs = msg.split(maxsplit=4)
    write_sock(
        str.format( "%s\r\n" % cmdargs)
    )
    return True

# dispatch code
# --------------------------------------------------------------------------------

# dispatch various server messages to their registered handlers
def irc_dispatch(rawmsg):

    if debug and len (rawmsg) > 0:
        print("-> %s" % rawmsg.rstrip('\n'), file=sys.stderr)

    global handler_dict
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
    sender, x, target, cmd, cmdargs = rawmsg.split(maxsplit=4)

    if cmd[0] == ":":
        cmd = cmd[1:]

    if cmd not in cmd_dict:
        return False

    if cmd in cmd_dict:
        pmsg = rawmsg.split()
        handlerlist = cmd_dict[cmd]
        for i in range( len(handlerlist)):
            handlerlist[i](rawmsg, pmsg)

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
def init(sq, config, debug_mode=False):
    # register on irc
    global sendq
    sendq = sq

    global conf
    conf = config

    global debug
    debug = debug_mode
    # server requests such as PING
    add_irc_handler(0,'PING', hndl_serverping)
    add_irc_handler(0, 'NOTICE', generic_notice)
    add_irc_handler(0, 'ERROR', hndl_died)

    # server notices
    add_irc_handler(0, 'QUIT', hndl_died)

    # numerics
    add_irc_handler(1,'376', hndl_376)
    add_irc_handler(1, '381', hndl_381)

    # first privmsg handler should look for commands
    add_irc_handler(1, 'PRIVMSG', cmd_check)

    # cmd dispatch
    add_cmd_handler(".die", cmd_quit)
    add_cmd_handler(".raw", cmd_raw)
    return True
