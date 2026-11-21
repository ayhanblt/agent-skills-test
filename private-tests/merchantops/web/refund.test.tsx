import {expect,it,vi} from 'vitest'
import {act,fireEvent,screen,waitFor} from '@testing-library/react'
import {RefundPanel} from '../src/RefundPanel'
import {PaymentList} from '../src/PaymentList'
import {mount,response,deferred} from './support'

const payment=(refunded:number)=>({id:'pay-1',amount:10000,currency:'USD',state:'paid',refunded})
async function setup(){
 const posts:{amount:number;finish:ReturnType<typeof deferred<Response>>}[]=[]
 const mock=vi.fn(async(path:string,init?:RequestInit)=>{
  if(init?.method==='POST'){
   const finish=deferred<Response>();posts.push({amount:JSON.parse(init.body as string).amount,finish});return finish.promise
  }
  // Intentionally stale service response for display reconciliation.
  return response(path==='/api/payments'?[payment(0)]:payment(0))
 })
 vi.stubGlobal('fetch',mock)
 mount(<><PaymentList select={()=>{}}/><RefundPanel id="pay-1"/></>)
 await screen.findByRole('button',{name:'Refund'})
 const submit=(amount:number)=>{
  fireEvent.change(screen.getByLabelText('Refund amount'),{target:{value:String(amount)}})
  fireEvent.click(screen.getByRole('button',{name:'Refund'}))
 }
 const total=async(n:number)=>waitFor(()=>{
  expect(screen.getByLabelText('Refunded amount').textContent).toBe(String(n))
  expect(screen.getByLabelText('Refunded pay-1').textContent).toBe(String(n))
 })
 return {posts,submit,total}
}

it('rolls back only a failed refund and retries it only on request',async()=>{
 const {posts,submit,total}=await setup()
 submit(100);await total(100)
 submit(200);await total(300)
 await waitFor(()=>expect(posts).toHaveLength(2))
 await act(async()=>posts[0].finish.resolve(response({},503)))
 await total(200)
 expect(await screen.findByRole('alert')).toBeTruthy()
 expect(posts).toHaveLength(2)
 await act(async()=>posts[1].finish.resolve(response(payment(200))))
 await total(200)
 fireEvent.click(screen.getByRole('button',{name:/retry refund/i}))
 await total(300);await waitFor(()=>expect(posts).toHaveLength(3))
 expect(posts[2].amount).toBe(100)
 await act(async()=>posts[2].finish.resolve(response(payment(300))))
 await total(300)
})

it('older mutation replies and stale refetch cannot regress confirmed total',async()=>{
 const {posts,submit,total}=await setup()
 submit(100);await total(100)
 submit(200);await total(300)
 await waitFor(()=>expect(posts).toHaveLength(2))
 await act(async()=>posts[1].finish.resolve(response(payment(300))))
 await total(300)
 await act(async()=>posts[0].finish.resolve(response(payment(100))))
 await total(300)
})
