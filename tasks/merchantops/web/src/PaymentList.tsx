import { useQuery } from '@tanstack/react-query'
import { request } from './api'
import { paymentList } from './keys'
import type { Payment } from './types'

export function PaymentList({select}: {select:(id:string)=>void}){
  const result=useQuery({queryKey:paymentList,queryFn:({signal})=>request<Payment[]>('/api/payments',{signal})})
  if (result.isPending) return <p>Loading payments…</p>
  if (result.isError) return <p role="alert">Payments unavailable.</p>
  return <ul aria-label="Payments">{result.data.map(p=><li key={p.id}>
    <button onClick={()=>select(p.id)}>{p.id}</button> · {p.state} · refunded <span aria-label={`Refunded ${p.id}`}>{p.refunded}</span>
  </li>)}</ul>
}
