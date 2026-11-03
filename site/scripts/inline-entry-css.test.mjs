import test from 'node:test';
import assert from 'node:assert/strict';
import {inlineEntryCss} from './inline-entry-css.js';

test('entry stylesheet is embedded without changing other document content',()=>{
 const html='<head><link rel="stylesheet" crossorigin href="/agent-memory/assets/index-abc.css"></head>';
 const out=inlineEntryCss(html,name=>{assert.equal(name,'index-abc.css');return 'body{color:#123}'});
 assert.equal(out,'<head><style>body{color:#123}</style></head>');
 assert.throws(()=>inlineEntryCss(html,()=>'</style><script>bad</script>'));
});
