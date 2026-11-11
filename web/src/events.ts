import { ApiError, requestData } from '@papr/shared/api'
import type { CsrfToken, EventInput, EventResult } from '@papr/shared/contracts'

// Best effort, memory-only. A retry reuses the exact event; a fresh action gets a fresh ID.
export function recordUsage(type: EventInput['type'], paperId: string, answerMode: 'student'|'solution', csrf: string): void {
  const event: EventInput={event_id:crypto.randomUUID(),type,paper_id:paperId,occurred_at:new Date().toISOString(),payload:{answer_mode:answerMode}}
  void (async()=>{
    for(let attempt=0;attempt<2;attempt++){
      try{await requestData<EventResult>('/api/v1/events',{body:{events:[event]},csrf});return}
      catch(error){
        if(attempt===1)return
        if(error instanceof ApiError){
          if(error.code==='CSRF_INVALID'){
            try{csrf=(await requestData<CsrfToken>('/api/v1/session/csrf',{body:{}})).csrf_token}catch{return}
          }else if(error.status<500)return
        }
      }
    }
  })()
}
