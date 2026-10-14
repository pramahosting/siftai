import React,{useCallback,useEffect,useRef,useState} from 'react';
import {UserPlus,Pencil,Trash2,Download,Upload,Search,Ban,CheckCircle2,X,Database,RefreshCw,Monitor,AlertTriangle,ShieldCheck} from 'lucide-react';

const when=v=>{if(!v)return 'Never';try{return new Date(v).toLocaleString(undefined,{day:'numeric',month:'short',year:'numeric',hour:'numeric',minute:'2-digit'})}catch{return '—'}};

/* ---------------- Users ---------------- */
export function UsersPage({request,download,me,canCreate,onChanged}){
 const [users,setUsers]=useState<any[]|null>(null),[q,setQ]=useState(''),[err,setErr]=useState(''),[msg,setMsg]=useState('');
 const [form,setForm]=useState<any>(null),[formErr,setFormErr]=useState(''),[saving,setSaving]=useState(false),[del,setDel]=useState<any>(null);
 const refresh=useCallback(async(term='')=>{try{setUsers(await request('/admin/users'+(term?`?q=${encodeURIComponent(term)}`:'')));setErr('')}catch(e){setErr(e.message)}},[request]);
 useEffect(()=>{refresh()},[refresh]);
 useEffect(()=>{const t=setTimeout(()=>refresh(q.trim()),250);return()=>clearTimeout(t)},[q,refresh]);
 const openCreate=()=>{setForm({mode:'create',email:'',display_name:'',password:'',role:'user',is_active:true});setFormErr('');setMsg('')};
 const openEdit=u=>{setForm({mode:'edit',id:u.id,email:u.email,display_name:u.display_name,role:u.role,is_active:u.is_active,password:'',orig:u,builtin:u.builtin,hasPassword:u.has_password});setFormErr('');setMsg('')};
 const save=async e=>{e.preventDefault();setFormErr('');setSaving(true);
  try{
   if(form.mode==='create'){
    if(!form.email.trim())throw new Error('Enter an email address.');
    if(form.password.length<8)throw new Error('Password must be at least 8 characters.');
    await request('/admin/users',{method:'POST',body:JSON.stringify({email:form.email.trim(),display_name:form.display_name.trim(),password:form.password,role:form.role,is_active:form.is_active})});setMsg(`Created ${form.email.trim()}.`);
   }else{
    const o=form.orig,body:any={};
    if(form.display_name.trim()&&form.display_name!==o.display_name)body.display_name=form.display_name.trim();
    if(form.role!==o.role)body.role=form.role;
    if(form.is_active!==o.is_active)body.is_active=form.is_active;
    if(form.password){if(form.password.length<8)throw new Error('Password must be at least 8 characters.');body.password=form.password}
    if(!Object.keys(body).length){setForm(null);return}
    await request(`/admin/users/${form.id}`,{method:'PATCH',body:JSON.stringify(body)});setMsg(`Saved changes to ${form.email}.`);
   }
   setForm(null);await refresh(q.trim());onChanged&&onChanged();
  }catch(ex){setFormErr(ex.message)}finally{setSaving(false)}};
 const toggle=async u=>{setMsg('');try{await request(`/admin/users/${u.id}`,{method:'PATCH',body:JSON.stringify({is_active:!u.is_active})});setMsg(`${u.email} ${u.is_active?'disabled':'enabled'}.`);await refresh(q.trim())}catch(ex){setErr(ex.message);setTimeout(()=>setErr(''),6000)}};
 const remove=async()=>{const u=del;setDel(null);setMsg('');try{const r=await request(`/admin/users/${u.id}`,{method:'DELETE'});setMsg(`Deleted ${u.email}${r.meetings_removed?` and ${r.meetings_removed} meeting(s) with their transcripts, minutes and actions`:''}.`);await refresh(q.trim());onChanged&&onChanged()}catch(ex){setErr(ex.message);setTimeout(()=>setErr(''),6000)}};
 return <>
  <div className="pagehead"><div><p className="eyebrow">ADMINISTRATION</p><h1>Users</h1><p>Create, update, disable or delete the people who can use this workspace.</p></div>
   <div className="headactions"><button className="secondary" onClick={()=>download('/admin/users/export','users.csv')}><Download size={16}/> Export CSV</button>{canCreate&&<button className="primary" onClick={openCreate}><UserPlus size={16}/> Add user</button>}</div></div>
  {msg&&<div className="okmsg" role="status"><CheckCircle2 size={16}/> {msg}</div>}
  {err&&<div className="alert" role="alert">{err}</div>}
  {!canCreate&&<div className="hint" style={{marginBottom:14}}>People sign in with Microsoft in this mode and appear here after their first sign-in. You can change their role, disable or remove them here.</div>}
  {form&&<form className="panel userform" onSubmit={save} aria-label={form.mode==='create'?'Add user':'Edit user'}>
   <div className="panelhead"><h2>{form.mode==='create'?'Add user':`Edit ${form.email}`}</h2><button type="button" className="iconbtn" aria-label="Close" onClick={()=>setForm(null)}><X size={18}/></button></div>
   <div className="formgrid">
    <label>Email<input type="email" value={form.email} disabled={form.mode==='edit'} onChange={e=>setForm({...form,email:e.target.value})} autoComplete="off" required/></label>
    <label>Full name<input value={form.display_name} onChange={e=>setForm({...form,display_name:e.target.value})} maxLength={200}/></label>
    {(form.mode==='create'||form.hasPassword)&&!form.builtin&&<label>{form.mode==='create'?'Password':'New password (leave blank to keep)'}<input type="password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})} autoComplete="new-password" minLength={8}/></label>}
    <label>Role<select value={form.role} disabled={form.builtin} onChange={e=>setForm({...form,role:e.target.value})}><option value="user">Member</option><option value="admin">Administrator</option></select></label>
    <label className="checklabel"><input type="checkbox" checked={form.is_active} disabled={form.builtin} onChange={e=>setForm({...form,is_active:e.target.checked})}/> Account is active (can sign in)</label>
   </div>
   {form.builtin&&<p className="muted">The built-in administrator can only be renamed.</p>}
   {formErr&&<div className="alert" role="alert">{formErr}</div>}
   <div className="actions"><button className="primary" disabled={saving}>{saving?'Saving…':form.mode==='create'?'Create user':'Save changes'}</button><button type="button" className="secondary" onClick={()=>setForm(null)}>Cancel</button></div>
  </form>}
  <section className="panel">
   <div className="searchbar"><Search size={16}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search by name or email" aria-label="Search users"/></div>
   {users===null?<div className="empty">Loading users…</div>:!users.length?<div className="empty">No users match.</div>:
   <div className="utable" role="table" aria-label="Users">
    <div className="urow uhead" role="row"><span>User</span><span>Role</span><span>Status</span><span>Meetings</span><span>Last sign-in</span><span>Actions</span></div>
    {users.map(u=><div className="urow" role="row" key={u.id}>
     <span className="ucell uname" data-label="User"><b>{u.display_name||u.email}</b><small>{u.email}{u.builtin?' · built-in':''}{u.source==='microsoft'?' · Microsoft':''}</small></span>
     <span className="ucell" data-label="Role"><span className={`badge ${u.role==='admin'?'green':''}`}>{u.role==='admin'?'Administrator':'Member'}</span></span>
     <span className="ucell" data-label="Status"><span className={`badge ${u.is_active?'green':'red'}`}>{u.is_active?'Active':'Disabled'}</span></span>
     <span className="ucell" data-label="Meetings">{u.meetings}</span>
     <span className="ucell" data-label="Last sign-in">{when(u.last_login_at)}</span>
     <span className="ucell uacts" data-label="Actions">
      <button className="textbtn" onClick={()=>openEdit(u)} aria-label={`Edit ${u.email}`}><Pencil size={14}/> Edit</button>
      {!u.builtin&&u.id!==me?.id&&<button className="textbtn" onClick={()=>toggle(u)} aria-label={`${u.is_active?'Disable':'Enable'} ${u.email}`}>{u.is_active?<><Ban size={14}/> Disable</>:<><CheckCircle2 size={14}/> Enable</>}</button>}
      {!u.builtin&&u.id!==me?.id&&<button className="textbtn danger" onClick={()=>setDel(u)} aria-label={`Delete ${u.email}`}><Trash2 size={14}/> Delete</button>}
     </span>
    </div>)}
   </div>}
  </section>
  {del&&<div className="modal-backdrop" onClick={()=>setDel(null)}><div className="confirm-dialog" role="alertdialog" aria-modal="true" aria-label="Confirm delete" onClick={e=>e.stopPropagation()}>
   <AlertTriangle size={22}/><h2>Delete {del.display_name||del.email}?</h2>
   <p>This permanently removes the account{del.meetings?` and ${del.meetings} meeting(s) with their transcripts, minutes and action items`:''}. It cannot be undone. To keep the data and only block sign-in, choose Disable instead.</p>
   <div className="actions"><button className="primary danger-btn" onClick={remove}>Delete user</button><button className="secondary" onClick={()=>setDel(null)}>Cancel</button></div>
  </div></div>}
 </>;
}

/* ---------------- Data import ---------------- */
export function DataImport({request,download,isAdmin,onDone}){
 const [tables,setTables]=useState<any[]|null>(null),[err,setErr]=useState(''),[busy,setBusy]=useState(''),[result,setResult]=useState<any>(null);
 const refs=useRef<Record<string,HTMLInputElement|null>>({});
 useEffect(()=>{request('/data/tables').then(setTables).catch(e=>setErr(e.message))},[request]);
 const run=async(label,fn)=>{setBusy(label);setErr('');setResult(null);try{const r=await fn();setResult(r);onDone&&onDone()}catch(e){setErr(e.message)}finally{setBusy('')}};
 const mock=reset=>run(reset?'reload':'load',()=>request(`/data/mock/load${reset?'?reset=true':''}`,{method:'POST'}));
 const upload=(table,file)=>{if(!file)return;if(!/\.csv$/i.test(file.name)){setErr('Choose a .csv file.');return}const fd=new FormData();fd.append('file',file);run(table,()=>request(`/data/import/${table}`,{method:'POST',body:fd}))};
 return <>
  <div className="pagehead"><div><p className="eyebrow">SAMPLE DATA</p><h1>Data import</h1><p>Fill the app with sample data in one click, or upload your own CSV file for any table.</p></div></div>
  <section className="panel">
   <div className="panelhead"><h2><Database size={18} style={{verticalAlign:'-3px'}}/> Mock data for all tables</h2></div>
   <p className="muted">{isAdmin?'Loads sample users, meetings, transcripts, minutes, actions, briefings, run history, jobs and audit entries (10 CSV files). Sample sign-ins use the password Passw0rd!.':'Loads sample meetings, a transcript, minutes, actions and briefings into your own account.'} Rows that already exist are left alone.</p>
   <div className="actions"><button className="primary" disabled={!!busy} onClick={()=>mock(false)}><Upload size={16}/> {busy==='load'?'Loading…':'Load mock data'}</button><button className="secondary" disabled={!!busy} onClick={()=>mock(true)} title="Removes earlier mock meetings first, then loads fresh copies"><RefreshCw size={16}/> {busy==='reload'?'Reloading…':'Reload (replace)'}</button></div>
  </section>
  {err&&<div className="alert" role="alert">{err}</div>}
  {result&&<section className="panel resultpanel" role="status" aria-live="polite"><div className="panelhead"><h2>Result</h2><button className="iconbtn" aria-label="Dismiss" onClick={()=>setResult(null)}><X size={18}/></button></div><p><b>{result.message}</b></p>
   <div className="utable resulttable"><div className="urow uhead"><span>Table</span><span>Added</span><span>Already there</span><span>Problems</span></div>
   {Object.entries(result.tables).map(([t,v]:any)=><div className="urow" key={t}><span className="ucell" data-label="Table">{t.replaceAll('_',' ')}</span><span className="ucell" data-label="Added">{v.inserted}</span><span className="ucell" data-label="Already there">{v.skipped}</span><span className="ucell" data-label="Problems">{v.errors.length}</span></div>)}</div>
   {Object.entries(result.tables).flatMap(([t,v]:any)=>v.errors.map(x=>({t,...x}))).slice(0,30).map((x,i)=><p className="rowerr" key={i}><b>{x.t.replaceAll('_',' ')}, row {x.row}:</b> {x.message}</p>)}
  </section>}
  <section className="panel">
   <div className="panelhead"><h2>Upload a CSV file</h2></div>
   <p className="muted">Download a template to see the columns, fill it in (UTF-8 CSV), then upload it. Dates can be like 2026-10-14 09:30 or today 09:30, tomorrow 14:00, +2d 10:00.</p>
   {tables===null?<div className="empty">Loading…</div>:tables.map(t=><div className="tablerow" key={t.table}>
    <div className="tinfo"><b>{t.table.replaceAll('_',' ')}</b>{t.admin_only&&<span className="badge amber">Admin only</span>}<small>{t.description}</small><small className="cols">{t.columns.map(c=><code key={c} className={t.required.includes(c)?'req':''}>{c}</code>)}</small></div>
    <div className="tacts"><button className="secondary" onClick={()=>download(`/data/template/${t.table}`,`${t.table}_template.csv`)}><Download size={15}/> Template</button>
     <input type="file" accept=".csv,text/csv" hidden ref={el=>{refs.current[t.table]=el}} onChange={e=>{upload(t.table,e.target.files?.[0]);e.target.value=''}}/>
     <button className="primary" disabled={!t.allowed||!!busy} onClick={()=>refs.current[t.table]?.click()}><Upload size={15}/> {busy===t.table?'Uploading…':'Upload CSV'}</button></div>
   </div>)}
  </section>
 </>;
}

/* ---------------- Calendar on this computer ---------------- */
export function MachinePrompt({machine,onChoose}){
 const [busy,setBusy]=useState(false);
 if(!machine||!machine.allowed_by_admin||!machine.available)return null;
 const choose=async a=>{setBusy(true);try{await onChoose(a)}finally{setBusy(false)}};
 if(machine.consent==='allowed')return null;
 return <div className="machine-prompt" role="group" aria-label="Use the calendar on this computer">
  <Monitor size={20}/>
  <div><b>{machine.consent==='denied'?'Use the calendar on this computer?':'Calendar found on this computer'}</b>
   <p>We found {machine.source}. Allow Meeting Intelligence to read your meetings from it so Today, at a glance stays current? Nothing is sent anywhere, and you can turn it off at any time.</p>
   {machine.can_grant?<div className="actions"><button className="primary" disabled={busy} onClick={()=>choose(true)}><ShieldCheck size={15}/> Allow</button>{machine.consent!=='denied'&&<button className="secondary" disabled={busy} onClick={()=>choose(false)}>Not now</button>}</div>
   :<p className="muted">Open this app on that computer to allow it.</p>}
  </div></div>;
}

export function CalendarFinder({machine,onSearch,onUpload}){
 const [busy,setBusy]=useState(false);
 const run=async f=>{setBusy(true);try{await f()}finally{setBusy(false)}};
 return <div className="cal-finder">
  <b>{machine?.available?'Or choose a calendar file yourself':'No calendar found on this computer yet'}</b>
  <p>{machine?.available?'':'The app looked in Downloads, Documents, Desktop, OneDrive and docs/calendar. '}Export your calendar as an .ics file (Outlook: File → Save Calendar; Google or Apple Calendar: Export) and upload it here. It is read on this computer only and stays private to your account.</p>
  <div className="actions">
   <label className="primary cal-up"><Upload size={15}/> {busy?'Reading…':'Upload .ics file'}<input type="file" accept=".ics,.ical,text/calendar" hidden disabled={busy} onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)run(()=>onUpload(f))}}/></label>
   <button type="button" className="secondary" disabled={busy} onClick={()=>run(onSearch)}><Search size={15}/> Search this computer again</button>
  </div>
  {machine?.folders?.length>0&&<small className="muted">Searched: {machine.folders.join(' · ')}</small>}
 </div>;
}
