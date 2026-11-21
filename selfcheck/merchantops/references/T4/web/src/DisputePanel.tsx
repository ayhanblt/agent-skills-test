import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query'
import {useState} from 'react'
import {HttpError,json} from './api'
import {disputeDetail,disputeList} from './keys'
import type {Dispute,DisputeDraft} from './types'
import {DocumentsPanel} from './DocumentsPanel'

type Version = Dispute & { revision:number; tag:string }
type Draft = DisputeDraft & { tag:string }
async function readVersion(path:string, init?:RequestInit):Promise<Version>{
  const response=await fetch(path,init)
  if(!response.ok)throw new HttpError(response.status)
  const tag=response.headers.get('ETag')
  if(!tag)throw new Error('Missing server validator')
  return {...await response.json(),tag}
}
export function DisputePanel({id}:{id:string}){
  const [draft,setDraft]=useState<Draft>()
  const [conflict,setConflict]=useState(false)
  const client=useQueryClient()
  const key=disputeDetail(id)
  const path=`/api/disputes/${id}`
  const detail=useQuery({
    queryKey:key,
    queryFn:async({signal})=>{
      const next=await readVersion(path,{signal})
      const old=client.getQueryData<Version>(key)
      return old&&old.revision>next.revision?old:next
    },
  })
  const refresh=()=>Promise.all([client.invalidateQueries({queryKey:disputeList}),client.invalidateQueries({queryKey:key})])
  const save=useMutation({
    mutationFn:({note,status,tag}:Draft)=>readVersion(path,json('PUT',{note,status},{'If-Match':tag})),
    onSuccess:async version=>{
      client.setQueryData<Version>(key,old=> !old||old.revision<=version.revision?version:old)
      setDraft(undefined);setConflict(false)
      await refresh()
    },
    onError:async err=>{
      if(err instanceof HttpError&&err.status===412){setConflict(true);await refresh()}
    },
  })
  if(detail.isPending)return <p>Loading dispute…</p>
  if(!detail.data)return <p role="alert">Dispute unavailable.</p>
  const server=detail.data,view=draft??server
  return <section aria-label="Dispute detail">
    <h2>{id}</h2>
    <p>Server note: <output aria-label="Server note">{server.note}</output></p>
    <form onSubmit={event=>{event.preventDefault();if(!conflict){setDraft(view);save.mutate(view)}}}>
      <label>Status <select value={view.status} onChange={e=>setDraft({note:view.note,tag:view.tag,status:e.target.value as Dispute['status']})}><option>open</option><option>review</option><option>closed</option></select></label>
      <label>Note <input value={view.note} onChange={e=>setDraft({status:view.status,note:e.target.value,tag:view.tag})} /></label>
      <button disabled={save.isPending||conflict}>Save dispute</button>
    </form>
    {conflict && <><p role="alert">Update conflict. Review the latest server version.</p>
      <button disabled={!draft||detail.isFetching||save.isPending||server.tag===draft.tag} onClick={()=>{if(draft){setDraft({...draft,tag:server.tag});setConflict(false)}}}>Use latest version</button></>}
    {save.isError && !conflict && !(save.error instanceof HttpError && save.error.status===412) && <p role="alert">Save failed.</p>}
    <DocumentsPanel id={id} />
  </section>
}
