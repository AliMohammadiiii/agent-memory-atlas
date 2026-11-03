import {readFileSync,writeFileSync} from 'node:fs';
import {basename,join,resolve} from 'node:path';

// The atlas uses one small entry stylesheet. Embed it in the document so the
// first render does not wait for an extra round trip on slow connections.
export function inlineEntryCss(html,readAsset){
 const link=/<link\s+rel="stylesheet"\s+crossorigin\s+href="([^"]+)"\s*\/?\s*>/;
 const match=html.match(link);
 if(!match)throw new Error('Entry stylesheet link was not found');
 const css=readAsset(basename(match[1]));
 if(typeof css!=='string'||/<\/style/i.test(css))throw new Error('Entry stylesheet cannot be safely embedded');
 return html.replace(link,`<style>${css}</style>`);
}
export default function inlineEntryCssPlugin(){
 let outDir;
 return {name:'atlas-inline-entry-css',apply:'build',configResolved(config){outDir=resolve(config.root,config.build.outDir);},closeBundle(){
  const index=join(outDir,'index.html'),html=readFileSync(index,'utf8');
  const result=inlineEntryCss(html,name=>readFileSync(join(outDir,'assets',name),'utf8'));
  writeFileSync(index,result);
 }};
}
