export const paymentList = ['payments'] as const
export const paymentDetail = (id: string) => ['payment', id] as const
export const disputeList = ['disputes'] as const
export const disputeDetail = (id: string) => ['dispute', id] as const
export const documentList = (id: string) => ['documents', id] as const
