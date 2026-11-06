// M10: real Python clients -> real Pages route functions -> real local D1 binding.
// Everything, including Wrangler persistence, lives under a disposable TEST root.
import {it, expect} from 'vitest';
import {spawn, execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {mkdtempSync, writeFileSync, existsSync, rmSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {tmpdir} from 'node:os';
import {createServer, request as proxyRequest} from 'node:http';
import {createInterface} from 'node:readline';

const execute=promisify(execFile);
const listen=(server,port=0)=>new Promise((done,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',()=>{server.removeListener('error',reject);done(server.address().port);});});
const close=(server)=>new Promise((done)=>{server.closeAllConnections();server.close(done);});
async function stop(child){
  if(!child || child.exitCode!==null)return;
  if(process.platform==='win32')await execute('taskkill',['/PID',String(child.pid),'/T','/F']).catch(()=>{});
  else process.kill(-child.pid,'SIGTERM');
}

it('M10 clean-account lifecycle, two devices, revocation, replacement and actual offline/restore on local D1',async()=>{
  const root=mkdtempSync(join(tmpdir(),'qs-m10-'));
  const portReservation=createServer();const workerPort=await listen(portReservation);await close(portReservation);
  const proxy=createServer((incoming,outgoing)=>{
    const upstream=proxyRequest({host:'127.0.0.1',port:workerPort,path:incoming.url,method:incoming.method,headers:incoming.headers},(response)=>{
      outgoing.writeHead(response.statusCode,response.headers);response.pipe(outgoing);
    });
    upstream.on('error',()=>{if(!outgoing.headersSent)outgoing.writeHead(502);if(!outgoing.writableEnded)outgoing.end();});incoming.pipe(upstream);
  });
  const port=await listen(proxy),origin=`http://127.0.0.1:${port}`;
  const routes=[
    ['/api/auth/signup','api/auth/signup.js'],['/api/auth/verify-otp','api/auth/verify-otp.js'],
    ['/api/beta/applications','api/beta/applications.js'],['/api/operator/applications','api/operator/applications.js'],
    ['/api/operator/activations','api/operator/activations.js'],
    ...['start','confirm','status','cancel'].map((n)=>[`/api/desktop-auth/${n}`,`api/desktop-auth/${n}.js`]),
    ...['device-challenge','device-retrieve','device-status-challenge','device-status'].map((n)=>[`/api/licence/${n}`,`api/licence/${n}.js`]),
  ];
  let entry=routes.map(([,file],i)=>`import * as route${i} from ${JSON.stringify(resolve('functions',file).replaceAll('\\','/'))};`).join('\n');
  entry+=`\nimport * as applicationStatus from ${JSON.stringify(resolve('functions/api/operator/applications/[applicationId]/status.js').replaceAll('\\','/'))};`;
  for(const name of ['licence','publish','revoke']) entry+=`\nimport * as ${name} from ${JSON.stringify(resolve(`functions/api/operator/activations/[activationId]/${name}.js`).replaceAll('\\','/'))};`;
  entry+=`\nconst routes = new Map([${routes.map(([path],i)=>`[${JSON.stringify(path)},route${i}]`).join(',')}]);
export default {async fetch(request,env){
 const path=new URL(request.url).pathname;
 if(path==='/__acceptance/health')return Response.json({ok:true});
 if(path==='/__acceptance/inspect'){
  const result={};for(const name of ['beta_applications','account_entitlements','beta_activations','beta_audit_events','published_licences'])
   result[name]=(await env.BETA_DB.prepare('SELECT * FROM '+name).all()).results;
  return Response.json(result);
 }
 let route=routes.get(path),params={};
 const application=path.match(new RegExp('^/api/operator/applications/([^/]+)/status$'));
 const activation=path.match(new RegExp('^/api/operator/activations/([^/]+)/(licence|publish|revoke)$'));
 if(application){route=applicationStatus;params={applicationId:application[1]};}
 if(activation){route={licence,publish,revoke}[activation[2]];params={activationId:activation[1]};}
 const handler=route?.[request.method==='POST'?'onRequestPost':'onRequestGet'];
 return handler?handler({request,env,params}):new Response('Not found',{status:404});
}};`;
  writeFileSync(join(root,'worker.js'),entry);
  const config=join(root,'wrangler.json');
  writeFileSync(config,JSON.stringify({name:'qs-m10-acceptance',main:'worker.js',compatibility_date:'2026-09-20',send_metrics:false,
    d1_databases:[{binding:'BETA_DB',database_name:'acceptance',database_id:'00000000-0000-0000-0000-000000000000',migrations_dir:resolve('migrations')}],
    vars:{BETA_ENVIRONMENT:'local',BETA_ALLOWED_ORIGIN:origin,BETA_PRIVACY_VERSION:'draft-0.1',BETA_TERMS_VERSION:'draft-0.1',
      BETA_IDENTITY_PEPPER:'synthetic-m10-identity',AUTH_OTP_PEPPER:'synthetic-m10-otp',AUTH_EMAIL_TEST_MODE:'true',BETA_TURNSTILE_TEST_MODE:'true',
      OPERATOR_SYNC_TOKEN:'synthetic-read',OPERATOR_STATUS_SYNC_TOKEN:'synthetic-status',OPERATOR_ACTIVATION_REVOKE_TOKEN:'synthetic-revoke',
      OPERATOR_LICENCE_SYNC_TOKEN:'synthetic-metadata',OPERATOR_LICENCE_PUBLISH_TOKEN:'synthetic-publish'}}));
  const wrangler=resolve('node_modules/wrangler/bin/wrangler.js'),state=join(root,'d1');
  const environment={...process.env,CI:'true',WRANGLER_SEND_METRICS:'false',BETA_ENVIRONMENT:'local'};
  let worker,desktop,logs='';
  try{
    await execute(process.execPath,[wrangler,'d1','migrations','apply','acceptance','--local','--persist-to',state,'--config',config],{env:environment,timeout:45000});
    worker=spawn(process.execPath,[wrangler,'dev','--local','--port',String(workerPort),'--persist-to',state,'--config',config],
      {env:environment,windowsHide:true,detached:process.platform!=='win32',stdio:['ignore','pipe','pipe']});
    worker.stdout.on('data',(chunk)=>{logs=(logs+chunk).slice(-5000);});worker.stderr.on('data',(chunk)=>{logs=(logs+chunk).slice(-5000);});
    let ready=false;
    for(let i=0;i<150;i++){
      try{if((await fetch(origin+'/__acceptance/health',{signal:AbortSignal.timeout(500)})).ok){ready=true;break;}}catch{}
      if(worker.exitCode!==null)break;
      await new Promise((done)=>setTimeout(done,200));
    }
    expect(ready,logs).toBe(true);
    const venv=resolve('..','.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
    const python=process.env.QS_TEST_PYTHON || (existsSync(venv)?venv:process.platform==='win32'?'python':'python3');
    desktop=spawn(python,[resolve('..','tests/licensing/m10_acceptance_driver.py'),origin,root],
      {env:{...environment,PYTHONDONTWRITEBYTECODE:'1'},windowsHide:true,timeout:60000,stdio:['pipe','pipe','pipe']});
    let errors='',messages=[];desktop.stderr.on('data',(chunk)=>{errors+=chunk;});
    let transition=Promise.resolve();
    const lines=createInterface({input:desktop.stdout});
    lines.on('line',(line)=>{
      messages.push(line);
      transition=transition.then(async()=>{
        if(line==='M10_NETWORK_DOWN'){await close(proxy);desktop.stdin.write('offline\n');}
        if(line==='M10_NETWORK_UP'){await listen(proxy,port);desktop.stdin.write('restored\n');}
      });
    });
    const code=await new Promise((done,reject)=>{desktop.once('exit',done);desktop.once('error',reject);});
    await transition;
    expect(code,errors).toBe(0);expect(messages).toContain('M10_ACCEPTANCE_PASSED');
  }finally{
    await stop(desktop);await close(proxy);await stop(worker);
    // Only the absolute mkdtemp-owned tree is deleted, never a configured QA root.
    rmSync(root,{recursive:true,force:true,maxRetries:10,retryDelay:200});
  }
},150000);
