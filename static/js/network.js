
var API_SERVER_HOST // use this variable to set API server host

// For ie9 and browser which doesn't support console
if (typeof(console) == 'undefined'){
    var console = {
        log: function(data){
            // do nothing
        },
        
        warning: function(data){
            // do nothing
        },
        
        error: function(data){
            // do nothing
        },

        info: function(data){
            // do nothing
        },
        
        count: function(data){
        	// do nothing
        }
    }
}

// Server emulation functionality for self testing

var gameCredits = 0

function initWebSocketConn(url, gameType)
{
 	setWebsocketConn(params.one_time_token);

    /*console.log( "initting websocket "+url+" for game "+gameType);
	    if(getHashVars()['offline'] != 1)
		{
		    xmlhttp=new XMLHttpRequest();
		    if(url)
			{
			    xmlhttp.open("POST",url,true);
			    xmlhttp.setRequestHeader("Content-type","application/x-www-form-urlencoded");
			    try{
				xmlhttp.send('gameType=' + gameType);
			    }
			    catch(err){
				setWebsocketConn('');
			    }
			}
		    else
			{
			    setWebsocketConn('');
			}
		

		    xmlhttp.onreadystatechange=function()
			{
			    if (xmlhttp.readyState==4 && xmlhttp.status==200)
				{
				    response = eval('(' + xmlhttp.responseText + ')')
			
				    setWebsocketConn(response.access_token);
				}
			}
			}
	}*/

}

function server_emulation(request, opts, networkObj){
    
    switch(request.Action.name){
        case 'init':
            balance = opts['balance'] | gameCredits;
        response = {errorCode: 0, Data: {Action: 'init', Result:{gsid: 7, Balance: balance}}};
            break;
        case 'beginGame':
            credit = opts['credits'] | gameCredits;
            if (credit > 0){
                response = {errorCode: 0, Data: {Action: 'beginGame', Result:{gsid: 7, gameID: 77, credit: credit}}}
            }
            else
                response = {errorCode: 303, errorMsg: 'No such credit to start game'};
            break;
        case 'scratch':
            result = opts['outcome'] | 0;
		stake = request.Action.params.amount | 0;
        response = {errorCode: 0, Data: {Action: 'scratch', Result: result, Balance: balance - stake + (stake*result)}};
            break;
        case 'leaveGame':
            response = {errorCode: 0, Data: {Action: 'leaveGame', Result: 'OK'}}
            break;
        case 'buyCredit':
            gameCredits += request.Action.params.amount;
            credit = opts['credits'] | gameCredits;
            response = {errorCode: 0, Data: {Action: 'buyCredit', Result: credit}}
                
    }
    
    api_channel.receiveCallback(response);
}

// New style object to communicate with server

// Some constants for channels id - this will eventually come from the serverside code
var CHANNELS = {SUPPORT_CHID:1,API_CHID:2,OP_CHID:3,BO_CHID:4,ERROR_CHID:500};

// The list of channel objects by channel_id
var channelObjs = Array()

// Create web socket connection with server
//host = ''
if (window.location.hostname){ host = window.location.hostname + ':' + window.location.port}
else {
    // while use this default value if not location is set 
    //host = '';//85.17.122.213:8080';
    }

// API_SERVER_HOST variable for storing here server host
host = API_SERVER_HOST || host;

var wsocket;
console.log("working with wsocket %o",wsocket);
var ws_connect_opened = false; // WebSocket opened flag
var ws_msg_stack = new Array(); // Stack for storing messages if WS connection isn't established

var wsocket_onopen = function(){
    //alert('Socket is opened');
    ws_connect_opened = true;
    var i = 0;
    // Send all messages from stack
    while (ws_msg_stack.length != i) {
	msg = ws_msg_stack[i];
	data_to_send = JSON.stringify(msg);
	wsocket.send(data_to_send);
	i += 1;
    }
}
    
function setWebsocketConn(user_access_token,noconn){
    if (!noconn)
    {
	wsocket = new WebSocket('ws://' + host + '/wsproxy/'+user_access_token+'/'+params.gamename);
	console.log('Try to open web socket on host: %o acess_token: %o', host, user_access_token)
    }
    wsocket.onopen = wsocket_onopen;

	wsocket.onmessage = function(obj){
		console.log(obj.data);
		response = eval('(' + obj.data + ')');
		channel_id = response.chid;
		if (channelObjs[channel_id]){
		    channel_inst = channelObjs[channel_id]; // get channel object instance for this channel
		    //alert(response.pkg);
		    channel_inst.receiveCallback(response.pkg);
		}
		else { 
		    //nothing
		 }
	}

	wsocket.onclose = function(obj){
		//alert('Connection with socket is closed. Try to connect with server');
		initWebSocketConn(get_token_url);
	}	
}

// Set web socket connection


if (getHashVars()['offline'] != 1){
} else {
	console.warn('Working in offline mode')
}

// main channel object for connecting with server
function Channel(channel_id) {
    console.log('initializing channel %o',channel_id);
    this.channel_id = channel_id;
    if (channelObjs[channel_id]){
        console.warning('Override channel object for channel no. ' + channel_id)
    }
    
    this.onRecieve = function(callback){
		this.receiveCallback = callback;
	}
	
	this._send = function(){
	    // while pass
	}
	
	this.send = function(data){
	    sent_obj = {chid: this.channel_id, pkg: data};
	    if (ws_connect_opened){
	        // If connection is opened just send data
	        data_to_send = JSON.stringify(sent_obj);
		console.log("sending over wsocket %o",data_to_send);
	        wsocket.send(data_to_send)
	    }
	    else{
	        // If not - put data to stack
	        ws_msg_stack.push(sent_obj);
	    }
	}
	
	channelObjs[channel_id] = this;

}


var api_channel = new Channel(CHANNELS.API_CHID);

network = {
    send: function(actionName, args){
	    
	    //console.log(window.location.hash);
	    
	    opts = getHashVars();

		if ((typeof args == "undefined") || (args == "")) args = {};
		
		offline = opts['offline'] | false;
		if (offline){

		    // self testing case
		    this._emulate({
		    "Action": {"name":actionName, "params":args},

		    "AppID":1
		    }, opts, this);
		}
		else{

          api_channel.send({
		    "Action": {"name":actionName, "params":args},
		    "AppID":1

		    });
		}		
		
	},
    
    onRecieve: function(callback){
        api_channel.onRecieve(callback)
    },
    
    _emulate: server_emulation
}

function getHashVars()
{
    var vars = [], hash;
    var hashes = window.location.href.slice(window.location.href.indexOf('#') + 1).split('&');
 
    for(var i = 0; i < hashes.length; i++)
    {
        hash = hashes[i].split('=');
        vars.push(hash[0]);
        vars[hash[0]] = hash[1];
    }
 
    return vars;
}

// Error channel handler

var error_channel = new Channel(CHANNELS.ERROR_CHID)

error_channel.onRecieve(
	function(response){
		// TODO: Make here facility for cool console	
		alert(response.tb);
	})

//examples of usage:
//  network.url = ""
//	network.onRecieve(function(response){
//			console.log(response);
//	});
//	network.send('init', 1)
