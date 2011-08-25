# -*- coding: utf-8 -*-
'''
filedesc: default controller file
'''
from noodles.http import Response,Redirect
from noodles.websocket import MultiChannelWS, WebSocketHandler
from noodles.templates import render_to,render_to_string
import logging,gevent,redis,json,sys,datetime,os,hashlib,random
from noodles.redisconn import RedisConn

rooms = json.loads(open(os.path.join('conf','rooms.json'),'r').read())
usersfn = os.path.join('conf','users.json')
users = json.loads(open(usersfn,'r').read())
roomfiles = {}

ROWLIMIT = 10

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
    try:
        objs = [r for r in d if r['id']==name]
    except KeyError:
        logging.info('error searching in %s'%d)
        raise
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
                user={'id':un,'password':hashlib.md5(pw).hexdigest()}
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
        openrooms = [getroom(rn) for rn in openrooms if rn[0]!='@']
        context = {'rooms':json.dumps(rooms),'openrooms':json.dumps(openrooms),'user':RedisConn.get('auth.%s'%authck),'authck':authck,'rowlimit':ROWLIMIT}

    rendered_page = render_to_string(rtpl, context, request)
    rsp= Response(rendered_page)
    if setauthck: 
        RedisConn.set('auth.%s'%setauthck,un)
        logging.info('setting auth cookie = %s (redis value = %s)'%(setauthck,RedisConn.get('auth.%s'%setauthck)))
        rsp =  Redirect('/')
        rsp.set_cookie('auth',setauthck)
    return rsp

channelpref = 'chatme_'

def dispatcher_routine(chan):
    " This listens dispatcher redis channel and send data through operator channel "
    rc = redis.Redis()
    sub = rc.pubsub()
    myrooms = RedisConn.smembers('rooms.%s'%chan.user)
    channels = []
    for rm in myrooms:
        logging.info('rm = %s, type=%s ; decoded: %s'%(rm,type(rm),json.loads(rm)))
        nch = channelpref+json.loads(rm)['id']
        channels.append(nch)
    if chan.user:
        channels.append(channelpref+'@'+chan.user)
    #channels = set([channelpref+rm['id'] for rm in myrooms])
    #substr = ' '.join(channels)
    if len(channels):
        for ochan in channels:
            RedisConn.publish(ochan,json.dumps({'op':'subscribe','user':chan.user,'room':ochan.split('_')[1],'stamp':nowstamp()}))

        logging.info('subscribing to chat at %s'%channels)
        sub.subscribe(channels)
        for msg in sub.listen():
            if msg['type']=='subscribe': 
                logging.info('SKIPPING SUBSCRIBE MESSAGE %s'%msg)
                continue
            logging.info('CHANNEL %s < DISPATCHER MESSAGE %s'%(chan,msg))
            msgd = msg['data']
            chan.send(json.loads(msgd)) #tosend(WS_CHANNELS['BO_CHID'], json.loads(msg['data']))                                                                     
    else:
        logging.info('no channels to subscribe to')
def nowstamp():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
class ChatChannel(WebSocketHandler):
    dispatcher=None
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
        if unsub:
            logging.info('looks like we\'re leaving. unsubscribing from channels:')
            while len(RedisConn.smembers('rooms.%s'%self.user)):
                room = json.loads(RedisConn.spop('rooms.%s'%self.user))['id']
                logging.info('unsub: %s'%room)
                ochan = channelpref + room
                RedisConn.srem('users.%s'%room,self.user)
                RedisConn.publish(ochan,json.dumps({'op':'unsubscribe','user':self.user,'room':room,'stamp':nowstamp()}))
        else:
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
                roomkey='rooms.%s'%self.user
                myrooms = RedisConn.smembers(roomkey)
                if roomname not in [json.loads(mr)['id'] for mr in myrooms]:
                    logging.info('%s not in myrooms %s, hence adding'%(roomname,myrooms))
                    RedisConn.sadd(roomkey,json.dumps(o))
                    myrooms = RedisConn.smembers(roomkey)
                    lo = {'op':'join','room':roomname,'user':self.user,'stamp':nowstamp(),'obj':o}
                    writelog(roomname,json.dumps(lo))

                RedisConn.sadd('users.%s'%roomname,self.user)


                self.resub()
                self.send({'op':'joinresult','status':'ok','roomname':roomname,'obj':o,'content':self.roomcontent(roomname),'users':list(RedisConn.smembers('users.%s'%roomname))})
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
                roomkey = 'rooms.%s'%self.user
                myrooms = RedisConn.smembers(roomkey)
                if roomname in [json.loads(mr)['id'] for mr in myrooms]:
                    RedisConn.srem(roomkey,json.dumps({'id':roomname}))
                    lo = {'op':'leave','room':roomname,'user':self.user,'stamp':nowstamp(),'obj':m['obj']}
                    writelog(roomname,json.dumps(lo))
                    logging.info('DEPARTTURE of %s from %s -> %s'%(self.user,roomname,RedisConn.smembers(roomkey)))
                    
                RedisConn.srem('users.%s'%roomname,self.user)
                self.resub()

                self.send({'op':'leaveresult','status':'ok','roomname':roomname})
            else:
                raise Exception('unknown objtype %s'%m['objtype'])
        elif m['op']=='leaveall':
            while len(RedisConn.smembers('rooms.%s'%self.user)): RedisConn.spop('rooms.%s'%self.user)
            self.resub()
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
            if len(rt)>ROWLIMIT: rt.pop(0)
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

