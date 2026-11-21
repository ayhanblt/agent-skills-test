import {useCallback,useSyncExternalStore} from 'react';
const idle={status:'idle',data:null,error:null};
export function createCache(fetcher){
 const entries=new Map();
 function entry(key){
  if(!entries.has(key))entries.set(key,{listeners:new Set(),snapshot:idle,gen:0,controller:null,stale:false});
  return entries.get(key);
 }
 function emit(e){for(const listener of e.listeners)listener();}
 function start(key,e){
  const gen=++e.gen;
  e.controller?.abort();
  const c=e.controller=new AbortController();
  const data=e.snapshot.data;
  e.stale=false;
  e.snapshot={status:'loading',data,error:null};
  emit(e);
  Promise.resolve().then(()=>fetcher(key,{signal:c.signal})).then(
   data=>{if(e.gen===gen){e.snapshot={status:'success',data,error:null};emit(e);}},
   error=>{if(e.gen===gen){e.snapshot={status:'error',data,error};emit(e);}}
  );
 }
 return {
  get(key){return key?entry(key).snapshot:idle;},
  subscribe(key,listener){
   if(!key)return ()=>{};
   const e=entry(key);
   e.listeners.add(listener);
   if(e.snapshot.status==='idle'||e.stale)start(key,e);
   return ()=>{
    e.listeners.delete(listener);
    if(!e.listeners.size&&e.snapshot.status==='loading'){
     e.gen++;
     e.controller.abort();
     e.stale=true;
    }
   };
  },
  retry(key){if(key)start(key,entry(key));},
  invalidate(key){
   if(!key)return;
   const e=entry(key);
   if(e.listeners.size)start(key,e);else e.stale=true;
  }
 };
}
export function useResource(cache,key){
 const subscribe=useCallback(fn=>cache.subscribe(key,fn),[cache,key]);
 const get=useCallback(()=>cache.get(key),[cache,key]);
 const snapshot=useSyncExternalStore(subscribe,get,get);
 const retry=useCallback(()=>cache.retry(key),[cache,key]);
 return {...snapshot,retry};
}
