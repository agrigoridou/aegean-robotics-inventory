'use strict';
const form=document.getElementById('loginForm');
form.addEventListener('submit',async ev=>{
 ev.preventDefault();const button=document.getElementById('loginSubmit');const error=document.getElementById('loginError');
 error.style.display='none';button.disabled=true;button.textContent='Σύνδεση…';
 try{
  const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},
   credentials:'same-origin',body:JSON.stringify({username:document.getElementById('username').value.trim(),password:document.getElementById('password').value})});
  const data=await response.json();if(!response.ok)throw new Error(data.error||'Αποτυχία σύνδεσης.');
  location.assign('/');
 }catch(err){error.textContent=err.message;error.style.display='block';button.disabled=false;button.textContent='Σύνδεση →';}
});
