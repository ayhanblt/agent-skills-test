import {useState} from 'react'
import {PaymentList} from './PaymentList'
import {RefundPanel} from './RefundPanel'
import {DisputeList} from './DisputeList'
import {DisputePanel} from './DisputePanel'

export default function App(){
  const [payment,setPayment]=useState('pay-1')
  const [dispute,setDispute]=useState('dis-1')
  return <main>
    <h1>MerchantOps</h1>
    <PaymentList select={setPayment} />
    <RefundPanel key={payment} id={payment} />
    <DisputeList paymentId={payment} select={setDispute} />
    <DisputePanel key={dispute} id={dispute} />
  </main>
}
