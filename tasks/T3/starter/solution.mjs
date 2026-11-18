import {useEffect,useState} from 'react';
export function useSearch(query,search){
 const [state,set]=useState({status:'idle',data:null,error:null});
 useEffect(()=>{if(!query)return;set({status:'loading',data:null,error:null});search(query,{}).then(data=>set({status:'success',data,error:null}),error=>set({status:'error',data:null,error}));},[query,search]);return state;
}
