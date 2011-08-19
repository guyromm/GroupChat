# -*- coding: utf-8 -*-
'''
filedesc: default controller file
'''
from noodles.http import Response
from noodles.websocket import MultiChannelWS, WebSocketHandler
from noodles.templates import render_to
import logging,gevent,redis
from noodles.redisconn import RedisConn

@render_to('index.html')
def index(request):
    return {}

def dispatcher_routine(chan):
    " This listens dispatcher redis channel and send data through operator channel "
    rc = redis.Redis()
    sub = rc.pubsub()
    logging.info('subscribing to chat')
    sub.subscribe('chat')
    for msg in sub.listen():
        logging.info('CHANNEL %s < DISPATCHER MESSAGE %s'%(chan,msg))
        chan.send(json.loads(msg['data'])) #tosend(WS_CHANNELS['BO_CHID'], json.loads(msg['data']))                                                                     
    
class ChatChannel(WebSocketHandler):
    def onopen(self):
        self.dispatcher = gevent.spawn(dispatcher_routine, self)
    def onmessage(self, msg):
        m = msg.data
        logging.info('ONMESSAGE < %s ; %s'%(msg.data,m['op']))

        if m['op']=='msg':
            logging.info('PUBLISH > %s'%m)
            RedisConn.publish('chat',json.dumps(m))
        #self.send(msg.data)

class ChatWebsocket(MultiChannelWS):
    def init_channels(self):
        self.register_channel(1,ChatChannel)
        
