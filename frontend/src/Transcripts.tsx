import React,{useMemo,useState} from 'react';
import {Copy,Check,Search,FileText,Mic,Upload} from 'lucide-react';

const COLORS=['#2f6f8f','#5b7f3a','#8a5a9a','#b06a2c','#2f7f6f','#9a4a5a'];
const mmss=(s:number|null|undefined)=>{if(s==null||isNaN(Number(s)))return '';const t=Math.max(0,Math.round(Number(s)));return `${String(Math.floor(t/60)).padStart(2,'0')}:${String(t%60).padStart(2,'0')}`};
const dayOf=(d:string)=>{try{return new Date(d).toLocaleString(undefined,{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}catch{return ''}};

export function TranscriptsPage({meetings,selected,transcript,onView,onFetch,onUpload}:{meetings:any[];selected:string|null;transcript:any;onView:(id:string)=>void;onFetch:(id:string)=>void;onUpload:(id:string,f:File)=>void}){
  const [q,setQ]=useState('');const [copied,setCopied]=useState(false);
  const ready=meetings.filter(m=>m.transcript_status==='ready');
  const pending=meetings.filter(m=>m.transcript_status!=='ready');
  const segs:any[]=transcript?.segments||[];
  const speakers=useMemo(()=>{const o:Record<string,number>={};segs.forEach(s=>{const k=s.speaker||'Unknown';if(!(k in o))o[k]=Object.keys(o).length});return o},[segs]);
  const needle=q.trim().toLowerCase();
  const shown=needle?segs.filter(s=>(s.text||'').toLowerCase().includes(needle)||(s.speaker||'').toLowerCase().includes(needle)):segs;
  const paras=(transcript?.full_text||'').split(/\n{2,}|\n/).map((x:string)=>x.trim()).filter(Boolean);
  const current=meetings.find(m=>m.id===selected);
  const asText=()=>segs.length?segs.map(s=>`${s.speaker||'Unknown'}${s.start_seconds!=null?` [${mmss(s.start_seconds)}]`:''}: ${s.text}`).join('\n'):(transcript?.full_text||'');
  const copy=async()=>{try{await navigator.clipboard.writeText(asText());setCopied(true);setTimeout(()=>setCopied(false),1800)}catch{}};
  return <div className="tr-wrap">
    <aside className="tr-list panel">
      <div className="panelhead"><h2>Meetings with a transcript</h2><span className="tr-count">{ready.length}</span></div>
      {ready.length?ready.map(m=><button type="button" key={m.id} className={`tr-item${m.id===selected?' active':''}`} onClick={()=>onView(m.id)}><b>{m.title}</b><small>{dayOf(m.start_at)}</small></button>):<p className="tr-empty">No transcripts yet. Use the actions below, or load mock data.</p>}
    </aside>
    <section className="tr-main panel">
      {transcript?<>
        <div className="panelhead tr-head"><div><h2>{current?.title||'Transcript'}</h2><small>{current?dayOf(current.start_at):''} · {transcript.source_type} · {segs.length||paras.length} {segs.length?'lines':'paragraphs'}</small></div>
          <button className="secondary" type="button" onClick={copy}>{copied?<Check size={15}/>:<Copy size={15}/>} {copied?'Copied':'Copy text'}</button></div>
        {segs.length>0&&<div className="tr-tools"><label className="tr-search"><Search size={15}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search this transcript"/></label>
          <div className="tr-legend">{Object.keys(speakers).map(n=><span key={n}><i style={{background:COLORS[speakers[n]%COLORS.length]}}/>{n}</span>)}</div></div>}
        {segs.length?<div className="tr-lines">{shown.map((s,i)=>{const n=s.speaker||'Unknown';const c=COLORS[speakers[n]%COLORS.length];return <div className="tr-line" key={s.id||i}><span className="tr-av" style={{background:c}}>{n.trim().charAt(0).toUpperCase()}</span><div><div className="tr-meta"><b style={{color:c}}>{n}</b>{s.start_seconds!=null&&<time>{mmss(s.start_seconds)}</time>}</div><p>{s.text}</p></div></div>})}{!shown.length&&<p className="tr-empty">Nothing matches “{q}”.</p>}</div>
          :<div className="tr-lines">{paras.map((p:string,i:number)=><p className="tr-para" key={i}>{p}</p>)}{!paras.length&&<p className="tr-empty">This transcript is empty.</p>}</div>}
      </>:<div className="tr-blank"><FileText size={28}/><h2>{ready.length?'Pick a meeting':'No transcripts yet'}</h2><p>{ready.length?'Choose a meeting on the left to read its transcript line by line.':'Official transcripts appear after a meeting ends, or you can upload an authorized recording below.'}</p></div>}
    </section>
    <section className="tr-pending panel">
      <div className="panelhead"><h2>Meetings without a transcript</h2><span className="tr-count">{pending.length}</span></div>
      {pending.length?pending.map(m=><div className="tr-prow" key={m.id}><div><b>{m.title}</b><small>{dayOf(m.start_at)} · {String(m.transcript_status).replaceAll('_',' ')}</small></div>
        <div className="tr-acts"><button className="secondary" type="button" onClick={()=>onFetch(m.id)}><Mic size={14}/> Fetch official transcript</button>
        <label className="secondary tr-up"><Upload size={14}/> Upload audio<input type="file" accept="audio/*,video/*" hidden onChange={e=>{const f=e.target.files?.[0];if(f)onUpload(m.id,f);e.target.value=''}}/></label></div></div>):<p className="tr-empty">Every meeting has a transcript.</p>}
    </section>
  </div>;
}
