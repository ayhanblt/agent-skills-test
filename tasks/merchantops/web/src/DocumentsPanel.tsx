import {useQuery,useMutation,useQueryClient} from '@tanstack/react-query'
import {useState} from 'react'
import {HttpError,request} from './api'
import {documentList} from './keys'
import type {DocumentRecord} from './types'

const headers={'X-Operator':'alice'}
export function DocumentsPanel({id}:{id:string}){
  const [file,setFile]=useState<File>()
  const client=useQueryClient()
  const base=`/api/disputes/${id}/documents`
  const docs=useQuery({queryKey:documentList(id),queryFn:({signal})=>request<DocumentRecord[]>(base,{headers,signal})})
  const upload=useMutation({
    mutationFn:(file:File)=>request<DocumentRecord>(`${base}?name=${encodeURIComponent(file.name)}`,{method:'POST',headers,body:file}),
    onSuccess:()=>client.invalidateQueries({queryKey:documentList(id)})
  })
  const download=useMutation({mutationFn:async(d:DocumentRecord)=>{
    const response=await fetch(`/api/documents/${d.id}`,{headers})
    if(!response.ok)throw new HttpError(response.status)
    const url=URL.createObjectURL(await response.blob())
    const link=document.createElement('a');link.href=url;link.download=d.name;link.click()
    URL.revokeObjectURL(url)
  }})
  return <section aria-label="Documents">
    {docs.isError && <p role="alert">Documents unavailable.</p>}
    <ul>{docs.data?.map(d=><li key={d.id}><button onClick={()=>download.mutate(d)}>{d.name}</button></li>)}</ul>
    <label>Document <input type="file" onChange={e=>setFile(e.target.files?.[0])} /></label>
    <button disabled={!file||upload.isPending} onClick={()=>file&&upload.mutate(file)}>Upload</button>
    {(upload.isError||download.isError) && <p role="alert">Document operation failed.</p>}
  </section>
}
