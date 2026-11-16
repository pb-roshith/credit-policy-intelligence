import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

test('Data Manufacturing exposes both restored generators and the manufactured controls register',async()=>{
 const server=await createServer({cacheDir:'node_modules/.vite-tests/'+process.pid,optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 const previous=globalThis.sessionStorage;
 globalThis.sessionStorage={getItem:()=> 'manufactured'};
 try {
  const session={token:'test',user:{user_id:'manager',role:'relationship_manager'}};
  const {default:Manufacturing}=await server.ssrLoadModule('/src/pages/DataManufacturing.jsx');
  const menu=renderToStaticMarkup(React.createElement(Manufacturing,{session,notify:()=>{}}));
  assert.ok(menu.includes('Generate Exceptions'));
  assert.ok(menu.includes('Generate Policy Controls'));
  const {default:Controls}=await server.ssrLoadModule('@cpi/pages/ControlsWorkspace.jsx');
  const register=renderToStaticMarkup(React.createElement(Controls,{session,policies:[]}));
  assert.ok(register.includes('Controls register'));
  assert.ok(!register.includes('Manufactured'));
  assert.ok(!register.includes('manufactured')); 
  assert.ok(register.includes('Controls Register'));
  assert.ok(register.includes('Published policy requirements'));
 } finally {globalThis.sessionStorage=previous;await server.close()}
});
