let token=sessionStorage.getItem('businessos-token');
export function setToken(value){token=value; value?sessionStorage.setItem('businessos-token',value):sessionStorage.removeItem('businessos-token');}
export const hasToken=()=>Boolean(token);
export async function api(path, options={}){
  const response=await fetch((import.meta.env.VITE_API_URL||'/api')+path,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...(token?{Authorization:`Bearer ${token}`} :{}),...options.headers}});
  if(!response.ok){
    const payload=await response.json().catch(()=>({}));
    if(response.status===401 && !path.startsWith('/auth/')){setToken(null);window.dispatchEvent(new Event('session-expired'));}
    throw new Error(typeof payload.detail==='string'?payload.detail:payload.detail?.map(e=>`${e.loc.at(-1)}: ${e.msg}`).join('; ')||'The request could not be completed.');
  }
  return options.download?response.blob():response.json();
}
export const save=(path,data,method='POST')=>api(path,{method,body:JSON.stringify(data)});
export async function download(kind){const blob=await api('/'+kind+'/export',{download:true});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=kind+'.csv';a.click();URL.revokeObjectURL(url);}
