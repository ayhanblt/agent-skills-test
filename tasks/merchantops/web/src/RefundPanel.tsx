import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { json, request } from './api'
import { paymentDetail, paymentList } from './keys'
import type { Payment } from './types'

export function RefundPanel({ id }: { id: string }) {
  const [amount, setAmount] = useState(0)
  const client = useQueryClient()
  const payment = useQuery({
    queryKey: paymentDetail(id),
    queryFn: ({signal}) => request<Payment>(`/api/payments/${id}`, {signal}),
  })
  const refund = useMutation({
    mutationFn: (amount: number) => request<Payment>(`/api/payments/${id}/refunds`, json('POST', {amount})),
    onSuccess: async () => {
      await Promise.all([client.invalidateQueries({queryKey: paymentList}),client.invalidateQueries({queryKey: paymentDetail(id)})])
    },
  })
  if (payment.isPending) return <p>Loading payment…</p>
  if (payment.isError) return <p role="alert">Payment unavailable.</p>
  const item = payment.data
  return <section aria-label="Payment detail">
    <h2>{item.id}</h2>
    <p>{item.state} · {item.amount} {item.currency} minor units</p>
    <p>Refunded: <output aria-label="Refunded amount">{item.refunded}</output></p>
    <form onSubmit={event => {event.preventDefault();refund.mutate(amount)}}>
      <label>Refund amount <input type="number" min={1} step={1} value={amount} onChange={e=>setAmount(Number(e.target.value))} /></label>
      <button disabled={amount<=0}>Refund</button>
    </form>
    {refund.isError && <p role="alert">Refund failed.</p>}
  </section>
}
