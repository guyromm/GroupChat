# -*- coding: utf-8 -*-
'''
filedesc: default controller file
'''
from noodles.http import Response
from noodles.websocket import MultiChannelWS, WebSocketHandler
from noodles.templates import render_to
import logging,gevent,redis,json,sys,datetime,os
from noodles.redisconn import RedisConn

rooms = json.loads(open('rooms.json','r').read())

roomfiles = {}
def writelog(r,l):
    global roomfiles
    fn = os.path.join('logs',r+'.log')
    if fn not in roomfiles:
        fp = open(fn,'a')
        roomfiles[fn]=fp
    else:
        fp = roomfiles[fn]
    fp.write(l+'\n')
    fp.flush()
    #fp.close()

def getroom(name):
    global rooms
    objs = [r for r in rooms if r['id']==name]
    return objs[0]
@render_to('index.html')
def index(request,room=None):
    global rooms
    if room: openrooms = room.split(',')
    else: openrooms = []
    openrooms = [getroom(rn) for rn in openrooms]
    return {'rooms':json.dumps(rooms),'openrooms':json.dumps(openrooms)}
channelpref = 'chatme_'

def dispatcher_routine(chan):
    " This listens dispatcher redis channel and send data through operator channel "
    rc = redis.Redis()
    sub = rc.pubsub()
    channels = set([channelpref+rm['id'] for rm in chan.myrooms])
    #substr = ' '.join(channels)
    if len(channels):
        logging.info('subscribing to chat at %s'%channels)
        sub.subscribe(channels)
        for msg in sub.listen():
            if msg['type']=='subscribe': 
                logging.info('SKIPING SUBSCRIBE MESSAGE %s'%msg)
                continue
            logging.info('CHANNEL %s < DISPATCHER MESSAGE %s'%(chan,msg))
            msgd = msg['data']
            chan.send(json.loads(msgd)) #tosend(WS_CHANNELS['BO_CHID'], json.loads(msg['data']))                                                                     
    else:
        logging.info('no channels to subscribe to')
def nowstamp():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%m')
class ChatChannel(WebSocketHandler):
    dispatcher=None
    myrooms=[]
    def onopen(self):
        self.resub()
    def resub(self,unsub=False):
        if self.dispatcher:
            logging.info('tearing down message dispatcher')
            gevent.kill(self.dispatcher)
            self.dispatcher=None
        if not unsub:
            logging.info('creating new dispatcher')
            self.dispatcher = gevent.spawn(dispatcher_routine, self)
    def onmessage(self, msg):
        m = msg.data
        logging.info('ONMESSAGE < %s ; %s'%(msg.data,m['op']))
        
        if m['op']=='msg':
            pass
        elif m['op']=='join':
            pass
        elif m['op'] in ['create','update']:
            o = m['obj']
            if m['objtype']=='joinedroom':
                roomname = o['id']
                r =  getroom(roomname) ; assert r
                if roomname not in self.myrooms:
                    self.myrooms.append(o)
                self.resub()
                self.send({'op':'joinresult','status':'ok','roomname':roomname,'obj':o,'content':self.roomcontent(roomname)})
            elif m['objtype']=='message':
                o['sender'] = self.request.remote_addr
                o['stamp'] = nowstamp()
                line = json.dumps(o)
                writelog(o['room'],line)
                pubchan = channelpref+o['room']
                assert o['room']
                logging.info('PUBLISH(%s) > %s'%(pubchan,m))
                RedisConn.publish(pubchan,json.dumps(m))
            else:
                raise Exception('unknown objtype %s'%m['objtype'])
        elif m['op'] in ['delete']:
            if m['objtype']=='joinedroom':
                roomname = m['obj']['id']
                r = getroom(roomname) ; assert r
                if roomname in self.myrooms:
                    self.myrooms.remove(roomname)
                self.resub()
                self.send({'op':'leaveresult','status':'ok','roomname':roomname})
            else:
                raise Exception('unknown objtype %s'%m['objtype'])
        else:
            raise Exception('unknown op %s'%m['op'])
        #self.send(msg.data)
    def roomcontent(self,roomname):
        fn = os.path.join('logs',roomname+'.log')
        if not os.path.exists(fn): 
            logging.info('log %s does not exist'%fn)
            return []

        fp = open(fn,'r')
        if os.stat(fn).st_size>=5000:
            seekam = -5000
            while True:
                try:
                    fp.seek(seekam,os.SEEK_END)
                    break
                except IOError:
                    seekam/=10

            fp.readline()
        rt = []
        while True:
            rl = fp.readline()
            if not rl: break
            jl = json.loads(rl)
            rt.append(jl)
        return rt #[{"content":"hi there, welcome to %s!"%roomname,"sender":"server","stamp":nowstamp()}]
    def onclose(self):
        logging.info('ChatChannel.ONCLOSE')
        self.resub(unsub=True)


class ChatWebsocket(MultiChannelWS):
    def init_channels(self):
        self.register_channel(1,ChatChannel)
    def onerror(self, e):                                                                                                                                             
        f = logging.Formatter()
        traceback = f.formatException(sys.exc_info())
        err_message = {'chid': 500, 'pkg': {'exception': e.__repr__(), 'tb': traceback}}
        logging.info('sending exception %s to user over error channel'%(err_message))
        self.send(err_message)

