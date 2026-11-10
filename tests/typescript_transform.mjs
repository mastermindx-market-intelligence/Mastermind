/** Test-only real-source compiler, using the product's locked Vite transformer
 * only when Node explicitly no longer supports its historical transform mode. */
import fs from 'node:fs';
import path from 'node:path';
import {createRequire,stripTypeScriptTypes} from 'node:module';
import {pathToFileURL} from 'node:url';
export async function sourceTransformer(sourceRoot) {
  try {
    stripTypeScriptTypes('const compilerProbe: number = 1;', {mode:'transform'});
    return (_filename,source)=>stripTypeScriptTypes(source,{mode:'transform'});
  } catch(error) {
    if(error?.code!=='ERR_INVALID_ARG_VALUE'||!String(error.message).includes('options.mode'))throw error;
  }
  const app=path.dirname(sourceRoot), require=createRequire(path.join(app,'package.json'));
  const installed=JSON.parse(fs.readFileSync(require.resolve('rolldown/package.json'),'utf8'));
  const lock=JSON.parse(fs.readFileSync(path.join(app,'package-lock.json'),'utf8'));
  if(installed.version!==lock.packages['node_modules/rolldown']?.version)throw Error('product TypeScript transformer differs from its lock');
  const {transformSync}=await import(pathToFileURL(require.resolve('rolldown/experimental')));
  return (filename,source)=>{
    const result=transformSync(filename,source,{lang:'ts',target:'es2022'});
    if(result.errors.length)throw Error('actual TypeScript source compilation refused');
    return result.code;
  };
}
