import {expect,it,vi} from 'vitest'
import {act,fireEvent,screen,waitFor} from '@testing-library/react'
import {DisputePanel} from '../src/DisputePanel'
import {disputeDetail} from '../src/keys'
import {mount,response,deferred} from './support'

const d=(revision:number,note:string)=>({id:'dis-1',paymentId:'pay-1',status:'open',note,revision})
it('preserves the original If-Match after background refresh and rebases only on explicit action',async()=>{
 let version=d(1,'first')
 const sent:string[]=[]
 vi.stubGlobal('fetch',vi.fn(async(path:string,init?:RequestInit)=>{
  if(path.endsWith('/documents'))return response([])
  if(init?.method==='PUT'){
   const tag=new Headers(init.headers).get('If-Match')??''
   sent.push(tag)
   if(tag!=='"r'+version.revision+'"')return response({},412)
   const {note}=JSON.parse(init!.body as string);version=d(version.revision+1,note)
  }
  return response(version,200,'"r'+version.revision+'"')
 }))
 const {client}=mount(<DisputePanel id="dis-1"/>)
 const input=await screen.findByLabelText('Note') as HTMLInputElement
 fireEvent.change(input,{target:{value:'my unsaved note'}})
 version=d(2,'other operator')
 await act(async()=>client.invalidateQueries({queryKey:disputeDetail('dis-1')}))
 expect(input.value).toBe('my unsaved note')
 expect(screen.queryByRole('alert')).toBeNull()
 fireEvent.click(screen.getByRole('button',{name:'Save dispute'}))
 expect((await screen.findByRole('alert')).textContent?.trim()).toBeTruthy()
 expect(sent).toEqual(['"r1"'])
 expect(input.value).toBe('my unsaved note')
 expect(screen.getByLabelText('Server note').textContent).toBe('other operator')
 const rebase=screen.getByRole('button',{name:'Use latest version'}) as HTMLButtonElement
 await waitFor(()=>expect(rebase.disabled).toBe(false))
 fireEvent.click(rebase)
 expect(sent).toHaveLength(1)
 fireEvent.click(screen.getByRole('button',{name:'Save dispute'}))
 await waitFor(()=>expect(sent).toEqual(['"r1"','"r2"']))
 await waitFor(()=>expect(screen.getByLabelText('Server note').textContent).toBe('my unsaved note'))
})

it('an older write reply does not overwrite a newer server read',async()=>{
 let version=d(1,'first')
 const writing=deferred<Response>()
 const put=vi.fn(()=>writing.promise)
 vi.stubGlobal('fetch',vi.fn(async(path:string,init?:RequestInit)=>{
  if(path.endsWith('/documents'))return response([])
  if(init?.method==='PUT')return put()
  return response(version,200,'"r'+version.revision+'"')
 }))
 const {client}=mount(<DisputePanel id="dis-1"/>)
 await screen.findByLabelText('Note')
 fireEvent.change(screen.getByLabelText('Note'),{target:{value:'my edit'}})
 fireEvent.click(screen.getByRole('button',{name:'Save dispute'}))
 await waitFor(()=>expect(put).toHaveBeenCalled())
 version=d(3,'later revision')
 await act(async()=>client.invalidateQueries({queryKey:disputeDetail('dis-1')}))
 await act(async()=>writing.resolve(response(d(2,'my edit'),200,'"r2"')))
 await waitFor(()=>expect(screen.getByLabelText('Server note').textContent).toBe('later revision'))
})
