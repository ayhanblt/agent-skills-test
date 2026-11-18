import {useEffect,useState} from 'react';
export function createCache(fetcher){return {fetcher};}
export function useResource(cache,key){const [s,set]=useState({status:'idle',data:null,error:null});const retry=()=>{set({status:'loading',data:null,error:null});cache.fetcher(key,{}).then(data=>set({status:'success',data,error:null}),error=>set({status:'error',data:null,error}));};useEffect(()=>{if(key)retry();},[cache,key]);return {...s,retry};}
