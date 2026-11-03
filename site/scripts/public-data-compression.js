import {createReadStream, statSync} from 'node:fs';
import {resolve, sep} from 'node:path';
import {createGzip} from 'node:zlib';

// Compress only permission-filtered static JSON. API traffic, source files and
// browser notes never pass through this middleware. No access/body logging.
export default function publicDataCompression() {
  const install=(server,preview)=>{
    const root=resolve(server.config.root,preview?server.config.build.outDir:'public','data');
    const prefix=server.config.base.replace(/\/$/,'')+'/data/';
    server.middlewares.use((req,res,next)=>{
      const acceptsGzip=String(req.headers['accept-encoding']||'').split(',').some(part=>{const [name,...params]=part.trim().split(';');const quality=params.find(p=>p.trim().startsWith('q='));return name.toLowerCase()==='gzip'&&(!quality||Number(quality.trim().slice(2))>0);});
      if(!['GET','HEAD'].includes(req.method)||!acceptsGzip)return next();
      let pathname;
      try{pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);}catch{return next();}
      if(!pathname.startsWith(prefix)||!pathname.endsWith('.json')||pathname.includes('\0'))return next();
      const file=resolve(root,pathname.slice(prefix.length));
      if(!file.startsWith(root+sep))return next();
      try{if(!statSync(file).isFile())return next();}catch{return next();}
      res.setHeader('Content-Type','application/json; charset=utf-8');
      res.setHeader('Content-Encoding','gzip');
      res.setHeader('Vary','Accept-Encoding');
      res.setHeader('Cache-Control','public, max-age=0, must-revalidate');
      if(req.method==='HEAD')return res.end();
      const stream=createReadStream(file),gzip=createGzip({level:6});
      const fail=()=>{stream.destroy();gzip.destroy();if(!res.headersSent){res.statusCode=503;res.removeHeader('Content-Encoding');res.end('Static dataset unavailable');}else res.destroy();};
      stream.on('error',fail);gzip.on('error',fail);res.on('close',()=>{stream.destroy();gzip.destroy();});
      stream.pipe(gzip).pipe(res);
    });
  };
  return {name:'atlas-public-json-compression',configureServer(server){install(server,false);},configurePreviewServer(server){install(server,true);}};
}
