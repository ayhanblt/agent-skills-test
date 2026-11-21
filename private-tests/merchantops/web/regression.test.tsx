import {expect,it,vi} from 'vitest'
import {screen} from '@testing-library/react'
import App from '../src/App'
import {mount,response} from './support'

it('shows existing fixture payments, disputes and documents',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(path:string)=>{
  if(path.endsWith('/documents'))return response([{id:'doc-1',disputeId:'dis-1',name:'Receipt',size:3}])
  if(path.startsWith('/api/payments')){
   const p={id:'pay-1',amount:10000,currency:'USD',state:'paid',refunded:0}
   return response(path==='/api/payments'?[p]:p)
  }
  const d={id:'dis-1',paymentId:'pay-1',status:'open',note:'Fixture dispute',revision:1}
  return response(path==='/api/disputes'?[d]:d,200,'"r1"')
 }))
 mount(<App />)
 await screen.findByRole('heading',{name:'MerchantOps'})
 await screen.findByRole('button',{name:'pay-1'})
 await screen.findByRole('button',{name:'Refund'})
 await screen.findByRole('button',{name:'Save dispute'})
 expect(await screen.findByRole('button',{name:'Receipt'})).toBeTruthy()
})
