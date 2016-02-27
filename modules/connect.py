import socket, ssl, re, fcntl, os


def is_v6(hoststr):
    if re.search( r"(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]).){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]).){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))", hoststr):
        return True
    else:
        return False

# connect to the irc server and return a connected socket for stream
def do_connect(host, port, use_ssl, timeout=None):

    # do IPv4
    if not is_v6(host):
        if use_ssl:
            s = socket.socket( socket.AF_INET, socket.SOCK_STREAM)

            #defaults to PROTOCOL_v23 in client mode.  ciphers will be negotiated based on handshake from server
            sock = ssl.wrap_socket( s )
        else:
            sock = socket.socket( socket.AF_INET, socket.SOCK_STREAM)

    # do IPv6
    else:
        if use_ssl:
            s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            sock = ssl.wrap_socket( s )
        else:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)

    sock.settimeout(timeout)

    # light this candle
    sock.connect((host,port))
    fcntl.fcntl(sock, fcntl.F_SETFL, os.O_NONBLOCK)
    return sock
