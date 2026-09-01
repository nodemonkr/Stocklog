import axios from 'axios'

const trimSlash=value=>String(value||'').replace(/\/+$/,'')

const configuredOrigin=trimSlash(import.meta.env.VITE_BACKEND_ORIGIN||'')
const nativeOrigin=typeof window!=='undefined'?trimSlash(window.__STOCKLOG_API_ORIGIN__||''):''

// Browser: same-origin (Vite/reverse proxy -> :8100). Installed app: the
// native shell injects the public StockLog gateway origin explicitly.
export const backendOrigin=configuredOrigin||nativeOrigin||trimSlash(window.location.origin)

export const websocketUrl=path=>{
  const wsOrigin=backendOrigin.replace(/^https:/i,'wss:').replace(/^http:/i,'ws:')
  return `${wsOrigin}${path.startsWith('/')?path:`/${path}`}`
}

const api=axios.create({
  baseURL:backendOrigin,
  timeout:120000
})

const safeText=value=>{
  try{return typeof value==='string'?value:JSON.stringify(value)}catch{return String(value||'')}
}

export const reportAdminDiagnostic=async(event,error,context={})=>{
  try{
    const token=localStorage.getItem('stocklog_token')
    if(!token)return
    const response=error?.response
    const config=error?.config||{}
    const requestId=response?.headers?.['x-request-id']||config?.headers?.['X-Request-ID']||''
    const payload={
      event:String(event||'frontend_error').slice(0,120),
      message:safeText(error?.message||response?.data?.detail||error||'').slice(0,12000),
      stack:String(error?.stack||'').slice(0,30000),
      url:String(config?.url||context?.url||window.location.href).slice(0,4000),
      method:String(config?.method||context?.method||'').toUpperCase().slice(0,20),
      status:Number(response?.status||context?.status||0)||null,
      request_id:String(requestId||'').slice(0,120),
      context:{
        ...context,
        browser_url:window.location.href,
        response:safeText(response?.data||'').slice(0,12000),
      }
    }
    await axios.post(`${backendOrigin}/api/admin/sync-error-logs/client-event`,payload,{
      timeout:5000,
      headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'}
    })
  }catch{}
}

const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))
const retryableStatus=new Set([502,503,504])

const diagnosticCooldownKey='stocklog_admin_diag_cooldowns_v1'
const shouldReportDiagnostic=(signature,cooldownMs=60000)=>{
  try{
    const now=Date.now()
    const raw=JSON.parse(localStorage.getItem(diagnosticCooldownKey)||'{}')
    const cleaned={}
    Object.entries(raw||{}).forEach(([key,value])=>{if(now-Number(value||0)<300000)cleaned[key]=Number(value||0)})
    const last=Number(cleaned[signature]||0)
    if(now-last<cooldownMs)return false
    cleaned[signature]=now
    localStorage.setItem(diagnosticCooldownKey,JSON.stringify(cleaned))
    return true
  }catch{return true}
}

api.interceptors.request.use(config=>{
  const token=localStorage.getItem('stocklog_token')
  if(token){
    config.headers.Authorization=`Bearer ${token}`
    // Remember the exact token carried by this request. When an administrator
    // changes their own password, the server rotates auth_version and returns a
    // replacement token. A late 401 from an older in-flight request must never
    // delete that newly issued token from localStorage.
    config.__stocklogAuthToken=token
  }
  config.headers['X-Request-ID']=config.headers['X-Request-ID']||`web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`
  return config
})

api.interceptors.response.use(
  response=>response,
  async error=>{
    const config=error.config||{}
    const status=Number(error.response?.status||0)
    const method=String(config.method||'get').toLowerCase()

    // One short retry for idempotent reads shields the UI from transient proxy/API hiccups.
    if(
      method==='get'
      && !config.__stocklogNoRetry
      && !config.__stocklogRetried
      && (!error.response||retryableStatus.has(status)||error.code==='ECONNABORTED')
    ){
      config.__stocklogRetried=true
      await sleep(450)
      return api.request(config)
    }

    const currentToken=localStorage.getItem('stocklog_token')
    const requestToken=String(config.__stocklogAuthToken||'')
    if(status===401&&currentToken&&(!requestToken||currentToken===requestToken)){
      localStorage.removeItem('stocklog_token')
      window.dispatchEvent(new CustomEvent('stocklog:auth-expired'))
    }

    if(status===403&&error.response?.data?.code==='ip_not_allowed'){
      window.dispatchEvent(new CustomEvent('stocklog:access-denied',{detail:error.response.data}))
    }

    const url=String(config.url||'')
    const isDiagnosticTransport=url.includes('/api/admin/sync-error-logs')
    if(
      !config.__skipDiagnostic
      && !isDiagnosticTransport
      && url.includes('/api/admin/')
      && /(sync|market-data|theme-normalize|classification)/i.test(url)
      && status!==401
    ){
      const signature=[url,method,status||0,error.code||'',String(error.message||'').slice(0,120)].join('|')
      if(shouldReportDiagnostic(signature,60000)){
        config.__stocklogDiagnosticReported=true
        reportAdminDiagnostic('ADMIN_SYNC_API_ERROR',error,{url,method,phase:'axios_interceptor',dedupe_window_ms:60000}).catch(()=>{})
      }
    }

    return Promise.reject(error)
  }
)

export default api
