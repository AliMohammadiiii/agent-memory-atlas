import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer, get} from 'node:http';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {gunzipSync} from 'node:zlib';
import publicDataCompression from './public-data-compression.js';

async function request(server,path,encoding='gzip',method='GET'){
 return new Promise((resolve,reject)=>{
  const port=server.address().port;
  const req=get({hostname:'localhost',port,path,method,headers:{'Accept-Encoding':encoding}},res=>{const chunks=[];res.on('data',x=>chunks.push(x));res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,body:Buffer.concat(chunks)}));});
  req.on('error',reject);
 });
}
async function fixture(preview,run){
 const root=mkdtempSync(join(tmpdir(),'atlas-public-gzip-'));const data=join(root,preview?'dist':'public','data');mkdirSync(data,{recursive:true});
 const body=JSON.stringify({metadata:Array.from({length:100},(_,id)=>({id,title:'Synthetic transport fixture'}))});writeFileSync(join(data,'index.json'),body);writeFileSync(join(root,'outside.json'),'must not be served');
 let middleware;const plugin=publicDataCompression();const config={root,base:'/fixture/',build:{outDir:'dist'}};
 plugin[preview?'configurePreviewServer':'configureServer']({config,middlewares:{use(fn){middleware=fn;}}});
 const server=createServer((req,res)=>middleware(req,res,()=>{res.statusCode=404;res.end('not handled');}));
 await new Promise(resolve=>server.listen(0,'localhost',resolve));
 try{await run(server,body);}finally{await new Promise(resolve=>server.close(resolve));rmSync(root,{recursive:true,force:true});}
}

test('dev JSON gzip is byte-identical and reduces actual HTTP body size',()=>fixture(false,async(server,body)=>{
 const r=await request(server,'/fixture/data/index.json');assert.equal(r.status,200);assert.equal(r.headers['content-encoding'],'gzip');assert.equal(gunzipSync(r.body).toString(),body);assert.ok(r.body.length<Buffer.byteLength(body));
}));
test('preview uses dist data, supports HEAD, and sets encoding variation',()=>fixture(true,async(server)=>{
 const r=await request(server,'/fixture/data/index.json','gzip','HEAD');assert.equal(r.status,200);assert.equal(r.headers['content-encoding'],'gzip');assert.equal(r.headers.vary,'Accept-Encoding');assert.equal(r.body.length,0);
}));
test('does not handle API, path traversal, or a refused gzip encoding',()=>fixture(false,async(server)=>{
 for(const path of ['/fixture/api/search','/fixture/data/..%2f..%2foutside.json'])assert.equal((await request(server,path)).status,404);
 const r=await request(server,'/fixture/data/index.json','gzip;q=0');assert.equal(r.status,404);assert.equal(r.headers['content-encoding'],undefined);
}));
