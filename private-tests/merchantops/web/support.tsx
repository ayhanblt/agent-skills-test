import {QueryClient,QueryClientProvider} from '@tanstack/react-query'
import {type ReactNode} from 'react'
import {render} from '@testing-library/react'
import {afterEach, vi} from 'vitest'
import {cleanup} from '@testing-library/react'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})
export function mount(children:ReactNode){
 const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:Infinity},mutations:{retry:false}}})
 const result=render(<QueryClientProvider client={client}>{children}</QueryClientProvider>)
 return {...result,client}
}
export function response(data:unknown,status=200,tag?:string){
 return new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json',...(tag?{ETag:tag}:{})}})
}
export function deferred<T>(){
 let resolve!:(x:T)=>void
 const promise=new Promise<T>(r=>{resolve=r})
 return {promise,resolve}
}
