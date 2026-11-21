import {QueryClient} from '@tanstack/react-query'
import type {Payment} from './types'
import {paymentDetail,paymentList} from './keys'

type Entry={ observed:Payment; start:number; successes:number; pending:Map<number,number> }
const states=new WeakMap<QueryClient, Map<string,Entry>>()
function get(c:QueryClient,p:Payment){
  let map=states.get(c)
  if(!map){map=new Map();states.set(c,map)}
  let entry=map.get(p.id)
  if(!entry){entry={observed:p,start:p.refunded,successes:0,pending:new Map()};map.set(p.id,entry)}
  return entry
}
function observe(e:Entry,p:Payment){
  if(p.refunded>=e.observed.refunded)e.observed=p
}
function view(e:Entry):Payment{
  const pending=[...e.pending.values()].reduce((a,b)=>a+b,0)
  return {...e.observed,refunded:Math.max(e.observed.refunded,e.start+e.successes+pending)}
}
function publish(c:QueryClient,e:Entry){
  const p=view(e)
  c.setQueryData<Payment>(paymentDetail(p.id),p)
  c.setQueryData<Payment[]>(paymentList,rows=>rows?.map(row=>row.id===p.id?p:row))
}
export function serverView(c:QueryClient,p:Payment){
  const e=get(c,p);observe(e,p)
  return view(e)
}
export function speculate(c:QueryClient,p:Payment,operation:number,amount:number){
  const e=get(c,p)
  if(!e.pending.size){e.start=e.observed.refunded;e.successes=0}
  e.pending.set(operation,amount)
  publish(c,e)
  return e
}
export function settle(c:QueryClient,e:Entry,operation:number,server?:Payment){
  const amount=e.pending.get(operation)
  if(amount===undefined)return
  e.pending.delete(operation)
  if(server){observe(e,server);e.successes+=amount}
  if(!e.pending.size){e.start=e.observed.refunded;e.successes=0}
  publish(c,e)
}
export function outstanding(c:QueryClient,id:string){
  return states.get(c)?.get(id)?.pending.size??0
}
