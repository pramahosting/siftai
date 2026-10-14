import React,{useState} from 'react';
import {Copy,Pencil,Save,CheckCircle2,Plus,X,Quote,User as UserIcon,CalendarDays} from 'lucide-react';

const STATUS:Record<string,[string,string]>={draft:['Draft · needs review','amber'],reviewed:['Reviewed','green'],approved:['Approved','green'],superseded:['Replaced by a newer version','']};
const PRIORITY:Record<string,string>={low:'Low',normal:'Normal',high:'High',urgent:'Urgent'};
const list=(v:any):string[]=>Array.isArray(v)?v.map(x=>String(x??'').trim()).filter(Boolean):[];
const niceDue=(v:string)=>{if(!v)return '';if(/^\d{4}-\d{2}-\d{2}$/.test(v)){try{return new Date(v+'T12:00:00').toLocaleDateString(undefined,{weekday:'short',day:'numeric',month:'short'})}catch{}}return v};

export function minutesToText(c:any,title=''):string{
 const out:string[]=[];if(title)out.push(title,'');
 if(c.executive_summary)out.push('SUMMARY',c.executive_summary,'');
 if(list(c.agenda).length)out.push('AGENDA',...list(c.agenda).map((a,i)=>`${i+1}. ${a}`),'');
 if(list(c.discussion_points).length)out.push('WHAT WAS DISCUSSED',...list(c.discussion_points).map(a=>`- ${a}`),'');
 if((c.decisions||[]).length)out.push('DECISIONS',...c.decisions.map((d:any)=>`- ${d.statement}${d.owner&&d.owner!=='Not specified'?` (owner: ${d.owner})`:''}`),'');
 if((c.action_items||[]).length)out.push('ACTION ITEMS',...c.action_items.map((a:any)=>`- ${a.description}${a.owner?` — ${a.owner}`:''}${a.due_date?`, due ${niceDue(a.due_date)}`:''}`),'');
 if(list(c.open_questions).length)out.push('OPEN QUESTIONS',...list(c.open_questions).map(a=>`- ${a}`),'');
 return out.join('\n').trim();
}

function Section({title,children,empty}:{title:string,children?:React.ReactNode,empty?:boolean}){
 return <div className="mn-section"><h3>{title}</h3>{empty?<p className="mn-none">Nothing recorded.</p>:children}</div>;
}

export function MinutesView({c}:{c:any}){
 const decisions=c.decisions||[],actions=c.action_items||[];
 return <div className="mn-body">
  <Section title="Summary" empty={!c.executive_summary}><p className="mn-summary">{c.executive_summary}</p></Section>
  <Section title="Agenda" empty={!list(c.agenda).length}><ol className="mn-list">{list(c.agenda).map((a,i)=><li key={i}>{a}</li>)}</ol></Section>
  <Section title="What was discussed" empty={!list(c.discussion_points).length}><ul className="mn-list">{list(c.discussion_points).map((a,i)=><li key={i}>{a}</li>)}</ul></Section>
  <Section title="Decisions" empty={!decisions.length}>{decisions.map((d:any,i:number)=><div className="mn-card" key={i}>
   <b>{d.statement}</b>
   {d.owner&&d.owner!=='Not specified'&&<span className="mn-meta"><UserIcon size={13}/> {d.owner}</span>}
   {d.evidence&&<p className="mn-evidence"><Quote size={12}/> “{d.evidence}”</p>}
  </div>)}</Section>
  <Section title="Action items" empty={!actions.length}>{actions.map((a:any,i:number)=><div className="mn-card" key={i}>
   <b>{a.description}</b>
   <span className="mn-chips">
    {a.owner&&<span className="mn-chip"><UserIcon size={13}/> {a.owner}</span>}
    {a.due_date&&<span className="mn-chip"><CalendarDays size={13}/> Due {niceDue(a.due_date)}</span>}
    {a.priority&&a.priority!=='normal'&&<span className={`mn-chip pri-${a.priority}`}>{PRIORITY[a.priority]||a.priority} priority</span>}
   </span>
   {a.evidence&&<p className="mn-evidence"><Quote size={12}/> “{a.evidence}”</p>}
  </div>)}</Section>
  <Section title="Open questions" empty={!list(c.open_questions).length}><ul className="mn-list">{list(c.open_questions).map((a,i)=><li key={i}>{a}</li>)}</ul></Section>
 </div>;
}

/* ---- plain-English editor: normal fields, no code ---- */
function Editor({c,onChange}:{c:any,onChange:(c:any)=>void}){
 const set=(k:string,v:any)=>onChange({...c,[k]:v});
 const lines=(k:string)=>(c[k]||[]).join('\n');
 const setLines=(k:string,t:string)=>set(k,t.split('\n'));
 const rows=(k:string)=>c[k]||[];
 const upd=(k:string,i:number,patch:any)=>set(k,rows(k).map((r:any,j:number)=>j===i?{...r,...patch}:r));
 const del=(k:string,i:number)=>set(k,rows(k).filter((_:any,j:number)=>j!==i));
 return <div className="mn-edit">
  <label>Summary<textarea rows={3} value={c.executive_summary||''} onChange={e=>set('executive_summary',e.target.value)}/></label>
  <label>Agenda <small>(one item per line)</small><textarea rows={3} value={lines('agenda')} onChange={e=>setLines('agenda',e.target.value)}/></label>
  <label>What was discussed <small>(one point per line)</small><textarea rows={4} value={lines('discussion_points')} onChange={e=>setLines('discussion_points',e.target.value)}/></label>
  <div className="mn-group"><h3>Decisions</h3>{rows('decisions').map((d:any,i:number)=><div className="mn-row" key={i}>
   <label>Decision<input value={d.statement||''} onChange={e=>upd('decisions',i,{statement:e.target.value})}/></label>
   <label>Owner<input value={d.owner==='Not specified'?'':d.owner||''} onChange={e=>upd('decisions',i,{owner:e.target.value||'Not specified'})}/></label>
   <button type="button" className="iconbtn" aria-label="Remove decision" onClick={()=>del('decisions',i)}><X size={16}/></button></div>)}
   <button type="button" className="textbtn" onClick={()=>set('decisions',[...rows('decisions'),{statement:'',owner:'Not specified',evidence:''}])}><Plus size={14}/> Add decision</button></div>
  <div className="mn-group"><h3>Action items</h3>{rows('action_items').map((a:any,i:number)=><div className="mn-row" key={i}>
   <label>Action<input value={a.description||''} onChange={e=>upd('action_items',i,{description:e.target.value})}/></label>
   <label>Owner<input value={a.owner||''} onChange={e=>upd('action_items',i,{owner:e.target.value})}/></label>
   <label>Due<input value={a.due_date||''} onChange={e=>upd('action_items',i,{due_date:e.target.value})} placeholder="Thursday or 2026-10-16"/></label>
   <label>Priority<select value={a.priority||'normal'} onChange={e=>upd('action_items',i,{priority:e.target.value})}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option></select></label>
   <button type="button" className="iconbtn" aria-label="Remove action item" onClick={()=>del('action_items',i)}><X size={16}/></button></div>)}
   <button type="button" className="textbtn" onClick={()=>set('action_items',[...rows('action_items'),{description:'',owner:'',due_date:'',priority:'normal',evidence:''}])}><Plus size={14}/> Add action item</button></div>
  <label>Open questions <small>(one per line)</small><textarea rows={3} value={lines('open_questions')} onChange={e=>setLines('open_questions',e.target.value)}/></label>
 </div>;
}

const clean=(c:any)=>({...c,
 agenda:list(c.agenda),discussion_points:list(c.discussion_points),open_questions:list(c.open_questions),
 decisions:(c.decisions||[]).filter((d:any)=>String(d.statement||'').trim()),
 action_items:(c.action_items||[]).filter((a:any)=>String(a.description||'').trim())});

export function MinutesCard({m,generated,title,onSave,collapsed}:{m:any,generated:string,title?:string,onSave:(row:any,content:any,status:string)=>Promise<void>|void,collapsed?:boolean}){
 const [editing,setEditing]=useState(false),[draft,setDraft]=useState<any>(null),[copied,setCopied]=useState(false);
 const [label,tone]=STATUS[m.review_status]||[m.review_status,''];
 const latest=m.review_status!=='superseded';
 const copy=async()=>{try{await navigator.clipboard.writeText(minutesToText(m.content,title));setCopied(true);setTimeout(()=>setCopied(false),1800)}catch{}};
 const body=<>
  {editing?<Editor c={draft} onChange={setDraft}/>:<MinutesView c={m.content}/>}
  {latest&&<div className="actions">
   {editing?<>
    <button className="primary" onClick={async()=>{await onSave(m,clean(draft),'reviewed');setEditing(false)}}><Save size={16}/> Save as reviewed</button>
    <button className="secondary" onClick={()=>setEditing(false)}>Cancel</button></>:<>
    <button className="secondary" onClick={()=>{setDraft(JSON.parse(JSON.stringify(m.content)));setEditing(true)}}><Pencil size={16}/> Edit</button>
    {m.review_status!=='approved'&&<button className="primary" onClick={()=>onSave(m,m.content,'approved')}><CheckCircle2 size={16}/> Approve minutes</button>}
    <button className="secondary" onClick={copy}><Copy size={16}/> {copied?'Copied':'Copy as text'}</button></>}
  </div>}
 </>;
 return <section className="panel mn-card-panel">
  <div className="panelhead"><div><h2>Version {m.version}</h2><p className="muted">Generated {generated} · <span className={`badge ${tone}`}>{label}</span>{m.edited_by?` · edited by ${m.edited_by}`:''}</p></div></div>
  {collapsed?<details><summary>Show this version</summary>{body}</details>:body}
 </section>;
}
