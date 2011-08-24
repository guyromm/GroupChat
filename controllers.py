# -*- coding: utf-8 -*-
'''
filedesc: default controller file
'''
from noodles.http import Response
from noodles.websocket import MultiChannelWS, WebSocketHandler
from noodles.templates import render_to,render_to_string
import logging,gevent,redis,json,sys,datetime,os,hashlib,random
from noodles.redisconn import RedisConn

rooms = json.loads(open(os.path.join('conf','rooms.json'),'r').read())
usersfn = os.path.join('conf','users.json')
users = json.loads(open(usersfn,'r').read())
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

def saveusers():
    fp = open(usersfn,'w')
    fp.write(json.dumps(users))
    fp.close()

def getuser(name):
    global users
    return getroom(name,d=users,fatal=False)

def getroom(name,d=rooms,fatal=True):
    objs = [r for r in d if r['id']==name]
    if fatal:
        if len(objs)!=1: raise Exception('length of objs with id=%s is %s'%(name,len(objs)))
        return objs[0]
    else:
        return objs



#@auth
#@render_to('index.html')
def index(request,room=None):
    authck = request.cookies.get('auth')
    logging.info('current auth cookie is %s (%s)'%(authck,RedisConn.get('auth.%s'%authck)))
    setauthck=None
    if not authck or not RedisConn.get('auth.%s'%authck):
        un = request.params.get('username','')
        pw = request.params.get('password','')
        err=''
        if un:
            u = getuser(un)
            if u:
                logging.info('user exists')
                u = u[0]
                hpw = hashlib.md5(pw).hexdigest()
                #raise Exception('comparing %s with %s'%(u,hpw))
                if u['password']==hpw:
                    logging.info('generating auth cookie')
                    setauthck = ''.join(random.choice('abcdefghijklmnopqrstuvwxyz') for i in xrange(16))
                else:
                    err='invalid login'
            else:
                logging.info('creating new user')
                user={'username':un,'password':hashlib.md5(pw).hexdigest()}
                users.append(user)
                saveusers()
                err='user %s created succesfully. please log in'%un
        context = {'username':un,'password':pw,'err':err}
        rtpl='auth.html'
    else:
        
        rtpl='index.html'
        global rooms
        if room: openrooms = room.split(',')
        else: openrooms = []
        openrooms = [getroom(rn) for rn in openrooms]
        context = {'rooms':json.dumps(rooms),'openrooms':json.dumps(openrooms),'user':RedisConn.get('auth.%s'%authck),'authck':authck}

    rendered_page = render_to_string(rtpl, context, request)
    rsp= Response(rendered_page)
    if setauthck: 
        rsp.set_cookie('auth',setauthck)
        RedisConn.set('auth.%s'%setauthck,un)
        logging.info('setting auth cookie = %s'%(setauthck))
        rsp.headers['Location']='/'
    return rsp

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
    authenticated=False
    authck = None
    user=None
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
        
        if m['op'] in 'auth':
            rauth = RedisConn.get('auth.%s'%m['authck'])
            if rauth == m['user']:
                self.authenticated=True
                self.user = m['user']
                self.authck = m['authck']
        if not self.authenticated:
            raise Exception('not authenticated')

        if m['op'] in 'auth': pass
        elif m['op'] in 'logout':
            RedisConn.delete('auth.%s'%self.authck)
            logging.info('signing out %s/%s'%(self.user,self.authck))
            self.send({'op':'signoutresult','status':'ok'})
        elif m['op']=='msg':
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
                o['sender'] = self.user #self.request.remote_addr
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

