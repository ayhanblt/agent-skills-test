import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { json, request } from './api'
import { paymentDetail, paymentList } from './keys'
import { speculate,settle,serverView,outstanding } from './refundState'
import type { Payment } from './types'

let nextOperation=0
export function RefundPanel({ id }: { id: string }) {
  const [amount, setAmount] = useState(0)
  const [failed, setFailed] = useState<{id:number;amount:number}[]>([])
  const client = useQueryClient()
  const detail = paymentDetail(id)
  const payment = useQuery({
    queryKey:detail,
    queryFn:async({signal})=>serverView(client,await request<Payment>(`/api/payments/${id}`,{signal})),
  })
  const refund=useMutation({
    mutationFn:({amount}:{amount:number;id:number;payment:Payment})=>request<Payment>(`/api/payments/${id}/refunds`,json('POST',{amount})),
    retry:false,
    onMutate:async op=>{
      await Promise.all([client.cancelQueries({queryKey:paymentList}),client.cancelQueries({queryKey:detail})])
      return speculate(client,op.payment,op.id,op.amount)
    },
    onError:(_error,op,context)=>{
      if(context)settle(client,context,op.id)
      setFailed(list=>[...list,{id:op.id,amount:op.amount}])
    },
    onSuccess:(server,op,context)=>{if(context)settle(client,context,op.id,server)},
    onSettled:async()=>{
      if(!outstanding(client,id))await Promise.all([
        client.invalidateQueries({queryKey:paymentList}),client.invalidateQueries({queryKey:detail}),
      ])
    },
  })
  if(payment.isPending)return <p>Loading payment…</p>
  if(!payment.data)return <p role="alert">Payment unavailable.</p>
  const item=payment.data
  const submit=(amount:number)=>refund.mutate({amount,id:++nextOperation,payment:item})
  return <section aria-label="Payment detail">
    <h2>{item.id}</h2>
    <p>{item.state} · {item.amount} {item.currency} minor units</p>
    <p>Refunded: <output aria-label="Refunded amount">{item.refunded}</output></p>
    <form onSubmit={event=>{event.preventDefault();if(amount>0)submit(amount)}}>
      <label>Refund amount <input type="number" min={1} step={1} value={amount} onChange={e=>setAmount(Number(e.target.value))} /></label>
      <button disabled={amount<=0}>Refund</button>
    </form>
    {failed.map(op=><div key={op.id}><p role="alert">Refund failed.</p>
      <button onClick={()=>{setFailed(list=>list.filter(x=>x.id!==op.id));submit(op.amount)}}>Retry refund {op.amount}</button></div>)}
  </section>
}
