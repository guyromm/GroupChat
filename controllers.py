# -*- coding: utf-8 -*-
'''
filedesc: default controller file
'''
from noodles.http import Response
from noodles.websocket import MultiChannelWS, WebSocketHandler
from noodles.templates import render_to
import logging,gevent,redis,json,sys,datetime
from noodles.redisconn import RedisConn

@render_to('index.html')
def index(request):
    return {}
channelpref = 'chatme'

def dispatcher_routine(chan):
    " This listens dispatcher redis channel and send data through operator channel "
    rc = redis.Redis()
    sub = rc.pubsub()
    logging.info('subscribing to chat at %s'%channelpref)
    sub.subscribe(channelpref)
    for msg in sub.listen():
        logging.info('CHANNEL %s < DISPATCHER MESSAGE %s'%(chan,msg))
        msgd = msg['data']
        chan.send(json.loads(msgd)) #tosend(WS_CHANNELS['BO_CHID'], json.loads(msg['data']))                                                                     
    
class ChatChannel(WebSocketHandler):
    def onopen(self):
        self.dispatcher = gevent.spawn(dispatcher_routine, self)
    def onmessage(self, msg):
        m = msg.data
        logging.info('ONMESSAGE < %s ; %s'%(msg.data,m['op']))

        if m['op']=='msg':
            m['sender'] = self.request.remote_addr
            m['stamp'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%m')
            logging.info('PUBLISH(%s) > %s'%(channelpref,m))
            RedisConn.publish(channelpref,json.dumps(m))
        #self.send(msg.data)

class ChatWebsocket(MultiChannelWS):
    def init_channels(self):
        self.register_channel(1,ChatChannel)
    def onerror(self, e):                                                                                                                                             
        f = logging.Formatter()
        traceback = f.formatException(sys.exc_info())
        err_message = {'chid': 500, 'pkg': {'exception': e.__repr__(), 'tb': traceback}}
        logging.info('sending exception %s to user over error channel'%(err_message))
        self.send(err_message)
