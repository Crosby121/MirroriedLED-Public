(() => {
 'use strict';
 const status=document.getElementById('orderingStatus');
 if(!status)return;
 const endpoint=new URL('../customer-portal/backend/api.php?action=commerce-status',document.currentScript.src);
 fetch(endpoint,{cache:'no-store',credentials:'same-origin'}).then(r=>{if(!r.ok)throw new Error();return r.json();}).then(data=>{
  status.textContent=data.paymentsAvailable&&data.paymentMode==='live'?'Infinity Mirror and address-sign designs, customer accounts, complete approved quotes, production estimates and secure checkout are available. Final quotes are reviewed by our team before payment.':data.accountsAvailable?'Infinity Mirror and address-sign designs, customer accounts and quote requests are available. Online payments are being finalized. Please contact us for ordering help.':'Infinity Mirror and address-sign designs are available. Customer accounts and online ordering are still being connected. Please contact us for ordering help.';
 }).catch(()=>{status.textContent='Infinity Mirror and address-sign designs are available. We are checking customer accounts and online ordering. Please contact us for ordering help.';});
})();
