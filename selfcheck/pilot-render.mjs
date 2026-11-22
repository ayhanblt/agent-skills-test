import {bundle} from '@remotion/bundler';
import {selectComposition, renderMedia} from '@remotion/renderer';
import fs from 'node:fs';
const props=JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const serveUrl=await bundle({entryPoint:'./video.jsx'});
const browserExecutable=process.env.PILOT_CHROME;
const composition=await selectComposition({serveUrl,id:'Info',inputProps:props,browserExecutable});
await renderMedia({serveUrl,composition,inputProps:props,outputLocation:process.argv[3],
  codec:'h264',browserExecutable,concurrency:2});
