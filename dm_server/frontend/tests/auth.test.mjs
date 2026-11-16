import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

test('DM reuses the CPI login layout and has its own API and CSRF cookie',async()=>{
 const server=await createServer({cacheDir:'node_modules/.vite-tests/'+process.pid,optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 const oldDocument=globalThis.document,oldFetch=globalThis.fetch;
 try{
  const {default:AuthScreen}=await server.ssrLoadModule('/src/pages/AuthScreen.jsx');
  const html=renderToStaticMarkup(React.createElement(AuthScreen,{onAuthenticated:()=>{}}));
  assert.ok(html.includes('Data Manufacturing'));
  assert.ok(html.includes('auth-page'));
  assert.ok(html.includes('Sign in'));
  const {apiRequest}=await server.ssrLoadModule('/src/api/client.js');
  let sent;
  globalThis.document={cookie:'cpi_csrf=wrong-token; dm_csrf=dm-token'};
  globalThis.fetch=async(url,options)=>{sent={url,options};return {ok:true,json:async()=>({ok:true})}};
  await apiRequest('/api/example',{method:'POST',body:'{}'});
  assert.equal(sent.url,'http://localhost:8005/api/example');
  assert.equal(sent.options.headers['X-CSRF-Token'],'dm-token');
  assert.equal(sent.options.credentials,'include');
 }finally{globalThis.document=oldDocument;globalThis.fetch=oldFetch;await server.close()}
});
