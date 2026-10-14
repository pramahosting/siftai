import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Mic,MicOff,Video,VideoOff,MonitorUp,MessageSquare,Circle,Square,PhoneOff,Link2,Users,Send,X,UserX,ShieldCheck,Check} from 'lucide-react';

type Peer={id:string;name:string;host?:boolean;stream:MediaStream;mic:boolean;cam:boolean;screen:boolean};
const wsUrl=(api:string,code:string)=>{const base=api.startsWith('http')?api:location.origin+api;return base.replace(/^http/,'ws')+`/ws/rooms/${code}`};

function VideoTile({stream,name,muted,off,host,screen,self}:{stream:MediaStream|null;name:string;muted?:boolean;off?:boolean;host?:boolean;screen?:boolean;self?:boolean}){
  const ref=useRef<HTMLVideoElement>(null);
  useEffect(()=>{const v=ref.current;if(v&&v.srcObject!==stream){v.srcObject=stream;v.play().catch(()=>{})}},[stream]);
  return <div className={`rm-tile${self?' self':''}`} data-name={name}>
    <video ref={ref} autoPlay playsInline muted={muted} className={off?'hidden':''}/>
    {off&&<div className="rm-avatar">{(name||'?').trim().charAt(0).toUpperCase()}</div>}
    <span className="rm-name">{name}{self?' (you)':''}{host?' · host':''}{screen?' · sharing':''}</span>
  </div>;
}

export function RoomPage({code,api,token,defaultName,onLeave}:{code:string;api:string;token:string;defaultName:string;onLeave:()=>void}){
  const [info,setInfo]=useState<any>(null);const [err,setErr]=useState('');
  const [phase,setPhase]=useState<'lobby'|'waiting'|'room'|'ended'>('lobby');
  const [passcode,setPasscode]=useState('');const [waitList,setWaitList]=useState<{id:string;name:string}[]>([]);const [hostInfo,setHostInfo]=useState<any>(null);const [secOpen,setSecOpen]=useState(false);
  const [name,setName]=useState(defaultName||'');
  const [mic,setMic]=useState(true);const [cam,setCam]=useState(true);const [screen,setScreen]=useState(false);
  const [peers,setPeers]=useState<Record<string,Peer>>({});
  const [isHost,setIsHost]=useState(false);const [recording,setRecording]=useState(false);const [recBusy,setRecBusy]=useState(false);
  const [chat,setChat]=useState<{name:string;text:string;at:string;me?:boolean}[]>([]);const [chatOpen,setChatOpen]=useState(false);const [chatText,setChatText]=useState('');
  const [notice,setNotice]=useState('');const [localStream,setLocalStream]=useState<MediaStream|null>(null);const [mediaNote,setMediaNote]=useState('');
  const ws=useRef<WebSocket|null>(null);const pcs=useRef<Record<string,RTCPeerConnection>>({});const myId=useRef('');
  const local=useRef<{audio?:MediaStreamTrack;video?:MediaStreamTrack;cam?:MediaStreamTrack}>({});
  const iceRef=useRef<any[]>([]);const peerStreams=useRef<Record<string,MediaStream>>({});
  const rec=useRef<any>(null);const wasRecording=useRef(false);

  useEffect(()=>{fetch(`${api}/rooms/${code}`,{headers:token?{Authorization:`Bearer ${token}`}:{}}).then(async r=>{const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.detail||'This meeting link is not valid.');setInfo(j);iceRef.current=j.ice||[];if(j.ended)setPhase('ended')}).catch(e=>setErr(e.message))},[api,code]);

  // ---- local media ----
  const getMedia=useCallback(async()=>{
    let stream:MediaStream|null=null;
    try{stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:{width:{ideal:1280},height:{ideal:720}}})}
    catch{try{stream=await navigator.mediaDevices.getUserMedia({audio:true});setMediaNote('Camera not available - joining with microphone only.')}catch{setMediaNote('No camera or microphone available - you can still watch, listen and chat.')}}
    if(stream){local.current.audio=stream.getAudioTracks()[0];local.current.video=stream.getVideoTracks()[0];local.current.cam=local.current.video;setCam(!!local.current.video);setMic(!!local.current.audio)}else{setCam(false);setMic(false)}
    setLocalStream(stream);return stream;
  },[]);
  useEffect(()=>{if(phase==='lobby'&&info&&!localStream&&!err)getMedia()},[phase,info]);// preview in the lobby
  useEffect(()=>()=>{local.current.audio?.stop();local.current.cam?.stop();local.current.video?.stop()},[]);

  // ---- peer connections ----
  const send=(m:any)=>{if(ws.current?.readyState===1)ws.current.send(JSON.stringify(m))};
  const upsert=(id:string,patch:Partial<Peer>)=>setPeers(p=>({...p,[id]:{id,name:'Guest',stream:peerStreams.current[id],mic:true,cam:true,screen:false,...p[id],...patch}}));
  const makePc=(id:string)=>{
    if(pcs.current[id])return pcs.current[id];
    const pc=new RTCPeerConnection({iceServers:iceRef.current});pcs.current[id]=pc;
    peerStreams.current[id]=peerStreams.current[id]||new MediaStream();
    pc.onicecandidate=e=>{if(e.candidate)send({type:'signal',to:id,data:{candidate:e.candidate}})};
    pc.ontrack=e=>{const s=peerStreams.current[id];if(!s.getTracks().includes(e.track))s.addTrack(e.track);upsert(id,{stream:s});e.track.onunmute=()=>upsert(id,{});recorderRefresh()};
    pc.onconnectionstatechange=()=>{if(pc.connectionState==='failed')setNotice('A connection to another person failed. A TURN server may be needed on this network.')};
    return pc;
  };
  const attachLocal=async(pc:RTCPeerConnection)=>{
    for(const tx of pc.getTransceivers()){
      const kind=tx.receiver.track.kind;tx.direction='sendrecv';
      const t=kind==='audio'?local.current.audio:local.current.video;if(t)await tx.sender.replaceTrack(t);
    }
  };
  const callPeer=async(id:string)=>{ // we are the newcomer: we send the offer
    const pc=makePc(id);pc.addTransceiver('audio',{direction:'sendrecv'});pc.addTransceiver('video',{direction:'sendrecv'});
    await attachLocal(pc);const offer=await pc.createOffer();await pc.setLocalDescription(offer);send({type:'signal',to:id,data:{sdp:pc.localDescription}});
  };
  const onSignal=async(from:string,data:any)=>{
    const pc=makePc(from);
    if(data.sdp){
      await pc.setRemoteDescription(data.sdp);
      if(data.sdp.type==='offer'){await attachLocal(pc);const ans=await pc.createAnswer();await pc.setLocalDescription(ans);send({type:'signal',to:from,data:{sdp:pc.localDescription}})}
    }else if(data.candidate){try{await pc.addIceCandidate(data.candidate)}catch{}}
  };
  const dropPeer=(id:string)=>{pcs.current[id]?.close();delete pcs.current[id];delete peerStreams.current[id];setPeers(p=>{const n={...p};delete n[id];return n});recorderRefresh()};

  const authH:any={'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})};
  const loadHostInfo=()=>fetch(`${api}/rooms/${code}/host`,{headers:authH}).then(r=>r.ok?r.json():null).then(j=>j&&setHostInfo(j)).catch(()=>{});
  const changeSecurity=async(patch:any)=>{const r=await fetch(`${api}/rooms/${code}`,{method:'PATCH',headers:authH,body:JSON.stringify(patch)});if(r.ok)setHostInfo({...hostInfo,...(await r.json())});else setNotice('Could not change the meeting settings.')};
  const join=async()=>{
    setErr('');
    const sock=new WebSocket(wsUrl(api,code));ws.current=sock;
    sock.onopen=()=>send({type:'join',name:name.trim()||'Guest',token:token||undefined,passcode:passcode.trim()||undefined});
    sock.onmessage=async ev=>{
      const m=JSON.parse(ev.data);
      if(m.type==='waiting'){setPhase('waiting')}
      else if(m.type==='denied'){setErr('The host did not let you in.');setPhase('ended')}
      else if(m.type==='waiting-list'){setWaitList(m.list||[]);if((m.list||[]).length)setNotice(`${m.list[m.list.length-1].name} is waiting to join`)}
      else if(m.type==='welcome'){setWaitList(m.waiting||[]);if(m.host)loadHostInfo();myId.current=m.id;setIsHost(!!m.host);setRecording(!!m.recording);setPhase('room');for(const p of m.peers){upsert(p.id,{name:p.name,host:p.host});await callPeer(p.id)}send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.video?.enabled,screen:false})}
      else if(m.type==='peer-joined'){upsert(m.id,{name:m.name,host:m.host});setNotice(`${m.name} joined`);send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.video?.enabled,screen:false})}
      else if(m.type==='peer-left'){setPeers(p=>{if(p[m.id])setNotice(`${p[m.id].name} left`);return p});dropPeer(m.id)}
      else if(m.type==='signal')onSignal(m.from,m.data);
      else if(m.type==='state')upsert(m.id,{mic:m.mic,cam:m.cam,screen:m.screen});
      else if(m.type==='chat'){setChat(c=>[...c,{name:m.name,text:m.text,at:m.at,me:m.from===myId.current}]);setChatOpen(o=>{if(!o)setNotice(`${m.name}: ${m.text.slice(0,60)}`);return o})}
      else if(m.type==='recording'){setRecording(m.on);setNotice(m.on?'This meeting is now being recorded.':'Recording stopped.')}
      else if(m.type==='kicked'){leaveLocal();setErr('You were removed from the meeting by the host.');setPhase('ended')}
      else if(m.type==='ended'){leaveLocal();setPhase('ended')}
      else if(m.type==='error'){setErr(m.message);sock.close()}
    };
    sock.onclose=()=>{setPhase(p=>p==='room'||p==='waiting'?'ended':p)};
  };
  const leaveLocal=()=>{Object.keys(pcs.current).forEach(id=>{pcs.current[id].close();delete pcs.current[id]});local.current.audio?.stop();local.current.cam?.stop();local.current.video?.stop();ws.current?.close()};
  const leave=async()=>{if(rec.current)await stopRecording(false);leaveLocal();onLeave()};
  const endAll=async()=>{if(!window.confirm('End the meeting for everyone?'))return;if(rec.current)await stopRecording(true);send({type:'end'});leaveLocal();onLeave()};

  // ---- controls ----
  const toggleMic=()=>{const t=local.current.audio;if(!t)return;t.enabled=!t.enabled;setMic(t.enabled);send({type:'state',mic:t.enabled,cam:!!local.current.video?.enabled,screen})};
  const toggleCam=()=>{const t=local.current.cam;if(!t)return;t.enabled=!t.enabled;setCam(t.enabled);send({type:'state',mic:!!local.current.audio?.enabled,cam:t.enabled,screen})};
  const replaceVideo=async(track?:MediaStreamTrack)=>{for(const pc of Object.values(pcs.current)){const tx=pc.getTransceivers().find(x=>x.receiver.track.kind==='video');if(tx)await tx.sender.replaceTrack(track||null)}};
  const toggleScreen=async()=>{
    if(screen){await replaceVideo(local.current.cam);local.current.video=local.current.cam;setLocalStream(s=>s);setScreen(false);send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:false});return}
    try{const d=await (navigator.mediaDevices as any).getDisplayMedia({video:true});const t=d.getVideoTracks()[0];local.current.video=t;t.onended=()=>{replaceVideo(local.current.cam);local.current.video=local.current.cam;setScreen(false);send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:false})};await replaceVideo(t);setScreen(true);send({type:'state',mic:!!local.current.audio?.enabled,cam:!!local.current.cam?.enabled,screen:true})}catch{setNotice('Screen sharing was cancelled or is not available in this browser.')}
  };
  const sendChat=(e:React.FormEvent)=>{e.preventDefault();if(!chatText.trim())return;send({type:'chat',text:chatText});setChatText('')};
  const copyLink=async()=>{const link=`${location.origin}${location.pathname}#/room/${code}`;const txt=link+(hostInfo?.passcode?`\nPasscode: ${hostInfo.passcode}`:'')+`\nMeeting ID: ${code}`;try{await navigator.clipboard.writeText(txt);setNotice(hostInfo?.passcode?'Link and passcode copied.':'Invitation link copied.')}catch{setNotice(txt)}};

  // ---- recording (host only): audio mix for the transcript + composite video for the archive ----
  const gridRef=useRef<HTMLDivElement>(null);
  const recorderRefresh=()=>{const r=rec.current;if(!r)return;const have=new Set<string>(r.sources.keys());
    const streams:Record<string,MediaStream>={...peerStreams.current,__me:localStream||new MediaStream()};
    for(const [k,s] of Object.entries(streams)){const t=s.getAudioTracks()[0];if(t&&!have.has(k+t.id)){try{const src=r.ctx.createMediaStreamSource(new MediaStream([t]));src.connect(r.dest);r.sources.set(k+t.id,src)}catch{}}}};
  useEffect(()=>{if(!recording)return;const h=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',h);return()=>window.removeEventListener('beforeunload',h)},[recording]);
  const startRecording=async()=>{
    if(!isHost||rec.current)return;
    if(!window.confirm('Start recording? Everyone in the meeting is told it is being recorded. Keep this tab open while recording (it may stay in the background).'))return;
    const ctx=new AudioContext();const dest=ctx.createMediaStreamDestination();const r:any={ctx,dest,sources:new Map(),audioChunks:[],videoChunks:[]};rec.current=r;
    await ctx.resume().catch(()=>{});
    const canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;const g=canvas.getContext('2d')!;
    const draw=()=>{const vids=Array.from(gridRef.current?.querySelectorAll('video')||[]).filter(v=>!v.classList.contains('hidden')&&v.videoWidth>0) as HTMLVideoElement[];
      g.fillStyle='#10202c';g.fillRect(0,0,1280,720);const n=Math.max(1,vids.length);const cols=Math.ceil(Math.sqrt(n));const rows=Math.ceil(n/cols);const w=1280/cols,h=720/rows;
      vids.forEach((v,i)=>{const x=(i%cols)*w,y=Math.floor(i/cols)*h;const s=Math.min(w/v.videoWidth,h/v.videoHeight);const dw=v.videoWidth*s,dh=v.videoHeight*s;g.drawImage(v,x+(w-dw)/2,y+(h-dh)/2,dw,dh)})};
    try{const wk=new Worker(URL.createObjectURL(new Blob(['setInterval(()=>postMessage(0),66)'],{type:'text/javascript'})));wk.onmessage=draw;r.timer=wk}catch{r.timer=setInterval(draw,66)}
    recorderRefresh();
    const mk=(stream:MediaStream,mime:string,opts:any,sink:Blob[])=>{const mr=new MediaRecorder(stream,{mimeType:mime,...opts});mr.ondataavailable=e=>{if(e.data.size)sink.push(e.data)};mr.start(2000);return mr};
    r.audioRec=mk(dest.stream,'audio/webm;codecs=opus',{audioBitsPerSecond:32000},r.audioChunks);
    const vs=canvas.captureStream(15);dest.stream.getAudioTracks().forEach(t=>vs.addTrack(t));
    r.videoRec=mk(vs,MediaRecorder.isTypeSupported('video/webm;codecs=vp8,opus')?'video/webm;codecs=vp8,opus':'video/webm',{videoBitsPerSecond:1500000},r.videoChunks);
    send({type:'record',on:true});setRecording(true);wasRecording.current=true;
  };
  const stopRecording=async(_ending?:boolean)=>{
    const r=rec.current;if(!r)return;rec.current=null;setRecBusy(true);
    const stopOne=(mr:MediaRecorder)=>new Promise<void>(res=>{mr.onstop=()=>res();try{mr.stop()}catch{res()}});
    await Promise.all([stopOne(r.audioRec),stopOne(r.videoRec)]);(typeof r.timer?.terminate==='function'?r.timer.terminate():clearInterval(r.timer));r.ctx.close().catch(()=>{});
    send({type:'record',on:false});setRecording(false);
    try{
      const form=new FormData();form.append('consent_acknowledged','true');
      form.append('audio',new Blob(r.audioChunks,{type:'audio/webm'}),'speech.webm');
      if(r.videoChunks.length)form.append('video',new Blob(r.videoChunks,{type:'video/webm'}),'meeting.webm');
      const res=await fetch(`${api}/rooms/${code}/recording`,{method:'POST',headers:{Authorization:`Bearer ${token}`},body:form});const j=await res.json().catch(()=>({}));
      setNotice(res.ok?j.message:(j.detail||'The recording could not be saved.'));
    }catch{setNotice('The recording could not be uploaded. Check the connection.')}finally{setRecBusy(false)}
  };
  useEffect(()=>{if(notice){const t=setTimeout(()=>setNotice(''),6000);return()=>clearTimeout(t)}},[notice]);

  // ---------- views ----------
  if(err&&phase!=='ended'&&!info)return <div className="rm-center"><div className="rm-card"><h1>Meeting not available</h1><p>{err}</p><button className="primary" onClick={onLeave}>Back to the app</button></div></div>;
  if(phase==='ended')return <div className="rm-center"><div className="rm-card"><h1>{err?'You left the meeting':'This meeting has ended'}</h1><p>{err||'Thanks for joining.'}</p><button className="primary" onClick={onLeave}>{token?'Back to the app':'Close'}</button></div></div>;
  if(!info)return <div className="rm-center"><div className="rm-card">Loading…</div></div>;
  if(phase==='lobby')return <div className="rm-center"><div className="rm-card lobby">
    <h1>{info.title}</h1><p className="muted">Hosted by {info.host||'the organizer'} · {info.people_now} {info.people_now===1?'person':'people'} in the meeting</p>
    <div className="rm-preview"><VideoTile stream={localStream} name={name||'You'} muted off={!cam||!localStream?.getVideoTracks().length} self/></div>
    {mediaNote&&<p className="muted">{mediaNote}</p>}
    <label>Your name<input value={name} onChange={e=>setName(e.target.value)} maxLength={60} placeholder="Your name" autoFocus/></label>
    {info.access==='passcode'&&!info.you_are_host&&<label>Meeting passcode<input value={passcode} onChange={e=>setPasscode(e.target.value)} maxLength={12} placeholder="Passcode from your invitation" autoComplete="off"/></label>}
    {info.access==='signed_in'&&!info.signed_in&&<p className="syncerr" role="alert">This meeting is only open to people with an account. Sign in, then open the link again.</p>}
    {info.waiting_room&&!info.you_are_host&&<p className="muted small">The host will let you in when they are ready.</p>}
    <div className="rm-lobbyctl"><button type="button" className={`secondary${!mic?' off':''}`} onClick={toggleMic} disabled={!local.current.audio}>{mic?<Mic size={16}/>:<MicOff size={16}/>} {mic?'Mic on':'Mic off'}</button><button type="button" className={`secondary${!cam?' off':''}`} onClick={toggleCam} disabled={!local.current.cam}>{cam?<Video size={16}/>:<VideoOff size={16}/>} {cam?'Camera on':'Camera off'}</button></div>
    <p className="muted small">The host may record this meeting. You will see a clear “Recording” banner if they do, and you can leave at any time.</p>
    {err&&<p className="syncerr" role="alert">{err}</p>}
    <button className="primary join" onClick={join} disabled={!name.trim()||(info.access==="passcode"&&!info.you_are_host&&passcode.trim().length<4)||(info.access==="signed_in"&&!info.signed_in)}>{info.waiting_room&&!info.you_are_host?"Ask to join":"Join meeting"}</button>
  </div></div>;
  if(phase==='waiting')return <div className="rm-center"><div className="rm-card"><h1>Waiting for the host</h1><p>The host will let you in shortly. You can leave this page at any time.</p><button className="secondary" onClick={()=>{ws.current?.close();onLeave()}}>Cancel</button></div></div>;
  const list=Object.values(peers);const tiles=list.length+1;
  return <div className="rm-shell">
    <header className="rm-top"><b>{info.title}</b>{recording&&<span className="rm-rec"><Circle size={10} fill="currentColor"/> Recording</span>}<span className="muted"><Users size={14}/> {tiles}</span>{notice&&<span className="rm-notice" role="status">{notice}</span>}</header>
    {isHost&&waitList.length>0&&<div className="rm-wait" role="region" aria-label="People waiting"><b>Waiting to join</b>{waitList.map(w=><div key={w.id} className="rm-waitrow"><span>{w.name}</span><button className="primary" onClick={()=>send({type:'admit',id:w.id})}>Admit</button><button className="secondary" onClick={()=>send({type:'deny',id:w.id})}>Deny</button></div>)}{waitList.length>1&&<button className="secondary" onClick={()=>send({type:'admit_all'})}>Admit all</button>}</div>}
    {isHost&&secOpen&&hostInfo&&<div className="rm-sec" role="dialog" aria-label="Meeting security"><b>Who can join</b>
      <label><input type="radio" name="acc" checked={hostInfo.access==='open'} onChange={()=>changeSecurity({access:'open'})}/> Anyone with the link</label>
      <label><input type="radio" name="acc" checked={hostInfo.access==='passcode'} onChange={()=>changeSecurity({access:'passcode'})}/> Link and passcode{hostInfo.passcode&&hostInfo.access==='passcode'?<> · <b>{hostInfo.passcode}</b></>:null}</label>
      <label><input type="radio" name="acc" checked={hostInfo.access==='signed_in'} onChange={()=>changeSecurity({access:'signed_in'})}/> Signed-in people only</label>
      <label><input type="checkbox" checked={!!hostInfo.waiting_room} onChange={e=>changeSecurity({waiting_room:e.target.checked})}/> Waiting room</label>
      <small className="muted">Changes apply to people who join from now on.</small><button className="secondary" onClick={()=>setSecOpen(false)}>Close</button></div>}
    <div className="rm-main"><div ref={gridRef} className={`rm-grid n${Math.min(tiles,9)}`}>
      <VideoTile stream={localStream} name={name||'You'} muted off={!cam&&!screen} self host={isHost} screen={screen}/>
      {list.map(p=><div key={p.id} className="rm-wrap">
        <VideoTile stream={p.stream||null} name={p.name} off={!p.cam&&!p.screen} host={p.host} screen={p.screen}/>
        {!p.mic&&<span className="rm-muted" title="Muted"><MicOff size={13}/></span>}
        {isHost&&<button className="rm-kick" title={`Remove ${p.name}`} onClick={()=>window.confirm(`Remove ${p.name} from the meeting?`)&&send({type:'kick',id:p.id})}><UserX size={14}/></button>}
      </div>)}
    </div>
    {chatOpen&&<aside className="rm-chat"><div className="rm-chathead"><b>Chat</b><button className="iconbtn" onClick={()=>setChatOpen(false)} aria-label="Close chat"><X size={16}/></button></div>
      <div className="rm-msgs">{chat.map((c,i)=><div key={i} className={`rm-msg${c.me?' me':''}`}><b>{c.me?'You':c.name}</b><p>{c.text}</p></div>)}{!chat.length&&<p className="muted">No messages yet.</p>}</div>
      <form onSubmit={sendChat}><input value={chatText} onChange={e=>setChatText(e.target.value)} placeholder="Message everyone" maxLength={2000}/><button className="primary" aria-label="Send"><Send size={15}/></button></form></aside>}
    </div>
    <footer className="rm-bar">
      <button className={`rm-btn${!mic?' off':''}`} onClick={toggleMic} disabled={!local.current.audio} aria-label={mic?'Mute microphone':'Unmute microphone'}>{mic?<Mic size={18}/>:<MicOff size={18}/>}<span>{mic?'Mute':'Unmute'}</span></button>
      <button className={`rm-btn${!cam?' off':''}`} onClick={toggleCam} disabled={!local.current.cam} aria-label={cam?'Turn camera off':'Turn camera on'}>{cam?<Video size={18}/>:<VideoOff size={18}/>}<span>{cam?'Camera':'Camera off'}</span></button>
      <button className={`rm-btn${screen?' on':''}`} onClick={toggleScreen} aria-label="Share screen"><MonitorUp size={18}/><span>{screen?'Stop sharing':'Share'}</span></button>
      <button className={`rm-btn${chatOpen?' on':''}`} onClick={()=>setChatOpen(o=>!o)} aria-label="Chat"><MessageSquare size={18}/><span>Chat</span></button>
      <button className="rm-btn" onClick={copyLink} aria-label="Copy invitation link"><Link2 size={18}/><span>Invite</span></button>
      {isHost&&<button className={`rm-btn${secOpen?' on':''}`} onClick={()=>{loadHostInfo();setSecOpen(o=>!o)}} aria-label="Meeting security"><ShieldCheck size={18}/><span>Security</span></button>}
      {isHost&&(recording?<button className="rm-btn rec" disabled={recBusy} onClick={()=>stopRecording()} aria-label="Stop recording"><Square size={18}/><span>{recBusy?'Saving…':'Stop rec'}</span></button>:<button className="rm-btn" onClick={startRecording} aria-label="Start recording"><Circle size={18}/><span>Record</span></button>)}
      <button className="rm-btn leave" onClick={leave} aria-label="Leave meeting"><PhoneOff size={18}/><span>Leave</span></button>
      {isHost&&<button className="rm-btn leave" onClick={endAll} aria-label="End meeting for everyone"><X size={18}/><span>End all</span></button>}
    </footer>
  </div>;
}
