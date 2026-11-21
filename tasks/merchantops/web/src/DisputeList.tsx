import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query'
import {useState} from 'react'
import {json,request} from './api'
import {disputeList} from './keys'
import type {Dispute} from './types'

export function DisputeList({paymentId,select}:{paymentId:string;select:(id:string)=>void}){
  const [note,setNote]=useState('')
  const client=useQueryClient()
  const list=useQuery({queryKey:disputeList,queryFn:({signal})=>request<Dispute[]>('/api/disputes',{signal})})
  const create=useMutation({
    mutationFn:()=>request<Dispute>('/api/disputes',json('POST',{paymentId,note})),
    onSuccess:async d=>{setNote('');select(d.id);await client.invalidateQueries({queryKey:disputeList})}
  })
  return <section aria-label="Disputes">
    {list.isError && <p role="alert">Disputes unavailable.</p>}
    <ul>{list.data?.map(d=><li key={d.id}><button onClick={()=>select(d.id)}>{d.id}</button> · {d.status} · {d.note}</li>)}</ul>
    <form onSubmit={event=>{event.preventDefault();create.mutate()}}>
      <label>New dispute note <input value={note} onChange={e=>setNote(e.target.value)} /></label>
      <button disabled={!note.trim()||create.isPending}>Create dispute</button>
    </form>
    {create.isError && <p role="alert">Create failed.</p>}
  </section>
}
