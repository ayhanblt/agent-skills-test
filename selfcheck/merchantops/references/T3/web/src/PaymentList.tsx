import { useQuery, useQueryClient } from '@tanstack/react-query'
import { request } from './api'
import { paymentList } from './keys'
import type { Payment } from './types'
import {serverView} from './refundState'

export function PaymentList({select}: {select:(id:string)=>void}){
  const client=useQueryClient()
  const result=useQuery({queryKey:paymentList,queryFn:async({signal})=>(await request<Payment[]>('/api/payments',{signal})).map(p=>serverView(client,p))})
  if (result.isPending) return <p>Loading payments…</p>
  if (result.isError) return <p role="alert">Payments unavailable.</p>
  return <ul aria-label="Payments">{result.data.map(p=><li key={p.id}>
    <button onClick={()=>select(p.id)}>{p.id}</button> · {p.state} · refunded <span aria-label={`Refunded ${p.id}`}>{p.refunded}</span>
  </li>)}</ul>
}
