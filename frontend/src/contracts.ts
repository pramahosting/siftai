export type Role = 'admin' | 'user';
export interface User { id:string; email:string; display_name:string; role:Role }
export interface Meeting { id:string; title:string; organizer:string; start_at:string; end_at:string; sensitivity:string; status:string; transcript_status:string; minutes_status:string }
export interface ActionItem { id:string; meeting_id:string; description:string; owner:string|null; due_date:string|null; status:'proposed'|'needs_review'|'assigned'|'in_progress'|'completed'; evidence?:string|null }
export interface Briefing { id:string; local_date:string; rendered_text:string; word_count:number; generation_status:string; delivery_status:string; created_at:string }
export interface WorkflowRun { id:string; workflow_name:string; status:string; safe_error?:string|null; created_at:string }
