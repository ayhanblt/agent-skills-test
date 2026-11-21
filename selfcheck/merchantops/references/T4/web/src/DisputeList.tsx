import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query'
import {useState} from 'react'
import {json,request} from './api'
import {disputeList,disputeDetail} from './keys'
import type {Dispute} from './types'

type Versioned = Dispute & {revision:number}
export function DisputeList({paymentId,select}:{paymentId:string;select:(id:string)=>void}){
  const [note,setNote]=useState('')
  const client=useQueryClient()
  const list=useQuery({queryKey:disputeList,queryFn:async({signal})=>{
    const incoming=await request<Versioned[]>('/api/disputes',{signal})
    const old=client.getQueryData<Versioned[]>(disputeList)??[]
    return incoming.map(next=>[next,old.find(d=>d.id===next.id),client.getQueryData<Versioned>(disputeDetail(next.id))]
      .filter((d):d is Versioned=>!!d).reduce((a,b)=> b.revision>a.revision?b:a))
  }})
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
