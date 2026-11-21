import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query'
import {useState} from 'react'
import {json,request} from './api'
import {disputeDetail,disputeList} from './keys'
import type {Dispute,DisputeDraft} from './types'
import {DocumentsPanel} from './DocumentsPanel'

export function DisputePanel({id}:{id:string}){
  const [draft,setDraft]=useState<DisputeDraft>()
  const client=useQueryClient()
  const detail=useQuery({queryKey:disputeDetail(id),queryFn:({signal})=>request<Dispute>(`/api/disputes/${id}`,{signal})})
  const save=useMutation({
    mutationFn:(draft:DisputeDraft)=>request<Dispute>(`/api/disputes/${id}`,json('PUT',draft)),
    onSuccess:async()=>{
      setDraft(undefined)
      await Promise.all([client.invalidateQueries({queryKey:disputeList}),client.invalidateQueries({queryKey:disputeDetail(id)})])
    }
  })
  if(detail.isPending)return <p>Loading dispute…</p>
  if(detail.isError)return <p role="alert">Dispute unavailable.</p>
  const view=draft??detail.data
  return <section aria-label="Dispute detail">
    <h2>{id}</h2>
    <p>Server note: <output aria-label="Server note">{detail.data.note}</output></p>
    <form onSubmit={event=>{event.preventDefault();save.mutate({note:view.note,status:view.status})}}>
      <label>Status <select value={view.status} onChange={e=>setDraft({note:view.note,status:e.target.value as Dispute['status']})}><option>open</option><option>review</option><option>closed</option></select></label>
      <label>Note <input value={view.note} onChange={e=>setDraft({status:view.status,note:e.target.value})} /></label>
      <button disabled={save.isPending}>Save dispute</button>
    </form>
    {save.isError && <p role="alert">Save failed.</p>}
    <DocumentsPanel id={id} />
  </section>
}
