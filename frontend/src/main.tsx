import React from 'react';
import { createRoot } from 'react-dom/client';
import { PublicClientApplication } from '@azure/msal-browser';
import App from './App.tsx';
import './style.css';

const cfg={auth:{clientId:import.meta.env.VITE_ENTRA_CLIENT_ID||'00000000-0000-0000-0000-000000000000',authority:`https://login.microsoftonline.com/${import.meta.env.VITE_ENTRA_TENANT_ID||'common'}`,redirectUri:window.location.origin},cache:{cacheLocation:'sessionStorage'}};
const msal=new PublicClientApplication(cfg);
async function start(){
 let token='';
 if(import.meta.env.VITE_DEMO_MODE!=='true' && import.meta.env.VITE_ENTRA_CLIENT_ID){
  await msal.initialize();const redirect=await msal.handleRedirectPromise();const account=redirect?.account||msal.getAllAccounts()[0];
  if(account){try{token=(await msal.acquireTokenSilent({account,scopes:[import.meta.env.VITE_ENTRA_API_SCOPE||`api://${import.meta.env.VITE_ENTRA_CLIENT_ID}/access_as_user`]})).accessToken}catch{}}
 }
 createRoot(document.getElementById('root')).render(<React.StrictMode><App initialToken={token} msal={msal}/></React.StrictMode>);
}
start();
