import React,{createContext,useContext,useState,useEffect} from 'react';
import {api,setToken,hasToken} from '../services/api';
const AuthContext=createContext(null);
export const useAuth=()=>useContext(AuthContext);
export function AuthProvider({children}){
 const [session,setSession]=useState(null),[loading,setLoading]=useState(true);
 const refresh=async()=>{const data=await api('/users/me');setSession(data);return data;};
 useEffect(()=>{if(hasToken())refresh().catch(()=>setToken(null)).finally(()=>setLoading(false));else setLoading(false);const clear=()=>setSession(null);window.addEventListener('session-expired',clear);return()=>window.removeEventListener('session-expired',clear);},[]);
 const signIn=async(token)=>{setToken(token);await refresh();};
 const signOut=async()=>{try{await saveLogout();}finally{setToken(null);setSession(null);}};
 const can=p=>session?.permissions.includes('*')||session?.permissions.includes(p);
 return <AuthContext.Provider value={{session,loading,refresh,signIn,signOut,can}}>{children}</AuthContext.Provider>;
}
const saveLogout=()=>api('/auth/logout',{method:'POST'});
