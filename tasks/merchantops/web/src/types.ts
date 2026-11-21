export type Payment = { id: string; amount: number; currency: string; state: string; refunded: number }
export type Dispute = { id: string; paymentId: string; status: 'open' | 'review' | 'closed'; note: string }
export type DisputeDraft = Pick<Dispute, 'status' | 'note'>
export type DocumentRecord = { id: string; disputeId: string; name: string; size: number }
