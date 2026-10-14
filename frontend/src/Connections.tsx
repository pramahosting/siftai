import React,{useEffect,useState} from 'react';
import {Link2,Trash2,RefreshCw,Video,CalendarPlus,CheckCircle2,AlertTriangle,Upload,Plus} from 'lucide-react';

export const PROVIDER_LABEL:Record<string,string>={room:'Meeting room',zoom:'Zoom',teams:'Teams',meet:'Google Meet',webex:'Webex'};
export function providerOf(url?:string|null){
  if(!url)return null;let h='';try{h=new URL(url).hostname.toLowerCase()}catch{return null}
  try{const u=new URL(url);if(u.hash.startsWith('#/room/'))return 'room'}catch{}
  const is=(s:string)=>h===s||h.endsWith('.'+s);
  if(is('zoom.us')||is('zoomgov.com'))return 'zoom';if(is('teams.microsoft.com')||is('teams.live.com'))return 'teams';
  if(is('meet.google.com'))return 'meet';if(is('webex.com'))return 'webex';return null;
}
export function JoinButton({url,small}:{url?:string|null;small?:boolean}){
  const p=providerOf(url);if(!url||!p)return null;
  const same=p==='room'&&(()=>{try{return new URL(url).origin===location.origin}catch{return false}})();
  return <a className={`joinbtn${small?' small':''}`} href={url} target={same?undefined:'_blank'} rel="noopener noreferrer" title={`Join ${PROVIDER_LABEL[p]} meeting`} aria-label={`Join ${PROVIDER_LABEL[p]} meeting`} onClick={e=>{e.stopPropagation();if(same){e.preventDefault();location.hash=new URL(url).hash}}}><Video size={14}/> {small?'Join':`Join ${PROVIDER_LABEL[p]}`}</a>;
}

export function suggestFor(email:string):{choice:string;label:string}{
  const d=(email.split('@')[1]||'').toLowerCase();
  if(/^(gmail|googlemail)\.com$/.test(d))return {choice:'ics:google',label:'Google / Gmail'};
  if(/^(yahoo\.|ymail\.|rocketmail\.)/.test(d))return {choice:'caldav:yahoo',label:'Yahoo'};
  if(/^(outlook|hotmail|live|msn)\./.test(d))return {choice:'ics:outlook',label:'Outlook.com / Microsoft'};
  if(/^(icloud|me|mac)\.com$/.test(d))return {choice:'caldav:icloud',label:'Apple iCloud'};
  if(/fastmail\./.test(d))return {choice:'caldav:fastmail',label:'Fastmail'};
  if(d)return {choice:'ics:outlook',label:'Work / other (often Microsoft 365)'};
  return {choice:'ics:google',label:''};
}

function MailPanel({info,request,run,busy}:{info:any;request:any;run:(f:()=>Promise<any>)=>void;busy:boolean}){
  const [prov,setProv]=useState('gmail');const [addr,setAddr]=useState('');const [pw,setPw]=useState('');const [imp,setImp]=useState(true);
  const [sh,setSh]=useState('');const [sp,setSp]=useState('587');const [ih,setIh]=useState('');const [ip,setIp]=useState('993');
  const pre=info.mail_presets.find((p:any)=>p.id===prov);const m=info.mail;
  const guess=(a:string)=>{setAddr(a);const d=(a.split('@')[1]||'').toLowerCase();setProv(/^(gmail|googlemail)\./.test(d)?'gmail':/^yahoo\.|^ymail\./.test(d)?'yahoo':/^(outlook|hotmail|live|msn)\./.test(d)?'outlook':/^(icloud|me|mac)\.com$/.test(d)?'icloud':prov)};
  return <section className="panel">
    <div className="panelhead"><h2>Your mail account</h2><span className="muted">Send meeting invitations; pick up invitations from your inbox</span></div>
    {m?<div className="conn-row"><div>{m.ok===false?<AlertTriangle size={16} className="bad"/>:<CheckCircle2 size={16} className="good"/>}</div>
      <div className="grow"><b>{m.address}</b><small>{m.import_invites?'Sends invitations and reads calendar invitations from the inbox (mail is never stored)':'Sends invitations'}{m.error?` · ${m.error}`:''}</small></div>
      <button className="secondary" disabled={busy} onClick={()=>run(()=>request('/connections/mail/test',{method:'POST'}))}>Send test</button>
      <button className="iconbtn" title="Disconnect" disabled={busy} onClick={()=>window.confirm('Disconnect this mail account?')&&run(()=>request('/connections/mail',{method:'DELETE'}))}><Trash2 size={16}/></button></div>
    :<form className="conn-form" onSubmit={e=>{e.preventDefault();run(()=>request('/connections/mail',{method:'POST',body:JSON.stringify({provider:prov,address:addr,password:pw,import_invites:imp,smtp_host:sh||undefined,smtp_port:sp,imap_host:ih||undefined,imap_port:ip})}).then(r=>{setPw('');return r}))}}>
      <label>Email address<input type="email" value={addr} onChange={e=>guess(e.target.value)} placeholder="name@gmail.com" required autoComplete="off"/></label>
      <label>Provider<select value={prov} onChange={e=>setProv(e.target.value)}>{info.mail_presets.map((p:any)=><option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
      <label className="span2">App password<input type="password" value={pw} onChange={e=>setPw(e.target.value)} autoComplete="new-password" required/></label>
      {prov==='other'&&<><label>Sending server (SMTP)<input value={sh} onChange={e=>setSh(e.target.value)} required/></label><label>Port<input value={sp} onChange={e=>setSp(e.target.value)}/></label><label>Reading server (IMAP)<input value={ih} onChange={e=>setIh(e.target.value)}/></label><label>Port<input value={ip} onChange={e=>setIp(e.target.value)}/></label></>}
      <label className="checklabel span2"><input type="checkbox" checked={imp} onChange={e=>setImp(e.target.checked)}/> Also add meeting invitations I receive in this inbox to my calendar (only the calendar data is read; mail is not stored or marked as read)</label>
      {pre?.how&&<p className="muted span2"><b>Where to get the app password:</b> {pre.how}</p>}
      <div className="actions span2"><button className="primary" disabled={busy||!addr||!pw}><Plus size={15}/> {busy?'Checking…':'Connect mail account'}</button></div>
    </form>}
  </section>;
}

export function ConnectionsPage({request,isAdmin,onChanged,goSettings,onUploadIcs,notify}:{request:any;isAdmin:boolean;onChanged:()=>void;goSettings:()=>void;onUploadIcs:(f:File)=>Promise<void>;notify:(m:string)=>void}){
  const [info,setInfo]=useState<any>(null);const [choice,setChoice]=useState('ics:google');const [email,setEmail]=useState('');const [url,setUrl]=useState('');const [label,setLabel]=useState('');
  const [user,setUser]=useState('');const [pw,setPw]=useState('');const [busy,setBusy]=useState(false);const [err,setErr]=useState('');
  const load=async()=>{try{setInfo(await request('/connections'))}catch(e:any){setErr(e.message)}};
  useEffect(()=>{load()},[]);
  const run=async(fn:()=>Promise<any>)=>{setBusy(true);setErr('');try{const r=await fn();if(r?.message)notify(r.message);await load();onChanged()}catch(e:any){setErr(e.message)}finally{setBusy(false)}};
  if(!info)return <section className="panel">{err||'Loading…'}</section>;
  const [mode,pid]=choice.split(':');const caldav=mode==='caldav';
  const preset=caldav?info.caldav_presets.find((p:any)=>p.id===pid):info.providers.find((p:any)=>p.id===pid);
  const pick=(em:string)=>{setEmail(em);const s=suggestFor(em);if(em.includes('@')){setChoice(s.choice);setUser(em)}};
  const comp=info.computer||{};
  const submit=(e:React.FormEvent)=>{e.preventDefault();run(async()=>{
    const r=caldav?await request('/connections/caldav',{method:'POST',body:JSON.stringify({provider:pid,label:label||email,url:pid==='other'?url:preset?.url,username:user,password:pw})})
      :await request('/connections/calendar-links',{method:'POST',body:JSON.stringify({provider:pid,label:label||email,url})});
    setUrl('');setPw('');setLabel('');setEmail('');return r})};
  return <div className="conn">
    {(comp.note||comp.outlook_accounts?.length>0||comp.in_use)&&<section className="panel">
      <div className="panelhead"><h2>Outlook on this computer</h2></div>
      {comp.in_use&&<p className="muted"><CheckCircle2 size={14} className="good"/> Reading {comp.source}.{comp.outlook_accounts?.length>0&&<> Accounts: {comp.outlook_accounts.join(', ')}.</>}</p>}
      {comp.note&&<p className="note-box">{comp.note}</p>}
    </section>}
    <section className="panel">
      <div className="panelhead"><h2>Add a calendar account</h2><span className="muted">Gmail, Yahoo, Outlook.com, iCloud, work accounts</span></div>
      <p className="muted">Type the email address of an account you use in Outlook and this page picks the right method. Meetings for the next 7 days are added and refreshed automatically; Zoom, Teams, Meet and Webex links become Join buttons.</p>
      {info.links.length>0&&<div className="conn-list">{info.links.map((l:any)=><div className="conn-row" key={l.id}>
        <div>{l.ok===false?<AlertTriangle size={16} className="bad"/>:<CheckCircle2 size={16} className="good"/>}</div>
        <div className="grow"><b>{l.label}</b><small>{l.kind==='caldav'?'CalDAV · ':''}{l.host}{l.error?` · ${l.error}`:l.at?` · checked ${new Date(l.at).toLocaleString()}`:''}</small></div>
        <button className="iconbtn" title="Remove this calendar" disabled={busy} onClick={()=>window.confirm('Remove this calendar? Meetings already added stay.')&&run(()=>request(`/connections/calendar-links/${l.id}`,{method:'DELETE'}))}><Trash2 size={16}/></button></div>)}
        <button className="secondary" disabled={busy} onClick={()=>run(()=>request('/connections/sync',{method:'POST'}))}><RefreshCw size={15}/> Refresh now</button></div>}
      <form className="conn-form" onSubmit={submit}>
        <label className="span2">Email address of the account<input type="email" value={email} onChange={e=>pick(e.target.value)} placeholder="name@gmail.com" autoComplete="off"/>{email.includes('@')&&<small className="muted">Suggested method: {suggestFor(email).label}</small>}</label>
        <label>Method<select value={choice} onChange={e=>setChoice(e.target.value)}>
          <optgroup label="Private calendar link">{info.providers.map((p:any)=><option key={p.id} value={`ics:${p.id}`}>{p.label}</option>)}</optgroup>
          <optgroup label="Sign in with an app password (CalDAV)">{info.caldav_presets.map((p:any)=><option key={p.id} value={`caldav:${p.id}`}>{p.label}</option>)}</optgroup></select></label>
        <label>Name (optional)<input value={label} onChange={e=>setLabel(e.target.value)} placeholder="e.g. Work Gmail" maxLength={80}/></label>
        {caldav?<>
          {pid==='other'&&<label className="span2">CalDAV server address<input value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://…" required/></label>}
          <label>Username<input value={user} onChange={e=>setUser(e.target.value)} autoComplete="off" required/></label>
          <label>App password<input type="password" value={pw} onChange={e=>setPw(e.target.value)} autoComplete="new-password" required/></label>
        </>:<label className="span2">Calendar link<input value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://… or webcal://…" inputMode="url" autoComplete="off" required/></label>}
        {preset?.how&&<p className="muted span2"><b>Where to find it:</b> {preset.how}</p>}
        <div className="actions span2"><button className="primary" disabled={busy||(caldav?!(user&&pw):!url.trim())}><Plus size={15}/> {busy?'Checking…':'Add calendar'}</button>
          <label className="secondary cal-up"><Upload size={15}/> Upload .ics file instead<input type="file" accept=".ics,.ical,text/calendar" hidden disabled={busy} onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)run(async()=>{await onUploadIcs(f)})}}/></label></div>
        <p className="muted span2 small">Links and passwords work like keys: they are stored encrypted, never shown again, and only used to read your calendar. Remove them any time. Use an app password, never your main account password.</p>
      </form>
      {err&&<p className="syncerr" role="alert">{err}</p>}
      {info.uploaded&&<p className="muted">An uploaded calendar file is also in use.</p>}
    </section>
    <MailPanel info={info} request={request} run={run} busy={busy}/>
    <section className="panel">
      <div className="panelhead"><h2>Meeting apps</h2></div>
      <div className="conn-row"><div><Video size={18}/></div><div className="grow"><b>Zoom</b><small>{info.zoom.configured?'Connected: new Zoom meetings can be created here and official transcripts fetched after a meeting (Zoom cloud recording with audio transcript must be on).':'Not set up yet. Zoom links in your calendar still show a Join button.'}</small></div>
        {isAdmin?<>{info.zoom.configured&&<button className="secondary" disabled={busy} onClick={()=>run(()=>request('/connections/zoom/test',{method:'POST'}))}>Test</button>}<button className="secondary" onClick={goSettings}>{info.zoom.configured?'Edit':'Set up'}</button></>:!info.zoom.configured&&<small className="muted">Ask an administrator.</small>}</div>
      <div className="conn-row"><div><Video size={18}/></div><div className="grow"><b>Meeting rooms in this app</b><small>Start a video meeting from the Meetings page. Share the link; guests join in any browser, with chat, screen sharing and optional recording.</small></div></div>
      <div className="conn-row"><div><Video size={18}/></div><div className="grow"><b>Microsoft Teams / Microsoft 365</b><small>{info.microsoft.configured?'Connected through Microsoft 365 (calendar and official transcripts).':'Not set up. An administrator can add it in Admin settings > Microsoft Entra and Graph.'}</small></div></div>
      <div className="conn-row"><div><Video size={18}/></div><div className="grow"><b>Google Meet and Webex</b><small>Join links in your calendar events are recognised.</small></div></div>
    </section>
  </div>;
}

export function JoinById({className=''}:{className?:string}){
  const [v,setV]=useState('');const [bad,setBad]=useState(false);
  const go=(e:React.FormEvent)=>{e.preventDefault();const m=v.match(/#\/room\/([A-Za-z0-9]{6,40})/)||v.trim().match(/^([A-Za-z0-9]{6,40})$/);if(!m){setBad(true);return}setBad(false);location.hash='#/room/'+m[1]};
  return <form className={`joinbyid ${className}`} onSubmit={go} aria-label="Join a meeting"><input value={v} onChange={e=>{setV(e.target.value);setBad(false)}} placeholder="Meeting ID or link" aria-label="Meeting ID or link" aria-invalid={bad}/><button className="secondary">Join</button>{bad&&<small className="syncerr" role="alert">Enter the meeting ID or the full link.</small>}</form>;
}

export function NewMeeting({request,zoomReady,onCreated,onCancel}:{request:any;zoomReady:boolean;onCreated:(m:string)=>void;onCancel:()=>void}){
  const pad=(n:number)=>String(n).padStart(2,'0');const d=new Date(Date.now()+3600e3);d.setMinutes(0,0,0);
  const [title,setTitle]=useState('');const [when,setWhen]=useState(`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`);
  const [dur,setDur]=useState(30);const [kind,setKind]=useState(zoomReady?'zoom':'room');const [link,setLink]=useState('');const [agenda,setAgenda]=useState('');const [invite,setInvite]=useState('');const [access,setAccess]=useState('');const [waiting,setWaiting]=useState(true);const [pcode,setPcode]=useState('');const [busy,setBusy]=useState(false);const [err,setErr]=useState('');
  const submit=async(e:React.FormEvent)=>{e.preventDefault();setBusy(true);setErr('');try{const body:any={title,start_at:new Date(when).toISOString(),duration_minutes:dur,agenda,invite};if(kind==='zoom')body.provider='zoom';else if(kind==='room'){body.provider='room';body.base_url=location.origin+location.pathname;if(access)body.access=access;body.waiting_room=waiting;if(access==='passcode'&&pcode.trim())body.passcode=pcode.trim()}else if(kind==='link')body.join_url=link;const r=await request('/meetings',{method:'POST',body:JSON.stringify(body)});onCreated(r.message+(r.passcode?` Passcode: ${r.passcode}.`:''))}catch(x:any){setErr(x.message)}finally{setBusy(false)}};
  return <form className="panel newmeeting conn-form" onSubmit={submit}>
    <div className="panelhead span2"><h2><CalendarPlus size={18}/> New meeting</h2></div>
    <label className="span2">Title<input value={title} onChange={e=>setTitle(e.target.value)} required maxLength={200} autoFocus/></label>
    <label>Starts<input type="datetime-local" value={when} onChange={e=>setWhen(e.target.value)} required/></label>
    <label>Length<select value={dur} onChange={e=>setDur(Number(e.target.value))}>{[15,30,45,60,90,120].map(m=><option key={m} value={m}>{m} minutes</option>)}</select></label>
    <label>Online meeting<select value={kind} onChange={e=>setKind(e.target.value)}><option value="none">No link</option><option value="room">Built-in video meeting (this app)</option>{zoomReady&&<option value="zoom">Create a Zoom meeting</option>}<option value="link">I have a Zoom / Teams / Meet link</option></select></label>
    {kind==='room'&&<><label>Who can join<select value={access} onChange={e=>setAccess(e.target.value)}><option value="">Administrator's default</option><option value="open">Anyone with the link</option><option value="passcode">Link and passcode</option><option value="signed_in">Signed-in people only</option></select></label>
      <label className="check"><input type="checkbox" checked={waiting} onChange={e=>setWaiting(e.target.checked)}/> Waiting room (I admit people)</label>
      {access==='passcode'&&<label>Passcode (optional)<input value={pcode} onChange={e=>setPcode(e.target.value)} maxLength={12} placeholder="Leave blank to make one"/></label>}</>}
    {kind==='link'&&<label>Meeting link<input value={link} onChange={e=>setLink(e.target.value)} placeholder="https://…" required/></label>}
    {!zoomReady&&<p className="muted span2 small">To create Zoom meetings from here, an administrator sets Zoom up in Admin settings.</p>}
    <label className="span2">Invite people (optional)<input value={invite} onChange={e=>setInvite(e.target.value)} placeholder="name@example.com, other@example.com"/><small className="muted">They get a normal calendar invitation from your connected mail account (Connections page).</small></label>
    <label className="span2">Agenda (optional)<textarea rows={3} value={agenda} onChange={e=>setAgenda(e.target.value)} maxLength={2000}/></label>
    {err&&<p className="syncerr span2" role="alert">{err}</p>}
    <div className="actions span2"><button className="primary" disabled={busy||!title.trim()}>{busy?'Creating…':'Create meeting'}</button><button type="button" className="secondary" onClick={onCancel}>Cancel</button></div>
  </form>;
}

export function RecordingsPanel({request,download,refreshKey}:{request:any;download:(p:string,n:string)=>void;refreshKey:number}){
  const [rows,setRows]=useState<any[]>([]);
  const load=()=>request('/recordings').then(setRows).catch(()=>{});
  useEffect(()=>{load()},[refreshKey]);
  if(!rows.length)return null;
  const mb=(n:number)=>n>=1048576?`${(n/1048576).toFixed(1)} MB`:`${Math.max(1,Math.round(n/1024))} KB`;
  return <section className="panel"><div className="panelhead"><h2>Meeting recordings</h2><span className="muted">Only you, the host, can see these</span></div>
    {rows.map(r=><div className="conn-row" key={r.id}><div><Video size={16}/></div><div className="grow"><b>{r.title}</b><small>{new Date(r.created_at).toLocaleString()} · {r.has_video?'video':'audio'} · {mb(r.size_bytes)}</small></div>
      <button className="secondary" onClick={()=>download(`/recordings/${r.id}/file`,`${r.title||'meeting'}.webm`)}>Download</button>
      <button className="iconbtn" title="Delete recording" onClick={()=>window.confirm('Delete this recording permanently?')&&request(`/recordings/${r.id}`,{method:'DELETE'}).then(load)}><Trash2 size={16}/></button></div>)}
  </section>;
}
