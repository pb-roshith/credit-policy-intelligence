import React,{useEffect,useRef,useState} from 'react';
import {Factory,LogOut,CheckCircle2,ChevronRight} from 'lucide-react';
import {apiRequest} from './api/client';
import AuthScreen from './pages/AuthScreen';
import DataManufacturing from './pages/DataManufacturing';

export default function Shell(){
 const [session,setSession]=useState(null),[checking,setChecking]=useState(true),[toast,setToast]=useState('');
 const timer=useRef(null);
 const clearSession=()=>{sessionStorage.removeItem('dm-session');setSession(null)};
 useEffect(()=>{
  let active=true;
  apiRequest('/api/auth/me').then(data=>{
   if(!active)return;
   let saved={};try{saved=JSON.parse(sessionStorage.getItem('dm-session'))||{}}catch{}
   setSession({...saved,user:data.user});
  }).catch(()=>{if(active)clearSession()}).finally(()=>{if(active)setChecking(false)});
  return()=>{active=false;clearTimeout(timer.current)};
 },[]);
 useEffect(()=>{
  if(!session)return;
  const validate=()=>apiRequest('/api/auth/me').catch(error=>{if([401,403,423].includes(error.status))clearSession()});
  const interval=setInterval(validate,60000);
  const expiry=session.expires_at?setTimeout(clearSession,Math.max(0,new Date(session.expires_at).getTime()-Date.now())):null;
  return()=>{clearInterval(interval);clearTimeout(expiry)};
 },[session]);
 function authenticated(data){sessionStorage.setItem('dm-session',JSON.stringify(data));setSession(data)}
 function notify(message){clearTimeout(timer.current);setToast(message);timer.current=setTimeout(()=>setToast(''),5000)}
 async function logout(){try{await apiRequest('/api/auth/logout',{method:'POST'})}catch{}finally{clearSession()}}
 if(checking)return <div className="auth-page"><p role="status">Checking your session...</p></div>;
 if(!session)return <AuthScreen onAuthenticated={authenticated}/>;
 const role=session.user.role.replaceAll('_',' ');
 return <div className="app"><aside><div className="brand"><div className="tcs-mark">tcs</div><div><strong>TCS DM</strong><small>DATA MANUFACTURING</small></div></div><div className="nav-label">WORKSPACE</div><nav><button className="active"><Factory size={18}/><span>Data Manufacturing</span></button></nav><div className="side-user"><div>{session.user.user_id.slice(0,2).toUpperCase()}</div><span><strong>{session.user.user_id}</strong><small>{role}</small></span></div></aside><div className="main"><header><div className="header-left"><span>Home</span><ChevronRight size={13}/><strong>Data Manufacturing</strong></div><button className="header-logout" onClick={logout} title="Sign out"><LogOut size={17}/></button></header><main><DataManufacturing session={session} notify={notify}/></main></div>{toast&&<div className="toast" role="status"><CheckCircle2 size={17}/>{toast}</div>}</div>;
}
