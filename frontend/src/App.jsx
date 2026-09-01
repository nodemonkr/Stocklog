import {useEffect,useMemo,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import * as echarts from 'echarts'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  ArrowUpDown,
  BarChart3,
  ChevronRight,
  CircleDollarSign,
  CalendarClock,
  Clock3,
  Edit3,
  Trash2,
  Info,
  Fingerprint,
  Compass,
  CheckCircle2,
  RotateCcw,
  Sparkles,
  ExternalLink,
  LogOut,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  UserRound,
  X,
  TrendingUp,
  Users,
  Crown,
  Gift,
  Landmark,
  SlidersHorizontal,
  LockKeyhole,
  KeyRound,
  Eye,
  EyeOff,
  Gauge,
  Globe2,
  Smartphone,
  CalendarDays
} from 'lucide-react'
import api,{websocketUrl,reportAdminDiagnostic} from './api'

const won=n=>Number(n||0).toLocaleString('ko-KR')

// The mobile app embeds this SPA locally and completes OAuth in the system browser.
// Browser builds keep using window.location.origin exactly as before.
const socialReturnUrl=()=>window.__STOCKLOG_NATIVE_RETURN_URL__||window.location.origin

const flowQty=value=>{
 const n=Number(value||0)
 if(!Number.isFinite(n))return '-'
 const sign=n>0?'+':n<0?'-':''
 const abs=Math.abs(n)
 if(abs>=100_000_000)return `${sign}${(abs/100_000_000).toFixed(abs>=1_000_000_000?1:2)}억주`
 if(abs>=10_000)return `${sign}${(abs/10_000).toFixed(abs>=1_000_000?1:0)}만주`
 return `${sign}${Math.round(abs).toLocaleString('ko-KR')}주`
}

const flowQtyExact=value=>{
 const n=Number(value||0)
 if(!Number.isFinite(n))return '-'
 const sign=n>0?'+':n<0?'-':''
 return `${sign}${Math.abs(Math.round(n)).toLocaleString('ko-KR')}주`
}

const flowDate=value=>value?String(value).replace(/-/g,'.').slice(5):'-'

function TradeFillToast({toast,onClose}){
 if(!toast)return null
 const side=toast.side==='sell'?'sell':'buy'
 const source=toast.source==='auto'?'자동':toast.source==='manual'?'수동':''
 const title=`${source?`${source} `:''}${side==='buy'?'매수':'매도'} ${toast.partial?'부분 체결':'체결 완료'}`
 return createPortal(
  <div className={`trade-fill-toast ${side}`} role="status" aria-live="polite">
   <span className="trade-fill-toast-icon"><CheckCircle2 size={18}/></span>
   <div className="trade-fill-toast-copy"><b>{title}</b><span>{toast.name||toast.code||'종목'} · {won(toast.quantity)}주 · {won(toast.price)}원{Number(toast.amount||0)>0?` · ${won(toast.amount)}원`:''}</span><small>{toast.time?new Date(toast.time).toLocaleString('ko-KR'):'방금 체결 확인'}</small></div>
   <button type="button" onClick={onClose} aria-label="알림 닫기"><X size={15}/></button>
  </div>,
  document.body
 )
}

function GlobalTradeFillNotifier({enabled=true}){
 const [toast,setToast]=useState(null)
 const seenRef=useRef(new Map())
 const queueRef=useRef([])
 const activeRef=useRef(false)
 const timerRef=useRef(null)
 const initializedRef=useRef(false)

 const showNext=()=>{
  if(activeRef.current||!queueRef.current.length)return
  const next=queueRef.current.shift()
  activeRef.current=true
  setToast(next)
  timerRef.current=setTimeout(()=>{
   setToast(null)
   activeRef.current=false
   timerRef.current=setTimeout(showNext,180)
  },5500)
 }

 useEffect(()=>{
  if(!enabled)return
  seenRef.current.clear()
  initializedRef.current=false
  let stopped=false
  let running=false
  const poll=async()=>{
   if(stopped||running)return
   running=true
   try{
    const r=await api.get('/api/trading/fill-events')
    if(stopped)return
    const rows=Array.isArray(r.data?.items)?r.data.items.slice().reverse():[]
    const discovered=[]
    if(!initializedRef.current){
     rows.forEach(row=>{
      const key=String(row.id||`${row.order_no||''}:${row.code||''}:${row.time||''}:${row.price||0}`)
      seenRef.current.set(key,Math.max(0,Number(row.quantity||0)))
     })
     initializedRef.current=true
     return
    }
    rows.forEach(row=>{
     const key=String(row.id||`${row.order_no||''}:${row.code||''}:${row.time||''}:${row.price||0}`)
     const current=Math.max(0,Number(row.quantity||0))
     const previous=seenRef.current.get(key)
     if(previous===undefined){
      seenRef.current.set(key,current)
      if(current>0)discovered.push({...row,quantity:current,amount:current*Number(row.price||0)})
      return
     }
     if(current>previous){
      const delta=current-previous
      seenRef.current.set(key,current)
      discovered.push({...row,quantity:delta,amount:delta*Number(row.price||0)})
     }
    })
    if(discovered.length){
     discovered.forEach(item=>{
      queueRef.current.push(item)
      window.dispatchEvent(new CustomEvent('stocklog:trade-filled',{detail:item}))
     })
     showNext()
    }
   }catch{}
   finally{running=false}
  }
  poll()
  const id=setInterval(poll,4000)
  const onVisible=()=>{if(document.visibilityState==='visible')poll()}
  document.addEventListener('visibilitychange',onVisible)
  return()=>{stopped=true;clearInterval(id);document.removeEventListener('visibilitychange',onVisible);if(timerRef.current)clearTimeout(timerRef.current);queueRef.current=[];activeRef.current=false}
 },[enabled])

 return <TradeFillToast toast={toast} onClose={()=>{if(timerRef.current)clearTimeout(timerRef.current);setToast(null);activeRef.current=false;timerRef.current=setTimeout(showNext,120)}}/>
}

const STOCKLOG_PAGE_IDS=new Set(['smart','themes','flow','trading','trading-auto','auto-settings','portfolio','settings','profile','account-profile','admin'])
const INVESTMENT_PAGE_IDS=new Set(['trading','trading-auto','auto-settings','portfolio'])
const STOCKLOG_PAGE_LABELS={
 smart:'스마트 분석',themes:'인기테마 분석',flow:'수급 분석',trading:'증권투자(수동)',
 'trading-auto':'증권투자(자동)','auto-settings':'자동매매 설정',portfolio:'포트폴리오',
 settings:'계정 연동',profile:'투자성향 분석','account-profile':'계정 프로필',admin:'관리자',
}
const LEGACY_LIVE_PAGE_MAP={
 'live-trading':'trading',
 'live-trading-auto':'trading-auto',
 'live-auto-settings':'auto-settings',
}
const availableInvestmentEnvironment=(requested,user)=>{
 const preferred=requested==='live'?'live':'mock'
 if(!user)return preferred
 const canMock=user?.features?.mock_trading?.enabled!==false
 const canLive=user?.features?.live_trading?.enabled!==false
 if(preferred==='live'&&canLive)return 'live'
 if(preferred==='mock'&&canMock)return 'mock'
 if(canMock)return 'mock'
 if(canLive)return 'live'
 return preferred
}
const readStocklogRoute=()=>{
 const params=new URLSearchParams(window.location.search)
 const requested=params.get('page')||'smart'
 const legacyPage=LEGACY_LIVE_PAGE_MAP[requested]
 const raw=legacyPage||requested
 const page=STOCKLOG_PAGE_IDS.has(raw)?raw:'smart'
 const code=String(params.get('stock')||'').trim()
 const environment=legacyPage||params.get('environment')==='live'?'live':'mock'
 const market=params.get('market')==='overseas'?'overseas':'domestic'
 return {page,environment,market,legacy:Boolean(legacyPage),detail:code?{code,smartMode:params.get('smart_mode')||'ai'}:null}
}

const financialAmount=value=>{
 if(value===null||value===undefined||value==='')return '-'
 const n=Number(value)
 if(!Number.isFinite(n))return '-'
 const abs=Math.abs(n)
 const sign=n<0?'-':''

 // 공식 공시 amounts are KRW.
 if(abs>=1_000_000_000_000){
   return `${sign}${(abs/1_000_000_000_000).toFixed(1)}조원`
 }
 if(abs>=100_000_000){
   return `${sign}${(abs/100_000_000).toFixed(1)}억원`
 }
 if(abs>=10_000){
   return `${sign}${(abs/10_000).toFixed(1)}만원`
 }
 return `${Math.round(n).toLocaleString('ko-KR')}원`
}
const pct=n=>`${Number(n||0).toFixed(2)}%`
const sentimentName={positive:'긍정',neutral:'관망',negative:'부정'}


const oneDecimal=value=>{
 if(value===null||value===undefined||value==='')return '-'
 const n=Number(value)
 return Number.isFinite(n)?n.toFixed(1):'-'
}

const cleanMultiline=value=>String(value??'').replace(/\\n/g,'\n').trim()

const metricValue=(value,suffix='')=>{
 const v=oneDecimal(value)
 return v==='-'?'-':`${v}${suffix}`
}

const sentimentScore100=value=>{
 const n=Number(value||0)
 return Math.round(Math.max(-1,Math.min(1,n))*100)
}

const deltaText=value=>{
 if(value===null||value===undefined||Number.isNaN(Number(value))){
   return '비교 데이터 없음'
 }
 const n=Number(value)
 return `${n>0?'+':''}${n.toFixed(1)}%`
}

const AI_VIEW_LABEL={
 positive:'긍정',
 neutral:'관망',
 negative:'주의'
}

const AI_AGREEMENT_LABEL={
 agree:'현재 흐름과 일치',
 partial:'일부 신호 확인',
 disagree:'추가 확인 필요'
}

const AI_VERDICT_LABEL={
 buy_bias:'매수 추천',
 wait:'관망',
 sell_bias:'매도 추천'
}

const AI_CONSENSUS_LABEL={
 aligned:'분석 의견 일치',
 mixed:'분석 의견 비교/합의',
 single_model:'단일 분석 결과'
}

const aiViewClass=value=>
 value==='positive'
  ? 'positive'
  : value==='negative'
    ? 'negative'
    : 'neutral'


const METRIC_HELP={
 PER:{title:'PER · 이익에 비해 주가가 비싼지',body:'주가가 1주당 이익(EPS)의 몇 배인지 보는 값입니다. 같은 업종끼리 비교할 때 낮으면 가격 부담이 적은 편이고 높으면 미래 성장을 많이 기대하고 있는 가격일 수 있습니다. 적자기업은 PER만으로 판단하면 안 됩니다.'},
 PBR:{title:'PBR · 회사 순자산에 비해 주가가 비싼지',body:'주가가 1주당 순자산(BPS)의 몇 배인지 보는 값입니다. 보통 같은 업종에서 낮을수록 자산 대비 가격 부담이 적지만, PBR이 낮아도 회사가 돈을 잘 못 벌면 싼 이유가 있을 수 있어 ROE와 같이 봐야 합니다.'},
 EPS:{title:'EPS · 주식 1주가 벌어들이는 이익',body:'회사가 번 순이익을 전체 주식 수로 나눈 값입니다. 일반적으로 EPS가 크고 꾸준히 증가하면 회사가 주당 더 많은 이익을 만들고 있다는 뜻입니다. 단, 다른 회사와 절대값만 비교하기보다 같은 회사의 과거 흐름을 보는 것이 좋습니다.'},
 BPS:{title:'BPS · 주식 1주당 회사의 순자산',body:'회사의 자산에서 빚을 뺀 금액을 주식 수로 나눈 값입니다. 현재 주가와 비교해 PBR을 계산할 때 사용합니다. BPS가 높다고 무조건 좋은 것은 아니고, 이 자산으로 이익을 얼마나 내는지 ROE를 같이 봐야 합니다.'},
 ROE:{title:'ROE · 내 돈을 얼마나 효율적으로 굴리는지',body:'주주가 넣은 자본으로 회사가 얼마나 이익을 냈는지 보여줍니다. 같은 업종에서 높고 여러 해 안정적으로 유지될수록 좋은 편입니다. 너무 갑자기 높아졌다면 일회성 이익인지 확인하는 것이 좋습니다.'},
 '배당수익률':{title:'배당수익률 · 주가 대비 받는 배당금',body:'현재 주가에 비해 1년에 받을 수 있는 배당금 비율입니다. 높을수록 배당 매력은 커지지만, 일회성 배당이나 실적 악화로 주가가 급락해 숫자만 높아진 경우는 주의해야 합니다.'},
 '매출 성장률':{title:'매출 성장률 · 회사가 얼마나 커지고 있는지',body:'회사가 파는 제품·서비스의 전체 매출이 이전 기간보다 얼마나 늘었는지 보여줍니다. 플러스가 이어지면 사업 규모가 커지는 흐름으로 볼 수 있고, 마이너스가 오래 이어지면 성장 둔화를 확인해야 합니다.'},
 '영업이익률':{title:'영업이익률 · 본업으로 얼마나 남기는지',body:'매출 100원 중 본업에서 몇 원을 이익으로 남겼는지 보여줍니다. 같은 업종에서 높고 안정적일수록 비용 관리와 사업 경쟁력이 좋은 편입니다.'},
 '매출':{title:'매출',body:'회사가 제품이나 서비스를 팔아 벌어들인 전체 금액입니다. 매출이 꾸준히 늘면서 이익도 같이 늘어나는지를 보는 것이 중요합니다.'},
 '영업이익':{title:'영업이익',body:'매출에서 제품 원가와 직원비·마케팅비 같은 영업비용을 뺀 본업의 이익입니다. 꾸준히 플러스이고 증가하는 흐름이 일반적으로 좋습니다.'},
 '순이익':{title:'순이익',body:'본업뿐 아니라 이자·세금·기타 손익까지 모두 반영하고 최종적으로 남은 이익입니다. 일회성 이익 때문에 갑자기 늘어난 것은 아닌지 같이 확인하는 것이 좋습니다.'},
 '자본':{title:'자본',body:'회사가 가진 전체 자산에서 부채를 뺀 주주 몫입니다. 자본이 꾸준히 늘고 부채가 과도하지 않은지 확인하면 회사의 기초 체력을 이해하는 데 도움이 됩니다.'},
 '밸류에이션':{title:'밸류에이션 · 지금 가격이 부담스러운지',body:'PER·PBR 같은 값을 이용해 현재 주가가 회사의 이익과 자산에 비해 비싼지 싼지 살펴보는 과정입니다. 숫자 하나보다 같은 업종과 과거 수준을 함께 비교해야 합니다.'},
 '사업성과':{title:'사업성과',body:'매출과 영업이익이 실제로 늘고 있는지 확인해 회사 본업이 좋아지는지 보는 항목입니다.'},
 '재무 건전성/이익 흐름':{title:'재무와 이익 흐름',body:'회사가 꾸준히 돈을 벌고 있는지, 자산과 부채 구조에 무리가 없는지를 초보자 관점에서 확인하는 항목입니다.'},
 '시장 흐름/뉴스':{title:'주가 흐름과 뉴스',body:'최근 주가가 강한지 약한지, 외국인·기관 수급과 뉴스가 같은 방향인지 확인합니다. 모멘텀은 쉽게 말해 최근 주가의 움직임이 이어지는 힘입니다.'},
 '증권사 리포트':{title:'증권사 리포트',body:'증권사가 공개한 기업 분석 자료입니다. 목표주가 숫자만 보기보다 왜 긍정 또는 부정으로 봤는지 내용 요약을 확인하는 것이 좋습니다.'},
 '뉴스 심리':{title:'뉴스 분위기',body:'최근 뉴스 내용을 긍정·관망·부정으로 나눠 보여줍니다. 점수가 아니라 어떤 사건 때문에 그런 방향으로 분류됐는지를 읽는 것이 중요합니다.'},
 '분기별 재무제표':{title:'분기별 재무제표',body:'회사의 매출·영업이익·순이익이 분기마다 어떻게 변했는지 확인합니다. 한 분기 숫자보다 여러 분기의 방향이 더 중요합니다.'},
 '수급 점수':{title:'수급 흐름',body:'외국인과 기관 등이 최근 주식을 계속 사고 있는지 파는지 확인합니다. 모멘텀과 함께 보면 단기적으로 돈이 들어오는 흐름인지 이해하기 쉽습니다.'},
 '수급':{title:'수급 · 누가 사고팔고 있는지',body:'외국인·기관·개인이 최근 이 종목을 얼마나 사고팔았는지 보는 정보입니다. 외국인과 기관의 순매수가 여러 날 이어지면 매수세가 들어오는 흐름으로 볼 수 있고, 반대로 계속 순매도하면 주가에 부담이 될 수 있습니다. 수급만으로 매수 여부를 결정하지 말고 실적과 주가 흐름을 함께 확인하세요.'}
}
function MetricInfo({metric,help=null}){
 const item=help||METRIC_HELP[metric]
 const triggerRef=useRef(null)
 const [tip,setTip]=useState(null)

 if(!item)return null

 const showTip=()=>{
  const rect=triggerRef.current?.getBoundingClientRect()
  if(!rect)return

  const viewportWidth=window.innerWidth
  const viewportHeight=window.innerHeight
  const width=Math.min(
   330,
   Math.max(220,viewportWidth-24)
  )

  let left=(
   rect.left
   + rect.width/2
   - width/2
  )

  left=Math.max(
   12,
   Math.min(
    left,
    viewportWidth-width-12
   )
  )

  const estimatedHeight=150
  const above=(
   rect.bottom+estimatedHeight+14
   > viewportHeight
   && rect.top>estimatedHeight+20
  )

  setTip({
   left,
   width,
   top:above
    ? rect.top-9
    : rect.bottom+9,
   placement:above
    ? 'above'
    : 'below'
  })
 }

 const hideTip=()=>{
  setTip(null)
 }

 const tooltip=tip&&typeof document!=='undefined'
  ? createPortal(
     <div
      className={`metric-tooltip-portal ${tip.placement}`}
      style={{
       left:`${tip.left}px`,
       top:`${tip.top}px`,
       width:`${tip.width}px`
      }}
      role="tooltip"
     >
      <b>{item.title}</b>
      <span>{item.body}</span>
     </div>,
     document.body
    )
  : null

 return <>
  <span className="metric-info">
   <button
    ref={triggerRef}
    type="button"
    className="metric-info-trigger"
    aria-label={`${item.title} 설명`}
    onMouseEnter={showTip}
    onMouseLeave={hideTip}
    onFocus={showTip}
    onBlur={hideTip}
    onClick={showTip}
   >
    <Info size={12}/>
   </button>
  </span>
  {tooltip}
 </>
}

function AutoMonitorDetailTooltip({id,children,content}){
 const triggerRef=useRef(null)
 const [open,setOpen]=useState(false)
 const [position,setPosition]=useState({left:12,top:12,width:390,maxHeight:320,placement:'below'})
 const updatePosition=()=>{
  const rect=triggerRef.current?.getBoundingClientRect?.()
  if(!rect||typeof window==='undefined')return
  const viewportWidth=window.innerWidth||document.documentElement.clientWidth||320
  const viewportHeight=window.innerHeight||document.documentElement.clientHeight||600
  const width=Math.min(410,Math.max(120,viewportWidth-24))
  const left=Math.max(12,Math.min(rect.left+rect.width/2-width/2,viewportWidth-width-12))
  const belowSpace=Math.max(0,viewportHeight-rect.bottom-18)
  const aboveSpace=Math.max(0,rect.top-18)
  const placement=belowSpace>=300||belowSpace>=aboveSpace?'below':'above'
  const maxHeight=Math.max(40,placement==='below'?belowSpace:aboveSpace)
  setPosition({left,top:placement==='below'?rect.bottom+9:rect.top-9,width,maxHeight,placement})
 }
 useEffect(()=>{
  if(!open)return
  updatePosition()
  const sync=()=>updatePosition()
  window.addEventListener('resize',sync)
  window.addEventListener('scroll',sync,true)
  return()=>{window.removeEventListener('resize',sync);window.removeEventListener('scroll',sync,true)}
 },[open])
 const show=()=>{updatePosition();setOpen(true)}
 const hide=()=>setOpen(false)
 return <>
  <button ref={triggerRef} type="button" className="auto-monitor-reason-trigger" aria-describedby={open?id:undefined} aria-expanded={open?'true':'false'} onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide} onClick={e=>{e.stopPropagation();show()}}>{children}</button>
  {open&&typeof document!=='undefined'&&createPortal(<div className={`auto-monitor-detail-tooltip portal ${position.placement}`} id={id} role="tooltip" style={{left:`${position.left}px`,top:`${position.top}px`,width:`${position.width}px`,maxHeight:`${position.maxHeight}px`}}>{content}</div>,document.body)}
 </>
}

const smartUpdatedText=value=>{
 if(!value)return '업데이트 시각 없음'
 try{
  const raw=String(value)
  // StockLog DB timestamps are stored as local server datetimes without an
  // offset in several legacy tables.  Preserve their displayed clock value
  // instead of accidentally shifting a naive timestamp in the browser.
  const match=raw.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  if(match)return `업데이트 ${match[2]}/${match[3]} ${match[4]}:${match[5]}`
  const d=new Date(raw)
  if(Number.isNaN(d.getTime()))return '업데이트 시각 없음'
  return `업데이트 ${d.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})}`
 }catch{return '업데이트 시각 없음'}
}

const financialMetricSummary=(label,delta)=>{if(delta===null||delta===undefined||Number.isNaN(Number(delta)))return '동일 기준으로 비교할 수 있는 이전 값이 없습니다.';const n=Number(delta);const meaning={'매출':n>0?'매출 규모가 확대되었습니다.':n<0?'매출 규모가 축소되었습니다.':'매출 규모가 유지되었습니다.','영업이익':n>0?'본업의 이익 흐름이 개선되었습니다.':n<0?'본업의 이익 흐름이 감소했습니다.':'본업의 이익 흐름이 유지되었습니다.','순이익':n>0?'최종 이익이 증가했습니다.':n<0?'최종 이익이 감소했습니다.':'최종 이익이 유지되었습니다.','자본':n>0?'순자산 규모가 늘었습니다.':n<0?'순자산 규모가 줄었습니다.':'순자산 규모가 유지되었습니다.'}[label]||'';return meaning}
const financialPeriodSummary=f=>{
 const entries=[['매출',f.change?.revenue],['영업이익',f.change?.operating_profit],['순이익',f.change?.net_income]]
  .filter(([,v])=>v!==null&&v!==undefined&&Number.isFinite(Number(v)))
 if(!entries.length)return '동일 기준의 비교값이 부족해 증감 방향을 표시하지 않았습니다.'
 const up=entries.filter(([,v])=>Number(v)>0).map(([l])=>l)
 const down=entries.filter(([,v])=>Number(v)<0).map(([l])=>l)
 const parts=[]
 if(up.length)parts.push(`${up.join('/')} 증가`)
 if(down.length)parts.push(`${down.join('/')} 감소`)
 if(!parts.length)parts.push('주요 손익 항목 변화가 제한적')
 const basis=f.comparison_periods?.revenue||f.comparison_period||'전년 동일 공시기간'
 return `${basis} 대비 ${parts.join(', ')}했습니다.`
}


const publicUiText=value=>{
 if(value===null||value===undefined)return ''
 return String(value)
  .replace(/\b(?:ka|kt)\d{5}\b/gi,'내부 조회')
  .replace(/\b0B\b/gi,'실시간 시세')
  .replace(/\bTR\b/gi,'조회')
  .replace(/cont-yn\s*\/\s*next-key/gi,'연속 확인')
  .replace(/공식 공시|공식 공시/gi,'공식 공시')
  .replace(/키움|Kiwoom|연결 서비스/gi,'연결 서비스')
 .replace(/OpenDART|DART/gi,'기업 정보')
  .replace(/Google AI Studio/gi,'StockLog Gbot')
  .replace(/\b(?:Gemini|Ollama)(?:[-_.\w]*)\b/gi,'StockLog Gbot')
  .replace(/StockLog Obot|\bObot\b/gi,'StockLog Gbot')
  .replace(/MySQL/gi,'저장 데이터')
  .replace(/REST\s*API|API/gi,'연결')
  .replace(/정량(?:적)?/g,'기초')
  .replace(/캐시/g,'최근 결과')
  .replace(/동기화/g,'업데이트')
  .replace(/수집/g,'반영')
  .replace(/크롤링|크롤러/g,'정보 확인')
  .replace(/가중치/g,'평가 기준')
  .replace(/매수\s*우위/g,'매수 추천')
  .replace(/매도\s*우위/g,'매도 추천')
  .replace(/상승\s*우위/g,'상승 추천')
  .replace(/명확도/g,'점수')
  .replace(/\uC911\uB9BD/g,'관망')
  .replace(/\s*·\s*/g,' / ')
}
const autoTradingErrorText=value=>{
 const raw=String(value||'')
 if(/429|too many requests|resource_exhausted|rate[_ -]?limit|quota[_ -]?exceeded|요청 한도|안전 한도/i.test(raw)){
  return 'StockLog Gbot 요청 한도에 일시적으로 도달했습니다. 이번 회차는 주문하지 않고 대기하며 다음 재시도 시점에 자동으로 다시 판단합니다.'
 }
 return publicUiText(raw)
}

const publicMultiline=value=>cleanMultiline(publicUiText(value))

const orderSideLabel=value=>{
 const raw=String(value||'').trim()
 const lower=raw.toLowerCase()

 if(
  raw.includes('매수')
  || lower==='buy'
  || lower==='b'
  || raw==='2'
  || raw==='+2'
 )return '매수'

 if(
  raw.includes('매도')
  || lower==='sell'
  || lower==='s'
  || raw==='1'
  || raw==='-1'
 )return '매도'

 return raw||'주문'
}

const orderSideClass=value=>
 orderSideLabel(value)==='매수'
  ? 'buy'
  : orderSideLabel(value)==='매도'
    ? 'sell'
    : 'neutral'

const reservationStatusClass=value=>{
 const status=String(value||'')

 if(status==='active')return 'active'
 if(status==='triggered')return 'triggered'
 if(status==='failed')return 'failed'
 if(status==='cancelled'||status==='expired')return 'closed'

 return 'waiting'
}

const orderTimeText=value=>{
 const raw=String(value||'').trim()
 if(!raw)return '-'
 const digits=raw.replace(/\D/g,'')
 if(digits.length===6){
  return `${digits.slice(0,2)}:${digits.slice(2,4)}:${digits.slice(4,6)}`
 }
 return publicUiText(raw)
}


let stocklogDialogListener=null

function openStocklogDialog(options){
 return new Promise(resolve=>{
   if(!stocklogDialogListener){
     resolve(
       options.type==='confirm'
         ? false
         : true
     )
     return
   }

   stocklogDialogListener({
     ...options,
     title:publicUiText(options.title),
     message:publicUiText(options.message),
     resolve
   })
 })
}

function showMessage(
 message,
 title='안내',
 tone='info'
){
 return openStocklogDialog({
   type:'message',
   title,
   message,
   tone
 })
}

function askConfirm(
 message,
 title='확인',
 tone='warning'
){
 return openStocklogDialog({
   type:'confirm',
   title,
   message,
   tone
 })
}

function GlobalDialog(){
 const [dialog,setDialog]=useState(null)

 useEffect(()=>{
   stocklogDialogListener=setDialog

   return()=>{
     if(
       stocklogDialogListener===setDialog
     ){
       stocklogDialogListener=null
     }
   }
 },[])

 if(!dialog)return null

 const finish=result=>{
   const resolve=dialog.resolve
   setDialog(null)
   resolve(result)
 }

 return <div
   className="pretty-dialog-backdrop"
   onMouseDown={e=>{
     if(
       e.target===e.currentTarget
       && dialog.type!=='confirm'
     ){
       finish(true)
     }
   }}
 >
   <div className={
     `pretty-dialog ${
       dialog.tone||'info'
     }`
   }>
     <div className="pretty-dialog-icon">
       {dialog.tone==='danger'
         ? '!'
         : dialog.tone==='success'
           ? '✓'
           : dialog.type==='confirm'
             ? '?'
             : 'i'}
     </div>

     <div className="pretty-dialog-copy">
       <h3>{dialog.title||'안내'}</h3>
       <p>{dialog.message}</p>
     </div>

     <div className="pretty-dialog-actions">
       {dialog.type==='confirm'&&
         <button
           className="secondary"
           onClick={()=>finish(false)}
         >
           취소
         </button>
       }

       <button
         className={
           dialog.tone==='danger'
             ? 'primary danger-button'
             : 'primary'
         }
         onClick={()=>finish(true)}
       >
         {dialog.type==='confirm'
           ? '확인'
           : '닫기'}
       </button>
     </div>
   </div>
 </div>
}

function Login({onLogin}){
 const adminEntry=useMemo(()=>new URLSearchParams(window.location.search).get('admin')==='1',[])
 const [mode,setMode]=useState(adminEntry?'legacy':'login')
 const [form,setForm]=useState({
  username:'',password:'',password_confirm:'',name:'',gender:'',birth_year:'',birth_month:'',birth_day:'',phone_number:'',
  age_14_or_older:false,terms_consent:false,privacy_consent:false
 })
 const [err,setErr]=useState('')
 const [busy,setBusy]=useState(false)
 const [signupStep,setSignupStep]=useState('account')
 const [testQuestions,setTestQuestions]=useState(()=>shuffleInvestmentQuestions())
 const [current,setCurrent]=useState(0)
 const [answers,setAnswers]=useState({})
 const [profilePayload,setProfilePayload]=useState(null)
 const [socialProviders,setSocialProviders]=useState({})
 const [socialBusy,setSocialBusy]=useState('')
 const [socialSignup,setSocialSignup]=useState(null)
 const [fieldTouched,setFieldTouched]=useState({})
 const [usernameCheck,setUsernameCheck]=useState({value:'',checking:false,available:null,message:''})
 const [showPassword,setShowPassword]=useState(false)
 const questionAdvanceTimer=useRef(null)
 const usernameCheckSeq=useRef(0)

 const currentYear=new Date().getFullYear()
 const birthYears=useMemo(()=>Array.from({length:107},(_,i)=>currentYear-14-i),[currentYear])
 const birthDayCount=useMemo(()=>{
  const year=Number(form.birth_year)||2000
  const month=Number(form.birth_month)||1
  return new Date(year,month,0).getDate()
 },[form.birth_year,form.birth_month])
 const birthDays=useMemo(()=>Array.from({length:birthDayCount},(_,i)=>i+1),[birthDayCount])
 const pad2=value=>String(value).padStart(2,'0')
 const touchField=field=>setFieldTouched(v=>({...v,[field]:true}))
 const updateField=(field,value)=>{
  setForm(v=>({...v,[field]:value}))
  touchField(field)
  if(err)setErr('')
 }
 const formatSignupPhone=value=>{
  let digits=String(value||'').replace(/\D/g,'')
  if(digits.startsWith('82')&&digits.length>=11)digits=`0${digits.slice(2)}`
  digits=digits.slice(0,11)
  if(digits.length<=3)return digits
  if(digits.length<=7)return `${digits.slice(0,3)}-${digits.slice(3)}`
  if(digits.length===10)return `${digits.slice(0,3)}-${digits.slice(3,6)}-${digits.slice(6)}`
  return `${digits.slice(0,3)}-${digits.slice(3,7)}-${digits.slice(7)}`
 }
 const birthValidation=useMemo(()=>{
  const year=Number(form.birth_year),month=Number(form.birth_month),day=Number(form.birth_day)
  if(!year||!month||!day)return {valid:false,message:'생년월일을 모두 선택해주세요.'}
  const born=new Date(year,month-1,day)
  if(born.getFullYear()!==year||born.getMonth()!==month-1||born.getDate()!==day)return {valid:false,message:'생년월일을 확인해주세요.'}
  const today=new Date()
  let age=today.getFullYear()-year
  if((today.getMonth()+1<month)||(today.getMonth()+1===month&&today.getDate()<day))age-=1
  if(age<14)return {valid:false,message:'만 14세 이상만 가입할 수 있습니다.'}
  if(age>120)return {valid:false,message:'생년월일을 확인해주세요.'}
  return {valid:true,message:`${year}년 ${pad2(month)}월 ${pad2(day)}일`}
 },[form.birth_year,form.birth_month,form.birth_day])
 const localSignupValidation=useMemo(()=>{
  const username=form.username.trim()
  const usernameFormat=/^[A-Za-z0-9._-]{3,60}$/.test(username)
  const usernameCurrent=usernameCheck.value===username
  const usernameValid=usernameFormat&&usernameCurrent&&usernameCheck.available===true
  const phoneDigits=String(form.phone_number||'').replace(/\D/g,'')
  return {
   username:{
    valid:usernameValid,
    pending:usernameFormat&&(!usernameCurrent||usernameCheck.checking),
    message:!username?'아이디를 입력해주세요.':!usernameFormat?'영문, 숫자, ., _, - 조합으로 3자 이상 입력해주세요.':usernameValid?'사용 가능한 아이디입니다.':(usernameCurrent&&usernameCheck.message)||'사용 가능 여부를 확인하고 있습니다.'
   },
   password:{valid:form.password.length>=8,message:form.password.length>=8?'사용할 수 있는 비밀번호입니다.':'비밀번호는 8자 이상 입력해주세요.'},
   password_confirm:{valid:form.password_confirm.length>0&&form.password===form.password_confirm,message:form.password_confirm.length>0&&form.password===form.password_confirm?'비밀번호가 일치합니다.':'비밀번호 확인이 일치하지 않습니다.'},
   name:{valid:form.name.trim().length>=2,message:form.name.trim().length>=2?'이름이 확인되었습니다.':'이름을 2자 이상 입력해주세요.'},
   gender:{valid:!!form.gender,message:form.gender?'성별이 선택되었습니다.':'성별을 선택해주세요.'},
   birth_date:birthValidation,
   phone_number:{valid:[10,11].includes(phoneDigits.length),message:[10,11].includes(phoneDigits.length)?'휴대폰 번호 형식이 확인되었습니다.':'휴대폰 번호를 정확히 입력해주세요.'},
   terms_consent:{valid:!!form.terms_consent,message:'서비스 이용약관 동의가 필요합니다.'},
   privacy_consent:{valid:!!form.privacy_consent,message:'개인정보 수집·이용 동의가 필요합니다.'}
  }
 },[form,usernameCheck,birthValidation])
 const localSignupReady=useMemo(()=>Object.values(localSignupValidation).every(item=>item.valid),[localSignupValidation])
 const validationClass=field=>{
  const state=localSignupValidation[field]
  if(!state)return ''
  if(state.pending)return 'checking'
  if(!fieldTouched[field]&&!state.valid)return ''
  return state.valid?'valid':'invalid'
 }
 const validationStatus=field=>{
  const state=localSignupValidation[field]
  if(!state)return null
  const visible=state.pending||(fieldTouched[field]&&!state.valid)
  if(!visible)return null
  const tone=state.pending?'checking':state.valid?'valid':'invalid'
  return <small className={`auth-field-status ${tone}`}>{state.valid?<CheckCircle2 size={13}/>:state.pending?<RefreshCw size={13}/>:<X size={13}/>}<span>{state.message}</span></small>
 }

 useEffect(()=>{
  if(adminEntry||mode!=='register'||signupStep!=='account'||socialSignup)return
  const value=form.username.trim()
  const seq=++usernameCheckSeq.current
  if(!value){
   setUsernameCheck({value:'',checking:false,available:null,message:''})
   return
  }
  if(!/^[A-Za-z0-9._-]{3,60}$/.test(value)){
   setUsernameCheck({value,checking:false,available:false,message:'아이디 형식을 확인해주세요.'})
   return
  }
  setUsernameCheck({value,checking:true,available:null,message:'사용 가능 여부 확인 중...'})
  const timer=window.setTimeout(async()=>{
   try{
    const r=await api.get('/api/auth/check-username',{params:{username:value}})
    if(seq!==usernameCheckSeq.current)return
    setUsernameCheck({value,checking:false,available:!!r.data?.available,message:r.data?.message||''})
   }catch{
    if(seq!==usernameCheckSeq.current)return
    setUsernameCheck({value,checking:false,available:false,message:'아이디 중복 확인에 실패했습니다.'})
   }
  },350)
  return()=>window.clearTimeout(timer)
 },[adminEntry,mode,signupStep,socialSignup,form.username])

 useEffect(()=>()=>{
  if(questionAdvanceTimer.current)window.clearTimeout(questionAdvanceTimer.current)
 },[])

 useEffect(()=>{
  if(adminEntry)return
  const params=new URLSearchParams(window.location.search)
  if(params.get('social_session'))return
  const draft=readInvestmentDraft(SIGNUP_INVESTMENT_DRAFT_KEY,60*60*1000)
  if(!draft?.account)return
  setMode('register')
  setSignupStep('account')
  setForm(v=>({...v,...draft.account,password:'',password_confirm:''}))
 },[])

 const loadSocialProviders=async()=>{
  try{
   const r=await api.get('/api/auth/social/providers',{params:{_ts:Date.now()}})
   setSocialProviders(r.data||{})
  }catch{
   setSocialProviders({})
  }
 }

 useEffect(()=>{
  loadSocialProviders()
  const refresh=()=>loadSocialProviders()
  const onVisibility=()=>{if(document.visibilityState==='visible')refresh()}
  window.addEventListener('pageshow',refresh)
  window.addEventListener('focus',refresh)
  document.addEventListener('visibilitychange',onVisibility)
  return()=>{
   window.removeEventListener('pageshow',refresh)
   window.removeEventListener('focus',refresh)
   document.removeEventListener('visibilitychange',onVisibility)
  }
 },[])

 useEffect(()=>{
  const resetSocialBusy=()=>setSocialBusy('')
  const onVisibility=()=>{if(document.visibilityState==='visible')resetSocialBusy()}
  window.addEventListener('pageshow',resetSocialBusy)
  window.addEventListener('focus',resetSocialBusy)
  document.addEventListener('visibilitychange',onVisibility)
  return()=>{
   window.removeEventListener('pageshow',resetSocialBusy)
   window.removeEventListener('focus',resetSocialBusy)
   document.removeEventListener('visibilitychange',onVisibility)
  }
 },[])

 useEffect(()=>{
  const params=new URLSearchParams(window.location.search)
  const sessionId=params.get('social_session')
  if(!sessionId)return
  const clean=()=>{
   const url=new URL(window.location.href)
   url.searchParams.delete('social_session')
   window.history.replaceState({},'',`${url.pathname}${url.search}${url.hash}`)
  }
  setBusy(true);setErr('')
  api.post('/api/auth/social/exchange',{session_id:sessionId}).then(r=>{
   clean()
   if(r.data?.token){
    localStorage.setItem('stocklog_token',r.data.token)
    onLogin(r.data.user)
    return
   }
   if(r.data?.needs_profile){
    setSocialSignup(r.data)
    setMode('register')
    setSignupStep('account')
    setForm(v=>({...v,
     name:r.data.display_name||'',
     gender:r.data.gender||'',
     birth_year:r.data.birth_year?String(r.data.birth_year):'',
     phone_number:r.data.phone_number||''
    }))
    setCurrent(0);setAnswers({});setProfilePayload(null);setTestQuestions(shuffleInvestmentQuestions())
   }
  }).catch(e=>{
   clean()
   setErr(publicUiText(e.response?.data?.detail)||'간편 로그인 처리 중 오류가 발생했습니다.')
  }).finally(()=>setBusy(false))
 },[])

 const clearSignupState=()=>{
  clearInvestmentDraft(SIGNUP_INVESTMENT_DRAFT_KEY)
  if(questionAdvanceTimer.current)window.clearTimeout(questionAdvanceTimer.current)
  setSignupStep('account');setCurrent(0);setAnswers({});setProfilePayload(null)
  setTestQuestions(shuffleInvestmentQuestions());setSocialSignup(null);setErr('')
  setFieldTouched({});setUsernameCheck({value:'',checking:false,available:null,message:''})
  setForm({
   username:'',password:'',password_confirm:'',name:'',gender:'',birth_year:'',birth_month:'',birth_day:'',phone_number:'',
   age_14_or_older:false,terms_consent:false,privacy_consent:false
  })
 }

 const memberLogin=async e=>{
  e.preventDefault();setErr('');setBusy(true)
  try{
   const r=await api.post('/api/auth/login',{username:form.username.trim(),password:form.password})
   localStorage.setItem('stocklog_token',r.data.token);onLogin(r.data.user)
  }catch(e){setErr(publicUiText(e.response?.data?.detail)||'로그인에 실패했습니다.')}
  finally{setBusy(false)}
 }

 const adminLogin=async e=>{
  e.preventDefault();setErr('');setBusy(true)
  try{
   const r=await api.post('/api/auth/admin-login',{username:form.username.trim(),password:form.password})
   localStorage.setItem('stocklog_token',r.data.token);onLogin(r.data.user)
  }catch(e){setErr(publicUiText(e.response?.data?.detail)||'관리자 로그인에 실패했습니다.')}
  finally{setBusy(false)}
 }

 const startSocial=async provider=>{
  setErr('');setSocialBusy(provider)
  try{
   const r=await api.get(`/api/auth/social/${provider}/start`,{params:{return_url:socialReturnUrl()}})
   if(!r.data?.authorization_url)throw new Error('authorization_url missing')
   window.location.assign(r.data.authorization_url)
  }catch(e){
   setErr(publicUiText(e.response?.data?.detail)||'간편 로그인을 시작하지 못했습니다.')
   setSocialBusy('')
  }
 }

 const socialLocked=field=>Array.isArray(socialSignup?.locked_fields)&&socialSignup.locked_fields.includes(field)

 const startInvestmentTest=e=>{
  e.preventDefault();setErr('')

  if(!socialSignup&&!localSignupReady){
   setFieldTouched({username:true,password:true,password_confirm:true,name:true,gender:true,birth_date:true,phone_number:true,terms_consent:true,privacy_consent:true})
   setErr('입력한 가입 정보를 확인해주세요.')
   return
  }

  if(!socialSignup){
   if(!/^[A-Za-z0-9._-]{3,60}$/.test(form.username.trim())){setErr('아이디는 영문, 숫자, ., _, - 조합으로 3자 이상 입력해주세요.');return}
   if(usernameCheck.value!==form.username.trim()||usernameCheck.available!==true){setErr('아이디 사용 가능 여부를 확인해주세요.');return}
   if(form.password.length<8){setErr('비밀번호는 8자 이상 입력해주세요.');return}
   if(form.password!==form.password_confirm){setErr('비밀번호 확인이 일치하지 않습니다.');return}
  }

  if(form.name.trim().length<2){setErr('이름을 2자 이상 입력해주세요.');return}
  if(!form.gender){setErr('성별을 선택해주세요.');return}

  if(socialSignup){
   const birthYear=Number(form.birth_year)
   if(!Number.isInteger(birthYear)||birthYear<currentYear-120||birthYear>currentYear-14){setErr('출생연도를 정확히 입력해주세요.');return}
   if(!form.age_14_or_older){setErr('만 14세 이상 확인이 필요합니다.');return}
  }else{
   const year=Number(form.birth_year),month=Number(form.birth_month),day=Number(form.birth_day)
   if(!year||!month||!day){setErr('생년월일을 선택해주세요.');return}
   const born=new Date(year,month-1,day)
   if(born.getFullYear()!==year||born.getMonth()!==month-1||born.getDate()!==day){setErr('생년월일을 확인해주세요.');return}
   const today=new Date()
   let age=today.getFullYear()-year
   if((today.getMonth()+1<month)||(today.getMonth()+1===month&&today.getDate()<day))age-=1
   if(age<14||age>120){setErr('만 14세 이상만 가입할 수 있습니다.');return}
  }

  if(String(form.phone_number||'').replace(/\D/g,'').length<10){setErr('휴대폰 번호를 정확히 입력해주세요.');return}
  if(!form.terms_consent||!form.privacy_consent){setErr('필수 약관과 개인정보 수집/이용에 동의해주세요.');return}

  if(!socialSignup){
   const saved=readInvestmentDraft(SIGNUP_INVESTMENT_DRAFT_KEY,60*60*1000)
   const restoredQuestions=restoreInvestmentQuestionOrder(saved?.order)
   if(saved?.username===form.username.trim()&&restoredQuestions&&Object.keys(saved?.answers||{}).length){
    setSignupStep('profile');setProfilePayload(null);setTestQuestions(restoredQuestions);setAnswers(saved.answers||{})
    setCurrent(Math.max(0,Math.min(INVESTMENT_QUESTIONS.length-1,Number(saved.current)||0)))
    return
   }
  }

  const questions=shuffleInvestmentQuestions()
  setSignupStep('profile');setCurrent(0);setAnswers({});setProfilePayload(null);setTestQuestions(questions)
  if(!socialSignup){
   writeInvestmentDraft(SIGNUP_INVESTMENT_DRAFT_KEY,{
    username:form.username.trim(),
    account:{
     username:form.username.trim(),name:form.name,gender:form.gender,birth_year:form.birth_year,birth_month:form.birth_month,birth_day:form.birth_day,
     phone_number:form.phone_number,age_14_or_older:form.age_14_or_older,terms_consent:form.terms_consent,privacy_consent:form.privacy_consent
    },
    answers:{},current:0,order:serializeInvestmentQuestionOrder(questions)
   })
  }
 }

 const question=testQuestions[current]
 const selected=question?answers[question.id]:null
 const quizStage=investmentQuizStage(current,testQuestions.length||INVESTMENT_QUESTIONS.length)

 const saveSignupQuizDraft=(nextAnswers,nextCurrent=current,nextQuestions=testQuestions)=>{
  if(socialSignup)return
  writeInvestmentDraft(SIGNUP_INVESTMENT_DRAFT_KEY,{
   username:form.username.trim(),
   account:{
    username:form.username.trim(),name:form.name,gender:form.gender,birth_year:form.birth_year,birth_month:form.birth_month,birth_day:form.birth_day,
    phone_number:form.phone_number,age_14_or_older:form.age_14_or_older,terms_consent:form.terms_consent,privacy_consent:form.privacy_consent
   },
   answers:nextAnswers,current:nextCurrent,order:serializeInvestmentQuestionOrder(nextQuestions)
  })
 }

 const goSignupQuestion=index=>{
  const next=Math.max(0,Math.min(INVESTMENT_QUESTIONS.length-1,index))
  setCurrent(next);saveSignupQuizDraft(answers,next)
 }

 const restartSignupQuiz=()=>{
  if(questionAdvanceTimer.current)window.clearTimeout(questionAdvanceTimer.current)
  const questions=shuffleInvestmentQuestions()
  setAnswers({});setCurrent(0);setErr('');setTestQuestions(questions)
  saveSignupQuizDraft({},0,questions)
 }

 const choose=value=>{
  if(!question)return
  const nextAnswers={...answers,[question.id]:value}
  setAnswers(nextAnswers);setErr('')
  if(questionAdvanceTimer.current)window.clearTimeout(questionAdvanceTimer.current)
  if(current<INVESTMENT_QUESTIONS.length-1){
   const nextCurrent=current+1
   saveSignupQuizDraft(nextAnswers,nextCurrent)
   questionAdvanceTimer.current=window.setTimeout(()=>setCurrent(v=>v===current?nextCurrent:v),260)
  }else{
   saveSignupQuizDraft(nextAnswers,current)
  }
 }

 const completeInvestmentTest=()=>{
  if(Object.keys(answers).length!==INVESTMENT_QUESTIONS.length){setErr('30개 문항에 모두 답해주세요.');return}
  const result=calculateInvestmentProfile(answers)
  const payload={
   result_code:result.code,
   answers:INVESTMENT_QUESTIONS.map(q=>({question_id:q.id,axis:q.primaryAxis,value:answers[q.id],option_label:q.options.find(option=>option.id===answers[q.id])?.label||''})),
   scores:{version:2,questionnaire:'mixed-30-v1',counts:result.counts,percentages:result.percentages}
  }
  setProfilePayload(payload);setSignupStep('complete');setErr('')
 }

 const register=async()=>{
  if(!profilePayload){setErr('투자성향 검사를 완료해주세요.');return}
  setErr('');setBusy(true)
  try{
   let r
   if(socialSignup){
    r=await api.post('/api/auth/social/complete',{
     session_id:socialSignup.session_id,
     signup_info:{
      name:form.name.trim(),gender:form.gender,birth_year:Number(form.birth_year),phone_number:form.phone_number,
      age_14_or_older:form.age_14_or_older,terms_consent:form.terms_consent,privacy_consent:form.privacy_consent
     },
     investment_profile:profilePayload
    })
   }else{
    r=await api.post('/api/auth/register',{
     username:form.username.trim(),password:form.password,display_name:form.name.trim(),gender:form.gender,
     birth_date:`${form.birth_year}-${pad2(form.birth_month)}-${pad2(form.birth_day)}`,
     phone_number:form.phone_number,terms_consent:form.terms_consent,privacy_consent:form.privacy_consent,
     investment_profile:profilePayload
    })
   }
   clearInvestmentDraft(SIGNUP_INVESTMENT_DRAFT_KEY)
   localStorage.setItem('stocklog_token',r.data.token);onLogin({...r.data.user,show_investment_profile:true})
  }catch(e){
   const detail=publicUiText(e.response?.data?.detail)
   setErr(typeof detail==='string'?detail:'회원가입 중 오류가 발생했습니다.')
  }finally{setBusy(false)}
 }

 const progress=Math.round(((current+1)/INVESTMENT_QUESTIONS.length)*100)
 const socialAvailable=Object.entries(socialProviders).filter(([,value])=>value?.available)
 const socialIcon=provider=>provider==='kakao'?'K':provider==='naver'?'N':'G'
 const renderSocialButtons=()=>socialAvailable.length?<div className="auth-social-buttons social-only">
  {socialAvailable.map(([provider,value])=><button type="button" key={provider} className={`auth-social-button ${provider}`} disabled={!!socialBusy||busy} onClick={()=>startSocial(provider)}><i>{socialIcon(provider)}</i><b>{socialBusy===provider?'연결 중...':`${value.label}로 계속하기`}</b></button>)}
 </div>:null
 const renderAuthModeTabs=()=>mode==='legacy'?null:<div className="auth-mode-tabs" role="tablist" aria-label="로그인과 회원가입 선택">
  <button type="button" role="tab" aria-selected={mode==='login'} className={mode==='login'?'active':''} onClick={()=>{clearSignupState();setMode('login')}}>로그인</button>
  <button type="button" role="tab" aria-selected={mode==='register'} className={mode==='register'?'active':''} onClick={()=>{clearSignupState();setMode('register')}}>회원가입</button>
 </div>

 return <div className="auth-shell-modern">
  <div className={`auth-layout-modern auth-mode-${mode} auth-step-${signupStep} ${mode==='register'&&signupStep==='profile'?'question-mode':''}`}>
   <section className="auth-brand-panel">
    <div className="auth-brand-top">
     <div className="auth-brand-logo"><BarChart3 size={22}/><b>StockLog</b></div>
     <div className="auth-brand-pill"><span className="auth-brand-status-dot"></span>투자 분석 서비스</div>
    </div>
    <div className="auth-brand-copy">
     <span>투자 분석과 기록</span>
     <h1>시장을 읽고,<br/>투자를 기록하세요.</h1>
     <p>종목 분석부터 포트폴리오, 수동·자동 투자까지 하나의 흐름으로 관리하는 개인 투자 워크스페이스입니다.</p>
    </div>
    <div className="auth-feature-grid auth-feature-list">
     <div><span className="auth-feature-no">01</span><Sparkles size={17}/><b>AI 종목 분석</b><small>핵심 데이터와 판단 근거를 한눈에</small></div>
     <div><span className="auth-feature-no">02</span><Fingerprint size={17}/><b>맞춤 투자 경험</b><small>내 투자성향에 맞춘 정보 우선순위</small></div>
     <div><span className="auth-feature-no">03</span><CircleDollarSign size={17}/><b>통합 증권투자</b><small>모의·실전 환경을 명확하게 분리</small></div>
     <div><span className="auth-feature-no">04</span><Activity size={17}/><b>포트폴리오 추적</b><small>수익과 보유 구성을 빠르게 확인</small></div>
    </div>
    <div className="auth-brand-foot"><ShieldCheck size={14}/><span>계정 정보와 거래 환경을 분리해 안전하게 관리합니다.</span></div>
   </section>

   <section className="auth-form-panel">
    <div className="auth-mobile-logo"><BarChart3/><b>StockLog</b></div>

    {mode==='login'&&<div className="auth-form-card">
     {renderAuthModeTabs()}
     <div className="auth-form-head"><span>로그인</span><h2>다시 만나 반가워요.</h2><p>StockLog 계정으로 로그인해 투자 내역과 분석을 이어가세요.</p></div>
     <form onSubmit={memberLogin} className="auth-modern-form">
      <label><span>아이디</span><div className="auth-input-control"><UserRound size={17}/><input autoFocus autoComplete="username" placeholder="아이디를 입력하세요" value={form.username} onChange={e=>{setForm({...form,username:e.target.value});if(err)setErr('')}}/></div></label>
      <label><span>비밀번호</span><div className="auth-input-control"><LockKeyhole size={17}/><input type={showPassword?'text':'password'} autoComplete="current-password" placeholder="비밀번호를 입력하세요" value={form.password} onChange={e=>{setForm({...form,password:e.target.value});if(err)setErr('')}}/><button type="button" className="auth-password-toggle" aria-label={showPassword?'비밀번호 숨기기':'비밀번호 보기'} onClick={()=>setShowPassword(v=>!v)}>{showPassword?<EyeOff size={17}/>:<Eye size={17}/>}</button></div></label>
      {err&&<div className="auth-error" role="alert" aria-live="polite">{err}</div>}
      <button className="primary auth-submit" disabled={busy||!form.username.trim()||!form.password}>{busy?'로그인 중...':'로그인'}<ChevronRight size={17}/></button>
     </form>
     {socialAvailable.length>0&&<><div className="auth-divider"><span>간편 로그인</span></div><div className="auth-social-primary">{renderSocialButtons()}</div></>}
    </div>}

    {mode==='legacy'&&<div className="auth-form-card">
     <div className="auth-form-head"><span>관리자 전용</span><h2>관리자 로그인</h2><p>관리 권한이 있는 계정으로만 접속할 수 있습니다.</p></div>
     <form onSubmit={adminLogin} className="auth-modern-form">
      <label><span>관리자 아이디</span><div className="auth-input-control"><UserRound size={17}/><input autoFocus autoComplete="username" placeholder="관리자 아이디" value={form.username} onChange={e=>{setForm({...form,username:e.target.value});if(err)setErr('')}}/></div></label>
      <label><span>비밀번호</span><div className="auth-input-control"><LockKeyhole size={17}/><input type={showPassword?'text':'password'} autoComplete="current-password" placeholder="비밀번호" value={form.password} onChange={e=>{setForm({...form,password:e.target.value});if(err)setErr('')}}/><button type="button" className="auth-password-toggle" aria-label={showPassword?'비밀번호 숨기기':'비밀번호 보기'} onClick={()=>setShowPassword(v=>!v)}>{showPassword?<EyeOff size={17}/>:<Eye size={17}/>}</button></div></label>
      {err&&<div className="auth-error" role="alert" aria-live="polite">{err}</div>}
      <button className="primary auth-submit" disabled={busy||!form.username.trim()||!form.password}>{busy?'로그인 중...':'관리자 로그인'}<ChevronRight size={17}/></button>
     </form>
     <div className="auth-switch"><button type="button" onClick={()=>{setMode('login');setErr('')}}>일반 로그인</button></div>
    </div>}

    {mode==='register'&&signupStep==='account'&&!socialSignup&&<div className="auth-form-card auth-local-signup">
     {renderAuthModeTabs()}
     <div className="auth-signup-progress"><span className="active"><b>1</b>가입 정보</span><i/><span><b>2</b>투자성향</span><i/><span><b>3</b>완료</span></div>
     <div className="auth-form-head"><span>회원가입</span><h2>StockLog 시작하기</h2><p>필수 정보만 입력하면 나에게 맞는 투자 환경을 준비해 드립니다.</p></div>
     <form onSubmit={startInvestmentTest} className="auth-modern-form auth-member-info-form">
      <label className={`auth-validated-field auth-field-full ${validationClass('username')}`}><span>아이디</span><div className="auth-input-control"><UserRound size={17}/><input autoFocus autoComplete="username" placeholder="영문·숫자 3자 이상" value={form.username} onChange={e=>updateField('username',e.target.value)}/></div>{validationStatus('username')}</label>
      <label className={`auth-validated-field ${validationClass('password')}`}><span>비밀번호</span><div className="auth-input-control"><LockKeyhole size={17}/><input type={showPassword?'text':'password'} autoComplete="new-password" placeholder="8자 이상" value={form.password} onChange={e=>updateField('password',e.target.value)}/><button type="button" className="auth-password-toggle" aria-label={showPassword?'비밀번호 숨기기':'비밀번호 보기'} onClick={()=>setShowPassword(v=>!v)}>{showPassword?<EyeOff size={17}/>:<Eye size={17}/>}</button></div>{validationStatus('password')}</label>
      <label className={`auth-validated-field ${validationClass('password_confirm')}`}><span>비밀번호 확인</span><div className="auth-input-control"><LockKeyhole size={17}/><input type={showPassword?'text':'password'} autoComplete="new-password" placeholder="한 번 더 입력" value={form.password_confirm} onChange={e=>updateField('password_confirm',e.target.value)}/></div>{validationStatus('password_confirm')}</label>
      <label className={`auth-validated-field ${validationClass('name')}`}><span>이름</span><div className="auth-input-control"><UserRound size={17}/><input autoComplete="name" placeholder="이름을 입력하세요" value={form.name} onChange={e=>updateField('name',e.target.value)}/></div>{validationStatus('name')}</label>
      <label className={`auth-validated-field ${validationClass('gender')}`}><span>성별</span><div className="auth-input-control"><UserRound size={17}/><select value={form.gender} onChange={e=>updateField('gender',e.target.value)}><option value="">선택</option><option value="male">남성</option><option value="female">여성</option><option value="other">기타</option><option value="prefer_not_to_say">응답하지 않음</option></select></div>{validationStatus('gender')}</label>
      <label className={`auth-validated-field auth-field-full ${validationClass('birth_date')}`}><span>생년월일</span><div className="auth-input-control auth-birthdate-control"><CalendarDays size={17}/><div className="auth-birthdate-selects">
       <select value={form.birth_year} onChange={e=>{setForm(v=>({...v,birth_year:e.target.value,birth_day:''}));touchField('birth_date');if(err)setErr('')}}><option value="">년</option>{birthYears.map(year=><option key={year} value={year}>{year}년</option>)}</select>
       <select value={form.birth_month} onChange={e=>{setForm(v=>({...v,birth_month:e.target.value,birth_day:''}));touchField('birth_date');if(err)setErr('')}}><option value="">월</option>{Array.from({length:12},(_,i)=>i+1).map(month=><option key={month} value={month}>{pad2(month)}월</option>)}</select>
       <select value={form.birth_day} onChange={e=>{setForm(v=>({...v,birth_day:e.target.value}));touchField('birth_date');if(err)setErr('')}}><option value="">일</option>{birthDays.map(day=><option key={day} value={day}>{pad2(day)}일</option>)}</select>
      </div></div>{validationStatus('birth_date')}</label>
      <label className={`auth-validated-field auth-field-full ${validationClass('phone_number')}`}><span>휴대폰 번호</span><div className="auth-input-control"><Smartphone size={17}/><input type="tel" inputMode="numeric" autoComplete="tel" placeholder="010-1234-5678" value={form.phone_number} onChange={e=>updateField('phone_number',formatSignupPhone(e.target.value))}/></div>{validationStatus('phone_number')}</label>
      <div className={`auth-consent-box auth-consent-compact ${form.terms_consent&&form.privacy_consent?'ready':''}`}>
       <label className={`auth-consent-check ${form.terms_consent?'valid':fieldTouched.terms_consent?'invalid':''}`}><input type="checkbox" checked={form.terms_consent} onChange={e=>{updateField('terms_consent',e.target.checked)}}/><span><b>[필수] 서비스 이용약관 동의</b></span>{form.terms_consent&&<CheckCircle2 size={15}/>}</label>
       <label className={`auth-consent-check ${form.privacy_consent?'valid':fieldTouched.privacy_consent?'invalid':''}`}><input type="checkbox" checked={form.privacy_consent} onChange={e=>{updateField('privacy_consent',e.target.checked)}}/><span><b>[필수] 개인정보 수집·이용 동의</b></span>{form.privacy_consent&&<CheckCircle2 size={15}/>}</label>
      </div>
      {err&&<div className="auth-error" role="alert" aria-live="polite">{err}</div>}
      <button className="primary auth-submit" disabled={!localSignupReady||usernameCheck.checking}>다음<ChevronRight size={17}/></button>
     </form>
     {socialAvailable.length>0&&<><div className="auth-divider"><span>간편 회원가입</span></div><div className="auth-social-primary">{renderSocialButtons()}</div></>}
    </div>}

    {mode==='register'&&signupStep==='account'&&socialSignup&&<div className="auth-form-card auth-profile-signup">
     {renderAuthModeTabs()}
     <div className="auth-signup-progress"><span className="active"><b>1</b>가입 정보</span><i/><span><b>2</b>투자성향</span><i/><span><b>3</b>완료</span></div>
     <div className="auth-form-head"><span>{socialSignup.provider_label} 계정 연결됨</span><h2>가입 정보 확인</h2><p>연결된 계정 정보를 확인하고 StockLog 이용에 필요한 항목을 완료해주세요.</p></div>
     <form onSubmit={startInvestmentTest} className="auth-modern-form auth-member-info-form">
      <label className={socialLocked('name')?'auth-provider-locked':''}><span>이름 {socialLocked('name')&&<em>{socialSignup?.provider_label} 제공</em>}</span><input autoFocus={!socialLocked('name')} disabled={socialLocked('name')} autoComplete="name" value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label>
      <label className={socialLocked('gender')?'auth-provider-locked':''}><span>성별 {socialLocked('gender')&&<em>{socialSignup?.provider_label} 제공</em>}</span><select disabled={socialLocked('gender')} value={form.gender} onChange={e=>setForm({...form,gender:e.target.value})}><option value="">선택</option><option value="male">남성</option><option value="female">여성</option><option value="other">기타</option><option value="prefer_not_to_say">응답하지 않음</option></select></label>
      <label className={socialLocked('birth_year')?'auth-provider-locked':''}><span>출생연도 {socialLocked('birth_year')&&<em>{socialSignup?.provider_label} 제공</em>}</span><select disabled={socialLocked('birth_year')} value={form.birth_year} onChange={e=>setForm({...form,birth_year:e.target.value})}><option value="">선택</option>{birthYears.map(year=><option key={year} value={year}>{year}년</option>)}</select></label>
      <label className={socialLocked('phone_number')?'auth-provider-locked':''}><span>휴대폰 번호 {socialLocked('phone_number')&&<em>{socialSignup?.provider_label} 제공</em>}</span><input disabled={socialLocked('phone_number')} type="tel" autoComplete="tel" placeholder="010-1234-5678" value={form.phone_number} onChange={e=>setForm({...form,phone_number:e.target.value})}/></label>
      <div className="auth-consent-box auth-consent-compact">
       <label className="auth-consent-check"><input type="checkbox" checked={form.age_14_or_older} onChange={e=>setForm({...form,age_14_or_older:e.target.checked})}/><span><b>[필수] 만 14세 이상</b></span></label>
       <label className="auth-consent-check"><input type="checkbox" checked={form.terms_consent} onChange={e=>setForm({...form,terms_consent:e.target.checked})}/><span><b>[필수] 서비스 이용약관 동의</b></span></label>
       <label className="auth-consent-check"><input type="checkbox" checked={form.privacy_consent} onChange={e=>setForm({...form,privacy_consent:e.target.checked})}/><span><b>[필수] 개인정보 수집·이용 동의</b></span></label>
      </div>
      {err&&<div className="auth-error" role="alert" aria-live="polite">{err}</div>}
      <button className="primary auth-submit">다음<ChevronRight size={17}/></button>
     </form>
     <div className="auth-switch"><button type="button" onClick={()=>{clearSignupState();setMode('login')}}>로그인</button></div>
    </div>}

    {mode==='register'&&signupStep==='profile'&&question&&<div className="auth-question-card investor-quiz-card">
     <div className="auth-signup-progress compact"><span className="done"><b>✓</b>가입 정보</span><i/><span className="active"><b>2</b>투자성향</span><i/><span><b>3</b>완료</span></div>
     <div className="auth-question-top">
      <div><span>투자성향 분석</span><h2>투자성향 검사</h2></div>
      <div className="quiz-top-actions"><button type="button" className="auth-back-button" onClick={restartSignupQuiz}><RotateCcw size={14}/>처음부터</button><button type="button" className="auth-back-button" onClick={()=>{setSignupStep('account');setErr('')}}>가입 정보 수정</button></div>
     </div>     <div className="signup-investment-benefit"><Sparkles size={17}/><div><b>왜 이 검사를 하나요?</b><span>결과는 스마트 종목 추천 순서와 위험 설명에 반영됩니다. 어려운 지식을 묻는 시험이 아니라, 평소 투자 상황에서 어떤 선택이 더 편한지만 고르면 됩니다.</span></div></div>

     <div className="investment-quiz-stage">
      <div><small>{quizStage.index+1}단계 · {quizStage.label}</small><b>{quizStage.hint}</b></div>
      <div className="investment-quiz-stage-dots">{INVESTMENT_QUIZ_STAGES.map((stage,index)=><span key={stage.label} className={index<quizStage.index?'done':index===quizStage.index?'active':''}><i/></span>)}</div>
     </div>
     <div className="auth-question-progress"><div><b>{current+1}</b><span>/ {INVESTMENT_QUESTIONS.length}</span></div><strong>{progress}%</strong></div>
     <div className="investor-progress-bar auth-progress"><i style={{width:`${progress}%`}}/></div>
     <div className="auth-question-body quiz-question-body" key={question.id}><h3>{investmentQuestionTitle(question)}</h3>
      <div className="auth-answer-list quiz-answer-list">{question.options.map((option,index)=><button type="button" key={option.id} className={selected===option.id?'selected':''} onClick={()=>choose(option.id)}><span>{['A','B','C','D'][index]}</span><b>{investmentAnswerLabel(question,index)}</b>{selected===option.id&&<CheckCircle2 size={20}/>}</button>)}</div>
     </div>
     {err&&<div className="auth-error" role="alert" aria-live="polite">{err}</div>}
     <div className="auth-question-actions quiz-question-actions"><button type="button" className="secondary" disabled={current===0} onClick={()=>goSignupQuestion(current-1)}>이전</button>{current===INVESTMENT_QUESTIONS.length-1?<button type="button" className="primary quiz-result-button" disabled={!selected} onClick={completeInvestmentTest}>내 투자성향 확인하기<Sparkles size={16}/></button>:<span className="quiz-auto-label">선택하면 다음 문항으로 이동합니다</span>}</div>
    </div>}

    {mode==='register'&&signupStep==='complete'&&profilePayload&&<div className="auth-form-card auth-complete-card">
     <div className="auth-signup-progress"><span className="done"><b>✓</b>가입 정보</span><i/><span className="done"><b>✓</b>투자성향</span><i/><span className="active"><b>3</b>완료</span></div>
     <div className="auth-complete-icon"><CheckCircle2 size={28}/></div>
     <div className="auth-form-head"><span>마지막 단계</span><h2>가입 준비 완료</h2><p>회원가입을 완료하면 분석 결과가 내 계정에 저장되고 StockLog를 바로 시작할 수 있습니다.</p></div>
     {err&&<div className="auth-error" role="alert" aria-live="polite">{err}</div>}
     <button type="button" className="primary auth-submit" disabled={busy} onClick={register}>{busy?'계정 생성 중...':'회원가입 완료'}<ChevronRight size={17}/></button>
    </div>}
   </section>
  </div>
 </div>
}

// 상세 차트용 단순 이동평균(SMA).
// 데이터가 부족하거나 종가가 유효하지 않은 구간은 null을 반환해
// ECharts가 해당 구간을 자연스럽게 비워 두도록 합니다.
const movingAverage=(rows,period)=>{
 const source=Array.isArray(rows)?rows:[]
 const size=Math.max(1,Number.parseInt(period,10)||1)
 const result=new Array(source.length).fill(null)
 let sum=0
 let invalid=0
 const window=[]

 for(let i=0;i<source.length;i+=1){
  const close=Number(source[i]?.close)
  const value=Number.isFinite(close)&&close>0?close:null
  window.push(value)
  if(value===null)invalid+=1
  else sum+=value

  if(window.length>size){
   const removed=window.shift()
   if(removed===null)invalid-=1
   else sum-=removed
  }

  if(window.length===size&&invalid===0){
   result[i]=Number((sum/size).toFixed(2))
  }
 }

 return result
}


function financialChangeMeta(row,key){
 const direction=String(row?.change_directions?.[key]||'none')
 const numeric=row?.change?.[key]
 if(direction==='none')return null
 if(numeric!==null&&numeric!==undefined&&Number.isFinite(Number(numeric))){
  const value=Number(numeric)
  return {direction,text:`${value>0?'+':''}${value.toFixed(1)}%`}
 }
 // Sign-changing profit rows (흑자 전환/적자 축소 등) intentionally avoid
 // qualitative labels. Only the YoY direction is shown to keep the table
 // consistent with ordinary +/- comparisons.
 if(direction==='up')return {direction,text:'+'}
 if(direction==='down')return {direction,text:'-'}
 if(direction==='flat')return {direction,text:'0'}
 return null
}

function FinancialTable({data=[]}){
 const rows=[...data].sort((a,b)=>String(b.period||'').localeCompare(String(a.period||''),'ko',{numeric:true}))
 const quarterly=rows.filter(r=>String(r.period||'').includes('Q')||String(r.period||'').includes('분기')||String(r.period||'').length>4&&!String(r.period||'').endsWith('-FY'))
 const list=quarterly.length?quarterly:rows
 const metrics=[['매출','revenue'],['영업이익','operating_profit'],['순이익','net_income'],['자본','equity']]
 return <div className="financial-table-wrap">
  <div className="financial-table-scroll"><table className="financial-report-table"><thead><tr><th>구분</th>{list.map(x=><th key={x.period}>{x.period}</th>)}</tr></thead><tbody>{metrics.map(([label,key])=><tr key={key}><th>{label}</th>{list.map(x=>{
   const change=financialChangeMeta(x,key)
   return <td key={x.period}><b className="financial-main-value">{x[key]==null?'-':financialAmount(x[key])}</b>{change&&<small className={`financial-yoy ${change.direction}`}><span>{change.text}</span><em>(작년대비)</em></small>}</td>
  })}</tr>)}</tbody></table></div>
 </div>
}

const emaSeries=(values,period)=>{
 const source=(Array.isArray(values)?values:[]).map(value=>Number(value))
 const size=Math.max(1,Number.parseInt(period,10)||1)
 const result=new Array(source.length).fill(null)
 if(source.length<size||source.slice(0,size).some(value=>!Number.isFinite(value)))return result
 const multiplier=2/(size+1)
 let previous=source.slice(0,size).reduce((sum,value)=>sum+value,0)/size
 result[size-1]=previous
 for(let i=size;i<source.length;i+=1){
  if(!Number.isFinite(source[i]))continue
  previous=(source[i]-previous)*multiplier+previous
  result[i]=previous
 }
 return result
}

const latestRsi=(data,period=14)=>{
 const closes=(Array.isArray(data)?data:[]).map(row=>Number(row?.close)).filter(value=>Number.isFinite(value)&&value>0)
 if(closes.length<=period)return null
 let gains=0
 let losses=0
 for(let i=1;i<=period;i+=1){
  const diff=closes[i]-closes[i-1]
  if(diff>0)gains+=diff
  else losses+=Math.abs(diff)
 }
 let avgGain=gains/period
 let avgLoss=losses/period
 for(let i=period+1;i<closes.length;i+=1){
  const diff=closes[i]-closes[i-1]
  const gain=diff>0?diff:0
  const loss=diff<0?Math.abs(diff):0
  avgGain=((avgGain*(period-1))+gain)/period
  avgLoss=((avgLoss*(period-1))+loss)/period
 }
 if(avgLoss===0)return avgGain===0?50:100
 const rs=avgGain/avgLoss
 return 100-(100/(1+rs))
}

const latestMacd=(data)=>{
 const closes=(Array.isArray(data)?data:[]).map(row=>Number(row?.close)).filter(value=>Number.isFinite(value)&&value>0)
 if(closes.length<35)return null
 const ema12=emaSeries(closes,12)
 const ema26=emaSeries(closes,26)
 const points=[]
 for(let i=0;i<closes.length;i+=1){
  if(ema12[i]!=null&&ema26[i]!=null)points.push({index:i,value:ema12[i]-ema26[i]})
 }
 const signal=emaSeries(points.map(point=>point.value),9)
 if(!points.length||signal.at(-1)==null)return null
 const macd=points.at(-1).value
 const signalValue=signal.at(-1)
 return {macd,signal:signalValue,histogram:macd-signalValue}
}

const latestBollinger=(data,period=20)=>{
 const closes=(Array.isArray(data)?data:[]).map(row=>Number(row?.close)).filter(value=>Number.isFinite(value)&&value>0)
 if(closes.length<period)return null
 const window=closes.slice(-period)
 const middle=window.reduce((sum,value)=>sum+value,0)/period
 const variance=window.reduce((sum,value)=>sum+((value-middle)**2),0)/period
 const deviation=Math.sqrt(variance)
 const upper=middle+deviation*2
 const lower=middle-deviation*2
 const close=closes.at(-1)
 const position=upper===lower?50:((close-lower)/(upper-lower))*100
 return {close,middle,upper,lower,position}
}

const signalToneLabel=tone=>({positive:'긍정',negative:'주의',neutral:'중립',unavailable:'데이터 부족'}[tone]||'중립')

function ChartSignalTable({data=[],stock=null,vix=null}){
 const source=Array.isArray(data)?data:[]
 const latest=source.at(-1)||{}
 const previous=source.at(-2)||{}
 const close=Number(latest?.close||0)
 const ma20=movingAverage(source,20).at(-1)
 const ma60=movingAverage(source,60).at(-1)
 const ma240=movingAverage(source,240).at(-1)
 const rsi=latestRsi(source,14)
 const macd=latestMacd(source)
 const bollinger=latestBollinger(source,20)
 const volumeWindow=(source.length>20?source.slice(-21,-1):source.slice(0,-1)).map(row=>Number(row?.volume)).filter(value=>Number.isFinite(value)&&value>=0)
 const avgVolume=volumeWindow.length?volumeWindow.reduce((sum,value)=>sum+value,0)/volumeWindow.length:null
 const currentVolume=Number(latest?.volume)
 const volumeRatio=avgVolume>0&&Number.isFinite(currentVolume)?currentVolume/avgVolume:null
 const dayChange=Number(previous?.close)>0?((close-Number(previous.close))/Number(previous.close))*100:null
 const per=Number(stock?.per)
 const vixValue=Number(vix?.value)

 const maAvailable=Number.isFinite(close)&&close>0&&ma20!==null&&ma20!==undefined&&Number.isFinite(Number(ma20))
 let maTone='unavailable'
 let maStatus='데이터 부족'
 let maInfo='20일 이동평균을 계산할 일봉 데이터가 충분하지 않습니다.'
 if(maAvailable){
  if(ma60!==null&&ma60!==undefined&&Number.isFinite(Number(ma60))&&close>Number(ma20)&&Number(ma20)>=Number(ma60)){
   maTone='positive';maStatus='상승 정렬';maInfo=`현재가가 20일선 위에 있고 20일선이 60일선보다 높아 단·중기 추세가 우호적입니다.${ma240!==null&&ma240!==undefined&&Number.isFinite(Number(ma240))?` 240일선 ${Number(ma240).toLocaleString('ko-KR',{maximumFractionDigits:0})}원도 함께 확인하세요.`:''}`
  }else if(ma60!==null&&ma60!==undefined&&Number.isFinite(Number(ma60))&&close<Number(ma20)&&Number(ma20)<=Number(ma60)){
   maTone='negative';maStatus='하락 정렬';maInfo='현재가가 20일선 아래이고 단기선이 중기선보다 낮아 약세 흐름을 확인할 필요가 있습니다.'
  }else{
   maTone='neutral';maStatus='혼조';maInfo='현재가와 단·중기 이동평균의 위치가 엇갈려 뚜렷한 방향 확인이 더 필요합니다.'
  }
 }

 let perTone='unavailable',perStatus='데이터 부족',perInfo='정상적인 양수 PER이 없어 이익 기준 가치평가를 단순 비교하기 어렵습니다.'
 if(Number.isFinite(per)&&per>0){
  if(per<=12){perTone='positive';perStatus='가격 부담 낮음';perInfo=`PER ${per.toFixed(1)}배로 이익 대비 가격 부담이 비교적 낮은 구간입니다. 다만 같은 업종 평균과 성장률을 함께 확인해야 합니다.`}
  else if(per<=25){perTone='neutral';perStatus='중립 구간';perInfo=`PER ${per.toFixed(1)}배입니다. 절대값만으로 고평가·저평가를 단정하지 말고 업종 평균과 이익 성장 속도를 같이 보세요.`}
  else{perTone='negative';perStatus='가격 부담 확인';perInfo=`PER ${per.toFixed(1)}배로 현재 이익 대비 기대가 많이 반영됐을 수 있습니다. 향후 실적 성장이 밸류에이션을 따라가는지 확인이 필요합니다.`}
 }

 let rsiTone='unavailable',rsiStatus='데이터 부족',rsiInfo='RSI(14)를 계산할 일봉 데이터가 충분하지 않습니다.'
 if(Number.isFinite(rsi)){
  if(rsi>=70){rsiTone='negative';rsiStatus='과매수 주의';rsiInfo=`RSI ${rsi.toFixed(1)}로 70 이상입니다. 상승 탄력은 강하지만 단기 과열과 되돌림 가능성을 함께 경계할 구간입니다.`}
  else if(rsi<=30){rsiTone='neutral';rsiStatus='과매도 구간';rsiInfo=`RSI ${rsi.toFixed(1)}로 30 이하입니다. 반등 가능성은 열려 있지만 약세 추세가 끝났다는 확인 신호는 아닙니다.`}
  else if(rsi>=50){rsiTone='positive';rsiStatus='강세 모멘텀';rsiInfo=`RSI ${rsi.toFixed(1)}로 중립선 50 위에서 움직여 매수 모멘텀이 상대적으로 우세합니다.`}
  else{rsiTone='neutral';rsiStatus='약한 모멘텀';rsiInfo=`RSI ${rsi.toFixed(1)}로 50 아래입니다. 과매도는 아니지만 단기 힘은 다소 약한 상태입니다.`}
 }

 let macdTone='unavailable',macdStatus='데이터 부족',macdInfo='MACD(12,26,9)를 계산할 일봉 데이터가 충분하지 않습니다.'
 if(macd){
  if(macd.histogram>0){macdTone='positive';macdStatus='강세 신호';macdInfo=`MACD ${macd.macd.toFixed(2)}가 신호선 ${macd.signal.toFixed(2)}보다 높습니다. 히스토그램이 양수라 상승 추세 힘이 우세합니다.`}
  else if(macd.histogram<0){macdTone='negative';macdStatus='약세 신호';macdInfo=`MACD ${macd.macd.toFixed(2)}가 신호선 ${macd.signal.toFixed(2)}보다 낮습니다. 하락 추세 압력이 우세한지 확인이 필요합니다.`}
  else{macdTone='neutral';macdStatus='중립';macdInfo='MACD와 신호선 차이가 거의 없어 방향성이 뚜렷하지 않습니다.'}
 }

 let bandTone='unavailable',bandStatus='데이터 부족',bandInfo='볼린저 밴드(20, 2σ)를 계산할 일봉 데이터가 충분하지 않습니다.'
 if(bollinger){
  if(bollinger.position>=100){bandTone='negative';bandStatus='상단 돌파';bandInfo=`현재가가 상단 밴드 ${Math.round(bollinger.upper).toLocaleString()}원을 넘어 단기 과열 여부를 확인할 구간입니다. 강한 거래량 동반 시 추세 돌파인지 함께 보세요.`}
  else if(bollinger.position>=85){bandTone='negative';bandStatus='상단 근접';bandInfo=`밴드 위치가 ${bollinger.position.toFixed(0)}%로 상단에 가깝습니다. 상승세는 강하지만 단기 과매수 가능성도 커집니다.`}
  else if(bollinger.position<=0){bandTone='negative';bandStatus='하단 이탈';bandInfo=`현재가가 하단 밴드 ${Math.round(bollinger.lower).toLocaleString()}원 아래로 내려 약세 변동성이 커진 상태입니다.`}
  else if(bollinger.position<=15){bandTone='neutral';bandStatus='하단 근접';bandInfo=`밴드 위치가 ${bollinger.position.toFixed(0)}%로 하단에 가깝습니다. 기술적 반등 가능성과 추세 약화를 동시에 확인해야 합니다.`}
  else{bandTone='neutral';bandStatus='밴드 내부';bandInfo=`밴드 위치가 ${bollinger.position.toFixed(0)}%로 정상 범위 안입니다. 상단·하단 돌파와 밴드 폭 변화를 다음 신호로 확인하세요.`}
 }

 let volumeTone='unavailable',volumeStatus='데이터 부족',volumeInfo='최근 거래량 평균을 계산할 데이터가 충분하지 않습니다.'
 if(Number.isFinite(volumeRatio)){
  const ratioText=`20일 평균의 ${volumeRatio.toFixed(2)}배`
  if(volumeRatio>=1.5&&Number(dayChange)>0){volumeTone='positive';volumeStatus='상승 거래량 증가';volumeInfo=`오늘 거래량이 ${ratioText}이고 주가도 ${dayChange>=0?'+':''}${dayChange.toFixed(1)}% 움직여 상승 움직임에 거래량이 실린 상태입니다.`}
  else if(volumeRatio>=1.5&&Number(dayChange)<0){volumeTone='negative';volumeStatus='하락 거래량 증가';volumeInfo=`오늘 거래량이 ${ratioText}로 크게 늘면서 주가는 ${dayChange.toFixed(1)}% 하락해 매도 압력이 강해졌는지 확인이 필요합니다.`}
  else{volumeTone='neutral';volumeStatus=volumeRatio>=1.2?'거래량 증가':'평균 수준';volumeInfo=`현재 거래량은 ${ratioText}입니다. 가격 방향과 함께 거래량이 1.5배 이상 확대되는지 보면 돌파 신뢰도를 판단하는 데 도움이 됩니다.`}
 }

 let vixTone='unavailable',vixStatus='조회 대기',vixInfo='VIX 실제 시장값을 확인하지 못했습니다. 개별 종목 신호와 별도로 시장 전체 위험 심리를 확인하세요.'
 if(Number.isFinite(vixValue)&&vixValue>0){
  if(vixValue<15){vixTone='positive';vixStatus='시장 안정';vixInfo=`VIX ${vixValue.toFixed(1)}로 시장 공포가 낮은 편입니다. 다만 낮은 변동성이 개별 종목의 상승을 보장하지는 않습니다.`}
  else if(vixValue<20){vixTone='neutral';vixStatus='보통';vixInfo=`VIX ${vixValue.toFixed(1)}로 시장 변동성은 비교적 평상 범위입니다. 종목 자체 추세와 수급 신호를 우선 확인하세요.`}
  else if(vixValue<30){vixTone='negative';vixStatus='경계 구간';vixInfo=`VIX ${vixValue.toFixed(1)}로 시장 불확실성이 높아진 구간입니다. 손절 기준과 포지션 크기를 평소보다 보수적으로 관리할 필요가 있습니다.`}
  else{vixTone='negative';vixStatus='공포 확대';vixInfo=`VIX ${vixValue.toFixed(1)}로 시장 변동성이 매우 높은 구간입니다. 개별 호재보다 시장 전체 급변 리스크가 크게 작용할 수 있습니다.`}
 }

 const rows=[
  {key:'per',name:'P/E · 주가수익비율',value:Number.isFinite(per)&&per>0?`${per.toFixed(1)}배`:'-',tone:perTone,status:perStatus,info:perInfo},
  {key:'ma',name:'이동평균 · MA',value:ma20?`20일 ${Math.round(ma20).toLocaleString()}원`:'-',tone:maTone,status:maStatus,info:maInfo},
  {key:'rsi',name:'상대강도지수 · RSI(14)',value:Number.isFinite(rsi)?rsi.toFixed(1):'-',tone:rsiTone,status:rsiStatus,info:rsiInfo},
  {key:'macd',name:'MACD · 12/26/9',value:macd?`${macd.histogram>=0?'+':''}${macd.histogram.toFixed(2)}`:'-',tone:macdTone,status:macdStatus,info:macdInfo},
  {key:'bollinger',name:'볼린저 밴드 · 20일',value:bollinger?`위치 ${bollinger.position.toFixed(0)}%`:'-',tone:bandTone,status:bandStatus,info:bandInfo},
  {key:'volume',name:'거래량 · Volume',value:Number.isFinite(volumeRatio)?`${volumeRatio.toFixed(2)}배`:'-',tone:volumeTone,status:volumeStatus,info:volumeInfo},
  {key:'vix',name:'시장 변동성 · VIX',value:Number.isFinite(vixValue)&&vixValue>0?vixValue.toFixed(1):'-',tone:vixTone,status:vixStatus,info:vixInfo},
 ]
 const positiveCount=rows.filter(row=>row.tone==='positive').length
 const negativeCount=rows.filter(row=>row.tone==='negative').length
 const summary=negativeCount>=3?'주의 신호가 상대적으로 많습니다. 기술적 반등보다 위험 관리 기준을 먼저 확인하세요.':positiveCount>=3?'긍정 신호가 상대적으로 우세합니다. 다만 과열 신호와 실적·수급을 함께 확인하세요.':'긍정·중립·주의 신호가 섞여 있습니다. 한 지표보다 여러 신호의 방향이 같이 맞는지 확인하세요.'

 return <div className="chart-signal-table chart-signal-analysis">
  <div className="chart-signal-title"><div><small>7 SIGNAL CHECK</small><h4>차트 주요 신호 분석</h4></div><p>{summary}</p></div>
  <div className="chart-signal-grid">{rows.map((row,index)=><article className={`chart-signal-card ${row.tone}`} key={row.key}>
   <div className="chart-signal-card-head"><span>{String(index+1).padStart(2,'0')}</span><div><b>{row.name}</b><small>{row.value}</small></div><em>{signalToneLabel(row.tone)} · {row.status}</em></div>
   <p>{row.info}</p>
  </article>)}</div>
  <small className="chart-signal-disclaimer">기술적 지표는 현재 데이터의 상태를 설명하는 참고 신호이며 단독 매수·매도 지시가 아닙니다. VIX는 미국 시장의 기대 변동성으로 국내 개별 종목에는 시장 심리 참고값으로 사용합니다.</small>
 </div>
}

function DetailedStockChart({data=[],compact=false}){
 const el=useRef(null)

 useEffect(()=>{
   if(!el.current||!Array.isArray(data)||!data.length)return

   const chart=echarts.init(el.current)

   const dates=data.map(x=>x.date)
   const candles=data.map(x=>[
     Number(x.open||0),
     Number(x.close||0),
     Number(x.low||0),
     Number(x.high||0)
   ])

   const ma20=movingAverage(data,20)
   const ma60=movingAverage(data,60)
   const ma240=movingAverage(data,240)
   const kospi=data.map(x=>x.kospi==null?null:Number(x.kospi))

   const volume=data.map(x=>({
     value:Number(x.volume||0),
     itemStyle:{
       color:'rgba(96,110,226,.92)',
       borderRadius:[1,1,0,0]
     }
   }))

   const visibleCount=compact?70:90
   const startPct=Math.max(
     0,
     Math.round(100-(visibleCount/Math.max(data.length,1))*100)
   )

   const formatDate=v=>{
     if(!v)return ''
     const p=String(v).split('-')
     if(p.length!==3)return String(v)
     return `${p[0]}-${p[1]}-${p[2]}`
   }

   const number=v=>Number(v||0).toLocaleString('ko-KR')

   const option={
     animation:false,
     backgroundColor:'#fff',

     legend:{
       top:8,
       left:'center',
       itemWidth:14,
       itemHeight:8,
       itemGap:22,
       textStyle:{
         color:'#222b3a',
         fontSize:compact?10:11,
         fontWeight:700
       },
       data:[
         '주가',
         '20일 이동평균선',
         '60일 이동평균선',
         '240일 이동평균선',
         '거래량',
         'KOSPI 지수'
       ]
     },

     tooltip:{
       trigger:'axis',
       axisPointer:{
         type:'cross',
         crossStyle:{color:'#8b95a7'},
         lineStyle:{color:'#8b95a7',type:'dashed'}
       },
       borderWidth:0,
       padding:0,
       backgroundColor:'transparent',
       extraCssText:'box-shadow:none',
       formatter(params){
         const index=params?.[0]?.dataIndex ?? 0
         const row=data[index]
         if(!row)return ''
         const rising=Number(row.close)>=Number(row.open)
         const bg=rising?'#b95d62':'#527db4'
         const value=v=>v==null?'-':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:2})
         return `
           <div style="min-width:214px;padding:12px 14px;border-radius:8px;background:${bg};color:#fff;font-size:12px;line-height:1.58;box-shadow:0 12px 28px rgba(15,23,42,.22)">
             <div style="font-weight:800;font-size:13px;margin-bottom:5px">날짜:${row.date}</div>
             <div>시가:${value(row.open)}</div>
             <div>저가:${value(row.low)}</div>
             <div>고가:${value(row.high)}</div>
             <div>종가:${value(row.close)}</div>
             <div style="margin-top:5px;border-top:1px solid rgba(255,255,255,.24);padding-top:5px">20일선:${value(ma20[index])}</div>
             <div>60일선:${value(ma60[index])}</div>
             <div>240일선:${value(ma240[index])}</div>
             <div>KOSPI:${value(row.kospi)}</div>
             <div style="margin-top:4px">거래량:${value(row.volume)}</div>
           </div>`
       }
     },

     axisPointer:{
       link:[{xAxisIndex:'all'}],
       label:{backgroundColor:'#101827',color:'#fff'}
     },

     grid:[
       {
         left:78,
         right:86,
         top:44,
         height:compact?'54%':'58%'
       },
       {
         left:78,
         right:86,
         top:compact?'72%':'73%',
         height:compact?'17%':'20%'
       }
     ],

     xAxis:[
       {
         type:'category',
         data:dates,
         boundaryGap:true,
         axisLine:{lineStyle:{color:'#b9c0ca'}},
         axisTick:{show:false},
         axisLabel:{show:false},
         splitLine:{
           show:true,
           lineStyle:{color:'#e5e7eb'}
         },
         min:'dataMin',
         max:'dataMax'
       },
       {
         type:'category',
         gridIndex:1,
         data:dates,
         boundaryGap:true,
         axisLine:{lineStyle:{color:'#b9c0ca'}},
         axisTick:{show:false},
         axisLabel:{
           show:true,
           color:'#202938',
           fontSize:compact?9:10,
           hideOverlap:true,
           formatter:formatDate,
           margin:12
         },
         splitLine:{
           show:true,
           lineStyle:{color:'#e5e7eb'}
         },
         min:'dataMin',
         max:'dataMax'
       }
     ],

     yAxis:[
       {
         scale:true,
         position:'left',
         splitNumber:5,
         axisLine:{show:false},
         axisTick:{show:false},
         axisLabel:{
           color:'#111827',
           fontSize:compact?9:10,
           formatter:v=>number(v)
         },
         splitLine:{
           show:true,
           lineStyle:{color:'#d7dbe2'}
         }
       },
       {
         scale:true,
         position:'right',
         splitLine:{show:false},
         axisLine:{show:false},
         axisTick:{show:false},
         axisLabel:{
           color:'#111827',
           fontSize:compact?9:10,
           fontWeight:700,
           formatter:v=>number(v)
         },
         name:'KOSPI 지수',
         nameLocation:'middle',
         nameGap:44,
         nameTextStyle:{
           color:'#111827',
           fontSize:compact?10:11,
           fontWeight:700
         }
       },
       {
         scale:true,
         gridIndex:1,
         position:'left',
         splitNumber:2,
         axisLine:{show:false},
         axisTick:{show:false},
         axisLabel:{
           color:'#111827',
           fontSize:compact?9:10,
           formatter:v=>number(v)
         },
         splitLine:{
           show:true,
           lineStyle:{color:'#d7dbe2'}
         }
       }
     ],

     dataZoom:[
       {
         type:'inside',
         xAxisIndex:[0,1],
         start:startPct,
         end:100,
         filterMode:'filter'
       }
     ],

     series:[
       {
         name:'주가',
         type:'candlestick',
         data:candles,
         barMaxWidth:compact?10:12,
         itemStyle:{
           color:'#b95d62',
           color0:'#527db4',
           borderColor:'#b95d62',
           borderColor0:'#527db4'
         },
         z:5
       },
       {
         name:'20일 이동평균선',
         type:'line',
         data:ma20,
         symbol:'none',
         lineStyle:{width:1.45,color:'#b95d62'},
         connectNulls:false,
         z:7
       },
       {
         name:'60일 이동평균선',
         type:'line',
         data:ma60,
         symbol:'none',
         lineStyle:{width:1.45,color:'#527db4'},
         connectNulls:false,
         z:7
       },
       {
         name:'240일 이동평균선',
         type:'line',
         data:ma240,
         symbol:'none',
         lineStyle:{width:1.45,color:'#1f9c97'},
         connectNulls:false,
         z:7
       },
       {
         name:'KOSPI 지수',
         type:'line',
         yAxisIndex:1,
         data:kospi,
         symbol:'none',
         lineStyle:{width:2,color:'#e9a81d'},
         connectNulls:true,
         z:4
       },
       {
         name:'거래량',
         type:'bar',
         xAxisIndex:1,
         yAxisIndex:2,
         data:volume,
         barMaxWidth:compact?9:12,
         barGap:'10%',
         z:3
       }
     ]
   }

   chart.setOption(option,true)

   let resizeFrame=0
   const resize=()=>{
    cancelAnimationFrame(resizeFrame)
    resizeFrame=requestAnimationFrame(
     ()=>chart.resize()
    )
   }

   window.addEventListener(
    'resize',
    resize
   )

   let observer=null

   if(typeof ResizeObserver!=='undefined'){
    observer=new ResizeObserver(
     resize
    )
    observer.observe(
     el.current
    )
   }

   return()=>{
     observer?.disconnect()
     cancelAnimationFrame(resizeFrame)
     window.removeEventListener(
      'resize',
      resize
     )
     chart.dispose()
   }
 },[data,compact])

 return (
   <div className="reference-chart-shell">
     <div className={compact?'detailed-chart compact':'detailed-chart'} ref={el}/>
   </div>
 )
}

function Delta({value}){
 if(value===null||value===undefined){
   return <span className="delta neutral">-</span>
 }

 const up=Number(value)>0
 const down=Number(value)<0

 return (
   <span
     className={`delta ${
       up
         ? 'delta-up'
         : down
           ? 'delta-down'
           : 'neutral'
     }`}
   >
     {up
       ? <ArrowUpRight size={12}/>
       : down
         ? <ArrowDownRight size={12}/>
         : null
     }
     {up?'+':''}{Number(value).toFixed(1)}%
   </span>
 )
}

function FinancialCell({value,delta}){
 return (
   <div className="financial-cell">
     <b>{won(Math.round(Number(value)||0))}</b>
     <Delta value={delta}/>
   </div>
 )
}

function StockThemeBadges({
 themes=[],
 fallback=null,
 max=2,
 compact=false
}){
 const shown=(themes||[]).slice(0,max)
 const fallbackObj=typeof fallback==='string'?{label:fallback}:fallback
 if(!shown.length&&!fallbackObj)return null
 return <span className={`stock-theme-badges ${compact?'compact':''}`}>
   {shown.length
     ? shown.map(t=>
       <em className="stock-theme-badge" key={`${t.theme_code||t.name}`} title="연관 테마">
         {t.name}
       </em>
     )
     : <em className="stock-business-badge" title="대표 사업 분류">
         {fallbackObj?.label||fallbackObj?.name}
       </em>
   }
   {(themes||[]).length>max&&<small>+{(themes||[]).length-max}</small>}
 </span>
}


function SmartInfoTooltip({text}){
 const buttonRef=useRef(null)
 const [open,setOpen]=useState(false)
 const [position,setPosition]=useState({left:0,top:0})
 const updatePosition=()=>{
  const rect=buttonRef.current?.getBoundingClientRect?.()
  if(!rect)return
  const viewportWidth=window.innerWidth||document.documentElement.clientWidth||320
  const halfWidth=Math.min(145,Math.max(110,viewportWidth/2-14))
  const center=Math.max(halfWidth+10,Math.min(viewportWidth-halfWidth-10,rect.left+rect.width/2))
  setPosition({left:center,top:rect.bottom+9})
 }
 useEffect(()=>{
  if(!open)return
  updatePosition()
  const sync=()=>updatePosition()
  window.addEventListener('resize',sync)
  window.addEventListener('scroll',sync,true)
  return()=>{window.removeEventListener('resize',sync);window.removeEventListener('scroll',sync,true)}
 },[open])
 const show=()=>{updatePosition();setOpen(true)}
 const hide=()=>setOpen(false)
 return <span className="smart-info-tooltip" onMouseEnter={show} onMouseLeave={hide}>
  <button
   ref={buttonRef}
   type="button"
   className="smart-info-button"
   aria-label="점수 기준 설명"
   aria-expanded={open?'true':'false'}
   onFocus={show}
   onBlur={hide}
   onClick={e=>{e.stopPropagation();open?hide():show()}}
  ><Info size={13}/></button>
  {open&&typeof document!=='undefined'&&createPortal(
   <span className="smart-info-portal-popover" role="tooltip" style={{left:position.left,top:position.top}}>{text}</span>,
   document.body
  )}
 </span>
}

function SmartStockSearch({value,onChange,onSearch,onClear,loading=false,placeholder='종목명 또는 종목코드를 입력 후 Enter',ariaLabel='스마트 분석 종목 검색'}){
 const inputRef=useRef(null)
 const submit=event=>{
  event.preventDefault()
  onSearch?.(value)
 }
 return <form
  className={`smart-stock-search${loading?' loading':''}`}
  role="search"
  onSubmit={submit}
 >
  <button type="submit" className="smart-search-submit" aria-label="검색" title="검색"><Search size={17}/></button>
  <input
   ref={inputRef}
   value={value}
   onChange={e=>onChange(e.target.value)}
   placeholder={placeholder}
   aria-label={ariaLabel}
   autoComplete="off"
  />
  {loading&&<RefreshCw size={14} className="spin-icon smart-search-loading" aria-hidden="true"/>}
  {value&&<button
   type="button"
   className="smart-search-clear"
   aria-label="검색어 지우기"
   title="검색어 지우기"
   onClick={()=>{onChange('');onClear?.();inputRef.current?.focus()}}
  ><X size={14}/></button>}
 </form>
}
function SmartScoreDetail({code,onClose,onOpenStock}){
 const [data,setData]=useState(null)
 const [loading,setLoading]=useState(true)
 const [err,setErr]=useState('')
 useEffect(()=>{
  let cancelled=false
  setLoading(true);setErr('');setData(null)
  api.get(`/api/smart/stocks/${code}/score-detail`)
   .then(r=>{if(!cancelled)setData(r.data)})
   .catch(e=>{if(!cancelled)setErr(publicUiText(e.response?.data?.detail)||'추천 점수 근거를 불러오지 못했습니다.')})
   .finally(()=>{if(!cancelled)setLoading(false)})
  return()=>{cancelled=true}
 },[code])
 useEffect(()=>{
  const key=e=>{if(e.key==='Escape')onClose()}
  window.addEventListener('keydown',key)
  return()=>window.removeEventListener('keydown',key)
 },[onClose])
 const backdrop=e=>{if(e.target===e.currentTarget)onClose()}
 const tone=score=>Number(score)>=80?'good':Number(score)<70?'bad':'normal'
 return <div className="modal smart-score-detail-modal" onMouseDown={backdrop}>
  <div className="smart-score-detail-panel">
   <button type="button" className="close" onClick={onClose} aria-label="점수 상세 닫기"><X/></button>
   {loading?<div className="smart-score-detail-loading"><div className="sync-spinner"/><b>추천 점수 근거를 정리하고 있어요</b><span>동기화된 재무·수급·뉴스 데이터를 비교합니다.</span></div>
   :err?<div className="error-box"><b>점수 상세 조회 오류</b><span>{err}</span></div>
   :data&&<>
    <div className="smart-score-detail-head">
     <div>
      <small>추천 점수 산정 근거</small>
      <h2>{data.stock?.name} 추천 점수 해설</h2>
      <p>{data.method}</p>
      <StockThemeBadges themes={data.stock?.themes} fallback={data.stock?.theme_fallback} max={3} compact/>
     </div>
     <span className="smart-score-updated">{smartUpdatedText(data.updated_at)}</span>
    </div>

    <div className="smart-dual-score-hero">
     <article className={`smart-score-hero-card ai ${tone(data.ai_score)}`}>
      <div><Sparkles size={18}/><span>StockLog 종합점수</span></div>
      <strong>{oneDecimal(data.ai_score)}<small>/100</small></strong>
      <b>{data.ai_label}</b>
      <p>StockLog 알고리즘으로 여러 투자 데이터를 같은 기준으로 계산한 종목 자체의 점수입니다.</p>
      <em>분석 데이터 커버리지 {oneDecimal(data.coverage)}%</em>
     </article>
     <article className={`smart-score-hero-card profile ${data.profile_score===null?'disabled':tone(data.profile_score)}`}>
      <div><Fingerprint size={18}/><span>내 투자성향 적합 점수</span></div>
      {data.profile_score===null
       ? <><strong>--</strong><b>성향 검사 필요</b><p>투자성향 검사를 완료하면 이 종목이 나와 얼마나 맞는지 별도로 계산합니다.</p></>
       : <><strong>{oneDecimal(data.profile_score)}<small>/100</small></strong><b>{data.profile_label}</b><p>내 보유기간·위험선호·성장/가치·수익실현·분산 성향과의 적합도입니다.</p><em>내 투자 유형 {data.profile_code||'-'}</em></>}
     </article>
    </div>

    {(data.summary||[]).length>0&&<div className="smart-score-summary-callout">
     <Gauge size={18}/><div>{data.summary.map((line,i)=><p key={i}>{line}</p>)}</div>
    </div>}

    <div className="smart-score-compare-title">
     <div><span>항목별 비교</span><h3>StockLog는 어떻게 평가했고, 내 성향에는 얼마나 맞을까?</h3></div>
     <small>점수가 높다고 무조건 매수하라는 의미는 아닙니다.</small>
    </div>
    <div className="smart-score-component-list">
     {(data.components||[]).map((item,index)=><article className={`smart-score-component ${item.available?'':'unavailable'}`} key={item.key}>
      <div className="smart-score-component-head">
       <span className="smart-score-component-no">{String(index+1).padStart(2,'0')}</span>
       <div><b>{item.label}</b><small>{item.source}</small></div>
       {!item.available&&<em>동기화 데이터 없음</em>}
      </div>
      <div className="smart-score-component-bars">
       <div className="smart-score-component-bar ai">
        <span>종합점수 항목</span><b>{item.available?oneDecimal(item.score):'--'}</b>
        <i><em style={{width:`${item.available?Math.max(0,Math.min(100,Number(item.score||0))):0}%`}}/></i>
       </div>
       <div className="smart-score-component-bar profile">
        <span><Fingerprint size={13}/>내 성향 적합도</span><b>{item.profile_score===null?'--':oneDecimal(item.profile_score)}</b>
        <i><em style={{width:`${item.profile_score===null?0:Math.max(0,Math.min(100,Number(item.profile_score||0)))}%`}}/></i>
       </div>
      </div>
      <div className="smart-score-component-copy">
       <div><small>StockLog 평가</small><p>{item.ai_view}</p></div>
       <div><small>내 성향과 비교</small><p>{item.profile_view}</p></div>
      </div>
      <div className="smart-score-evidence">
       {(item.evidence||[]).map((line,i)=><span key={i}><CheckCircle2 size={13}/>{line}</span>)}
      </div>
     </article>)}
    </div>
    <div className="smart-score-detail-actions">
     <button type="button" className="secondary" onClick={onClose}>닫기</button>
     <button type="button" className="primary" onClick={()=>onOpenStock?.({code:data.stock?.code})}>종목 상세 분석 보기<ChevronRight size={16}/></button>
    </div>
   </>}
  </div>
 </div>
}

function SmartListLoadingOverlay({kind='filter',stage=0,page=1,query='',marketLabel='국내증권',pageLabel='스마트 분석'}){
 const configs={
  initial:{eyebrow:'백그라운드 업데이트',title:`${marketLabel} 분석 데이터를 채우고 있어요`,desc:'화면은 먼저 열렸으며 결과가 도착하는 순서대로 반영합니다.'},
  page:{eyebrow:'목록 업데이트',title:`${page}페이지 분석 결과를 불러오고 있어요`,desc:'현재 화면을 유지하면서 다음 결과를 정리합니다.'},
  search:{eyebrow:'종목 검색',title:`${marketLabel} 검색 결과를 업데이트하고 있어요`,desc:query?`“${query}” 결과를 찾는 동안 기존 화면을 계속 사용할 수 있습니다.`:'검색 결과를 업데이트합니다.'},
  filter:{eyebrow:'조건 적용',title:`${marketLabel} 분석 조건을 반영하고 있어요`,desc:'현재 화면을 유지하면서 선택한 조건의 결과로 교체합니다.'},
  mode:{eyebrow:'순위 갱신',title:`${marketLabel} 분석 순위를 업데이트하고 있어요`,desc:'종합점수와 투자성향 순서를 백그라운드에서 반영합니다.'}
 }
 const info=configs[kind]||configs.filter
 const steps=[
  {label:'조회 조건 확인',desc:'선택한 검색·필터 조건을 확인합니다.'},
  {label:`${marketLabel} 분석 데이터`,desc:'종합점수와 성향 적합도를 가져옵니다.'},
  {label:'결과 정리',desc:'점수와 조건에 맞춰 표시할 종목을 정리합니다.'}
 ]
 return <div className={`smart-list-loading-overlay smart-background-loading-status ${marketLabel==='해외증권'?'overseas-loading-overlay':'domestic-loading-overlay'}`} role="status" aria-live="polite" aria-label={info.title}>
  <div className="smart-list-loading-card">
   <div className="stock-detail-loader-mark smart-list-loader-mark"><div className="sync-spinner"/><Sparkles size={18}/></div>
   <span className="smart-list-loading-context">{marketLabel} · {pageLabel}</span>
   <small>{info.eyebrow}</small>
   <h3>{info.title}</h3>
   <p>{info.desc}</p>
   <div className="smart-list-load-steps">
    {steps.map((item,index)=><div key={item.label} className={`smart-list-load-step ${index<stage?'done':index===stage?'active':''}`}>
      <span>{index<stage?<CheckCircle2 size={13}/>:index+1}</span>
      <div><b>{item.label}</b>{index===stage&&<em>확인 중</em>}</div>
    </div>)}
   </div>
   <div className="stock-detail-load-bar"><i style={{width:`${30+(stage*32)}%`}}/></div>
   <div className="stock-detail-loading-dots"><i/><i/><i/></div>
  </div>
 </div>
}

function PageDataLoadingStatus({marketLabel='국내증권',pageLabel='페이지',title,detail,steps}){
 const [stage,setStage]=useState(0)
 const progressSteps=steps||['현재 화면 유지','최신 데이터 확인','결과 화면 반영']
 useEffect(()=>{
  setStage(0)
  const first=setTimeout(()=>setStage(1),360)
  const second=setTimeout(()=>setStage(2),950)
  return()=>{clearTimeout(first);clearTimeout(second)}
 },[marketLabel,pageLabel,title])
 return <div className={`smart-list-loading-overlay smart-background-loading-status page-data-loading-status ${marketLabel==='해외증권'?'overseas-loading-overlay':'domestic-loading-overlay'}`} role="status" aria-live="polite" aria-label={title||`${pageLabel} 데이터 업데이트 중`}>
  <div className="smart-list-loading-card">
   <div className="stock-detail-loader-mark smart-list-loader-mark"><div className="sync-spinner"/><Activity size={18}/></div>
   <span className="smart-list-loading-context">{marketLabel} · {pageLabel}</span>
   <small>백그라운드 업데이트</small>
   <h3>{title||`${pageLabel} 데이터를 업데이트하고 있어요`}</h3>
   <p>{detail||'화면은 먼저 표시하고 최신 결과가 도착하면 자동으로 반영합니다.'}</p>
   <div className="smart-list-load-steps">
    {progressSteps.map((label,index)=><div key={label} className={`smart-list-load-step ${index<stage?'done':index===stage?'active':''}`}>
     <span>{index<stage?<CheckCircle2 size={13}/>:index+1}</span><div><b>{label}</b>{index===stage&&<em>진행 중</em>}</div>
    </div>)}
   </div>
   <div className="stock-detail-load-bar"><i style={{width:`${30+(stage*32)}%`}}/></div>
  </div>
 </div>
}

function WorkspacePageLoadingOverlay({market='domestic',page='smart',stage=0}){
 const marketLabel=market==='overseas'?'해외증권':'국내증권'
 const pageLabel=STOCKLOG_PAGE_LABELS[page]||'페이지'
 const steps=['메뉴 선택 확인','페이지 화면 준비','최신 정보 연결']
 return <div className={`smart-list-loading-overlay workspace-page-loading-overlay ${market==='overseas'?'overseas-loading-overlay':'domestic-loading-overlay'}`} role="status" aria-live="polite" aria-label={`${marketLabel} ${pageLabel} 로딩 중`}>
  <div className="smart-list-loading-card workspace-page-loading-card">
   <div className="stock-detail-loader-mark smart-list-loader-mark"><div className="sync-spinner"/><Compass size={18}/></div>
   <span className="smart-list-loading-context">{marketLabel} · {pageLabel}</span>
   <small>페이지 이동</small>
   <h3>{marketLabel} {pageLabel} 페이지를 여는 중이에요</h3>
   <p>화면과 필요한 정보를 순서대로 준비하고 있습니다.</p>
   <div className="smart-list-load-steps">
    {steps.map((label,index)=><div key={label} className={`smart-list-load-step ${index<stage?'done':index===stage?'active':''}`}>
     <span>{index<stage?<CheckCircle2 size={13}/>:index+1}</span><div><b>{label}</b>{index===stage&&<em>진행 중</em>}</div>
    </div>)}
   </div>
   <div className="stock-detail-load-bar"><i style={{width:`${30+(stage*32)}%`}}/></div>
  </div>
 </div>
}

function Smart({openStock}){
 const mode='ai'
 const [rows,setRows]=useState([])
 const [meta,setMeta]=useState(null)
 const [strategy,setStrategy]=useState('전체')
 const [theme,setTheme]=useState('전체')
 const [subtheme,setSubtheme]=useState('전체')
 const [filterOptions,setFilterOptions]=useState({themes:[],theme_tree:{},markets:[],access:{}})
 const [filterOptionsLoading,setFilterOptionsLoading]=useState(true)
 const [searchInput,setSearchInput]=useState('')
 const [q,setQ]=useState('')
 const [market,setMarket]=useState('전체')
 const [aiScoreMin,setAiScoreMin]=useState(0)
 const [profileScoreMin,setProfileScoreMin]=useState(0)
 const [coverageMin,setCoverageMin]=useState(0)
 const [marketCapMin,setMarketCapMin]=useState(0)
 const [perMax,setPerMax]=useState(0)
 const [pbrMax,setPbrMax]=useState(0)
 const [roeMin,setRoeMin]=useState(-999)
 const [dividendMin,setDividendMin]=useState(-1)
 const [flowSignal,setFlowSignal]=useState('전체')
 const [sentimentSignal,setSentimentSignal]=useState('전체')
 const [advancedOpen,setAdvancedOpen]=useState(false)
 const [loading,setLoading]=useState(false)
 const [listLoadStage,setListLoadStage]=useState(0)
 const [listLoadKind,setListLoadKind]=useState('initial')
 const [err,setErr]=useState('')
 const [marketOverview,setMarketOverview]=useState([])
 const [marketOverviewLoading,setMarketOverviewLoading]=useState(false)
 const [marketOverviewAt,setMarketOverviewAt]=useState(null)
 const [page,setPage]=useState(1)
 const [pageSize,setPageSize]=useState(10)
 const [scoreDetailCode,setScoreDetailCode]=useState(null)
 const [scoreSort,setScoreSort]=useState({field:'ai_score',order:'desc'})
 const recommendRequestRef=useRef(0)
 const fullMarketAccessHint=Boolean(meta?.access?.full_market_enabled??filterOptions?.access?.full_market_enabled)



 const strategies=['전체','가치','성장','모멘텀','배당','안정']

 useEffect(()=>{setPage(1)},[mode,strategy,theme,subtheme,q,market,aiScoreMin,profileScoreMin,coverageMin,marketCapMin,perMax,pbrMax,roeMin,dividendMin,flowSignal,sentimentSignal,pageSize,scoreSort.field,scoreSort.order])
 const loadFilterOptions=async(silent=false)=>{
  if(!silent)setFilterOptionsLoading(true)
  try{
   const r=await api.get('/api/smart/filter-options')
   setFilterOptions(r.data||{themes:[],theme_tree:{},markets:[],access:{}})
  }catch{
   setFilterOptions({themes:[],theme_tree:{},markets:[],access:{}})
  }finally{
   if(!silent)setFilterOptionsLoading(false)
  }
 }
 useEffect(()=>{if(subtheme!=='전체'&&!(filterOptions?.theme_tree?.[theme]||[]).includes(subtheme))setSubtheme('전체')},[theme,subtheme,filterOptions])
 useEffect(()=>{
  loadFilterOptions()
  const refresh=()=>{loadFilterOptions(true);setTheme('전체');setSubtheme('전체')}
  window.addEventListener('stocklog:themes-normalized',refresh)
  window.addEventListener('stocklog:data-updated',refresh)
  return()=>{window.removeEventListener('stocklog:themes-normalized',refresh);window.removeEventListener('stocklog:data-updated',refresh)}
 },[])

 const load=async(silent=false,kind='filter')=>{
   const requestId=++recommendRequestRef.current
   if(!silent){setListLoadKind(kind);setLoading(true)}
   setErr('')
   try{
     const r=await api.get(`/api/smart/recommend/${mode}`,{
       params:{
        strategy,theme,subtheme,q:q.trim(),page,page_size:pageSize,
        market,ai_score_min:aiScoreMin,profile_score_min:profileScoreMin,
        coverage_min:coverageMin,market_cap_min:marketCapMin,
        per_max:perMax,pbr_max:pbrMax,roe_min:roeMin,dividend_min:dividendMin,
        flow_signal:flowSignal,sentiment_signal:sentimentSignal,
        sort_by:scoreSort.field,sort_order:scoreSort.order
       }
     })
     if(requestId!==recommendRequestRef.current)return
     setRows(r.data.items||[])
     setMeta(r.data)
   }catch(e){
     if(requestId!==recommendRequestRef.current)return
     setRows([])
     setErr(publicUiText(e.response?.data?.detail)||'스마트 추천 데이터를 불러오지 못했습니다.')
   }finally{
     if(requestId===recommendRequestRef.current&&!silent)setLoading(false)
   }
 }

 useEffect(()=>{
  if(!loading){setListLoadStage(0);return}
  setListLoadStage(0)
  const first=setTimeout(()=>setListLoadStage(1),420)
  const second=setTimeout(()=>setListLoadStage(2),1150)
  return()=>{clearTimeout(first);clearTimeout(second)}
 },[loading])

 // 검색어는 입력만으로 조회하지 않습니다. Enter(또는 검색 버튼)로 q가 확정될 때만 API를 호출합니다.
 useEffect(()=>{
   const servedPage=Number(meta?.page||0)
   const kind=!meta?'initial':q.trim()?'search':page!==servedPage?'page':'filter'
   load(false,kind)
 },[mode,strategy,theme,subtheme,q,page,pageSize,market,aiScoreMin,profileScoreMin,coverageMin,marketCapMin,perMax,pbrMax,roeMin,dividendMin,flowSignal,sentimentSignal,scoreSort.field,scoreSort.order])

 useEffect(()=>{
   const timer=setInterval(()=>{
     if(document.visibilityState==='visible')load(true)
   },fullMarketAccessHint?60000:30000)
   return()=>clearInterval(timer)
 },[mode,strategy,theme,subtheme,q,page,pageSize,market,aiScoreMin,profileScoreMin,coverageMin,marketCapMin,perMax,pbrMax,roeMin,dividendMin,flowSignal,sentimentSignal,scoreSort.field,scoreSort.order,fullMarketAccessHint])

 useEffect(()=>{
   const refresh=()=>load(true)
   window.addEventListener('stocklog:data-updated',refresh)
   return()=>window.removeEventListener('stocklog:data-updated',refresh)
 },[mode,strategy,theme,subtheme,q,page,pageSize,market,aiScoreMin,profileScoreMin,coverageMin,marketCapMin,perMax,pbrMax,roeMin,dividendMin,flowSignal,sentimentSignal,scoreSort.field,scoreSort.order])


const loadMarketOverview=async(silent=false)=>{
 if(!silent)setMarketOverviewLoading(true)

 try{
  const r=await api.get(
   '/api/market-overview'
  )

  setMarketOverview(
   r.data.items||[]
  )
  setMarketOverviewAt(
   new Date()
  )

 }catch(e){
  // Macro cards are supplemental. A quote-provider issue must never
  // block the Smart recommendation page.
  if(!silent){
   setMarketOverview([])
  }

 }finally{
  if(!silent)setMarketOverviewLoading(false)
 }
}

useEffect(()=>{
 loadMarketOverview()

 const timer=setInterval(
  ()=>{
   if(
    document.visibilityState
    === 'visible'
   ){
    loadMarketOverview(true)
   }
  },
  30_000
 )

 return()=>clearInterval(timer)
},[])



 const pageRows=rows
 const toggleScoreSort=field=>setScoreSort(current=>({
  field,
  order:current.field===field&&current.order==='desc'?'asc':'desc'
 }))
 const scoreSortIcon=field=><ArrowUpDown size={14} className={`score-sort-icon ${scoreSort.field===field?scoreSort.order:''}`}/>
 const scoreSortClass=field=>scoreSort.field===field?`active order-${scoreSort.order}`:''
 const scoreSortTitle=(field,label)=>{
  const nextOrder=scoreSort.field===field&&scoreSort.order==='desc'?'asc':'desc'
  return `${label} ${nextOrder==='desc'?'높은':'낮은'} 점수순으로 정렬`
 }
 const totalPages=Math.max(1,Number(meta?.pages||1))
 const currentPage=Math.min(Number(meta?.page||page),totalPages)
 const totalResults=Number(meta?.total??rows.length)
 const fullMarketEnabled=fullMarketAccessHint
 const fullMarketSearch=Boolean(!fullMarketEnabled&&meta?.access?.scope==='full_market_search')

 useEffect(()=>{
  if(page>totalPages)setPage(totalPages)
 },[page,totalPages])

 const advancedFilterActive=market!=='전체'||aiScoreMin>0||profileScoreMin>0||coverageMin>0||marketCapMin>0||perMax>0||pbrMax>0||roeMin>-999||dividendMin>-1||flowSignal!=='전체'||sentimentSignal!=='전체'
 const resetAdvancedFilters=()=>{
  setMarket('전체');setAiScoreMin(0);setProfileScoreMin(0);setCoverageMin(0);setMarketCapMin(0)
  setPerMax(0);setPbrMax(0);setRoeMin(-999);setDividendMin(-1);setFlowSignal('전체');setSentimentSignal('전체')
 }

 return <>
   <div className="page-head smart-page-head">
     <div>
       <span>스마트 분석</span>
       <h1>국내 증권</h1>
       <p>{fullMarketAccessHint?'KOSPI·KOSDAQ 일반 상장종목을 StockLog 종합점수와 투자성향으로 분석합니다.':'일반 회원은 매일 새로운 종목을 둘러볼 수 있으며, 종합점수와 투자성향 비교는 프리미엄에서 제공됩니다.'}</p>
     </div>

     <div className="smart-page-tools">
      <div className="smart-market-mini" aria-label="주요 시장 지표">
       <div className="smart-market-mini-title">
        <span>주요 시장지표</span>
        <small className={marketOverviewLoading?'smart-market-loading':''}>{marketOverviewLoading?<><RefreshCw size={11} className="spin-icon"/>불러오는 중</>:marketOverviewAt?marketOverviewAt.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):''}</small>
       </div>
       <div className="smart-market-mini-items">
        {(marketOverview.length
          ? marketOverview
          : [
             {key:'nasdaq',label:'NASDAQ'},
             {key:'kospi',label:'KOSPI'},
             {key:'kosdaq',label:'KOSDAQ'},
             {key:'usdkrw',label:'달러 / 원화'},
             {key:'usdjpy',label:'원화 / 엔'},
            ]
         ).map(item=>{
          const value=Number(item.value)
          const rate=Number(item.change_rate)
          const available=item.available!==false&&Number.isFinite(value)
          const direction=Number.isFinite(rate)?rate>0?'up':rate<0?'down':'flat':'flat'
          const decimals=0
          return <span className="smart-market-mini-item" key={item.key} title={item.sub_label||item.label}>
            <b>{item.label}</b>
            <em>{available?value.toLocaleString(undefined,{minimumFractionDigits:decimals,maximumFractionDigits:decimals}):'--'}</em>
            <i className={direction}>{Number.isFinite(rate)?`${rate>0?'+':''}${Math.round(rate)}%`:''}</i>
           </span>
         })}
       </div>
      </div>

     </div>
   </div>

   {loading&&<SmartListLoadingOverlay kind={listLoadKind} stage={listLoadStage} page={page} query={q.trim()}/>}

   <section className={`smart-membership-value ${fullMarketEnabled?'premium':'normal'}`}>
    <div className="smart-membership-value-copy">
     <small>{fullMarketEnabled?'적용된 혜택':'분석 범위 안내'}</small>
     <b>{fullMarketEnabled?'프리미엄 기능을 이용하고 있습니다':'프리미엄으로 더 넓게 분석할 수 있습니다'}</b>
     <p>{fullMarketEnabled
      ? 'KOSPI·KOSDAQ 일반 상장종목 전체를 종합점수와 내 투자성향으로 살펴볼 수 있습니다.'
      : '프리미엄에서는 KOSPI·KOSDAQ 일반 상장종목 전체, 종합점수, 내 투자성향 비교와 더 자세한 분석 기능을 사용할 수 있습니다.'}</p>
    </div>
    <div className="smart-membership-benefits" aria-label={fullMarketEnabled?'적용 중인 프리미엄 기능':'프리미엄 제공 기능'}>
     <span>{fullMarketEnabled?'전체 분석종목 보기':'전체 분석종목 보기'}</span>
     <span>{fullMarketEnabled?'고급 조건 검색':'고급 조건 검색'}</span>
     <span>{fullMarketEnabled?'점수 상세 비교':'점수 상세 비교'}</span>
     <span>{fullMarketEnabled?'종목 상세 프리미엄 AI 분석':'종목 상세 프리미엄 AI 분석'}</span>
    </div>
   </section>


   <div className="smart-list-controls">
     <div className="smart-search-section">
       <div className="smart-search-heading"><span>종목 검색</span><small>종목명 또는 코드</small></div>
       <SmartStockSearch value={searchInput} onChange={setSearchInput} onSearch={value=>{const next=String(value||'').trim();setPage(1);if(next===q)load(false,next?'search':'filter');else setQ(next)}} onClear={()=>{setPage(1);if(q)setQ('')}} loading={loading&&listLoadKind==='search'}/>
     </div>
     <div className={`smart-filter-shell ${filterOptionsLoading?'is-loading':''}`} aria-busy={filterOptionsLoading?'true':'false'}>
      <div className="smart-filter-toolbar-head"><div><span>조건 필터</span><small>원하는 조건만 빠르게 조합하세요</small></div><b>{[strategy!=='전체',theme!=='전체',subtheme!=='전체',advancedFilterActive].filter(Boolean).length}개 적용</b></div>
      {filterOptionsLoading&&<span className="smart-filter-options-loading"><RefreshCw size={12} className="spin-icon"/>테마·시장 필터를 준비하고 있어요</span>}
      <div className="smart-explore-filters">
       <div className="smart-filter-field">
        <label htmlFor="smart-strategy">투자 스타일</label>
        <select id="smart-strategy" value={strategy} onChange={e=>setStrategy(e.target.value)}>
         {strategies.map(x=><option value={x} key={x}>{x==='전체'?'스타일 전체':x}</option>)}
        </select>
       </div>
       <div className="smart-filter-field theme">
        <label htmlFor="smart-theme">대표 테마</label>
        <select id="smart-theme" value={theme} onChange={e=>{setTheme(e.target.value);setSubtheme('전체')}}>
         <option value="전체">대표 테마 전체</option>
         {(filterOptions.themes||[]).map(x=><option value={x} key={x}>{x}</option>)}
        </select>
       </div>
       {theme!=='전체'&&(filterOptions?.theme_tree?.[theme]||[]).length>0&&<div className="smart-filter-field theme-sub">
        <label htmlFor="smart-subtheme">세부 테마</label>
        <select id="smart-subtheme" value={subtheme} onChange={e=>setSubtheme(e.target.value)}>
         <option value="전체">세부 테마 전체</option>
         {(filterOptions?.theme_tree?.[theme]||[]).map(x=><option value={x} key={x}>{x}</option>)}
        </select>
       </div>}
       {fullMarketEnabled&&<div className="smart-filter-field">
        <label htmlFor="smart-market">시장</label>
        <select id="smart-market" value={market} onChange={e=>setMarket(e.target.value)}>
         <option value="전체">시장 전체</option>
         {(filterOptions.markets||[]).map(x=><option value={x} key={x}>{x}</option>)}
        </select>
       </div>}
       {fullMarketEnabled&&<button type="button" className={`smart-advanced-toggle ${advancedOpen?'active':''}`} onClick={()=>setAdvancedOpen(v=>!v)}><SlidersHorizontal size={15}/>고급 필터{advancedFilterActive&&<i/>}</button>}
       {(strategy!=='전체'||theme!=='전체'||subtheme!=='전체'||advancedFilterActive)&&<button type="button" className="smart-filter-reset" onClick={()=>{setStrategy('전체');setTheme('전체');setSubtheme('전체');resetAdvancedFilters()}}>전체 초기화</button>}
      </div>

      {fullMarketEnabled&&advancedOpen&&<div className="smart-premium-filter-grid">
       <div className="smart-filter-field"><label>종합점수 최소</label><select value={aiScoreMin} onChange={e=>setAiScoreMin(Number(e.target.value))}>{[0,50,60,70,80].map(x=><option key={x} value={x}>{x?`${x}점 이상`:'제한 없음'}</option>)}</select></div>
       <div className="smart-filter-field"><label>내 성향 최소</label><select value={profileScoreMin} disabled={!meta?.profile} onChange={e=>setProfileScoreMin(Number(e.target.value))}>{[0,50,60,70,80].map(x=><option key={x} value={x}>{x?`${x}점 이상`:'제한 없음'}</option>)}</select></div>
       <div className="smart-filter-field"><label>데이터 커버리지</label><select value={coverageMin} onChange={e=>setCoverageMin(Number(e.target.value))}>{[0,50,70,85,100].map(x=><option key={x} value={x}>{x?`${x}% 이상`:'제한 없음'}</option>)}</select></div>
       <div className="smart-filter-field"><label>시가총액</label><select value={marketCapMin} onChange={e=>setMarketCapMin(Number(e.target.value))}>{[[0,'제한 없음'],[1000,'1,000억원 이상'],[5000,'5,000억원 이상'],[10000,'1조원 이상'],[50000,'5조원 이상']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
       <div className="smart-filter-field"><label>PER</label><select value={perMax} onChange={e=>setPerMax(Number(e.target.value))}>{[[0,'제한 없음'],[10,'10배 이하'],[15,'15배 이하'],[20,'20배 이하'],[30,'30배 이하']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
       <div className="smart-filter-field"><label>PBR</label><select value={pbrMax} onChange={e=>setPbrMax(Number(e.target.value))}>{[[0,'제한 없음'],[1,'1배 이하'],[1.5,'1.5배 이하'],[2,'2배 이하'],[3,'3배 이하']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
       <div className="smart-filter-field"><label>ROE</label><select value={roeMin} onChange={e=>setRoeMin(Number(e.target.value))}>{[[-999,'제한 없음'],[5,'5% 이상'],[10,'10% 이상'],[15,'15% 이상'],[20,'20% 이상']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
       <div className="smart-filter-field"><label>배당수익률</label><select value={dividendMin} onChange={e=>setDividendMin(Number(e.target.value))}>{[[-1,'제한 없음'],[1,'1% 이상'],[2,'2% 이상'],[3,'3% 이상'],[5,'5% 이상']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
       <div className="smart-filter-field"><label>외국인·기관 수급</label><select value={flowSignal} onChange={e=>setFlowSignal(e.target.value)}><option value="전체">전체</option><option value="긍정">긍정</option><option value="부정">부정</option></select></div>
       <div className="smart-filter-field"><label>뉴스·리포트</label><select value={sentimentSignal} onChange={e=>setSentimentSignal(e.target.value)}><option value="전체">전체</option><option value="긍정">긍정</option><option value="부정">부정</option></select></div>
       <div className="smart-filter-field"><label>페이지당</label><select value={pageSize} onChange={e=>setPageSize(Number(e.target.value))}>{[10,20,50].map(x=><option key={x} value={x}>{x}종목</option>)}</select></div>
       <div className="smart-premium-filter-note"><Gauge size={15}/><span>수급·뉴스 필터는 동기화된 항목 점수를 사용하며 데이터가 없는 종목은 해당 조건에서 제외됩니다.</span></div>
      </div>}
     </div>
   </div>

   {err&&<div className="error-box"><b>스마트 추천 조회 오류</b><span>{err}</span></div>}

   {!err&&<div className={`smart-table-wrap smart-recommend-table smart-dual-score-table ${loading?'is-loading':''}`} aria-busy={loading?'true':'false'}>
     <div className="smart-table-head smart-recommend-head smart-dual-score-head">
       <span>{fullMarketEnabled?'순위':fullMarketSearch?'검색':'번호'}</span><span>종목</span><span>현재가</span><span>핵심 지표</span><span className="smart-score-head-label">StockLog 종합점수 <button type="button" className={`score-sort-btn ${scoreSortClass('ai_score')}`} title={scoreSortTitle('ai_score','종합점수')} aria-label={scoreSortTitle('ai_score','StockLog 종합점수')} disabled={!fullMarketEnabled} onClick={()=>toggleScoreSort('ai_score')}>{scoreSortIcon('ai_score')}</button><SmartInfoTooltip text={meta?.score_guide?.ai||'StockLog 알고리즘으로 여러 투자 데이터를 같은 기준으로 계산한 점수입니다. 더 깊은 해석은 종목 상세의 프리미엄 AI 분석에서 확인할 수 있습니다.'}/></span><span className="smart-score-head-label">내 투자성향 <button type="button" className={`score-sort-btn ${scoreSortClass('profile_score')}`} title={scoreSortTitle('profile_score','성향 적합도')} aria-label={scoreSortTitle('profile_score','내 투자성향 적합도')} disabled={!fullMarketEnabled||!meta?.profile} onClick={()=>toggleScoreSort('profile_score')}>{scoreSortIcon('profile_score')}</button><SmartInfoTooltip text={meta?.score_guide?.profile||'종합점수와 별개로 이 종목의 성격이 내 투자방식과 얼마나 잘 맞는지 계산합니다.'}/></span><span>상세 보기</span>
     </div>
     {rows.length
         ? pageRows.map((s,index)=>{
             const aiScore=fullMarketEnabled?Number(s.ai_recommend_score||0):null
             const profileScore=fullMarketEnabled&&(s.profile_recommend_score!==null&&s.profile_recommend_score!==undefined)?Number(s.profile_recommend_score):null
             const aiTone=aiScore===null?'locked':aiScore>=80?'good':aiScore<70?'bad':'normal'
             const profileTone=!fullMarketEnabled?'locked':profileScore===null?'disabled':profileScore>=80?'good':profileScore<70?'bad':'normal'
             const visibleIndex=(currentPage-1)*pageSize+index+1
             return <div className="smart-table-row smart-recommend-row smart-dual-score-row" key={s.code}>
               <span className={`smart-rank-cell ${fullMarketEnabled?'ranked':fullMarketSearch?'search':'random'}`}><strong>{visibleIndex}</strong><small>{fullMarketEnabled?'위':fullMarketSearch?'검색':'랜덤'}</small></span>
               <span className="smart-stock-name"><span className="stock-title-line"><b>{s.name}</b>{Array.isArray(s.former_names)&&s.former_names.length>0&&<small className="stock-former-name">구 {s.former_names[0]}</small>}<StockThemeBadges themes={s.themes} fallback={s.theme_fallback} max={2} compact/></span><span className="smart-stock-subline"><small>{s.code} / {s.market}</small><small className="smart-updated-at">{smartUpdatedText(s.recommendation_updated_at)}</small></span></span>
               <span className="smart-price-cell"><b>{won(s.price)}</b><small>원</small><em className={Number(s.change_rate)>=0?'up':'down'}>{pct(s.change_rate)}</em></span>
               <span className="smart-core-metrics">
                <i><small>PER <SmartInfoTooltip text="회사가 버는 돈에 비해 주가가 어느 정도인지 보는 값입니다. 같은 업종에서는 보통 낮을수록 가격 부담이 적지만, 너무 낮다면 이유가 있는지도 확인해야 합니다."/></small><b>{metricValue(s.per,'배')}</b></i>
                <i><small>PBR <SmartInfoTooltip text="회사가 가진 순자산과 비교해 주가가 어느 정도인지 보는 값입니다. 1배 근처나 아래면 자산가치보다 낮게 거래될 수 있지만 업종마다 기준이 다릅니다."/></small><b>{metricValue(s.pbr,'배')}</b></i>
                <i><small>ROE <SmartInfoTooltip text="회사가 자기 돈을 이용해 이익을 얼마나 잘 내는지 보여주는 값입니다. 보통 꾸준히 높을수록 돈을 효율적으로 쓰는 회사로 봅니다."/></small><b>{metricValue(s.roe,'%')}</b></i>
                <i><small>성장 <SmartInfoTooltip text="최근 매출이 얼마나 늘거나 줄었는지 보여줍니다. 한 번 크게 오르는 것보다 꾸준히 성장하는지 함께 보는 것이 좋습니다."/></small><b>{metricValue(s.revenue_growth,'%')}</b></i>
               </span>
               {!fullMarketEnabled
                ? <span className="smart-premium-score-lock"><LockKeyhole size={18}/><b>프리미엄 회원만 제공됩니다</b><small>StockLog 종합점수와 KOSPI·KOSDAQ 분석종목 순위를 확인할 수 있습니다.</small></span>
                : !s.analysis_ready
                  ? <span className="smart-dual-score-card ai disabled"><small>종합점수</small><div className="smart-score-number"><strong>--</strong></div><b>분석 데이터 준비 중</b><span>{s.analysis_exclusion_reason||'다음 동기화에서 분석 데이터를 준비합니다.'}</span></span>
                  : <span className={`smart-dual-score-card ai ${aiTone}`}><small>종합점수</small><div className="smart-score-number"><strong>{Math.round(aiScore)}</strong><em>점</em></div><b>{s.ai_recommend_label||'분석'}</b><i><em style={{width:`${Math.max(0,Math.min(100,aiScore))}%`}}/></i><span>데이터 {Math.round(Number(s.score_coverage||0))}%</span></span>}
               {!fullMarketEnabled
                ? <span className="smart-premium-score-lock"><LockKeyhole size={18}/><b>프리미엄 회원만 제공됩니다</b><small>내 투자성향과 종목의 적합도를 비교할 수 있습니다.</small></span>
                : !s.analysis_ready
                  ? <span className="smart-dual-score-card profile disabled"><small>성향 적합도</small><div className="smart-score-number"><strong>--</strong></div><b>분석 데이터 준비 중</b><span>기업 분석 완료 후 계산됩니다.</span></span>
                  : <span className={`smart-dual-score-card profile ${profileTone}`}><small>성향 적합도</small>{profileScore===null?<><div className="smart-score-number"><strong>--</strong></div><b>성향 검사 필요</b><span>검사 후 자동 비교</span></>:<><div className="smart-score-number"><strong>{Math.round(profileScore)}</strong><em>점</em></div><b>{s.profile_recommend_label||'적합도'}</b><i><em style={{width:`${Math.max(0,Math.min(100,profileScore))}%`}}/></i><span>{meta?.profile?.result_code?`유형 ${meta.profile.result_code}`:'성향 적합도'}</span></>}</span>}
               <span className="smart-score-actions">
                {fullMarketEnabled&&s.analysis_ready?<button type="button" className="smart-score-detail-button" onClick={()=>setScoreDetailCode(s.code)}>점수 상세</button>:<button type="button" className="smart-score-detail-button locked" disabled title="프리미엄 이상 회원에게 제공됩니다">점수 상세</button>}
                <button type="button" className="smart-stock-detail-button" onClick={()=>openStock({code:s.code,smartMode:mode,recommendScore:fullMarketEnabled?s.recommend_score:null,recommendType:fullMarketEnabled?s.recommend_type:null})}>종목 상세</button>
               </span>
             </div>
           })
         : <div className="empty">{q.trim()?'검색 조건에 맞는 종목이 없습니다.':'현재 기준에 맞는 종목이 없습니다.'}</div>}
   </div>}


   {!err&&rows.length>0&&<div className="stocklog-pagination" aria-label="스마트 분석 페이지 이동">
     <button type="button" onClick={()=>setPage(1)} disabled={loading||currentPage===1}>처음</button>
     <button type="button" onClick={()=>setPage(p=>Math.max(1,p-1))} disabled={loading||currentPage===1}>이전</button>
     <div className="stocklog-page-numbers">
       {Array.from({length:totalPages},(_,i)=>i+1)
         .filter(n=>n===1||n===totalPages||Math.abs(n-currentPage)<=2)
         .map((n,i,arr)=>{
           const prev=arr[i-1]
           return <span key={n} className="stocklog-page-number-wrap">
             {prev&&n-prev>1&&<em>…</em>}
             <button type="button" className={n===currentPage?'active':''} onClick={()=>setPage(n)} disabled={loading}>{n}</button>
           </span>
         })}
     </div>
     <button type="button" onClick={()=>setPage(p=>Math.min(totalPages,p+1))} disabled={loading||currentPage===totalPages}>다음</button>
     <button type="button" onClick={()=>setPage(totalPages)} disabled={loading||currentPage===totalPages}>끝</button>
     <small>{loading?<><RefreshCw size={12} className="spin-icon"/>목록 갱신 중</>:<>{currentPage} / {totalPages} 페이지 / 총 {totalResults.toLocaleString()}개</>}</small>
   </div>}

   {scoreDetailCode&&<SmartScoreDetail code={scoreDetailCode} onClose={()=>setScoreDetailCode(null)} onOpenStock={({code})=>{setScoreDetailCode(null);openStock({code,smartMode:mode})}}/>}

 </>
}

function HighlightFinancialMetrics({children,sentiment=''}){
 const text=cleanMultiline(publicUiText(children))
 const lines=String(text||'').split('\n')
 const metricPattern=/([+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:%|배|억원|조원|원|주|점))/g
 const exactMetric=/^[+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:%|배|억원|조원|원|주|점)$/
 const tone=['positive','negative','neutral'].includes(String(sentiment))?` sentiment-${sentiment}`:''
 const renderLine=(line,lineIndex)=>{
  const parts=line.split(metricPattern)
  return <span key={`metric-line-${lineIndex}`}>{parts.map((part,index)=>exactMetric.test(part)?<strong className={`inline-financial-emphasis${tone}`} key={index}>{part}</strong>:<span key={index}>{part}</span>)}{lineIndex<lines.length-1&&<br/>}</span>
 }
 return <>{lines.map(renderLine)}</>
}

function AiReadableText({children,className=''}){
 const text=cleanMultiline(publicUiText(children))
 if(!text)return null
 const sourceBlocks=text.split(/\n+/).map(x=>x.trim()).filter(Boolean)
 const paragraphs=[]
 sourceBlocks.forEach(block=>{
  const sentences=block
   .split(/(?<=[.!?])\s+(?=[가-힣A-Za-z0-9“"'‘(])/g)
   .map(x=>x.trim())
   .filter(Boolean)
  if(sentences.length<=1){
   paragraphs.push(block)
   return
  }
  for(let i=0;i<sentences.length;i+=2){
   paragraphs.push(sentences.slice(i,i+2).join(' '))
  }
 })
 return <div className={`ai-readable-text ${className}`.trim()}>
  {paragraphs.map((paragraph,index)=><p key={`ai-readable-${index}`}><HighlightFinancialMetrics>{paragraph}</HighlightFinancialMetrics></p>)}
 </div>
}


function AnalysisSection({title,items=[]}){
 return <div className="analysis-block"><h4 className="explainable-heading">{title}<MetricInfo metric={title}/></h4>{items.length?items.map((x,i)=><p key={i}><HighlightFinancialMetrics>{x}</HighlightFinancialMetrics></p>):<p className="muted">분석할 데이터가 충분하지 않습니다.</p>}</div>
}

function AiUsageBadge({user}){
 const aiPolicy=user?.features?.ai_analysis
 const aiEnabled=aiPolicy?.enabled!==false
 const policyLimit=Number(aiPolicy?.limit_value)
 const policyUnlimited=Boolean(user?.is_admin)||(Number.isFinite(policyLimit)&&policyLimit<0)
 const [usage,setUsage]=useState(null)

 useEffect(()=>{
  if(!aiEnabled){
   setUsage(null)
   return undefined
  }

  let cancelled=false

  const load=async()=>{
   try{
    const r=await api.get('/api/ai-usage')
    if(!cancelled)setUsage(r.data||null)
   }catch{
    // The badge is supplemental UI. A transient usage API failure must never
    // make the authenticated application unusable. Keep the policy fallback.
   }
  }

  load()
  window.addEventListener('ai-usage-changed',load)

  return()=>{
   cancelled=true
   window.removeEventListener('ai-usage-changed',load)
  }
 },[user?.id,aiEnabled])

 if(!aiEnabled)return null

 const unlimited=usage?.unlimited===true||policyUnlimited
 if(unlimited){
  return <span className="ai-usage-badge unlimited" title="AI 종목 분석 사용 횟수 제한이 없습니다."><Sparkles size={11}/><span>AI</span><b>무제한</b></span>
 }

 const fallbackLimit=Number.isFinite(policyLimit)&&policyLimit>=0?policyLimit:5
 const dailyLimit=Number.isFinite(Number(usage?.daily_limit))?Number(usage.daily_limit):fallbackLimit
 const used=Number.isFinite(Number(usage?.used))?Number(usage.used):null
 const remaining=Number.isFinite(Number(usage?.remaining))?Number(usage.remaining):null
 const label=used===null?`하루 ${dailyLimit}회`:`${used}/${dailyLimit}회`
 const title=remaining===null
  ? `AI 종목 분석은 하루 ${dailyLimit}회까지 사용할 수 있습니다.`
  : `오늘 ${used}회 사용 · ${remaining}회 남음 · 매일 00:00 초기화`

 return <span className="ai-usage-badge" title={title}><Sparkles size={11}/><span>AI</span><b>{label}</b></span>
}

function DetailFold({label,meta='',open=true,children,className=''}){
 return <details className={`detail-content-fold ${className}`} open={open}>
  <summary aria-label={`${label} 접기 또는 펼치기`}>
   <span className="detail-fold-copy">
    <b>{label}</b>
    {meta&&<small>{meta}</small>}
   </span>
   <span className="detail-fold-toggle" aria-hidden="true">
    <span className="detail-fold-toggle-copy">
     <em className="detail-fold-open-label">접기</em>
     <em className="detail-fold-closed-label">펼치기</em>
    </span>
    <span className="detail-fold-toggle-icon">
     <ChevronRight size={17} className="detail-fold-chevron"/>
    </span>
   </span>
  </summary>
  <div className="detail-content-fold-body">{children}</div>
 </details>
}

function StockDetail({code,onClose,smartMode="ai",recommendScore=null,recommendType="",onBuy,user}){
 const [d,setD]=useState(null)
 const [refreshingNews,setRefreshingNews]=useState(false)
 const [err,setErr]=useState('')
 const [aiAnalysis,setAiAnalysis]=useState(null)
 const [aiLoading,setAiLoading]=useState(false)
 const [aiStage,setAiStage]=useState('')
 const [aiProgress,setAiProgress]=useState(null)
 const [aiElapsed,setAiElapsed]=useState(0)
 const [aiError,setAiError]=useState('')
 const [reportPage,setReportPage]=useState(1)
 const [newsPage,setNewsPage]=useState(1)
 const [reportFilter,setReportFilter]=useState('all')
 const [newsFilter,setNewsFilter]=useState('all')
 const [disclosurePage,setDisclosurePage]=useState(1)
 const [detailLoadStage,setDetailLoadStage]=useState(0)
 const [aiConsentOpen,setAiConsentOpen]=useState(false)
 const [aiUsageInfo,setAiUsageInfo]=useState(null)
 const [aiUsageLoading,setAiUsageLoading]=useState(false)
 const [vixContext,setVixContext]=useState(null)
 const detailPageSize=2
 const aiPolicy=user?.features?.ai_analysis
 const aiAllowed=aiPolicy?.enabled!==false
 const aiLimit=aiPolicy?.limit_value
 const membershipTier=String(user?.membership_tier||user?.account_type||'NORMAL').toUpperCase()
 const membershipLabel=user?.membership_label||({NORMAL:'일반회원',PREMIUM:'프리미엄회원',EVENT:'이벤트회원',ADMIN:'관리자'}[membershipTier]||'현재 등급')
 const premiumAiEnabled=['PREMIUM','EVENT','ADMIN'].includes(membershipTier)
 const aiAnalysisLabel=premiumAiEnabled?'프리미엄 AI 분석':'AI 분석'
 const openAiConsent=async()=>{
  setAiUsageLoading(true)
  setAiError('')
  try{
   const r=await api.get('/api/ai-usage',{timeout:10000})
   setAiUsageInfo(r.data||null)
  }catch{
   setAiUsageInfo(null)
  }finally{
   setAiUsageLoading(false)
   setAiConsentOpen(true)
  }
 }
 const acceptAiAnalysis=()=>{
  setAiConsentOpen(false)
  loadAiAnalysis(Boolean(aiAnalysis?.result))
 }

 const load=async()=>{
   setD(null)
   setErr('')
   setDetailLoadStage(0)
   try{
     const r=await api.get(`/api/stocks/${code}/detail`,{params:{smart_mode:smartMode||'ai'}})
     setD(r.data)
     window.dispatchEvent(
       new CustomEvent('stocklog:data-updated',{
         detail:{code}
       })
     )
   }catch(e){
     setErr(
       publicUiText(e.response?.data?.detail)
       || '종목 상세 조회 실패'
     )
   }
 }

 useEffect(()=>{
  let cancelled=false
  setVixContext(null)
  api.get('/api/market-overview',{timeout:10000})
   .then(response=>{
    if(cancelled)return
    const item=(response.data?.items||[]).find(value=>value?.key==='vix')
    setVixContext(item?.available?item:null)
   })
   .catch(()=>{if(!cancelled)setVixContext(null)})
  return()=>{cancelled=true}
 },[code])

 useEffect(()=>{
   setReportPage(1)
   setNewsPage(1)
   setDisclosurePage(1)
   setAiAnalysis(null)
   setAiError('')
   setAiStage('')
   setAiProgress(null)
   setAiElapsed(0)
   load()
 },[code,smartMode])

 useEffect(()=>{
   if(d||err)return
   const timers=[
     setTimeout(()=>setDetailLoadStage(1),750),
     setTimeout(()=>setDetailLoadStage(2),1750),
     setTimeout(()=>setDetailLoadStage(3),2950)
   ]
   return()=>timers.forEach(clearTimeout)
 },[code,smartMode,Boolean(d),Boolean(err)])

 useEffect(()=>{
   const key=e=>{
     if(e.key==='Escape')onClose()
   }
   window.addEventListener('keydown',key)
   return()=>window.removeEventListener('keydown',key)
 },[onClose])

 useEffect(()=>{
   const before=document.body.style.overflow
   document.body.style.overflow='hidden'

   return()=>{
    document.body.style.overflow=before
   }
 },[])


useEffect(()=>{
 if(!aiLoading)return
 const parsed=Date.parse(aiProgress?.started_at||'')
 const serverStart=Number.isFinite(parsed)?parsed:Date.now()-Math.max(0,Number(aiProgress?.elapsed_seconds||0))*1000
 const tick=()=>setAiElapsed(Math.max(0,Math.floor((Date.now()-serverStart)/1000)))
 tick()
 const timer=setInterval(tick,1000)
 return()=>clearInterval(timer)
},[aiLoading,aiProgress?.started_at])

const formatAiElapsed=(seconds)=>{
 const value=Math.max(0,Math.floor(Number(seconds)||0))
 const minutes=Math.floor(value/60)
 const remain=value%60
 return minutes>0?`${minutes}분 ${remain}초`:`${remain}초`
}

const loadAiAnalysis=async(force=false)=>{
 setAiError('')
 setAiLoading(true)
 if(force){
  setAiStage('queued')
  setAiProgress(null)
  setAiElapsed(0)
 }

 const modeValue=smartMode||'ai'

 const getStatus=async()=>{
  const r=await api.get(
   `/api/stocks/${code}/ai-analysis/status`,
   {
    params:{
     smart_mode:modeValue
    },
    timeout:10000
   }
  )

  return r.data
 }

 const applyStatus=(value,{showFailure=true}={})=>{
  if(value?.status)setAiStage(String(value.status))
  if(value?.progress){
   setAiProgress(value.progress)
   if(Number.isFinite(Number(value.progress.elapsed_seconds)))setAiElapsed(Number(value.progress.elapsed_seconds))
  }
  if(
   value?.result
   && (
    value.status==='ready'
    || value.status==='stale'
   )
  ){
   setAiAnalysis({
    ...value,
    cached:true
   })
   setAiError('')
  }

  if(value?.status==='failed'&&showFailure){
   setAiError(
    value.message
    || value.error_message
    || 'AI 분석에 실패했습니다.'
   )
  }
 }

 try{
  const current=await getStatus()
  // A failed row may be from a previous analysis. Do not flash that old
  // error while immediately starting a fresh analysis for this detail view.
  applyStatus(current,{showFailure:false})

  if(
   !force
   && current?.status==='ready'
   && !current?.stale
   && current?.result
  ){
   setAiLoading(false)
   return
  }

  if(
   !['running','context','queued','obot_running','obot_completed','gbot_running','gbot_completed','verifying'].includes(
    current?.status
   )
  ){
   await api.post(
    `/api/stocks/${code}/ai-analysis/start`,
    null,
    {
     params:{
      smart_mode:modeValue,
      force
     },
     timeout:10000
    }
   )
   window.dispatchEvent(new Event('ai-usage-changed'))
   // Clear any persisted failure from the previous run once a new job starts.
   setAiError('')
   setAiStage('queued')
   setAiProgress({stage:'queued',phase:'queued',message:'프리미엄 AI 분석을 시작할 준비를 하고 있습니다.',elapsed_seconds:0,attempt:1,started_at:new Date().toISOString()})
   setAiElapsed(0)
  }

  setAiLoading(true)

  const startedAt=Date.now()
  // Premium detail analysis now uses Gbot only. Keep polling beyond the server-side
  // Gbot safety limit so a completed result is not missed by the browser.
  const maxWaitMs=4*60*1000

  while(Date.now()-startedAt<maxWaitMs){
   await new Promise(
    resolve=>setTimeout(resolve,2000)
   )

   const state=await getStatus()
   applyStatus(state)

   if(
    state?.status==='ready'
    && state?.result
   ){
    setAiAnalysis({
     ...state,
     cached:true
    })
    setAiLoading(false)
    return
   }

   if(state?.status==='failed'){
    // Only show a failure returned by the newly started/polled run.
    applyStatus(state,{showFailure:true})
    setAiLoading(false)
    return
   }
  }

  setAiError(
   'AI 분석이 장시간 진행되고 있습니다. 상세페이지를 다시 열면 현재 진행 상태 또는 완료 결과를 이어서 확인할 수 있습니다.'
  )
  setAiLoading(false)

 }catch(e){
  setAiError(
   publicUiText(e.response?.data?.detail)
   || (
    e.code==='ECONNABORTED'
     ? 'StockLog 백엔드 응답 시간이 초과되었습니다.'
     : 'AI 상태를 확인하지 못했습니다.'
   )
  )
  setAiLoading(false)
 }
}

// 이미 완료한 분석은 비용을 다시 쓰지 않고 상세 진입 시 자동으로 보여줍니다.
useEffect(()=>{
 let cancelled=false
 if(!d||!code||!aiAllowed)return()=>{cancelled=true}
 const loadExisting=async()=>{
  try{
   const r=await api.get(`/api/stocks/${code}/ai-analysis/status`,{params:{smart_mode:smartMode||'ai'},timeout:10000})
   const state=r.data
   if(cancelled)return
   if(state?.result&&['ready','stale'].includes(state?.status)){
    setAiAnalysis({...state,cached:true})
    setAiError('')
   }else if(['queued','context','running','obot_running','obot_completed','gbot_running','gbot_completed','verifying'].includes(state?.status)){
    // Reopening the stock detail while a shared premium job is running should
    // reconnect to the same job and resume its live progress instead of looking idle.
    setAiStage(String(state.status))
    if(state.progress)setAiProgress(state.progress)
    loadAiAnalysis(false)
   }
  }catch(e){
   // missing entitlement/result is expected for stocks the member never analyzed.
  }
 }
 loadExisting()
 return()=>{cancelled=true}
},[Boolean(d),code,smartMode,aiAllowed])


 const refreshNews=async()=>{
   setRefreshingNews(true)
   try{
     const r=await api.get(`/api/stocks/${code}/detail`,{params:{smart_mode:smartMode||'ai',refresh_news:true},timeout:45000})
     setD(r.data)
     setNewsPage(1)
     setReportPage(1)
     setDisclosurePage(1)
   }catch(e){
     await showMessage(
       publicUiText(e.response?.data?.detail)
       || '최신 뉴스/공시/리포트 갱신에 실패했습니다.',
       '최신 정보 조회 오류',
       'danger'
     )
   }finally{
     setRefreshingNews(false)
   }
 }

 const backdrop=e=>{
   if(e.target===e.currentTarget)onClose()
 }

 if(err){
   return <div className="modal" onMouseDown={backdrop}>
     <div className="detail">
       <button className="close" onClick={onClose}><X/></button>
       <div className="error-box">{err}</div>
     </div>
   </div>
 }

 if(!d){
   const loadingSteps=[
    {label:'기본 정보 확인',desc:'현재가와 종목 기본 정보를 불러오고 있어요.'},
    {label:'재무 · 분석 데이터',desc:'재무지표와 투자 분석 데이터를 정리하고 있어요.'},
    {label:'뉴스 · 공시 · 리포트',desc:'최신 참고 데이터를 함께 준비하고 있어요.'},
    {label:'차트 분석',desc:'일봉과 이동평균·추세 신호를 마지막으로 분석하고 있어요.'}
   ]
   return <div className="modal stock-detail-loading-modal stock-detail-loading-curtain" onMouseDown={backdrop}>
     <div className="stock-detail-loading-stage">
       <button className="close stock-detail-loading-close" onClick={onClose} aria-label="종목 상세 닫기"><X/></button>
       <div className="stock-detail-loader-card" role="status" aria-live="polite">
        <div className="stock-detail-loader-mark">
         <div className="sync-spinner"/>
         <Sparkles size={19}/>
        </div>
        <small>STOCKLOG ANALYSIS</small>
        <h3>종목 분석 데이터를 준비하고 있어요</h3>
        <p>{loadingSteps[detailLoadStage]?.desc}</p>

        <div className="stock-detail-load-steps">
         {loadingSteps.map((step,index)=>
          <div key={step.label} className={`stock-detail-load-step ${index<detailLoadStage?'done':index===detailLoadStage?'active':''}`}>
           <span>{index<detailLoadStage?<CheckCircle2 size={14}/>:index+1}</span>
           <div>
            <b>{step.label}</b>
            {index===detailLoadStage&&<em>확인 중</em>}
           </div>
          </div>
         )}
        </div>

        <div className="stock-detail-load-bar"><i style={{width:`${25+(detailLoadStage*25)}%`}}/></div>
        <div className="stock-detail-loading-dots"><i/><i/><i/></div>
       </div>
     </div>
   </div>
 }

 const s=d.stock
 const rawAnalysis=d.analysis||{recommendation:'분석 대기',score:0,summary:'분석 데이터가 충분하지 않습니다.',sections:{},reasons:[],risks:[],notice:''}
 // Backend detail score is the single current score source.
 const a=rawAnalysis
 const status=d.data_status||{}
 const reports=d.reports||[]
 const disclosures=d.disclosures||[]
 const newsItems=d.news||[]
 const investorFlow=d.investor_flow||{}
 const flowSeries=Array.isArray(investorFlow.series)?investorFlow.series:[]
 const filteredReports=reportFilter==='all'?reports:reports.filter(x=>x.sentiment===reportFilter)
 const filteredNews=newsFilter==='all'?newsItems:newsItems.filter(x=>x.sentiment===newsFilter)
 const reportTotalPages=Math.max(1,Math.ceil(filteredReports.length/detailPageSize))
 const disclosureTotalPages=Math.max(1,Math.ceil(disclosures.length/detailPageSize))
 const newsTotalPages=Math.max(1,Math.ceil(filteredNews.length/detailPageSize))
 const safeReportPage=Math.min(reportPage,reportTotalPages)
 const safeDisclosurePage=Math.min(disclosurePage,disclosureTotalPages)
 const safeNewsPage=Math.min(newsPage,newsTotalPages)
 const visibleReports=filteredReports.slice((safeReportPage-1)*detailPageSize,safeReportPage*detailPageSize)
 const visibleDisclosures=disclosures.slice((safeDisclosurePage-1)*detailPageSize,safeDisclosurePage*detailPageSize)
 const visibleNews=filteredNews.slice((safeNewsPage-1)*detailPageSize,safeNewsPage*detailPageSize)

 return <div className="modal" onMouseDown={backdrop}>
   <div className="detail">
     <button className="close" onClick={onClose}><X/></button>

     <div className="detail-title">
       <div>
         <small>{s.code} / {s.market} / {s.sector}</small>
         <h2>{s.name}{Array.isArray(s.former_names)&&s.former_names.length>0&&<small className="stock-detail-former-name">구 {s.former_names[0]}</small>}</h2>
         <div className="big-price">
           {won(s.price)}원
           <span className={s.change_rate>=0?'up':'down'}>
             {pct(s.change_rate)}
           </span>
         </div>
       </div>

       <div className="detail-title-actions">
        <button type="button" className="detail-quick-buy" onClick={()=>onBuy?.(s)}>매수</button>
        <button type="button" className="detail-ai-start" disabled={aiLoading||!aiAllowed} onClick={openAiConsent}>
         {aiLoading?'AI 분석 중':aiAnalysis?.result?'다시 분석':'AI 분석 시작'}
        </button>
       </div>
     </div>


{aiConsentOpen&&createPortal(
 <div className="ai-consent-backdrop" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)setAiConsentOpen(false)}}>
  <div className="ai-consent-modal" role="dialog" aria-modal="true" aria-labelledby="ai-consent-title">
   <button type="button" className="ai-consent-close" onClick={()=>setAiConsentOpen(false)} aria-label="AI 분석 안내 닫기"><X size={18}/></button>
   <div className="ai-consent-head">
    <small>STOCKLOG AI ANALYSIS</small>
    <h3 id="ai-consent-title">{aiAnalysisLabel}을 시작할까요?</h3>
    <p>Gbot이 재무·가격·수급·뉴스 등 핵심 투자 데이터를 종합해 의견과 근거를 정리합니다.</p>
   </div>
   <div className="ai-consent-membership">
    <div><small>현재 등급</small><b>{membershipLabel}</b></div>
    <div><small>오늘 이용 가능</small><b>{aiUsageLoading?'확인 중':aiUsageInfo?.unlimited?'무제한':aiUsageInfo?`${Number(aiUsageInfo.remaining||0)}회 남음`:`하루 ${Number(aiLimit??5)}회`}</b></div>
   </div>
   <div className="ai-consent-scope">
    <article><b>Gbot 종합 분석</b><span>핵심 투자 정보를 바탕으로 매수·관망·매도 의견과 근거를 정리합니다.</span></article>
    <article><b>회사 실적과 가격</b><span>재무 흐름과 PER·PBR 등 현재 가격 부담을 실제 수치로 비교합니다.</span></article>
    <article><b>수급·추세·공개 정보</b><span>외국인·기관 수급, 주가 흐름, 뉴스·리포트·공시를 함께 확인합니다.</span></article>
    <article><b>핵심 위험 확인</b><span>판단에 영향을 줄 수 있는 변동성·공시·뉴스 위험을 함께 보여드립니다.</span></article>
   </div>
   <div className="ai-consent-time"><Clock3 size={16}/><span>분석 시간은 Gbot 응답 속도와 데이터 양에 따라 달라질 수 있습니다.</span></div>
   {!aiAllowed&&<div className="ai-consent-disabled">현재 등급에서는 AI 분석 기능을 사용할 수 없습니다.</div>}
   <div className="ai-consent-actions">
    <button type="button" className="secondary" onClick={()=>setAiConsentOpen(false)}>비동의 · 취소</button>
    <button type="button" className="primary" disabled={!aiAllowed||aiUsageLoading||(!aiUsageInfo?.unlimited&&aiUsageInfo&&Number(aiUsageInfo.remaining||0)<=0)} onClick={acceptAiAnalysis}>동의하고 분석 시작</button>
   </div>
  </div>
 </div>,document.body
)}

{aiLoading&&<section className="ai-analysis-result-section ai-analysis-loading-section">
 <div className="stock-detail-loader-card ai-detail-loader-card" role="status" aria-live="polite">
  <div className="stock-detail-loader-mark"><div className="sync-spinner"/><Sparkles size={19}/></div>
  <small>STOCKLOG GBOT ANALYSIS</small>
  <h3>{aiAnalysisLabel}을 진행하고 있어요</h3>
  <p>Gbot이 최신 투자 데이터를 종합해 이해하기 쉬운 의견과 근거를 정리하고 있습니다.</p>
  <div className="ai-live-progress" aria-live="polite">
   <div className="ai-live-progress-main"><span className="ai-live-pulse"/><b>{publicUiText(aiProgress?.message)||'Gbot이 투자 데이터를 분석하고 있습니다.'}</b></div>
   <div className="ai-live-progress-meta">
    <span>전체 경과 <strong>{formatAiElapsed(aiElapsed)}</strong></span>
    <span>화면을 닫아도 분석은 계속됩니다.</span>
   </div>
  </div>
 </div>
</section>}

{aiError&&!aiLoading&&<section className="ai-analysis-result-section"><div className="ai-analyst-error"><b>AI 분석을 완료하지 못했습니다.</b><span>{aiError}</span></div></section>}

{aiAnalysis?.result&&!aiLoading&&(()=>{
 const ai=aiAnalysis.result
 const providerLabel='StockLog Gbot 분석'
 return <section className="ai-analysis-result-section">
  <div className="section-title-row"><div><h3>최근 {aiAnalysisLabel}</h3>{aiAnalysis.generated_at&&<small className="ai-analysis-generated-at">분석 시각 {new Date(aiAnalysis.generated_at).toLocaleString('ko-KR')}</small>}{aiAnalysis.refresh_error&&<small className="ai-analysis-refresh-note">최근 재분석은 완료되지 않아 마지막 완료 결과를 보여드리고 있습니다.</small>}</div><button type="button" className="secondary ai-reanalyze" onClick={openAiConsent}>다시 분석</button></div>
  <div className="ai-investment-decision">
   <div className={`ai-main-view ${aiViewClass(ai.view)}`}><small>최종 의견</small><b>{AI_VERDICT_LABEL[ai.verdict]||AI_VIEW_LABEL[ai.view]||'관망'}</b></div>
   <div className="ai-decision-copy"><h4>{publicUiText(ai.headline||ai.one_line)}</h4><AiReadableText className="ai-premium-summary-copy">{ai.executive_summary||ai.company_view}</AiReadableText><span>{aiAnalysis.cached?'최근 분석 / ':'방금 분석 / '}{providerLabel}</span></div>
  </div>
  {ai.decision_balance&&<div className="ai-decision-balance" aria-label="프리미엄 AI 판단 근거 균형">
   <div><small>판단 근거</small><b>{AI_VERDICT_LABEL[ai.verdict]||AI_VIEW_LABEL[ai.view]||'관망'}</b></div>
   <span className="positive"><em>{Number(ai.decision_balance.positive||0)}</em> 긍정</span>
   <span className="negative"><em>{Number(ai.decision_balance.negative||0)}</em> 주의</span>
   <span className="neutral"><em>{Number(ai.decision_balance.neutral||0)}</em> 중립</span>
   <p>최종 의견과 오른쪽 요약, 아래 근거는 모두 같은 최종 판정을 기준으로 표시됩니다.</p>
  </div>}
  {Array.isArray(ai.quantitative_breakdown)&&ai.quantitative_breakdown.length>0&&<div className="ai-quant-breakdown">
   {ai.quantitative_breakdown.map((item,i)=><article key={`${item.key||item.label}-${i}`} className={item.view||'neutral'}>
    <div><small>{item.label}</small><b>{publicUiText(item.current||'-')}</b></div>
    <span>{publicUiText(item.benchmark||'')}</span>
    <p>{publicUiText(item.interpretation||'')}</p>
   </article>)}
  </div>}
  <div className="ai-verdict-ladder" aria-label="AI 투자 의견 위치">
   {[
    ['buy_bias','매수 추천','현재 데이터가 비교적 우호적인 구간입니다.'],
    ['wait','관망','좋은 점과 위험이 섞여 있어 추가 확인이 필요한 구간입니다.'],
    ['sell_bias','매도 추천','위험 요인이 더 크게 보이는 구간입니다.']
   ].map(([key,label,desc])=><div className={`ai-verdict-step ${ai.verdict===key?'active':''}`} key={key}><span>{ai.verdict===key?'→':''}</span><div><b>{label}</b><small>{desc}</small></div></div>)}
  </div>
  <div className="ai-action-summary-grid">
   <article><small>새로 매수하려는 경우</small><p>{publicUiText(ai.new_investor_strategy||ai.entry_timing||'가격과 거래 흐름을 더 확인한 뒤 접근을 검토합니다.')}</p></article>
   <article><small>이미 보유 중인 경우</small><p>{publicUiText(ai.holder_strategy||'실적과 수급 흐름이 유지되는지 확인하면서 기존 판단을 점검합니다.')}</p></article>
  </div>
  <div className="ai-entry-timing"><div><small>진입 · 매수 타이밍</small><h4>{publicUiText(ai.entry_timing||'가격과 거래 흐름을 더 확인한 뒤 접근을 검토합니다.')}</h4></div><p>{publicUiText(ai.buy_plan||'작은 비중으로 시작하고 실적·수급·가격 조건이 확인될 때 추가 접근을 검토합니다.')}</p></div>
  <div className="ai-factor-grid">
   <div className="ai-factor-box positive"><h4>긍정적으로 보는 이유</h4>{(ai.positive_factors||[]).map((item,i)=><p key={`aipos-${i}`}><b>{i+1}.</b> <HighlightFinancialMetrics sentiment="positive">{item}</HighlightFinancialMetrics></p>)}</div>
   <div className="ai-factor-box negative"><h4>부정 · 주의해서 보는 이유</h4>{(ai.risk_factors||[]).map((item,i)=><p key={`airisk-${i}`}><b>{i+1}.</b> <HighlightFinancialMetrics sentiment="negative">{item}</HighlightFinancialMetrics></p>)}</div>
  </div>
  {(ai.watch_conditions||[]).length>0&&<div className="ai-watch-conditions"><b>이 조건이 바뀌면 판단도 다시 봅니다</b><div>{ai.watch_conditions.map((item,i)=><span key={`watch-${i}`}>{i+1}. {publicMultiline(item)}</span>)}</div></div>}
 </section>
})()}

     <section className="valuation-summary">
       <div className="section-title-row">
         <div>
           <h3 className="explainable-heading">회사 투자지표 분석<MetricInfo metric="밸류에이션"/></h3>
         </div>
       </div>

       <DetailFold
        label="투자지표 보기"
        meta=""
        open
        className="reference-detail-fold"
       >
       <div className="valuation-grid">
         {[
           ['PER',metricValue(s.per,'배')],
           ['PBR',metricValue(s.pbr,'배')],
           ['EPS',s.eps==null?'-':`${Math.round(Number(s.eps)).toLocaleString()}원`],
           ['BPS',s.bps==null?'-':`${Math.round(Number(s.bps)).toLocaleString()}원`],
           ['ROE',metricValue(s.roe,'%')],
           ['배당수익률',metricValue(s.dividend_yield,'%')],
           ['매출 성장률',metricValue(s.revenue_growth,'%')],
           ['영업이익률',metricValue(s.operating_margin,'%')]
         ].map(([label,value])=>
           <div key={label}>
             <small className="metric-label">{label}<MetricInfo metric={label}/></small>
             <b>{value??'-'}</b>
           </div>
         )}
       </div>
       </DetailFold>
     </section>

     <section className="verdict-section beginner-check-section">
       <div className="verdict-head"><div><h3>체크 포인트</h3></div></div>
       <div className="beginner-check-grid">
        <article><small>수익성</small><b>{Number(s.roe||0)>=12?'좋은 편':'확인 필요'}</b><span>ROE {metricValue(s.roe,'%')} · 영업이익률 {metricValue(s.operating_margin,'%')}</span></article>
        <article><small>가격 부담</small><b>{Number(s.per||0)>0&&Number(s.per)<=18?'낮은 편':'비교 필요'}</b><span>PER {metricValue(s.per,'배')} · PBR {metricValue(s.pbr,'배')}</span></article>
        <article><small>최근 주가</small><b>{Number(s.momentum_20d||0)>=5?'상승 흐름':Number(s.momentum_20d||0)<=-5?'약한 흐름':'중립'}</b><span>20일 {metricValue(s.momentum_20d,'%')}</span></article>
        <article><small>주의 신호</small><b>{(a.risks||[])[0]?'확인 필요':'뚜렷한 경고 적음'}</b><span>{publicUiText((a.risks||[])[0]||'현재 뚜렷한 경고 신호가 적습니다.')}</span></article>
       </div>
     </section>

     <section className="financial-detail-section">
       <div className="section-title-row">
         <div>
           <h3 className="explainable-heading">사업성과 / 분기별 재무제표<MetricInfo metric="분기별 재무제표"/></h3>
         </div>
       </div>

       <DetailFold
        label="분기별 재무 데이터 보기"
        meta=""
        className="reference-detail-fold"
       >
{d.financials?.length
  ? <FinancialTable data={d.financials}/>
  : <div className="empty data-empty-guide">
      {status.financials?.message||'실제 재무데이터가 아직 없습니다.'}
    </div>
}
       </DetailFold>
     </section>

<section className="disclosure-section">
  <div className="section-title-row">
    <div>
      <h3>최근 공식 공시</h3>
    </div>
    
  </div>
  <DetailFold
   label="공시 목록 보기"
   meta=""
   className="reference-detail-fold"
  >
  {d._meta?.disclosures?.warning&&<div className="real-data-warning">{publicUiText(d._meta.disclosures.warning)}</div>}
  <div className="disclosure-list">
    {disclosures.length?visibleDisclosures.map((item,i)=><a className="disclosure-card" href={item.link} target="_blank" rel="noopener noreferrer" key={`${item.receipt_no}-${i}`}>
      <div className="disclosure-card-top">
        <span className={Number(item.importance_score)>=90?'disclosure-impact high':'disclosure-impact'}>중요도 {Math.round(Number(item.importance_score||0))}</span>
        <small>{item.receipt_date||'-'} / {item.filer_name||s.name}</small>
        <ExternalLink size={16}/>
      </div>
      <b>{item.report_name}</b>
    </a>):<div className="empty">{status.disclosures?.message||'최근 공식 공시가 없습니다.'}</div>}
  </div>
  {disclosures.length>detailPageSize&&<div className="stocklog-pagination compact">
    <button type="button" onClick={()=>setDisclosurePage(1)} disabled={safeDisclosurePage===1}>처음</button>
    <button type="button" onClick={()=>setDisclosurePage(p=>Math.max(1,p-1))} disabled={safeDisclosurePage===1}>이전</button>
    <strong>{safeDisclosurePage} / {disclosureTotalPages}</strong>
    <button type="button" onClick={()=>setDisclosurePage(p=>Math.min(disclosureTotalPages,p+1))} disabled={safeDisclosurePage===disclosureTotalPages}>다음</button>
    <button type="button" onClick={()=>setDisclosurePage(disclosureTotalPages)} disabled={safeDisclosurePage===disclosureTotalPages}>끝</button>
  </div>}
  </DetailFold>
</section>

<section className="broker-report-section">
  <div className="section-title-row"><div><h3 className="explainable-heading">리포트 분석<MetricInfo metric="증권사 리포트"/></h3></div></div>
  <DetailFold
   label="리포트 보기"
   meta=""
   className="reference-detail-fold"
  >
  {(d.reports?.length||0)>0&&<div className={`report-sentiment-overview ${d.report_summary?.overall||'neutral'}`}><div className="report-sentiment-main"><small>리포트 분위기</small><b>{sentimentName[d.report_summary?.overall]||'관망'}</b></div><div><small>긍정</small><b>{d.report_summary?.positive??0}</b></div><div><small>관망</small><b>{d.report_summary?.neutral??0}</b></div><div><small>부정</small><b>{d.report_summary?.negative??0}</b></div></div>}
  <div className="sentiment-filter-tabs"><button className={reportFilter==='all'?'active':''} onClick={()=>{setReportFilter('all');setReportPage(1)}}>전체</button><button className={reportFilter==='positive'?'active positive':''} onClick={()=>{setReportFilter('positive');setReportPage(1)}}>긍정</button><button className={reportFilter==='negative'?'active negative':''} onClick={()=>{setReportFilter('negative');setReportPage(1)}}>부정</button></div>
  <div className="report-card-list">{filteredReports.length?visibleReports.map((r,i)=>{const sentiment=r.sentiment||'neutral';return <a className={`report-analysis-card ${sentiment}`} href={r.link} target="_blank" rel="noopener noreferrer" key={`${r.title}-${i}`}><div className="report-card-top"><span className={`sent ${sentiment}`}>{sentimentName[sentiment]||'관망'}</span><div><small>{r.date||'-'} / {r.broker||'-'}</small><b>{r.title}</b></div><ExternalLink size={15}/></div><p><HighlightFinancialMetrics sentiment={sentiment}>{publicUiText(r.brief_summary)||'공개된 리포트 내용에서 요약할 문장을 충분히 찾지 못했습니다.'}</HighlightFinancialMetrics></p><div className="report-card-meta">{r.investment_opinion&&<span>투자의견 {publicUiText(r.investment_opinion)}</span>}{r.target_price&&<span>목표주가 <strong className={`sentiment-number sentiment-${sentiment}`}>{won(r.target_price)}원</strong></span>}</div></a>}):<div className="empty">{status.reports?.message||'리포트가 없습니다.'}</div>}</div>
  {filteredReports.length>detailPageSize&&<div className="stocklog-pagination compact">
    <button type="button" onClick={()=>setReportPage(1)} disabled={safeReportPage===1}>처음</button>
    <button type="button" onClick={()=>setReportPage(p=>Math.max(1,p-1))} disabled={safeReportPage===1}>이전</button>
    <strong>{safeReportPage} / {reportTotalPages}</strong>
    <button type="button" onClick={()=>setReportPage(p=>Math.min(reportTotalPages,p+1))} disabled={safeReportPage===reportTotalPages}>다음</button>
    <button type="button" onClick={()=>setReportPage(reportTotalPages)} disabled={safeReportPage===reportTotalPages}>끝</button>
  </div>}
  </DetailFold>
</section>

     <section className="stock-news-section">
       <div className="section-title-row news-section-head">
         <div>
           <h3 className="explainable-heading">뉴스 분석<MetricInfo metric="뉴스 심리"/></h3>
         </div>

         <button
           className="secondary news-refresh"
           onClick={refreshNews}
           disabled={refreshingNews}
         >
           {refreshingNews?'최신 정보 갱신 중...':'뉴스/리포트 갱신'}
         </button>
       </div>

       <DetailFold
        label="뉴스 보기"
        meta=""
        className="reference-detail-fold"
       >
       {d._meta?.news?.warning&&
         <div className="real-data-warning">
           {publicUiText(d._meta.news.warning)}
         </div>
       }

       <div className={
         `news-sentiment-overview ${
           d.news_summary?.overall||'neutral'
         }`
       }>
         <div className="news-sentiment-main">
           <small>뉴스 분위기</small>
           <b>
             {sentimentName[d.news_summary?.overall]||'관망'}
           </b>
         </div>

         <div className="news-count positive">
           <small>긍정</small>
           <b>{d.news_summary?.positive??0}</b>
         </div>
         <div className="news-count neutral">
           <small>관망</small>
           <b>{d.news_summary?.neutral??0}</b>
         </div>
         <div className="news-count negative">
           <small>부정</small>
           <b>{d.news_summary?.negative??0}</b>
         </div>
       </div>
<div className="sentiment-filter-tabs"><button className={newsFilter==='all'?'active':''} onClick={()=>{setNewsFilter('all');setNewsPage(1)}}>전체</button><button className={newsFilter==='positive'?'active positive':''} onClick={()=>{setNewsFilter('positive');setNewsPage(1)}}>긍정</button><button className={newsFilter==='negative'?'active negative':''} onClick={()=>{setNewsFilter('negative');setNewsPage(1)}}>부정</button></div>
       <div className="news-list rich-news-list">
         {filteredNews.length
           ? visibleNews.map((n,i)=>
             <a
               href={n.link}
               target="_blank"
               rel="noopener noreferrer"
               className={`news rich-news ${n.sentiment}`}
               key={`${n.link}-${i}`}
             >
               <div className="news-sentiment-col">
                 <span className={`sent ${n.sentiment}`}>
                   {sentimentName[n.sentiment]}
                 </span>
               </div>

               <div className="news-copy">
                 <div className="news-meta">
                   <span>{n.publisher||'언론사'}</span>
                   <span>{n.published_at||'-'}</span>
                 </div>
                 <b>{n.title}</b>
                 <div className="news-brief-analysis"><b>내용 요약</b><span><HighlightFinancialMetrics sentiment={n.sentiment||'neutral'}>{n.brief_summary||'뚜렷한 방향성 표현이 적습니다.'}</HighlightFinancialMetrics></span></div>
               </div>

               <ExternalLink size={15}/>
             </a>
           )
           : <div className="empty">
               뉴스가 없습니다.
             </div>
         }
       </div>
       {filteredNews.length>detailPageSize&&<div className="stocklog-pagination compact">
         <button type="button" onClick={()=>setNewsPage(1)} disabled={safeNewsPage===1}>처음</button>
         <button type="button" onClick={()=>setNewsPage(p=>Math.max(1,p-1))} disabled={safeNewsPage===1}>이전</button>
         <strong>{safeNewsPage} / {newsTotalPages}</strong>
         <button type="button" onClick={()=>setNewsPage(p=>Math.min(newsTotalPages,p+1))} disabled={safeNewsPage===newsTotalPages}>다음</button>
         <button type="button" onClick={()=>setNewsPage(newsTotalPages)} disabled={safeNewsPage===newsTotalPages}>끝</button>
       </div>}
       </DetailFold>
     </section>

     <section className="flow-detail-section">
       <div className="section-title-row">
         <div><h3 className="explainable-heading">수급 분석<MetricInfo metric="수급"/></h3></div>
       </div>
       <DetailFold label="수급 데이터 보기" meta="" className="reference-detail-fold">
        {investorFlow.available
         ? <>
           <div className="detail-flow-summary">
            {[
             ['외국인',investorFlow.foreign_net],
             ['기관',investorFlow.institution_net],
             ['개인',investorFlow.individual_net]
            ].map(([label,value])=><article key={label}>
              <small>{label} 최근 {Number(investorFlow.days||0)}거래일</small>
              <b className={Number(value||0)>=0?'up':'down'}>{flowQty(value)}</b>
              <span>{Number(value||0)>0?'순매수':Number(value||0)<0?'순매도':'변화 적음'}</span>
             </article>)}
            <article className="flow-insight-card"><small>현재 흐름</small><b>{investorFlow.insight||'수급 흐름 확인'}</b><span>{investorFlow.latest_date||'-'} 기준</span></article>
           </div>
           {flowSeries.length>0&&<div className="detail-flow-table">
            <div className="detail-flow-row head"><span>날짜</span><span>외국인</span><span>기관</span><span>개인</span></div>
            {flowSeries.slice(-7).reverse().map((row,i)=><div className="detail-flow-row" key={`${row.date}-${i}`}>
             <span>{String(row.date||'').slice(5).replace('-','.')||'-'}</span>
             <b className={Number(row.foreign||0)>=0?'up':'down'}>{flowQty(row.foreign)}</b>
             <b className={Number(row.institution||0)>=0?'up':'down'}>{flowQty(row.institution)}</b>
             <b className={Number(row.individual||0)>=0?'up':'down'}>{flowQty(row.individual)}</b>
            </div>)}
           </div>}
          </>
         : <div className="empty">{investorFlow.message||'수급 데이터가 아직 준비되지 않았습니다.'}</div>}
       </DetailFold>
     </section>

     <section className="chart-section chart-section-bottom">
       <div className="section-title-row">
         <div>
           <h3>차트 분석</h3>
         </div>
       </div>

       <DetailFold
        label="차트 보기"
        meta=""
        className="reference-detail-fold"
       >
       {d.chart?.length
         ? <><ChartSignalTable data={d.chart} stock={s} vix={vixContext}/><DetailedStockChart data={d.chart}/></>
         : <div className="empty data-empty-guide">
             {status.price?.message||'실제 일봉 데이터가 없습니다.'}
           </div>
       }
       </DetailFold>
     </section>

   </div>
 </div>
}

const INVESTMENT_TRAITS={
 L:{
  name:'장기투자형',
  short:'장기',
  english:'Long',
  summary:'시간과 복리, 기업의 장기 성장 스토리를 믿고 기다리는 편입니다.',
  strength:'시장 소음에 흔들리지 않고 좋은 기업의 성장을 오래 가져갈 수 있습니다.',
  caution:'투자 논리가 훼손됐는데도 단순히 오래 보유하는 실수를 경계해야 합니다.'
 },
 N:{
  name:'신중 관망형',
  short:'균형',
  english:'Neutral',
  summary:'기간을 미리 고정하기보다 상황과 투자 논리에 맞춰 유연하게 대응합니다.',
  strength:'장기와 단기의 장점을 섞어 시장 변화에 비교적 유연하게 대응합니다.',
  caution:'판단 기준이 모호하면 매도/보유 결정을 계속 미룰 수 있습니다.'
 },
 S:{
  name:'단기투자형',
  short:'단기',
  english:'Short',
  summary:'짧은 기간의 가격 변화와 타이밍을 적극적으로 활용하는 편입니다.',
  strength:'시장 변화에 빠르게 대응하고 기회비용을 민감하게 관리합니다.',
  caution:'잦은 매매와 단기 노이즈에 과도하게 반응하지 않도록 기준이 필요합니다.'
 },
 A:{
  name:'공격적 투자형',
  short:'공격',
  english:'Aggressive',
  summary:'수익 기회가 크다고 판단하면 변동성을 감수하고 적극적으로 투자합니다.',
  strength:'확신이 높은 기회에서 높은 수익 잠재력을 적극적으로 활용합니다.',
  caution:'손실 폭과 포지션 크기를 미리 정하지 않으면 낙폭도 커질 수 있습니다.'
 },
 D:{
  name:'방어적 투자형',
  short:'방어',
  english:'Defensive',
  summary:'수익률보다 먼저 손실 가능성과 자산 보전을 확인하는 편입니다.',
  strength:'하락장에서 계좌를 지키고 감정적인 큰 손실을 줄이는 데 유리합니다.',
  caution:'위험을 너무 피하면 좋은 상승 기회를 충분히 활용하지 못할 수 있습니다.'
 },
 G:{
  name:'미래가치형',
  short:'성장',
  english:'Growth',
  summary:'현재 숫자보다 앞으로 커질 시장과 기업의 성장 가능성을 중요하게 봅니다.',
  strength:'산업 구조 변화와 장기 성장 기업을 일찍 발견하는 데 강점이 있습니다.',
  caution:'좋은 미래 이야기만으로 지나치게 높은 가격을 정당화하지 않도록 주의해야 합니다.'
 },
 V:{
  name:'현실가치형',
  short:'가치',
  english:'Value',
  summary:'현재 실적과 자산, 밸류에이션처럼 확인 가능한 숫자를 더 중요하게 봅니다.',
  strength:'가격 대비 실제 가치와 안전마진을 꼼꼼하게 확인하는 데 강점이 있습니다.',
  caution:'싸다는 이유만으로 성장성이 약한 기업을 오래 보유하는 가치 함정을 조심해야 합니다.'
 },
 P:{
  name:'빠른수익실현형',
  short:'빠른실현',
  english:'Profit',
  summary:'목표 수익이 어느 정도 나면 확보한 이익을 빠르게 확정하는 편입니다.',
  strength:'수익을 실제 계좌 이익으로 확정하고 급격한 되돌림 위험을 줄입니다.',
  caution:'좋은 종목의 큰 추세가 시작됐는데 너무 빨리 내려 수익을 제한할 수 있습니다.'
 },
 H:{
  name:'큰수익추구형',
  short:'큰수익',
  english:'High Return',
  summary:'조금 오른 것보다 투자 논리가 유지되는 동안 큰 수익 구간을 기다리는 편입니다.',
  strength:'강한 추세와 장기 승자를 오래 보유해 큰 수익을 노릴 수 있습니다.',
  caution:'이미 큰 수익이 난 뒤에도 욕심 때문에 이익을 상당 부분 반납할 수 있습니다.'
 },
 F:{
  name:'집중투자형',
  short:'집중',
  english:'Focused',
  summary:'확신이 높은 소수 종목에 자금을 집중하는 편입니다.',
  strength:'분석이 맞았을 때 좋은 아이디어의 수익 기여도를 크게 만들 수 있습니다.',
  caution:'한 종목/한 산업의 예상치 못한 악재가 계좌 전체에 큰 영향을 줄 수 있습니다.'
 },
 M:{
  name:'분산투자형',
  short:'분산',
  english:'Multi',
  summary:'여러 종목과 업종으로 나눠 특정 종목의 위험을 줄이는 편입니다.',
  strength:'개별 종목 실수가 전체 계좌에 미치는 충격을 줄이는 데 유리합니다.',
  caution:'종목 수가 지나치게 많아지면 좋은 아이디어의 효과가 희석되고 관리가 어려워질 수 있습니다.'
 }
}

const INVESTMENT_AXES=[
 {
  key:'horizon',
  name:'투자 기간',
  letters:['L','N','S'],
  caption:'오래 보유 ↔ 상황 대응 ↔ 빠른 기회 포착'
 },
 {
  key:'risk',
  name:'위험 감수',
  letters:['A','D'],
  caption:'높은 변동 감수 ↔ 손실 방어 우선'
 },
 {
  key:'value',
  name:'가치 판단',
  letters:['G','V'],
  caption:'미래 성장성 ↔ 현재 가격과 가치'
 },
 {
  key:'profit',
  name:'수익 실현',
  letters:['P','H'],
  caption:'수익 확보 ↔ 상승 여력 추구'
 },
 {
  key:'spread',
  name:'종목 배분',
  letters:['F','M'],
  caption:'소수 종목 집중 ↔ 여러 종목 분산'
 }
]

const INVESTMENT_QUESTIONS=[
 {
  id:1, primaryAxis:'horizon',
  title:'산 회사의 매출과 이익은 예상대로 좋아지고 있지만 주가는 4개월째 거의 움직이지 않습니다. 가장 가까운 행동은?',
  options:[
   {id:'1a',label:'회사가 계속 좋아지고 있다면 주가는 늦게 오를 수도 있으니 계속 가지고 있는다.',scores:{L:3,H:1}},
   {id:'1b',label:'한두 달 더 지켜보면서 다른 좋은 회사와 비교해 투자금 일부를 옮길지 생각한다.',scores:{N:3,M:1}},
   {id:'1c',label:'주가가 너무 오래 움직이지 않으면 최근 흐름이 좋은 다른 회사로 투자금 일부를 옮긴다.',scores:{S:3,P:1}},
   {id:'1d',label:'회사의 매출과 이익, 현재 가격을 다시 보고 더 좋아 보이면 오히려 더 산다.',scores:{L:2,A:1,F:1}}
  ]
 },
 {
  id:2, primaryAxis:'risk',
  title:'관심 있는 주식이 하루에도 7~8%씩 크게 오르내리지만 앞으로 회사가 크게 성장할 가능성이 높아 보입니다. 어떻게 하시겠습니까?',
  options:[
   {id:'2a',label:'가격이 너무 크게 오르내리면 좋은 회사라도 투자하지 않는다.',scores:{D:3,V:1}},
   {id:'2b',label:'아주 적은 금액으로 먼저 사보고 가격 움직임이 안정되면 더 산다.',scores:{D:2,N:1,M:1}},
   {id:'2c',label:'충분히 알아본 뒤 괜찮다고 생각되면 다른 주식과 비슷한 금액을 투자한다.',scores:{A:2,G:1}},
   {id:'2d',label:'손실 가능성이 커도 크게 오를 가능성이 높다고 판단되면 적극적으로 투자한다.',scores:{A:3,G:1,F:1}}
  ]
 },
 {
  id:3, primaryAxis:'value',
  title:'두 기업 중 하나만 고른다면 어느 쪽에 더 관심이 갑니까?',
  options:[
   {id:'3a',label:'지금은 이익이 적지만 앞으로 이 회사가 속한 시장이 크게 커질 가능성이 높은 회사.',scores:{G:3,L:1,H:1}},
   {id:'3b',label:'빠르게 성장하지는 않지만 회사가 버는 돈과 가진 재산에 비해 주식 가격이 싸 보이는 회사.',scores:{V:3,D:1}},
   {id:'3c',label:'성장 가능성도 괜찮고 주식 가격도 크게 비싸 보이지 않는 안정적인 회사.',scores:{G:1,V:1,N:2,M:1}},
   {id:'3d',label:'최근 주가가 더 잘 오르고 사람들의 관심을 많이 받는 회사를 먼저 선택한다.',scores:{S:2,A:1,P:1}}
  ]
 },
 {
  id:4, primaryAxis:'profit',
  title:'산 주식이 예상보다 빠르게 18% 올랐습니다. 처음 이 회사를 산 이유는 아직 그대로입니다.',
  options:[
   {id:'4a',label:'수익을 지키기 위해 대부분 정리한다.',scores:{P:3,D:1,S:1}},
   {id:'4b',label:'절반 정도 팔아서 수익을 챙기고 나머지는 계속 가지고 있는다.',scores:{P:2,N:2,M:1}},
   {id:'4c',label:'처음 이 회사를 산 이유가 그대로라면 계속 가지고 있는다.',scores:{H:3,L:1}},
   {id:'4d',label:'회사가 더 좋아졌다고 생각되면 이미 올랐어도 조금 더 사는 것을 생각한다.',scores:{H:2,A:2,F:1}}
  ]
 },
 {
  id:5, primaryAxis:'spread',
  title:'투자할 수 있는 돈이 1,000만원이고 정말 좋아 보이는 주식 하나를 발견했습니다. 이 주식에 얼마 정도 투자하시겠습니까?',
  options:[
   {id:'5a',label:'100만원 정도만 사고 나머지 돈은 여러 주식에 나눠 투자한다.',scores:{M:3,D:1}},
   {id:'5b',label:'200~250만원 정도 투자하고 나머지는 다른 주식에도 나눠 넣는다.',scores:{M:2,N:2}},
   {id:'5c',label:'좋다고 생각하면 350~400만원 정도까지 투자할 수 있다.',scores:{F:2,A:1}},
   {id:'5d',label:'정말 자신 있다면 500만원 이상도 한 주식에 투자할 수 있다.',scores:{F:3,A:2,H:1}}
  ]
 },
 {
  id:6, primaryAxis:'horizon',
  title:'새로운 투자 아이디어를 찾을 때 가장 먼저 확인하고 싶은 것은?',
  options:[
   {id:'6a',label:'3~5년 뒤에도 이 회사가 계속 돈을 잘 벌 수 있을지.',scores:{L:3,G:1}},
   {id:'6b',label:'앞으로 몇 달 동안 매출과 이익이 좋아질지, 지금 가격이 너무 비싸지는 않은지.',scores:{N:3,V:1}},
   {id:'6c',label:'최근 사람들이 많이 사고 있는지, 곧 주가가 오를 만한 좋은 소식이 있는지.',scores:{S:3,A:1}},
   {id:'6d',label:'오랫동안 성장할 회사인지도 보고, 지금 사기 좋은 가격인지도 함께 본다.',scores:{L:1,N:2,G:1}}
  ]
 },
 {
  id:7, primaryAxis:'risk',
  title:'좋다고 생각해 산 주식이 12% 떨어졌지만 회사의 매출과 이익은 아직 나빠지지 않았습니다.',
  options:[
   {id:'7a',label:'더 떨어질까 걱정되어 일부 또는 전부 판다.',scores:{D:3,P:1}},
   {id:'7b',label:'당장은 사고팔지 않고 왜 떨어졌는지 더 알아본다.',scores:{D:1,N:2}},
   {id:'7c',label:'처음 좋게 본 이유가 그대로라면 지금 가격에서 조금 더 산다.',scores:{A:2,L:1}},
   {id:'7d',label:'회사의 상태가 그대로 좋다면 싸게 살 기회라고 보고 적극적으로 더 산다.',scores:{A:3,V:1,F:1}}
  ]
 },
 {
  id:8, primaryAxis:'value',
  title:'비슷한 회사들보다 주식 가격이 비싼 편이지만 매출이 매년 30%씩 빠르게 늘고 있는 회사입니다.',
  options:[
   {id:'8a',label:'회사가 잘 성장해도 지금 가격은 너무 비싸 보이므로 기다린다.',scores:{V:3,D:1}},
   {id:'8b',label:'가격이 조금 내려오면 살 수 있도록 계속 지켜본다.',scores:{V:2,N:1}},
   {id:'8c',label:'앞으로도 오랫동안 빠르게 성장할 이유가 충분하다면 지금 가격에도 살 수 있다.',scores:{G:3,L:1}},
   {id:'8d',label:'회사도 빠르게 성장하고 최근 주가도 계속 오르는 흐름이라면 적극적으로 산다.',scores:{G:2,A:2,S:1}}
  ]
 },
 {
  id:9, primaryAxis:'profit',
  title:'수익 중인 주식이 최근 가장 높았던 가격에서 6% 내려왔지만 전체적으로는 아직 오르는 흐름입니다.',
  options:[
   {id:'9a',label:'수익이 더 줄기 전에 정리한다.',scores:{P:3,D:1}},
   {id:'9b',label:'일부만 팔아 수익을 확보한다.',scores:{P:2,M:1,N:1}},
   {id:'9c',label:'주가가 계속 오르는 흐름이 확실히 끝날 때까지 가지고 있는다.',scores:{H:3,S:1}},
   {id:'9d',label:'회사가 얼마나 좋은지가 더 중요하므로 최근에 조금 떨어진 것은 크게 신경 쓰지 않는다.',scores:{H:2,L:2}}
  ]
 },
 {
  id:10, primaryAxis:'spread',
  title:'같은 업종에서 앞으로 잘될 것 같은 회사가 4개 보입니다. 가장 자연스러운 선택은?',
  options:[
   {id:'10a',label:'가장 좋은 한 기업만 깊게 분석해 투자한다.',scores:{F:3}},
   {id:'10b',label:'상위 두 기업에 대부분을 나눠 투자한다.',scores:{F:2,M:1}},
   {id:'10c',label:'3~4개 회사에 비슷한 금액을 나눠 투자한다.',scores:{M:3}},
   {id:'10d',label:'이 업종뿐 아니라 다른 업종의 주식도 함께 사서 위험을 더 나눈다.',scores:{M:3,D:1}}
  ]
 },
 {
  id:11, primaryAxis:'risk',
  title:'회사가 곧 매출과 이익을 발표할 예정이고, 현재 이 주식에서 5% 수익이 나고 있습니다.',
  options:[
   {id:'11a',label:'발표 결과가 나쁠 수도 있으니 발표 전에 대부분 판다.',scores:{D:3,P:2}},
   {id:'11b',label:'일부만 팔아 발표 결과가 나쁠 때 손실을 줄인다.',scores:{D:2,M:1}},
   {id:'11c',label:'회사가 잘하고 있다고 생각하면 팔지 않고 발표 결과를 확인한다.',scores:{A:2,H:1}},
   {id:'11d',label:'매출과 이익이 크게 좋아질 것이라고 확신하면 발표 전에 더 살 수도 있다.',scores:{A:3,F:1}}
  ]
 },
 {
  id:12, primaryAxis:'horizon',
  title:'종목을 매수한 뒤 어떤 주기로 확인하는 편이 가장 마음에 가깝습니까?',
  options:[
   {id:'12a',label:'회사의 매출과 이익 발표나 큰 변화가 있을 때 주로 확인한다.',scores:{L:3}},
   {id:'12b',label:'일주일에 한두 번 정도 주가와 중요한 뉴스를 확인한다.',scores:{N:3}},
   {id:'12c',label:'거의 매일 주가가 얼마나 움직였고 사람들이 얼마나 사고팔았는지 확인한다.',scores:{S:2,P:1}},
   {id:'12d',label:'주식시장이 열려 있는 동안에도 여러 번 가격을 확인한다.',scores:{S:3,A:1}}
  ]
 },
 {
  id:13, primaryAxis:'value',
  title:'최근 1년간 주가는 거의 오르지 않았지만 회사가 꾸준히 돈을 벌고 있고 주주에게 나눠주는 돈도 늘고 있는 회사입니다.',
  options:[
   {id:'13a',label:'빠르게 성장하지 않아도 주식 가격이 충분히 싸다면 좋은 투자 후보라고 본다.',scores:{V:3,D:1,L:1}},
   {id:'13b',label:'내가 가진 주식들 중 안정적인 한 종목으로는 괜찮다고 본다.',scores:{V:2,M:1}},
   {id:'13c',label:'성장성이 부족하다면 큰 매력은 느끼지 못한다.',scores:{G:2,A:1}},
   {id:'13d',label:'최근 주가가 거의 오르지 않는다면 다른 주식을 먼저 찾는다.',scores:{S:2,P:1}}
  ]
 },
 {
  id:14, primaryAxis:'profit',
  title:'매수할 때 목표 수익률을 정하는 방식은?',
  options:[
   {id:'14a',label:'10~15%처럼 명확한 숫자를 정하고 도달하면 정리한다.',scores:{P:3,S:1}},
   {id:'14b',label:'목표로 생각한 수익 범위는 있지만 상황에 따라 파는 시점을 바꾼다.',scores:{P:2,N:2}},
   {id:'14c',label:'정해진 수익률보다 주가가 더 이상 오르지 않는 흐름으로 바뀌는지를 본다.',scores:{H:2,S:1}},
   {id:'14d',label:'회사의 장기적인 성장 가능성이 나빠질 때까지 특별히 얼마에 팔겠다는 가격을 정하지 않는다.',scores:{H:3,L:2}}
  ]
 },
 {
  id:15, primaryAxis:'spread',
  title:'한 주식이 많이 올라 내가 투자한 전체 돈의 40%를 차지하게 됐습니다. 회사의 전망은 여전히 좋습니다.',
  options:[
   {id:'15a',label:'한 주식에 너무 많은 돈이 몰렸으므로 일부 팔아 원래 생각했던 투자금 수준으로 줄인다.',scores:{M:3,D:1,P:1}},
   {id:'15b',label:'조금만 팔아 위험을 낮추되 여전히 가장 많이 투자한 주식으로 유지한다.',scores:{M:2,F:1}},
   {id:'15c',label:'가장 자신 있는 주식이라면 전체 투자금의 40%가 되어도 괜찮다.',scores:{F:3,H:1}},
   {id:'15d',label:'회사가 더 좋아졌다고 생각한다면 한 주식에 많은 돈이 들어가 있는 것 자체는 문제라고 생각하지 않는다.',scores:{F:3,A:1}}
  ]
 },
 {
  id:16, primaryAxis:'horizon',
  title:'산 주식이 예상했던 좋은 소식 때문에 일주일 만에 크게 올랐습니다. 이후에는 어떻게 하시겠습니까?',
  options:[
   {id:'16a',label:'기대했던 좋은 소식이 이미 주가에 반영됐다고 보고 빠르게 팔아 수익을 챙긴다.',scores:{S:3,P:2}},
   {id:'16b',label:'일부만 팔아 수익을 챙기고 나머지는 주가 움직임을 더 지켜본다.',scores:{N:2,P:1}},
   {id:'16c',label:'며칠 사이 크게 오른 것보다 앞으로 회사의 매출과 이익이 더 좋아질지를 보고 결정한다.',scores:{N:2,L:1}},
   {id:'16d',label:'오랫동안 성장할 회사라는 생각이 그대로라면 갑자기 많이 올라도 계속 가지고 있는다.',scores:{L:3,H:1}}
  ]
 },
 {
  id:17, primaryAxis:'risk',
  title:'투자할 수 있는 돈 중 35%를 아직 현금으로 가지고 있는데 주식시장이 계속 크게 오르고 있습니다.',
  options:[
   {id:'17a',label:'이미 많이 오른 주식을 따라 사지 않고 현금을 가지고 가격이 내려오기를 기다린다.',scores:{D:3,V:1}},
   {id:'17b',label:'좋아 보이는 주식만 조금씩 사면서 현금을 천천히 투자한다.',scores:{D:1,N:2}},
   {id:'17c',label:'주식시장이 계속 오르는 흐름이라고 생각되면 현금으로 남겨둔 돈을 적극적으로 투자한다.',scores:{A:2,S:1}},
   {id:'17d',label:'더 오를 기회를 놓치는 것이 더 아쉬워 남은 현금 대부분을 투자할 수 있다.',scores:{A:3,F:1}}
  ]
 },
 {
  id:18, primaryAxis:'value',
  title:'어떤 회사를 살지 알아볼 때 가장 먼저 궁금한 것은 무엇입니까?',
  options:[
   {id:'18a',label:'회사의 매출이 얼마나 빠르게 늘고 있는지, 앞으로 시장이 얼마나 커질지, 새로운 사업이 있는지.',scores:{G:3}},
   {id:'18b',label:'회사가 버는 돈과 가진 재산에 비해 지금 주식 가격이 싼지 비싼지.',scores:{V:3}},
   {id:'18c',label:'회사가 가진 돈을 잘 활용해 꾸준히 이익을 내고 있는지.',scores:{G:1,V:1,L:1}},
   {id:'18d',label:'최근 주가가 얼마나 올랐는지, 사람들이 많이 사고 있는지, 주가 움직임이 어떤지.',scores:{S:3,A:1}}
  ]
 },
 {
  id:19, primaryAxis:'profit',
  title:'산 주식이 하루 만에 12% 크게 올라 예상보다 큰 수익이 생겼습니다.',
  options:[
   {id:'19a',label:'갑작스러운 수익은 바로 대부분 확정한다.',scores:{P:3,D:1}},
   {id:'19b',label:'일부를 팔아 처음 투자한 돈의 일부를 돌려받고 나머지는 계속 가지고 있는다.',scores:{P:2,M:1}},
   {id:'19c',label:'사려는 사람이 많고 계속 오르는 흐름이면 더 오를 수 있다고 기대한다.',scores:{H:2,S:2,A:1}},
   {id:'19d',label:'하루 동안 크게 오른 것보다 처음에 이 회사를 오래 가지고 있으려 했던 이유를 더 중요하게 본다.',scores:{H:3,L:2}}
  ]
 },
 {
  id:20, primaryAxis:'spread',
  title:'새로 좋아 보이는 주식을 발견했지만 이미 8개의 주식을 가지고 있습니다.',
  options:[
   {id:'20a',label:'기존 주식 중 덜 좋아 보이는 것을 팔고 새 주식에 더 많이 투자한다.',scores:{F:3}},
   {id:'20b',label:'기존 주식에 들어간 돈을 조금씩 줄여 새 주식에도 충분한 금액을 투자한다.',scores:{F:1,M:2}},
   {id:'20c',label:'새 주식에는 적은 금액만 투자해 여러 주식으로 나눠 가진 상태를 유지한다.',scores:{M:3}},
   {id:'20d',label:'이미 가진 주식이 많으므로 새 주식은 사지 않는다.',scores:{M:2,D:1}}
  ]
 },
 {
  id:21, primaryAxis:'risk',
  title:'아직 회사가 이익을 내지는 못하고 있지만 기술력이 좋고 많은 사람들이 관심을 갖는 회사입니다.',
  options:[
   {id:'21a',label:'회사가 실제로 돈을 벌기 시작하기 전에는 투자하지 않는다.',scores:{D:3,V:2}},
   {id:'21b',label:'회사를 지켜본다는 생각으로 아주 적은 금액만 투자할 수 있다.',scores:{D:1,G:1,M:1}},
   {id:'21c',label:'앞으로 크게 성장할 가능성이 충분하다면 다른 주식과 비슷한 금액을 투자한다.',scores:{A:2,G:2}},
   {id:'21d',label:'성공했을 때 크게 오를 수 있다면 손실 위험이 높아도 투자할 수 있다.',scores:{A:3,G:2,H:1}}
  ]
 },
 {
  id:22, primaryAxis:'horizon',
  title:'내가 주식을 잘 선택했는지 판단하려면 어느 정도 기간을 보는 것이 가장 자연스럽습니까?',
  options:[
   {id:'22a',label:'최소 1~3년은 지나야 제대로 평가할 수 있다.',scores:{L:3}},
   {id:'22b',label:'6개월~1년 정도면 내가 고른 주식이 괜찮았는지 판단할 수 있다.',scores:{N:3}},
   {id:'22c',label:'한두 달 안에도 생각과 다르게 움직이면 다른 주식으로 바꿀 수 있다.',scores:{S:2,N:1}},
   {id:'22d',label:'며칠~몇 주 안에 기대했던 움직임이 나오지 않으면 다른 주식을 찾는다.',scores:{S:3}}
  ]
 },
 {
  id:23, primaryAxis:'value',
  title:'주가가 이미 많이 올랐지만 앞으로 회사의 매출과 이익도 계속 좋아질 것으로 예상되는 회사를 발견했습니다.',
  options:[
   {id:'23a',label:'이미 너무 많이 오른 것 같아 지금은 사지 않고 기다린다.',scores:{V:3,D:1}},
   {id:'23b',label:'가격이 조금 내려올 때까지 사지 않고 계속 지켜본다.',scores:{V:2,N:1}},
   {id:'23c',label:'주가가 오른 것보다 회사가 더 빠르게 좋아지고 있다면 지금도 살 수 있다.',scores:{G:3}},
   {id:'23d',label:'회사의 매출과 이익도 좋아지고 주가도 계속 오르고 있다면 적극적으로 살 수 있다.',scores:{G:2,S:2,A:1}}
  ]
 },
 {
  id:24, primaryAxis:'profit',
  title:'한 주식에서 이미 40% 수익이 났는데, 처음 기대했던 회사의 좋은 변화가 이제 막 실제로 나타나기 시작했습니다.',
  options:[
   {id:'24a',label:'40%면 충분한 수익이므로 대부분 정리한다.',scores:{P:3,D:1}},
   {id:'24b',label:'절반 정도만 수익을 확정한다.',scores:{P:2,M:1}},
   {id:'24c',label:'회사가 이제 본격적으로 좋아지기 시작했다면 더 큰 수익을 기다린다.',scores:{H:3,G:1}},
   {id:'24d',label:'회사가 앞으로 오랫동안 성장하기 시작한 단계라고 생각되면 몇 년 더 가지고 있을 수 있다.',scores:{H:3,L:2}}
  ]
 },
 {
  id:25, primaryAxis:'spread',
  title:'내가 가장 편하게 관리할 수 있는 주식 보유 방식은 어느 쪽에 가깝습니까?',
  options:[
   {id:'25a',label:'3~5개의 주식만 골라 자세히 살펴보며 투자한다.',scores:{F:3}},
   {id:'25b',label:'6~10개 정도의 주식을 중심으로 관리한다.',scores:{F:1,M:2}},
   {id:'25c',label:'10~15개 이상의 주식을 여러 업종으로 나눠 가진다.',scores:{M:3}},
   {id:'25d',label:'한두 주식에 몰기보다 여러 종류의 주식과 투자상품에 최대한 넓게 나눠 두는 것이 편하다.',scores:{M:3,D:1}}
  ]
 },
 {
  id:26, primaryAxis:'risk',
  title:'주식시장 전체가 갑자기 10% 이상 크게 떨어졌습니다. 관심 있던 회사들의 매출과 이익 전망에는 큰 변화가 없습니다.',
  options:[
   {id:'26a',label:'더 떨어질까 걱정되어 가지고 있던 주식을 일부 팔고 현금을 늘린다.',scores:{D:3,P:1}},
   {id:'26b',label:'가지고 있는 주식은 팔지 않지만 당분간 새로 사지도 않는다.',scores:{D:2,N:1}},
   {id:'26c',label:'좋게 봤던 회사의 주식을 한 번에 많이 사지 않고 조금씩 나눠 산다.',scores:{A:2,V:1,M:1}},
   {id:'26d',label:'평소 사고 싶었던 가격까지 내려왔다면 적극적으로 더 산다.',scores:{A:3,V:1,F:1}}
  ]
 },
 {
  id:27, primaryAxis:'horizon',
  title:'회사의 먼 미래 전망은 좋지만 앞으로 2~3개월 동안은 특별히 매출이나 이익이 좋아질 만한 일이 없어 보입니다.',
  options:[
   {id:'27a',label:'앞으로 몇 년 뒤의 모습이 더 중요하므로 계속 가지고 있는다.',scores:{L:3}},
   {id:'27b',label:'지금 투자한 금액은 그대로 두고 다음 매출과 이익 발표를 확인한다.',scores:{N:2,L:1}},
   {id:'27c',label:'일부를 팔아 그 돈으로 가까운 시기에 더 오를 것 같은 다른 주식을 찾아본다.',scores:{S:2,N:1}},
   {id:'27d',label:'당분간 주가가 오를 만한 특별한 소식이 없다면 팔고 나중에 다시 본다.',scores:{S:3,P:1}}
  ]
 },
 {
  id:28, primaryAxis:'value',
  title:'빠르게 성장하지는 않지만 업계 1위이고 꾸준히 이익을 잘 내며 회사가 가진 현금도 많은 회사입니다.',
  options:[
   {id:'28a',label:'주식 가격까지 싸 보인다면 매우 매력적이라고 느낀다.',scores:{V:3,L:1}},
   {id:'28b',label:'안정적으로 오래 가지고 갈 주식으로 일부 투자할 수 있다.',scores:{V:2,D:1,M:1}},
   {id:'28c',label:'좋은 회사여도 앞으로 빠르게 성장할 가능성이 낮다면 많은 돈을 투자하기는 어렵다.',scores:{G:2}},
   {id:'28d',label:'사람들의 관심이 적고 최근 주가도 잘 오르지 않는다면 우선순위가 낮다.',scores:{S:2,A:1}}
  ]
 },
 {
  id:29, primaryAxis:'profit',
  title:'수익 중인 주식에 좋지 않은 뉴스가 나왔지만 회사는 잠깐 생긴 문제라고 설명했습니다.',
  options:[
   {id:'29a',label:'아직 수익이 남아 있을 때 먼저 팔아 손실 위험을 없앤다.',scores:{P:3,D:2}},
   {id:'29b',label:'일부만 팔고 실제로 얼마나 심각한 문제인지 더 확인한다.',scores:{P:1,D:1,N:2}},
   {id:'29c',label:'회사의 중요한 사업이 나빠진 것이 아니라면 그대로 가지고 있는다.',scores:{H:2,L:1}},
   {id:'29d',label:'사람들이 뉴스에 너무 크게 반응했다고 생각되면 오히려 더 사는 것도 생각한다.',scores:{H:1,A:3,V:1}}
  ]
 },
 {
  id:30, primaryAxis:'spread',
  title:'올해 가장 좋아 보이는 주식 하나를 발견했습니다. 이미 가지고 있는 다른 주식들과 비교하면 어떻게 투자하시겠습니까?',
  options:[
   {id:'30a',label:'아무리 좋아 보여도 다른 주식과 비슷한 금액만 투자한다.',scores:{M:3,D:1}},
   {id:'30b',label:'다른 주식보다 조금 더 많은 금액을 투자한다.',scores:{M:1,F:2}},
   {id:'30c',label:'다른 주식보다 훨씬 좋아 보인다면 기존 주식을 일부 팔고 이 주식에 더 많은 돈을 투자한다.',scores:{F:3,A:1}},
   {id:'30d',label:'가장 좋아 보이는 한 주식에 많은 돈을 투자하는 것이 더 합리적이라고 생각한다.',scores:{F:3,A:2,H:1}}
  ]
 }
]

const shuffleInvestmentQuestions=()=>{
 const shuffle=list=>{
  const copy=[...list]
  for(let i=copy.length-1;i>0;i--){
   const j=Math.floor(Math.random()*(i+1))
   ;[copy[i],copy[j]]=[copy[j],copy[i]]
  }
  return copy
 }
 return shuffle(
  INVESTMENT_QUESTIONS.map(q=>({
   ...q,
   options:shuffle(q.options)
  }))
 )
}

const INVESTMENT_FRIENDLY_TITLES={
1:'회사는 좋아지고 있는데 주가만 몇 달째 그대로라면 어떻게 하실 것 같나요?',
2:'좋은 회사 같지만 하루에 7~8%씩 크게 움직인다면 투자하시겠어요?',
3:'둘 중 하나만 고른다면 어떤 회사가 더 끌리나요?',
4:'산 주식이 빠르게 18% 올랐고, 산 이유는 그대로라면 어떻게 하시겠어요?',
5:'투자금 1,000만원이 있다면 정말 마음에 드는 한 종목에 얼마까지 넣을 수 있나요?',
6:'새 종목을 볼 때 가장 먼저 보고 싶은 건 무엇인가요?',
7:'좋게 본 주식이 12% 떨어졌지만 회사는 그대로 괜찮다면 어떻게 하시겠어요?',
8:'조금 비싸 보여도 매출이 빠르게 늘고 있는 회사라면 어떻게 하시겠어요?',
9:'수익 중인 주식이 고점에서 6% 내려왔다면 어떻게 하시겠어요?',
10:'같은 업종에 좋아 보이는 회사가 4개 있다면 어떻게 나눠 투자하시겠어요?',
11:'실적 발표를 앞두고 5% 수익 중이라면 어떻게 하시겠어요?',
12:'주식을 사고 나면 얼마나 자주 확인하는 편인가요?',
13:'잘 오르진 않지만 돈을 꾸준히 벌고 배당도 늘리는 회사는 어떤가요?',
14:'주식을 살 때 목표 수익률을 미리 정하는 편인가요?',
15:'한 종목 비중이 40%까지 커졌는데 회사 전망은 좋다면 어떻게 하시겠어요?',
16:'좋은 소식으로 일주일 만에 크게 올랐다면 이후엔 어떻게 하시겠어요?',
17:'현금이 남아 있는데 시장이 계속 오르고 있다면 어떻게 하시겠어요?',
18:'회사를 처음 볼 때 무엇부터 알고 싶나요?',
19:'하루 만에 12% 올랐다면 어떻게 하시겠어요?',
20:'이미 8종목을 갖고 있는데 더 좋은 종목을 찾았다면 어떻게 하시겠어요?',
21:'아직 적자지만 기술력과 관심이 큰 회사라면 투자하시겠어요?',
22:'내가 종목을 잘 골랐는지 판단하려면 어느 정도는 지켜봐야 한다고 생각하나요?',
23:'이미 많이 올랐지만 실적도 계속 좋아질 것 같은 회사라면 어떻게 하시겠어요?',
24:'이미 40% 수익인데 회사가 이제 본격적으로 좋아지기 시작했다면 어떻게 하시겠어요?',
25:'몇 종목 정도를 들고 있는 게 가장 편한가요?',
26:'시장 전체가 갑자기 10% 넘게 떨어졌지만 회사 전망은 그대로라면 어떻게 하시겠어요?',
27:'장기 전망은 좋은데 당장 몇 달간 특별한 호재가 없다면 어떻게 하시겠어요?',
28:'성장은 느려도 업계 1위이고 돈을 꾸준히 잘 버는 회사는 어떤가요?',
29:'수익 중인 주식에 안 좋은 뉴스가 나왔지만 회사는 일시적 문제라고 한다면요?',
30:'올해 가장 좋아 보이는 종목을 찾았다면 다른 종목보다 더 많이 투자하시겠어요?'
}
const INVESTMENT_SHORT_ANSWERS={
1:['계속 가진다','조금 더 본다','일부 옮긴다','더 산다'],2:['안 산다','조금만 산다','보통만큼 산다','적극 산다'],3:['성장하는 회사','싼 회사','균형 잡힌 회사','잘 오르는 회사'],4:['대부분 판다','일부 판다','계속 가진다','더 산다'],5:['조금만 산다','적당히 산다','많이 산다','절반 이상도 산다'],6:['장기 성장','실적과 가격','최근 흐름','둘 다 본다'],7:['판다','기다린다','조금 더 산다','적극 더 산다'],8:['안 산다','기다린다','산다','적극 산다'],9:['판다','일부 판다','계속 가진다','신경 쓰지 않는다'],10:['1개만 산다','2개 산다','3~4개 산다','업종도 나눈다'],11:['발표 전 판다','일부 판다','그대로 둔다','더 살 수도 있다'],12:['큰일 있을 때','주 1~2회','매일','하루에도 여러 번'],13:['좋다','괜찮다','매력 적다','다른 종목 본다'],14:['정한다','대략 정한다','흐름 보고 판다','따로 안 정한다'],15:['일부 판다','조금만 줄인다','그대로 둔다','더 커져도 괜찮다'],16:['판다','일부 판다','실적 보고 결정','계속 가진다'],17:['기다린다','조금씩 산다','적극 산다','대부분 산다'],18:['성장성','가격','돈 버는 힘','주가 흐름'],19:['대부분 판다','일부 판다','더 지켜본다','계속 가진다'],20:['바꿔 산다','조금씩 바꾼다','조금만 추가한다','안 산다'],21:['안 산다','조금만 산다','보통만큼 산다','위험해도 산다'],22:['1~3년','6개월~1년','1~2개월','며칠~몇 주'],23:['안 산다','기다린다','산다','적극 산다'],24:['대부분 판다','절반 판다','더 기다린다','몇 년 더 가진다'],25:['3~5개','6~10개','10~15개 이상','아주 넓게 나눈다'],26:['일부 판다','그대로 둔다','조금씩 산다','적극 산다'],27:['계속 가진다','실적을 기다린다','일부 옮긴다','팔고 다시 본다'],28:['매우 좋다','괜찮다','조금 아쉽다','우선순위 낮다'],29:['판다','일부 판다','계속 가진다','더 살 수도 있다'],30:['비슷하게 산다','조금 더 산다','많이 더 산다','집중해서 산다']
}
const investmentQuestionTitle=q=>INVESTMENT_FRIENDLY_TITLES[q?.id]||q?.title||''
const investmentAnswerLabel=(q,index)=>INVESTMENT_SHORT_ANSWERS[q?.id]?.[index]||q?.options?.[index]?.label||''

const INVESTMENT_QUIZ_STAGES=[
 {label:'시작',hint:'첫 느낌대로 선택해보세요.'},
 {label:'탐색',hint:'내 선택 패턴을 찾아가는 중이에요.'},
 {label:'균형',hint:'절반을 향해 잘 진행하고 있어요.'},
 {label:'정교화',hint:'조금만 더 선택하면 성향이 선명해져요.'},
 {label:'마무리',hint:'거의 다 왔어요.'}
]

const investmentQuizStage=(current,total=INVESTMENT_QUESTIONS.length)=>{
 const count=Math.max(1,total)
 const size=Math.ceil(count/INVESTMENT_QUIZ_STAGES.length)
 const index=Math.min(INVESTMENT_QUIZ_STAGES.length-1,Math.floor(Math.max(0,current)/size))
 return {index,...INVESTMENT_QUIZ_STAGES[index]}
}

const serializeInvestmentQuestionOrder=questions=>(Array.isArray(questions)?questions:[]).map(q=>({
 id:q.id,
 option_ids:(q.options||[]).map(option=>option.id)
}))

const restoreInvestmentQuestionOrder=order=>{
 if(!Array.isArray(order)||!order.length)return null
 const restored=order.map(item=>{
  const base=INVESTMENT_QUESTIONS.find(q=>String(q.id)===String(item?.id))
  if(!base)return null
  const optionIds=Array.isArray(item?.option_ids)?item.option_ids:[]
  const orderedOptions=optionIds.map(id=>base.options.find(option=>option.id===id)).filter(Boolean)
  return {...base,options:orderedOptions.length===base.options.length?orderedOptions:[...base.options]}
 }).filter(Boolean)
 return restored.length===INVESTMENT_QUESTIONS.length?restored:null
}

const readInvestmentDraft=(key,maxAgeMs=24*60*60*1000)=>{
 try{
  const raw=sessionStorage.getItem(key)
  if(!raw)return null
  const parsed=JSON.parse(raw)
  if(!parsed?.saved_at||Date.now()-Number(parsed.saved_at)>maxAgeMs){sessionStorage.removeItem(key);return null}
  return parsed
 }catch{return null}
}

const writeInvestmentDraft=(key,payload)=>{
 try{sessionStorage.setItem(key,JSON.stringify({...payload,saved_at:Date.now()}))}catch{}
}

const clearInvestmentDraft=key=>{
 try{sessionStorage.removeItem(key)}catch{}
}

const SIGNUP_INVESTMENT_DRAFT_KEY='stocklog_signup_investment_draft_v1'
const PROFILE_INVESTMENT_DRAFT_KEY='stocklog_profile_investment_draft_v1'

const ALL_INVESTMENT_CODES=[
 'L','N','S'
].flatMap(h=>
 ['A','D'].flatMap(r=>
  ['G','V'].flatMap(v=>
   ['P','H'].flatMap(p=>
    ['F','M'].map(m=>`${h}${r}${v}${p}${m}`)
   )
  )
 )
)

const profileCodeTitle=code=>{
 if(!code||code.length<5)return '투자 성향 분석'
 const t=code.split('').map(letter=>INVESTMENT_TRAITS[letter])
 return `${t[0].short} / ${t[1].short} / ${t[2].short} / ${t[3].short} / ${t[4].short}형`
}

const profileNickname=code=>{
 if(!code||code.length<5)return '투자 DNA'
 const horizon={
  L:'복리 설계자',
  N:'균형 조율자',
  S:'기회 포착자'
 }[code[0]]
 const value=code[2]==='G'
  ? '성장 탐색'
  : '가치 발굴'
 const spread=code[4]==='F'
  ? '집중형'
  : '분산형'
 return `${horizon} / ${value} ${spread}`
}

const calculateInvestmentProfile=answers=>{
 const points={
  horizon:{L:0,N:0,S:0},
  risk:{A:0,D:0},
  value:{G:0,V:0},
  profit:{P:0,H:0},
  spread:{F:0,M:0}
 }

 const letterAxis={
  L:'horizon',N:'horizon',S:'horizon',
  A:'risk',D:'risk',G:'value',V:'value',
  P:'profit',H:'profit',F:'spread',M:'spread'
 }

 for(const question of INVESTMENT_QUESTIONS){
  const optionId=answers[question.id]
  const option=question.options.find(x=>x.id===optionId)
  if(!option)continue

  Object.entries(option.scores||{}).forEach(([letter,weight])=>{
   const axis=letterAxis[letter]
   if(axis&&letter in points[axis]){
    points[axis][letter]+=Number(weight)||0
   }
  })
 }

 const percentages={}
 for(const axis of INVESTMENT_AXES){
  const values=points[axis.key]
  const total=Object.values(values).reduce((sum,value)=>sum+value,0)
  percentages[axis.key]={}
  for(const letter of axis.letters){
   percentages[axis.key][letter]=total
    ? Math.round(values[letter]/total*100)
    : Math.round(100/axis.letters.length)
  }
 }

 const pickMax=(axis,fallback)=>{
  const entries=Object.entries(points[axis])
  const max=Math.max(...entries.map(([,value])=>value))
  const winners=entries.filter(([,value])=>value===max).map(([letter])=>letter)
  return winners.length===1?winners[0]:(winners.includes(fallback)?fallback:winners[0])
 }

 const code=[
  pickMax('horizon','N'),
  pickMax('risk','D'),
  pickMax('value','V'),
  pickMax('profit','P'),
  pickMax('spread','M')
 ].join('')

 return {code,counts:points,percentages}
}

function InvestmentProfilePage(){
 const [loading,setLoading]=useState(true)
 const [testing,setTesting]=useState(false)
 const [current,setCurrent]=useState(0)
 const [answers,setAnswers]=useState({})
 const [profile,setProfile]=useState(null)
 const [saving,setSaving]=useState(false)
 const [showAllTypes,setShowAllTypes]=useState(false)
 const [testQuestions,setTestQuestions]=useState(()=>shuffleInvestmentQuestions())
 const questionAdvanceTimer=useRef(null)

 useEffect(()=>()=>{
  if(questionAdvanceTimer.current)window.clearTimeout(questionAdvanceTimer.current)
 },[])

 useEffect(()=>{
  let alive=true

  api.get('/api/investment-profile')
   .then(r=>{
    if(!alive)return
    if(r.data?.exists&&r.data?.profile){
     // A profile already stored in the DB is authoritative. Browser drafts are
     // only resumed when no saved profile exists; retesting starts only after
     // the member explicitly presses the retest button.
     setProfile(r.data.profile)
     setTesting(false)
     return
    }
    setProfile(null)
    const draft=readInvestmentDraft(PROFILE_INVESTMENT_DRAFT_KEY)
    const restoredQuestions=restoreInvestmentQuestionOrder(draft?.order)
    if(restoredQuestions&&Object.keys(draft?.answers||{}).length){
     setTestQuestions(restoredQuestions)
     setAnswers(draft.answers||{})
     setCurrent(Math.max(0,Math.min(INVESTMENT_QUESTIONS.length-1,Number(draft.current)||0)))
     setTesting(true)
    }
   })
   .catch(()=>{})
   .finally(()=>{
    if(alive)setLoading(false)
   })

  return()=>{
   alive=false
  }
 },[])

 const startTest=()=>{
  if(questionAdvanceTimer.current)window.clearTimeout(questionAdvanceTimer.current)
  const draft=readInvestmentDraft(PROFILE_INVESTMENT_DRAFT_KEY)
  const restoredQuestions=restoreInvestmentQuestionOrder(draft?.order)
  if(restoredQuestions&&Object.keys(draft?.answers||{}).length){
   setAnswers(draft.answers||{})
   setCurrent(Math.max(0,Math.min(INVESTMENT_QUESTIONS.length-1,Number(draft.current)||0)))
   setTestQuestions(restoredQuestions)
  }else{
   const questions=shuffleInvestmentQuestions()
   setAnswers({})
   setCurrent(0)
   setTestQuestions(questions)
   writeInvestmentDraft(PROFILE_INVESTMENT_DRAFT_KEY,{answers:{},current:0,order:serializeInvestmentQuestionOrder(questions)})
  }
  setTesting(true)
  setShowAllTypes(false)
 }

 const restartTest=()=>{
  if(questionAdvanceTimer.current)window.clearTimeout(questionAdvanceTimer.current)
  const questions=shuffleInvestmentQuestions()
  setAnswers({});setCurrent(0);setTestQuestions(questions);setTesting(true);setShowAllTypes(false)
  writeInvestmentDraft(PROFILE_INVESTMENT_DRAFT_KEY,{answers:{},current:0,order:serializeInvestmentQuestionOrder(questions)})
 }

 const question=testQuestions[current]
 const selected=question
  ? answers[question.id]
  : null
 const quizStage=investmentQuizStage(current,testQuestions.length||INVESTMENT_QUESTIONS.length)

 const saveProfileQuizDraft=(nextAnswers,nextCurrent=current,nextQuestions=testQuestions)=>{
  writeInvestmentDraft(PROFILE_INVESTMENT_DRAFT_KEY,{answers:nextAnswers,current:nextCurrent,order:serializeInvestmentQuestionOrder(nextQuestions)})
 }

 const goProfileQuestion=index=>{
  const next=Math.max(0,Math.min(INVESTMENT_QUESTIONS.length-1,index))
  setCurrent(next);saveProfileQuizDraft(answers,next)
 }

 const choose=value=>{
  if(!question)return
  const nextAnswers={...answers,[question.id]:value}
  setAnswers(nextAnswers)
  if(questionAdvanceTimer.current)window.clearTimeout(questionAdvanceTimer.current)
  if(current<INVESTMENT_QUESTIONS.length-1){
   const nextCurrent=current+1
   saveProfileQuizDraft(nextAnswers,nextCurrent)
   questionAdvanceTimer.current=window.setTimeout(()=>setCurrent(v=>v===current?nextCurrent:v),260)
  }else{
   saveProfileQuizDraft(nextAnswers,current)
  }
 }

 const finish=async()=>{
  if(Object.keys(answers).length!==INVESTMENT_QUESTIONS.length){
   await showMessage(
    '30개 문항에 모두 답해주세요.',
    '응답 확인',
    'warning'
   )
   return
  }

  const result=calculateInvestmentProfile(
   answers
  )

  const payload={
   result_code:result.code,
   answers:INVESTMENT_QUESTIONS.map(q=>({
    question_id:q.id,
    axis:q.primaryAxis,
    value:answers[q.id],
    option_label:q.options.find(option=>option.id===answers[q.id])?.label||''
   })),
   scores:{
    version:2,
    questionnaire:'mixed-30-v1',
    counts:result.counts,
    percentages:result.percentages
   }
  }

  setSaving(true)

  try{
   const r=await api.post(
    '/api/investment-profile',
    payload
   )
   clearInvestmentDraft(PROFILE_INVESTMENT_DRAFT_KEY)
   setProfile(r.data.profile)
   setTesting(false)
   setCurrent(0)
   setShowAllTypes(false)

   window.scrollTo({
    top:0,
    behavior:'smooth'
   })

  }catch(e){
   await showMessage(
    publicUiText(e.response?.data?.detail)
    || '투자 성향 결과 저장에 실패했습니다.',
    '저장 실패',
    'danger'
   )

  }finally{
   setSaving(false)
  }
 }

 if(loading){
  return <div className="loading">
   투자 성향 정보를 불러오는 중...
  </div>
 }

 if(testing){
  const progress=Math.round(
   (current+1)
   / INVESTMENT_QUESTIONS.length
   * 100
  )

  return <>
   <div className="page-head investor-page-head investor-quiz-page-head">
    <div>
     <span>투자성향 검사</span>
     <h1>투자 성향 분석</h1>
    </div>
    <div className="quiz-top-actions">
     <button className="secondary" onClick={restartTest}><RotateCcw size={15}/>처음부터</button>
     <button className="secondary" onClick={()=>setTesting(false)}>테스트 나가기</button>
    </div>
   </div>

   <section className="panel investor-test-panel investor-quiz-card">
    <div className="investment-quiz-stage">
     <div><small>{quizStage.index+1}단계 · {quizStage.label}</small><b>{quizStage.hint}</b></div>
     <div className="investment-quiz-stage-dots">{INVESTMENT_QUIZ_STAGES.map((stage,index)=><span key={stage.label} className={index<quizStage.index?'done':index===quizStage.index?'active':''}><i/></span>)}</div>
    </div>

    <div className="investor-test-progress">
     <div><b>{current+1}</b><span>/ {INVESTMENT_QUESTIONS.length}</span></div>
     <strong>{progress}%</strong>
    </div>

    <div className="investor-progress-bar"><i style={{width:`${progress}%`}}/></div>

    <div className="quiz-question-body investor-quiz-question" key={question.id}>
     <div className="investor-axis-label">상황 선택</div>
     <h2>{investmentQuestionTitle(question)}</h2>

     <div className="investor-answer-list quiz-answer-list">
      {question.options.map((option,index)=>
       <button type="button" key={option.id} className={selected===option.id?'selected':''} onClick={()=>choose(option.id)}>
        <span className="answer-letter">{['A','B','C','D'][index]}</span>
        <span>{investmentAnswerLabel(question,index)}</span>
        {selected===option.id&&<CheckCircle2 size={20}/>}
       </button>
      )}
     </div>
    </div>

    <div className="investor-test-actions quiz-question-actions">
     <button type="button" className="secondary" disabled={current===0} onClick={()=>goProfileQuestion(current-1)}>이전</button>
     {current===INVESTMENT_QUESTIONS.length-1
      ? <button type="button" className="primary quiz-result-button" disabled={!selected||saving} onClick={finish}>{saving?'분석 저장 중...':'내 투자성향 확인하기'}<Sparkles size={16}/></button>
      : <span className="quiz-auto-label">선택하면 다음 문항으로 이동합니다</span>}
    </div>
   </section>
  </>
 }

 if(!profile){
  return <>
   <div className="page-head investor-page-head">
    <div>
     <span>투자성향 분석</span>
     <h1>투자 성향 분석</h1>
     <p>실제 투자 상황에서 어떤 선택을 하는지 빠르게 확인해보세요.</p>
    </div>
   </div>

   <section className="panel investor-intro-hero">
    <div className="investor-intro-icon">
     <Fingerprint size={34}/>
    </div>
    <div>
     <span>5 AXES / 48 INVESTOR TYPES</span>
     <h2>나의 투자 습관을 다섯 글자로</h2>
     <p>
      어렵게 투자 지식을 시험하는 검사가 아닙니다. 평소 어떤 상황에서 사고, 기다리고, 파는지가 StockLog 추천 기준에 반영됩니다.
     </p>
     <div className="investor-benefit-grid">
      <span><CheckCircle2 size={15}/><b>내 성향 추천</b><small>나와 맞는 스마트 종목을 우선 보여드립니다.</small></span>
      <span><CheckCircle2 size={15}/><b>설명 방식 조정</b><small>위험·보유기간·가격 민감도를 내 성향에 맞춰 해석합니다.</small></span>
      <span><CheckCircle2 size={15}/><b>과한 선택 줄이기</b><small>내가 흔들리기 쉬운 상황과 주의점을 같이 알려드립니다.</small></span>
     </div>
    </div>
    <button
     type="button"
     className="primary investor-start-button"
     onClick={startTest}
    >
     <Sparkles size={17}/>
     투자성향 시작하기
    </button>
   </section>

   <div className="investor-axis-preview-grid">
    {INVESTMENT_AXES.map(axis=>
     <section className="panel investor-axis-preview" key={axis.key}>
      <small>{axis.name}</small>
      <b>{axis.caption}</b>
      <div className="investor-axis-neutral">
       <span>선택 패턴을 바탕으로 성향을 분석합니다.</span>
      </div>
     </section>
    )}
   </div>

   <p className="investor-disclaimer">
    이 테스트는 투자 습관을 돌아보기 위한 자기점검용 콘텐츠이며
    금융회사의 공식 투자자 적합성/적정성 평가가 아닙니다.
   </p>
  </>
 }

 const code=profile.result_code
 const traits=code.split('').map(letter=>({
  letter,
  ...INVESTMENT_TRAITS[letter]
 }))
 const percentages=profile.scores?.percentages||{}

 return <>
  <div className="page-head investor-page-head">
   <div>
    <span>나의 투자성향</span>
    <h1>나의 투자 성향</h1>
    <p>30개 혼합형 상황 문항의 가중점수를 바탕으로 현재 투자 습관을 5자리 코드와 연속 점수로 정리했습니다.</p>
   </div>
   <button
    type="button"
    className="secondary"
    onClick={startTest}
   >
    <RotateCcw size={15}/>
    다시 테스트
   </button>
  </div>

  <section className="panel investor-result-hero">
   <div className="investor-result-symbol">
    <Fingerprint size={32}/>
   </div>

   <div className="investor-result-main">
    <small>YOUR TYPE</small>
    <div className="investor-code">
     {code.split('').map((letter,i)=>
      <span key={`${letter}-${i}`}>
       {letter}
      </span>
     )}
    </div>
    <h2>{profileNickname(code)}</h2>
    <p>{profileCodeTitle(code)}</p>
   </div>

   <div className="investor-result-date">
    <small>최근 검사</small>
    <b>
     {profile.completed_at
      ? new Date(profile.completed_at).toLocaleDateString('ko-KR')
      : '-'}
    </b>
   </div>
  </section>

  <div className="investor-trait-grid">
   {traits.map((trait,index)=>
    <section
     className="panel investor-trait-card"
     key={`${trait.letter}-${index}`}
    >
     <div className="investor-trait-head">
      <strong>{trait.letter}</strong>
      <div>
       <small>{INVESTMENT_AXES[index].name}</small>
       <h3>{trait.name}</h3>
      </div>
     </div>

     <p>{trait.summary}</p>

     <div className="investor-trait-note good">
      <b>강점</b>
      <span>{trait.strength}</span>
     </div>

     <div className="investor-trait-note caution">
      <b>주의</b>
      <span>{trait.caution}</span>
     </div>
    </section>
   )}
  </div>

  <section className="panel investor-balance-panel">
   <div className="section-title-row">
    <div>
     <span>MY BALANCE</span>
     <h3>성향 비율</h3>
     <p>여러 상황 선택에 반영된 가중점수를 0~100 비율로 환산한 결과입니다.</p>
    </div>
    <Compass size={21}/>
   </div>

   <div className="investor-balance-list">
    {INVESTMENT_AXES.map(axis=>
     <div className="investor-balance-axis" key={axis.key}>
      <div className="investor-balance-axis-title">
       <b>{axis.name}</b>
       <span>{axis.caption}</span>
      </div>
      <div className="investor-balance-bars">
       {axis.letters.map(letter=>{
        const value=percentages?.[axis.key]?.[letter]??0
        return <div className="investor-balance-row" key={letter}>
         <span>
          <b>{letter}</b>
          {INVESTMENT_TRAITS[letter].short}
         </span>
         <i>
          <em style={{width:`${value}%`}}/>
         </i>
         <strong>{value}%</strong>
        </div>
       })}
      </div>
     </div>
    )}
   </div>
  </section>

  <section className="panel investor-all-types">
   <div className="section-title-row">
    <div>
     <span>48 INVESTOR TYPES</span>
     <h3>다른 투자 성향도 둘러보기</h3>
     <p>L/N/S × A/D × G/V × P/H × F/M 조합으로 총 48가지 유형이 만들어집니다.</p>
    </div>

    <button
     type="button"
     className="secondary"
     onClick={()=>setShowAllTypes(v=>!v)}
    >
     {showAllTypes
      ? '유형 접기'
      : '48가지 전체 보기'}
    </button>
   </div>

   <div className={`investor-type-grid ${showAllTypes?'expanded':''}`}>
    {(showAllTypes
      ? ALL_INVESTMENT_CODES
      : ALL_INVESTMENT_CODES.slice(0,8)
     ).map(typeCode=>
      <article
       className={`investor-type-card ${typeCode===code?'mine':''}`}
       key={typeCode}
      >
       <div>
        <strong>{typeCode}</strong>
        {typeCode===code&&<em>MY TYPE</em>}
       </div>
       <b>{profileNickname(typeCode)}</b>
       <span>{profileCodeTitle(typeCode)}</span>
      </article>
     )}
   </div>
  </section>

  <p className="investor-disclaimer">
   투자 성향은 경험/자산상황/시장환경에 따라 바뀔 수 있습니다.
   이 결과는 자기점검용이며 투자 권유나 금융회사의 공식 적합성 평가가 아닙니다.
  </p>
 </>
}


function TradingConnectionPanel({environment}){
 const live=environment==='live',apiRoot=live?'/api/live-trading':'/api/trading',label=live?'실전투자':'모의투자'
 const [form,setForm]=useState({app_key:'',secret_key:'',use_mock:!live}),[state,setState]=useState({}),[msg,setMsg]=useState(''),[busy,setBusy]=useState(false),[activation,setActivation]=useState('')
 const load=async()=>{const r=await api.get(`${apiRoot}/connection`);setState(r.data||{})}
 useEffect(()=>{load().catch(()=>{})},[environment])
 const save=async()=>{
  setBusy(true);setMsg(`${label} 전용 키를 저장하고 계좌를 확인하고 있습니다...`)
  try{const r=await api.put(`${apiRoot}/connection`,{...form,use_mock:!live});setState(r.data.settings||{});setForm({app_key:'',secret_key:'',use_mock:!live});setMsg(publicUiText(r.data.message))}
  catch(e){setMsg(publicUiText(e.response?.data?.detail)||`${label} 연결 저장에 실패했습니다.`);await load().catch(()=>{})}finally{setBusy(false)}
 }
 const reconnect=async()=>{
  setBusy(true);setMsg(`${label} 인증 서버와 계좌를 다시 확인하고 있습니다...`)
  try{const r=await api.post(`${apiRoot}/connection/test`);if(r.data.settings)setState(r.data.settings);setMsg(publicUiText(r.data.message))}
  catch(e){setMsg(publicUiText(e.response?.data?.detail)||`${label} 연결 확인에 실패했습니다.`)}finally{setBusy(false)}
 }
 const activate=async enabled=>{
  const expected=enabled?'실전투자 활성화':'실전투자 비활성화'
  if(activation.trim()!==expected){setMsg(`확인 문구 '${expected}'를 정확히 입력해주세요.`);return}
  setBusy(true)
  try{const r=await api.put('/api/live-trading/activation',{enabled,confirmation_text:activation.trim()});setState(r.data.settings||state);setActivation('');setMsg(r.data.message)}
  catch(e){setMsg(publicUiText(e.response?.data?.detail)||'실전 주문 상태 변경에 실패했습니다.')}finally{setBusy(false)}
 }
 return <div className={`connection-environment ${live?'live':''}`}>
  {live&&<div className="live-account-warning"><AlertTriangle size={20}/><div><b>실제 자금이 움직이는 실전 계정입니다.</b><span>모의 키와 실전 키는 별도 암호화 저장되며, 실전 API 서버에서 계좌가 확인되어도 주문 기능은 자동으로 켜지지 않습니다.</span></div></div>}
  <div className="two-col">
   <div className="panel"><div className="connection-card-title"><div><small>{live?'PRODUCTION API':'MOCK API'}</small><h3>{label} 전용 연동 정보</h3></div><span className={state.configured?'ok':'off'}>{state.configured?'연결 정보 있음':'미설정'}</span></div>
    <p className="muted">계좌번호는 직접 입력하지 않습니다. {label} 전용 인증 서버에서 토큰 발급과 계좌 조회를 순서대로 확인합니다.</p>
    <label>App Key<input type="password" value={form.app_key} onChange={e=>setForm({...form,app_key:e.target.value})} placeholder={state.has_app_key?'기존 키를 유지하려면 비워두세요':`${label} App Key`}/></label>
    <label>Secret Key<input type="password" value={form.secret_key} onChange={e=>setForm({...form,secret_key:e.target.value})} placeholder={state.has_secret_key?'기존 키를 유지하려면 비워두세요':`${label} Secret Key`}/></label>
    <div className="row"><button className={live?'danger-live-button':'primary'} onClick={save} disabled={busy}>{busy?'처리 중...':'키 저장 + 계좌 확인'}</button><button className="secondary" onClick={reconnect} disabled={busy||!state.configured}>연동 테스트</button></div>
    {msg&&<div className={`info ${live?'live-info':''}`}>{msg}</div>}
   </div>
   <div className="panel"><h3>{label} 저장 상태</h3><div className="status-grid">
    <div className="status-item"><small>환경</small><b>{live?'실전 서버':'모의 서버'}</b></div><div className="status-item"><small>연결 계좌</small><b>{state.account_no_masked||'아직 조회되지 않음'}</b></div>
    <div className="status-item"><small>App Key</small><b>{state.has_app_key?state.app_key_masked:'미저장'}</b></div><div className="status-item"><small>Secret Key</small><b>{state.has_secret_key?state.secret_key_masked:'미저장'}</b></div>
    <div className="status-item"><small>마지막 저장</small><b>{state.updated_at?new Date(state.updated_at).toLocaleString():'-'}</b></div><div className="status-item"><small>마지막 연결 확인</small><b>{state.last_connected_at?new Date(state.last_connected_at).toLocaleString():'-'}</b></div>
   </div><button className="secondary" onClick={load} style={{marginTop:12}}>저장 상태 다시 읽기</button></div>
  </div>
  {live&&<div className={`panel live-activation-panel ${state.trading_enabled?'enabled':''}`}><div><small>LIVE ORDER SAFETY LOCK</small><h3>실전 주문 잠금</h3><p>{state.trading_enabled?'실전 수동·자동 주문이 활성화되어 있습니다. 비활성화하면 자동매매도 즉시 중지됩니다.':'연결 테스트만으로는 주문되지 않습니다. 아래 확인 문구를 직접 입력해야 수동·자동 주문 API가 열립니다.'}</p></div><div className="live-activation-control"><label>확인 문구<input value={activation} onChange={e=>setActivation(e.target.value)} placeholder={state.trading_enabled?'실전투자 비활성화':'실전투자 활성화'}/></label><button className={state.trading_enabled?'secondary':'danger-live-button'} disabled={busy||!state.account_no} onClick={()=>activate(!state.trading_enabled)}>{state.trading_enabled?'실전 주문 비활성화':'실전 주문 활성화'}</button></div></div>}
 </div>
}

function TradingConnectionSettings(){
 const [tab,setTab]=useState('mock')
 return <><div className="page-head"><div><span>BROKER SETTINGS</span><h1>계정 연동</h1><p>키움 모의투자와 실전투자를 서로 분리해 저장하고 각각 연결 테스트할 수 있습니다.</p></div></div>
 <div className="connection-tabs" role="tablist"><button className={tab==='mock'?'active':''} onClick={()=>setTab('mock')}><ShieldCheck size={16}/>모의투자 연동</button><button className={tab==='live'?'active live':''} onClick={()=>setTab('live')}><AlertTriangle size={16}/>실전투자 연동</button></div>
 <TradingConnectionPanel key={tab} environment={tab}/>
 <div className="panel guide connection-isolation-guide"><h3>계정 분리 원칙</h3><ol><li>모의 키는 키움 모의 서버, 실전 키는 키움 실전 서버에만 전송합니다.</li><li>토큰·계좌번호·잔고 캐시·주문 이력·자동매매 설정을 환경별로 분리합니다.</li><li>실전 연결 테스트는 인증과 계좌 조회만 수행하며 주문은 전송하지 않습니다.</li><li>실전 주문은 별도의 활성화와 매 주문 확인, 서버 주문금액 한도를 모두 통과해야 합니다.</li></ol></div></>
}

function InvestmentEnvironmentSwitch({environment='mock',onChange,canMock=true,canLive=true}){
 const isLive=environment==='live'
 return <section className={`investment-environment-switch ${isLive?'live':''}`} aria-label="증권투자 계좌 환경">
  <div className="investment-environment-copy">
   <span>{isLive?<AlertTriangle size={16}/>:<ShieldCheck size={16}/>}</span>
   <div><small>TRADING ENVIRONMENT</small><b>{isLive?'실전투자 계좌':'모의투자 계좌'}</b><p>{isLive?'실제 자금이 움직이는 실계좌 데이터와 주문 기능을 사용합니다.':'모의 계좌 데이터와 주문 기능을 사용하며 실계좌에는 영향을 주지 않습니다.'}</p></div>
  </div>
  <div className="connection-tabs investment-environment-tabs" role="tablist" aria-label="모의투자와 실전투자 전환">
   <button type="button" role="tab" aria-selected={!isLive} className={!isLive?'active':''} disabled={!canMock} title={!canMock?'현재 회원 등급에서는 모의투자를 사용할 수 없습니다.':undefined} onClick={()=>canMock&&onChange?.('mock')}><ShieldCheck size={16}/>모의투자</button>
   <button type="button" role="tab" aria-selected={isLive} className={isLive?'active live':'live'} disabled={!canLive} title={!canLive?'현재 회원 등급에서는 실전투자를 사용할 수 없습니다.':undefined} onClick={()=>canLive&&onChange?.('live')}><AlertTriangle size={16}/>실전투자</button>
  </div>
 </section>
}

function InvestmentPageShell({environment,onEnvironmentChange,canMock,canLive,children}){
 return <div className="investment-page-shell">
  <InvestmentEnvironmentSwitch environment={environment} onChange={onEnvironmentChange} canMock={canMock} canLive={canLive}/>
  {children}
 </div>
}

function PortfolioCategoryChart({items=[]}){
 const el=useRef(null)
 const chartRef=useRef(null)

 useEffect(()=>{
  if(!el.current)return

  const chart=echarts.init(el.current)
  chartRef.current=chart

  const resize=()=>chart.resize()

  window.addEventListener(
   'resize',
   resize
  )

  let observer=null

  if(typeof ResizeObserver!=='undefined'){
   observer=new ResizeObserver(resize)
   observer.observe(el.current)
  }

  return()=>{
   observer?.disconnect()
   window.removeEventListener(
    'resize',
    resize
   )
   chart.dispose()
   chartRef.current=null
  }
 },[])

 useEffect(()=>{
  const chart=chartRef.current
  if(!chart)return

  const data=(items||[])
   .filter(
    x=>Number(x.evaluation_amount||0)>0
   )
   .map(x=>({
    name:x.name,
    value:Number(x.evaluation_amount||0)
   }))

  chart.setOption(
   {
    animation:false,
    animationDuration:0,
    animationDurationUpdate:0,
    tooltip:{
     trigger:'item',
     formatter:p=>`${p.name}<br/>${Number(p.value||0).toLocaleString('ko-KR')}원 / ${Number(p.percent||0).toFixed(1)}%`
    },
    legend:{
     type:'scroll',
     bottom:0,
     left:'center',
     textStyle:{fontSize:12}
    },
    series:[{
     name:'투자 비중',
     type:'pie',
     radius:['48%','72%'],
     center:['50%','43%'],
     avoidLabelOverlap:true,
     itemStyle:{
      borderRadius:6,
      borderColor:'#fff',
      borderWidth:2
     },
     label:{
      show:true,
      formatter:'{b}\n{d}%',
      fontSize:12
     },
     labelLine:{
      length:8,
      length2:6
     },
     data
    }]
   },
   {
    notMerge:false,
    lazyUpdate:true
   }
  )
 },[items])

 return <div
  className="portfolio-category-chart"
  ref={el}
 />
}



function PortfolioPage({user,openStock,environment='mock'}){
 const isLive=environment==='live'
 const portfolioApiRoot=isLive?'/api/live-trading':'/api/trading'
 const accountLabel=isLive?'실전투자':'모의투자'
 const [p,setP]=useState(null)
 const [loading,setLoading]=useState(true)
 const [refreshing,setRefreshing]=useState(false)
 const [err,setErr]=useState('')
 const [lastUpdated,setLastUpdated]=useState(null)
 const [momentum,setMomentum]=useState({})
 const [reasonDetail,setReasonDetail]=useState(null)
 const canMomentum=!isLive&&Boolean(user?.features?.portfolio_ai_momentum?.enabled)
 const load=async(force=false,{silent=false}={})=>{
  if(!silent)setRefreshing(true)
  try{
   const r=await api.get(`${portfolioApiRoot}/portfolio`,{params:{force}})
   setP(r.data||null);setErr('');setLastUpdated(new Date())
  }catch(e){if(!silent)setErr(publicUiText(e.response?.data?.detail)||`${accountLabel} 포트폴리오를 불러오지 못했습니다.`)}
  finally{setLoading(false);if(!silent)setRefreshing(false)}
 }
 useEffect(()=>{
  let stopped=false
  load(false).catch(()=>{})
  const timer=setInterval(()=>{if(!stopped&&document.visibilityState==='visible')load(false,{silent:true}).catch(()=>{})},20000)
  return()=>{stopped=true;clearInterval(timer)}
 },[environment])
 useEffect(()=>{
  if(!canMomentum||!p?.holdings?.length)return
  let alive=true
  const read=async()=>{
   try{
    const r=await api.get('/api/trading/portfolio/outlook')
    if(!alive)return
    const map={};(r.data?.items||[]).forEach(x=>{map[String(x.code||'')]=x});setMomentum(map)
    if(!r.data?.job?.running&&Object.values(map).every(x=>!x?.ready)){
     try{await api.post('/api/trading/portfolio/outlook/start')}catch{}
    }
   }catch{}
  }
  read();const t=setInterval(read,12000)
  return()=>{alive=false;clearInterval(t)}
 },[canMomentum,(p?.holdings||[]).map(x=>x.code).join('|')])
 const summary=p?.summary||{}
 const holdings=Array.isArray(p?.holdings)?p.holdings:[]
 const categoryStats=useMemo(()=>{
  const map=new Map()
  holdings.forEach(h=>{
   const name=String(h.portfolio_category||h.industry_name||h.sector||'기타').trim()||'기타'
   const prev=map.get(name)||{name,stock_count:0,evaluation_amount:0,purchase_amount:0,profit_loss:0}
   prev.stock_count+=1
   const evalAmount=Number(h.market_value||0)||Number(h.current_price||0)*Number(h.quantity||0)||Number(h.evaluation_amount||0)
   const purchaseAmount=Number(h.purchase_amount||0)||Number(h.avg_price||0)*Number(h.quantity||0)
   const totalProfit=Number(h.profit_loss||0)||(evalAmount-purchaseAmount)
   prev.evaluation_amount+=evalAmount
   prev.purchase_amount+=purchaseAmount
   prev.profit_loss+=totalProfit
   map.set(name,prev)
  })
  const total=[...map.values()].reduce((sum,x)=>sum+Number(x.evaluation_amount||0),0)
  return [...map.values()].map(x=>({...x,weight:total>0?x.evaluation_amount/total*100:0,return_rate:x.purchase_amount>0?x.profit_loss/x.purchase_amount*100:0})).sort((a,b)=>b.evaluation_amount-a.evaluation_amount)
 },[holdings])
 const sourceCounts=useMemo(()=>holdings.reduce((acc,h)=>{const k=h.acquisition_source||'manual';acc[k]=(acc[k]||0)+1;return acc},{manual:0,auto:0,mixed:0}),[holdings])
 const portfolioPnl=Number(summary.profit_loss||0)
 const portfolioDayPnl=Number(summary.day_profit||0)
 const portfolioDayRate=Number(summary.day_return_rate||0)
 return <>{reasonDetail&&<AutoTradeHistoryDetail row={reasonDetail} onClose={()=>setReasonDetail(null)}/>} {(loading||refreshing)&&<PageDataLoadingStatus marketLabel="국내증권" pageLabel="포트폴리오" title={`${accountLabel} 포트폴리오를 업데이트하고 있어요`} detail="현재 화면을 유지하면서 계좌 원장과 보유종목 평가를 다시 확인합니다." steps={['현재 포트폴리오 유지','계좌 원장 확인','평가 결과 반영']}/>}<div className="sync-page portfolio-page">
  <div className="page-head portfolio-page-head">
   <div><span>MY INVESTMENT / PORTFOLIO</span><h1>포트폴리오</h1><p>{accountLabel}의 수동·자동 보유종목을 한곳에서 보고, 직접 매수와 Gbot 자동매수 비중까지 구분합니다.</p></div>
   <div className="portfolio-page-actions"><div className="live-update-stamp"><Activity size={14}/><span>최근 업데이트</span><b>{lastUpdated?lastUpdated.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'-'}</b></div><button className="secondary" disabled={refreshing} onClick={()=>load(true)}><RefreshCw size={15} className={refreshing?'spin-icon':''}/>{refreshing?'갱신 중...':'새로고침'}</button></div>
  </div>
  {err&&<div className="error-box"><b>포트폴리오 조회</b><span>{err}</span></div>}
  {p&&<>
   <section className="portfolio-page-hero">
    <div className="portfolio-page-total"><small>투자 평가액</small><strong>{won(summary.evaluation_amount)}<em>원</em></strong><span>계좌 {p.account_no||'-'} · 키움 총평가 · 총매입 {won(summary.purchase_amount)}원</span></div>
    <div className="portfolio-page-hero-kpis portfolio-profit-split">
     <article><small>금일 투자손익</small><b className={portfolioDayPnl>=0?'up':'down'}>{portfolioDayPnl>=0?'+':''}{won(portfolioDayPnl)}원</b><span className={portfolioDayRate>=0?'up':'down'}>{portfolioDayRate>=0?'+':''}{portfolioDayRate.toFixed(2)}%</span></article>
     <article><small>총손익</small><b className={portfolioPnl>=0?'up':'down'}>{portfolioPnl>=0?'+':''}{won(portfolioPnl)}원</b><span className={Number(summary.return_rate||0)>=0?'up':'down'}>{Number(summary.return_rate||0)>=0?'+':''}{Number(summary.return_rate||0).toFixed(2)}%</span></article>
     <article><small>총 자산</small><b>{won(summary.total_asset)}원</b><span>{summary.total_asset_basis==='kiwoom_prsm_dpst_aset_amt'?'키움 추정예탁자산':summary.total_asset_basis==='kiwoom_fallback'?'키움 계좌원장':'총자산 원장 확인 필요'}</span></article>
     <article><small>주문가능금액</small><b>{won(summary.buying_power_available?summary.buying_power:summary.cash)}원</b><span>{summary.buying_power_available?'키움 실시간 기준':'계좌 현금 기준'}</span></article>
     <article><small>보유 구성</small><b>{holdings.length}종목</b><span>직접 {sourceCounts.manual} · Gbot {sourceCounts.auto} · 혼합 {sourceCounts.mixed}</span></article>
    </div>
   </section>

   <section className="panel portfolio-holdings-v2">
    <div className="section-title-row"><div><span>HOLDINGS</span><h3>보유 종목</h3><p>{accountLabel} 계좌 보유수량을 기준으로 해당 환경의 자동매매 원장과 대조해 매수 출처를 표시합니다.</p></div></div>
    {holdings.length?<div className="portfolio-holding-table">
     <div className="portfolio-holding-head"><span>종목</span><span>매수 구분</span><span>매입가격</span><span>보유수량</span><span>현재가</span><span>평가금액</span><span>금일 투자손익</span><span>수수료</span><span>총손익 (수수료반영)</span><span>수익률</span><span>테마</span><span></span></div>
     {holdings.slice().sort((a,b)=>Number(b.evaluation_amount||0)-Number(a.evaluation_amount||0)).map(h=>{
      const source=h.acquisition_source||'manual'
      const sourceText=source==='auto'?'Gbot 자동':source==='mixed'?'직접 + Gbot':'직접 매수'
      return <div role="button" tabIndex={0} className="portfolio-holding-row" key={h.code} onClick={()=>openStock?.({code:h.code})} onKeyDown={e=>{if(e.key==='Enter')openStock?.({code:h.code})}}>
       <span className="portfolio-stock-cell"><b>{h.name||h.code}</b><small>{h.code}{h.market?` · ${h.market}`:''}</small>{canMomentum&&momentum[String(h.code||'')]?.ready&&<em className={`portfolio-ai-badge ${momentum[String(h.code||'')]?.analysis?.view||'neutral'}`}>AI {publicUiText(momentum[String(h.code||'')]?.analysis?.label)||'모멘텀'} · {Number(momentum[String(h.code||'')]?.analysis?.confidence||0)}점</em>}</span>
       <span className={`portfolio-source-badge ${source}`}><b>{sourceText}</b><small>{source==='mixed'?`직접 ${won(h.manual_quantity)}주 · Gbot ${won(h.auto_quantity)}주`:source==='auto'?`Gbot ${won(h.auto_quantity)}주`:`직접 ${won(h.manual_quantity??h.quantity)}주`}</small>{h.last_trade_source&&<em>최근 {h.last_trade_source==='auto'?'Gbot':'직접'} {h.last_trade_side==='sell'?'매도':'매수'}</em>}</span>
       <span><b>{won(h.avg_price)}원</b><small>평균 매입가</small></span>
       <span><b>{Number(h.quantity||0).toLocaleString()}주</b><small>계좌 보유</small></span>
       <span><b>{won(h.current_price)}원</b><small>현재 체결가</small></span>
       <span><b>{won(Number(h.evaluation_amount||0)||Number(h.current_price||0)*Number(h.quantity||0))}원</b><small>{String(h.pnl_basis||'').startsWith('kiwoom')?'키움 평가금액':'보정 평가금액'}</small></span>
       <span className={Number(h.day_profit||0)>=0?'up':'down'}><b>{Number(h.day_profit||0)>=0?'+':''}{won(h.day_profit)}원</b><small>{Number(h.day_return_rate||0)>=0?'+':''}{Number(h.day_return_rate||0).toFixed(2)}%</small>{h.day_profit_basis==='today_acquired_kiwoom_net'&&Math.abs(Number(h.market_day_profit||0)-Number(h.day_profit||0))>=1?<em className="portfolio-market-day-note">주가 일간변동 {Number(h.market_day_profit||0)>=0?'+':''}{won(h.market_day_profit)}원</em>:null}</span>
       <span><b>{won(h.fee_amount||0)}원</b><small>{h.fee_estimated?'순손익 기준 역산':'순손익 반영'}</small></span>
       <span className={Number(h.profit_loss||0)>=0?'up':'down'}><b>{Number(h.profit_loss||0)>=0?'+':''}{won(h.profit_loss)}원</b><small>{String(h.pnl_basis||'').startsWith('kiwoom')?'키움 원장·비용반영':'보정값'}</small></span>
       <span className={Number(h.return_rate||0)>=0?'up':'down'}><b>{Number(h.return_rate||0)>=0?'+':''}{Number(h.return_rate||0).toFixed(2)}%</b></span>
       <span className="portfolio-theme-cell"><StockThemeBadges themes={h.themes||[]} fallback={h.theme_fallback} max={2} compact/></span>
       <span className="portfolio-row-actions">{h.auto_trade_reason?<button type="button" className="portfolio-ai-reason-btn" onClick={e=>{e.stopPropagation();setReasonDetail({...h.auto_trade_reason,name:h.auto_trade_reason?.name||h.name||h.code,code:h.auto_trade_reason?.code||h.code,portfolio_context:true})}}><Sparkles size={13}/>AI 체결사유</button>:null}</span>
      </div>
     })}
    </div>:<div className="empty portfolio-empty">현재 보유 중인 {accountLabel} 종목이 없습니다.</div>}
   </section>

   {categoryStats.length>0&&<section className="panel portfolio-mix-v2">
    <div className="section-title-row"><div><span>PORTFOLIO MIX</span><h3>테마 · 카테고리 비중</h3><p>StockLog 대표 테마와 업종 분류를 기준으로 현재 포트폴리오가 어디에 집중되어 있는지 보여줍니다.</p></div></div>
    <div className="portfolio-mix-layout"><div className="portfolio-category-chart-card"><PortfolioCategoryChart items={categoryStats}/></div><div className="portfolio-mix-list">{categoryStats.slice(0,10).map(row=><div key={row.name}><span><b>{row.name}</b><small>{row.stock_count}종목</small></span><span><b>{row.weight.toFixed(1)}%</b><small>{won(row.evaluation_amount)}원</small></span><i><em style={{width:`${Math.min(100,Math.max(0,row.weight))}%`}}/></i></div>)}</div></div>
   </section>}
  </>}
 </div></>
}

function HoldingPriceChart({data=[],liveValues=[],currentPrice=0}){
 const el=useRef(null)
 const chartRef=useRef(null)
 const rows=Array.isArray(data)?data.slice(-90):[]
 const ticks=(liveValues||[]).map(Number).filter(v=>Number.isFinite(v)&&v>0)
 const hasData=rows.length>1||ticks.length>1

 useEffect(()=>{
  if(!hasData||!el.current)return
  const chart=echarts.init(el.current)
  chartRef.current=chart
  const resize=()=>chart.resize()
  window.addEventListener('resize',resize)
  let observer=null
  if(typeof ResizeObserver!=='undefined'){
   observer=new ResizeObserver(resize)
   observer.observe(el.current)
  }
  return()=>{
   observer?.disconnect()
   window.removeEventListener('resize',resize)
   chart.dispose()
   chartRef.current=null
  }
 },[hasData])

 useEffect(()=>{
  const chart=chartRef.current
  if(!chart||!hasData)return
  let labels=[],values=[]
  if(rows.length>1){
   labels=rows.map(x=>String(x.date||'').slice(5))
   values=rows.map(x=>Number(x.close||0))
   const live=Number(currentPrice||ticks[ticks.length-1]||0)
   if(live>0&&values.length)values[values.length-1]=live
  }else{
   labels=ticks.map((_,i)=>String(i+1))
   values=ticks
  }
  chart.setOption({
   animation:false,
   grid:{left:8,right:8,top:12,bottom:24,containLabel:true},
   tooltip:{
    trigger:'axis',
    backgroundColor:'#172033',
    borderWidth:0,
    textStyle:{color:'#fff',fontSize:12},
    formatter:params=>{
     const p=params?.[0]
     if(!p)return ''
     return `${p.axisValue}<br/><b>${Number(p.value||0).toLocaleString('ko-KR')}원</b>`
    }
   },
   xAxis:{
    type:'category',
    boundaryGap:false,
    data:labels,
    axisLine:{lineStyle:{color:'#dce2eb'}},
    axisTick:{show:false},
    axisLabel:{color:'#8a96a9',fontSize:12,hideOverlap:true,interval:'auto'}
   },
   yAxis:{
    type:'value',
    scale:true,
    splitNumber:3,
    axisLabel:{color:'#8a96a9',fontSize:12,formatter:v=>Number(v).toLocaleString('ko-KR')},
    splitLine:{lineStyle:{color:'#eef1f5',type:'dashed'}}
   },
   series:[{
    type:'line',
    data:values,
    showSymbol:false,
    smooth:.16,
    lineStyle:{width:2.2,color:'#586a9c'},
    areaStyle:{color:'rgba(88,106,156,.08)'},
    emphasis:{focus:'series'}
   }]
  },{notMerge:true,lazyUpdate:true})
 },[data,liveValues,currentPrice,hasData])

 if(!hasData){
  return <div className="holding-chart-empty"><BarChart3 size={20}/><b>마지막 차트 데이터 없음</b><span>최근 확인된 가격 정보를 바탕으로 차트를 표시합니다.</span></div>
 }
 return <div className="holding-price-chart" ref={el}/>
}

function Trading({intent,user,environment='mock'}){
 const isLive=environment==='live'
 const tradingApiRoot=isLive?'/api/live-trading':'/api/trading'
 const tradingLabel=isLive?'실전투자':'모의투자'
 const [p,setP]=useState(null),[err,setErr]=useState('')
 const [form,setForm]=useState({side:'buy',stock_code:'',quantity:1,order_type:'market',price:''}),[busy,setBusy]=useState(false)
 const [searchQ,setSearchQ]=useState(''),[results,setResults]=useState([]),[selected,setSelected]=useState(null),[chart,setChart]=useState([]),[quote,setQuote]=useState(null),[searching,setSearching]=useState(false),[quoteLoading,setQuoteLoading]=useState(false),[searchOpen,setSearchOpen]=useState(false)
 const [syncing,setSyncing]=useState(false),[lastAttempt,setLastAttempt]=useState(null)
 const [holdingFocusCode,setHoldingFocusCode]=useState('')
 const [orderOpen,setOrderOpen]=useState(true)
 const [orderPanelTab,setOrderPanelTab]=useState('normal')
 const [orderHistoryTab,setOrderHistoryTab]=useState('pending')
 const [orderbook,setOrderbook]=useState({asks:[],bids:[],best_ask:null,best_bid:null})
 const [orderbookLoading,setOrderbookLoading]=useState(false)
 const [reservations,setReservations]=useState([])
 const [reservationBusy,setReservationBusy]=useState(false)
 const [reservationEditingId,setReservationEditingId]=useState(null)
 const [reservationForm,setReservationForm]=useState({
  side:'buy',
  trigger_operator:'lte',
  trigger_price:'',
  quantity:1,
  order_type:'market',
  order_price:'',
  expires_at:''
 })
 const [liveQuotes,setLiveQuotes]=useState({}),[liveHistory,setLiveHistory]=useState({}),[lastLiveAt,setLastLiveAt]=useState(null)
 const [liveState,setLiveState]=useState({state:'connecting',message:'실시간 연결 준비 중',subscribed:0})
 const [buyingPowerLive,setBuyingPowerLive]=useState(null)
 const [holdingChartData,setHoldingChartData]=useState([]),[holdingChartLoading,setHoldingChartLoading]=useState(false)
 const [investorFlow,setInvestorFlow]=useState(null),[investorFlowLoading,setInvestorFlowLoading]=useState(false)
 const [refreshPolicy,setRefreshPolicy]=useState(user?.refresh_policy||{})
 const [portfolioMomentum,setPortfolioMomentum]=useState({})
 const [portfolioMomentumJob,setPortfolioMomentumJob]=useState({running:false,total:0,completed:0,failed:0})
 const holdingInfoSeqRef=useRef(0)
 const syncBusyRef=useRef(false)
 const buyingPowerBusyRef=useRef(false)
 const orderbookBusyRef=useRef(new Set())
 const embeddedPortfolioVisible=false
 const canPortfolioMomentum=false // v3.76.1: portfolio AI moved to the dedicated Portfolio page
 const tradingRefreshSeconds=Math.max(0,Number(refreshPolicy?.trading_seconds??30))

 const fetchPortfolioMomentum=async()=>{
  if(!canPortfolioMomentum)return {running:false}
  try{
   const r=await api.get('/api/trading/portfolio/outlook')
   const map={}
   ;(r.data?.items||[]).forEach(item=>{map[String(item.code||'')]=item})
   setPortfolioMomentum(map)
   setPortfolioMomentumJob(r.data?.job||{running:false})
   return r.data?.job||{running:false}
  }catch{
   return {running:false}
  }
 }

 const accountRenderSignature=data=>{
  if(!data)return ''

  try{
   return JSON.stringify({
    account_no:data.account_no||'',
    summary:data.summary||{},
    holdings:(data.holdings||[]).map(h=>({
     code:h.code||h.stock_code||'',
     name:h.name||'',
     quantity:Number(h.quantity||0),
     avg_price:Number(h.avg_price||0),
     current_price:Number(h.current_price||0),
     profit_loss:Number(h.profit_loss||0),
     return_rate:Number(h.return_rate||0),
     market:h.market||'',
     portfolio_category:h.portfolio_category||'',
     themes:h.themes||[],
     theme_fallback:h.theme_fallback||null
    })),
    orders:(data.orders||[]).map(o=>({
     order_no:o.order_no||'',
     code:o.code||'',
     name:o.name||'',
     side:o.side||'',
     order_qty:Number(o.order_qty||0),
     filled_qty:Number(o.filled_qty||0),
     price:Number(o.price||0),
     time:o.time||''
    }))
   })
  }catch{
   return ''
  }
 }

 const load=async(force=false,{silent=false}={})=>{
  if(syncBusyRef.current)return

  syncBusyRef.current=true

  // Automatic refresh is invisible to the user.
  if(!silent){
   setErr('')
   setLastAttempt(new Date())
   setSyncing(true)
  }

  try{
   const r=await api.get(
    `${tradingApiRoot}/portfolio`,
    {
     params:{force}
    }
   )

   const next=r.data

   setP(prev=>{
    if(
     silent
     && prev
     && accountRenderSignature(prev)
        ===accountRenderSignature(next)
    ){
     return prev
    }

    return next
   })

  }catch(e){
   // Keep the last good snapshot and retry later without flashing an error.
   if(!silent){
    setErr(
     publicUiText(e.response?.data?.detail)
     || (
      force
       ? `${tradingLabel} 계좌를 새로 불러오지 못했습니다.`
       : `${tradingLabel} 계좌 갱신 실패`
     )
    )
   }

  }finally{
   syncBusyRef.current=false

   if(!silent){
    setSyncing(false)
   }
  }
 }


const loadBuyingPower=async({silent=true}={})=>{
 if(buyingPowerBusyRef.current)return
 buyingPowerBusyRef.current=true
 try{
  const r=await api.get(`${tradingApiRoot}/buying-power`)
  setBuyingPowerLive(r.data)
 }catch(e){
  if(!silent){
   setBuyingPowerLive(prev=>prev||{available:false,error:true,message:publicUiText(e.response?.data?.detail)||'주문가능금액 조회 실패'})
  }
 }finally{
  buyingPowerBusyRef.current=false
 }
}

const loadHoldingMarketInfo=async code=>{
 if(!code)return
 const seq=++holdingInfoSeqRef.current
 setHoldingChartData([])
 setInvestorFlow(null)
 setHoldingChartLoading(true)
 setInvestorFlowLoading(true)

 api.get(`/api/stocks/${code}/chart/cached`)
  .then(r=>{
   if(seq===holdingInfoSeqRef.current)setHoldingChartData(r.data.chart||[])
  })
  .catch(()=>{
   if(seq===holdingInfoSeqRef.current)setHoldingChartData([])
  })
  .finally(()=>{
   if(seq===holdingInfoSeqRef.current)setHoldingChartLoading(false)
  })

 api.get(`/api/stocks/${code}/investor-flow`)
  .then(r=>{
   if(seq===holdingInfoSeqRef.current)setInvestorFlow(r.data)
  })
  .catch(()=>{
   if(seq===holdingInfoSeqRef.current)setInvestorFlow(null)
  })
  .finally(()=>{
   if(seq===holdingInfoSeqRef.current)setInvestorFlowLoading(false)
  })
}

const loadOrderbook=async(code,{silent=false}={})=>{
 if(!code)return
 const key=String(code)
 if(orderbookBusyRef.current.has(key))return
 orderbookBusyRef.current.add(key)

 if(!silent)setOrderbookLoading(true)

 try{
  const r=await api.get(
   `/api/stocks/${code}/orderbook`
  )

  setOrderbook({
   asks:r.data.asks||[],
   bids:r.data.bids||[],
   best_ask:r.data.best_ask||null,
   best_bid:r.data.best_bid||null,
   total_ask_quantity:r.data.total_ask_quantity||0,
   total_bid_quantity:r.data.total_bid_quantity||0
  })

 }catch{
  // Orderbook is supplemental. Keep the last valid book quietly.

 }finally{
  orderbookBusyRef.current.delete(key)
  if(!silent)setOrderbookLoading(false)
 }
}

const loadReservations=async({silent=true}={})=>{
 if(isLive){setReservations([]);return}
 try{
  const r=await api.get(
   '/api/trading/reservations'
  )

  setReservations(
   r.data.items||[]
  )

 }catch(e){
  if(!silent){
   await showMessage(
    publicUiText(e.response?.data?.detail)
    || '예약 목록을 불러오지 못했습니다.',
    '예약 조회 오류',
    'danger'
   )
  }
 }
}

const reservationReset=()=>{
 setReservationEditingId(null)
 setReservationForm({
  side:'buy',
  trigger_operator:'lte',
  trigger_price:currentPrice||'',
  quantity:1,
  order_type:'market',
  order_price:'',
  expires_at:''
 })
}

const saveReservation=async()=>{
 if(!selected?.code){
  await showMessage(
   '예약할 종목을 먼저 선택해주세요.',
   '종목 선택 필요',
   'warning'
  )
  return
 }

 const payload={
  stock_code:selected.code,
  side:reservationForm.side,
  trigger_operator:reservationForm.trigger_operator,
  trigger_price:Number(reservationForm.trigger_price||0),
  quantity:Number(reservationForm.quantity||0),
  order_type:reservationForm.order_type,
  order_price:
   reservationForm.order_type==='limit'
    ? Number(reservationForm.order_price||0)
    : null,
  exchange:'KRX',
  expires_at:
   reservationForm.expires_at
    ? reservationForm.expires_at
    : null
 }

 const conditionText=
  payload.trigger_operator==='lte'
   ? '이하'
   : '이상'

 if(!(await askConfirm(
  `${selected.name} ${payload.trigger_price.toLocaleString('ko-KR')}원 ${conditionText} 도달 시 ${payload.quantity}주 ${payload.side==='buy'?'매수':'매도'} 주문을 전송하도록 예약할까요?`,
  reservationEditingId?'예약 수정 확인':'가격감시 예약 등록',
  'warning'
 )))return

 setReservationBusy(true)

 try{
  const r=reservationEditingId
   ? await api.put(
      `/api/trading/reservations/${reservationEditingId}`,
      payload
     )
   : await api.post(
      '/api/trading/reservations',
      payload
     )

  await showMessage(
   r.data.message,
   reservationEditingId?'예약 수정':'예약 등록',
   'success'
  )

  reservationReset()
  setOrderHistoryTab('reservation')
  await loadReservations({silent:true})

 }catch(e){
  await showMessage(
   publicUiText(e.response?.data?.detail)
   || '예약 저장에 실패했습니다.',
   '예약 저장 실패',
   'danger'
  )

 }finally{
  setReservationBusy(false)
 }
}

const editReservation=async row=>{
 setOrderPanelTab('reservation')
 setOrderHistoryTab('reservation')
 setReservationEditingId(row.id)

 setReservationForm({
  side:row.side,
  trigger_operator:row.trigger_operator,
  trigger_price:row.trigger_price,
  quantity:row.quantity,
  order_type:row.order_type,
  order_price:row.order_price||'',
  expires_at:row.expires_at
   ? String(row.expires_at).slice(0,16)
   : ''
 })

 if(selected?.code!==row.stock_code){
  await selectStock({
   code:row.stock_code,
   name:row.stock_name||row.stock_code,
   market:'KRX',
   themes:[],
   theme_fallback:null
  })
 }
}

const cancelReservation=async row=>{
 if(!(await askConfirm(
  `${row.stock_name} 가격감시 예약을 취소할까요?`,
  '예약 취소',
  'danger'
 )))return

 try{
  const r=await api.post(
   `/api/trading/reservations/${row.id}/cancel`
  )

  await showMessage(
   r.data.message,
   '예약 취소',
   'success'
  )

  if(reservationEditingId===row.id){
   reservationReset()
  }

  await loadReservations({silent:true})

 }catch(e){
  await showMessage(
   publicUiText(e.response?.data?.detail)
   || '예약 취소에 실패했습니다.',
   '예약 취소 실패',
   'danger'
  )
 }
}

 const runSearch=async(value=searchQ)=>{
  const q=String(value||'').trim()
  if(!q){setResults([]);setSearchOpen(false);return}
  setSearching(true)
  try{
   const r=await api.get('/api/stocks/search',{params:{q,limit:12}})
   setResults(Array.isArray(r.data)?r.data:[])
   setSearchOpen(true)
  }catch{setResults([])}finally{setSearching(false)}
 }

 const selectStock=async stock=>{
  setSelected(stock);setSearchQ(stock.name);setSearchOpen(false)
  setForm(prev=>({...prev,stock_code:stock.code}));setQuoteLoading(true)
  try{
   const [chartRes,quoteRes]=await Promise.all([
    api.get(`/api/stocks/${stock.code}/chart`),
    api.get(`/api/stocks/${stock.code}/quote`)
   ])

   setChart(chartRes.data.chart||[])
   setQuote(quoteRes.data)

   const initialPrice=Number(
    quoteRes.data?.current_price
    || stock.price
    || 0
   )

   setReservationForm(prev=>({
    ...prev,
    trigger_price:
     reservationEditingId
      ? prev.trigger_price
      : initialPrice||'',
    order_price:
     reservationEditingId
      ? prev.order_price
      : ''
   }))

   loadOrderbook(
    stock.code,
    {silent:true}
   )
  }catch(e){
   setQuote(null)
   await showMessage(publicUiText(e.response?.data?.detail)||'실제 종목 시세 조회 실패','시세 조회 오류','danger')
  }finally{setQuoteLoading(false)}
 }

 const openOrderPage=async(holding,side=null)=>{
  let target=null

  if(holding?.code){
   target={
    code:holding.code,
    name:holding.name||holding.code,
    market:holding.market||'',
    price:holding.current_price||holding.price||0,
    themes:holding.themes||[],
    theme_fallback:holding.theme_fallback||null
   }
  }else if(selected?.code){
   target=selected
  }else{
   const firstHolding=liveHoldings
    .slice()
    .sort(
     (a,b)=>
      Number(b.evaluation_amount||0)
      - Number(a.evaluation_amount||0)
    )[0]

   target=firstHolding?.code
    ? {
       code:firstHolding.code,
       name:firstHolding.name||firstHolding.code,
       market:firstHolding.market||'',
       price:firstHolding.current_price||0,
       themes:firstHolding.themes||[],
       theme_fallback:firstHolding.theme_fallback||null
      }
    : {
       code:'005930',
       name:'삼성전자',
       market:'KOSPI',
       themes:[],
       theme_fallback:null
      }
  }

  if(side){
   setForm(prev=>({
    ...prev,
    side,
    quantity:side==='sell'&&holding?.quantity?Number(holding.quantity):Math.max(1,Number(prev.quantity||1))
   }))
   setOrderPanelTab('normal')
  }

  setOrderOpen(true)

  if(
   target?.code
   && String(selected?.code||'')
      !==String(target.code)
  ){
   await selectStock(target)
  }
 }

 useEffect(()=>{
  if(!orderOpen)return

  if(!selected?.code){
   selectStock({
    code:'005930',
    name:'삼성전자',
    market:'KOSPI',
    themes:[],
    theme_fallback:null
   })
  }

  if(!isLive)loadReservations({silent:true})

  const reservationTimer=setInterval(
   ()=>!isLive&&loadReservations({silent:true}),
   10000
  )

  return()=>clearInterval(
   reservationTimer
  )
 },[orderOpen,isLive])

 useEffect(()=>{
  if(!orderOpen||!selected?.code)return

  loadOrderbook(
   selected.code,
   {silent:true}
  )

  const timer=setInterval(
   ()=>{
    if(document.visibilityState==='visible'){
     loadOrderbook(
      selected.code,
      {silent:true}
     )
    }
   },
   5000
  )

  return()=>clearInterval(
   timer
  )
 },[orderOpen,selected?.code])



 useEffect(()=>{
  if(!intent?.code)return

  setForm(prev=>({
   ...prev,
   side:intent.side||'buy'
  }))
  setOrderOpen(true)

  selectStock({
   code:intent.code,
   name:intent.name||intent.code,
   market:intent.market||'',
   themes:intent.themes||[],
   theme_fallback:intent.theme_fallback||null
  })
 },[intent?.nonce])

 useEffect(()=>{
  load(false)
  api.get('/api/membership/refresh-policy').then(r=>setRefreshPolicy(r.data||{})).catch(()=>{})
 },[environment])

 useEffect(()=>{
  if(!p?.account_no)return
  loadBuyingPower({silent:false})
 },[p?.account_no])

 // 회원 등급별 관리자 설정 주기로 계좌 원장과 주문가능금액을 순차 갱신한다.
 // 실시간 가격은 WebSocket을 사용하므로 이 주기를 짧게 설정해도 가격 tick polling은 발생하지 않는다.
 useEffect(()=>{
  if(!p||tradingRefreshSeconds<=0)return
  let delayed=null
  const t=setInterval(()=>{
   if(document.visibilityState!=='visible')return
   load(false,{silent:true})
   delayed=setTimeout(()=>loadBuyingPower({silent:true}),1300)
  },Math.max(10,tradingRefreshSeconds)*1000)
  return()=>{clearInterval(t);if(delayed)clearTimeout(delayed)}
 },[Boolean(p),tradingRefreshSeconds])

 useEffect(()=>{
  const q=searchQ.trim()
  if(!q||selected?.name===q){if(!q)setResults([]);return}
  const t=setTimeout(()=>runSearch(q),180)
  return()=>clearTimeout(t)
 },[searchQ])

 const holdingCodes=useMemo(()=>(p?.holdings||[]).map(x=>String(x.code||x.stock_code||'')).filter(Boolean).sort().join(','),[p?.holdings])

 // PREMIUM / EVENT / ADMIN: 보유종목이 확인되면 별도 클릭 없이 AI 모멘텀 캐시를 준비한다.
 useEffect(()=>{
  if(!canPortfolioMomentum||!holdingCodes)return
  let stopped=false
  let timer=null
  const poll=async()=>{
   if(stopped)return
   const job=await fetchPortfolioMomentum()
   if(!stopped&&job?.running)timer=setTimeout(poll,2500)
  }
  ;(async()=>{
   try{await api.post('/api/trading/portfolio/outlook/start')}catch{}
   if(stopped)return
   timer=setTimeout(poll,250)
  })()
  return()=>{stopped=true;if(timer)clearTimeout(timer)}
 },[canPortfolioMomentum,holdingCodes])

 // 가격은 polling하지 않고 실제 Kiwoom 실시간 시세이 들어올 때마다 갱신한다.
 useEffect(()=>{
  if(!p)return
  let stopped=false,ws=null,reconnectTimer=null,reconnectCount=0
  const connect=()=>{
   if(stopped)return
   setLiveState(prev=>({...prev,state:'connecting',message:'실시간 시세 연결 중'}))
   ws=new WebSocket(websocketUrl(`/ws/trading/portfolio-live?environment=${isLive?'live':'mock'}`))
   ws.onopen=()=>{
    reconnectCount=0
    ws.send(JSON.stringify({type:'auth',token:localStorage.getItem('stocklog_token')}))
   }
   ws.onmessage=event=>{
    let packet
    try{packet=JSON.parse(event.data)}catch{return}
    if(packet.type==='status'){
     setLiveState({state:packet.state||'live',message:publicUiText(packet.message)||'실시간 시세 연결',subscribed:Number(packet.subscribed||0),truncated:Boolean(packet.truncated)})
     return
    }
    if(packet.type==='heartbeat'){setLastLiveAt(new Date());return}
    if(packet.type==='error'){
     setLiveState({state:'error',message:publicUiText(packet.message)||'실시간 연결 오류',subscribed:0})
     return
    }
    if(packet.type!=='tick_batch'||!Array.isArray(packet.ticks))return
    const now=new Date();setLastLiveAt(now)
    setLiveState(prev=>({...prev,state:'live',message:prev.subscribed?`실시간 시세 연결 / ${prev.subscribed}종목`:'실시간 시세 연결'}))
    setLiveQuotes(prev=>{
     const next={...prev}
     packet.ticks.forEach(t=>{if(t?.code)next[String(t.code)]={...next[String(t.code)],...t,received_at:packet.received_at||now.toISOString()}})
     return next
    })
    setLiveHistory(prev=>{
     const next={...prev}
     packet.ticks.forEach(t=>{
      const code=String(t?.code||''),price=Number(t?.current_price||0)
      if(!code||!Number.isFinite(price)||price<=0)return
      const old=next[code]||[],last=old[old.length-1]
      next[code]=(last===price?old:[...old,price]).slice(-36)
     })
     return next
    })
   }
   ws.onerror=()=>setLiveState(prev=>({...prev,state:'error',message:'실시간 시세 연결 확인 중'}))
   ws.onclose=()=>{
    if(stopped)return
    reconnectCount+=1
    const delay=Math.min(10000,1200*reconnectCount)
    setLiveState(prev=>({...prev,state:'reconnecting',message:`실시간 재연결 대기 / ${(delay/1000).toFixed(1)}초`}))
    reconnectTimer=setTimeout(connect,delay)
   }
  }
  connect()
  return()=>{stopped=true;if(reconnectTimer)clearTimeout(reconnectTimer);try{ws?.close()}catch{}}
 },[p?.account_no,holdingCodes,isLive])

 const liveHoldings=useMemo(()=>(p?.holdings||[]).map(h=>{
  const code=String(h.code||h.stock_code||''),tick=liveQuotes[code]
  const quantity=Number(h.quantity||0),avg=Number(h.avg_price||0)
  const snapshotCurrent=Number(h.current_price||0)
  const current=Number(tick?.current_price||snapshotCurrent||0)
  const purchase=Number(h.purchase_amount||0)||avg*quantity
  const snapshotEvaluation=Number(h.evaluation_amount||0)||snapshotCurrent*quantity
  const snapshotPnl=Number(h.profit_loss||0)
  const liveDelta=tick?(current-snapshotCurrent)*quantity:0
  // Keep Kiwoom's cost-adjusted account P/L as the base. Realtime quotes only
  // add the price movement since the last broker snapshot; they must not erase
  // commission/tax effects by rebuilding P/L as current*qty - avg*qty.
  const evaluation=snapshotEvaluation+liveDelta
  const pnl=snapshotPnl+liveDelta
  const returnRate=purchase?pnl/purchase*100:0
  const change=Number(tick?.change||0)
  const prevClose=Number(h.previous_close||0)
  const dayProfit=prevClose>0?(current-prevClose)*quantity:Number(h.day_profit||0)+liveDelta
  return {...h,code,quantity,avg_price:avg,snapshot_current_price:snapshotCurrent,current_price:current,purchase_amount:purchase,evaluation_amount:evaluation,profit_loss:pnl,return_rate:returnRate,change,change_rate:Number(tick?.change_rate||0),day_profit:dayProfit,live_value_delta:liveDelta,is_live:Boolean(tick)}
 }),[p?.holdings,liveQuotes])

 // API account totals are the source of truth. We never compute total assets
 // as `cash + holdings` in the browser because Kiwoom account cash/deposit
 // fields can include settlement amounts already represented by account assets.
 // Realtime 0B only applies the price delta since the latest account snapshot.
 const liveSummary=useMemo(()=>{
  const apiTotal=Number(p?.summary?.total_asset||0)
  const apiCash=Number(p?.summary?.cash||0)
  const apiBuyingPower=Number(
   buyingPowerLive?.available
    ? buyingPowerLive.amount
    : p?.summary?.buying_power||0
  )
  const buyingPowerAvailable=Boolean(
   buyingPowerLive?.available
   || p?.summary?.buying_power_available
  )
  const apiPurchase=Number(p?.summary?.purchase_amount||0)
  const apiEvaluation=Number(p?.summary?.evaluation_amount||0)
  const apiPnl=Number(p?.summary?.profit_loss||0)
  const holdingPurchase=liveHoldings.reduce((s,h)=>s+Number(h.purchase_amount||0),0)
  const holdingEvaluation=liveHoldings.reduce((s,h)=>s+Number(h.evaluation_amount||0),0)
  const liveDelta=liveHoldings.reduce((s,h)=>s+Number(h.live_value_delta||0),0)
  const purchase=apiPurchase||holdingPurchase
  const evaluation=apiEvaluation?apiEvaluation+liveDelta:holdingEvaluation
  const pnl=(apiPnl||apiPnl===0)?apiPnl+liveDelta:evaluation-purchase
  const returnRate=purchase?pnl/purchase*100:0
  // Never synthesize account total as cash + securities evaluation: unsettled
  // same-day buys can make that double-count capital. If Kiwoom did not expose
  // a total asset, show the securities value as an explicitly limited fallback.
  const totalAsset=apiTotal?apiTotal+liveDelta:evaluation
  const apiDayProfit=Number(p?.summary?.day_profit||0)
  const apiDayRate=Number(p?.summary?.day_return_rate||0)
  const dayProfit=p?.summary?.day_profit_basis==='kiwoom'?apiDayProfit+liveDelta:liveHoldings.reduce((s,h)=>s+Number(h.day_profit||0),0)
  const previous=evaluation-dayProfit,dayRate=p?.summary?.day_profit_basis==='kiwoom'&&Math.abs(liveDelta)<0.01?apiDayRate:(previous?dayProfit/previous*100:0)
  return {
   cash:apiCash,
   buying_power:apiBuyingPower,
   buying_power_available:buyingPowerAvailable,
   purchase_amount:purchase,
   evaluation_amount:evaluation,
   profit_loss:pnl,
   return_rate:returnRate,
   total_asset:totalAsset,
   api_total_asset:apiTotal,
   live_value_delta:liveDelta,
   day_profit:dayProfit,
   day_rate:dayRate
  }
 },[p?.summary,liveHoldings,buyingPowerLive])

 const categoryStats=useMemo(()=>{
  const groups=new Map()
  const totalEvaluation=liveHoldings.reduce(
   (sum,h)=>sum+Number(h.evaluation_amount||0),
   0
  )

  liveHoldings.forEach(h=>{
   const name=String(
    h.portfolio_category
    || h.sector
    || h.category
    || '기타'
   ).trim()||'기타'

   const row=groups.get(name)||{
    name,
    stock_count:0,
    purchase_amount:0,
    evaluation_amount:0,
    profit_loss:0
   }

   row.stock_count+=1
   row.purchase_amount+=Number(h.purchase_amount||0)
   row.evaluation_amount+=Number(h.evaluation_amount||0)
   row.profit_loss+=Number(h.profit_loss||0)
   groups.set(name,row)
  })

  return Array.from(groups.values())
   .map(row=>({
    ...row,
    weight:totalEvaluation
     ? row.evaluation_amount/totalEvaluation*100
     : 0,
    return_rate:row.purchase_amount
     ? row.profit_loss/row.purchase_amount*100
     : 0
   }))
   .sort((a,b)=>b.evaluation_amount-a.evaluation_amount)
 },[liveHoldings])

 const bestCategory=useMemo(()=>
  categoryStats.length
   ? [...categoryStats].sort((a,b)=>b.profit_loss-a.profit_loss)[0]
   : null,
  [categoryStats]
 )

 useEffect(()=>{
  if(!liveHoldings.length){setHoldingFocusCode('');return}
  if(!liveHoldings.some(h=>h.code===holdingFocusCode)){
   setHoldingFocusCode(liveHoldings[0].code)
  }
 },[holdingCodes,holdingFocusCode,liveHoldings.length])

 const order=async()=>{
  const confirmMessage=isLive
   ? `${selected?.name||form.stock_code} (${form.stock_code}) ${form.quantity}주 ${form.side==='buy'?'매수':'매도'} 주문을 실제 계좌로 전송할까요? 실제 자금이 움직이며 취소되지 않을 수 있습니다.`
   : `${selected?.name||form.stock_code} (${form.stock_code}) ${form.quantity}주 ${form.side==='buy'?'매수':'매도'} 주문을 모의투자 계좌로 전송할까요?`
  if(!(await askConfirm(confirmMessage,isLive?'실전주문 최종 확인':'모의주문 확인',isLive?'danger':'warning')))return
  setBusy(true)
  try{
   const r=await api.post(`${tradingApiRoot}/order`,{...form,quantity:Number(form.quantity),price:form.price?Number(form.price):null,...(isLive?{confirmation_text:'실전주문'}:{})})
   await showMessage(publicUiText(r.data.message),isLive?'실전 주문 접수':'주문 접수','success')
   // Avoid a post-order request burst on Kiwoom mock. Refresh sequentially.
   setTimeout(async()=>{
    await load(true,{silent:true})
    await new Promise(resolve=>setTimeout(resolve,1200))
    await loadBuyingPower({silent:true})
    if(selected?.code){
     await new Promise(resolve=>setTimeout(resolve,1200))
     await loadOrderbook(selected.code,{silent:true})
    }
   },1400)
  }catch(e){await showMessage(publicUiText(e.response?.data?.detail)||'주문 실패','주문 실패','danger')}finally{setBusy(false)}
 }

const selectedHolding=liveHoldings.find(x=>String(x.code||'')===String(selected?.code||'')),selectedTick=liveQuotes[String(selected?.code||'')]

const orderViewRows=(()=>{
 const merged=new Map()

 for(const raw of (p?.orders||[])){
  const orderNo=String(raw.order_no||'').trim()
  const code=String(raw.code||'').trim()
  const key=`${orderNo}::${code}`
  const orderQty=Math.max(0,Number(raw.order_qty||0))
  const filledQty=Math.max(0,Number(raw.filled_qty||0))
  const isOpenSource=String(raw.source_tr||'')==='ka10075'
  const calculatedRemaining=Math.max(orderQty-filledQty,0)

  const existing=merged.get(key)

  if(!existing){
   merged.set(key,{
    ...raw,
    order_qty:orderQty,
    filled_qty:filledQty,
    remaining_qty:isOpenSource?calculatedRemaining:0,
    has_open_order:isOpenSource,
    latest_time:String(raw.time||'')
   })
   continue
  }

  existing.order_qty=Math.max(
   Number(existing.order_qty||0),
   orderQty
  )

  existing.filled_qty=Math.max(
   Number(existing.filled_qty||0),
   filledQty
  )

  if(isOpenSource){
   existing.has_open_order=true
   existing.remaining_qty=calculatedRemaining
  }

  if(!existing.name&&raw.name)existing.name=raw.name
  if(!existing.side&&raw.side)existing.side=raw.side
  if(!existing.price&&raw.price)existing.price=raw.price

  const rawTime=String(raw.time||'')
  if(rawTime>String(existing.latest_time||'')){
   existing.latest_time=rawTime
   existing.time=raw.time
  }
 }

 return [...merged.values()]
  .map(row=>({
   ...row,
   remaining_qty:row.has_open_order
    ? Math.max(
       0,
       Number(
        row.remaining_qty
        ??Math.max(
         Number(row.order_qty||0)-Number(row.filled_qty||0),
         0
        )
       )
      )
    : 0
  }))
  .sort(
   (a,b)=>
    String(b.time||'').localeCompare(
     String(a.time||'')
    )
  )
})()

const pendingOrders=orderViewRows.filter(
 o=>Boolean(o.has_open_order)&&Number(o.remaining_qty||0)>0
)

const filledOrders=orderViewRows.filter(
 o=>!Boolean(o.has_open_order)&&Number(o.filled_qty||0)>0
)

 useEffect(()=>{
  const onFill=()=>{
   load(true,{silent:true}).catch(()=>{})
   setTimeout(()=>loadBuyingPower({silent:true}).catch(()=>{}),900)
  }
  window.addEventListener('stocklog:trade-filled',onFill)
  return()=>window.removeEventListener('stocklog:trade-filled',onFill)
 },[])

const selectedPendingQty=pendingOrders
 .filter(
  o=>String(o.code||'')===String(selected?.code||'')
 )
 .reduce(
  (sum,o)=>sum+Math.max(0,Number(o.remaining_qty||0)),
  0
 )

const focusedHolding=liveHoldings.find(h=>h.code===holdingFocusCode)||liveHoldings[0]||null
 const focusedMomentum=focusedHolding?portfolioMomentum[String(focusedHolding.code||'')]||null:null
 const focusedMomentumResult=focusedMomentum?.analysis||{}
 const focusedWeight=focusedHolding&&liveSummary.evaluation_amount?Number(focusedHolding.evaluation_amount||0)/Number(liveSummary.evaluation_amount||1)*100:0

 useEffect(()=>{
  if(!embeddedPortfolioVisible)return
  if(!focusedHolding?.code){
   setHoldingChartData([])
   setInvestorFlow(null)
   return
  }
  loadHoldingMarketInfo(focusedHolding.code)
 },[embeddedPortfolioVisible,focusedHolding?.code])
 const currentPrice=Number(selectedTick?.current_price||quote?.current_price||selected?.price||0)
 const bestAsk=Number(orderbook?.best_ask||0)
 const bestBid=Number(orderbook?.best_bid||0)
 const selectedChange=Number(selectedTick?.change??quote?.change??0),selectedChangeRate=Number(selectedTick?.change_rate??quote?.change_rate??0)
 const estimatePrice=form.order_type==='limit'?Number(form.price||0):currentPrice
 const estimatedAmount=Math.max(0,Number(form.quantity||0))*Math.max(0,estimatePrice)
 const approximateBuyable=(
  estimatePrice>0
  && liveSummary.buying_power_available
 )
  ? Math.max(
     0,
     Math.floor(
      Number(liveSummary.buying_power||0)
      / estimatePrice
     )
    )
  : 0
 const activeReservations=reservations.filter(r=>r.status==='active')
 const quoteUp=selectedChange>=0
 const liveConnected=liveState.state==='live'

 const applyQuantityRatio=ratio=>{
  const baseQty=
   form.side==='sell'
    ? Number(selectedHolding?.quantity||0)
    : approximateBuyable

  const qty=Math.floor(
   baseQty*ratio
  )

  setForm(prev=>({
   ...prev,
   quantity:Math.max(
    1,
    qty
   )
  }))
 }

 const selectTicketPrice=price=>{
  const value=Number(price||0)
  if(value<=0)return

  setForm(prev=>({
   ...prev,
   order_type:'limit',
   price:value
  }))
 }

 const selectReservationPrice=price=>{
  const value=Number(price||0)
  if(value<=0)return

  setReservationForm(prev=>({
   ...prev,
   trigger_price:value
  }))
 }

 return <>{syncing&&<PageDataLoadingStatus marketLabel="국내증권" pageLabel="증권투자(수동)" title={`${tradingLabel} 계좌를 업데이트하고 있어요`} detail="주문 화면을 유지하면서 잔고·보유종목·주문가능금액을 다시 확인합니다." steps={['주문 화면 유지','계좌 원장 확인','최신 잔고 반영']}/>}<div className="sync-page trading-dashboard">
  <div className={`page-head trading-page-head ${isLive?'live-trading-head':''}`}>
   <div><span>{isLive?'LIVE TRADING / MANUAL':'PAPER TRADING / MANUAL'}</span><h1>증권투자(수동)</h1><p>{isLive?'실제 계좌의 보유종목과 평가현황을 확인하고, 명시적으로 확인한 주문만 실전 서버에 전송합니다.':'모의투자 보유종목과 현재 평가현황을 확인하고, 가격 변화는 화면 새로고침 없이 반영됩니다.'}</p></div>
   <div className="trading-head-actions">
    <div className="live-update-stamp"><Activity size={14}/><span>실시간 업데이트</span><b>{lastLiveAt?lastLiveAt.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'대기 중'}</b></div>
    <button className="primary manual-order-launch" type="button" onClick={()=>openOrderPage(null)}><CircleDollarSign size={16}/>주식 주문</button>
    <button className="secondary" disabled={syncing} onClick={()=>load(true,{silent:false})}><RefreshCw size={16} className={syncing?'spin-icon':''}/>{syncing?'계좌 갱신 중...':'계좌 새로고침'}</button>
   </div>
  </div>

  {err&&<div className="error-box sync-error-box"><b>계좌 상태 확인</b><span>{err}</span>{lastAttempt&&<small>마지막 시도: {lastAttempt.toLocaleString()}</small>}</div>}
  {isLive&&<div className="live-trading-inline-warning"><AlertTriangle size={18}/><div><b>실전투자 화면</b><span>주문 버튼을 누르면 실제 계좌에 주문이 접수됩니다. 주문번호와 체결 상태를 키움에서도 확인해주세요.</span></div></div>}
  {p&&<>
   <section className="portfolio-hero">
    <div className="portfolio-hero-main">
     <div className="portfolio-account-label"><span>총 자산</span><small>계좌 {p.account_no||'-'}</small></div>
     <strong>{won(liveSummary.total_asset)}<em>원</em></strong>
     <div className="portfolio-total-source">
      <span>계좌 평가 기준</span>
      {liveSummary.live_value_delta!==0&&<em>실시간 시세 반영 {liveSummary.live_value_delta>=0?'+':''}{won(liveSummary.live_value_delta)}원</em>}
     </div>
     <div className="portfolio-hero-profit"><span>평가손익</span><b className={liveSummary.profit_loss>=0?'up':'down'}>{liveSummary.profit_loss>=0?'+':''}{won(liveSummary.profit_loss)}원</b><em className={liveSummary.return_rate>=0?'up':'down'}>{liveSummary.return_rate>=0?'+':''}{liveSummary.return_rate.toFixed(2)}%</em></div>
     <div className="portfolio-day-move"><span>오늘 보유종목 변동</span><b className={liveSummary.day_profit>=0?'up':'down'}>{liveSummary.day_profit>=0?'+':''}{won(liveSummary.day_profit)}원</b><small className={liveSummary.day_rate>=0?'up':'down'}>{liveSummary.day_rate>=0?'+':''}{liveSummary.day_rate.toFixed(2)}%</small></div>
    </div>
    <div className="portfolio-kpi-grid">
     <div className="buying-power-kpi">
      <span>주식 구매가능 금액</span>
      <b>{liveSummary.buying_power_available?`${won(liveSummary.buying_power)}원`:(buyingPowerLive?.error?'조회 실패':'조회 중...')}</b>
      <small>{buyingPowerLive?.stale?'최근 확인 금액':'현재 주문 가능 금액'}</small>
     </div>
     <div><span>매입금액</span><b>{won(liveSummary.purchase_amount)}원</b><small>현재 보유분 기준</small></div>
     <div><span>실시간 평가액</span><b>{won(liveSummary.evaluation_amount)}원</b><small>실시간 체결가 반영</small></div>
     <div><span>보유종목</span><b>{liveHoldings.length}종목</b><small>{liveHoldings.filter(x=>x.is_live).length}종목 실시간 수신</small></div>
    </div>
   </section>

   <section className="panel live-holdings-panel">
    <div className="section-title-row holdings-title-row">
     <div><span>LIVE HOLDINGS</span><h3>보유 종목</h3><p>현재가 체결 시 평가금액/손익/수익률이 즉시 바뀝니다.</p></div>
     <div className="holding-panel-actions">
      <div className="holding-panel-status calm-status"><Activity size={14}/><span>마지막 업데이트</span><b>{lastLiveAt?lastLiveAt.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'-'}</b></div>
      <button className="primary holdings-order-button" type="button" onClick={()=>openOrderPage(null)}><CircleDollarSign size={16}/>주식 주문</button>
     </div>
    </div>
{liveHoldings.length?
 <div className="holding-browser">
  <div className="holding-list-shell">
   <div className="holding-list-head">
    <span>종목</span><span>현재가</span><span>평가손익</span><span>수익률</span><span>주문</span>
   </div>
   <div className="holding-list">
    {liveHoldings.slice().sort((a,b)=>Number(b.evaluation_amount||0)-Number(a.evaluation_amount||0)).map((h,i)=>{
     const positive=Number(h.profit_loss||0)>=0
     const dayPositive=Number(h.change||0)>=0
     return <div
      className={`holding-list-row ${holdingFocusCode===h.code?'active':''}`}
      key={`${h.code}-${i}`}
     >
      <button type="button" className="holding-row-main" onClick={()=>setHoldingFocusCode(h.code)} aria-label={`${h.name||h.code} 상세 보기`}>
       <span className="holding-list-name">
        <b>{h.name||h.code}</b>
        <small>{h.code}{h.is_live?' / LIVE':''}</small>
        {canPortfolioMomentum&&portfolioMomentum[String(h.code||'')]?.ready&&<em className={`holding-ai-momentum-mini ${portfolioMomentum[String(h.code||'')]?.analysis?.view||'neutral'}`}>AI {portfolioMomentum[String(h.code||'')]?.analysis?.label||'모멘텀'}</em>}
       </span>
       <span className="holding-list-price">
        <b>{won(h.current_price)}원</b>
        <small className={dayPositive?'up':'down'}>{h.change_rate>=0?'+':''}{Number(h.change_rate||0).toFixed(2)}%</small>
       </span>
       <span className={`holding-list-pnl ${positive?'up':'down'}`}>
        <b>{h.profit_loss>=0?'+':''}{won(h.profit_loss)}원</b>
        <small>{won(h.evaluation_amount)}원 평가</small>
       </span>
       <span className={positive?'up':'down'}>
        <b>{h.return_rate>=0?'+':''}{Number(h.return_rate||0).toFixed(2)}%</b>
        <ChevronRight size={14}/>
       </span>
      </button>
      <button type="button" className="holding-quick-sell" onClick={()=>openOrderPage(h,'sell')}>매도</button>
     </div>
    })}
   </div>
  </div>

  {focusedHolding&&<div className="holding-detail-pane">
   <div className="holding-detail-head">
    <div>
     <span className="holding-name-row"><b>{focusedHolding.name||focusedHolding.code}</b>{focusedHolding.is_live&&<em>LIVE</em>}</span>
     <small>{focusedHolding.code}</small>
    </div>
    <div className="holding-detail-current">
     <strong>{won(focusedHolding.current_price)}원</strong>
     <span className={focusedHolding.change>=0?'up':'down'}>{focusedHolding.change>=0?'+':''}{won(focusedHolding.change)} / {focusedHolding.change_rate>=0?'+':''}{Number(focusedHolding.change_rate||0).toFixed(2)}%</span>
    </div>
   </div>

   <div className="holding-detail-chart">
    <div className="holding-chart-head"><span>가격 차트</span><small>{focusedHolding.is_live?'마지막 일봉 + 실시간 현재가':'저장된 마지막 실제 일봉'}</small></div>
    {holdingChartLoading&&!holdingChartData.length
     ? <div className="holding-chart-loading">차트 불러오는 중...</div>
     : <HoldingPriceChart data={holdingChartData} liveValues={liveHistory[focusedHolding.code]||[]} currentPrice={focusedHolding.current_price}/>}
   </div>

   <div className="holding-detail-profit">
    <span>평가손익</span>
    <strong className={focusedHolding.profit_loss>=0?'up':'down'}>{focusedHolding.profit_loss>=0?'+':''}{won(focusedHolding.profit_loss)}원</strong>
    <em className={focusedHolding.return_rate>=0?'up':'down'}>{focusedHolding.return_rate>=0?'+':''}{Number(focusedHolding.return_rate||0).toFixed(2)}%</em>
   </div>

   <div className="holding-detail-stats">
    <div><span>보유수량</span><b>{won(focusedHolding.quantity)}주</b></div>
    <div><span>평균단가</span><b>{won(focusedHolding.avg_price)}원</b></div>
    <div><span>매입금액</span><b>{won(focusedHolding.purchase_amount)}원</b></div>
    <div><span>평가금액</span><b>{won(focusedHolding.evaluation_amount)}원</b></div>
    <div><span>오늘 변동 손익</span><b className={focusedHolding.day_profit>=0?'up':'down'}>{focusedHolding.day_profit>=0?'+':''}{won(focusedHolding.day_profit)}원</b></div>
    <div><span>포트폴리오 비중</span><b>{focusedWeight.toFixed(1)}%</b></div>
   </div>

   {canPortfolioMomentum
    ? <div className={`holding-ai-momentum ${focusedMomentumResult?.view||'neutral'}`}>
       <div className="holding-ai-momentum-head">
        <div><span><Sparkles size={14}/> AI MOMENTUM</span><b>보유종목 자동 모멘텀 분석</b></div>
        {focusedMomentum?.ready?<em>{publicUiText(focusedMomentumResult?.label)||'관망'} / 분석 점수 {Number(focusedMomentumResult?.confidence||0)}점</em>:<em className="loading">{portfolioMomentumJob?.running?'분석 중':'분석 준비'}</em>}
       </div>
       {focusedMomentum?.ready
        ? <><p>{focusedMomentumResult?.summary||'최근 가격 흐름과 이동평균을 기준으로 모멘텀을 확인했습니다.'}</p>
          <div className="holding-ai-checkpoints">{(focusedMomentumResult?.checkpoints||[]).slice(0,3).map((x,i)=><span key={i}>{x}</span>)}</div>
          <small>{focusedMomentum?.generated_at?`최근 분석 ${new Date(focusedMomentum.generated_at).toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}`:'AI 자동 분석'}</small></>
        : <p>보유종목의 최근 시장 흐름을 분석하고 있습니다. 완료되면 자동으로 표시됩니다.</p>}
      </div>
    : <div className="holding-ai-momentum locked">
       <div className="holding-ai-momentum-head"><div><span><Crown size={14}/> PREMIUM</span><b>보유종목 AI 모멘텀</b></div><LockKeyhole size={17}/></div>
       <p>프리미엄 이상 회원은 보유종목의 최근 흐름을 StockLog AI Bot이 자동으로 살펴봅니다.</p>
      </div>}

   <div className="holding-investor-flow">
    <div className="holding-flow-head">
     <div><span>TODAY FLOW</span><b>오늘 투자자별 매매</b></div>
     <small>{investorFlow?.date?`${String(investorFlow.date).slice(4,6)}/${String(investorFlow.date).slice(6,8)} / 주`:'최근 확인 데이터'}</small>
    </div>
    {investorFlowLoading&&!investorFlow
     ? <div className="holding-flow-loading">투자자 수급 조회 중...</div>
     : investorFlow?.available
      ? <>
       <div className="holding-flow-primary">
        {[['외국인','foreign'],['기관','institution']].map(([label,key])=>{
         const row=investorFlow.categories?.[key]||{}
         const net=Number(row.net||0)
         return <div key={key}>
          <span>{label}</span>
          <strong className={net>=0?'up':'down'}>{net>=0?'+':''}{won(net)}주</strong>
          <small><em>매수 {won(row.buy)}주</em><em>매도 {won(row.sell)}주</em></small>
         </div>
        })}
       </div>
       <div className="holding-flow-detail">
        {[['금융투자','financial_investment'],['투신','investment_trust'],['연기금 등','pension_etc'],['보험','insurance'],['은행','bank'],['사모펀드','private_equity']].map(([label,key])=>{
         const row=investorFlow.categories?.[key]||{}
         const net=Number(row.net||0)
         return <div key={key}>
          <span>{label}</span>
          <b className={net>=0?'up':'down'}>{net>=0?'+':''}{won(net)}주</b>
          <small>매수 {won(row.buy)} / 매도 {won(row.sell)}</small>
         </div>
        })}
       </div>
      </>
      : <div className="holding-flow-loading">투자자별 매매 데이터를 확인하지 못했습니다.</div>}
   </div>

   <div className="holding-weight detail-weight">
    <div><span>포트폴리오 비중</span><b>{focusedWeight.toFixed(1)}%</b></div>
    <i><em style={{width:`${Math.min(100,Math.max(0,focusedWeight))}%`}}/></i>
   </div>
   <div className="holding-detail-order-actions">
    <button type="button" className="holding-detail-trade-button buy" onClick={()=>openOrderPage(focusedHolding,'buy')}><CircleDollarSign size={16}/>매수 주문</button>
    <button type="button" className="holding-detail-trade-button sell" onClick={()=>openOrderPage(focusedHolding,'sell')}><CircleDollarSign size={16}/>매도 주문</button>
   </div>
  </div>}
 </div>
 :<div className="empty portfolio-empty">{tradingLabel} 계좌에 현재 보유 중인 종목이 없습니다.</div>}
   </section>

   {categoryStats.length>0&&
    <section className="panel portfolio-category-panel">
     <div className="section-title-row">
      <div>
       <span>PORTFOLIO MIX</span>
       <h3>카테고리별 투자 비중 / 수익</h3>
       <p>각 종목의 실제 테마를 우선 사용하고, 테마가 없으면 업종 기준으로 한 종목당 하나의 대표 카테고리를 적용합니다.</p>
      </div>
      {bestCategory&&
       <div className={`category-best-summary ${bestCategory.profit_loss>=0?'up':'down'}`}>
        <small>현재 손익 1위</small>
        <b>{bestCategory.name}</b>
        <strong>{bestCategory.profit_loss>=0?'+':''}{won(bestCategory.profit_loss)}원</strong>
       </div>
      }
     </div>

     <div className="portfolio-category-layout">
      <div className="portfolio-category-chart-card">
       <PortfolioCategoryChart items={categoryStats}/>
      </div>

      <div className="portfolio-category-table-wrap">
       <div className="portfolio-category-table-head">
        <span>카테고리</span>
        <span>비중</span>
        <span>평가액</span>
        <span>손익</span>
        <span>수익률</span>
       </div>
       <div className="portfolio-category-rows">
        {categoryStats.map(row=>
         <div className="portfolio-category-row" key={row.name}>
          <span className="category-name-cell">
           <b>{row.name}</b>
           <small>{row.stock_count}종목</small>
          </span>
          <span>
           <b>{row.weight.toFixed(1)}%</b>
           <i><em style={{width:`${Math.min(100,Math.max(0,row.weight))}%`}}/></i>
          </span>
          <span>{won(row.evaluation_amount)}원</span>
          <span className={row.profit_loss>=0?'up':'down'}>{row.profit_loss>=0?'+':''}{won(row.profit_loss)}원</span>
          <span className={row.return_rate>=0?'up':'down'}>{row.return_rate>=0?'+':''}{row.return_rate.toFixed(2)}%</span>
         </div>
        )}
       </div>
      </div>
     </div>
    </section>
   }

{orderOpen&&
 <div
  className="order-page-overlay manual-order-page-embedded"
  role="region"
  aria-label="주식 주문"
 >
  <div className="order-page-shell pro-order-shell">
   <header className="order-page-header pro-order-header">
    <div className="pro-order-title">
     <span>{isLive?'LIVE TRADING':'PAPER TRADING'}</span>
     <h2>주식 주문</h2>
     <p>{isLive?'실전 현재가 / 10호가 / 일반주문 / 미체결 / 체결을 한 화면에서 확인합니다.':'현재가 / 10호가 / 일반주문 / 미체결 / 체결 / 가격감시 예약을 한 화면에서 관리합니다.'}</p>
    </div>

    <div className="pro-order-header-actions">
     <div className="live-update-stamp compact"><Activity size={13}/><span>업데이트</span><b>{lastLiveAt?lastLiveAt.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'대기 중'}</b></div>

    </div>
   </header>

   <div className="order-page-body pro-order-body">
    <section className="pro-stock-bar">
     <div className="broker-stock-search pro-stock-search">
      <div className="search broker-search-input">
       <Search size={17}/>
       <input
        value={searchQ}
        onChange={e=>{
         setSearchQ(e.target.value)
         setSelected(
          prev=>prev?.name===e.target.value
           ?prev
           :null
         )
         setQuote(null)
        }}
        onFocus={()=>results.length&&setSearchOpen(true)}
        placeholder="종목명 또는 종목코드 검색"
        autoComplete="off"
       />
       {searching&&<RefreshCw size={14} className="spin-icon"/>}
      </div>

      {searchOpen&&results.length>0&&
       <div className="broker-autocomplete">
        {results.map(r=>
         <button
          key={r.code}
          type="button"
          onMouseDown={e=>e.preventDefault()}
          onClick={()=>selectStock(r)}
         >
          <div>
           <span className="stock-title-line">
            <b>{r.name}</b>
            <StockThemeBadges
             themes={r.themes}
             fallback={r.theme_fallback}
             max={2}
             compact
            />
           </span>
           <small>{r.code} / {r.market}{r.sector?` / ${r.sector}`:''}</small>
          </div>
          <div className="autocomplete-price">
           <strong>{won(r.price)}원</strong>
           <span className={Number(r.change_rate)>=0?'up':'down'}>
            {pct(r.change_rate)}
           </span>
          </div>
         </button>
        )}
       </div>
      }
     </div>

     {selected
      ? <div className="pro-selected-quote">
         <div className="pro-selected-name">
          <b>{selected.name}</b>
          <span>{selected.code}{selected.market?` / ${selected.market}`:''}</span>
         </div>

         <div className={`pro-selected-price ${quoteUp?'up':'down'}`}>
          <strong>{won(currentPrice)}원</strong>
          <span>{selectedChange>=0?'+':''}{won(selectedChange)} / {selectedChangeRate>=0?'+':''}{selectedChangeRate.toFixed(2)}%</span>
         </div>

         <div className="pro-selected-holding">
          <span>실제 보유</span>
          <b>{selectedHolding?`${won(selectedHolding.quantity)}주`:'미보유'}</b>
          {selectedPendingQty>0&&
           <em>미체결 {won(selectedPendingQty)}주</em>
          }
         </div>
        </div>
      : <div className="pro-selected-placeholder">
         주문할 종목을 검색해주세요.
        </div>
     }
    </section>

    {!selected
     ? <div className="pro-order-empty">
        <Search size={30}/>
        <b>기본 종목을 불러오는 중입니다.</b>
        <span>현재가와 주문 정보를 자동으로 준비하고 있습니다.</span>
       </div>
     : <>
      <div className="pro-order-grid">
       <section className="panel pro-market-panel">
        <div className="pro-panel-title">
         <div>
          <span>MARKET</span>
          <h3>현재가 / 호가</h3>
         </div>
         <small>{selectedTick?'실시간 체결':'최근 실제 시세'}</small>
        </div>

        <div className="pro-market-stat-grid">
         <div><span>시가</span><b>{won(quote?.open)}</b></div>
         <div><span>고가</span><b className="up">{won(quote?.high)}</b></div>
         <div><span>저가</span><b className="down">{won(quote?.low)}</b></div>
         <div><span>전일</span><b>{won(quote?.previous_close)}</b></div>
         <div><span>거래량</span><b>{won(selectedTick?.volume||quote?.volume)}</b></div>
         <div><span>현재가</span><b>{won(currentPrice)}</b></div>
        </div>

        <div className="pro-orderbook">
         <div className="pro-orderbook-head">
          <span>잔량</span>
          <b>10호가</b>
          <span>잔량</span>
         </div>

         {orderbookLoading&&!orderbook?.asks?.length
          ? <div className="pro-orderbook-loading">호가 조회 중...</div>
          : <>
           <div className="pro-ask-list">
            {(orderbook.asks||[]).map(level=>
             <button
              type="button"
              key={`ask-${level.level}`}
              onClick={()=>selectTicketPrice(level.price)}
             >
              <span>{won(level.quantity)}</span>
              <b>{won(level.price)}</b>
              <em>매도 {level.level}</em>
             </button>
            )}
           </div>

           <div className="pro-orderbook-mid">
            <span>매도잔량 {won(orderbook.total_ask_quantity||0)}</span>
            <strong>{won(currentPrice)}원</strong>
            <span>매수잔량 {won(orderbook.total_bid_quantity||0)}</span>
           </div>

           <div className="pro-bid-list">
            {(orderbook.bids||[]).map(level=>
             <button
              type="button"
              key={`bid-${level.level}`}
              onClick={()=>selectTicketPrice(level.price)}
             >
              <span>{won(level.quantity)}</span>
              <b>{won(level.price)}</b>
              <em>매수 {level.level}</em>
             </button>
            )}
           </div>
          </>
         }
        </div>
       </section>

       <section className="panel pro-ticket-panel">
        <div className="pro-ticket-main-tabs">
         <button
          type="button"
          className={orderPanelTab==='normal'?'active':''}
          onClick={()=>setOrderPanelTab('normal')}
         >
          <CircleDollarSign size={15}/>
          일반 주문
         </button>
         {!isLive&&<button
          type="button"
          className={orderPanelTab==='reservation'?'active':''}
          onClick={()=>{
           setOrderPanelTab('reservation')
           if(!reservationEditingId){
            setReservationForm(prev=>({
             ...prev,
             side:form.side,
             trigger_operator:form.side==='buy'?'lte':'gte',
             trigger_price:prev.trigger_price||currentPrice||''
            }))
           }
          }}
         >
          <CalendarClock size={15}/>
          가격감시 예약
         </button>}
        </div>

        {orderPanelTab==='normal'
         ? <>
          <div className="pro-side-tabs">
           <button
            type="button"
            className={form.side==='buy'?'buy active':''}
            onClick={()=>setForm(prev=>({...prev,side:'buy'}))}
           >
            매수
           </button>
           <button
            type="button"
            className={form.side==='sell'?'sell active':''}
            onClick={()=>setForm(prev=>({...prev,side:'sell'}))}
           >
            매도
           </button>
          </div>

          <div className="pro-account-strip">
           <div>
            <span>주식 구매가능 금액</span>
            <b>
             {liveSummary.buying_power_available
              ? `${won(liveSummary.buying_power)}원`
              : (buyingPowerLive?.error?'조회 실패':'조회 중...')}
            </b>
           </div>
           <div>
            <span>실제 보유</span>
            <b>{won(selectedHolding?.quantity||0)}주</b>
           </div>
           <div>
            <span>현재가 기준 구매가능</span>
            <b>{form.side==='buy'?`${won(approximateBuyable)}주`:`${won(selectedHolding?.quantity||0)}주`}</b>
           </div>
          </div>

          <div className="pro-form-group">
           <label>주문 유형</label>
           <div className="pro-segment">
            <button
             type="button"
             className={form.order_type==='market'?'active':''}
             onClick={()=>setForm(prev=>({...prev,order_type:'market',price:''}))}
            >
             시장가
            </button>
            <button
             type="button"
             className={form.order_type==='limit'?'active':''}
             onClick={()=>setForm(prev=>({...prev,order_type:'limit',price:prev.price||currentPrice||''}))}
            >
             지정가
            </button>
           </div>
          </div>

          {form.order_type==='limit'&&
           <div className="pro-form-group">
            <label>주문 가격 <em className="pro-label-unit">KRW / 원</em></label>
            <div className="pro-price-input">
             <input
              type="number"
              min="0"
              value={form.price}
              onChange={e=>setForm(prev=>({...prev,price:e.target.value}))}
             />
             <span>원</span>
            </div>
            <div className="pro-price-shortcuts">
             <button type="button" disabled={!currentPrice} onClick={()=>selectTicketPrice(currentPrice)}><span>현재가</span><b>{currentPrice?`${won(currentPrice)}원`:'-'}</b></button>
             <button type="button" disabled={!bestAsk} onClick={()=>selectTicketPrice(bestAsk)}><span>최우선 매도호가</span><b>{bestAsk?`${won(bestAsk)}원`:'-'}</b></button>
             <button type="button" disabled={!bestBid} onClick={()=>selectTicketPrice(bestBid)}><span>최우선 매수호가</span><b>{bestBid?`${won(bestBid)}원`:'-'}</b></button>
            </div>
           </div>
          }

          <div className="pro-form-group">
           <label>주문 수량</label>
           <div className="pro-qty-input">
            <button
             type="button"
             onClick={()=>setForm(prev=>({...prev,quantity:Math.max(1,Number(prev.quantity||1)-1)}))}
            >
             −
            </button>
            <input
             type="number"
             min="1"
             value={form.quantity}
             onChange={e=>setForm(prev=>({...prev,quantity:e.target.value}))}
            />
            <button
             type="button"
             onClick={()=>setForm(prev=>({...prev,quantity:Number(prev.quantity||0)+1}))}
            >
             ＋
            </button>
           </div>

           <div className="pro-ratio-buttons">
            {[.1,.25,.5,1].map(ratio=>
             <button
              key={ratio}
              type="button"
              onClick={()=>applyQuantityRatio(ratio)}
             >
              {Math.round(ratio*100)}%
             </button>
            )}
           </div>
          </div>

          <div className="pro-order-preview">
           <div><span>기준 가격</span><b>{estimatePrice?`${won(estimatePrice)}원`:'시장가'}</b></div>
           <div><span>예상 주문금액</span><strong>{estimatedAmount?`${won(estimatedAmount)}원`:'체결가 기준'}</strong></div>
           <div><span>미체결</span><b>{won(selectedPendingQty)}주</b></div>
          </div>

          <button
           className={`pro-order-submit ${form.side}`}
           disabled={busy||quoteLoading||!form.stock_code}
           onClick={order}
          >
           {busy
            ? '주문 전송 중...'
            : `${selected.name} ${form.side==='buy'?'매수':'매도'} 주문`}
          </button>
         </>
         : <>
          <div className="reservation-explain">
           <CalendarClock size={18}/>
           <div>
            <b>StockLog 가격감시 예약</b>
            <span>설정한 가격 조건을 확인하고 충족되면 모의투자 주문을 1회 실행합니다.</span>
           </div>
          </div>

          <div className="pro-side-tabs">
           <button
            type="button"
            className={reservationForm.side==='buy'?'buy active':''}
            onClick={()=>setReservationForm(prev=>({...prev,side:'buy',trigger_operator:'lte'}))}
           >
            예약 매수
           </button>
           <button
            type="button"
            className={reservationForm.side==='sell'?'sell active':''}
            onClick={()=>setReservationForm(prev=>({...prev,side:'sell',trigger_operator:'gte'}))}
           >
            예약 매도
           </button>
          </div>

          <div className="reservation-condition-row">
           <div className="pro-form-group">
            <label>감시 조건</label>
            <select
             value={reservationForm.trigger_operator}
             onChange={e=>setReservationForm(prev=>({...prev,trigger_operator:e.target.value}))}
            >
             <option value="lte">가격 이하 도달 ≤</option>
             <option value="gte">가격 이상 도달 ≥</option>
            </select>
           </div>

           <div className="pro-form-group">
            <label>감시 가격</label>
            <div className="pro-price-input">
             <input
              type="number"
              min="1"
              value={reservationForm.trigger_price}
              onChange={e=>setReservationForm(prev=>({...prev,trigger_price:e.target.value}))}
             />
             <span>원</span>
            </div>
           </div>
          </div>

          <div className="pro-price-shortcuts reservation-shortcuts">
           <button type="button" disabled={!currentPrice} onClick={()=>selectReservationPrice(currentPrice)}><span>현재가</span><b>{currentPrice?`${won(currentPrice)}원`:'-'}</b></button>
           <button type="button" disabled={!bestAsk} onClick={()=>selectReservationPrice(bestAsk)}><span>최우선 매도호가</span><b>{bestAsk?`${won(bestAsk)}원`:'-'}</b></button>
           <button type="button" disabled={!bestBid} onClick={()=>selectReservationPrice(bestBid)}><span>최우선 매수호가</span><b>{bestBid?`${won(bestBid)}원`:'-'}</b></button>
          </div>

          <div className="pro-form-group">
           <label>예약 수량</label>
           <div className="pro-qty-input">
            <button
             type="button"
             onClick={()=>setReservationForm(prev=>({...prev,quantity:Math.max(1,Number(prev.quantity||1)-1)}))}
            >
             −
            </button>
            <input
             type="number"
             min="1"
             value={reservationForm.quantity}
             onChange={e=>setReservationForm(prev=>({...prev,quantity:e.target.value}))}
            />
            <button
             type="button"
             onClick={()=>setReservationForm(prev=>({...prev,quantity:Number(prev.quantity||0)+1}))}
            >
             ＋
            </button>
           </div>
          </div>

          <div className="pro-form-group">
           <label>조건 충족 후 주문</label>
           <div className="pro-segment">
            <button
             type="button"
             className={reservationForm.order_type==='market'?'active':''}
             onClick={()=>setReservationForm(prev=>({...prev,order_type:'market',order_price:''}))}
            >
             시장가
            </button>
            <button
             type="button"
             className={reservationForm.order_type==='limit'?'active':''}
             onClick={()=>setReservationForm(prev=>({...prev,order_type:'limit',order_price:prev.order_price||prev.trigger_price||currentPrice||''}))}
            >
             지정가
            </button>
           </div>
          </div>

          {reservationForm.order_type==='limit'&&
           <div className="pro-form-group">
            <label>실행 지정가</label>
            <div className="pro-price-input">
             <input
              type="number"
              min="1"
              value={reservationForm.order_price}
              onChange={e=>setReservationForm(prev=>({...prev,order_price:e.target.value}))}
             />
             <span>원</span>
            </div>
           </div>
          }

          <div className="pro-form-group">
           <label>유효기간</label>
           <input
            className="reservation-date-input"
            type="datetime-local"
            value={reservationForm.expires_at}
            onChange={e=>setReservationForm(prev=>({...prev,expires_at:e.target.value}))}
           />
           <small className="pro-field-help">비워두면 취소할 때까지 감시합니다. 정규장 09:00~15:30에만 조건을 실행합니다.</small>
          </div>

          <div className="reservation-preview">
           <span>{selected.name}</span>
           <b>
            {won(Number(reservationForm.trigger_price||0))}원
            {' '}
            {reservationForm.trigger_operator==='lte'?'이하':'이상'}
            {' '}
            → {reservationForm.side==='buy'?'매수':'매도'} {won(reservationForm.quantity)}주
           </b>
          </div>

          <div className="reservation-submit-row">
           {reservationEditingId&&
            <button
             type="button"
             className="secondary"
             onClick={reservationReset}
            >
             편집 취소
            </button>
           }
           <button
            type="button"
            className={`pro-order-submit ${reservationForm.side}`}
            disabled={reservationBusy}
            onClick={saveReservation}
           >
            {reservationBusy
             ? '저장 중...'
             : reservationEditingId
               ? '예약 수정 저장'
               : '가격감시 예약 등록'}
           </button>
          </div>
         </>
        }
       </section>

       <section className="panel pro-chart-panel">
        <div className="pro-panel-title">
         <div>
          <span>CHART</span>
          <h3>종목 차트</h3>
         </div>
         <small>{selectedTick?'현재가 실시간':'실제 일봉'}</small>
        </div>

        {chart.length
         ? <DetailedStockChart data={chart} compact/>
         : <div className="empty">차트 데이터를 불러오는 중입니다.</div>
        }
       </section>
      </div>

      <section className="panel pro-order-manager">
       <div className="pro-manager-tabs">
        <button
         type="button"
         className={orderHistoryTab==='pending'?'active':''}
         onClick={()=>setOrderHistoryTab('pending')}
        >
         미체결
         <b>{pendingOrders.length}</b>
        </button>
        <button
         type="button"
         className={orderHistoryTab==='filled'?'active':''}
         onClick={()=>setOrderHistoryTab('filled')}
        >
         체결
         <b>{filledOrders.length}</b>
        </button>
        {!isLive&&<button
         type="button"
         className={orderHistoryTab==='reservation'?'active':''}
         onClick={()=>setOrderHistoryTab('reservation')}
        >
         예약관리
         <b>{activeReservations.length}</b>
        </button>}

        <button
         type="button"
         className="pro-manager-refresh"
         disabled={syncing}
         onClick={()=>{
          load(true,{silent:false})
          if(!isLive)loadReservations({silent:true})
          loadOrderbook(selected.code,{silent:true})
         }}
        >
         <RefreshCw size={14}/>
         새로고침
        </button>
       </div>

       {orderHistoryTab==='pending'&&
        <div className="pro-order-table-wrap">
         {pendingOrders.length
          ? <div className="pro-order-table">
             <div className="pro-order-table-head">
              <span>구분</span>
              <span>종목</span>
              <span>주문수량</span>
              <span>체결</span>
              <span>미체결</span>
              <span>주문가격</span>
              <span>시간</span>
              <span>상태</span>
             </div>

             {pendingOrders.map((t,i)=>{
              const side=orderSideLabel(t.side)
              const orderQty=Math.max(0,Number(t.order_qty||0))
              const filledQty=Math.max(0,Number(t.filled_qty||0))
              const remainingQty=Math.max(0,Number(t.remaining_qty||0))

              return <div
               className="pro-order-table-row"
               key={`pending-${t.order_no||i}-${t.code||i}`}
              >
               <span><em className={`trade-side ${orderSideClass(t.side)}`}>{side}</em></span>
               <span className="pro-order-stock-cell"><b>{t.name||t.code||'종목'}</b><small>{t.code||'-'}</small></span>
               <span>{won(orderQty)}주</span>
               <span>{won(filledQty)}주</span>
               <span className="pending-value">{won(remainingQty)}주</span>
               <span>{Number(t.price||0)>0?`${won(t.price)}원`:'시장가'}</span>
               <span>{orderTimeText(t.time)}</span>
               <span><em className="order-status pending">미체결 / 보유 미반영</em></span>
              </div>
             })}
            </div>
          : <div className="pro-manager-empty">현재 미체결 주문이 없습니다.</div>
         }
        </div>
       }

       {orderHistoryTab==='filled'&&
        <div className="pro-order-table-wrap">
         {filledOrders.length
          ? <div className="pro-order-table">
             <div className="pro-order-table-head filled-head">
              <span>체결구분</span>
              <span>종목</span>
              <span>주문수량</span>
              <span>체결수량</span>
              <span>체결/주문가</span>
              <span>시간</span>
              <span>상태</span>
             </div>

             {filledOrders.map((t,i)=>{
              const side=orderSideLabel(t.side)
              return <div
               className="pro-order-table-row filled-row"
               key={`filled-${t.order_no||i}-${t.code||i}`}
              >
               <span><em className={`trade-side ${orderSideClass(t.side)}`}>{side} 체결</em></span>
               <span className="pro-order-stock-cell"><b>{t.name||t.code||'종목'}</b><small>{t.code||'-'}</small></span>
               <span>{won(t.order_qty)}주</span>
               <span>{won(t.filled_qty)}주</span>
               <span>{Number(t.price||0)>0?`${won(t.price)}원`:'시장가'}</span>
               <span>{orderTimeText(t.time)}</span>
               <span><em className="order-status filled">체결 완료</em></span>
              </div>
             })}
            </div>
          : <div className="pro-manager-empty">실제 체결 완료된 주문 내역이 없습니다.</div>
         }
        </div>
       }

       {!isLive&&orderHistoryTab==='reservation'&&
        <div className="reservation-manager">
         {reservations.length
          ? reservations.map(row=>
             <article
              className={`reservation-card ${reservationStatusClass(row.status)}`}
              key={row.id}
             >
              <div className="reservation-card-side">
               <em className={`trade-side ${row.side==='buy'?'buy':'sell'}`}>
                {row.side_label}
               </em>
               <div>
                <b>{row.stock_name||row.stock_code}</b>
                <small>{row.stock_code}</small>
               </div>
              </div>

              <div className="reservation-card-condition">
               <span>감시조건</span>
               <b>{won(row.trigger_price)}원 {row.trigger_operator==='lte'?'이하':'이상'}</b>
              </div>

              <div className="reservation-card-condition">
               <span>실행주문</span>
               <b>{row.order_type_label} / {won(row.quantity)}주</b>
              </div>

              <div className="reservation-card-condition">
               <span>최근 확인가</span>
               <b>{row.last_price?`${won(row.last_price)}원`:'대기'}</b>
              </div>

              <div className="reservation-card-status">
               <em className={reservationStatusClass(row.status)}>
                {row.status_label}
               </em>
               {row.expires_at&&<small>만료 {new Date(row.expires_at).toLocaleString()}</small>}
               {row.error_message&&<small className="error">{row.error_message}</small>}
              </div>

              <div className="reservation-card-actions">
               {row.status==='active'&&<>
                <button
                 type="button"
                 onClick={()=>editReservation(row)}
                >
                 <Edit3 size={13}/>
                 편집
                </button>
                <button
                 type="button"
                 className="danger"
                 onClick={()=>cancelReservation(row)}
                >
                 <Trash2 size={13}/>
                 취소
                </button>
               </>}
               {row.status==='triggered'&&
                <span className="reservation-order-number">
                 주문 전송 완료
                </span>
               }
              </div>
             </article>
            )
          : <div className="pro-manager-empty">
             등록된 가격감시 예약이 없습니다.
            </div>
         }
        </div>
       }
      </section>
     </>
    }
   </div>
  </div>
 </div>
}

   <section className="panel account-status-panel">
    <div className="section-title-row"><div><span>ACCOUNT STATUS</span><h3>계좌 연결 상태</h3><p>실제 사용에 필요한 연결 상태만 간단하게 표시합니다.</p></div></div>
    <div className={`account-source-bar compact-source-bar ${isLive?'live-source-bar':'calm'}`}><div><small>{isLive?'실계좌':'모의계좌'}</small><b>{p?.account_no||'-'}</b></div><div><small>계좌 업데이트</small><b>{p?._meta?.last_success_at?new Date(p._meta.last_success_at).toLocaleString():'-'}</b></div><div><small>실시간 업데이트</small><b>{lastLiveAt?lastLiveAt.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'-'}</b></div></div>
   </section>
  </>}
 </div></>
}



function splitAutoAuditNarrative(value){
 const raw=String(value||'').replace(/\r/g,'').trim()
 if(!raw)return []
 const blocks=raw
  .replace(/[•▪◦]/g,'\n')
  .replace(/\s+[|]\s+/g,'\n')
  .split(/\n+/)
  .map(x=>x.trim())
  .filter(Boolean)
 const lines=[]
 blocks.forEach(block=>{
  const sentenceParts=block.split(/(?<=[.!?。])\s+(?=[가-힣A-Za-z0-9(])/).map(x=>x.trim()).filter(Boolean)
  ;(sentenceParts.length?sentenceParts:[block]).forEach(part=>{
   if(/\s[·/]\s/.test(part)){
    part.split(/\s[·/]\s/).map(x=>x.trim()).filter(Boolean).forEach(x=>lines.push(x))
   }else if(part.length>110&&part.includes(',')){
    const commaParts=part.split(/,\s*/).map(x=>x.trim()).filter(Boolean)
    commaParts.forEach((x,index)=>lines.push(index<commaParts.length-1?`${x},`:x))
   }else lines.push(part)
  })
 })
 return lines.slice(0,14)
}

function AutoAuditNarrative({text,fallback='상세 판단 이유가 기록되지 않았습니다.',guard=false}){
 const lines=splitAutoAuditNarrative(text||fallback)
 return <div className={`auto-audit-narrative ${guard?'guard':''}`}>
  {lines.map((line,index)=><p key={`${index}-${line.slice(0,18)}`}><span>{line}</span></p>)}
 </div>
}


function AutoTradeHistoryDetail({row,onClose}){
 useEffect(()=>{
  const before=document.body.style.overflow
  document.body.style.overflow='hidden'
  const key=e=>{if(e.key==='Escape')onClose?.()}
  window.addEventListener('keydown',key)
  return()=>{document.body.style.overflow=before;window.removeEventListener('keydown',key)}
 },[onClose])
 if(!row)return null
 const statusMap={filled:'체결 완료',partial:'부분체결',accepted:'주문접수',submitting:'주문전송 중',blocked:'안전장치 차단 · 주문 없음',order_failed:'주문실패',hold:'관망',decision:'판단'}
 const orderAttempted=Boolean(row.order_attempted)
 const decisionSource=row.decision_source==='risk_guard'?'risk_guard':'gbot'
 const isRiskGuard=decisionSource==='risk_guard'
 const sideLabel=!orderAttempted&&row.status==='blocked'?(row.action==='buy'?'매수 판단':row.action==='sell'?'매도 판단':'관망'):row.action==='buy'?'매수':row.action==='sell'?'매도':'관망'
 const time=v=>v?new Date(v).toLocaleString('ko-KR',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}):'-'
 const amount=Number(row.filled_amount||0)>0?Number(row.filled_amount):Number(row.requested_amount||0)
 return createPortal(<div className="auto-audit-detail-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose?.()}}>
  <section className={`auto-audit-detail-shell ${row.portfolio_context?'portfolio-ai-execution-detail':''}`} role="dialog" aria-modal="true" aria-label={`${row.name||row.code} 자동매매 상세`}>
   <header className="auto-audit-detail-head">
    <div className="auto-audit-detail-title">
     <span className={`auto-action ${row.action}`}>{sideLabel}</span>
     <div><small>{isRiskGuard?'자동 안전규칙':orderAttempted?'AI 체결 사유':'AI 판단 사유'} · 기록 #{row.id}</small><h2>{row.name||row.code}</h2><p>{row.code} · {statusMap[row.status]||row.status}</p></div>
    </div>
    <button type="button" onClick={onClose} aria-label="상세 닫기"><X size={18}/></button>
   </header>

   <div className="auto-audit-detail-hero">
    <article><small>{row.filled_quantity>0?'실제 체결금액':'주문금액'}</small><b>{amount>0?`${won(amount)}원`:'-'}</b><span>{row.filled_quantity>0?'실제 체결 기준':'주문 기준'}</span></article>
    <article><small>수량</small><b>{won(row.filled_quantity||row.requested_quantity)}주</b><span>주문 {won(row.requested_quantity)}주</span></article>
    <article><small>{row.filled_quantity>0?'체결가격':'주문가격'}</small><b>{won(row.filled_price||row.requested_price)}원</b><span>{row.filled_quantity>0?'평균 체결가':'주문 기준가'}</span></article>
    <article><small>{isRiskGuard?'판단 출처':'Gbot 확신도'}</small><b>{isRiskGuard?'리스크 규칙':`${Number(row.confidence||0).toFixed(0)}점`}</b><span>{isRiskGuard?'사용자 손절·익절 설정 우선':'Gbot 판단'}</span></article>
   </div>

   {['buy','sell'].includes(row.action)&&<div className="auto-audit-timeline">
    <div className="done"><i><CheckCircle2 size={14}/></i><span><small>{isRiskGuard?'StockLog 리스크 규칙':'Gbot 판단'}</small><b>{time(row.decided_at)}</b></span></div>
    <div className={row.order_submitted_at?'done':row.status==='blocked'||row.status==='order_failed'?'blocked':''}><i>{row.order_submitted_at?<CheckCircle2 size={14}/>:<Clock3 size={14}/>}</i><span><small>{row.status==='blocked'&&!row.order_attempted?'주문 미전송':row.status==='order_failed'?'주문 전송 실패':'주문 접수'}</small><b>{row.order_submitted_at?time(row.order_submitted_at):row.status==='blocked'?'안전장치에서 주문을 차단했습니다.':row.status==='order_failed'?'주문 전송에 실패했습니다.':'미전송'}</b></span></div>
    <div className={row.filled_at?'done':row.status==='partial'?'active':''}><i>{row.filled_at?<CheckCircle2 size={14}/>:<Clock3 size={14}/>}</i><span><small>{row.status==='partial'?'부분 체결':'체결 완료'}</small><b>{row.filled_at?time(row.filled_at):row.order_submitted_at?'체결 대기':'-'}</b></span></div>
   </div>}

   <div className="auto-audit-detail-grid">
    <main>
     <section className="auto-audit-detail-section reason-card"><div className="auto-audit-section-title">{isRiskGuard?<ShieldCheck size={20}/>:<Sparkles size={20}/>}<div><small>{isRiskGuard?'규칙 실행 근거':'AI 판단 근거'}</small><h3>{isRiskGuard?'리스크 규칙 실행 사유':'AI 체결 사유'}</h3></div></div><AutoAuditNarrative text={row.reason}/></section>
     {(row.evidence||[]).length>0&&<section className="auto-audit-detail-section"><div className="auto-audit-section-title"><CheckCircle2 size={20}/><div><small>확인한 데이터</small><h3>핵심 근거</h3></div></div><ul className="auto-audit-detail-list evidence">{row.evidence.map((x,i)=><li key={i}>{x}</li>)}</ul></section>}
     {(row.risks||[]).length>0&&<section className="auto-audit-detail-section"><div className="auto-audit-section-title"><AlertTriangle size={20}/><div><small>주의해서 볼 내용</small><h3>위험 요인</h3></div></div><ul className="auto-audit-detail-list risk">{row.risks.map((x,i)=><li key={i}>{x}</li>)}</ul></section>}
     {row.exit_plan&&<section className="auto-audit-detail-section"><div className="auto-audit-section-title"><Compass size={20}/><div><small>다음 대응 기준</small><h3>재평가 · 청산 기준</h3></div></div><AutoAuditNarrative text={row.exit_plan}/></section>}
     {row.guard_message&&<section className={`auto-audit-detail-section auto-audit-guard-record ${row.status==='blocked'||row.status==='order_failed'?'blocked':''}`}><div className="auto-audit-section-title"><ShieldCheck size={20}/><div><small>StockLog 주문 보호</small><h3>{row.status==='blocked'&&!row.order_attempted?'안전장치 사전 차단 · 키움 주문 미전송':'주문 안전장치 기록'}</h3></div></div><AutoAuditNarrative text={row.guard_message} guard/></section>}
    </main>
    <div className="auto-audit-meta-column">
     <section className="auto-audit-meta-card"><h3>주문 정보</h3><dl><div><dt>주문수량</dt><dd>{won(row.requested_quantity)}주</dd></div><div><dt>주문가격</dt><dd>{won(row.requested_price)}원</dd></div><div><dt>주문금액</dt><dd>{won(row.requested_amount)}원</dd></div><div><dt>체결수량</dt><dd>{won(row.filled_quantity)}주</dd></div><div><dt>체결가격</dt><dd>{won(row.filled_price)}원</dd></div><div><dt>체결금액</dt><dd>{won(row.filled_amount)}원</dd></div></dl></section>
     <section className="auto-audit-meta-card"><h3>기록 정보</h3><dl><div><dt>판단 일시</dt><dd>{time(row.decided_at)}</dd></div><div><dt>주문 일시</dt><dd>{time(row.order_submitted_at)}</dd></div><div><dt>체결 일시</dt><dd>{time(row.filled_at)}</dd></div><div><dt>주문번호</dt><dd>{row.broker_order_no||'-'}</dd></div><div><dt>판단 출처</dt><dd>{isRiskGuard?'StockLog 안전 규칙':'StockLog Gbot'}</dd></div></dl></section>
    </div>
   </div>
  </section>
 </div>,document.body)
}

function AutoTradeHistoryWorkspace({
 open,onClose,detailOpen=false,isLive=false,mode,setMode,loading,data,page,pages,pageNumbers,setPage,
 onSelect,onDelete,onClear,
}){
 useEffect(()=>{
  if(!open)return
  const before=document.body.style.overflow
  document.body.style.overflow='hidden'
  const key=e=>{if(e.key==='Escape'&&!detailOpen)onClose?.()}
  window.addEventListener('keydown',key)
  return()=>{document.body.style.overflow=before;window.removeEventListener('keydown',key)}
 },[open,onClose,detailOpen])
 if(!open)return null
 const items=data?.items||[]
 const statusLabel={filled:'체결 완료',partial:'부분체결',accepted:'주문접수',submitting:'주문전송 중',blocked:'안전장치 차단',order_failed:'주문실패',hold:'관망',decision:'판단'}
 const filledCount=items.filter(x=>Number(x.filled_quantity||0)>0).length
 const blockedCount=items.filter(x=>x.status==='blocked'||x.status==='order_failed').length
 const latestTime=items[0]?.filled_at||items[0]?.order_submitted_at||items[0]?.decided_at
 return createPortal(<div className="auto-history-workspace-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose?.()}}>
  <section className="auto-history-workspace" role="dialog" aria-modal="true" aria-label={`${isLive?'실전':'모의'} 자동매매 이력`}>
   <header className="auto-history-workspace-head">
    <div className="auto-history-workspace-title"><span><Clock3 size={22}/></span><div><small>{isLive?'실전 자동매매':'모의 자동매매'}</small><h2>자동매매 이력</h2><p>주문·체결·안전장치 기록을 확인하고 종목을 눌러 AI 판단 근거를 자세히 볼 수 있습니다.</p></div></div>
    <button type="button" className="auto-history-workspace-close" onClick={onClose} aria-label="자동매매 이력 닫기"><X size={21}/></button>
   </header>

   <div className="auto-history-workspace-summary">
    <article><small>전체 기록</small><b>{Number(data?.total||0).toLocaleString()}건</b><span>{mode==='orders'?'실제 주문 기준':'전체 판단 기준'}</span></article>
    <article><small>현재 페이지 체결</small><b>{filledCount}건</b><span>체결 수량이 확인된 기록</span></article>
    <article><small>현재 페이지 보호 차단</small><b>{blockedCount}건</b><span>주문 전송 전 또는 전송 실패</span></article>
    <article><small>최근 기록</small><b>{latestTime?new Date(latestTime).toLocaleDateString('ko-KR',{month:'2-digit',day:'2-digit'}):'-'}</b><span>{latestTime?new Date(latestTime).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'}):'기록 없음'}</span></article>
   </div>

   <div className="auto-history-workspace-toolbar">
    <div className="auto-history-tabs" role="tablist"><button className={mode==='orders'?'active':''} onClick={()=>setMode?.('orders')}>실제 주문</button><button className={mode==='all'?'active':''} onClick={()=>setMode?.('all')}>전체 판단</button></div>
    <div><span>종목을 누르면 상세 사유가 열립니다.</span><button type="button" className="auto-history-clear" disabled={!Number(data?.total||0)} onClick={onClear}><Trash2 size={14}/>이력 정리</button></div>
   </div>

   <div className="auto-history-workspace-content">
    <div className="auto-history-column-head"><span>종목 · 판단 요약</span><span>상태</span><span>금액</span><span>수량 · 가격</span><span>확신도</span><span>최근 시각</span><span>상세</span></div>
    {loading&&<div className="auto-history-loading"><div className="sync-spinner small"/><span>자동매매 이력을 불러오는 중입니다.</span></div>}
    {!loading&&items.length>0&&<div className="auto-history-compact-list">{items.map(row=>{
     const actualAmount=Number(row.filled_amount||0)>0?Number(row.filled_amount):Number(row.requested_amount||0)
     const isBlocked=row.status==='blocked'||row.status==='order_failed'
     const orderAttempted=Boolean(row.order_attempted)
     const sideLabel=!orderAttempted&&row.status==='blocked'?(row.action==='buy'?'매수 판단':row.action==='sell'?'매도 판단':'관망'):row.action==='buy'?'매수':row.action==='sell'?'매도':'관망'
     const quantity=Number(row.filled_quantity||row.requested_quantity||0)
     const priceValue=Number(row.filled_price||row.requested_price||0)
     const recordedAt=row.filled_at||row.order_submitted_at||row.decided_at
     const isRiskGuard=row.decision_source==='risk_guard'
     return <article key={row.id} className={`auto-history-compact-row ${row.action} ${isBlocked?'blocked':''} ${isRiskGuard?'risk-guard':''}`} onClick={()=>onSelect?.(row)}>
      <div className="auto-history-compact-stock"><span className={`auto-action ${row.action}`}>{sideLabel}</span><div><b>{row.name}</b><small>{row.code} · 기록 #{row.id}</small><em>{row.reason||row.guard_message||'상세 판단 사유가 기록되지 않았습니다.'}</em></div></div>
      <div><span className={`auto-status-chip ${row.status}`}>{statusLabel[row.status]||row.status}</span></div>
      <div className="auto-history-compact-value"><strong>{actualAmount>0?`${won(actualAmount)}원`:row.action==='hold'?'관망':'-'}</strong><small>{row.filled_quantity>0?'실제 체결':'주문 기준'}</small></div>
      <div className="auto-history-compact-value"><strong>{quantity>0?`${won(quantity)}주`:'-'}</strong><small>{priceValue>0?`${won(priceValue)}원`:'가격 없음'}</small></div>
      <div className="auto-history-compact-confidence"><strong>{isRiskGuard?'규칙':Number(row.confidence||0).toFixed(0)}</strong><small>{isRiskGuard?'실행':'점'}</small></div>
      <div className="auto-history-compact-time"><strong>{recordedAt?new Date(recordedAt).toLocaleDateString('ko-KR',{month:'2-digit',day:'2-digit'}):'-'}</strong><small>{recordedAt?new Date(recordedAt).toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'}):'-'}</small></div>
      <div className="auto-history-row-actions"><button type="button" className="auto-history-detail-button" onClick={e=>{e.stopPropagation();onSelect?.(row)}}>{isRiskGuard?<ShieldCheck size={15}/>:<Sparkles size={15}/>} {isRiskGuard?'규칙 실행 사유':orderAttempted?'AI 체결 사유':'AI 판단 사유'}</button><button type="button" className="auto-history-delete-button" disabled={['accepted','partial','submitting'].includes(row.status)} onClick={e=>{e.stopPropagation();onDelete?.(row)}} title="이력 삭제"><Trash2 size={15}/></button></div>
     </article>
    })}</div>}
    {!loading&&!items.length&&<div className="auto-empty history"><Clock3 size={28}/><b>{mode==='orders'?'아직 실제 주문 이력이 없습니다.':'아직 자동 판단 이력이 없습니다.'}</b><span>{mode==='orders'?'안전장치에서 사전 차단된 판단은 실제 주문에 포함되지 않습니다.':'자동 판단이 실행되면 이곳에서 판단 근거까지 확인할 수 있습니다.'}</span></div>}
   </div>

   {!loading&&pages>1&&<div className="stocklog-pagination auto-history-pagination auto-history-workspace-pagination">
    <button disabled={page<=1} onClick={()=>setPage?.(1)}>처음</button><button disabled={page<=1} onClick={()=>setPage?.(Math.max(1,page-1))}>이전</button>
    {pageNumbers.map(n=><button key={n} className={n===page?'active':''} onClick={()=>setPage?.(n)}>{n}</button>)}
    <button disabled={page>=pages} onClick={()=>setPage?.(Math.min(pages,page+1))}>다음</button><button disabled={page>=pages} onClick={()=>setPage?.(pages)}>끝</button><small>{page} / {pages} 페이지</small>
   </div>}
  </section>
 </div>,document.body)
}

function AutoTradingSettingsPage({navigatePage,environment='mock'}){
 const isLive=environment==='live'
 const autoApiRoot=isLive?'/api/live-trading/auto':'/api/trading/auto'
 const [data,setData]=useState(null)
 const [options,setOptions]=useState({markets:['KOSPI','KOSDAQ'],categories:[],themes:[]})
 const [form,setForm]=useState(null)
 const [loading,setLoading]=useState(true)
 const [saving,setSaving]=useState(false)
 const [themeSearch,setThemeSearch]=useState('')
 const [configTab,setConfigTab]=useState('core')
 const [msg,setMsg]=useState('')

 useEffect(()=>{
  let alive=true
  setLoading(true)
  Promise.all([
   api.get(`${autoApiRoot}/status`),
   api.get(`${autoApiRoot}/options`).catch(()=>({data:{markets:['KOSPI','KOSDAQ'],categories:[],themes:[]}}))
  ]).then(([status,opts])=>{
   if(!alive)return
   setData(status.data||null)
   setForm(status.data?.settings||null)
   setOptions(opts.data||{})
  }).catch(e=>{if(alive)setMsg(publicUiText(e.response?.data?.detail)||'자동매매 설정을 불러오지 못했습니다.')})
   .finally(()=>{if(alive)setLoading(false)})
  return()=>{alive=false}
 },[environment])

 const update=(key,value)=>setForm(v=>({...v,[key]:value}))
 const toggleList=(key,value)=>setForm(v=>{
  const set=new Set(v?.[key]||[]);set.has(value)?set.delete(value):set.add(value)
  return {...v,[key]:[...set]}
 })
 const save=async()=>{
  if(!form)return
  setSaving(true);setMsg('')
  try{
   const payload={...form,enabled:undefined,last_cycle_at:undefined,next_cycle_at:undefined,last_error:undefined,last_message:undefined,updated_at:undefined}
   Object.keys(payload).forEach(k=>payload[k]===undefined&&delete payload[k])
   const r=await api.put(`${autoApiRoot}/settings`,payload)
   setForm(r.data?.settings||form)
   setMsg(r.data?.message||'자동매매 설정을 저장했습니다.')
   const status=await api.get(`${autoApiRoot}/status`).catch(()=>null)
   if(status?.data)setData(status.data)
  }catch(e){setMsg(publicUiText(e.response?.data?.detail)||'자동매매 설정 저장에 실패했습니다.')}
  finally{setSaving(false)}
 }
 if(!form)return <div className="sync-page auto-trading-page auto-v2 auto-settings-page">
  {loading&&<PageDataLoadingStatus marketLabel="국내증권" pageLabel="자동매매 설정" title="자동매매 설정을 불러오고 있어요" detail="설정 화면을 먼저 표시하고 저장된 예산·주기·안전 기준을 순서대로 반영합니다." steps={['설정 화면 표시','저장 기준 확인','입력값 반영']}/>} 
  <div className="page-head auto-settings-page-head"><div><span>{isLive?'실전 자동매매 설정':'모의 자동매매 설정'}</span><h1>증권투자(자동) 설정</h1><p>저장된 자동매매 기준을 확인하고 있습니다. 화면을 이동하거나 다른 메뉴를 사용할 수 있습니다.</p></div></div>
  {msg&&<div className="info auto-msg">{msg}</div>}
  <section className="panel auto-config-panel auto-config-v2 auto-config-standalone"><div className="auto-section-head auto-config-head"><div><span>내 자동매매 설정</span><h3>자동매매 기준</h3><p>저장된 설정이 확인되면 편집 항목이 이 화면에 자동으로 표시됩니다.</p></div></div></section>
 </div>

 const wholeNumberSuffixes=new Set(['원','억원','개','회','종목','주','점'])
 const readWholeNumber=value=>{const digits=String(value??'').replace(/[^0-9]/g,'').replace(/^0+(?=\d)/,'');return digits?Number(digits):0}
 const readDecimalNumber=value=>{const cleaned=String(value??'').replace(/[^0-9.]/g,'');const [head,...tail]=cleaned.split('.');const number=Number(`${head||'0'}${tail.length?`.${tail.join('')}`:''}`);return Number.isFinite(number)?number:0}
 const displayInputNumber=(value,whole=true)=>{const number=Number(value||0);if(!Number.isFinite(number))return '0';return whole?Math.max(0,Math.trunc(number)).toLocaleString('ko-KR'):String(Math.max(0,number))}
 const fieldNum=(key,label,suffix='',step='1',hint='')=>{
  const whole=wholeNumberSuffixes.has(suffix)&&!String(step).includes('.')
  const isMoney=suffix==='원'
  return <label className={`auto-field ${isMoney?'money-field':''}`}><span>{label}</span><div><input type="text" inputMode={whole?'numeric':'decimal'} value={displayInputNumber(form[key],whole)} onFocus={e=>e.currentTarget.select()} onChange={e=>update(key,whole?readWholeNumber(e.target.value):readDecimalNumber(e.target.value))}/>{suffix&&<em>{suffix}</em>}</div>{hint&&<small>{hint}</small>}</label>
 }
 const visibleThemes=(options.themes||[]).filter(x=>!themeSearch||String(x).toLowerCase().includes(themeSearch.toLowerCase())).slice(0,80)
 const selectedMarkets=(form.markets||[]).length?(form.markets||[]).join(' · '):'선택 없음'
 const selectedThemes=form.use_all_themes?'모든 테마':(form.themes||[]).length?`${(form.themes||[]).length}개 테마`:'선택한 테마 없음'
 const sellRules=[Number(form.stop_loss_pct||0)>0?`${Number(form.stop_loss_pct)}% 떨어지면 팔기`:null,Number(form.take_profit_pct||0)>0?`${Number(form.take_profit_pct)}% 오르면 팔기`:null].filter(Boolean)
 const sellRuleText=sellRules.length?sellRules.join(' · '):'정해둔 가격 없이 Gbot이 판단'

 return <div className="sync-page auto-trading-page auto-v2 auto-settings-page">
  <div className="page-head auto-settings-page-head">
   <div><span>{isLive?'GBOT LIVE AUTO SETTINGS':'GBOT AUTO SETTINGS'}</span><h1>증권투자(자동) 설정</h1><p>{isLive?'실제 계좌에 적용할 예산·주기·대상 종목·주문 안전장치를 별도로 관리합니다.':'자동 운용 화면과 설정을 분리했습니다. 예산·주기·대상 종목·매도 안전장치를 이 페이지에서만 관리합니다.'}</p></div>
   <div className="auto-settings-page-actions"><button type="button" className="secondary" onClick={()=>navigatePage?.('trading-auto',{environment})}><ChevronRight className="auto-back-chevron" size={15}/>자동매매로 돌아가기</button><button type="button" className={isLive?'danger-live-button':'primary'} disabled={saving} onClick={save}>{saving?'저장 중...':'설정 저장'}</button></div>
  </div>
  {msg&&<div className="info auto-msg">{msg}</div>}
  {data?.settings?.enabled&&<div className="auto-settings-running-note"><Activity size={16}/><div><b>현재 자동 운용이 켜져 있습니다.</b><span>저장한 새 설정은 다음 자동 판단부터 적용됩니다. 이미 접수된 주문에는 영향을 주지 않습니다.</span></div></div>}
  <section className="panel auto-config-panel auto-config-v2 auto-config-standalone">
   <div className="auto-section-head auto-config-head"><div><span>내 자동매매 설정</span><h3>자동매매 기준</h3><p>설정 화면에서는 운용 기준만 편집하고, 실행 상태·보유 감시는 자동매매 화면에서, 전체 이력은 별도 이력 화면에서 확인합니다.</p></div><button className="primary auto-save-btn" disabled={saving} onClick={save}>{saving?'저장 중...':'설정 저장'}</button></div>
   <div className="auto-config-summary">
    <div className="auto-config-summary-head"><div><span>한눈에 보기</span><b>현재 입력한 자동매매 설정</b></div><small>아래 값을 바꾸면 요약도 바로 바뀝니다.</small></div>
    <div className="auto-config-summary-grid">
     <article><small>쓸 수 있는 돈</small><b>{won(form.max_capital)}원</b><span>한 종목 최대 {won(form.max_position_amount)}원</span></article>
     <article><small>새 종목 찾기</small><b>{Number(form.interval_minutes||0)}분마다</b><span>{form.trading_start||'-'} ~ {form.trading_end||'-'}</span></article>
     <article><small>볼 시장 · 테마</small><b>{selectedMarkets}</b><span>{selectedThemes}</span></article>
     <article><small>최대 보유</small><b>{Number(form.max_positions||0)}종목</b><span>하루 주문 최대 {Number(form.max_daily_orders||0)}번</span></article>
     <article><small>살 때 기준</small><b>Gbot {Number(form.min_confidence||0)}점 이상</b><span>StockLog {Number(form.min_smart_score||0)}점 이상</span></article>
     <article><small>팔 때 기준</small><b>{sellRuleText}</b><span>{form.allow_sell_manual_holdings?'수동 보유도 자동판매 허용':'자동매매 보유만 자동판매'}</span></article>
    </div>
   </div>
   <div className="auto-config-tabs">
    <button className={configTab==='core'?'active':''} onClick={()=>setConfigTab('core')}><Gauge size={15}/><span>돈 · 시간</span></button>
    <button className={configTab==='universe'?'active':''} onClick={()=>setConfigTab('universe')}><SlidersHorizontal size={15}/><span>살 종목 고르기</span></button>
    <button className={configTab==='risk'?'active':''} onClick={()=>setConfigTab('risk')}><ShieldCheck size={15}/><span>팔기 · 안전</span></button>
   </div>
   {configTab==='core'&&<div className="auto-settings-stack">
    <div className="auto-settings-card"><div className="auto-settings-card-head"><div><b>언제 새 종목을 찾을까요?</b><span>신규 매수 후보를 검색하는 시간입니다. 기존 보유종목 감시는 별도로 계속됩니다.</span></div><Clock3 size={17}/></div><div className="auto-field-grid three"><label className="auto-field"><span>새 종목 찾는 간격</span><div><select value={form.interval_minutes} onChange={e=>update('interval_minutes',Number(e.target.value))}>{[5,10,15,20,30,45,60,120].map(n=><option key={n} value={n}>{n}분</option>)}</select></div></label><label className="auto-field"><span>시작할 시간</span><div><input type="time" value={form.trading_start||'09:05'} onChange={e=>update('trading_start',e.target.value)}/></div></label><label className="auto-field"><span>끝낼 시간</span><div><input type="time" value={form.trading_end||'15:15'} onChange={e=>update('trading_end',e.target.value)}/></div></label></div></div>
    <div className="auto-settings-card important"><div className="auto-settings-card-head"><div><b>자동매매에 얼마까지 쓸까요?</b><span>Gbot이 매수를 판단해도 아래 한도와 현금 안전장치를 넘을 수 없습니다.</span></div><CircleDollarSign size={17}/></div><div className="auto-field-grid three">{fieldNum('max_capital','자동매매 전체 예산','원','100000','자동매매가 모두 합쳐서 쓸 수 있는 가장 큰 금액')}{fieldNum('max_position_amount','한 종목에 쓸 최대 금액','원','100000','한 종목에 이 금액보다 많이 사지 않습니다')}{fieldNum('min_cash_ratio','계좌에 남겨둘 현금','%','1','이 비율만큼 현금으로 남겨둡니다')}{fieldNum('max_positions','최대 보유 종목','개','1')}{fieldNum('max_daily_orders','하루 주문 최대 횟수','회','1')}{fieldNum('max_new_buys_per_cycle','회차당 신규 매수','종목','1')}</div><div className="auto-sizing-rule"><Sparkles size={15}/><div><b>Gbot 점수가 높을수록 주문 비중을 높입니다.</b><span>79점 이하 25% · 80~84점 50% · 85~89점 75% · 90점 이상 100%</span><small>모든 안전 조건과 주문가능금액을 먼저 확인합니다.</small></div></div></div>
   </div>}
   {configTab==='universe'&&<div className="auto-settings-stack">
    <div className="auto-settings-card"><div className="auto-settings-card-head"><div><b>어떤 종목을 볼까요?</b><span>시장·가격·시가총액·거래량·StockLog 점수 범위를 정합니다.</span></div><SlidersHorizontal size={17}/></div><div className="auto-market-checks">{(options.markets||['KOSPI','KOSDAQ']).map(x=><label key={x}><input type="checkbox" checked={(form.markets||[]).includes(x)} onChange={()=>toggleList('markets',x)}/><span>{x}</span></label>)}</div><div className="auto-field-grid three">{fieldNum('min_price','최소 주가','원','100')}{fieldNum('max_price','최대 주가','원','100','0이면 상한 없음')}{fieldNum('min_market_cap','최소 시가총액','억원','100')}{fieldNum('max_market_cap','최대 시가총액','억원','100','0이면 상한 없음')}{fieldNum('min_avg_volume','20일 평균 거래량','주','1000')}{fieldNum('min_smart_score','StockLog 최소 점수','점','1')}{fieldNum('candidate_limit','Gbot 검토 후보 수','종목','1')}{fieldNum('min_confidence','Gbot 최소 확신도','점','1')}</div></div>
    <div className="auto-settings-card"><div className="auto-settings-card-head"><div><b>업종 고르기</b><span>선택하지 않으면 모든 업종을 대상으로 합니다.</span></div><Compass size={17}/></div><div className="auto-chip-list auto-chip-roomy">{(options.categories||[]).slice(0,80).map(x=><button type="button" key={x} className={(form.categories||[]).includes(x)?'active':''} onClick={()=>toggleList('categories',x)}>{x}</button>)}</div></div>
    <div className="auto-settings-card"><div className="auto-settings-card-head"><div><b>테마 고르기</b><span>전체 테마를 사용하거나 관심 테마만 선택할 수 있습니다.</span></div><label className="auto-all-theme"><input type="checkbox" checked={!!form.use_all_themes} onChange={e=>update('use_all_themes',e.target.checked)}/><span>전체 테마</span></label></div>{!form.use_all_themes?<><input className="auto-theme-search" value={themeSearch} onChange={e=>setThemeSearch(e.target.value)} placeholder="테마 검색"/><div className="auto-chip-list auto-chip-roomy theme-list">{visibleThemes.map(x=><button type="button" key={x} className={(form.themes||[]).includes(x)?'active':''} onClick={()=>toggleList('themes',x)}>{x}</button>)}</div>{(form.themes||[]).length>0&&<small className="auto-selected-note">선택 {(form.themes||[]).length}개 · {(form.themes||[]).slice(0,10).join(', ')}{(form.themes||[]).length>10?' 외':''}</small>}</>:<div className="auto-all-theme-empty"><CheckCircle2 size={18}/><div><b>전체 테마를 대상으로 합니다.</b><span>다른 필터 조건은 그대로 적용됩니다.</span></div></div>}</div>
   </div>}
   {configTab==='risk'&&<div className="auto-settings-stack"><div className="auto-settings-card"><div className="auto-settings-card-head"><div><b>언제 자동으로 팔까요?</b><span>0%로 두면 해당 가격 규칙은 사용하지 않고 Gbot 판단을 따릅니다.</span></div><ShieldCheck size={17}/></div><div className="auto-field-grid three">{fieldNum('stop_loss_pct','손절 기준','%','0.5','0이면 사용하지 않습니다')}{fieldNum('take_profit_pct','익절 기준','%','0.5','0이면 사용하지 않습니다')}</div></div><div className="auto-settings-card danger-card"><label className="auto-danger-check"><input type="checkbox" disabled={isLive} checked={isLive?false:!!form.allow_sell_manual_holdings} onChange={e=>update('allow_sell_manual_holdings',e.target.checked)}/><span><b>{isLive?'실전 직접 매수 보유분 자동매도 금지':'직접 매수한 보유종목도 Gbot 자동매도 허용'}</b><small>{isLive?'실전에서는 StockLog 자동매수로 확인된 수량만 자동매도할 수 있습니다.':'끄면 Gbot은 자동매매로 매수한 종목만 매도할 수 있습니다.'}</small></span></label></div><div className="auto-safety-summary"><ShieldCheck size={18}/><div><b>모든 주문 직전에 안전장치를 다시 확인합니다.</b><span>전체 예산·종목별 금액·현금 비율·보유 종목 수·일 주문 횟수·중복 주문 여부를 확인한 뒤 주문합니다.</span></div></div></div>}
   <div className="auto-config-footer auto-config-footer-v2"><span>설정을 저장하면 자동매매 메인 화면의 ‘현재 운용 기준’에 반영됩니다.</span><button className="primary" disabled={saving} onClick={save}>{saving?'저장 중...':'변경사항 저장'}</button></div>
  </section>
 </div>
}

function AutoTrading({user,navigatePage,environment='mock'}){
 const isLive=environment==='live'
 const autoApiRoot=isLive?'/api/live-trading/auto':'/api/trading/auto'
 const [data,setData]=useState(null)
 const [options,setOptions]=useState({markets:['KOSPI','KOSDAQ'],categories:[],themes:[]})
 const [form,setForm]=useState(null)
 const [loading,setLoading]=useState(true)
 const [saving,setSaving]=useState(false)
 const [busy,setBusy]=useState('')
 const [themeSearch,setThemeSearch]=useState('')
 const [historyMode,setHistoryMode]=useState('orders')
 const [historyPage,setHistoryPage]=useState(1)
 const [historyData,setHistoryData]=useState({items:[],page:1,pages:1,total:0,page_size:12})
 const [historyLoading,setHistoryLoading]=useState(false)
 const [configTab,setConfigTab]=useState('core')
 const [historyDetail,setHistoryDetail]=useState(null)
 const [historyOpen,setHistoryOpen]=useState(false)
 const [msg,setMsg]=useState('')
 const load=async({silent=false}={})=>{
  if(!silent)setLoading(true)
  try{
   const r=await api.get(`${autoApiRoot}/status`)
   setData(r.data)
   setForm(prev=>prev||r.data?.settings||null)
  }catch(e){if(!silent)setMsg(publicUiText(e.response?.data?.detail)||`${isLive?'실전':'모의'} 자동투자 상태를 불러오지 못했습니다.`)}
  finally{if(!silent)setLoading(false)}
 }
 const loadHistory=async({silent=false,page=historyPage,mode=historyMode}={})=>{
  if(!silent)setHistoryLoading(true)
  try{
   const r=await api.get(`${autoApiRoot}/history`,{params:{mode,page,page_size:12}})
   setHistoryData(r.data||{items:[],page:1,pages:1,total:0,page_size:12})
   if(Number(r.data?.page||1)!==Number(page))setHistoryPage(Number(r.data?.page||1))
  }catch(e){if(!silent)setMsg(publicUiText(e.response?.data?.detail)||'자동매매 이력을 불러오지 못했습니다.')}
  finally{if(!silent)setHistoryLoading(false)}
 }
 useEffect(()=>{
  load()
  api.get(`${autoApiRoot}/options`).then(r=>setOptions(r.data||{})).catch(()=>{})
 },[environment])
 useEffect(()=>{setHistoryPage(1)},[historyMode])
 useEffect(()=>{loadHistory({page:historyPage,mode:historyMode})},[historyMode,historyPage])
 useEffect(()=>{
  if(!historyDetail)return
  const fresh=(historyData?.items||[]).find(x=>Number(x.id)===Number(historyDetail.id))
  if(fresh)setHistoryDetail(fresh)
 },[historyData?.items])
 useEffect(()=>{
  if(!data?.settings?.enabled&&!data?.running&&!Number(data?.pending_order_count||0))return
  const t=setInterval(()=>{
   load({silent:true})
   loadHistory({silent:true,page:historyPage,mode:historyMode})
  },5000)
  return()=>clearInterval(t)
 },[data?.settings?.enabled,data?.running,data?.pending_order_count,historyMode,historyPage])
 useEffect(()=>{
  const onFill=()=>{
   load({silent:true})
   loadHistory({silent:true,page:historyPage,mode:historyMode})
  }
  window.addEventListener('stocklog:trade-filled',onFill)
  return()=>window.removeEventListener('stocklog:trade-filled',onFill)
 },[historyMode,historyPage])

 const update=(key,value)=>setForm(v=>({...v,[key]:value}))
 const toggleList=(key,value)=>setForm(v=>{
  const set=new Set(v?.[key]||[]);set.has(value)?set.delete(value):set.add(value)
  return {...v,[key]:[...set]}
 })
 const save=async()=>{
  setSaving(true);setMsg('')
  try{
   const payload={...form,enabled:undefined,last_cycle_at:undefined,next_cycle_at:undefined,last_error:undefined,last_message:undefined,updated_at:undefined}
   Object.keys(payload).forEach(k=>payload[k]===undefined&&delete payload[k])
   const r=await api.put(`${autoApiRoot}/settings`,payload)
   setForm(r.data?.settings||form);setMsg(r.data?.message||'설정을 저장했습니다.');await load({silent:true});return true
  }catch(e){setMsg(publicUiText(e.response?.data?.detail)||'자동매매 설정 저장에 실패했습니다.');return false}
  finally{setSaving(false)}
 }
 const start=async()=>{
  const startMessage=isLive?'현재 설정으로 실전 자동매매를 시작할까요? 조건을 통과하면 실제 계좌로 주문이 전송됩니다.':'현재 설정으로 StockLog Gbot 자동 모의투자를 시작할까요? 실제 증권계좌가 아닌 키움 모의투자 계좌에만 주문합니다.'
  if(!(await askConfirm(startMessage,isLive?'실전 자동매매 시작':'자동 모의투자 시작',isLive?'danger':'warning')))return
  setBusy('start');setMsg('')
  try{if(!(await save()))return;const r=await api.post(`${autoApiRoot}/start`,isLive?{confirmation_text:'실전자동매매 시작'}:undefined);setMsg(r.data?.message||'자동매매를 시작했습니다.');await load({silent:true})}
  catch(e){setMsg(publicUiText(e.response?.data?.detail)||'자동매매를 시작하지 못했습니다.')}
  finally{setBusy('')}
 }
 const stop=async()=>{
  if(!(await askConfirm(`${isLive?'실전':'모의'} 자동투자를 중지할까요? 이미 키움으로 전송된 주문은 그대로 유지됩니다.`,`${isLive?'실전':'모의'} 자동투자 중지`,'danger')))return
  setBusy('stop');setMsg('')
  try{const r=await api.post(`${autoApiRoot}/stop`);setMsg(r.data?.message||'자동매매를 중지했습니다.');await load({silent:true})}
  catch(e){setMsg(publicUiText(e.response?.data?.detail)||'자동매매 중지에 실패했습니다.')}
  finally{setBusy('')}
 }
 const runOnce=async()=>{
  if(isLive&&!(await askConfirm('Gbot이 판단한 주문이 안전 기준을 통과하면 실제 계좌로 전송됩니다. 실전 1회 판단을 시작할까요?','실전 자동판단 확인','danger')))return
  setBusy('run');setMsg('')
  try{const r=await api.post(`${autoApiRoot}/run-once`,isLive?{confirmation_text:'실전자동매매 시작'}:undefined);setMsg(r.data?.message||'Gbot 판단을 시작했습니다.');setTimeout(()=>{load({silent:true});loadHistory({silent:true,page:historyPage,mode:historyMode})},1200)}
  catch(e){setMsg(publicUiText(e.response?.data?.detail)||'1회 판단 시작에 실패했습니다.')}
  finally{setBusy('')}
 }
 const deleteHistoryRow=async row=>{
  if(!row?.id)return
  if(!(await askConfirm(`${row.name||row.code} 자동매매 이력을 삭제할까요?`, '이력 삭제','danger')))return
  try{await api.delete(`${autoApiRoot}/history/${row.id}`);if(Number(historyDetail?.id)===Number(row.id))setHistoryDetail(null);await loadHistory({page:historyPage,mode:historyMode});setMsg('자동매매 이력을 삭제했습니다.')}
  catch(e){setMsg(publicUiText(e.response?.data?.detail)||'이력을 삭제하지 못했습니다.')}
 }
 const clearHistory=async()=>{
  if(!(await askConfirm(`${historyMode==='orders'?'매수·매도':'전체 판단'} 종료 이력을 정리할까요? 진행 중인 주문은 삭제되지 않습니다.`, '이력 정리','danger')))return
  try{const r=await api.delete(`${autoApiRoot}/history`,{params:{mode:historyMode}});setHistoryDetail(null);setHistoryPage(1);setMsg(r.data?.message||'이력을 정리했습니다.');await loadHistory({page:1,mode:historyMode})}
  catch(e){setMsg(publicUiText(e.response?.data?.detail)||'이력을 정리하지 못했습니다.')}
 }
 const reviewLearning=async()=>{
  if(isLive){setMsg('실전 자동매매 학습 이력은 모의투자 학습 데이터와 분리되어 있습니다.');return}
  setBusy('learning');setMsg('')
  try{const r=await api.post('/api/trading/auto/learning/review-ready');setMsg(r.data?.message||'AI 사후분석을 요청했습니다.');setTimeout(()=>load({silent:true}),1200)}
  catch(e){setMsg(publicUiText(e.response?.data?.detail)||'AI 사후분석을 시작하지 못했습니다.')}
  finally{setBusy('')}
 }
 if(!form)return <div className="sync-page auto-trading-page auto-v2">
  {loading&&<PageDataLoadingStatus marketLabel="국내증권" pageLabel="증권투자(자동)" title={`${isLive?'실전':'모의'} 자동매매 상태를 확인하고 있어요`} detail="자동매매 화면을 먼저 표시하고 운용 상태·보유종목 감시·최근 판단을 순서대로 반영합니다." steps={['운용 화면 표시','Gbot 상태 확인','감시 결과 반영']}/>} 
  <div className={`page-head auto-page-head ${isLive?'live-trading-head':''}`}><div><span>{isLive?'실전 Gbot 자동 운용':'모의 Gbot 자동 운용'}</span><h1>증권투자(자동)</h1><p>저장된 자동매매 운용 상태를 확인하고 있습니다. 다른 메뉴와 화면은 계속 사용할 수 있습니다.</p></div></div>
  {msg&&<div className="info auto-msg">{msg}</div>}
  <section className="auto-control-center"><div className="auto-control-copy"><div className="auto-control-kicker"><span className="auto-live-dot"/><b>운용 상태 확인 중</b></div><h2>화면을 먼저 열고 Gbot 상태를 백그라운드에서 연결합니다.</h2></div></section>
 </div>
 const st=data?.settings||form
 const sm=data?.summary||{}
 const enabled=Boolean(st.enabled)
 const monitor=data?.monitoring||{}
 const monitored=monitor?.items||[]
 const monitorStatus=String(monitor?.status||(enabled?'waiting':'stopped'))
 const monitorLastSuccess=monitor?.last_success_at?new Date(monitor.last_success_at):null
 const monitorNextExpected=monitor?.next_expected_at?new Date(monitor.next_expected_at):null
 const monitorInterval=Math.max(30,Number(monitor?.interval_seconds||60))
 const monitorStatusLabel=monitor?.label||(enabled?'감시 기록 대기':'감시 중지')
 const autoPositionMap=new Map((data?.positions||[]).map(item=>[String(item.code||''),item]))
 const latestDecisionMap=new Map()
 ;(data?.decisions||[]).forEach(item=>{const code=String(item?.code||'');if(code&&!latestDecisionMap.has(code))latestDecisionMap.set(code,item)})
 const diag=data?.diagnostics||{}
 const todayDiag=diag?.today||{}
 const gbotIntegrity=diag?.gbot_integrity||{}
 const lastGbotDecision=gbotIntegrity?.last_decision||null
 const learning=data?.learning||{}
 const health=diag?.health||{}
 const historyPages=Math.max(1,Number(historyData?.pages||1))
 const historyCurrent=Math.max(1,Number(historyData?.page||historyPage||1))
 const historyPageNumbers=(()=>{
  const start=Math.max(1,Math.min(historyCurrent-2,historyPages-4))
  const end=Math.min(historyPages,start+4)
  return Array.from({length:Math.max(0,end-start+1)},(_,i)=>start+i)
 })()
 const visibleThemes=(options.themes||[]).filter(x=>!themeSearch||String(x).toLowerCase().includes(themeSearch.toLowerCase())).slice(0,80)
 const capitalUsedPct=Number(st.max_capital)>0?Math.min(100,Number(sm.auto_invested||0)/Number(st.max_capital)*100):0
 const remainingCapital=Math.max(0,Number(st.max_capital||0)-Number(sm.auto_invested||0))
 const reserveBase=Number(sm.account_value_reference||0)
 const reserveAmount=Number(sm.cash_reserve_amount||0)
 const wholeNumberSuffixes=new Set(['원','억원','개','회','종목','주','점'])
 const readWholeNumber=value=>{
  const digits=String(value??'').replace(/[^0-9]/g,'').replace(/^0+(?=\d)/,'')
  return digits?Number(digits):0
 }
 const readDecimalNumber=value=>{
  const cleaned=String(value??'').replace(/[^0-9.]/g,'')
  const [head,...tail]=cleaned.split('.')
  const normalized=`${head||'0'}${tail.length?`.${tail.join('')}`:''}`
  const number=Number(normalized)
  return Number.isFinite(number)?number:0
 }
 const displayInputNumber=(value,whole=true)=>{
  const number=Number(value||0)
  if(!Number.isFinite(number))return '0'
  return whole?Math.max(0,Math.trunc(number)).toLocaleString('ko-KR'):String(Math.max(0,number))
 }
 const fieldNum=(key,label,suffix='',step='1',hint='')=>{
  const whole=wholeNumberSuffixes.has(suffix)&&!String(step).includes('.')
  const isMoney=suffix==='원'
  return <label className={`auto-field ${isMoney?'money-field':''}`}><span>{label}</span><div><input type="text" inputMode={whole?'numeric':'decimal'} value={displayInputNumber(form[key],whole)} onFocus={e=>e.currentTarget.select()} onChange={e=>update(key,whole?readWholeNumber(e.target.value):readDecimalNumber(e.target.value))}/>{suffix&&<em>{suffix}</em>}</div>{hint&&<small>{hint}</small>}</label>
 }
 const selectedMarkets=(form.markets||[]).length?(form.markets||[]).join(' · '):'선택 없음'
 const selectedThemes=form.use_all_themes?'모든 테마':(form.themes||[]).length?`${(form.themes||[]).length}개 테마`:'선택한 테마 없음'
 const sellRules=[Number(form.stop_loss_pct||0)>0?`${Number(form.stop_loss_pct)}% 떨어지면 팔기`:null,Number(form.take_profit_pct||0)>0?`${Number(form.take_profit_pct)}% 오르면 팔기`:null].filter(Boolean)
 const sellRuleText=sellRules.length?sellRules.join(' · '):'정해둔 가격 없이 Gbot이 판단'
 const timeText=v=>v?new Date(v).toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'-'
 const rateLimited=/429|한도|rate|quota/i.test(String(st.last_error||''))
 const rateCooldown=Boolean(rateLimited&&st.next_cycle_at&&new Date(st.next_cycle_at).getTime()>Date.now())
 const nonExecutableGbotResponse=/유효한 JSON 객체를 찾지 못했습니다|보유종목 판단을 누락했습니다|Gbot 판단이 0건입니다|Gbot 응답 무결성 검사 실패|decisions 형식이 배열이 아닙니다/.test(String(st.last_error||''))
 const safeSkipMessage=nonExecutableGbotResponse
  ?'Gbot 응답이 주문 안전 기준을 완전히 충족하지 못해 이번 회차를 안전하게 건너뛰었습니다. 주문은 전송하지 않았으며 다음 회차에 자동으로 다시 판단합니다.'
  :(!st.last_error&&/안전하게 건너뛰|응답을 완결하지 못해 이번 회차|주문 안전 기준/.test(String(st.last_message||''))?String(st.last_message):'')
 const marketPhase=String(data?.market_phase||'closed')
 const returnTone=value=>Number(value)>0?'up':Number(value)<0?'down':'flat'
 const returnText=value=>{const number=Number(value||0);return `${number>0?'+':''}${number.toFixed(2)}%`}
 const dayReturnBasis=marketPhase==='preopen'?'장 시작 전':marketPhase==='open'?'전일 종가 대비':'마지막 장 가격 기준'
 return <>{(loading||historyLoading||['run','learning','start','stop'].includes(busy))&&<PageDataLoadingStatus marketLabel="국내증권" pageLabel="증권투자(자동)" title={historyLoading?'자동매매 이력을 업데이트하고 있어요':busy==='run'?'Gbot 1회 판단을 시작하고 있어요':busy==='learning'?'자동매매 사후학습을 확인하고 있어요':'자동매매 운용 상태를 업데이트하고 있어요'} detail="현재 운용 화면과 감시 정보는 유지하고 새 결과가 도착하면 자동으로 반영합니다." steps={['현재 운용 화면 유지','Gbot·계좌 상태 확인','최신 결과 반영']}/>} {historyOpen&&<AutoTradeHistoryWorkspace open={historyOpen} onClose={()=>setHistoryOpen(false)} detailOpen={!!historyDetail} isLive={isLive} mode={historyMode} setMode={setHistoryMode} loading={historyLoading} data={historyData} page={historyCurrent} pages={historyPages} pageNumbers={historyPageNumbers} setPage={setHistoryPage} onSelect={setHistoryDetail} onDelete={deleteHistoryRow} onClear={clearHistory}/>} {historyDetail&&<AutoTradeHistoryDetail row={historyDetail} onClose={()=>setHistoryDetail(null)}/>}<div className="sync-page auto-trading-page auto-v2">
  <div className={`page-head auto-page-head ${isLive?'live-trading-head':''}`}>
   <div><span>{isLive?'실전 Gbot 자동 운용':'모의 Gbot 자동 운용'}</span><h1>증권투자(자동)</h1><p>{isLive?'모의투자와 분리된 실계좌·한도·이력으로 Gbot을 운용합니다. 안전 기준을 통과한 주문은 실제 계좌에 전송됩니다.':'StockLog 데이터로 후보를 압축하고 Gbot이 판단합니다. 주문은 키움 모의투자 계좌에서만 실행됩니다.'}</p></div>
   <div className="auto-head-actions">
    <span className={`auto-engine-pill ${enabled?'on':'off'} ${rateCooldown?'waiting':''}`}><i/>{data?.running?'Gbot 판단 중':rateCooldown?'Gbot 한도 대기':enabled?'자동 운용 중':'자동 운용 중지'}</span>
    <button type="button" className="secondary auto-history-launch" onClick={()=>{setHistoryOpen(true);loadHistory({page:historyPage,mode:historyMode})}}><Clock3 size={15}/>자동매매 이력</button>
    <button type="button" className="secondary auto-settings-launch" onClick={()=>navigatePage?.('auto-settings',{environment})}><Settings size={15}/>자동매매 설정</button>
    <button className="secondary auto-refresh-btn" disabled={!!busy} onClick={()=>load()}><RefreshCw size={15}/>새로고침</button>
    {enabled?<button className="secondary danger-outline" disabled={!!busy} onClick={stop}>{busy==='stop'?'중지 중...':'거래 중지'}</button>:<button className={isLive?'danger-live-button':'primary'} disabled={!!busy} onClick={start}>{busy==='start'?'시작 중...':'거래 시작'}</button>}
   </div>
  </div>
  {isLive&&<div className="live-trading-inline-warning"><AlertTriangle size={18}/><div><b>실전 자동매매</b><span>실전 연결·주문 활성화·운용한도·현금비율·확신도·중복주문 검증을 모두 통과한 경우에만 실제 주문을 전송합니다.</span></div></div>}

  {msg&&<div className="info auto-msg">{msg}</div>}
  {sm.capital_limit_exceeded&&<div className="auto-limit-notice error"><div><AlertTriangle size={17}/><span><b>자동운용 한도 초과 감지 · 신규매수 차단</b><small>현재 Gbot 귀속 원금 {won(sm.capital_guard_committed)}원이 설정 한도 {won(st.max_capital)}원을 {won(sm.capital_limit_over_amount)}원 초과했습니다. 기존 보유를 임의로 매도하지 않고 신규 자동매수만 즉시 막습니다.</small></span></div></div>}
  {safeSkipMessage&&<div className="auto-limit-notice safe"><div><ShieldCheck size={17}/><span><b>이번 회차 안전 건너뜀 · 주문 없음</b><small>{safeSkipMessage}</small></span></div>{st.next_cycle_at&&<em>다음 판단 {timeText(st.next_cycle_at)}</em>}</div>}
  {st.last_error&&!nonExecutableGbotResponse&&<div className={`auto-limit-notice ${/429|한도|rate|quota/i.test(String(st.last_error||''))?'rate':'error'}`}><div><AlertTriangle size={17}/><span><b>{/429|한도|rate|quota/i.test(String(st.last_error||''))?'Gbot 호출 한도 대기':'최근 자동 판단 오류'}</b><small>{autoTradingErrorText(st.last_error)}</small></span></div>{st.next_cycle_at&&<em>다음 판단 {timeText(st.next_cycle_at)}</em>}</div>}

  <section className={`auto-control-center ${enabled?'running':''}`}>
   <div className="auto-control-copy">
    <div className="auto-control-kicker"><span className="auto-live-dot"/><b>{enabled?'Gbot 자동 운용':'자동 운용 중지'}</b></div>
    <h2>{data?.running?'StockLog 데이터를 읽고 다음 거래를 판단하고 있습니다.':enabled?'설정된 주기에 맞춰 다음 판단을 대기합니다.':'설정을 확인한 뒤 거래 시작을 눌러 자동 운용을 시작하세요.'}</h2>
    <div className="auto-control-meta"><span><Clock3 size={13}/>최근 판단 {timeText(st.last_cycle_at)}</span><span><CalendarClock size={13}/>다음 판단 {enabled?timeText(st.next_cycle_at):'-'}</span><span><ShieldCheck size={13}/>{isLive?'실전 주문 안전잠금':'모의 주문 전용'}</span></div>
   </div>
   <div className="auto-control-actions"><button className="auto-run-once" disabled={!!busy||data?.running||rateCooldown} onClick={runOnce}><Sparkles size={17}/><span>{busy==='run'?'Gbot 실행 중...':rateCooldown?'호출 한도 대기 중':'지금 1회 판단'}</span></button></div>
  </section>

  <section className="auto-overview-grid auto-overview-v2">
   <article><div className="auto-kpi-icon"><Gauge size={17}/></div><small>자동 운용 평가액</small><b>{won(sm.auto_evaluation)}원</b><span>한도판정 원금 {won(sm.capital_guard_committed??sm.auto_invested)}원</span></article>
   <article><div className="auto-kpi-icon"><TrendingUp size={17}/></div><small>자동 운용 손익</small><b className={Number(sm.auto_profit_loss)>=0?'up':'down'}>{Number(sm.auto_profit_loss)>=0?'+':''}{won(sm.auto_profit_loss)}원</b><span>Gbot 보유 {Number(sm.position_count||0)}종목</span></article>
   <article><div className="auto-kpi-icon"><CircleDollarSign size={17}/></div><small>자동운용 잔여 한도</small><b>{won(remainingCapital)}원</b><span>총 {won(st.max_capital)}원 중 {capitalUsedPct.toFixed(1)}% 사용</span><div className="auto-kpi-progress"><i style={{width:`${capitalUsedPct}%`}}/></div></article>
   <article><div className="auto-kpi-icon"><Landmark size={17}/></div><small>{sm.buying_power_available?'계좌 주문가능금액':'자동매매 사용 가능 현금'}</small><b>{won(sm.effective_order_cash??sm.buying_power??sm.account_cash)}원</b><span>현금보유 기준 {won(reserveAmount)}원 · 기준자산 {won(reserveBase)}원</span></article>
  </section>

  <details className={`panel auto-ops-details health-${health.level||'unknown'} gbot-${gbotIntegrity.level||'idle'}`}>
   <summary>
    <span className="auto-ops-summary-main"><span className="auto-ops-summary-icon"><Activity size={17}/></span><span><b>운용 상세</b><small>오늘 {Number(todayDiag.cycles||0)}회 실행 · 주문 {Number(todayDiag.order_total||0)}건 · Gbot {gbotIntegrity.label||'확인 중'}</small></span></span>
    <span className="auto-ops-summary-status"><i/><b>{health.label||'확인 중'}</b><ChevronRight size={17}/></span>
   </summary>
   <div className="auto-ops-details-body">
    <article className="auto-ops-card">
     <header><span><small>오늘 현황</small><b>{health.label||'확인 중'}</b></span><em>{Number(todayDiag.cycles||0)}회 실행</em></header>
     <p>{health.message||'오늘의 자동 판단과 주문 결과입니다.'}</p>
     <dl className="auto-ops-metrics"><div><dt>정상 · 오류</dt><dd>{Number(todayDiag.success||0)} · {Number(todayDiag.errors||0)}</dd></div><div><dt>후보 검토</dt><dd>{Number(todayDiag.candidate_total||0)}종목</dd></div><div><dt>Gbot 판단</dt><dd>{Number(todayDiag.decision_total||0)}건</dd></div><div><dt>실제 주문</dt><dd>{Number(todayDiag.order_total||0)}건</dd></div></dl>
     {diag.last_successful_cycle&&<footer>마지막 정상 {timeText(diag.last_successful_cycle.finished_at||diag.last_successful_cycle.started_at)} · 판단 {Number(diag.last_successful_cycle.decision_count||0)} · 주문 {Number(diag.last_successful_cycle.order_count||0)}</footer>}
    </article>
    <article className="auto-ops-card">
     <header><span><small>Gbot 상태</small><b>{gbotIntegrity.label||'확인 중'}</b></span><em>{gbotIntegrity.configured?'연결됨':'설정 필요'}</em></header>
     <p>{gbotIntegrity.message||'Gbot 연결과 최근 판단 상태입니다.'}</p>
     <dl className="auto-ops-metrics"><div><dt>최근 판단</dt><dd>{gbotIntegrity.last_gbot_at?timeText(gbotIntegrity.last_gbot_at):'기록 없음'}</dd></div><div><dt>주문 기준</dt><dd>{Number((gbotIntegrity.min_confidence??st.min_confidence)||0).toFixed(0)}점 이상</dd></div></dl>
     {lastGbotDecision&&<div className="auto-ops-last-decision"><span><small>최근 판단</small><b>{lastGbotDecision.name||lastGbotDecision.code} · {String(lastGbotDecision.action||'hold').toUpperCase()}</b></span><button type="button" className="secondary" onClick={()=>setHistoryDetail(lastGbotDecision)}><Sparkles size={13}/>판단 근거</button><p>{lastGbotDecision.reason||'판단 이유가 없습니다.'}</p></div>}
     <div className={`auto-ops-risk ${gbotIntegrity.risk_rule_override?'on':'off'}`}><ShieldCheck size={14}/><span>{gbotIntegrity.risk_rule_override?(gbotIntegrity.risk_rule_text||'손절·익절 가격 규칙 사용 중'):'강제 손절·익절 규칙 미사용'}</span></div>
    </article>
    <article className="auto-ops-card auto-ops-settings-card">
     <header><span><small>현재 적용 기준</small><b>자동매매 설정</b></span><button type="button" className="secondary" onClick={()=>navigatePage?.('auto-settings',{environment})}><Settings size={14}/>설정 열기</button></header>
     <dl className="auto-ops-settings"><div><dt>전체 예산</dt><dd>{won(st.max_capital)}원</dd></div><div><dt>종목당 최대</dt><dd>{won(st.max_position_amount)}원</dd></div><div><dt>현금 유지</dt><dd>{Number(st.min_cash_ratio||0).toFixed(0)}% · {won(reserveAmount)}원</dd></div><div><dt>Gbot 주문</dt><dd>{Number(st.min_confidence||0).toFixed(0)}점 이상</dd></div></dl>
    </article>
   </div>
  </details>

  <details className="panel auto-ops-details auto-learning-details">
   <summary>
    <span className="auto-ops-summary-main"><span className="auto-ops-summary-icon learning"><Sparkles size={17}/></span><span><b>사후학습</b><small>학습 {Number(learning.total_cases||0)}건 · 관찰 {Number(learning.observing||0)}건 · 분석 대기 {Number(learning.review_ready||0)}건</small></span></span>
    <span className="auto-ops-summary-status"><b>{Number(learning.review_ready||0)?`확인 ${Number(learning.review_ready||0)}건`:'대기 없음'}</b><ChevronRight size={17}/></span>
   </summary>
   <div className="auto-learning-details-body">
    <div className="auto-learning-compact-head"><p>손실 사례의 독립 반복 패턴만 다음 Gbot 판단에 반영합니다.</p><button className="secondary" disabled={!!busy||!Number(learning.review_ready||0)} onClick={reviewLearning}>{busy==='learning'?'분석 요청 중...':`사후분석 ${Number(learning.review_ready||0)}건`}</button></div>
    <div className="auto-diagnostic-grid learning">
     <article><small>학습 사례</small><b>{Number(learning.total_cases||0)}건</b><span>실제 자동매수만 기록</span></article>
     <article><small>관찰 중</small><b>{Number(learning.observing||0)}건</b><span>매수 후 성과 추적</span></article>
     <article><small>분석 대기</small><b>{Number(learning.review_ready||0)}건</b><span>손실 조건 충족</span></article>
     <article><small>재사용 가능</small><b>{Number(learning.actionable_cases||0)}건</b><span>반복 패턴만 반영</span></article>
    </div>
    {(learning.recurring_patterns||[]).length?<div className="auto-learning-patterns"><b>독립 반복 실패 패턴</b><div>{learning.recurring_patterns.map(x=><span key={x.tag}>{String(x.tag||'pattern').replaceAll('_',' ')} ×{Number(x.count||0)}{x.adjustment_ready?' · 확신도 보정':' · 관찰'}</span>)}</div></div>:<div className="auto-diagnostic-last"><b>아직 반복 실패 패턴이 없습니다.</b><span>한 번의 손실만으로 다음 종목을 자동 제외하지 않습니다.</span></div>}
    {(learning.recent_cases||[]).filter(x=>x.outcome_label==='loss'||x.status==='review_ready').slice(0,4).length>0&&<div className="auto-learning-cases">{learning.recent_cases.filter(x=>x.outcome_label==='loss'||x.status==='review_ready').slice(0,4).map(x=><article key={x.id}><div><b>{x.stock_name||x.stock_code}</b><span className={Number(x.realized_return_pct??x.current_return_pct)<0?'down':'up'}>{Number(x.realized_return_pct??x.current_return_pct)>=0?'+':''}{Number(x.realized_return_pct??x.current_return_pct??0).toFixed(2)}%</span></div><small>{x.status==='review_ready'?'AI 사후분석 대기':x.reviewed_at?'사후분석 완료':'관찰 중'} · 최대낙폭 {Number(x.max_drawdown_pct||0).toFixed(2)}%</small>{(x.reusable_failure_tags??x.failure_tags??[]).length>0&&<p>재사용 원인 · {(x.reusable_failure_tags??x.failure_tags??[]).join(', ')}</p>}{(x.lessons||[]).length>0&&<p>학습 · {x.lessons.slice(0,2).join(' · ')}</p>}{!(x.lessons||[]).length&&x.review_reason&&<p>{x.review_reason}</p>}</article>)}</div>}
    <div className="auto-learning-guard"><ShieldCheck size={15}/><span>{learning.guardrail||'정상 변동과 중복 사례를 제외하고, 독립 반복 패턴과 현재 데이터가 함께 일치할 때만 위험조정 확신도에 반영합니다.'}</span></div>
   </div>
  </details>

  <section className={`panel auto-monitor-panel monitor-${monitorStatus}`}>
   <div className="auto-monitor-head">
    <div><span>실제 감시 검증</span><h3>보유종목 자동 감시</h3><p>{monitor?.message||'키움 계좌 시세 확인 결과로 자동 감시가 실제 동작했는지 검증합니다.'}</p></div>
    <div className={`auto-monitor-count status-${monitorStatus}`}><i/><b>{monitorStatusLabel}</b><span>{monitored.length}종목</span></div>
   </div>
   <div className="auto-monitor-proof-grid">
    <article><small>마지막 성공 확인</small><b>{monitorLastSuccess?monitorLastSuccess.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'기록 없음'}</b><span>{monitorLastSuccess?`${Math.max(0,Math.floor(Number(monitor?.age_seconds||0)/60))}분 전`:'성공한 시세 확인 대기'}</span></article>
    <article><small>확인 주기</small><b>약 {monitorInterval}초</b><span>지연 판정 {Math.max(3,Math.round(Number(monitor?.stale_after_seconds||180)/60))}분</span></article>
    <article><small>실제 확인 범위</small><b>{Number(monitor?.checked_positions||0)} / {Number(monitor?.position_count??monitored.length)}종목</b><span>{monitor?.source||'키움 계좌 시세'}</span></article>
    <article><small>서버 시작 후 검증</small><b>{Number(monitor?.check_count||0)}회</b><span>{monitorNextExpected&&enabled?`다음 목표 ${monitorNextExpected.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`:'다음 확인 대기'}</span></article>
   </div>
   {monitor?.last_error&&monitorStatus==='error'&&<div className="auto-monitor-proof-error"><AlertTriangle size={15}/><span>{publicUiText(monitor.last_error)}</span></div>}
   {monitored.length?<div className="auto-monitor-table">
    <div className="auto-monitor-columns"><span>종목</span><span>Gbot 신호</span><span>매입가격</span><span>보유수량</span><span>수익률</span><span>금일 순익</span><span>총손익 (수수료반영)</span><span>실시간 감시</span><span>최근 확인</span></div>
    {monitored.map(item=>{
     const signal=String(item.signal||'HOLD').toUpperCase()
     const signalLabel={ADD:'추가매수',HOLD:'보유 유지',WATCH:'집중 감시',REDUCE:'비중 축소',SELL:'매도 신호'}[signal]||signal
     const checked=item.last_checked_at?new Date(item.last_checked_at):null
     const gbot=item.last_gbot_at?new Date(item.last_gbot_at):null
     const position=autoPositionMap.get(String(item.code||''))||{}
     const ret=Number(position.return_rate??item.return_rate??0)
     const dayRet=marketPhase==='preopen'?0:Number(position.day_return_rate??0)
     const currentPrice=Number(position.current_price??item.current_price??0)
     const netPnl=Number(position.profit_loss??item.profit_loss??0)
     const stopLoss=Math.max(0,Number(st.stop_loss_pct||0))
     const stopWarning=-Math.max(1,stopLoss*.8)
     const stopTrigger=-stopLoss
     const stopTriggerPrice=Number(item.risk_rule?.stop_trigger_price||(Number((position.avg_price??item.avg_price)||0)*(1-stopLoss/100)))
     const riskStatus=String(item.risk_rule?.status||(stopLoss>0&&ret<=stopTrigger?'stop_triggered':stopLoss>0&&ret<=stopWarning?'stop_approaching':'normal'))
     const stopTriggered=riskStatus==='stop_triggered'
     const stopApproaching=riskStatus==='stop_approaching'
     const latestDecision=latestDecisionMap.get(String(item.code||''))
     const latestSellBlock=latestDecision?.action==='sell'&&latestDecision?.status==='blocked'?String(latestDecision.guard_message||'주문 안전장치에서 차단됨'):''
     const tooltipId=`auto-monitor-detail-${String(item.code||'').replace(/[^a-zA-Z0-9_-]/g,'')}`
     return <article key={item.code} className={`auto-monitor-row signal-${signal.toLowerCase()}`}>
      <div className="auto-monitor-stock"><b>{item.name||item.code}</b><small>{item.code}</small></div>
      <div className="auto-monitor-signal"><span className={`auto-signal-light ${signal.toLowerCase()}`}><i/>{signal}</span><small>{signalLabel}{Number(item.confidence||0)>0?` · ${Number(item.confidence).toFixed(0)}점`:''}</small></div>
      <div className="auto-monitor-money"><b>{won(position.avg_price??item.avg_price)}원</b><small>평균 매입가</small></div>
      <div className="auto-monitor-money"><b>{Number(position.quantity??item.quantity??0).toLocaleString()}주</b><small>Gbot 보유</small></div>
      <div className={`auto-monitor-return ${returnTone(ret)}`}><b>{returnText(ret)}</b><small>현재 {won(currentPrice)}원</small></div>
      <div className={`auto-monitor-return auto-monitor-day-return ${returnTone(dayRet)}`}><b>{returnText(dayRet)}</b><small>{dayReturnBasis}</small></div>
      <div className={`auto-monitor-money auto-monitor-net-pnl ${returnTone(netPnl)}`}><b>{netPnl>0?'+':''}{won(netPnl)}원</b><small>수수료 반영 순손익</small></div>
      <div className={`auto-monitor-reason risk-${riskStatus}`}><AutoMonitorDetailTooltip id={tooltipId} content={<>
        <span className="auto-monitor-tooltip-head"><b>{stopTriggered?'손절 실행 조건 도달':stopApproaching?'손절 전 조기 경고':'실시간 감시 상세'}</b><em>{item.risk_rule?.price_source||'키움 계좌 현재가'}</em></span>
        <span className="auto-monitor-tooltip-grid"><span><small>현재 수익률</small><b className={returnTone(ret)}>{returnText(ret)}</b></span><span><small>접근 알림</small><b>{stopLoss>0?`${stopWarning.toFixed(2)}%`:'미사용'}</b></span><span><small>자동 손절</small><b>{stopLoss>0?`${stopTrigger.toFixed(2)}% 이하`:'미사용'}</b></span><span><small>손절 가격</small><b>{stopTriggerPrice>0?`${won(stopTriggerPrice)}원`:'-'}</b></span></span>
        <span className={`auto-monitor-tooltip-explain ${stopTriggered?'danger':stopApproaching?'warning':''}`}>{stopTriggered?'저장된 손절 기준에 도달했습니다. 강제 손절은 Gbot 점수와 일일 주문 횟수보다 우선하여 다음 리스크 판단에서 자동 보유수량 전량 매도를 시도합니다.':stopApproaching?`‘접근’은 실제 손절선의 80% 구간부터 보여주는 조기 경고입니다. 현재는 ${stopTrigger.toFixed(2)}% 실행선에 아직 도달하지 않아 자동매도하지 않습니다.`:'현재 저장된 손절 실행 범위에는 들어오지 않았습니다.'}</span>
        {latestSellBlock&&<span className="auto-monitor-tooltip-block"><b>직전 매도 미실행 사유</b><small>{latestSellBlock}</small></span>}
        <span className="auto-monitor-tooltip-foot">장중 키움 가격 확인 → 손절선 판정 → 주문 안전 확인 → 시장가 매도 순서로 처리됩니다.</span>
       </>}>
       <span className="auto-monitor-reason-title"><b>{item.reason||'첫 키움 시세 확인 대기'}</b><Info size={13}/></span>
       <small>{Number(item.drawdown_pct||0)<0?`감시 고점 대비 ${Number(item.drawdown_pct).toFixed(2)}% · `:''}{gbot?`Gbot ${gbot.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'})}`:'Gbot 재평가 준비'}</small>
      </AutoMonitorDetailTooltip></div>
      <div className={`auto-monitor-time verification-${item.verification_status||'waiting'}`}><b>{checked?checked.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'-'}</b><small>{{verified:'확인 완료',delayed:'확인 지연',waiting:'첫 확인 대기'}[item.verification_status]||(enabled?'확인 대기':'중지')}</small></div>
     </article>
    })}
   </div>:<div className="auto-monitor-empty"><Activity size={20}/><div><b>현재 Gbot 자동보유 종목이 없습니다.</b><span>자동 체결 종목이 생기면 이곳에서 HOLD · WATCH · REDUCE · SELL 신호를 계속 확인할 수 있습니다.</span></div></div>}
  </section>

 </div></>
}

function FlowSpark({series=[],field='foreign'}){
 const rows=Array.isArray(series)?series.slice(-7):[]
 const max=Math.max(1,...rows.map(x=>Math.abs(Number(x?.[field]||0))))
 return <div className="flow-spark" aria-label={`${field} 최근 수급`}>
  {rows.map((row,i)=>{
   const value=Number(row?.[field]||0)
   const height=Math.max(12,Math.round(Math.abs(value)/max*100))
   return <span key={`${row?.date||i}-${i}`} className={value>0?'up':value<0?'down':'flat'} title={`${flowDate(row?.date)} ${flowQty(value)}`}>
    <i style={{height:`${height}%`}}></i>
   </span>
  })}
 </div>
}

function FlowWeekDetail({series=[]}){
 const rows=Array.isArray(series)?series.slice(-7):[]
 if(!rows.length)return null
 return <div className="flow-week-detail" onClick={e=>e.stopPropagation()}>
  <div className="flow-week-detail-head"><b>최근 {rows.length}거래일 수급 상세</b><span>날짜별 순매수 수량</span></div>
  <div className="flow-week-scroll">
   <div className="flow-week-grid" style={{'--flow-days':rows.length}}>
    <div className="flow-week-label date">날짜</div>
    {rows.map((row,i)=><div className="flow-week-date" key={`date-${row?.date||i}`}>{flowDate(row?.date)}</div>)}
    <div className="flow-week-label foreign">외국인</div>
    {rows.map((row,i)=>{const v=Number(row?.foreign||0);return <div className={`flow-week-value ${v>0?'up':v<0?'down':'flat'}`} key={`foreign-${row?.date||i}`} title={`${String(row?.date||'')} 외국인 ${flowQtyExact(v)}`}>{flowQtyExact(v)}</div>})}
    <div className="flow-week-label institution">기관</div>
    {rows.map((row,i)=>{const v=Number(row?.institution||0);return <div className={`flow-week-value ${v>0?'up':v<0?'down':'flat'}`} key={`institution-${row?.date||i}`} title={`${String(row?.date||'')} 기관 ${flowQtyExact(v)}`}>{flowQtyExact(v)}</div>})}
   </div>
  </div>
 </div>
}

function FlowAnalysis({openStock,user}){
 const advanced=Boolean(user?.features?.flow_advanced?.enabled)
 const [period,setPeriod]=useState(advanced?7:1)
 const [investor,setInvestor]=useState('all')
 const [market,setMarket]=useState('ALL')
 const [signal,setSignal]=useState('all')
 const [sort,setSort]=useState('score')
 const [query,setQuery]=useState('')
 const [debouncedQuery,setDebouncedQuery]=useState('')
 const [page,setPage]=useState(1)
 const [data,setData]=useState({items:[],page:1,pages:1,total:0,summary:{}})
 const [loading,setLoading]=useState(true)
 const [err,setErr]=useState('')

 useEffect(()=>{
  const t=setTimeout(()=>setDebouncedQuery(query.trim()),220)
  return()=>clearTimeout(t)
 },[query])
 useEffect(()=>{
  if(!advanced){setPeriod(1);setSignal('all');if(!['all','foreign','institution','individual'].includes(investor))setInvestor('all')}
 },[advanced])
 useEffect(()=>{setPage(1)},[period,investor,market,signal,sort,debouncedQuery])
 useEffect(()=>{
  let alive=true
  setLoading(true);setErr('')
  api.get('/api/flow-analysis/rankings',{params:{period,investor,market,signal,sort,q:debouncedQuery,page,page_size:30}})
   .then(r=>{if(alive)setData(r.data||{items:[]})})
   .catch(e=>{if(alive)setErr(publicUiText(e.response?.data?.detail)||'수급 분석 데이터를 불러오지 못했습니다.')})
   .finally(()=>{if(alive)setLoading(false)})
  return()=>{alive=false}
 },[period,investor,market,signal,sort,debouncedQuery,page])

 const investorOptions=advanced
  ? [['all','종합'],['foreign','외국인'],['institution','기관'],['individual','개인'],['financial_investment','금융투자'],['investment_trust','투신'],['pension','연기금'],['insurance','보험'],['bank','은행'],['private_equity','사모펀드']]
  : [['all','종합'],['foreign','외국인'],['institution','기관'],['individual','개인']]
 const summary=data?.summary||{}
 const rows=data?.items||[]
 const latest=data?.latest_date

 return <>
  {loading&&<PageDataLoadingStatus marketLabel="국내증권" pageLabel="수급 분석" title="수급 순위를 업데이트하고 있어요" detail="현재 순위와 필터 화면을 유지하면서 외국인·기관·개인 수급을 다시 계산합니다." steps={['필터 조건 유지','수급 데이터 확인','순위 결과 반영']}/>} 
  <div className="page-head flow-page-head">
   <div><span>INVESTOR FLOW</span><h1>수급 분석</h1><p>외국인/기관/개인과 기관 세부 주체의 실제 순매수 흐름을 거래일 단위로 분석합니다.</p></div>
   <div className="flow-latest"><Clock3 size={15}/><span>{latest?`최근 데이터 ${latest}`:'업데이트 전'}</span></div>
  </div>

  <div className="flow-summary-grid">
   <article><span className="flow-summary-icon"><Users size={18}/></span><div><small>외국인 순매수</small><b>{Number(summary.foreign_positive||0).toLocaleString()}종목</b><em>{period}거래일 기준</em></div></article>
   <article><span className="flow-summary-icon"><Landmark size={18}/></span><div><small>기관 순매수</small><b>{Number(summary.institution_positive||0).toLocaleString()}종목</b><em>{period}거래일 기준</em></div></article>
   <article><span className="flow-summary-icon"><TrendingUp size={18}/></span><div><small>외국인/기관 쌍끌이</small><b>{Number(summary.joint_buy||0).toLocaleString()}종목</b><em>동반 누적 순매수</em></div></article>
   <article><span className="flow-summary-icon"><RotateCcw size={18}/></span><div><small>수급 반전</small><b>{Number(summary.reversal||0).toLocaleString()}종목</b><em>최근 매도 → 매수</em></div></article>
  </div>

  <section className="panel flow-filter-panel">
   <div className="flow-filter-head"><div><SlidersHorizontal size={17}/><b>수급 필터</b></div><span>순매수 수량 기준 / 데이터는 서버 DB에서 조회</span></div>
   <div className="flow-filter-row flow-period-row">
    <small>기간</small>
    <div className="flow-chip-group">
     {[[1,'오늘'],[3,'3일'],[5,'5일'],[7,'7일'],[20,'20일']].map(([value,label])=><button key={value} type="button" className={period===value?'active':''} disabled={!advanced&&value!==1} onClick={()=>setPeriod(value)}>{label}{!advanced&&value!==1&&<LockKeyhole size={11}/>}</button>)}
    </div>
   </div>
   <div className="flow-filter-grid">
    <label><span>투자자</span><select value={investor} onChange={e=>setInvestor(e.target.value)}>{investorOptions.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
    <label><span>시장</span><select value={market} onChange={e=>setMarket(e.target.value)}><option value="ALL">전체 시장</option><option value="KOSPI">KOSPI</option><option value="KOSDAQ">KOSDAQ</option></select></label>
    <label><span>정렬</span><select value={sort} onChange={e=>setSort(e.target.value)}><option value="score">수급점수순</option><option value="net">순매수순</option><option value="strength">수급강도순</option><option value="persistence">지속성순</option></select></label>
    <label className="flow-search"><span>종목 검색</span><div><Search size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="종목명 또는 코드"/></div></label>
   </div>
   {advanced?<div className="flow-filter-row"><small>신호</small><div className="flow-chip-group">{[['all','전체'],['joint','쌍끌이'],['streak','3일+ 연속매수'],['reversal','수급 반전'],['foreign','외국인 매수'],['institution','기관 매수']].map(([value,label])=><button key={value} type="button" className={signal===value?'active':''} onClick={()=>setSignal(value)}>{label}</button>)}</div></div>
    :<div className="flow-premium-note"><Crown size={15}/><div><b>프리미엄 수급 기능</b><span>3/5/7/20일 누적, 금융투자/투신/연기금 세부 필터와 쌍끌이/반전/연속매수 신호는 프리미엄/이벤트 회원 기능입니다.</span></div></div>}
  </section>

  {err&&<div className="info error">{err}</div>}
  {!loading&&!err&&!rows.length&&<div className="panel empty flow-empty"><Gauge size={30}/><b>표시할 수급 데이터가 없습니다.</b><span>{publicUiText(data?.message)||'아직 수급 정보가 준비되지 않았습니다.'}</span></div>}

  {rows.length>0&&<div className="flow-list" aria-busy={loading?'true':'false'}>
   {rows.map((row,index)=>{
    const rank=(Number(data.page||1)-1)*Number(data.page_size||30)+index+1
    const score=Number(row.score||0)
    const cumulativeDays=Math.max(1,Number(row.days||period)||period)
    return <article key={row.code} className="flow-card flow-card-v2">
     <aside className="flow-rank-v2">
      <span className="flow-rank-label">RANK</span>
      <div className="flow-rank-number"><strong>{rank}</strong><small>위</small></div>
      <div className={`flow-score-modern ${score>=70?'strong':score>=50?'balanced':'watch'}`}><div><span>FLOW SCORE</span><b>{score.toFixed(1)}</b></div><div className="flow-score-track"><i style={{width:`${Math.max(0,Math.min(100,score))}%`}}/></div><small>{score>=70?'강한 수급':score>=50?'중립 이상':'관찰 필요'}</small></div>
     </aside>
     <div className="flow-stock-main flow-stock-main-v2">
      <header className="flow-stock-title-v2">
       <div><div className="flow-name-price"><b>{row.name}</b><strong>{Number(row.price||0)>0?`${won(row.price)}원`:'-'}</strong><em className={Number(row.change_rate||0)>0?'up':Number(row.change_rate||0)<0?'down':'flat'}>{Number(row.change_rate||0)>0?'+':''}{Number(row.change_rate||0).toFixed(2)}%</em></div><span>{row.code} · {row.market}</span></div>
       <button type="button" className="flow-stock-detail-button" onClick={()=>openStock({code:row.code})}><span>종목 상세</span><ChevronRight size={15}/></button>
      </header>
      <section className="flow-data-section primary">
       <div className="flow-section-caption core"><span>핵심 수급</span></div>
       <div className="flow-investor-values flow-investor-values-v2">
        <span><small>외국인</small><b className={Number(row.foreign_net)>=0?'up':'down'}>{flowQty(row.foreign_net)}</b></span>
        <span><small>기관</small><b className={Number(row.institution_net)>=0?'up':'down'}>{flowQty(row.institution_net)}</b></span>
        <span><small>개인</small><b className={Number(row.individual_net)>=0?'up':'down'}>{flowQty(row.individual_net)}</b></span>
        <span><small>금융투자</small><b className={Number(row.financial_investment_net)>=0?'up':'down'}>{flowQty(row.financial_investment_net)}</b></span>
       </div>
      </section>
      <section className="flow-data-section secondary">
       <div className="flow-section-caption"><span>기관 세부</span></div>
       <div className="flow-subject-row flow-subject-row-v2"><span><small>투신</small><b className={Number(row.investment_trust_net)>0?'up':Number(row.investment_trust_net)<0?'down':'flat'}>{flowQty(row.investment_trust_net)}</b></span><span><small>연기금</small><b className={Number(row.pension_net)>0?'up':Number(row.pension_net)<0?'down':'flat'}>{flowQty(row.pension_net)}</b></span><span><small>보험</small><b className={Number(row.insurance_net)>0?'up':Number(row.insurance_net)<0?'down':'flat'}>{flowQty(row.insurance_net)}</b></span><span><small>사모</small><b className={Number(row.private_equity_net)>0?'up':Number(row.private_equity_net)<0?'down':'flat'}>{flowQty(row.private_equity_net)}</b></span></div>
      </section>
      <div className="flow-insight-v2"><span><Sparkles size={13}/>수급 인사이트</span><b>{row.insight}</b><small>외국인 {row.foreign_buy_days}/{cumulativeDays}일 · 기관 {row.institution_buy_days}/{cumulativeDays}일 순매수</small></div>
      <FlowWeekDetail series={row.series}/>
     </div>
    </article>
   })}
  </div>}

  {Number(data.pages||1)>1&&<div className="stocklog-pagination flow-pagination"><button disabled={loading||Number(data.page||1)<=1} onClick={()=>setPage(p=>Math.max(1,p-1))}>이전</button><b>{Number(data.page||1)} / {Number(data.pages||1)}</b><button disabled={loading||Number(data.page||1)>=Number(data.pages||1)} onClick={()=>setPage(p=>p+1)}>다음</button></div>}
  <div className="flow-disclaimer">수급점수는 최근 투자자 흐름을 종합해 보여주는 참고지표이며 미래 수익률을 보장하지 않습니다.</div>
 </>
}

function Themes({openStock,user}){
 const [themes,setThemes]=useState([])
 const [selected,setSelected]=useState(null)
 const [stocks,setStocks]=useState([])
 const [loading,setLoading]=useState(false)
 const [detailLoading,setDetailLoading]=useState(false)
 const [detailNote,setDetailNote]=useState('')
 const [detailFallback,setDetailFallback]=useState(false)
 const [themeWarning,setThemeWarning]=useState('')
 const [gbotSummary,setGbotSummary]=useState(null)
 const [gbotLoading,setGbotLoading]=useState(false)
 const themeGbotRequestRef=useRef(0)
 const [refreshPolicy,setRefreshPolicy]=useState(user?.refresh_policy||{})
 const themeRefreshSeconds=Math.max(0,Number(refreshPolicy?.theme_seconds??60))

 const load=async({silent=false}={})=>{
  if(!silent)setLoading(true)

  try{
   const r=await api.get(
    '/api/themes'
   )
   setThemes(
    r.data.items||[]
   )
   setThemeWarning(publicUiText(r.data.warning)||'')

  }catch(e){
   if(!silent){
    await showMessage(
     publicUiText(e.response?.data?.detail)
     || '강세 테마를 불러오지 못했습니다.',
     '테마 조회 오류',
     'danger'
    )
   }

  }finally{
   if(!silent)setLoading(false)
  }
 }

 useEffect(()=>{
  load()
  api.get('/api/membership/refresh-policy').then(r=>setRefreshPolicy(r.data||{})).catch(()=>{})
 },[])

 useEffect(()=>{
  if(themeRefreshSeconds<=0)return
  const timer=setInterval(()=>{
   if(document.visibilityState==='visible')load({silent:true})
  },Math.max(10,themeRefreshSeconds)*1000)
  return()=>clearInterval(timer)
 },[themeRefreshSeconds])

 const pick=async t=>{
  const gbotRequestId=++themeGbotRequestRef.current
  setSelected(t)
  setStocks([])
  setDetailLoading(true)
  setDetailNote('')
  setDetailFallback(false)
  setGbotSummary(null)
  setGbotLoading(false)

  try{
   const r=await api.get(
    `/api/themes/${encodeURIComponent(t.theme_code)}`,
    {
     params:{
      theme_name:t.theme_name
     }
    }
   )

   const nextStocks=r.data.items||[]
   setStocks(nextStocks)
   setDetailNote(publicUiText(r.data.message)||'')
   setDetailFallback(Boolean(r.data.fallback))
   setGbotLoading(true)
   setGbotSummary(null)
   api.post('/api/themes/gbot-summary',{
    theme_code:t.theme_code,
    theme_name:t.theme_name,
    change_rate:t.change_rate,
    stocks:nextStocks.slice(0,12).map(x=>({code:x.code,name:x.name,market:x.market,price:x.price,change_rate:x.change_rate,per:x.per,pbr:x.pbr,roe:x.roe}))
   }).then(res=>{if(themeGbotRequestRef.current===gbotRequestId)setGbotSummary(res.data||null)}).catch(err=>{if(themeGbotRequestRef.current===gbotRequestId)setGbotSummary({available:false,message:publicUiText(err.response?.data?.detail)||'Gbot 테마 분석을 잠시 불러오지 못했습니다.'})}).finally(()=>{if(themeGbotRequestRef.current===gbotRequestId)setGbotLoading(false)})

  }catch(e){
   // Keep any previously displayed data instead of turning a simple
   // theme switch into a blank page.
   const message=
    publicUiText(e.response?.data?.detail)
    || '구성종목을 불러오지 못했습니다.'

   setDetailNote(message)
   setDetailFallback(false)

  }finally{
   setDetailLoading(false)
  }
 }

 return <>
  {(loading||detailLoading||gbotLoading)&&<PageDataLoadingStatus marketLabel="국내증권" pageLabel="인기테마 분석" title={detailLoading?`${selected?.theme_name||'선택한 테마'} 구성종목을 확인하고 있어요`:gbotLoading?`${selected?.theme_name||'선택한 테마'} 분석을 정리하고 있어요`:'강세 테마 순위를 업데이트하고 있어요'} detail="테마 화면을 먼저 표시하고 순위·구성종목·Gbot 요약을 준비되는 순서대로 반영합니다." steps={['현재 테마 화면 유지','테마 데이터 확인','분석 결과 반영']}/>} 
  <div className="page-head">
   <div>
    <span>MARKET THEMES</span>
    <h1>강세 테마</h1>
    <p>현재 시장에서 강한 흐름을 보이는 테마를 순서대로 확인합니다.{themeRefreshSeconds>0?` / ${themeRefreshSeconds}초 자동 새로고침`:' / 자동 새로고침 꺼짐'}</p>
   </div>

   <button
    className="secondary"
    onClick={load}
    disabled={loading}
   >
    <RefreshCw size={16}/>
    {loading?'불러오는 중':'새로고침'}
   </button>
  </div>

  {themeWarning&&<div className="theme-stale-note">{themeWarning}</div>}

  <div className="theme-layout">
   <div className="theme-rank-panel">
    <div className="theme-panel-head">
     <b>강세 테마 순위</b>
     <small>시장 테마</small>
    </div>

    <div className="theme-rank-list">
     {themes.map((t,i)=>
      <button
       key={t.theme_code}
       className={
        selected?.theme_code===t.theme_code
         ? 'theme-rank-item active'
         : 'theme-rank-item'
       }
       onClick={()=>pick(t)}
      >
       <i>{i+1}</i>
       <span>
        <b>{t.theme_name}</b>
        <small>
         {t.stock_count
          ? `${t.stock_count}개 종목`
          : '구성종목 보기'}
        </small>
       </span>
       <strong className={(t.change_rate||0)>=0?'up':'down'}>
        {t.change_rate==null
         ? '-'
         : `${Number(t.change_rate)>0?'+':''}${oneDecimal(t.change_rate)}%`}
       </strong>
      </button>
     )}
    </div>
   </div>

   <div className="theme-stock-panel">
    {!selected
     ? <div className="theme-empty">
        <b>테마를 선택해주세요</b>
        <p>왼쪽 강세 순위에서 선택하면 구성종목이 표시됩니다.</p>
       </div>
     : <>
        <div className="theme-selected-head">
         <div>
          <h2>{selected.theme_name}</h2>
          {detailFallback&&
           <span className="theme-data-source cached">
            최근 확인 데이터
           </span>
          }
          {!detailFallback&&!detailLoading&&stocks.length>0&&
           <span className="theme-data-source live">
            현재 구성종목
           </span>
          }
         </div>

         <strong className={(selected.change_rate||0)>=0?'up':'down'}>
          {selected.change_rate==null
           ? '-'
           : `${Number(selected.change_rate)>0?'+':''}${oneDecimal(selected.change_rate)}%`}
         </strong>
        </div>

        {gbotLoading?<div className="theme-gbot-card loading"><div className="theme-gbot-mark"><div className="sync-spinner small"/><Sparkles size={17}/></div><div><small>STOCKLOG GBOT THEME VIEW</small><b>{selected.theme_name} 강세 이유를 분석하고 있습니다.</b><span>구성종목 확산도, 주도 종목, 최근 뉴스와 실제 가격 움직임을 연결해 왜 지금 강한지 정리합니다.</span></div></div>:
         gbotSummary?.available!==false&&gbotSummary?.summary?<div className="theme-gbot-card"><div className="theme-gbot-head"><div><span><Sparkles size={14}/>GBOT THEME VIEW</span><h3>{gbotSummary.headline||`${selected.theme_name} 강세 요약`}</h3></div><em>{gbotSummary.tone||'시장 강도 분석'}</em></div><div className="theme-gbot-summary-lines">{(Array.isArray(gbotSummary.summary_lines)&&gbotSummary.summary_lines.length?gbotSummary.summary_lines:String(gbotSummary.summary||'').split(/(?<=[.!?])\s+/).filter(Boolean).map((text,index)=>({text,important:index===0}))).slice(0,6).map((line,i)=>{const text=typeof line==='string'?line:line?.text;const important=typeof line==='object'&&Boolean(line?.important);return text?<p className={important?'important':''} key={i}>{important?<strong>{text}</strong>:text}</p>:null})}</div><div className="theme-gbot-drivers">{(gbotSummary.drivers||[]).slice(0,4).map((x,i)=><span key={i}><i>{i+1}</i><b>{x}</b></span>)}</div>{(gbotSummary.risks||[]).length>0&&<div className="theme-gbot-risk"><AlertTriangle size={14}/><span>{gbotSummary.risks.slice(0,3).join(' · ')}</span></div>}</div>:
         gbotSummary?.message?<div className="theme-gbot-card unavailable"><Sparkles size={17}/><div><small>STOCKLOG GBOT</small><b>테마 요약을 잠시 쉬고 있습니다.</b><span>{gbotSummary.message}</span></div></div>:null}

        {detailNote&&
         <div className={`theme-inline-note ${detailFallback?'cached':'warning'}`}>
          {publicUiText(detailNote)}
         </div>
        }

        {stocks.length
           ? <div className="theme-stock-list">
              {stocks.map((s,i)=>
               <button
                key={s.code}
                onClick={()=>openStock(s.code)}
               >
                <i>{i+1}</i>
                <span>
                 <span className="stock-title-line">
                  <b>{s.name}</b>
                  <em className="stock-category-badge">
                   {selected.theme_name}
                  </em>
                 </span>
                 <small>
                  {s.code} / {s.market||'-'}
                 </small>
                </span>
                <em>{metricValue(s.per,'배')}</em>
                <strong className={(s.change_rate||0)>=0?'up':'down'}>
                 {s.change_rate==null
                  ? '-'
                  : `${Number(s.change_rate)>0?'+':''}${oneDecimal(s.change_rate)}%`}
                </strong>
               </button>
              )}
             </div>
           : <div className="theme-empty compact">
              <b>표시할 구성종목이 없습니다.</b>
              <p>{detailLoading?'구성종목을 확인하는 동안 테마 화면을 계속 사용할 수 있습니다.':detailNote||'현재 확인되는 구성종목이 없습니다.'}</p>
             </div>
        }
       </>
    }
   </div>
  </div>
 </>
}

function themeSyncStatusLabel(status){
 const map={
  starting:'요청 준비',
  requesting:'연결 서비스 응답 대기',
  received:'연결 서비스 응답 수신',
  parsing:'응답 파싱',
  parsed:'응답 파싱 완료',
  db_saving:'MySQL 저장',
  db_error:'MySQL 저장 오류',
  done:'테마 저장 완료',
  retry_wait:'재시도 대기',
  rate_limit:'호출 제한 대기',
  catalog:'목록 조회',
  catalog_request:'목록 조회',
  catalog_page_done:'목록 수신',
  members:'구성종목 수집',
  failed:'실패',
  finalizing:'최종 정리',
  completed:'완료',
  finished:'완료',
  cancelled:'중지됨'
 }
 return map[status]||status||'-'
}

function AdminMemberDetailModal({detail,loading,error,tab,setTab,onClose}){
 const user=detail?.user||{}
 const portfolio=detail?.portfolio||{}
 const summary=portfolio?.summary||{}
 const profile=detail?.investment_profile||null
 const trading=detail?.trading||{}
 const ai=detail?.ai_usage||{}
 const connections=detail?.connections||{}
 const memberProfile=user?.member_profile||{}
 const tier=String(user?.membership_tier||'NORMAL').toUpperCase()
 const membershipLabels={NORMAL:'일반회원',PREMIUM:'프리미엄회원',EVENT:'이벤트회원',ADMIN:'관리자'}
 const genderLabel={male:'남성',female:'여성',other:'기타',prefer_not_to_say:'응답하지 않음'}[memberProfile.gender]||'-'
 const money=value=>`${Math.round(Number(value||0)).toLocaleString('ko-KR')}원`
 const signedMoney=value=>{
  const n=Number(value||0)
  return `${n>0?'+':''}${Math.round(n).toLocaleString('ko-KR')}원`
 }
 const signedPct=value=>{
  const n=Number(value||0)
  return `${n>0?'+':''}${n.toFixed(2)}%`
 }
 const dateTime=value=>value?new Date(value).toLocaleString('ko-KR'):'-'
 const dateOnly=value=>value?new Date(value).toLocaleDateString('ko-KR'):'-'
 const providerName={google:'Google',naver:'네이버',kakao:'카카오',local:'아이디/비밀번호',admin:'관리자 로그인'}
 const pnlClass=Number(summary.profit_loss||0)>0?'up':Number(summary.profit_loss||0)<0?'down':'flat'
 const profileCode=profile?.result_code||''
 const traits=profileCode.split('').map((letter,index)=>({letter,index,...(INVESTMENT_TRAITS[letter]||{})}))
 const aiHistory=ai?.history_14_days||[]
 const maxAi=Math.max(1,...aiHistory.map(row=>Number(row.queries||0)))
 const tabs=[['overview','요약'],['portfolio','포트폴리오'],['profile','투자성향'],['activity','계정 · 활동']]
 const closeOnBackdrop=e=>{if(e.target===e.currentTarget)onClose()}
 return createPortal(
  <div className="admin-member-modal" onMouseDown={closeOnBackdrop}>
   <div className="admin-member-detail" role="dialog" aria-modal="true" aria-label="회원 상세보기">
    <button type="button" className="admin-member-detail-close" onClick={onClose} aria-label="닫기"><X size={19}/></button>
    {loading?<div className="admin-member-detail-loading"><RefreshCw className="spin-icon" size={20}/><b>회원 정보를 불러오는 중...</b></div>:
    error?<div className="admin-member-detail-loading error"><b>{error}</b></div>:
    detail&&<>
     <header className="admin-member-detail-head">
      <div className="admin-member-detail-avatar"><UserRound size={24}/></div>
      <div className="admin-member-detail-title">
       <div><h2>{user.display_name||user.username}</h2><em className={tier.toLowerCase()}>{membershipLabels[tier]||tier}</em>{user.is_active?<span className="active">활성</span>:<span className="inactive">비활성</span>}</div>
       <p>@{user.username} · 가입 {dateOnly(user.created_at)} · 최근 로그인 {dateTime(user.last_login_at)}</p>
      </div>
     </header>

     <nav className="admin-member-detail-tabs">
      {tabs.map(([key,label])=><button type="button" key={key} className={tab===key?'active':''} onClick={()=>setTab(key)}>{label}</button>)}
     </nav>

     <div className="admin-member-detail-body">
      {tab==='overview'&&<>
       <div className="admin-member-kpi-grid">
        <article><small>모의투자 총자산</small><b>{portfolio.last_success_at?money(summary.total_asset):'-'}</b><span>{portfolio.last_success_at?`최근 동기화 ${dateTime(portfolio.last_success_at)}`:'계좌 동기화 없음'}</span></article>
        <article className={pnlClass}><small>평가손익</small><b>{portfolio.last_success_at?signedMoney(summary.profit_loss):'-'}</b><span>{portfolio.last_success_at?signedPct(summary.return_rate):'수익률 정보 없음'}</span></article>
        <article><small>보유종목</small><b>{Number(summary.holding_count||0).toLocaleString()}종목</b><span>평가금액 {portfolio.last_success_at?money(summary.evaluation_amount):'-'}</span></article>
        <article><small>투자성향</small><b>{profileCode||'미검사'}</b><span>{profileCode?profileNickname(profileCode):'투자성향 결과 없음'}</span></article>
        <article><small>AI 사용</small><b>{Number(ai.last_30_days||0).toLocaleString()}회</b><span>최근 30일 · 누적 {Number(ai.total||0).toLocaleString()}회</span></article>
        <article><small>거래 기록</small><b>{Number(trading.total_orders||0).toLocaleString()}건</b><span>매수 {Number(trading.buy_orders||0)} · 매도 {Number(trading.sell_orders||0)}</span></article>
       </div>

       <div className="admin-member-overview-grid">
        <section className="admin-member-card">
         <div className="admin-member-card-head"><div><small>PORTFOLIO</small><h3>보유 비중 상위 종목</h3></div><Landmark size={18}/></div>
         {(portfolio.holdings||[]).length?<div className="admin-member-top-holdings">{(portfolio.holdings||[]).slice(0,5).map(row=>{
          const total=Number(summary.evaluation_amount||0)||(portfolio.holdings||[]).reduce((sum,item)=>sum+Number(item.evaluation_amount||0),0)
          const weight=total?Number(row.evaluation_amount||0)/total*100:0
          return <div key={row.code}><div><b>{row.name||row.code}</b><span>{row.code}</span></div><strong className={Number(row.profit_loss||0)>=0?'up':'down'}>{signedPct(row.return_rate)}</strong><i><em style={{width:`${Math.max(2,Math.min(100,weight))}%`}}/></i><small>{weight.toFixed(1)}% · {money(row.evaluation_amount)}</small></div>
         })}</div>:<div className="admin-member-empty">현재 저장된 보유종목이 없습니다.</div>}
        </section>

        <section className="admin-member-card">
         <div className="admin-member-card-head"><div><small>INVESTOR DNA</small><h3>투자성향 요약</h3></div><Fingerprint size={18}/></div>
         {profileCode?<div className="admin-member-dna-summary"><div className="admin-member-dna-code">{profileCode.split('').map((letter,i)=><span key={`${letter}-${i}`}>{letter}</span>)}</div><b>{profileNickname(profileCode)}</b><p>{profileCodeTitle(profileCode)}</p><small>최근 검사 {dateOnly(profile.completed_at)}</small></div>:<div className="admin-member-empty">투자성향 검사를 완료하지 않았습니다.</div>}
        </section>
       </div>
      </>}

      {tab==='portfolio'&&<>
       <div className="admin-member-portfolio-summary">
        <article><small>총자산</small><b>{portfolio.last_success_at?money(summary.total_asset):'-'}</b></article>
        <article><small>예수금</small><b>{portfolio.last_success_at?money(summary.cash):'-'}</b></article>
        <article><small>매수금액</small><b>{portfolio.last_success_at?money(summary.purchase_amount):'-'}</b></article>
        <article><small>평가금액</small><b>{portfolio.last_success_at?money(summary.evaluation_amount):'-'}</b></article>
        <article className={pnlClass}><small>평가손익</small><b>{portfolio.last_success_at?signedMoney(summary.profit_loss):'-'}</b></article>
        <article className={pnlClass}><small>수익률</small><b>{portfolio.last_success_at?signedPct(summary.return_rate):'-'}</b></article>
       </div>
       <div className="admin-member-section-title"><div><span>HOLDINGS</span><h3>보유 종목</h3></div><small>{portfolio.account_no_masked?`계좌 ${portfolio.account_no_masked}`:'연결 계좌 없음'} · 관리자 조회는 저장된 최근 동기화 데이터 기준</small></div>
       {(portfolio.holdings||[]).length?<div className="admin-member-table-wrap"><table className="admin-member-table"><thead><tr><th>종목</th><th>수량</th><th>평균단가</th><th>현재가</th><th>평가금액</th><th>평가손익</th><th>수익률</th></tr></thead><tbody>{portfolio.holdings.map(row=><tr key={row.code}><td><b>{row.name||row.code}</b><small>{row.code}{row.market?` · ${row.market}`:''}</small></td><td>{Number(row.quantity||0).toLocaleString()}주</td><td>{money(row.avg_price)}</td><td>{money(row.current_price)}</td><td>{money(row.evaluation_amount)}</td><td className={Number(row.profit_loss||0)>=0?'up':'down'}>{signedMoney(row.profit_loss)}</td><td className={Number(row.return_rate||0)>=0?'up':'down'}>{signedPct(row.return_rate)}</td></tr>)}</tbody></table></div>:<div className="admin-member-empty large">저장된 모의투자 보유종목이 없습니다.</div>}

       <div className="admin-member-two-col">
        <section className="admin-member-card">
         <div className="admin-member-card-head"><div><small>ORDERS</small><h3>최근 주문</h3></div><CircleDollarSign size={18}/></div>
         {(trading.recent_orders||[]).length?<div className="admin-member-activity-list">{trading.recent_orders.slice(0,8).map(row=><div key={row.id}><span className={row.side==='buy'?'buy':'sell'}>{row.side==='buy'?'매수':'매도'}</span><div><b>{row.stock_name||row.stock_code}</b><small>{row.stock_code} · {dateTime(row.created_at)} · {Number(row.quantity||0).toLocaleString()}주</small></div><strong>{row.price?money(row.price):'시장가'}</strong><em>{row.status||'-'}</em></div>)}</div>:<div className="admin-member-empty">주문 기록이 없습니다.</div>}
        </section>
        <section className="admin-member-card">
         <div className="admin-member-card-head"><div><small>RESERVATIONS</small><h3>가격감시 예약</h3></div><CalendarClock size={18}/></div>
         <div className="admin-member-mini-kpis"><span><small>전체</small><b>{Number(trading.reservation_total||0)}</b></span><span><small>활성</small><b>{Number(trading.reservation_active||0)}</b></span></div>
         {(trading.recent_reservations||[]).length?<div className="admin-member-activity-list compact">{trading.recent_reservations.slice(0,6).map(row=><div key={row.id}><span className={row.side==='buy'?'buy':'sell'}>{row.side==='buy'?'매수':'매도'}</span><div><b>{row.stock_name||row.stock_code}</b><small>{Number(row.trigger_price||0).toLocaleString()}원 조건 · {Number(row.quantity||0).toLocaleString()}주</small></div><em>{row.status||'-'}</em></div>)}</div>:<div className="admin-member-empty">예약 주문이 없습니다.</div>}
        </section>
       </div>
      </>}

      {tab==='profile'&&<>
       {profileCode?<>
        <section className="admin-member-profile-hero">
         <div><small>INVESTOR DNA</small><div className="admin-member-dna-code large">{profileCode.split('').map((letter,i)=><span key={`${letter}-${i}`}>{letter}</span>)}</div></div>
         <div><h3>{profileNickname(profileCode)}</h3><p>{profileCodeTitle(profileCode)}</p><small>30문항 완료 · 최근 검사 {dateTime(profile.completed_at)}</small></div>
        </section>
        <div className="admin-member-trait-grid">{traits.map(trait=>{
         const axis=INVESTMENT_AXES[trait.index]
         const axisScores=profile?.scores?.percentages?.[axis?.key]||{}
         return <article key={`${trait.letter}-${trait.index}`}><div className="admin-member-trait-title"><strong>{trait.letter}</strong><div><small>{axis?.name||''}</small><b>{trait.name||trait.letter}</b></div></div><p>{trait.summary||''}</p><div className="admin-member-axis-bars">{Object.entries(axisScores).map(([letter,value])=><div key={letter}><span><b>{INVESTMENT_TRAITS[letter]?.name||letter}</b><em>{Number(value||0).toFixed(0)}%</em></span><i><strong style={{width:`${Math.max(0,Math.min(100,Number(value||0)))}%`}}/></i></div>)}</div></article>
        })}</div>
       </>:<div className="admin-member-empty large">이 회원은 아직 투자성향 검사를 완료하지 않았습니다.</div>}
      </>}

      {tab==='activity'&&<>
       <div className="admin-member-two-col account">
        <section className="admin-member-card">
         <div className="admin-member-card-head"><div><small>ACCOUNT</small><h3>회원 정보</h3></div><UserRound size={18}/></div>
         <dl className="admin-member-info-list">
          <div><dt>아이디</dt><dd>@{user.username}</dd></div>
          <div><dt>이름</dt><dd>{memberProfile.name||user.display_name||'-'}</dd></div>
          <div><dt>성별</dt><dd>{genderLabel}</dd></div>
          <div><dt>생년월일</dt><dd>{memberProfile.birth_date||memberProfile.birth_year||'-'}{memberProfile.age!==null&&memberProfile.age!==undefined?` · 만 ${memberProfile.age}세`:''}</dd></div>
          <div><dt>휴대폰</dt><dd>{memberProfile.phone_number_masked||'-'}</dd></div>
          <div><dt>가입 방식</dt><dd>{user.signup_method==='social'?'SNS 회원가입':'아이디/비밀번호'}</dd></div>
          <div><dt>가입일</dt><dd>{dateTime(user.created_at)}</dd></div>
          <div><dt>최근 로그인</dt><dd>{dateTime(user.last_login_at)}{user.last_login_method?` · ${providerName[user.last_login_method]||user.last_login_method}`:''}</dd></div>
          <div><dt>로그인 횟수</dt><dd>{Number(user.login_count||0).toLocaleString()}회</dd></div>
         </dl>
        </section>
        <section className="admin-member-card">
         <div className="admin-member-card-head"><div><small>CONNECTIONS</small><h3>연결 서비스</h3></div><Settings size={18}/></div>
         <div className="admin-member-connection-list">
          <div><span><Landmark size={15}/>키움 모의투자</span><b>{connections.kiwoom?.configured?'연결됨':'미연결'}</b><small>{connections.kiwoom?.account_no_masked||'계좌 없음'}{connections.kiwoom?.last_connected_at?` · ${dateTime(connections.kiwoom.last_connected_at)}`:''}</small></div>
          {(connections.social_accounts||[]).map(row=><div key={`${row.provider}-${row.email}`}><span><UserRound size={15}/>{providerName[row.provider]||row.provider}</span><b>연결됨</b><small>{row.email||row.nickname||'-'}{row.last_login_at?` · 최근 ${dateTime(row.last_login_at)}`:''}</small></div>)}
          {!(connections.social_accounts||[]).length&&<div><span><UserRound size={15}/>SNS 계정</span><b>미연결</b><small>아이디/비밀번호 계정</small></div>}
         </div>
        </section>
       </div>

       <section className="admin-member-card admin-member-ai-card">
        <div className="admin-member-card-head"><div><small>AI USAGE</small><h3>최근 AI 사용량</h3></div><Sparkles size={18}/></div>
        <div className="admin-member-ai-summary"><span><small>오늘</small><b>{ai.today?.unlimited?`${Number(ai.today?.used||0)}회 / 무제한`:`${Number(ai.today?.used||0)} / ${Number(ai.today?.daily_limit||0)}회`}</b></span><span><small>최근 30일</small><b>{Number(ai.last_30_days||0).toLocaleString()}회</b></span><span><small>누적</small><b>{Number(ai.total||0).toLocaleString()}회</b></span></div>
        <div className="admin-member-ai-chart">{aiHistory.map(row=><div key={row.date} title={`${row.date}: ${row.queries}회`}><i style={{height:`${Math.max(4,Number(row.queries||0)/maxAi*100)}%`}}/><small>{String(row.date).slice(5).replace('-','/')}</small></div>)}</div>
       </section>

       <div className="admin-member-two-col account">
        <section className="admin-member-card">
         <div className="admin-member-card-head"><div><small>CONSENT</small><h3>동의 기록</h3></div><ShieldCheck size={18}/></div>
         {(detail.consents||[]).length?<div className="admin-member-consent-list">{detail.consents.map((row,i)=><div key={`${row.type}-${i}`}><b>{{terms:'이용약관',privacy:'개인정보',age_14_plus:'만 14세 이상'}[row.type]||row.type}</b><span>{row.policy_version}</span><small>{dateTime(row.agreed_at)}</small></div>)}</div>:<div className="admin-member-empty">동의 기록이 없습니다.</div>}
        </section>
        <section className="admin-member-card">
         <div className="admin-member-card-head"><div><small>SMART FORMULA</small><h3>나만의 공식</h3></div><SlidersHorizontal size={18}/></div>
         {detail.smart_formula?<div className="admin-member-formula-grid">{[['PER 최대','per_max'],['PBR 최대','pbr_max'],['ROE 최소','roe_min'],['매출성장 최소','revenue_growth_min'],['영업이익률 최소','operating_margin_min'],['배당 최소','dividend_yield_min'],['20일 모멘텀 최소','momentum_20d_min'],['시가총액 최소','market_cap_min']].map(([label,key])=><span key={key}><small>{label}</small><b>{detail.smart_formula[key]===null||detail.smart_formula[key]===undefined?'-':Number(detail.smart_formula[key]).toLocaleString()}</b></span>)}</div>:<div className="admin-member-empty">저장한 나만의 공식이 없습니다.</div>}
        </section>
       </div>
      </>}
     </div>
    </>}
   </div>
  </div>,document.body
 )
}

function AdminPasswordModal({target,currentUser,onClose,onSaved}){
 const [newPassword,setNewPassword]=useState('')
 const [confirmPassword,setConfirmPassword]=useState('')
 const [showPassword,setShowPassword]=useState(false)
 const [saving,setSaving]=useState(false)
 const [error,setError]=useState('')
 const isSelf=Number(target?.id)===Number(currentUser?.id)
 const isAdmin=String(target?.membership_tier||target?.account_type||'NORMAL').toUpperCase()==='ADMIN'
 const validLength=newPassword.length>=8&&newPassword.length<=128
 const differsFromUsername=Boolean(newPassword)&&newPassword.toLocaleLowerCase()!==String(target?.username||'').toLocaleLowerCase()
 const matches=Boolean(confirmPassword)&&newPassword===confirmPassword
 const closeOnBackdrop=e=>{if(e.target===e.currentTarget&&!saving)onClose()}
 useEffect(()=>{
  const onKey=e=>{if(e.key==='Escape'&&!saving)onClose()}
  window.addEventListener('keydown',onKey)
  return()=>window.removeEventListener('keydown',onKey)
 },[saving,onClose])
 const submit=async e=>{
  e.preventDefault();setError('')
  if(!validLength){setError('비밀번호는 8자 이상 128자 이하로 입력해주세요.');return}
  if(!differsFromUsername){setError('아이디와 동일한 비밀번호는 사용할 수 없습니다.');return}
  if(!matches){setError('새 비밀번호 확인이 일치하지 않습니다.');return}
  setSaving(true)
  try{
   const r=await api.put(`/api/admin/users/${target.id}/password`,{new_password:newPassword})
   const replacement=String(r.data?.current_session_token||'')
   if(replacement)localStorage.setItem('stocklog_token',replacement)
   onSaved(r.data?.message||'비밀번호를 변경했습니다.')
   onClose()
   // Cancel in-flight requests carrying the previous token and resume with the
   // replacement token when the acting administrator changed their own password.
   if(replacement)window.location.reload()
  }catch(err){setError(err.response?.data?.detail||'비밀번호 변경에 실패했습니다.')}
  finally{setSaving(false)}
 }
 return createPortal(
  <div className="admin-password-modal" onMouseDown={closeOnBackdrop}>
   <form className="admin-password-dialog" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="admin-password-title">
    <button type="button" className="admin-password-close" onClick={onClose} disabled={saving} aria-label="닫기"><X size={18}/></button>
    <header><span><KeyRound size={21}/></span><div><small>ACCOUNT SECURITY</small><h2 id="admin-password-title">비밀번호 변경</h2></div></header>
    <div className="admin-password-target"><div className="admin-account-avatar"><UserRound size={17}/></div><span><b>{target?.display_name||target?.username}</b><small>@{target?.username} · {isAdmin?'관리자':'회원'}{isSelf?' · 현재 로그인 계정':''}</small></span></div>
    <div className={`admin-password-warning ${isAdmin?'admin':''}`}><ShieldCheck size={17}/><span><b>{isSelf?'관리자 본인의 비밀번호를 변경합니다.':isAdmin?'관리자 계정의 비밀번호를 변경합니다.':'회원의 새 비밀번호를 설정합니다.'}</b><small>변경 즉시 이 계정의 기존 로그인 세션은 모두 종료됩니다.{isSelf?' 현재 브라우저는 새 인증으로 안전하게 다시 연결됩니다.':''}</small></span></div>
    <label className="admin-password-field"><span>새 비밀번호</span><div><input type={showPassword?'text':'password'} value={newPassword} onChange={e=>setNewPassword(e.target.value)} minLength="8" maxLength="128" autoComplete="new-password" autoFocus placeholder="8자 이상 입력"/><button type="button" onClick={()=>setShowPassword(v=>!v)} aria-label={showPassword?'비밀번호 숨기기':'비밀번호 보기'}>{showPassword?<EyeOff size={17}/>:<Eye size={17}/>}</button></div></label>
    <label className="admin-password-field"><span>새 비밀번호 확인</span><div><input type={showPassword?'text':'password'} value={confirmPassword} onChange={e=>setConfirmPassword(e.target.value)} minLength="8" maxLength="128" autoComplete="new-password" placeholder="새 비밀번호 다시 입력"/><button type="button" onClick={()=>setShowPassword(v=>!v)} aria-label={showPassword?'비밀번호 숨기기':'비밀번호 보기'}>{showPassword?<EyeOff size={17}/>:<Eye size={17}/>}</button></div></label>
    <div className="admin-password-checks"><span className={validLength?'ok':''}><CheckCircle2 size={14}/>8~128자</span><span className={differsFromUsername?'ok':''}><CheckCircle2 size={14}/>아이디와 다름</span><span className={matches?'ok':''}><CheckCircle2 size={14}/>비밀번호 일치</span></div>
    {error&&<div className="admin-password-error" role="alert">{error}</div>}
    <div className="admin-password-actions"><button type="button" className="secondary" onClick={onClose} disabled={saving}>취소</button><button type="submit" className="primary" disabled={saving||!validLength||!differsFromUsername||!matches}>{saving?'변경 중...':'비밀번호 변경'}</button></div>
   </form>
  </div>,document.body
 )
}

function AdminFold({title,subtitle='',defaultOpen=false,className='',badge='',children}){
 const [open,setOpen]=useState(defaultOpen)
 return <section className={`panel admin-fold ${className} ${open?'open':'closed'}`}>
  <button type="button" className="admin-fold-toggle" onClick={()=>setOpen(v=>!v)} aria-expanded={open}>
   <span className="admin-fold-chevron"><ChevronRight size={18}/></span>
   <span className="admin-fold-title"><b>{title}</b>{subtitle&&<small>{subtitle}</small>}</span>
   {badge&&<em className="admin-fold-badge">{badge}</em>}
  </button>
  {open&&<div className="admin-fold-body">{children}</div>}
 </section>
}

const ADMIN_SYNC_SCOPES=[
 {key:'kiwoom',label:'키움 시세',hint:'종목·일봉·투자지표'},
 {key:'dart',label:'DART 재무',hint:'재무·밸류 지표'},
 {key:'kiwoom_themes',label:'키움 테마',hint:'테마·구성종목'},
 {key:'market_themes',label:'시장 테마',hint:'시장 테마 데이터'},
 {key:'classification',label:'종목 분류',hint:'사업·업종 분류'},
 {key:'theme_engine',label:'표준 테마',hint:'StockLog 테마 재구축'},
 {key:'flow',label:'수급 데이터',hint:'최근 20거래일'},
 {key:'smart_scores',label:'스마트 점수',hint:'분석 점수 사전계산'},
]
const ADMIN_SYNC_SCOPE_KEYS=ADMIN_SYNC_SCOPES.map(x=>x.key)

function Admin({currentUser}){
 const [s,setS]=useState(null)
 const [market,setMarket]=useState(null)
 const [themeSync,setThemeSync]=useState(null)
 const [marketThemeSync,setMarketThemeSync]=useState(null)
 const [classificationSync,setClassificationSync]=useState(null)
 const [unifiedSync,setUnifiedSync]=useState(null)
 const [externalApis,setExternalApis]=useState(null)
 const [socialAuth,setSocialAuth]=useState(null)
 const [kiwoomRuntime,setKiwoomRuntime]=useState(null)
 const [membershipPolicy,setMembershipPolicy]=useState(null)
 const [policySaving,setPolicySaving]=useState(false)
 const [refreshPolicies,setRefreshPolicies]=useState(null)
 const [refreshPolicySaving,setRefreshPolicySaving]=useState(false)
 const [accessControl,setAccessControl]=useState(null)
 const [accessMode,setAccessMode]=useState('allow_all')
 const [accessIpsText,setAccessIpsText]=useState('')
 const [accessSaving,setAccessSaving]=useState(false)
 const [flowSync,setFlowSync]=useState(null)
 const [flowUniverseLimit,setFlowUniverseLimit]=useState(0)
 const [flowBusy,setFlowBusy]=useState(false)
 const [scheduleFlowUniverseLimit,setScheduleFlowUniverseLimit]=useState(0)
 const [syncErrorLogs,setSyncErrorLogs]=useState([])
 const [syncErrorLogsLoading,setSyncErrorLogsLoading]=useState(false)
 const [socialForm,setSocialForm]=useState({
  kakaoClientId:'',kakaoClientSecret:'',kakaoRedirectUri:`${window.location.origin}/api/auth/social/kakao/callback`,kakaoEnabled:true,
  naverClientId:'',naverClientSecret:'',naverRedirectUri:`${window.location.origin}/api/auth/social/naver/callback`,naverEnabled:true,
  googleClientId:'',googleClientSecret:'',googleRedirectUri:`${window.location.origin}/api/auth/social/google/callback`,googleEnabled:true
 })
 const [socialBusy,setSocialBusy]=useState('')
 const [accountUsers,setAccountUsers]=useState([])
 const [accountMeta,setAccountMeta]=useState({page:1,pages:1,total:0,page_size:20})
 const [accountPage,setAccountPage]=useState(1)
 const [accountQuery,setAccountQuery]=useState('')
 const [accountType,setAccountType]=useState('all')
 const [accountLoading,setAccountLoading]=useState(false)
 const [accountBusy,setAccountBusy]=useState('')
 const [accountDetail,setAccountDetail]=useState(null)
 const [accountDetailLoading,setAccountDetailLoading]=useState(false)
 const [accountDetailError,setAccountDetailError]=useState('')
 const [accountDetailTab,setAccountDetailTab]=useState('overview')
 const [passwordTarget,setPasswordTarget]=useState(null)
 const accountDetailRequestRef=useRef(0)
 const [apiForm,setApiForm]=useState({naverClientId:'',naverClientSecret:'',dartApiKey:'',geminiApiKey:'',finnhubApiKey:'',alphaVantageApiKey:'',secEdgarContact:''})
 const [apiBusy,setApiBusy]=useState('')
 const [starting,setStarting]=useState('')
 const [msg,setMsg]=useState('')
 const [showSyncWarnings,setShowSyncWarnings]=useState(false)
 const [syncMonitor,setSyncMonitor]=useState({degraded:false,lastCheckedAt:null,monitorMs:null,error:''})
 const [syncRefreshing,setSyncRefreshing]=useState(false)
 const [syncStopping,setSyncStopping]=useState(false)
 const [syncPollProblem,setSyncPollProblem]=useState('')
 const [themeNormalizeBusy,setThemeNormalizeBusy]=useState(false)
 const [themeNormalize,setThemeNormalize]=useState(null)
 const themeNormalizeCompletedRef=useRef('')
 const [scheduleEnabled,setScheduleEnabled]=useState(true)
 const [scheduleRunCount,setScheduleRunCount]=useState(1)
 const [scheduleTimes,setScheduleTimes]=useState(['22:00'])
 const [scheduleSaving,setScheduleSaving]=useState(false)
 const [scheduleScopes,setScheduleScopes]=useState(ADMIN_SYNC_SCOPE_KEYS)
 const [manualSyncOpen,setManualSyncOpen]=useState(false)
 const [manualSyncScopes,setManualSyncScopes]=useState(ADMIN_SYNC_SCOPE_KEYS)

 const syncWasRunningRef=useRef(false)
 const syncPollFailureRef=useRef(0)

 const applySyncOverview=data=>{
  if(!data||typeof data!=='object')return
  if(data.market)setMarket(data.market)
  if(data.theme_sync)setThemeSync(data.theme_sync)
  if(data.market_theme_sync)setMarketThemeSync(data.market_theme_sync)
  if(data.classification_sync)setClassificationSync(data.classification_sync)
  if(data.unified_sync)setUnifiedSync(data.unified_sync)
  if(data.theme_normalize)setThemeNormalize(data.theme_normalize)
  if(data.flow_sync)setFlowSync(data.flow_sync)
  if(data.kiwoom_runtime)setKiwoomRuntime(data.kiwoom_runtime)
  setSyncMonitor({
   degraded:Boolean(data.degraded),
   lastCheckedAt:Date.now(),
   monitorMs:Number(data.monitor_ms||0),
   error:data.degraded_reason||''
  })
  if(!data.degraded)setSyncPollProblem('')
 }

 const loadSyncOverview=()=>{
  // Page-global single-flight survives admin component remounts as well as poll ticks.
  // A slow status request can never overlap with another request in this browser tab.
  if(window.__stocklogSyncOverviewPromise)return window.__stocklogSyncOverviewPromise
  let request
  request=api.get('/api/admin/sync-overview',{timeout:8000,__stocklogNoRetry:true})
   .then(r=>{applySyncOverview(r.data);return r.data})
   .finally(()=>{if(window.__stocklogSyncOverviewPromise===request)window.__stocklogSyncOverviewPromise=null})
  window.__stocklogSyncOverviewPromise=request
  return request
 }

 const refreshSyncStatus=async()=>{
  setSyncRefreshing(true);setSyncPollProblem('')
  try{await loadSyncOverview()}
  catch(e){setSyncPollProblem(e.response?.data?.detail||'상태 연결이 잠시 지연되고 있습니다.')}
  finally{setSyncRefreshing(false)}
 }

 const load=async(includeExternal=true)=>{
  const overviewResult=await Promise.allSettled([loadSyncOverview()])
  const overviewItem=overviewResult[0]
  const overviewData=overviewItem?.status==='fulfilled'?overviewItem.value:null
  if(overviewItem?.status==='rejected'){
   if(!includeExternal)throw overviewItem.reason
   const detail=overviewItem.reason?.response?.data?.detail||'동기화 상태 조회가 지연되고 있습니다.'
   setSyncPollProblem(detail);setMsg(detail)
   return null
  }
  if(!includeExternal)return overviewData
  // Never create a login/admin-page burst against the main DB pool.  The
  // isolated sync monitor is read first; heavier static admin queries follow.
  // While any sync is running, defer those static counts until completion.
  const overviewRunning=Boolean(
   overviewData?.unified_sync?.running||overviewData?.market?.running||overviewData?.theme_sync?.running||
   overviewData?.market_theme_sync?.running||overviewData?.classification_sync?.running||
   overviewData?.flow_sync?.running||overviewData?.theme_normalize?.running
  )
  if(overviewRunning)return overviewData
  const req=[
   api.get('/api/admin/status',{timeout:10000,__stocklogNoRetry:true}),
   api.get('/api/admin/membership/features',{timeout:10000,__stocklogNoRetry:true}),
   api.get('/api/admin/membership/refresh-policy',{timeout:10000,__stocklogNoRetry:true}),
   api.get('/api/admin/external-apis',{timeout:10000,__stocklogNoRetry:true}),
   api.get('/api/admin/access-control',{timeout:10000,__stocklogNoRetry:true})
  ]
  const [status,features,refreshPolicy,external,access]=await Promise.allSettled(req)
  if(status.status==='fulfilled')setS(status.value.data)
  if(features.status==='fulfilled')setMembershipPolicy(features.value.data)
  if(refreshPolicy.status==='fulfilled')setRefreshPolicies(refreshPolicy.value.data)
  if(external.status==='fulfilled'&&external.value?.data)setExternalApis(external.value.data)
  if(access.status==='fulfilled'&&access.value?.data){
   const value=access.value.data
   setAccessControl(value)
   setAccessMode(value.mode==='allowlist'?'allowlist':'allow_all')
   setAccessIpsText(Array.isArray(value.allowed_ips)?value.allowed_ips.join('\n'):'')
  }
  const failed=[overviewResult[0],status,features,refreshPolicy].find(x=>x?.status==='rejected')
  if(failed)setMsg(failed.reason?.response?.data?.detail||'관리자 상태 일부를 불러오지 못했습니다.')
 }

 const loadSyncErrorLogs=async()=>{
  setSyncErrorLogsLoading(true)
  try{
   const r=await api.get('/api/admin/sync-error-logs',{params:{limit:80},timeout:10000,__stocklogNoRetry:true,__skipDiagnostic:true})
   setSyncErrorLogs(Array.isArray(r.data?.items)?r.data.items:[])
  }catch(e){
   setMsg(e.response?.data?.detail||'동기화 진단 로그 목록을 불러오지 못했습니다.')
  }finally{setSyncErrorLogsLoading(false)}
 }
 const saveBlob=(blob,filename)=>{
  const url=URL.createObjectURL(blob)
  const a=document.createElement('a');a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove()
  setTimeout(()=>URL.revokeObjectURL(url),1000)
 }
 const downloadSyncErrorLog=async filename=>{
  try{
   const r=await api.get(`/api/admin/sync-error-logs/${encodeURIComponent(filename)}`,{responseType:'blob',timeout:15000,__stocklogNoRetry:true,__skipDiagnostic:true})
   saveBlob(r.data,filename)
  }catch(e){
   setMsg(e.response?.data?.detail||'오류 로그 파일을 내려받지 못했습니다.')
  }
 }
 const downloadAllSyncErrorLogs=async()=>{
  try{
   const r=await api.get('/api/admin/sync-error-logs/download-all',{params:{limit:250},responseType:'blob',timeout:30000,__stocklogNoRetry:true,__skipDiagnostic:true})
   const stamp=new Date().toISOString().replace(/[-:T]/g,'').slice(0,14)
   saveBlob(r.data,`StockLog_sync_diagnostics_${stamp}.zip`)
  }catch(e){
   setMsg(e.response?.data?.detail||'동기화 진단 로그 ZIP을 내려받지 못했습니다.')
  }
 }

 const loadSocialAuth=async()=>{
  try{
   const r=await api.get('/api/admin/social-auth')
   const data=r.data||{}
   setSocialAuth(data)
   setSocialForm(v=>({
    ...v,
    kakaoRedirectUri:data.kakao?.redirect_uri||v.kakaoRedirectUri,
    kakaoEnabled:data.kakao?.enabled??v.kakaoEnabled,
    naverRedirectUri:data.naver?.redirect_uri||v.naverRedirectUri,
    naverEnabled:data.naver?.enabled??v.naverEnabled,
    googleRedirectUri:data.google?.redirect_uri||v.googleRedirectUri,
    googleEnabled:data.google?.enabled??v.googleEnabled
   }))
  }catch(e){
   setMsg(e.response?.data?.detail||'소셜 로그인 설정을 불러오지 못했습니다.')
  }
 }

 const loadAccounts=async()=>{
  setAccountLoading(true)
  try{
   const r=await api.get('/api/admin/users',{params:{page:accountPage,page_size:20,q:accountQuery,account_type:accountType}})
   setAccountUsers(r.data?.items||[])
   setAccountMeta({
    page:Number(r.data?.page||1),
    pages:Number(r.data?.pages||1),
    total:Number(r.data?.total||0),
    page_size:Number(r.data?.page_size||20),
    tier_counts:r.data?.tier_counts||{}
   })
   if(Number(r.data?.page||1)!==accountPage)setAccountPage(Number(r.data?.page||1))
  }catch(e){
   setMsg(e.response?.data?.detail||'계정 목록을 불러오지 못했습니다.')
  }finally{
   setAccountLoading(false)
  }
 }

 useEffect(()=>{load().catch(()=>{});loadSocialAuth().catch(()=>{});loadSyncErrorLogs().catch(()=>{})},[])
 useEffect(()=>{
  const onWindowError=event=>{
   const err=event?.error||new Error(event?.message||'window error')
   reportAdminDiagnostic('ADMIN_FRONTEND_WINDOW_ERROR',err,{filename:event?.filename||'',lineno:event?.lineno||0,colno:event?.colno||0}).catch(()=>{})
  }
  const onUnhandled=event=>{
   const reason=event?.reason instanceof Error?event.reason:new Error(String(event?.reason||'unhandled rejection'))
   reportAdminDiagnostic('ADMIN_FRONTEND_UNHANDLED_REJECTION',reason,{phase:'window_unhandledrejection'}).catch(()=>{})
  }
  window.addEventListener('error',onWindowError)
  window.addEventListener('unhandledrejection',onUnhandled)
  return()=>{window.removeEventListener('error',onWindowError);window.removeEventListener('unhandledrejection',onUnhandled)}
 },[])

 useEffect(()=>{
  const params=new URLSearchParams(window.location.search)
  const sessionId=params.get('social_test_session')
  if(!sessionId)return
  api.get(`/api/admin/social-auth/test-result/${sessionId}`).then(r=>{
   setMsg(r.data?.message||'소셜 로그인 연결 테스트를 완료했습니다.')
  }).catch(e=>{
   setMsg(e.response?.data?.detail||'소셜 로그인 연결 테스트 결과를 확인하지 못했습니다.')
  }).finally(()=>{
   loadSocialAuth().catch(()=>{})
   const url=new URL(window.location.href)
   url.searchParams.delete('social_test_session')
   window.history.replaceState({},'',`${url.pathname}${url.search}${url.hash}`)
  })
 },[])

 useEffect(()=>{
  const timer=setTimeout(()=>loadAccounts().catch(()=>{}),250)
  return()=>clearTimeout(timer)
 },[accountPage,accountQuery,accountType])
 useEffect(()=>{
  const running=Boolean(unifiedSync?.running||market?.running||themeSync?.running||marketThemeSync?.running||classificationSync?.running||flowSync?.running||themeNormalize?.running)
  if(!running){
   if(syncWasRunningRef.current){
    syncWasRunningRef.current=false
    // Refresh counts/policies once at completion; no periodic heavy polling.
    load(true).catch(()=>{})
    loadSyncErrorLogs().catch(()=>{})
   }
   return
  }
  syncWasRunningRef.current=true
  let stopped=false
  let timer=null
  const poll=async()=>{
   let delay=document.visibilityState==='visible'?3000:10000
   try{
   await load(false)
   syncPollFailureRef.current=0
   setSyncPollProblem('')
   }catch(e){
    syncPollFailureRef.current=Math.min(6,syncPollFailureRef.current+1)
    setSyncPollProblem(e.response?.data?.detail||'진행 상태 연결이 잠시 지연되고 있습니다.')
    delay=Math.min(20000,3000*Math.pow(2,syncPollFailureRef.current))
   }finally{if(!stopped)timer=setTimeout(poll,delay)}
  }
  timer=setTimeout(poll,1200)
  return()=>{stopped=true;if(timer)clearTimeout(timer)}
 },[unifiedSync?.running,market?.running,themeSync?.running,marketThemeSync?.running,classificationSync?.running,flowSync?.running,themeNormalize?.running])

 useEffect(()=>{
  if(themeNormalize?.phase!=='completed'||!themeNormalize?.finished_at)return
  if(themeNormalizeCompletedRef.current===themeNormalize.finished_at)return
  themeNormalizeCompletedRef.current=themeNormalize.finished_at
  window.dispatchEvent(new Event('stocklog:themes-normalized'))
 },[themeNormalize?.phase,themeNormalize?.finished_at])

 useEffect(()=>{
  const schedule=unifiedSync?.schedule
  if(!schedule)return
  const times=Array.isArray(schedule.run_times)&&schedule.run_times.length?schedule.run_times:['22:00']
  setScheduleEnabled(schedule.enabled!==false)
  setScheduleRunCount(Math.max(1,Math.min(6,Number(schedule.run_count||times.length||1))))
  setScheduleTimes(times.slice(0,6))
  setScheduleFlowUniverseLimit(Number(schedule.flow_universe_limit??0))
  setScheduleScopes(Array.isArray(schedule.scopes)&&schedule.scopes.length?schedule.scopes:ADMIN_SYNC_SCOPE_KEYS)
 },[unifiedSync?.schedule?.updated_at,unifiedSync?.schedule?.run_times?.join('|'),unifiedSync?.schedule?.scopes?.join('|')])

 const startMarket=async(type)=>{
  const label=type==='kiwoom'?'키움 시세':'DART 재무'
  if(!(await askConfirm(`${label} 동기화를 시작할까요?`,`${label} 동기화`,'warning')))return
  setStarting(type);setMsg('')
  try{
   const r=await api.post(`/api/admin/market-data/start/${type}`)
   setMsg(r.data.message);setTimeout(()=>load(false),400)
  }catch(e){setMsg(e.response?.data?.detail||`${label} 동기화 시작 실패`)}
  finally{setStarting('')}
 }
 const stopMarket=async()=>{
  try{const r=await api.post('/api/admin/market-data/stop');setMsg(r.data.message);setTimeout(()=>load(false),300)}
  catch(e){setMsg(e.response?.data?.detail||'동기화 중지 실패')}
 }
 const startTheme=async()=>{
  setStarting('themes');setMsg('')
  try{const r=await api.post('/api/admin/theme-sync/start');setMsg(r.data.message);setTimeout(()=>load(false),400)}
  catch(e){setMsg(e.response?.data?.detail||'키움 테마 동기화 시작 실패')}
  finally{setStarting('')}
 }
 const stopTheme=async()=>{
  try{const r=await api.post('/api/admin/theme-sync/stop');setMsg(r.data.message);setTimeout(()=>load(false),300)}
  catch(e){setMsg(e.response?.data?.detail||'키움 테마 중지 실패')}
 }
 const normalizeThemes=async()=>{
  if(!(await askConfirm('공급사 원본 테마를 보존한 채 StockLog 표준 테마 체계로 전체 종목을 다시 분류합니다. 반도체 > 팹리스/HBM, 화장품 > K-뷰티/ODM처럼 상위·세부 테마를 고정된 기준으로 재구축합니다. 진행할까요?','표준 테마 전체 재구축','warning')))return
  setThemeNormalizeBusy(true);setMsg('표준 테마 재구축을 시작하고 있습니다...')
  try{
   const r=await api.post('/api/admin/theme-normalize')
   setMsg(r.data?.message||'표준 테마 재구축을 시작했습니다.')
   await load(false)
   window.dispatchEvent(new Event('stocklog:themes-normalized'))
  }catch(e){setMsg(e.response?.data?.detail||'표준 테마 재구축을 시작하지 못했습니다.')}
  finally{setThemeNormalizeBusy(false)}
 }

 const startMarketTheme=async()=>{
  setStarting('market-themes');setMsg('')
  try{const r=await api.post('/api/admin/market-theme-sync/start');setMsg(r.data.message);setTimeout(()=>load(false),400)}
  catch(e){setMsg(e.response?.data?.detail||'시장 테마 동기화 시작 실패')}
  finally{setStarting('')}
 }
 const stopMarketTheme=async()=>{
  try{const r=await api.post('/api/admin/market-theme-sync/stop');setMsg(r.data.message);setTimeout(()=>load(false),300)}
  catch(e){setMsg(e.response?.data?.detail||'시장 테마 중지 실패')}
 }
 const startClassification=async()=>{
  setStarting('classification');setMsg('')
  try{const r=await api.post('/api/admin/classification-sync/start');setMsg(r.data.message);setTimeout(()=>load(false),400)}
  catch(e){setMsg(e.response?.data?.detail||'종목 분류 동기화 시작 실패')}
  finally{setStarting('')}
 }
 const stopClassification=async()=>{
  try{const r=await api.post('/api/admin/classification-sync/stop');setMsg(r.data.message);setTimeout(()=>load(false),300)}
  catch(e){setMsg(e.response?.data?.detail||'종목 분류 중지 실패')}
 }
 const startUnified=()=>{
  setManualSyncScopes(ADMIN_SYNC_SCOPE_KEYS)
  setManualSyncOpen(true)
 }
 const toggleScope=(list,setter,key)=>{
  setter(list.includes(key)?list.filter(x=>x!==key):[...list,key].filter(x=>ADMIN_SYNC_SCOPE_KEYS.includes(x)))
 }
 const runUnifiedSelected=async()=>{
  if(!manualSyncScopes.length){setMsg('동기화 항목을 하나 이상 선택해주세요.');return}
  setStarting('unified');setMsg('')
  try{
   const r=await api.post('/api/admin/unified-sync/start',{
    flow_universe_limit:Number(flowUniverseLimit),
    flow_history_days:20,
    scopes:manualSyncScopes
   })
   setManualSyncOpen(false)
   setMsg(r.data.message);setTimeout(()=>load(false),400)
  }catch(e){setMsg(e.response?.data?.detail||'전체 동기화 시작 실패')}
  finally{setStarting('')}
 }
 const startSingleScope=async key=>{
  const item=ADMIN_SYNC_SCOPES.find(x=>x.key===key)
  if(!item)return
  if(!(await askConfirm(`${item.label}만 지금 갱신할까요?`,item.label,'warning')))return
  setStarting(`scope-${key}`);setMsg('')
  try{
   const r=await api.post('/api/admin/unified-sync/start',{flow_universe_limit:Number(flowUniverseLimit),flow_history_days:20,scopes:[key]})
   setMsg(r.data?.message||`${item.label} 동기화를 시작했습니다.`);setTimeout(()=>load(false),350)
  }catch(e){setMsg(e.response?.data?.detail||`${item.label} 동기화 시작 실패`)}
  finally{setStarting('')}
 }
 const stopUnified=async()=>{
  setSyncStopping(true)
  try{const r=await api.post('/api/admin/unified-sync/stop');setMsg(r.data.message);setTimeout(()=>load(false),300)}
  catch(e){setMsg(e.response?.data?.detail||'전체 동기화 중지 실패')}
  finally{setTimeout(()=>setSyncStopping(false),700)}
 }

 const scheduleDefaults={
  1:['22:00'],
  2:['09:00','22:00'],
  3:['09:00','15:00','22:00'],
  4:['08:00','12:00','18:00','22:00'],
  5:['08:00','11:00','14:00','18:00','22:00'],
  6:['08:00','10:30','13:00','15:30','18:30','22:00']
 }
 const changeScheduleCount=value=>{
  const count=Math.max(1,Math.min(6,Number(value||1)))
  setScheduleRunCount(count)
  setScheduleTimes(prev=>{
   const next=[...prev]
   const defaults=scheduleDefaults[count]||scheduleDefaults[1]
   while(next.length<count)next.push(defaults[next.length]||'22:00')
   return next.slice(0,count)
  })
 }
 const saveSyncSchedule=async()=>{
  setScheduleSaving(true);setMsg('')
  try{
   const runTimes=scheduleTimes.slice(0,scheduleRunCount)
   if(!scheduleScopes.length){setMsg('자동 동기화 항목을 하나 이상 선택해주세요.');return}
   const r=await api.put('/api/admin/unified-sync/schedule',{
    enabled:scheduleEnabled,
    run_times:runTimes,
    flow_universe_limit:Number(scheduleFlowUniverseLimit),
    flow_history_days:20,
    scopes:scheduleScopes
   })
   setUnifiedSync(prev=>prev?{...prev,schedule:r.data?.schedule||prev.schedule}:prev)
   setMsg(r.data?.message||'자동 동기화 설정을 저장했습니다.')
  }catch(e){setMsg(e.response?.data?.detail||'자동 동기화 설정 저장에 실패했습니다.')}
  finally{setScheduleSaving(false)}
 }

 const saveExternalApi=async(provider)=>{
  const isNaver=provider==='naver';const isGemini=provider==='gemini';setApiBusy(`save-${provider}`);setMsg('')
  try{
   const keyByProvider={dart:apiForm.dartApiKey,gemini:apiForm.geminiApiKey,finnhub:apiForm.finnhubApiKey,alpha_vantage:apiForm.alphaVantageApiKey}
   const payload=isNaver
    ?{client_id:apiForm.naverClientId,client_secret:apiForm.naverClientSecret,enabled:true}
    :provider==='sec_edgar'?{client_id:apiForm.secEdgarContact,enabled:true}:{api_key:keyByProvider[provider]||'',enabled:true}
   const r=await api.put(`/api/admin/external-apis/${provider}`,payload)
   setMsg(r.data?.message||'API 설정을 저장했습니다.')
   const fieldByProvider={dart:'dartApiKey',gemini:'geminiApiKey',finnhub:'finnhubApiKey',alpha_vantage:'alphaVantageApiKey',sec_edgar:'secEdgarContact'}
   setApiForm(v=>isNaver?{...v,naverClientId:'',naverClientSecret:''}:{...v,[fieldByProvider[provider]]:''})
   await load()
  }catch(e){setMsg(e.response?.data?.detail||'API 설정 저장에 실패했습니다.')}
  finally{setApiBusy('')}
 }
 const saveExternalApiGroup=async(scope='domestic')=>{
  const providers=scope==='overseas'
   ?[{id:'finnhub',changed:apiForm.finnhubApiKey},{id:'alpha_vantage',changed:apiForm.alphaVantageApiKey},{id:'sec_edgar',changed:apiForm.secEdgarContact}]
   :[{id:'naver',changed:apiForm.naverClientId||apiForm.naverClientSecret},{id:'dart',changed:apiForm.dartApiKey},{id:'gemini',changed:apiForm.geminiApiKey}]
  const changed=providers.filter(row=>String(row.changed||'').trim())
  if(!changed.length){setMsg('변경할 API 값을 입력해주세요. 기존에 저장된 키는 그대로 유지됩니다.');return}
  const label=scope==='overseas'?'해외증권 분석 API':'외부 API / AI'
  if(!(await askConfirm(`${changed.length}개 API 설정을 암호화하여 일괄 저장합니다. 저장할까요?`,`${label} 저장`,'info')))return
  setApiBusy(`save-${scope}-group`);setMsg('')
  try{
   for(const row of changed){
    const provider=row.id
    const payload=provider==='naver'
     ?{client_id:apiForm.naverClientId,client_secret:apiForm.naverClientSecret,enabled:true}
     :provider==='sec_edgar'?{client_id:apiForm.secEdgarContact,enabled:true}
      :{api_key:{dart:apiForm.dartApiKey,gemini:apiForm.geminiApiKey,finnhub:apiForm.finnhubApiKey,alpha_vantage:apiForm.alphaVantageApiKey}[provider]||'',enabled:true}
    await api.put(`/api/admin/external-apis/${provider}`,payload)
   }
   setApiForm(v=>scope==='overseas'?{...v,finnhubApiKey:'',alphaVantageApiKey:'',secEdgarContact:''}:{...v,naverClientId:'',naverClientSecret:'',dartApiKey:'',geminiApiKey:''})
   setMsg(`${label} 변경사항 ${changed.length}개를 저장했습니다.`);await load()
  }catch(e){setMsg(e.response?.data?.detail||`${label} 일괄 저장에 실패했습니다.`)}
  finally{setApiBusy('')}
 }
 const testExternalApi=async(provider)=>{
  setApiBusy(`test-${provider}`);setMsg('')
  try{const r=await api.post(`/api/admin/external-apis/${provider}/test`);setMsg(r.data?.message||'연결 테스트에 성공했습니다.');await load()}
  catch(e){setMsg(e.response?.data?.detail||'연결 테스트에 실패했습니다.');await load().catch(()=>{})}
  finally{setApiBusy('')}
 }
 const removeExternalApi=async(provider)=>{
  if(!(await askConfirm('MySQL에 저장된 API 설정을 삭제할까요?','API 설정 삭제','warning')))return
  setApiBusy(`delete-${provider}`);setMsg('')
  try{const r=await api.delete(`/api/admin/external-apis/${provider}`);setMsg(r.data?.message||'삭제했습니다.');await load()}
  catch(e){setMsg(e.response?.data?.detail||'API 설정 삭제에 실패했습니다.')}
  finally{setApiBusy('')}
 }

 const saveSocialAuth=async provider=>{
  const map={
   kakao:{id:'kakaoClientId',secret:'kakaoClientSecret',redirect:'kakaoRedirectUri',enabled:'kakaoEnabled'},
   naver:{id:'naverClientId',secret:'naverClientSecret',redirect:'naverRedirectUri',enabled:'naverEnabled'},
   google:{id:'googleClientId',secret:'googleClientSecret',redirect:'googleRedirectUri',enabled:'googleEnabled'}
  }
  const f=map[provider];if(!f)return
  setSocialBusy(`save-${provider}`);setMsg('')
  try{
   const payload={client_id:socialForm[f.id],client_secret:socialForm[f.secret],redirect_uri:socialForm[f.redirect],enabled:socialForm[f.enabled]}
   const r=await api.put(`/api/admin/social-auth/${provider}`,payload)
   setMsg(r.data?.message||'소셜 로그인 설정을 저장했습니다.')
   setSocialForm(v=>({...v,[f.id]:'',[f.secret]:''}))
   await loadSocialAuth()
  }catch(e){setMsg(e.response?.data?.detail||'소셜 로그인 설정 저장에 실패했습니다.')}
  finally{setSocialBusy('')}
 }
 const saveAllSocialAuth=async()=>{
  const map={
   kakao:{id:'kakaoClientId',secret:'kakaoClientSecret',redirect:'kakaoRedirectUri',enabled:'kakaoEnabled',status:kakaoLogin},
   naver:{id:'naverClientId',secret:'naverClientSecret',redirect:'naverRedirectUri',enabled:'naverEnabled',status:naverLogin},
   google:{id:'googleClientId',secret:'googleClientSecret',redirect:'googleRedirectUri',enabled:'googleEnabled',status:googleLogin}
  }
  const targets=Object.entries(map).filter(([,f])=>f.status?.configured||String(socialForm[f.id]||'').trim()||String(socialForm[f.secret]||'').trim())
  if(!targets.length){setMsg('저장할 소셜 로그인 정보를 입력해주세요.');return}
  if(!(await askConfirm(`${targets.length}개 소셜 로그인 제공자의 입력값과 노출 설정을 한 번에 저장합니다. 계속할까요?`,'소셜 로그인 일괄 저장','info')))return
  setSocialBusy('save-all');setMsg('')
  try{
   for(const [provider,f] of targets){await api.put(`/api/admin/social-auth/${provider}`,{client_id:socialForm[f.id],client_secret:socialForm[f.secret],redirect_uri:socialForm[f.redirect],enabled:socialForm[f.enabled]})}
   setSocialForm(v=>({...v,kakaoClientId:'',kakaoClientSecret:'',naverClientId:'',naverClientSecret:'',googleClientId:'',googleClientSecret:''}))
   setMsg(`소셜 로그인 ${targets.length}개 설정을 일괄 저장했습니다.`);await loadSocialAuth()
  }catch(e){setMsg(e.response?.data?.detail||'소셜 로그인 일괄 저장에 실패했습니다.')}
  finally{setSocialBusy('')}
 }

 const confirmAdminSave=async(title,message,action)=>{
  if(await askConfirm(message,title,'info'))await action()
 }
 const testSocialAuth=async provider=>{
  setSocialBusy(`test-${provider}`);setMsg('')
  try{
   const r=await api.get(`/api/admin/social-auth/${provider}/test/start`,{params:{return_url:socialReturnUrl()}})
   if(!r.data?.authorization_url)throw new Error('authorization_url missing')
   window.location.assign(r.data.authorization_url)
  }catch(e){
   setMsg(e.response?.data?.detail||'소셜 로그인 연결 테스트를 시작하지 못했습니다.')
   setSocialBusy('')
  }
 }
 const removeSocialAuth=async provider=>{
  const label=provider==='kakao'?'카카오':provider==='naver'?'네이버':'구글'
  if(!(await askConfirm(`${label} 로그인 Client ID/Secret/Redirect URI 설정을 삭제할까요?`,'소셜 로그인 설정 삭제','warning')))return
  setSocialBusy(`delete-${provider}`);setMsg('')
  try{
   const r=await api.delete(`/api/admin/social-auth/${provider}`)
   setMsg(r.data?.message||'소셜 로그인 설정을 삭제했습니다.')
   await loadSocialAuth()
  }catch(e){setMsg(e.response?.data?.detail||'소셜 로그인 설정 삭제에 실패했습니다.')}
  finally{setSocialBusy('')}
 }

 const membershipLabels={NORMAL:'일반회원',PREMIUM:'프리미엄회원',EVENT:'이벤트회원',ADMIN:'관리자'}
 const changeMembership=async(account,nextTier)=>{
  const current=String(account.membership_tier||account.account_type||'NORMAL').toUpperCase()
  if(current===nextTier)return
  const nextLabel=membershipLabels[nextTier]||nextTier
  const warning=nextTier==='ADMIN'||current==='ADMIN'
  if(!(await askConfirm(
   `${account.display_name||account.username} 회원을 ${nextLabel} 등급으로 변경할까요?${nextTier==='ADMIN'?' 관리자 기능 전체에 접근할 수 있게 됩니다.':''}`,
   '회원 등급 변경',warning?'warning':'default'
  )))return
  setAccountBusy(String(account.id));setMsg('')
  try{
   const r=await api.patch(`/api/admin/users/${account.id}/membership`,{membership_tier:nextTier})
   setMsg(r.data?.message||'회원 등급을 변경했습니다.')
   await loadAccounts()
   if(accountDetail?.user?.id===account.id){const d=await api.get(`/api/admin/users/${account.id}/detail`);setAccountDetail(d.data||null)}
  }catch(e){setMsg(e.response?.data?.detail||'회원 등급 변경에 실패했습니다.')}
  finally{setAccountBusy('')}
 }
 const deleteMember=async account=>{
  const tier=String(account.membership_tier||account.account_type||'NORMAL').toUpperCase()
  const label=account.display_name||account.username
  if(!(await askConfirm(
   `${label} 회원을 탈퇴시킬까요? 소셜 로그인 연결, 투자성향, AI 사용내역, 키움 계정설정 등 회원 전용 데이터가 함께 삭제되며 되돌릴 수 없습니다.`,
   '회원 탈퇴 처리','warning'
  )))return
  if(tier==='ADMIN'&&!confirm(`${label} 계정은 관리자입니다. 정말 탈퇴 처리하시겠습니까?`))return
  setAccountBusy(String(account.id));setMsg('')
  try{
   const r=await api.delete(`/api/admin/users/${account.id}`)
   setMsg(r.data?.message||'회원을 탈퇴 처리했습니다.')
   if(accountDetail?.user?.id===account.id)closeMemberDetail()
   await loadAccounts()
  }catch(e){setMsg(e.response?.data?.detail||'회원 탈퇴 처리에 실패했습니다.')}
  finally{setAccountBusy('')}
 }

 const openMemberDetail=async account=>{
  const requestId=++accountDetailRequestRef.current
  setAccountDetail(null);setAccountDetailError('');setAccountDetailTab('overview');setAccountDetailLoading(true)
  try{
   const r=await api.get(`/api/admin/users/${account.id}/detail`)
   if(requestId===accountDetailRequestRef.current)setAccountDetail(r.data||null)
  }catch(e){if(requestId===accountDetailRequestRef.current)setAccountDetailError(e.response?.data?.detail||'회원 상세 정보를 불러오지 못했습니다.')}
  finally{if(requestId===accountDetailRequestRef.current)setAccountDetailLoading(false)}
 }
 const closeMemberDetail=()=>{accountDetailRequestRef.current+=1;setAccountDetail(null);setAccountDetailError('');setAccountDetailLoading(false);setAccountDetailTab('overview')}
 useEffect(()=>{
  if(!accountDetail&&!accountDetailLoading&&!accountDetailError)return
  const before=document.body.style.overflow
  document.body.style.overflow='hidden'
  const onKey=e=>{if(e.key==='Escape')closeMemberDetail()}
  window.addEventListener('keydown',onKey)
  return()=>{document.body.style.overflow=before;window.removeEventListener('keydown',onKey)}
 },[Boolean(accountDetail),accountDetailLoading,Boolean(accountDetailError)])

 const updatePolicyLocal=(tier,key,patch)=>{
  setMembershipPolicy(prev=>{
   if(!prev)return prev
   return {...prev,tiers:(prev.tiers||[]).map(t=>t.tier!==tier?t:{...t,features:{...t.features,[key]:{...t.features?.[key],...patch}}})}
  })
 }
 const saveMembershipPolicy=async()=>{
  if(!membershipPolicy)return
  setPolicySaving(true);setMsg('')
  try{
   const items=[]
   for(const tierRow of membershipPolicy.tiers||[]){
    if(tierRow.tier==='ADMIN')continue
    for(const key of membershipPolicy.feature_order||[]){
     const item=tierRow.features?.[key]
     if(!item)continue
     items.push({tier:tierRow.tier,feature_key:key,enabled:Boolean(item.enabled),limit_value:key==='ai_analysis'?Number(item.limit_value??5):null})
    }
   }
   const r=await api.put('/api/admin/membership/features',{items})
   setMembershipPolicy(r.data?.policy||membershipPolicy)
   setMsg('회원 등급별 기능 정책을 저장했습니다.')
   await loadAccounts()
  }catch(e){setMsg(e.response?.data?.detail||'회원 기능 정책 저장에 실패했습니다.')}
  finally{setPolicySaving(false)}
 }
 const updateRefreshPolicyLocal=(tier,key,value)=>{
  setRefreshPolicies(prev=>prev?{...prev,tiers:(prev.tiers||[]).map(row=>row.tier===tier?{...row,[key]:Math.max(0,Number(value||0))}:row)}:prev)
 }
 const saveRefreshPolicies=async()=>{
  if(!refreshPolicies)return
  setRefreshPolicySaving(true);setMsg('')
  try{
   const items=(refreshPolicies.tiers||[]).map(row=>({tier:row.tier,trading_seconds:Number(row.trading_seconds||0),theme_seconds:Number(row.theme_seconds||0)}))
   const r=await api.put('/api/admin/membership/refresh-policy',{items})
   setRefreshPolicies(r.data?.policy||refreshPolicies)
   setMsg('등급별 자동 새로고침 주기를 저장했습니다.')
  }catch(e){setMsg(e.response?.data?.detail||'자동 새로고침 정책 저장에 실패했습니다.')}
  finally{setRefreshPolicySaving(false)}
 }

 const accessIpItems=()=>String(accessIpsText||'').split(/[\s,]+/).map(x=>x.trim()).filter(Boolean)
 const addCurrentAccessIp=()=>{
  const current=String(accessControl?.current_ip||'').trim()
  if(!current||current==='확인 불가')return
  const items=accessIpItems()
  if(!items.includes(current))setAccessIpsText([...items,current].join('\n'))
 }
 const saveAccessControl=async()=>{
  const allowedIps=accessIpItems()
  if(accessMode==='allowlist'&&!allowedIps.length){setMsg('허용 IP만 접속하려면 IP 또는 CIDR을 1개 이상 입력해주세요.');return}
  if(accessMode==='allowlist'){
   const confirmed=await askConfirm(
    `허용 목록에 포함된 IP에만 StockLog 로그인 화면이 전달됩니다. 로그인 API와 실시간 기능도 함께 차단됩니다. 현재 접속 IP ${accessControl?.current_ip||'확인 불가'}가 반드시 목록에 있어야 합니다. 저장할까요?`,
    '접속 IP 제한 적용','warning'
   )
   if(!confirmed)return
  }else{
   if(!(await askConfirm('모든 IP에서 StockLog에 접속할 수 있도록 정책을 저장합니다. 계속할까요?','접속 정책 저장','info')))return
  }
  setAccessSaving(true);setMsg('')
  try{
   const r=await api.put('/api/admin/access-control',{mode:accessMode,allowed_ips:allowedIps})
   const value=r.data||{}
   setAccessControl(value)
   setAccessMode(value.mode==='allowlist'?'allowlist':'allow_all')
   setAccessIpsText(Array.isArray(value.allowed_ips)?value.allowed_ips.join('\n'):'')
   setMsg(value.message||'접속 IP 설정을 저장했습니다.')
  }catch(e){setMsg(publicUiText(e.response?.data?.detail)||'접속 IP 설정 저장에 실패했습니다.')}
  finally{setAccessSaving(false)}
 }

 const startFlowSync=async()=>{
  const label=flowUniverseLimit===0?'전체 분석 종목':`시가총액 상위 ${Number(flowUniverseLimit).toLocaleString()}종목`
  if(!(await askConfirm(`${label}의 최근 20거래일 투자자 수급을 순차 수집합니다. 모의투자 동일 TR 제한 때문에 시간이 걸릴 수 있습니다. 시작할까요?`,'수급 데이터 동기화','warning')))return
  setFlowBusy(true);setMsg('')
  try{
   const r=await api.post('/api/admin/flow-sync/start',{universe_limit:Number(flowUniverseLimit),history_days:20})
   setFlowSync(r.data?.status||null);setMsg(r.data?.message||'수급 동기화를 시작했습니다.')
  }catch(e){setMsg(e.response?.data?.detail||'수급 동기화를 시작하지 못했습니다.')}
  finally{setFlowBusy(false)}
 }
 const stopFlowSync=async()=>{
  setFlowBusy(true)
  try{const r=await api.post('/api/admin/flow-sync/stop');setFlowSync(r.data?.status||null);setMsg(r.data?.message||'수급 동기화 중지를 요청했습니다.')}
  catch(e){setMsg(e.response?.data?.detail||'수급 동기화 중지에 실패했습니다.')}
  finally{setFlowBusy(false)}
 }

 const fmtTime=v=>v?new Date(v).toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'-'
 const fmtShort=v=>v?new Date(v).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'-'
 const universeInfo=market?.provider_status?.universe||{}
 const marketKiwoomStats=market?.provider_status?.kiwoom||{}
 const marketDartStats=market?.provider_status?.dart||{}
 const marketQuality={
  skipped:Number(marketKiwoomStats?.skipped||0)+Number(marketDartStats?.skipped||0),
  cached:Number(marketDartStats?.cached||0),
  retried:Number(marketKiwoomStats?.retried||0)+Number(marketDartStats?.retried||0),
  recovered:Number(marketKiwoomStats?.transient_recovered||0)+Number(marketDartStats?.transient_recovered||0),
  deferred:Number(marketDartStats?.deferred||0),
 }
 const flowMeta=flowSync?.provider_status||{}
 const flowSelectedTotal=Number(flowMeta.selected_total||flowSync?.total||0)
 const flowEligibleTotal=Number(flowMeta.eligible_total||0)
 const flowMissingData=Number(flowMeta.missing_data||0)
 const flowHardFailed=Number(flowSync?.failed||0)
 const flowCoverage=Number(flowMeta.selected_coverage_percent||0)
 const flowOutsideSelection=Number(flowMeta.outside_selection||0)
 const themeEngineMeta=themeNormalize?.provider_status||{}
 const themeEngineTotal=Number(themeEngineMeta.classification_total||0)
 const themeEngineClassified=Number(themeEngineMeta.engine_classified||themeEngineMeta.classified||0)
 const themeEngineStrong=Number(themeEngineMeta.strong_classified||0)
 const themeEngineFallback=Number(themeEngineMeta.fallback_classified||0)
 const themeEngineNoTheme=Number(themeEngineMeta.no_theme??themeEngineMeta.unresolved??0)
 const themeEngineErrors=Number(themeEngineMeta.errors||themeNormalize?.failed||0)
 const themeEngineCoverage=Number(themeEngineMeta.classification_coverage||(themeEngineTotal>0?(themeEngineClassified/themeEngineTotal)*100:0))
 const counts=universeInfo?.markets||s?.markets||{}
 const rawUniverse=Number(universeInfo?.raw_total||universeInfo?.total||s?.raw_stocks||s?.stocks||0)
 const analysisUniverse=Number(universeInfo?.analysis_total||s?.stocks||0)
 const excludedUniverse=Number(universeInfo?.excluded_total||Math.max(0,rawUniverse-analysisUniverse))
 const naverUsage=externalApis?.naver?.usage||{}
 const dartUsage=externalApis?.dart?.usage||{}
 const geminiUsage=externalApis?.gemini?.usage||{}
 const kakaoLogin=socialAuth?.kakao||{}
 const naverLogin=socialAuth?.naver||{}
 const googleLogin=socialAuth?.google||{}
 const socialStatusLabel=value=>value==='success'?'연결 확인':value==='failed'?'테스트 실패':value==='untested'?'테스트 필요':'미설정'
 const anyRunning=Boolean(unifiedSync?.running||market?.running||themeSync?.running||marketThemeSync?.running||classificationSync?.running||flowSync?.running||themeNormalize?.running)
 const inferSyncSeverity=item=>{
  if(['success','info','retry','error'].includes(item?.severity))return item.severity
  const message=String(item?.message||'')
  if(/(?:오류|실패)\s*[1-9]/.test(message)||message.includes('확인 필요'))return 'error'
  if(message.includes('다음회차 보강')&&!/다음회차 보강\s*0/.test(message))return 'retry'
  return item?.status==='partial'||Number(item?.warning_count||0)>0?'info':'success'
 }
 const syncResultText=(item,fallback='동기화 결과 안내')=>{
  const text=publicUiText(item?.message||fallback).replace(/\s*\/\s*/g,' · ')
  if(text.includes('일부 종목 확인 필요'))return Number(item?.warning_count||0)>0?`완료 · 일부 오류 ${Number(item.warning_count).toLocaleString()}개`:'완료 · 일부 오류'
  return text
 }
 const unifiedSteps=(Array.isArray(unifiedSync?.steps)?unifiedSync.steps:[]).map(x=>({...x,severity:inferSyncSeverity(x)}))
 const unifiedStepMap=Object.fromEntries(unifiedSteps.map(x=>[x.key,x]))
 const syncWarnings=(unifiedSync?.warnings||[]).map(x=>({...x,severity:inferSyncSeverity(x)}))
 const unifiedDoneWithWarnings=unifiedSync?.phase==='success_with_warnings'
 const syncIssueCount=Number(unifiedSync?.issue_count??syncWarnings.filter(x=>x.severity==='error').length)
 const syncRetryCount=Number(unifiedSync?.retry_count??syncWarnings.filter(x=>x.severity==='retry').length)
 const syncNoticeCount=Number(unifiedSync?.notice_count??syncWarnings.filter(x=>x.severity==='info').length)
 const runningUnifiedStep=unifiedSteps.find(x=>x.status==='running')||null
 const liveSync=market?.running?market:themeSync?.running?themeSync:marketThemeSync?.running?marketThemeSync:classificationSync?.running?classificationSync:themeNormalize?.running?themeNormalize:flowSync?.running?flowSync:null
 const liveSyncLabel=market?.running?(market?.job_type==='dart'?'DART 재무':'키움 시세'):themeSync?.running?'키움 테마':marketThemeSync?.running?'시장 테마':classificationSync?.running?'종목 분류':themeNormalize?.running?'표준 테마':flowSync?.running?'수급 데이터':runningUnifiedStep?.label||unifiedSync?.stage_label||'동기화'
 const liveStageProgress=Math.max(0,Math.min(100,Number(liveSync?.progress??runningUnifiedStep?.progress??unifiedSync?.progress??0)))
 const selectedRunSteps=unifiedSteps.filter(x=>x.selected!==false&&x.status!=='skipped')
 const unifiedLiveProgress=(()=>{
  if(!unifiedSync?.running)return Math.max(0,Math.min(100,Number(unifiedSync?.progress||0)))
  if(!selectedRunSteps.length)return Math.max(0,Math.min(100,Number(unifiedSync?.progress||0)))
  const completed=selectedRunSteps.filter(x=>['done','partial'].includes(x.status)).length
  const active=selectedRunSteps.some(x=>x.status==='running')?liveStageProgress/100:0
  return Math.max(0,Math.min(100,((completed+active)/selectedRunSteps.length)*100))
 })()
 const liveDone=Number(liveSync?.item_completed??unifiedSync?.item_completed??0)
 const liveTotal=Number(liveSync?.item_total??unifiedSync?.item_total??0)
 const liveEta=Math.max(0,Number(liveSync?.eta_seconds??unifiedSync?.eta_seconds??0))
 const liveEtaLabel=liveEta>0?(liveEta>=3600?`${Math.floor(liveEta/3600)}시간 ${Math.ceil((liveEta%3600)/60)}분`:`${Math.max(1,Math.ceil(liveEta/60))}분`):'-'
 const liveUpdatedAt=liveSync?.updated_at||unifiedSync?.updated_at||null
 const liveUpdatedMs=liveUpdatedAt?new Date(liveUpdatedAt).getTime():NaN
 const liveUpdateAge=Number.isFinite(liveUpdatedMs)?Math.max(0,Math.floor((Date.now()-liveUpdatedMs)/1000)):null
 const liveFreshnessLabel=liveUpdateAge==null?'-':liveUpdateAge<5?'방금':liveUpdateAge<60?`${liveUpdateAge}초 전`:`${Math.floor(liveUpdateAge/60)}분 전`
 const syncMonitorDelayed=Boolean(syncMonitor.degraded||syncPollProblem||(anyRunning&&liveUpdateAge!=null&&liveUpdateAge>90))
 const liveCurrentName=liveSync?.current_name||unifiedSync?.current_name||''
 const liveCurrentCode=liveSync?.current_code||unifiedSync?.current_code||''
 const liveItem=liveCurrentName?(liveCurrentCode?`${liveCurrentName} (${liveCurrentCode})`:liveCurrentName):''
 const unifiedStepProgress=x=>{
  if(x?.status!=='running')return Number(x?.progress||0)
  if(['kiwoom','dart'].includes(x.key)&&market?.running)return Number(market?.progress||0)
  if(x.key==='kiwoom_themes'&&themeSync?.running)return Number(themeSync?.progress||0)
  if(x.key==='market_themes'&&marketThemeSync?.running)return Number(marketThemeSync?.progress||0)
  if(x.key==='classification'&&classificationSync?.running)return Number(classificationSync?.progress||0)
  if(x.key==='theme_engine'&&themeNormalize?.running)return Number(themeNormalize?.progress||0)
  if(x.key==='flow'&&flowSync?.running)return Number(flowSync?.progress||0)
  return Number(x?.progress||0)
 }
 const syncStatusLabel=(status,severity)=>status==='partial'?({error:'일부 오류',retry:'자동 보완',info:'완료'}[severity]||'완료 · 안내'):({done:'완료',running:'진행 중',failed:'실패',skipped:'이번 실행 제외',not_run:'미실행',cancelled:'중지',pending:'대기'}[status]||'대기')
 const syncStatusClass=(status,severity)=>status==='done'||(status==='partial'&&severity==='info')?'done':status==='partial'?'partial':status==='running'?'running':status==='failed'?'failed':status==='skipped'?'skipped':status==='cancelled'?'cancelled':'pending'
 const currentRunScopeCount=Array.isArray(unifiedSync?.selected_scopes)?unifiedSync.selected_scopes.length:selectedRunSteps.length
 const overallSyncState=!unifiedSync?'불러오는 중':anyRunning?(unifiedSync?.phase==='stopping'?'중지 중':'진행 중'):unifiedSync?.phase==='failed'?'실패':unifiedSync?.phase==='interrupted'?'이전 실행 종료':unifiedSync?.phase==='cancelled'?'중지':unifiedDoneWithWarnings?(syncIssueCount?'완료 · 일부 오류':syncRetryCount?'완료 · 자동 보완 예정':'완료'):unifiedSync?.phase==='completed'?'완료':'실행 기록 없음'
 const overallSyncTone=anyRunning?'running':unifiedSync?.phase==='failed'?'failed':syncIssueCount?'partial':unifiedSync?.phase==='completed'||unifiedDoneWithWarnings?'done':'idle'
 const connectedApis=Number(Boolean(externalApis?.naver?.configured))+Number(Boolean(externalApis?.dart?.configured))+Number(Boolean(externalApis?.gemini?.configured))
 const autoSyncRunning=Boolean(unifiedSync?.running&&unifiedSync?.trigger==='schedule')
 const rawAutoRuntimeMessage=unifiedSync?.auto_scheduler_message||''
 const autoRuntimeMessage=!autoSyncRunning&&rawAutoRuntimeMessage.includes('실행 중')?`최근 자동 동기화는 ${fmtTime(unifiedSync?.finished_at)}에 종료되었습니다.`:rawAutoRuntimeMessage

 return <>
  {(accountDetail||accountDetailLoading||accountDetailError)&&<AdminMemberDetailModal detail={accountDetail} loading={accountDetailLoading} error={accountDetailError} tab={accountDetailTab} setTab={setAccountDetailTab} onClose={closeMemberDetail}/>}
  {passwordTarget&&<AdminPasswordModal target={passwordTarget} currentUser={currentUser} onClose={()=>setPasswordTarget(null)} onSaved={message=>setMsg(message)}/>} 
  {manualSyncOpen&&createPortal(<div className="admin-sync-modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&starting!=='unified')setManualSyncOpen(false)}}>
   <div className="admin-sync-modal" role="dialog" aria-modal="true" aria-label="전체 동기화 항목 선택">
    <div className="admin-sync-modal-head"><div><small>MANUAL SYNC</small><h3>전체 동기화 실행</h3></div><button type="button" className="admin-sync-modal-close" disabled={starting==='unified'} onClick={()=>setManualSyncOpen(false)}><X size={18}/></button></div>
    <div className="admin-sync-modal-toolbar"><span><b>{manualSyncScopes.length}</b>개 항목 선택</span><button type="button" onClick={()=>setManualSyncScopes(manualSyncScopes.length===ADMIN_SYNC_SCOPE_KEYS.length?[]:ADMIN_SYNC_SCOPE_KEYS)}>{manualSyncScopes.length===ADMIN_SYNC_SCOPE_KEYS.length?'선택 해제':'전체 선택'}</button></div>
    <div className="admin-sync-scope-picker">
     {ADMIN_SYNC_SCOPES.map((item,i)=><label key={item.key} className={manualSyncScopes.includes(item.key)?'selected':''}>
      <input type="checkbox" checked={manualSyncScopes.includes(item.key)} onChange={()=>toggleScope(manualSyncScopes,setManualSyncScopes,item.key)}/>
      <span className="admin-sync-check"><CheckCircle2 size={16}/></span>
      <span className="admin-sync-scope-copy"><small>{String(i+1).padStart(2,'0')}</small><b>{item.label}</b><em>{item.hint}</em></span>
     </label>)}
    </div>
    {manualSyncScopes.includes('flow')&&<div className="admin-sync-modal-flow"><span><small>수급 범위</small><b>{flowUniverseLimit===0?'전체 분석종목':`상위 ${Number(flowUniverseLimit).toLocaleString()}종목`}</b><em>{flowUniverseLimit===0?'모든 분석 대상 종목의 수급을 수집합니다.':'선택 범위 밖 종목은 분석 시 필요한 경우 자동 보충 수집합니다.'}</em></span><select value={flowUniverseLimit} onChange={e=>setFlowUniverseLimit(Number(e.target.value))}><option value={0}>전체 분석종목</option><option value={300}>상위 300종목</option><option value={800}>상위 800종목</option><option value={1500}>상위 1,500종목</option></select></div>}
    <div className="admin-sync-modal-actions"><button type="button" className="secondary" disabled={starting==='unified'} onClick={()=>setManualSyncOpen(false)}>취소</button><button type="button" className="primary" disabled={!manualSyncScopes.length||starting==='unified'} onClick={runUnifiedSelected}>{starting==='unified'?'시작 중...':`${manualSyncScopes.length}개 항목 실행`}</button></div>
   </div>
  </div>,document.body)}
  <div className="page-head admin-page-head">
   <div><span>ADMIN</span><h1>관리자</h1></div>
   <button className="secondary admin-refresh" onClick={()=>{load();loadAccounts();loadSocialAuth()}} disabled={!!apiBusy||!!accountBusy}><RefreshCw size={15}/>새로고침</button>
  </div>

  <div className="admin-summary-bar">
   <div><small>분석 대상 종목</small><b>{s?analysisUniverse.toLocaleString():'—'}</b><em>{s?`KOSPI·KOSDAQ 일반 상장종목 / 원본 ${rawUniverse.toLocaleString()} / 제외 ${excludedUniverse.toLocaleString()}`:'데이터를 불러오는 중입니다.'}</em></div>
   <div><small>테마</small><b>{s?Number((s?.kiwoom_themes||0)+(s?.market_themes||0)).toLocaleString():'—'}</b><em>{s?'키움 + 시장 테마':'데이터를 불러오는 중입니다.'}</em></div>
   <div><small>분류 커버리지</small><b>{s?`${Number(s?.classification_coverage_percent||0).toFixed(1)}%`:'—'}</b><em>{s?'활성 종목 기준':'데이터를 불러오는 중입니다.'}</em></div>
   <div><small>외부 API</small><b>{externalApis?`${connectedApis}/3`:'—'}</b><em>{!externalApis?'연결 상태를 불러오는 중입니다.':connectedApis===3?'정상 연동':`${3-connectedApis}개 기능 미연결`}</em></div>
  </div>

  <div className="admin-fold-list">
  <AdminFold title="접속 IP 관리" subtitle="StockLog 전체 접속 허용 범위" className="admin-access-control" badge={accessMode==='allowlist'?`허용 IP ${accessIpItems().length}개`:'모두 허용'}>
   {!accessControl?<div className="admin-account-loading">접속 정책을 불러오는 중...</div>:<div className="admin-access-control-body">
    <div className="admin-access-mode-grid" role="radiogroup" aria-label="StockLog 접속 정책">
     <button type="button" role="radio" aria-checked={accessMode==='allow_all'} className={accessMode==='allow_all'?'active':''} onClick={()=>setAccessMode('allow_all')}>
      <span><Users size={18}/></span><div><b>모두 허용</b><small>현재처럼 모든 IP에서 로그인과 서비스를 사용할 수 있습니다.</small></div><i>{accessMode==='allow_all'?<CheckCircle2 size={17}/>:null}</i>
     </button>
     <button type="button" role="radio" aria-checked={accessMode==='allowlist'} className={accessMode==='allowlist'?'active restricted':''} onClick={()=>setAccessMode('allowlist')}>
      <span><LockKeyhole size={18}/></span><div><b>허용 IP만 접속</b><small>미허용 IP에는 로그인 화면도 표시하지 않고 전체 접속을 차단합니다.</small></div><i>{accessMode==='allowlist'?<CheckCircle2 size={17}/>:null}</i>
     </button>
    </div>
    <div className="admin-access-current">
     <div><small>현재 관리자 접속 IP</small><b>{accessControl.current_ip||'확인 불가'}</b><span>서버가 프록시를 거쳐 확인한 실제 접속 주소입니다.</span></div>
     <button type="button" className="secondary" disabled={!accessControl.current_ip||accessControl.current_ip==='확인 불가'||accessIpItems().includes(accessControl.current_ip)} onClick={addCurrentAccessIp}>{accessIpItems().includes(accessControl.current_ip)?'목록에 포함됨':'현재 IP 추가'}</button>
    </div>
    <label className={`admin-access-rules ${accessMode==='allow_all'?'disabled':''}`}>
     <span><b>허용 IP 또는 CIDR</b><small>한 줄에 하나씩 입력하세요. 예: 203.0.113.10 또는 192.168.0.0/24</small></span>
     <textarea rows="6" spellCheck="false" disabled={accessMode==='allow_all'} value={accessIpsText} onChange={e=>setAccessIpsText(e.target.value)} placeholder={'203.0.113.10\n192.168.0.0/24'}/>
    </label>
    <div className={`admin-access-notice ${accessMode==='allowlist'?'warning':'safe'}`}>
     {accessMode==='allowlist'?<AlertTriangle size={17}/>:<ShieldCheck size={17}/>}<span><b>{accessMode==='allowlist'?'저장 즉시 로그인 화면부터 접속 제한이 적용됩니다.':'현재 제한 미적용: 모든 IP에서 로그인할 수 있습니다.'}</b><small>{accessMode==='allowlist'?'현재 관리자 IP가 허용 규칙에 포함되지 않으면 서버가 저장을 거부합니다. 서버 내부 복구를 위해 루프백 접속은 항상 허용됩니다.':'허용 IP를 입력하고 ‘허용 IP만 접속’을 선택한 뒤 반드시 접속 정책을 저장해야 차단이 시작됩니다.'}</small></span>
    </div>
    <div className="admin-access-actions"><span>{accessControl.updated_at?`최근 저장 ${new Date(accessControl.updated_at).toLocaleString('ko-KR')}`:'아직 별도로 저장된 정책이 없습니다.'}</span><button type="button" className="primary" disabled={accessSaving||(accessMode==='allowlist'&&!accessIpItems().length)} onClick={saveAccessControl}>{accessSaving?'저장 중...':'접속 정책 저장'}</button></div>
   </div>}
  </AdminFold>



  <AdminFold title="데이터 동기화" subtitle="전체·선택·자동 동기화" className="admin-sync-hub admin-sync-hub-v2" badge={unifiedSync?.running?`${unifiedLiveProgress.toFixed(0)}%`:overallSyncState}>
   <div className="admin-sync-v2-head">
    <div><span className={`admin-sync-v2-state ${overallSyncTone}`}></span><div><small>최근 실행</small><b>{overallSyncState}</b></div></div>
    <div className="admin-sync-v2-head-meta"><span><small>최근 실행 완료</small><b>{fmtTime(unifiedSync?.last_success_at)}</b></span><span><small>다음 자동 실행</small><b>{scheduleEnabled?fmtTime(unifiedSync?.schedule?.next_run_at):'사용 안 함'}</b></span></div>
    <div className="admin-sync-v2-actions"><button type="button" className="secondary admin-sync-status-refresh" aria-label="동기화 상태 새로고침" title="상태 새로고침" disabled={syncRefreshing} onClick={refreshSyncStatus}><RefreshCw size={14} className={syncRefreshing?'spin':''}/></button>{unifiedSync?.running?<button className="secondary danger-outline" disabled={syncStopping} onClick={stopUnified}>{syncStopping||unifiedSync?.phase==='stopping'?'중지 중...':'동기화 중지'}</button>:anyRunning?<button className="secondary" disabled>개별 작업 진행 중</button>:<button className="primary" disabled={!unifiedSync||starting==='unified'} onClick={startUnified}>전체 동기화</button>}</div>
    <div className="admin-sync-v2-overall-bar"><i style={{width:`${Math.min(100,unifiedSync?.running?unifiedLiveProgress:Number(unifiedSync?.progress||0))}%`}}/></div>
   </div>

   {syncMonitorDelayed&&<div className="admin-sync-monitor-note"><AlertTriangle size={16}/><div><b>{anyRunning?'진행 상태 표시가 지연되고 있습니다.':'상태 연결이 잠시 지연됐습니다.'}</b><span>{anyRunning?'서버 작업은 계속 실행됩니다. 최신 진행률을 다시 불러올 수 있습니다.':'마지막으로 받은 상태를 표시하고 있습니다.'}</span></div><button type="button" className="secondary" disabled={syncRefreshing} onClick={refreshSyncStatus}>{syncRefreshing?'확인 중...':'다시 확인'}</button></div>}

   {(unifiedSync?.running||liveSync?.running)&&<div className="admin-sync-liveboard admin-sync-liveboard-v2">
    <div className="admin-sync-live-head"><div><span className="admin-sync-live-pulse"></span><small>진행 중</small><b>{liveSyncLabel}</b></div><strong>{unifiedLiveProgress.toFixed(1)}%</strong></div>
    <div className="admin-sync-live-body-v2">
     <div className="admin-sync-current-item"><small>현재 처리</small><b>{liveItem||liveSync?.stage_label||runningUnifiedStep?.message||'작업 준비 중'}</b>{(liveSync?.message||runningUnifiedStep?.message)&&<span>{publicUiText(liveSync?.message||runningUnifiedStep?.message)}</span>}</div>
     <div className="admin-sync-live-kpi"><span><small>단계</small><b>{liveStageProgress.toFixed(1)}%</b></span><span><small>처리</small><b>{liveTotal>0?`${liveDone.toLocaleString()} / ${liveTotal.toLocaleString()}`:'-'}</b></span><span><small>예상 잔여</small><b>{liveEtaLabel}</b></span><span className={liveUpdateAge!=null&&liveUpdateAge>90?'stale':''}><small>마지막 진행</small><b>{liveFreshnessLabel}</b></span></div>
    </div>
    <div className="admin-sync-live-progress"><i style={{width:`${liveStageProgress}%`}}/></div>
   </div>}

   <div className="admin-sync-section-title"><div><b>동기화 항목</b><span>이번 실행 상태만 표시합니다.</span></div><small>{currentRunScopeCount||0}개 선택 실행</small></div>
   <div className="admin-sync-step-grid-v2">
    {ADMIN_SYNC_SCOPES.map((item,i)=>{const runStep=unifiedStepMap[item.key];const status=runStep?.status||'pending';const severity=runStep?.severity||'success';const progress=unifiedStepProgress(runStep);return <article key={item.key} className={`admin-sync-step-v2 ${syncStatusClass(status,severity)}`}>
     <div className="admin-sync-step-v2-top"><span>{String(i+1).padStart(2,'0')}</span><em>{syncStatusLabel(status,severity)}</em></div>
     <b>{item.label}</b>
     <small>{status==='running'?`${progress.toFixed(0)}% 진행 중`:runStep?.finished_at?`이번 실행 ${fmtShort(runStep.finished_at)}`:status==='skipped'?'이번 실행에서 제외':'이번 실행 기록 없음'}</small>
     {runStep?.message&&status!=='running'&&<span className="admin-sync-step-message">{syncResultText(runStep)}</span>}
     {status==='running'&&<div className="admin-sync-step-mini-bar"><i style={{width:`${progress}%`}}/></div>}
     <button type="button" className="secondary" disabled={anyRunning||!!starting} onClick={()=>startSingleScope(item.key)}>{starting===`scope-${item.key}`?'시작 중...':runStep?.finished_at?'다시 실행':'이 항목만 실행'}</button>
    </article>})}
   </div>

   {!unifiedSync?.running&&syncWarnings.length>0&&<section className={`admin-sync-result-summary ${syncIssueCount?'has-issues':'informational'}`}>
    <div className="admin-sync-result-head">{syncIssueCount?<AlertTriangle size={17}/>:<CheckCircle2 size={17}/>}<div><b>{syncIssueCount?`완료 · 일부 오류 ${syncIssueCount}단계`:syncRetryCount?`완료 · ${syncRetryCount}단계 자동 보완 예정`:'정상 완료 · 데이터 없음 항목 포함'}</b><span>{syncIssueCount?'정상 저장된 데이터는 유지됩니다. 오류가 있는 항목만 다시 실행할 수 있습니다.':syncRetryCount?'일시적으로 받지 못한 항목은 다음 실행에서 자동으로 보완합니다.':`공급사에 데이터가 없는 ${syncNoticeCount||syncWarnings.length}단계는 오류가 아닙니다.`}</span></div><button type="button" onClick={()=>setShowSyncWarnings(v=>!v)}>{showSyncWarnings?'상세 접기':'결과 상세'}</button></div>
    {showSyncWarnings&&<div className="admin-sync-result-detail">{syncWarnings.map((w,i)=><div key={w.key||i}><span className={`admin-sync-result-tag ${w.severity||'info'}`}>{w.severity==='error'?'일부 오류':w.severity==='retry'?'자동 보완':'안내'}</span><b>{w.label}</b><p>{syncResultText(w,'동기화 결과에 일부 안내가 있습니다.')}</p></div>)}</div>}
   </section>}

   <section className="admin-auto-sync-v2 admin-auto-sync-v3">
    <div className="admin-auto-sync-v2-head">
     <div><CalendarClock size={18}/><span><small>자동 전체 동기화</small><b>{scheduleEnabled?'자동 실행 사용 중':'자동 실행 꺼짐'}</b></span></div>
     <div className="admin-auto-sync-head-right"><span><small>다음 실행</small><b>{scheduleEnabled?fmtTime(unifiedSync?.schedule?.next_run_at):'-'}</b></span><label className="admin-sync-switch"><input type="checkbox" checked={scheduleEnabled} onChange={e=>setScheduleEnabled(e.target.checked)}/><i></i></label></div>
    </div>
    {autoRuntimeMessage&&<div className={`admin-auto-sync-runtime ${unifiedSync?.auto_pending_slot?'waiting':autoSyncRunning?'running':'ok'}`}><span className="admin-auto-sync-runtime-dot"></span><div><b>{unifiedSync?.auto_pending_slot?'대기 중인 자동 실행':autoSyncRunning?'자동 실행 진행 중':'최근 자동 실행'}</b><small>{autoRuntimeMessage}</small></div></div>}
    <div className="admin-auto-sync-config-grid">
     <div className="admin-auto-sync-count-card">
      <div className="admin-auto-sync-field-head"><span><small>하루 실행 횟수</small><b>{scheduleRunCount}회</b></span><small>원하는 횟수만큼 시간을 따로 지정합니다.</small></div>
      <div className="admin-auto-sync-count-buttons">{[1,2,3,4,5,6].map(n=><button type="button" key={n} className={scheduleRunCount===n?'active':''} disabled={scheduleSaving} onClick={()=>changeScheduleCount(n)}>{n}회</button>)}</div>
     </div>
     {scheduleScopes.includes('flow')&&<label className="admin-auto-flow-range admin-auto-flow-range-v3"><span><small>수급 데이터 범위</small><b>한 번에 가져올 종목</b></span><select value={scheduleFlowUniverseLimit} disabled={scheduleSaving||anyRunning} onChange={e=>setScheduleFlowUniverseLimit(Number(e.target.value))}><option value={0}>전체 분석종목</option><option value={300}>상위 300종목</option><option value={800}>상위 800종목</option><option value={1500}>상위 1,500종목</option></select></label>}
    </div>
    <div className="admin-auto-sync-times-panel">
     <div className="admin-auto-sync-times-head"><span><small>실행 시간</small><b>각 회차가 시작될 시간을 정해주세요.</b></span><small>한국 시간 기준</small></div>
     <div className="admin-auto-sync-times-grid">{Array.from({length:scheduleRunCount}).map((_,i)=><label key={i}><span>{i+1}회차</span><input type="time" disabled={scheduleSaving} value={scheduleTimes[i]||'22:00'} onChange={e=>setScheduleTimes(prev=>{const next=[...prev];next[i]=e.target.value;return next})}/></label>)}</div>
    </div>
    <div className="admin-auto-sync-scopes-head"><span>자동 실행 항목</span><button type="button" disabled={scheduleSaving} onClick={()=>setScheduleScopes(scheduleScopes.length===ADMIN_SYNC_SCOPE_KEYS.length?[]:ADMIN_SYNC_SCOPE_KEYS)}>{scheduleScopes.length===ADMIN_SYNC_SCOPE_KEYS.length?'전체 해제':'전체 선택'}</button></div>
    <div className="admin-auto-sync-scopes">{ADMIN_SYNC_SCOPES.map(item=><label key={item.key} className={scheduleScopes.includes(item.key)?'selected':''}><input type="checkbox" checked={scheduleScopes.includes(item.key)} onChange={()=>toggleScope(scheduleScopes,setScheduleScopes,item.key)}/><CheckCircle2 size={14}/><span>{item.label}</span></label>)}</div>
    <div className="admin-auto-sync-v2-foot"><span><b>하루 {scheduleRunCount}회</b> · {scheduleScopes.length}개 항목 · {scheduleTimes.slice(0,scheduleRunCount).join(' · ')}</span><button className="primary" disabled={scheduleSaving||anyRunning||!scheduleScopes.length} onClick={()=>confirmAdminSave('자동 동기화 설정 저장',`하루 ${scheduleRunCount}회 실행 시간과 ${scheduleScopes.length}개 동기화 항목을 저장합니다. 계속할까요?`,saveSyncSchedule)}>{scheduleSaving?'저장 중...':'자동 설정 저장'}</button></div>
   </section>

   {(unifiedSync?.phase==='failed'&&unifiedSync?.last_error)&&<div className="admin-sync-error-v2"><div><b>{unifiedSync?.stage_label||'동기화'} 단계에서 중단</b><span>{fmtTime(unifiedSync?.finished_at)}</span></div><p>{publicUiText(unifiedSync.last_error)}</p></div>}

   {themeEngineTotal>0&&<section className={`admin-flow-coverage ${themeEngineErrors?'warning':'ok'}`}>
    <div className="admin-flow-coverage-head"><div><span className="admin-sync-log-dot"></span><span><small>최근 표준 테마 분류 커버리지</small><b>{themeEngineClassified.toLocaleString()} / {themeEngineTotal.toLocaleString()}종목</b></span></div><strong>{themeEngineCoverage>0?`${themeEngineCoverage.toFixed(1)}%`:'-'}</strong></div>
    <div className="admin-flow-coverage-grid"><span><small>강한 근거</small><b>{themeEngineStrong.toLocaleString()}</b></span><span><small>업종 보조</small><b>{themeEngineFallback.toLocaleString()}</b></span><span><small>무테마</small><b>{themeEngineNoTheme.toLocaleString()}</b></span><span><small>실제 오류</small><b>{themeEngineErrors.toLocaleString()}</b></span></div>
    <p>{themeEngineErrors>0?'실제 처리 오류가 남아 있어 확인이 필요합니다. 무테마 종목은 오류와 별개입니다.':themeEngineNoTheme>0?'무테마는 현재 근거가 부족해 억지로 테마를 부여하지 않은 정상 상태입니다. 다음 동기화에서 공급사 테마·DART 업종·뉴스·리포트·기존 분류 근거가 보강되면 자동 재분류됩니다.':'분석 대상 종목이 모두 StockLog 표준 테마로 분류되었습니다.'}</p>
   </section>}

   {(flowSelectedTotal>0||flowEligibleTotal>0)&&<section className={`admin-flow-coverage ${flowMissingData||flowHardFailed?'warning':'ok'}`}>
    <div className="admin-flow-coverage-head"><div><Users size={17}/><span><small>최근 수급 동기화 커버리지</small><b>{flowEligibleTotal>0?`${flowSelectedTotal.toLocaleString()} / ${flowEligibleTotal.toLocaleString()}종목`:`${flowSelectedTotal.toLocaleString()}종목`}</b></span></div><strong>{flowCoverage>0?`${flowCoverage.toFixed(1)}%`:'-'}</strong></div>
    <div className="admin-flow-coverage-grid"><span><small>저장 성공</small><b>{Number(flowSync?.success||0).toLocaleString()}</b></span><span><small>데이터 없음</small><b>{flowMissingData.toLocaleString()}</b></span><span><small>오류</small><b>{flowHardFailed.toLocaleString()}</b></span><span><small>선택 범위 밖</small><b>{flowOutsideSelection.toLocaleString()}</b></span></div>
    <p>{flowOutsideSelection>0?'선택한 상위 N개 밖 종목은 벌크 수집에서 제외됩니다. 다만 프리미엄 종목 분석 시 DB에 수급이 전혀 없으면 해당 종목만 자동 보충 수집합니다.':'전체 분석 대상 종목을 수급 동기화 범위로 사용했습니다.'}</p>
   </section>}

   <section className="admin-sync-log-box">
    <div className="admin-sync-log-head"><div><AlertTriangle size={17}/><span><small>동기화 진단 로그</small><b>백엔드·프론트 오류 TXT</b></span></div><div className="admin-sync-log-actions"><button type="button" className="secondary" disabled={!syncErrorLogs.length} onClick={()=>downloadAllSyncErrorLogs()}>전체 ZIP 다운로드</button><button type="button" className="secondary" disabled={syncErrorLogsLoading} onClick={()=>loadSyncErrorLogs()}>{syncErrorLogsLoading?'불러오는 중...':'새로고침'}</button></div></div>
    <p>동기화 실행별 오류·경고와 브라우저 측 동기화 오류를 날짜·시간별 TXT로 저장합니다. 토큰·비밀번호·API 키·계좌번호는 자동 마스킹됩니다.</p>
    <div className="admin-sync-log-list">
     {syncErrorLogs.slice(0,12).map(item=><div key={item.filename}><span><b>{item.filename}</b><small>{item.modified_at?new Date(item.modified_at).toLocaleString('ko-KR'):'-'} · {(Number(item.size||0)/1024).toFixed(1)} KB</small></span><button type="button" className="secondary" onClick={()=>downloadSyncErrorLog(item.filename)}>TXT 다운로드</button></div>)}
     {!syncErrorLogsLoading&&!syncErrorLogs.length&&<div className="admin-sync-log-empty">저장된 동기화 오류 로그가 없습니다.</div>}
    </div>
   </section>
  </AdminFold>

  <AdminFold title="키움 API 상태" subtitle="호출 대기열과 최근 오류를 확인합니다." className="admin-kiwoom-runtime-fold">
   <div className={`admin-kiwoom-runtime ${kiwoomRuntime?.state||'ok'}`}>
    <div><small>키움 API 상태</small><b>{kiwoomRuntime?.message||'상태 확인 중'}</b><span>{kiwoomRuntime?.last_success_at?`최근 성공 ${fmtTime(kiwoomRuntime.last_success_at)}`:'최근 성공 기록 없음'}</span></div>
    <div><small>대기열</small><b>{Number(kiwoomRuntime?.queued||0)}건</b><span>{Number(kiwoomRuntime?.cooldown_seconds||0)>0?`쿨다운 ${Number(kiwoomRuntime.cooldown_seconds).toFixed(1)}초`:'호출 가능'}</span></div>
    <div className="admin-kiwoom-runtime-error"><small>최근 상태</small><span>{kiwoomRuntime?.last_error||'오류 없음'}</span></div>
   </div>
  </AdminFold>

  <AdminFold title="회원 관리" subtitle="회원·투자성향·포트폴리오 운영 정보" className="admin-account-hub" badge={`${Number(accountMeta.total||0).toLocaleString()}명`}>
   <div className="admin-compact-head"><div><h3>회원 관리</h3><p>회원과 관리자 계정의 비밀번호·등급을 관리합니다. 현재 로그인한 관리자의 관리자 권한과 계정 삭제는 잠겨 있습니다.</p></div><span className="admin-account-count">총 {Number(accountMeta.total||0).toLocaleString()}명</span></div>
   <div className="admin-tier-summary">
    {['NORMAL','PREMIUM','EVENT','ADMIN'].map(tier=><span key={tier} className={tier.toLowerCase()}><small>{membershipLabels[tier]}</small><b>{Number(accountMeta?.tier_counts?.[tier]||0).toLocaleString()}</b></span>)}
   </div>
   <div className="admin-account-toolbar">
    <div className="admin-account-search"><Search size={15}/><input value={accountQuery} onChange={e=>{setAccountQuery(e.target.value);setAccountPage(1)}} placeholder="아이디 또는 표시 이름 검색"/></div>
    <div className="admin-account-filters">
     {[['all','전체'],['normal','일반'],['premium','프리미엄'],['event','이벤트'],['admin','관리자']].map(([value,label])=><button type="button" key={value} className={accountType===value?'active':''} onClick={()=>{setAccountType(value);setAccountPage(1)}}>{label}</button>)}
    </div>
   </div>
   <div className="admin-account-list">
    {accountUsers.map(account=>{
     const usage=account.ai_usage||{}
     const tier=String(account.membership_tier||account.account_type||'NORMAL').toUpperCase()
     const currentAdmin=tier==='ADMIN'&&Number(account.id)===Number(currentUser?.id)
     return <div className={`admin-account-row tier-${tier.toLowerCase()}`} key={account.id}>
      <div className="admin-account-identity"><div className="admin-account-avatar"><UserRound size={17}/></div><div><b>{account.display_name||account.username}</b><span>@{account.username}</span></div></div>
      <div className="admin-account-role"><small>회원 등급</small><b className={tier.toLowerCase()}>{membershipLabels[tier]||tier}</b></div>
      <div className="admin-account-usage"><small>오늘 AI</small><b>{usage.unlimited?'무제한':`${Number(usage.used||0)}/${Number(usage.daily_limit||0)}회`}</b><span>{usage.unlimited?'AI 제한 없음':`${Number(usage.remaining||0)}회 남음`}</span></div>
      <div className="admin-account-date"><small>가입일</small><b>{account.created_at?new Date(account.created_at).toLocaleDateString('ko-KR'):'-'}</b></div>
      <div className="admin-account-action admin-membership-action">
       <button type="button" className="admin-member-detail-button" disabled={accountBusy===String(account.id)} onClick={()=>openMemberDetail(account)}><Search size={14}/>상세보기</button>
       <button type="button" className="admin-member-password" disabled={accountBusy===String(account.id)} onClick={()=>setPasswordTarget(account)}><KeyRound size={14}/>비밀번호</button>
       <div className={`admin-membership-select ${currentAdmin?'locked':''}`}><select value={tier} disabled={accountBusy===String(account.id)||currentAdmin} onChange={e=>changeMembership(account,e.target.value)} aria-label={`${account.display_name||account.username} 회원 등급 변경`} title={currentAdmin?'현재 로그인한 관리자의 관리자 권한은 해제할 수 없습니다.':'회원 등급 변경'}>
        <option value="NORMAL">일반회원</option><option value="PREMIUM">프리미엄회원</option><option value="EVENT">이벤트회원</option><option value="ADMIN">관리자</option>
       </select>{currentAdmin&&<small><LockKeyhole size={11}/>본인 권한 잠금</small>}</div>
       <button type="button" className="admin-member-delete" disabled={accountBusy===String(account.id)||currentAdmin} onClick={()=>deleteMember(account)} title={currentAdmin?'현재 로그인한 관리자 계정은 삭제할 수 없습니다.':'회원 탈퇴'}><Trash2 size={14}/>탈퇴</button>
       {accountBusy===String(account.id)&&<span className="admin-account-changing">처리 중...</span>}
      </div>
     </div>
    })}
    {accountLoading&&<div className="admin-account-loading">계정 목록을 불러오는 중...</div>}
    {!accountLoading&&!accountUsers.length&&<div className="empty">조건에 맞는 계정이 없습니다.</div>}
   </div>
   <div className="admin-account-pagination">
    <span>페이지당 20명 / {Number(accountMeta.total||0).toLocaleString()}명 검색됨</span>
    <div><button type="button" disabled={accountPage<=1||accountLoading} onClick={()=>setAccountPage(p=>Math.max(1,p-1))}>이전</button><b>{accountMeta.page||1} / {accountMeta.pages||1}</b><button type="button" disabled={accountPage>=Number(accountMeta.pages||1)||accountLoading} onClick={()=>setAccountPage(p=>Math.min(Number(accountMeta.pages||1),p+1))}>다음</button></div>
   </div>
  </AdminFold>

  <AdminFold title="등급별 기능 권한" subtitle="회원 등급별 기능과 AI 사용 한도" className="admin-membership-policy">
   <div className="admin-compact-head"><div><h3>등급별 기능 권한</h3><p>기능 공개 여부와 AI 일일 사용량을 코드 수정 없이 운영 정책으로 관리합니다. 관리자 권한은 잠금 방지를 위해 항상 전체 허용입니다.</p></div><button className="primary" disabled={!membershipPolicy||policySaving} onClick={()=>confirmAdminSave('회원 권한 정책 저장','모든 회원 등급의 기능 권한과 AI 사용 한도를 한 번에 저장합니다. 계속할까요?',saveMembershipPolicy)}>{policySaving?'저장 중...':'권한 정책 저장'}</button></div>
   {!membershipPolicy?<div className="admin-account-loading">권한 정책을 불러오는 중...</div>:<div className="admin-policy-wrap">
    <div className="admin-policy-table">
     <div className="admin-policy-row admin-policy-head"><b>기능</b>{(membershipPolicy.tiers||[]).map(t=><b key={t.tier}>{t.label}</b>)}</div>
     {(membershipPolicy.feature_order||[]).map(key=>{
      const meta=membershipPolicy.tiers?.[0]?.features?.[key]||{}
      return <div className="admin-policy-row" key={key}>
       <div><b>{meta.label||key}</b><span>{meta.description||''}</span></div>
       {(membershipPolicy.tiers||[]).map(t=>{
        const item=t.features?.[key]||{}
        const premiumOnly=key==='portfolio_ai_momentum'&&t.tier==='NORMAL'
        const adminLocked=t.tier==='ADMIN'
        const locked=adminLocked||premiumOnly
        return <div className="admin-policy-cell" key={`${t.tier}-${key}`}>
         <label className="admin-policy-toggle"><input type="checkbox" checked={premiumOnly?false:adminLocked?true:Boolean(item.enabled)} disabled={locked} onChange={e=>updatePolicyLocal(t.tier,key,{enabled:e.target.checked})}/><span>{premiumOnly?'프리미엄+':adminLocked?'고정':item.enabled?'허용':'차단'}</span></label>
         {key==='ai_analysis'&&<div className="admin-ai-limit"><small>일 제한</small><input type="number" min="-1" max="100000" disabled={locked||!item.enabled} value={locked?-1:Number(item.limit_value??5)} onChange={e=>updatePolicyLocal(t.tier,key,{limit_value:Number(e.target.value)})}/><em>-1 = 무제한</em></div>}
        </div>
       })}
      </div>
     })}
    </div>
   </div>}
  </AdminFold>

  <AdminFold title="자동 새로고침 정책" subtitle="회원 등급별 화면 갱신 주기" className="admin-refresh-policy">
   <div className="admin-compact-head"><div><h3>등급별 자동 새로고침</h3><p>모의투자 계좌 정보와 강세 테마의 백그라운드 갱신 주기를 회원 등급별로 설정합니다. 0초는 자동 새로고침 사용 안 함이며, 그 외에는 10초 이상으로 설정합니다.</p></div><button className="primary" disabled={!refreshPolicies||refreshPolicySaving} onClick={()=>confirmAdminSave('새로고침 정책 저장','모든 회원 등급의 화면 갱신 주기를 한 번에 저장합니다. 계속할까요?',saveRefreshPolicies)}>{refreshPolicySaving?'저장 중...':'새로고침 정책 저장'}</button></div>
   {!refreshPolicies?<div className="admin-account-loading">새로고침 정책을 불러오는 중...</div>:<div className="admin-refresh-policy-grid">
    {(refreshPolicies.tiers||[]).map(row=><article key={row.tier} className={`tier-${String(row.tier).toLowerCase()}`}>
     <div className="admin-refresh-tier"><small>MEMBERSHIP</small><b>{row.label}</b></div>
     <label><span>모의투자</span><div><input type="number" min="0" max="3600" step="5" value={Number(row.trading_seconds||0)} onChange={e=>updateRefreshPolicyLocal(row.tier,'trading_seconds',e.target.value)}/><em>초</em></div></label>
     <label><span>강세 테마</span><div><input type="number" min="0" max="3600" step="5" value={Number(row.theme_seconds||0)} onChange={e=>updateRefreshPolicyLocal(row.tier,'theme_seconds',e.target.value)}/><em>초</em></div></label>
     <p>{Number(row.trading_seconds||0)===0&&Number(row.theme_seconds||0)===0?'자동 갱신 없음':'화면이 열려 있고 브라우저가 활성 상태일 때만 적용'}</p>
    </article>)}
   </div>}
  </AdminFold>

  <AdminFold title="소셜 로그인" subtitle="카카오·네이버·구글 OAuth" className="admin-social-auth-hub">
   <div className="admin-compact-head"><div><h3>소셜 로그인</h3><p>카카오 / 네이버 / 구글 OAuth 설정을 서버 DB에 암호화 저장하고 실제 로그인 왕복으로 연결 상태를 검증합니다.</p></div><button className="primary" disabled={!!socialBusy} onClick={saveAllSocialAuth}>{socialBusy==='save-all'?'일괄 저장 중...':'변경사항 일괄 저장'}</button></div>
   <div className="admin-social-grid">
    {[['kakao','카카오',kakaoLogin],['naver','네이버',naverLogin],['google','구글',googleLogin]].map(([provider,label,status])=>{
     const fields=provider==='kakao'
      ?{id:'kakaoClientId',secret:'kakaoClientSecret',redirect:'kakaoRedirectUri',enabled:'kakaoEnabled',icon:'K',idLabel:'REST API Key'}
      :provider==='naver'
       ?{id:'naverClientId',secret:'naverClientSecret',redirect:'naverRedirectUri',enabled:'naverEnabled',icon:'N',idLabel:'Client ID'}
       :{id:'googleClientId',secret:'googleClientSecret',redirect:'googleRedirectUri',enabled:'googleEnabled',icon:'G',idLabel:'Client ID'}
     const clientId=socialForm[fields.id]
     const clientSecret=socialForm[fields.secret]
     const redirectUri=socialForm[fields.redirect]
     const enabled=socialForm[fields.enabled]
     return <article key={provider} className={`admin-social-card ${provider}`}>
      <div className="admin-social-card-head"><div className="admin-social-brand"><i>{fields.icon}</i><div><b>{label} 로그인</b><small>OAuth 2.0 / 신규 가입은 기본 정보와 투자성향 확인 필수</small></div></div><span className={status?.last_test_status==='success'&&status?.enabled?'ok':status?.last_test_status==='failed'?'bad':'wait'}>{status?.configured?socialStatusLabel(status?.last_test_status):'미설정'}</span></div>
      <div className="admin-social-form">
       <label><span>{fields.idLabel}</span><input value={clientId} onChange={e=>setSocialForm(v=>({...v,[fields.id]:e.target.value}))} placeholder={status?.client_id_masked||`${label} ${fields.idLabel}`}/></label>
       <label><span>Client Secret {provider==='kakao'&&<em>사용 중인 경우 입력</em>}</span><input type="password" value={clientSecret} onChange={e=>setSocialForm(v=>({...v,[fields.secret]:e.target.value}))} placeholder={status?.has_client_secret?'변경할 때만 입력':'Client Secret'}/></label>
       <label className="wide"><span>Redirect URI / 개발자 콘솔에도 정확히 동일하게 등록</span><input value={redirectUri} onChange={e=>setSocialForm(v=>({...v,[fields.redirect]:e.target.value}))}/></label>
      </div>
      <div className="admin-social-foot">
       <label className="admin-social-toggle"><input type="checkbox" checked={enabled} onChange={e=>setSocialForm(v=>({...v,[fields.enabled]:e.target.checked}))}/><span>로그인 화면에 노출</span></label>
       <div className="admin-social-actions"><button className="secondary" disabled={!!socialBusy||!status?.configured} onClick={()=>testSocialAuth(provider)}>{socialBusy===`test-${provider}`?'이동 중':'실제 연결 테스트'}</button>{status?.configured&&<button className="text-danger" disabled={!!socialBusy} onClick={()=>removeSocialAuth(provider)}>삭제</button>}</div>
      </div>
      <div className="admin-social-result"><span>{status?.last_test_status==='success'?'✓':status?.last_test_status==='failed'?'!':'i'}</span><div><b>{status?.last_test_message||'설정 저장 후 실제 연결 테스트를 진행해주세요.'}</b><small>{status?.last_tested_at?`최근 테스트 ${fmtTime(status.last_tested_at)}`:'Client Secret은 저장 후 화면에 다시 표시하지 않습니다.'}</small></div></div>
      {provider==='google'&&<div className="admin-social-guide"><b>구글 설정 핵심</b><span>Google Auth Platform / Web application / scopes: openid, email, profile + 성별/생년월일/휴대폰 읽기</span><code>{`${window.location.origin}/api/auth/social/google/callback`}</code></div>}
     </article>
    })}
   </div>
  </AdminFold>

  <AdminFold title="외부 API / AI" subtitle="뉴스·공시·Gbot 연결 및 사용량" className="admin-api-hub">
   <div className="admin-compact-head"><div><h3>외부 API / AI</h3><p>뉴스·공시·Gbot 연결 상태와 운영 사용량을 관리합니다.</p></div><button className="primary" disabled={!!apiBusy} onClick={()=>saveExternalApiGroup('domestic')}>{apiBusy==='save-domestic-group'?'일괄 저장 중...':'변경사항 일괄 저장'}</button></div>
   <div className="admin-api-compact-grid">
    <article>
     <div className="admin-api-card-head"><div><b>네이버 뉴스</b><small>NAVER API HUB</small></div><span className={externalApis?.naver?.configured?'ok':'off'}>{externalApis?.naver?.configured?'연동':'미연동'}</span></div>
     <div className="admin-api-metrics"><span><small>오늘</small><b>{Number(naverUsage.total_calls||0).toLocaleString()} / {Number(naverUsage.daily_limit||25000).toLocaleString()}</b></span><span><small>사용률</small><b>{Number(naverUsage.usage_percent||0).toFixed(1)}%</b></span><span><small>최근 1시간</small><b>{Number(naverUsage.recent_hour_calls||0).toLocaleString()}</b></span></div>
     <div className="admin-api-progress"><i style={{width:`${Math.min(100,Number(naverUsage.usage_percent||0))}%`}}/></div>
     <div className="admin-api-form"><input value={apiForm.naverClientId} onChange={e=>setApiForm(v=>({...v,naverClientId:e.target.value}))} placeholder={externalApis?.naver?.client_id_masked||'Client ID'}/><input type="password" value={apiForm.naverClientSecret} onChange={e=>setApiForm(v=>({...v,naverClientSecret:e.target.value}))} placeholder={externalApis?.naver?.configured?'Secret 변경 시 입력':'Client Secret'}/></div>
     <div className="admin-api-actions"><button className="secondary" disabled={!!apiBusy||!externalApis?.naver?.configured} onClick={()=>testExternalApi('naver')}>연결 확인</button>{externalApis?.naver?.stored_in_mysql&&<button className="text-danger" disabled={!!apiBusy} onClick={()=>removeExternalApi('naver')}>삭제</button>}</div>
    </article>
    <article>
     <div className="admin-api-card-head"><div><b>OpenDART</b><small>공시 / 재무</small></div><span className={externalApis?.dart?.configured?'ok':'off'}>{externalApis?.dart?.configured?'연동':'미연동'}</span></div>
     <div className="admin-api-metrics"><span><small>오늘</small><b>{Number(dartUsage.total_calls||0).toLocaleString()}회</b></span><span><small>성공</small><b>{Number(dartUsage.successful_calls||0).toLocaleString()}</b></span><span><small>실패</small><b>{Number(dartUsage.failed_calls||0).toLocaleString()}</b></span></div>
     <div className="admin-api-form single"><input type="password" value={apiForm.dartApiKey} onChange={e=>setApiForm(v=>({...v,dartApiKey:e.target.value}))} placeholder={externalApis?.dart?.api_key_masked||'OpenDART API Key'}/></div>
     <div className="admin-api-actions"><button className="secondary" disabled={!!apiBusy||!externalApis?.dart?.configured} onClick={()=>testExternalApi('dart')}>연결 확인</button>{externalApis?.dart?.stored_in_mysql&&<button className="text-danger" disabled={!!apiBusy} onClick={()=>removeExternalApi('dart')}>삭제</button>}</div>
    </article>
    <article className="admin-api-gemini">
     <div className="admin-api-card-head"><div><b>StockLog Gbot</b><small>투자 분석 엔진</small></div><span className={externalApis?.gemini?.configured?'ok':'off'}>{externalApis?.gemini?.configured?'연동':'미연동'}</span></div>
     <div className="admin-api-metrics"><span><small>오늘</small><b>{Number(geminiUsage.total_calls||0).toLocaleString()} / {Number(geminiUsage.daily_limit||200).toLocaleString()}</b></span><span><small>남은 안전 한도</small><b>{Number(geminiUsage.remaining_calls??geminiUsage.daily_limit??200).toLocaleString()}</b></span><span><small>백그라운드</small><b>{Number(geminiUsage.background_calls||0).toLocaleString()}회</b></span></div>
     <div className="admin-api-progress"><i style={{width:`${Math.min(100,Number(geminiUsage.usage_percent||0))}%`}}/></div>
     <div className="admin-api-form single"><input type="password" value={apiForm.geminiApiKey} onChange={e=>setApiForm(v=>({...v,geminiApiKey:e.target.value}))} placeholder={externalApis?.gemini?.api_key_masked||'Gbot API Key'}/></div>
     <div className="admin-api-actions"><button className="secondary" disabled={!!apiBusy||!externalApis?.gemini?.configured} onClick={()=>testExternalApi('gemini')}>연결 확인</button>{externalApis?.gemini?.stored_in_mysql&&<button className="text-danger" disabled={!!apiBusy} onClick={()=>removeExternalApi('gemini')}>삭제</button>}</div>
     <div className="admin-api-free-note"><b>SAFE LIMIT</b><span>StockLog 안전 한도와 오류 보호 정책을 적용합니다.</span></div>
    </article>
   </div>
  </AdminFold>

  <AdminFold title="해외증권 분석 API" subtitle="무료 시세·기업정보·미국 공시를 국내 API와 분리 관리" className="admin-api-hub overseas-api-admin">
   <div className="admin-compact-head"><div><h3>해외증권 무료 데이터</h3><p>Finnhub를 우선 시세로 사용하고 Alpha Vantage는 무료 한도 내 보조, SEC EDGAR는 공시 전용으로 사용합니다.</p></div><div className="admin-compact-actions"><span className="overseas-free-chip">FREE ONLY</span><button className="primary" disabled={!!apiBusy} onClick={()=>saveExternalApiGroup('overseas')}>{apiBusy==='save-overseas-group'?'일괄 저장 중...':'변경사항 일괄 저장'}</button></div></div>
   <div className="admin-api-compact-grid">
    {[
     {id:'finnhub',title:'Finnhub',sub:'미국 시세 · 검색 · 기업정보',field:'finnhubApiKey',placeholder:'Finnhub API Key'},
     {id:'alpha_vantage',title:'Alpha Vantage',sub:'보조 시세 · 기업 개요 / 일 25회 보호',field:'alphaVantageApiKey',placeholder:'Alpha Vantage API Key'}
    ].map(item=>{const status=externalApis?.overseas?.[item.id];const usage=status?.usage||{};return <article key={item.id}>
     <div className="admin-api-card-head"><div><b>{item.title}</b><small>{item.sub}</small></div><span className={status?.configured?'ok':'off'}>{status?.configured?'연동':'미연동'}</span></div>
     <div className="admin-api-metrics"><span><small>오늘 호출</small><b>{Number(usage.total_calls||0).toLocaleString()}</b></span><span><small>성공</small><b>{Number(usage.successful_calls||0).toLocaleString()}</b></span><span><small>실패</small><b>{Number(usage.failed_calls||0).toLocaleString()}</b></span></div>
     <div className="admin-api-form single"><input type="password" value={apiForm[item.field]} onChange={e=>setApiForm(v=>({...v,[item.field]:e.target.value}))} placeholder={status?.api_key_masked||item.placeholder}/></div>
     <div className="admin-api-actions"><button className="secondary" disabled={!!apiBusy||!status?.configured} onClick={()=>testExternalApi(item.id)}>연결 확인</button>{status?.stored_in_mysql&&<button className="text-danger" disabled={!!apiBusy} onClick={()=>removeExternalApi(item.id)}>삭제</button>}</div>
    </article>})}
    <article>
     <div className="admin-api-card-head"><div><b>SEC EDGAR</b><small>미국 공시 · XBRL / API Key 불필요</small></div><span className={externalApis?.overseas?.sec_edgar?.configured?'ok':'off'}>{externalApis?.overseas?.sec_edgar?.configured?'연동':'미연동'}</span></div>
     <div className="admin-api-free-note"><b>NO API KEY</b><span>SEC 요청 정책에 맞는 식별용 이메일 또는 연락처만 저장합니다.</span></div>
     <div className="admin-api-form single"><input value={apiForm.secEdgarContact} onChange={e=>setApiForm(v=>({...v,secEdgarContact:e.target.value}))} placeholder={externalApis?.overseas?.sec_edgar?.contact_masked||'contact@example.com'}/></div>
     <div className="admin-api-actions"><button className="secondary" disabled={!!apiBusy||!externalApis?.overseas?.sec_edgar?.configured} onClick={()=>testExternalApi('sec_edgar')}>연결 확인</button>{externalApis?.overseas?.sec_edgar?.stored_in_mysql&&<button className="text-danger" disabled={!!apiBusy} onClick={()=>removeExternalApi('sec_edgar')}>삭제</button>}</div>
    </article>
   </div>
  </AdminFold>

  </div>
  <div className="admin-footnote">분석 점수는 시세/재무 동기화 과정에서 자동으로 다시 계산되므로 별도 재계산 메뉴를 제거했습니다.</div>
  {msg&&<div className="info admin-global-msg">{publicUiText(msg)}</div>}
 </>
}

const usd=value=>Number(value||0).toLocaleString('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2})

function OverseasWorkspace({view='smart'}){
 const [status,setStatus]=useState(null),[overview,setOverview]=useState(null),[portfolio,setPortfolio]=useState(null),[orders,setOrders]=useState([])
 const [selected,setSelected]=useState(null),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[message,setMessage]=useState('')
 const [smartData,setSmartData]=useState(null),[smartLoading,setSmartLoading]=useState(false),[smartSyncing,setSmartSyncing]=useState(false)
 const [smartLoadKind,setSmartLoadKind]=useState('initial'),[smartLoadStage,setSmartLoadStage]=useState(0)
 const [searchInput,setSearchInput]=useState(''),[smartQuery,setSmartQuery]=useState(''),[smartPage,setSmartPage]=useState(1)
 const [smartExchange,setSmartExchange]=useState('all'),[smartAsset,setSmartAsset]=useState('stock'),[smartSort,setSmartSort]=useState('analysis_score')
 const [orderForm,setOrderForm]=useState({symbol:'AAPL',side:'buy',quantity:1})
 const smartRequestRef=useRef(0)
 const isTrading=view==='trading'||view==='portfolio'
 const load=async()=>{
  setLoading(true);setMessage('')
  try{
   const requests=[api.get('/api/overseas/status')]
   if(view!=='smart')requests.push(api.get('/api/overseas/overview'))
   if(isTrading)requests.push(api.get('/api/overseas/paper/portfolio'),api.get('/api/overseas/paper/orders'))
   const rows=await Promise.all(requests)
   setStatus(rows[0].data)
   if(view!=='smart')setOverview(rows[1].data)
   if(isTrading){setPortfolio(rows[2].data);setOrders(rows[3].data?.items||[])}
  }catch(e){setMessage(e.response?.data?.detail||'해외증권 데이터를 불러오지 못했습니다.')}
  finally{setLoading(false)}
 }
 useEffect(()=>{load()},[view])
 const loadSmart=async(refresh=true,kind='filter')=>{
  if(view!=='smart')return
  const requestId=++smartRequestRef.current
  setSmartLoadKind(kind);setSmartLoading(true);setMessage('')
  try{
   const params={q:smartQuery,exchange:smartExchange,asset_type:smartAsset,sort_by:smartSort,sort_order:smartSort==='symbol'?'asc':'desc',page:smartPage,page_size:20}
   const cached=await api.get('/api/overseas/smart',{params:{...params,refresh:false}})
   if(requestId!==smartRequestRef.current)return
   setSmartData(cached.data)
   if(refresh){
    setSmartLoadStage(current=>Math.max(1,current))
    const fresh=await api.get('/api/overseas/smart',{params:{...params,refresh:true}})
    if(requestId!==smartRequestRef.current)return
    setSmartData(fresh.data)
   }
  }catch(e){if(requestId===smartRequestRef.current)setMessage(e.response?.data?.detail||'미국 종목 분석 목록을 불러오지 못했습니다.')}
  finally{if(requestId===smartRequestRef.current)setSmartLoading(false)}
 }
 useEffect(()=>{
  const servedPage=Number(smartData?.page||0)
  const servedQuery=String(smartData?.filters?.q||'')
  const kind=!smartData?'initial':smartQuery!==servedQuery?'search':smartPage!==servedPage?'page':smartSort!==smartData?.sort_by?'mode':'filter'
  loadSmart(true,kind)
 },[view,smartQuery,smartExchange,smartAsset,smartSort,smartPage])
 useEffect(()=>{
  if(!smartLoading){setSmartLoadStage(0);return}
  setSmartLoadStage(0)
  const first=setTimeout(()=>setSmartLoadStage(1),420)
  const second=setTimeout(()=>setSmartLoadStage(2),1150)
  return()=>{clearTimeout(first);clearTimeout(second)}
 },[smartLoading])
 const submitSmartSearch=value=>{
  const next=String(value??searchInput).trim()
  setSmartPage(1)
  if(next===smartQuery)loadSmart(true,'search')
  else setSmartQuery(next)
 }
 const syncUniverse=async()=>{
  setSmartSyncing(true);setMessage('')
  try{const r=await api.post('/api/overseas/universe/sync');setMessage(r.data?.message||'미국 종목 목록을 갱신했습니다.');await loadSmart(true,'mode');await load()}
  catch(e){setMessage(e.response?.data?.detail||'미국 종목 목록 갱신에 실패했습니다.')}
  finally{setSmartSyncing(false)}
 }
 const openSymbol=async symbol=>{
  setBusy(true);setMessage('')
  try{const r=await api.get(`/api/overseas/stocks/${encodeURIComponent(symbol)}`);setSelected(r.data);setOrderForm(v=>({...v,symbol:r.data.symbol}))}
  catch(e){setMessage(e.response?.data?.detail||'종목 정보를 불러오지 못했습니다.')}
  finally{setBusy(false)}
 }
 const submitOrder=async event=>{
  event.preventDefault();setBusy(true);setMessage('')
  try{const r=await api.post('/api/overseas/paper/orders',{...orderForm,quantity:Number(orderForm.quantity)});setMessage(r.data?.message||'해외 모의주문이 체결되었습니다.');await load()}
  catch(e){setMessage(e.response?.data?.detail||'해외 모의주문에 실패했습니다.')}
  finally{setBusy(false)}
 }
 const provider=status?.providers?.active
 const items=overview?.items||[]
 const smartRows=smartData?.items||[]
 const smartUniverse=smartData?.universe||status?.universe||{}
 const smartTotalPages=Math.max(1,Number(smartData?.pages||1)),smartCurrentPage=Math.min(Number(smartData?.page||smartPage),smartTotalPages)
 const title={smart:'해외 증권',themes:'해외 섹터 분석',flow:'해외시장 흐름',trading:'해외증권 모의투자',portfolio:'해외 포트폴리오','trading-auto':'해외 자동 분석','auto-settings':'해외 자동 분석 설정'}[view]||'해외증권'
 const loadingPageLabel={themes:'인기테마 분석',flow:'수급 분석',trading:'증권투자(수동)',portfolio:'포트폴리오','trading-auto':'증권투자(자동)','auto-settings':'자동매매 설정'}[view]||title
 const activeSmartFilterCount=[smartExchange!=='all',smartAsset!=='stock',smartSort!=='analysis_score'].filter(Boolean).length
 return <div className="overseas-workspace">
  {view==='smart'&&smartLoading&&<SmartListLoadingOverlay kind={smartLoadKind} stage={smartLoadStage} page={smartPage} query={smartQuery} marketLabel="해외증권" pageLabel="스마트 분석"/>}
  {view!=='smart'&&(loading||busy)&&<PageDataLoadingStatus marketLabel="해외증권" pageLabel={loadingPageLabel} title={`${loadingPageLabel} 데이터를 업데이트하고 있어요`} detail="해외증권 화면을 먼저 표시하고 무료 시세·계좌 정보를 준비되는 순서대로 반영합니다." steps={['현재 화면 유지','해외 데이터 확인','최신 결과 반영']}/>} 
  <div className="page-head overseas-page-head"><div><span>{view==='smart'?'스마트 분석':'미국 증권'}</span><h1>{title}</h1><p>{view==='smart'?'미국 상장 종목 전체를 검색하고 무료 시세 기반 분석 순서로 살펴봅니다.':'무료 데이터 범위에서 미국 종목을 분석하고 달러 모의계좌로 거래합니다. 제공 시세는 지연될 수 있습니다.'}</p></div><button type="button" className="secondary" onClick={()=>view==='smart'?loadSmart(true,'mode'):load()} disabled={loading||smartLoading}><RefreshCw size={16}/>새로고침</button></div>
  <div className={`overseas-provider-banner ${provider&&provider!=='none'?'ready':'warning'}`}><Globe2 size={19}/><div><b>{provider&&provider!=='none'?`${provider==='finnhub'?'Finnhub':'Alpha Vantage'} 시세 연결됨`:'해외 시세 API 설정 필요'}</b><span>{provider&&provider!=='none'?'무료 호출 한도를 보호하며 화면에 보이는 종목부터 시세와 분석을 갱신합니다.':'전체 종목 조회는 가능하며, 시세 분석은 관리자 > 해외증권 분석 API에서 무료 키를 설정하면 시작됩니다.'}</span></div><em>{provider&&provider!=='none'?'지연 시세':'설정 필요'}</em></div>
  {message&&<div className="info overseas-message">{message}</div>}
  <>
   {view==='smart'&&<>
    <section className="overseas-smart-summary">
     <article className="panel"><small>전체 미국 상장 종목</small><b>{Number(smartUniverse.total||0).toLocaleString()}개</b><span>Nasdaq Trader 공식 목록</span></article>
     <article className="panel"><small>분석 완료</small><b>{Number(smartUniverse.analyzed||0).toLocaleString()}개</b><span>확인한 종목부터 누적</span></article>
     <article className="panel"><small>시세 캐시</small><b>{Number(smartUniverse.quoted||0).toLocaleString()}개</b><span>무료 API 호출 보호</span></article>
     <article className="panel"><small>현재 데이터</small><b>{provider==='finnhub'?'Finnhub':provider==='alpha_vantage'?'Alpha Vantage':'목록 전용'}</b><span>{provider&&provider!=='none'?'지연 시세':'API 키 미설정'}</span></article>
    </section>
    <div className="smart-list-controls overseas-smart-list-controls">
     <div className="smart-search-section">
      <div className="smart-search-heading"><span>종목 검색</span><small>티커 · 영문명 · 한글명</small></div>
      <SmartStockSearch
       value={searchInput}
       onChange={setSearchInput}
       onSearch={submitSmartSearch}
       onClear={()=>{setSmartPage(1);if(smartQuery)setSmartQuery('')}}
       loading={smartLoading&&smartLoadKind==='search'}
       placeholder="TSLA, Tesla, 테슬라처럼 입력 후 Enter"
       ariaLabel="해외증권 스마트 분석 종목 검색"
      />
     </div>
     <div className="smart-filter-shell">
      <div className="smart-filter-toolbar-head"><div><span>조건 필터</span><small>국내증권과 같은 방식으로 조건을 조합하세요</small></div><b>{activeSmartFilterCount}개 적용</b></div>
      <div className="smart-explore-filters">
       <div className="smart-filter-field"><label htmlFor="overseas-smart-exchange">거래소</label><select id="overseas-smart-exchange" value={smartExchange} onChange={e=>{setSmartPage(1);setSmartExchange(e.target.value)}}><option value="all">전체 거래소</option>{(smartData?.filter_options?.exchanges||[]).map(value=><option key={value} value={value}>{value}</option>)}</select></div>
       <div className="smart-filter-field"><label htmlFor="overseas-smart-asset">종목 구분</label><select id="overseas-smart-asset" value={smartAsset} onChange={e=>{setSmartPage(1);setSmartAsset(e.target.value)}}><option value="stock">주식</option><option value="etf">ETF</option><option value="all">전체</option></select></div>
       <div className="smart-filter-field"><label htmlFor="overseas-smart-sort">정렬 기준</label><select id="overseas-smart-sort" value={smartSort} onChange={e=>{setSmartPage(1);setSmartSort(e.target.value)}}><option value="analysis_score">종합점수 높은순</option><option value="profile_score">내 성향 높은순</option><option value="change_percent">등락률 높은순</option><option value="symbol">티커 가나다순</option></select></div>
       {activeSmartFilterCount>0&&<button type="button" className="smart-filter-reset" onClick={()=>{setSmartPage(1);setSmartExchange('all');setSmartAsset('stock');setSmartSort('analysis_score')}}>전체 초기화</button>}
       <button type="button" className="smart-filter-reset overseas-universe-sync" onClick={syncUniverse} disabled={smartSyncing}><RefreshCw size={15} className={smartSyncing?'spin-icon':''}/>{smartSyncing?'목록 갱신 중':'전체 목록 갱신'}</button>
      </div>
     </div>
    </div>
    {smartData&&!smartData?.profile?.ready&&<div className="overseas-profile-hint"><Fingerprint size={17}/><div><b>내 성향 적합도를 보려면 투자성향 검사가 필요합니다.</b><span>검사를 완료하면 해외 종목도 국내증권과 같은 기준으로 내 투자방식과 비교합니다.</span></div></div>}
    {smartUniverse.warning&&<div className="overseas-smart-warning">{smartUniverse.warning} 저장된 목록은 계속 표시합니다.</div>}
    <section className={`panel overseas-smart-list ${smartLoading?'is-loading':''}`} aria-busy={smartLoading?'true':'false'}>
     <div className="overseas-smart-list-title"><div><h3>미국 스마트 분석</h3><p>{smartData?.analysis_guide||'무료 시세 기반 분석 결과를 목록으로 제공합니다.'}</p></div><b>검색 결과 {Number(smartData?.total||0).toLocaleString()}개</b></div>
     <div className="overseas-smart-head"><span>순번</span><span>종목</span><span>현재가</span><span>등락률</span><span>StockLog 종합점수</span><span>내 투자성향</span><span>분석 근거</span><span>데이터</span></div>
     <div className="overseas-smart-body">
      {smartRows.map((row,index)=>{const quote=row.quote||{},analysis=row.analysis||{},change=Number(quote.change_percent||0),score=analysis.score,profileScore=analysis.profile_score;return <button type="button" className="overseas-smart-row" key={row.symbol} onClick={()=>openSymbol(row.symbol)}>
       <span className="overseas-smart-rank">{(smartCurrentPage-1)*20+index+1}</span>
       <span className="overseas-smart-name"><b>{row.display_name||row.symbol}</b><small>{row.name}</small><em>{row.exchange} · {row.is_etf?'ETF':'주식'}</em></span>
       <span className="overseas-smart-price">{quote.available?usd(quote.price):'시세 대기'}</span>
       <span className={change>0?'up':change<0?'down':''}>{quote.available?`${change>0?'+':''}${change.toFixed(2)}%`:'-'}</span>
       <span className={`overseas-smart-score aggregate ${score>=70?'good':score<43&&score!==null?'weak':''}`}><b>{score===null||score===undefined?'--':Math.round(score)}{score!==null&&score!==undefined&&<em>점</em>}</b><small>{analysis.label||'분석 대기'}</small></span>
       <span className={`overseas-smart-score profile ${profileScore>=70?'good':profileScore<43&&profileScore!==null?'weak':''}`}><b>{profileScore===null||profileScore===undefined?'--':Math.round(profileScore)}{profileScore!==null&&profileScore!==undefined&&<em>점</em>}</b><small>{analysis.profile_label||'성향 미검사'}</small></span>
       <span className="overseas-smart-reason"><b>데이터 {Math.round(Number(analysis.coverage||0))}%</b><small>{analysis.reason||'시세 데이터 준비 중'}</small></span>
       <span className={`overseas-smart-data ${row.data_state}`}><i/>{row.data_state==='fresh'?'최신':row.data_state==='stale'?'캐시':'대기'}</span>
      </button>})}
      {!smartRows.length&&!smartLoading&&<div className="empty">검색 조건에 맞는 미국 종목이 없습니다.</div>}
     </div>
    </section>
    {smartRows.length>0&&<div className="stocklog-pagination overseas-smart-pagination"><button type="button" disabled={smartLoading||smartCurrentPage===1} onClick={()=>setSmartPage(1)}>처음</button><button type="button" disabled={smartLoading||smartCurrentPage===1} onClick={()=>setSmartPage(p=>Math.max(1,p-1))}>이전</button><small>{smartCurrentPage} / {smartTotalPages} 페이지</small><button type="button" disabled={smartLoading||smartCurrentPage===smartTotalPages} onClick={()=>setSmartPage(p=>Math.min(smartTotalPages,p+1))}>다음</button><button type="button" disabled={smartLoading||smartCurrentPage===smartTotalPages} onClick={()=>setSmartPage(smartTotalPages)}>끝</button></div>}
   </>}
   {(view==='flow'||view==='trading-auto'||view==='auto-settings')&&<>
    {(view==='trading-auto'||view==='auto-settings')&&<div className="overseas-safety-note panel"><ShieldCheck size={21}/><div><b>해외 자동매매는 분석 전용으로 안전하게 제한했습니다.</b><p>무료 지연 시세만으로 실전 자동주문을 실행하지 않습니다. 후보 관찰과 등락 분석은 제공하며 브로커·환전·장 운영시간 검증 후 주문 기능을 별도로 개방할 수 있습니다.</p></div></div>}
    <section className="overseas-quote-grid">{items.map(row=>{const q=row.quote||{};return <button type="button" key={row.symbol} className="panel overseas-quote-card" onClick={()=>openSymbol(row.symbol)}><span><b>{row.symbol}</b><small>{row.name}</small></span><strong>{q.available?usd(q.price):'시세 대기'}</strong><em className={Number(q.change_percent||0)>0?'up':Number(q.change_percent||0)<0?'down':''}>{Number(q.change_percent||0)>0?'+':''}{Number(q.change_percent||0).toFixed(2)}%</em><small>{row.sector}</small></button>})}</section>
   </>}
   {view==='themes'&&<section className="overseas-sector-grid">{[...new Set((overview?.items||[]).map(x=>x.sector))].map(name=><article className="panel" key={name}><span>미국 업종</span><h3>{name}</h3><p>{items.filter(x=>x.sector===name).map(x=>x.symbol).join(' · ')}</p></article>)}</section>}
   {isTrading&&<>
    <section className="overseas-summary-grid">{[['총 자산',portfolio?.summary?.total_asset],['주문 가능',portfolio?.summary?.buying_power],['평가 손익',portfolio?.summary?.profit_loss],['금일 순익',portfolio?.summary?.day_profit]].map(([label,value])=><article className="panel" key={label}><small>{label}</small><b className={Number(value||0)>0?'up':Number(value||0)<0?'down':''}>{usd(value)}</b></article>)}</section>
    {view==='trading'&&<form className="panel overseas-order-form" onSubmit={submitOrder}><div><span>달러 모의주문</span><h3>해외주식 주문</h3></div><label>티커<input value={orderForm.symbol} onChange={e=>setOrderForm(v=>({...v,symbol:e.target.value.toUpperCase()}))}/></label><label>구분<select value={orderForm.side} onChange={e=>setOrderForm(v=>({...v,side:e.target.value}))}><option value="buy">매수</option><option value="sell">매도</option></select></label><label>수량<input type="number" min="1" value={orderForm.quantity} onChange={e=>setOrderForm(v=>({...v,quantity:e.target.value}))}/></label><button className={orderForm.side==='buy'?'primary':'danger'} disabled={busy}>{busy?'처리 중':`모의 ${orderForm.side==='buy'?'매수':'매도'}`}</button></form>}
    <section className="panel overseas-table-panel"><h3>해외 보유 종목</h3><div className="table-scroll"><table><thead><tr><th>종목</th><th>수량</th><th>평균단가</th><th>현재가</th><th>평가금액</th><th>수익률</th><th>금일 순익</th></tr></thead><tbody>{(portfolio?.holdings||[]).map(row=><tr key={row.symbol}><td><b>{row.symbol}</b><small>{row.name}</small></td><td>{row.quantity}</td><td>{usd(row.avg_price)}</td><td>{usd(row.current_price)}</td><td>{usd(row.evaluation_amount)}</td><td className={row.return_rate>0?'up':row.return_rate<0?'down':''}>{row.return_rate>0?'+':''}{row.return_rate}%</td><td className={row.day_profit>0?'up':row.day_profit<0?'down':''}>{usd(row.day_profit)}</td></tr>)}{!(portfolio?.holdings||[]).length&&<tr><td colSpan="7" className="empty">보유 중인 해외 모의종목이 없습니다.</td></tr>}</tbody></table></div></section>
    {view==='trading'&&<section className="panel overseas-table-panel"><h3>최근 주문</h3><div className="table-scroll"><table><thead><tr><th>시간</th><th>종목</th><th>구분</th><th>수량</th><th>체결가</th><th>금액</th></tr></thead><tbody>{orders.map(row=><tr key={row.id}><td>{new Date(row.created_at).toLocaleString('ko-KR')}</td><td>{row.symbol}</td><td>{row.side==='buy'?'매수':'매도'}</td><td>{row.quantity}</td><td>{usd(row.price)}</td><td>{usd(row.amount)}</td></tr>)}</tbody></table></div></section>}
   </>}
  </>
  {selected&&<div className="overseas-detail-backdrop" onMouseDown={e=>e.target===e.currentTarget&&setSelected(null)}><article className="overseas-detail panel"><button type="button" className="icon-btn" onClick={()=>setSelected(null)} aria-label="닫기"><X size={18}/></button><span>미국 상장 종목</span><h2>{selected.profile?.name_ko?`${selected.symbol}(${selected.profile.name_ko})`:selected.symbol}<small>{selected.profile?.name||selected.symbol}</small></h2><strong>{selected.quote?.available?usd(selected.quote.price):'시세 없음'}</strong><em className={selected.quote?.change_percent>0?'up':selected.quote?.change_percent<0?'down':''}>{selected.quote?.change_percent>0?'+':''}{Number(selected.quote?.change_percent||0).toFixed(2)}%</em><dl><div><dt>종합점수</dt><dd>{selected.analysis?.score===null||selected.analysis?.score===undefined?'분석 대기':`${Math.round(selected.analysis.score)}점 · ${selected.analysis.label}`}</dd></div><div><dt>내 투자성향</dt><dd>{selected.analysis?.profile_score===null||selected.analysis?.profile_score===undefined?'성향 검사 필요':`${Math.round(selected.analysis.profile_score)}점 · ${selected.analysis.profile_label}`}</dd></div><div><dt>거래소</dt><dd>{selected.profile?.exchange||'-'}</dd></div><div><dt>통화</dt><dd>{selected.profile?.currency||'USD'}</dd></div><div><dt>데이터 범위</dt><dd>{Math.round(Number(selected.analysis?.coverage||0))}%</dd></div><div><dt>시세 제공</dt><dd>{selected.quote?.provider||'없음'} · 지연</dd></div></dl><h3>최근 SEC 공시</h3><div className="overseas-filings">{(selected.filings||[]).map((row,index)=><a key={`${row.form}-${index}`} href={row.url} target="_blank" rel="noreferrer"><b>{row.form}</b><span>{row.filed_at}</span><ExternalLink size={14}/></a>)}{!(selected.filings||[]).length&&<p>SEC 연락처를 설정하면 최근 공시를 함께 표시합니다.</p>}</div></article></div>}
 </div>
}

function AccountProfilePage({user,navigatePage}){
 const tier=String(user?.membership_tier||user?.account_type||'NORMAL').toUpperCase()
 const roleLabel=user?.membership_label||({NORMAL:'일반 회원',PREMIUM:'프리미엄 회원',EVENT:'이벤트 회원',ADMIN:'관리자'}[tier]||'일반 회원')
 const roleClass=tier.toLowerCase()
 const initials=String(user?.display_name||user?.username||'S').trim().slice(0,1).toUpperCase()
 const memberProfile=user?.member_profile||{}
 const genderLabel={male:'남성',female:'여성',other:'기타',prefer_not_to_say:'응답하지 않음'}[memberProfile.gender]||'-'
 const featureOn=key=>user?.features?.[key]?.enabled!==false
 const profileTools=[
  {id:'settings',title:'계정 연동',desc:'모의투자와 실전투자 키·계좌를 각각 연결하고 테스트합니다.',icon:Settings,enabled:featureOn('kiwoom_settings'),action:'계정 연동 열기'},
  {id:'profile',title:'투자 성향 분석',desc:'내 투자 성향 결과를 확인하거나 다시 검사할 수 있습니다.',icon:Fingerprint,enabled:true,action:user?.has_investment_profile===false?'검사 시작':'결과 확인'}
 ]

 return <div className="account-profile-page">
  <div className="page-head account-profile-head">
   <div>
    <span>MY PROFILE</span>
    <h1>프로필</h1>
    <p>계정 정보부터 거래 연동, 투자 성향과 화면 설정까지 한곳에서 관리합니다. 포트폴리오는 왼쪽 메인 메뉴에서 바로 확인할 수 있습니다.</p>
   </div>
  </div>

  <section className="account-profile-hero panel">
   <div className="account-profile-avatar">{initials}</div>
   <div className="account-profile-identity">
    <div className="account-profile-name-row">
     <h2>{user?.display_name||user?.username}</h2>
     <em className={roleClass}>{roleLabel}</em>
    </div>
    <p>내 StockLog 계정</p>
    <AiUsageBadge user={user}/>
   </div>
   <button type="button" className="secondary account-profile-edit" disabled title="프로필 편집 기능은 준비 중입니다."><Edit3 size={16}/>프로필 편집</button>
  </section>

  <section className="panel account-profile-section account-profile-wide account-profile-service-hub">
   <div className="account-profile-section-head"><div><span>MY SERVICES</span><h3>내 투자 · 거래 관리</h3></div><Gauge size={20}/></div>
   <p className="account-profile-section-desc">계정과 연결된 설정 기능을 한곳에서 관리합니다. 포트폴리오와 모의투자는 왼쪽 메인 메뉴에 배치했습니다.</p>
   <div className="account-profile-service-grid">
    {profileTools.map(item=>{
     const Icon=item.icon
     return <button type="button" key={item.id} className="account-profile-service-card" disabled={!item.enabled} onClick={()=>item.enabled&&navigatePage?.(item.id)}>
      <span className="account-profile-service-icon"><Icon size={19}/></span>
      <span className="account-profile-service-copy"><b>{item.title}</b><small>{item.desc}</small></span>
      <span className="account-profile-service-action">{item.enabled?item.action:'현재 등급에서 사용 불가'}<ChevronRight size={14}/></span>
     </button>
    })}
   </div>
  </section>

  <div className="account-profile-grid">
   <section className="panel account-profile-section">
    <div className="account-profile-section-head"><div><span>ACCOUNT</span><h3>기본 정보</h3></div><UserRound size={20}/></div>
    <dl className="account-profile-info-list">
     <div><dt>이름</dt><dd>{memberProfile.name||user?.display_name||'-'}</dd></div>
     <div><dt>성별</dt><dd>{genderLabel}</dd></div>
     <div><dt>출생연도</dt><dd>{memberProfile.birth_year?`${memberProfile.birth_year}년`:'-'}</dd></div>
     <div><dt>휴대폰</dt><dd>{memberProfile.phone_number_masked||'-'}</dd></div>
     <div><dt>회원 유형</dt><dd>{roleLabel}</dd></div>
    </dl>
   </section>

   <section className="panel account-profile-section">
    <div className="account-profile-section-head"><div><span>SOCIAL</span><h3>연결 계정</h3></div><ExternalLink size={20}/></div>
    <div className="account-profile-placeholder">
     <b>소셜 계정 관리</b>
     <p>카카오 / 네이버 / 구글 연결 상태 확인과 계정 연결/해제 기능을 추가할 수 있도록 준비한 영역입니다.</p>
     <span>준비 중</span>
    </div>
   </section>

  </div>
 </div>
}

function GlobalMarketTicker({marketRegion='domestic'}){
 const [items,setItems]=useState([]),[loading,setLoading]=useState(true),[updatedAt,setUpdatedAt]=useState(null)
 const load=async(silent=false)=>{
  if(!silent)setLoading(true)
  try{const r=await api.get('/api/market-overview',{timeout:10000});setItems(Array.isArray(r.data?.items)?r.data.items:[]);setUpdatedAt(new Date())}
  catch{if(!silent)setItems([])}
  finally{if(!silent)setLoading(false)}
 }
 useEffect(()=>{
  load()
  const timer=setInterval(()=>{if(document.visibilityState==='visible')load(true)},30000)
  return()=>clearInterval(timer)
 },[])
 const fallback=[{key:'nasdaq',label:'NASDAQ'},{key:'kospi',label:'KOSPI'},{key:'kosdaq',label:'KOSDAQ'},{key:'usdkrw',label:'달러/원'},{key:'usdjpy',label:'원/엔'}]
 return <section className={`global-market-ticker ${marketRegion}`} aria-label="주요 시장지표">
  <div className="global-market-ticker-title"><span><Activity size={15}/>주요 시장지표</span><small>{loading?'업데이트 중':updatedAt?updatedAt.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'}):'연결 대기'}</small></div>
  <div className="global-market-ticker-items">{(items.length?items:fallback).map(item=>{const value=Number(item.value),rate=Number(item.change_rate),available=item.available!==false&&Number.isFinite(value),rounded=available?Math.round(value).toLocaleString('ko-KR'):'—',suffix=String(item.value_suffix||'').trim(),displayValue=!available?'—':['달러','USD','$'].includes(suffix)?`$${rounded}`:suffix==='원'?`${rounded}원`:`${rounded}${suffix}`;return <span key={item.key} className="global-market-ticker-item"><b>{item.label}</b><em>{displayValue}</em><i className={rate>0?'up':rate<0?'down':'flat'}>{Number.isFinite(rate)?`${rate>0?'+':''}${rate.toFixed(2)}%`:''}</i></span>})}</div>
 </section>
}

export default function App(){
 const initialRoute=readStocklogRoute()
 const [user,setUser]=useState(null),[page,setPage]=useState(initialRoute.page),[detail,setDetail]=useState(initialRoute.detail),[tradeIntent,setTradeIntent]=useState(null),[loading,setLoading]=useState(true)
 const [tradingEnvironment,setTradingEnvironment]=useState(initialRoute.environment)
 const [marketRegion,setMarketRegion]=useState(initialRoute.market)
 const [bootError,setBootError]=useState('')
 const [accessDenied,setAccessDenied]=useState(null)
 const [bootRetry,setBootRetry]=useState(0)
 const [pageTransition,setPageTransition]=useState(null)
 const [pageTransitionStage,setPageTransitionStage]=useState(0)
 const mobileNavRef=useRef(null)
 useEffect(()=>{
  document.documentElement.setAttribute('data-stocklog-theme','light')
  document.documentElement.style.colorScheme='light'
  localStorage.removeItem('stocklog_ui_theme')
 },[])

 const writeRoute=(nextPage,{stock=null,smartMode='ai',replace=false,environment=tradingEnvironment,market=marketRegion}={})=>{
  const url=new URL(window.location.href)
  url.searchParams.set('page',nextPage)
  if(INVESTMENT_PAGE_IDS.has(nextPage))url.searchParams.set('environment',environment==='live'?'live':'mock')
  else url.searchParams.delete('environment')
  if(market==='overseas')url.searchParams.set('market','overseas')
  else url.searchParams.delete('market')
  if(stock){
   url.searchParams.set('stock',String(stock))
   url.searchParams.set('smart_mode',smartMode||'ai')
  }else{
   url.searchParams.delete('stock')
   url.searchParams.delete('smart_mode')
  }
  const target=`${url.pathname}${url.search}${url.hash}`
  if(replace)window.history.replaceState({stocklog:true,page:nextPage},'',target)
  else window.history.pushState({stocklog:true,page:nextPage},'',target)
 }

 const startPageTransition=(nextPage,nextMarket=marketRegion)=>{
  setPageTransitionStage(0)
  setPageTransition({page:nextPage,market:nextMarket,startedAt:Date.now()})
 }

 useEffect(()=>{
  if(!pageTransition)return
  const first=setTimeout(()=>setPageTransitionStage(1),70)
  const second=setTimeout(()=>setPageTransitionStage(2),150)
  const finish=setTimeout(()=>setPageTransition(null),280)
  return()=>{clearTimeout(first);clearTimeout(second);clearTimeout(finish)}
 },[pageTransition?.startedAt])

 useEffect(()=>{
  if(initialRoute.legacy)writeRoute(initialRoute.page,{stock:initialRoute.detail?.code||null,smartMode:initialRoute.detail?.smartMode||'ai',environment:initialRoute.environment,replace:true})
 },[])

 useEffect(()=>{
  const params=new URLSearchParams(window.location.search)
  const forcedAdmin=Boolean(params.get('social_test_session'))
  if(forcedAdmin){setPage('admin');setDetail(null)}
  const t=localStorage.getItem('stocklog_token')
  setBootError('')
  setAccessDenied(null)
  setLoading(true)
  // Check the server-side IP gate before rendering login or restoring a token.
  // This endpoint is intentionally the only public policy probe.
  api.get('/api/access/status',{timeout:7000,__stocklogNoRetry:true})
   .then(access=>{
    if(access.data?.allowed===false){
     setUser(null);setAccessDenied(access.data)
     return null
    }
    if(!t)return null
    // Bootstrap must have a hard upper bound. A saturated backend previously
    // inherited the global 120s timeout + retry and looked like an infinite
    // "StockLog 로딩 중..." screen. Do not retry this health/auth probe.
    return api.get('/api/auth/me',{timeout:10000,__stocklogNoRetry:true}).then(r=>{
     setUser(r.data)
     const route=readStocklogRoute()
     const target=r.data?.has_investment_profile===false?'profile':forcedAdmin?'admin':route.page
     setPage(target)
     const nextEnvironment=availableInvestmentEnvironment(route.environment,r.data)
     setTradingEnvironment(route.market==='overseas'?'mock':nextEnvironment)
     setMarketRegion(route.market)
     setDetail(target===route.page?route.detail:null)
     if(target!==route.page||nextEnvironment!==route.environment)writeRoute(target,{environment:nextEnvironment,replace:true})
     return r
    })
   })
   .catch(err=>{
    if(err?.response?.data?.code==='ip_not_allowed'){
     setUser(null);setAccessDenied(err.response.data)
     return
    }
    const status=Number(err?.response?.status||0)
    if(status===401){
     localStorage.removeItem('stocklog_token')
     setUser(null)
     return
    }
    // Network/DB pressure is not an authentication failure. Keep the token so
    // the user can retry after the server recovers instead of being logged out.
    setBootError('서버 연결이 지연되어 로그인 상태를 확인하지 못했습니다. 동기화 작업이 복구된 뒤 다시 연결할 수 있습니다.')
   })
   .finally(()=>setLoading(false))
 },[bootRetry])

 // Browser history is the navigation source of truth. This keeps refresh and
 // back/forward behavior consistent for every workspace page and stock detail.
 useEffect(()=>{
  const onPopState=()=>{
   const route=readStocklogRoute()
   const nextEnvironment=availableInvestmentEnvironment(route.environment,user)
   startPageTransition(route.page,route.market)
   setPage(route.page)
   setTradingEnvironment(route.market==='overseas'?'mock':nextEnvironment)
   setMarketRegion(route.market)
   setDetail(route.detail)
   setTradeIntent(null)
   if(route.legacy||nextEnvironment!==route.environment)writeRoute(route.page,{stock:route.detail?.code||null,smartMode:route.detail?.smartMode||'ai',environment:nextEnvironment,replace:true})
   requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'auto'}))
  }
  window.addEventListener('popstate',onPopState)
  return()=>window.removeEventListener('popstate',onPopState)
 },[user])

 useEffect(()=>{
  if(!user)return
  const featureOn=key=>user?.features?.[key]?.enabled!==false
  const canMock=featureOn('mock_trading')
  const canLive=featureOn('live_trading')
  if(INVESTMENT_PAGE_IDS.has(page)){
   const environmentAllowed=tradingEnvironment==='live'?canLive:canMock
   if(!environmentAllowed){
    const fallback=canMock?'mock':canLive?'live':null
    if(fallback){
     setTradingEnvironment(fallback)
     writeRoute(page,{environment:fallback,replace:true})
     return
    }
   }
  }
  const allowed=(
   page==='smart'?featureOn('smart_analysis'):
   page==='themes'?featureOn('theme_analysis'):
   page==='flow'?featureOn('flow_analysis'):
   INVESTMENT_PAGE_IDS.has(page)?(canMock||canLive):
   page==='settings'?featureOn('kiwoom_settings'):
   page==='admin'?Boolean(user.is_admin):true
  )
  if(!allowed){setPage('smart');setDetail(null);writeRoute('smart',{replace:true})}
 },[user,page,tradingEnvironment])

 useEffect(()=>{
  if(!user||window.innerWidth>760)return
  const nav=mobileNavRef.current
  const activeItem=nav?.querySelector('button.active')
  if(!nav||!activeItem)return
  const left=activeItem.offsetLeft-(nav.clientWidth-activeItem.offsetWidth)/2
  const reduceMotion=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  nav.scrollTo({left:Math.max(0,left),behavior:reduceMotion?'auto':'smooth'})
 },[page,user])

 useEffect(()=>{
  const expire=()=>{
   setBootError('')
   setUser(null)
   setDetail(null)
   setTradeIntent(null)
   setPage('smart')
   writeRoute('smart',{replace:true})
  }
  window.addEventListener('stocklog:auth-expired',expire)
  return()=>window.removeEventListener('stocklog:auth-expired',expire)
 },[])

 useEffect(()=>{
  const deny=event=>{
   setUser(null);setBootError('');setLoading(false)
   setAccessDenied(event?.detail||{client_ip:'확인 불가'})
  }
  window.addEventListener('stocklog:access-denied',deny)
  return()=>window.removeEventListener('stocklog:access-denied',deny)
 },[])

 if(loading)return <div className="splash"><div className="splash-status"><b>StockLog 로딩 중...</b><span>서버와 로그인 상태를 확인하고 있습니다.</span></div></div>
 if(accessDenied)return <div className="splash access-denied-splash"><div className="splash-status splash-status-error access-denied-card"><span className="access-denied-icon"><LockKeyhole size={25}/></span><b>StockLog 접속 제한</b><span>현재 IP는 관리자가 설정한 접속 허용 목록에 포함되어 있지 않습니다.</span><small>현재 접속 IP <strong>{accessDenied.client_ip||'확인 불가'}</strong></small><button type="button" className="primary" onClick={()=>setBootRetry(v=>v+1)}>접속 권한 다시 확인</button></div></div>
 if(bootError)return <div className="splash"><div className="splash-status splash-status-error"><b>StockLog 연결 지연</b><span>{bootError}</span><button type="button" className="primary" onClick={()=>setBootRetry(v=>v+1)}>다시 연결</button></div></div>
 if(!user)return <Login onLogin={value=>{
 setUser(value)
  const route=readStocklogRoute()
  const target=value?.show_investment_profile||value?.has_investment_profile===false?'profile':route.page
  const nextEnvironment=availableInvestmentEnvironment(route.environment,value)
  setTradingEnvironment(route.market==='overseas'?'mock':nextEnvironment)
  setMarketRegion(route.market)
  setPage(target);setDetail(target===route.page?route.detail:null)
  if(target!==route.page||nextEnvironment!==route.environment)writeRoute(target,{environment:nextEnvironment,replace:true})
 }}/>

 const logout=()=>{
  localStorage.removeItem('stocklog_token')
  setDetail(null)
  setTradeIntent(null)
  const url=new URL(window.location.href)
  ;['admin','social_test_session','page','stock','smart_mode','environment','market'].forEach(key=>url.searchParams.delete(key))
  window.history.replaceState({},'',`${url.pathname}${url.search}${url.hash}`)
  setPage('smart')
  setTradingEnvironment('mock')
  setUser(null)
 }

 const navigatePage=(id,{environment=tradingEnvironment}={})=>{
  const canonical=LEGACY_LIVE_PAGE_MAP[id]||id
  const requestedEnvironment=LEGACY_LIVE_PAGE_MAP[id]?'live':environment==='live'?'live':'mock'
  const nextEnvironment=availableInvestmentEnvironment(requestedEnvironment,user)
  setDetail(null)
  if(canonical!=='trading')setTradeIntent(null)
  if(INVESTMENT_PAGE_IDS.has(canonical))setTradingEnvironment(nextEnvironment)
  const params=new URLSearchParams(window.location.search)
  if(page!==canonical||params.get('stock')||(INVESTMENT_PAGE_IDS.has(canonical)&&params.get('environment')!==nextEnvironment))startPageTransition(canonical,marketRegion)
  if(page!==canonical||params.get('stock')||(INVESTMENT_PAGE_IDS.has(canonical)&&params.get('environment')!==nextEnvironment))writeRoute(canonical,{environment:nextEnvironment})
  setPage(canonical)
  requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'auto'}))
 }

 const changeTradingEnvironment=nextEnvironment=>{
  if(marketRegion==='overseas')return
  if(!INVESTMENT_PAGE_IDS.has(page)||nextEnvironment===tradingEnvironment)return
  startPageTransition(page,marketRegion)
  setTradingEnvironment(nextEnvironment)
  setTradeIntent(null)
  setDetail(null)
  writeRoute(page,{environment:nextEnvironment})
  requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'auto'}))
 }

 const changeMarketRegion=nextMarket=>{
  const market=nextMarket==='overseas'?'overseas':'domestic'
  if(market===marketRegion)return
  startPageTransition(page,market)
  setMarketRegion(market);setDetail(null);setTradeIntent(null)
  if(market==='overseas')setTradingEnvironment('mock')
  writeRoute(page,{market,environment:market==='overseas'?'mock':tradingEnvironment})
  requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'auto'}))
 }

 const openDetail=value=>{
  const next=typeof value==='string'?{code:value}:{...value}
  if(!next?.code)return
  setDetail(next)
  writeRoute(page,{stock:next.code,smartMode:next.smartMode||'ai'})
 }
 const closeDetail=()=>{
  const params=new URLSearchParams(window.location.search)
  if(params.get('stock')&&window.history.state?.stocklog){
   window.history.back()
   return
  }
  setDetail(null)
  writeRoute(page,{replace:true})
 }
 const buyFromDetail=stock=>{
  setTradeIntent({
   code:stock.code,
   name:stock.name,
   market:stock.market,
   themes:stock.themes||[],
   theme_fallback:stock.theme_fallback||null,
   side:'buy',
   nonce:Date.now()
  })
  setDetail(null)
  startPageTransition('trading',marketRegion)
  setPage('trading')
  writeRoute('trading',{environment:tradingEnvironment})
  requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'auto'}))
 }
 const can=key=>user?.features?.[key]?.enabled!==false
 const signedInName=String(user?.display_name||user?.username||'회원').trim()
 const signedInGreeting=`${signedInName.endsWith('님')?signedInName:`${signedInName}님`},`
 const analysisItems=[]
 const investmentItems=[]
 if(can('smart_analysis'))analysisItems.push(['smart','스마트 분석','분석',Activity])
 if(can('theme_analysis'))analysisItems.push(['themes','인기테마 분석','인기테마',TrendingUp])
 if(can('flow_analysis'))analysisItems.push(['flow','수급 분석','수급',Users])
 if(can('mock_trading')||can('live_trading')){
  investmentItems.push(['portfolio','포트폴리오','포트폴리오',Landmark])
  investmentItems.push(['trading','증권투자(수동)','수동투자',CircleDollarSign])
  investmentItems.push(['trading-auto','증권투자(자동)','자동투자',Sparkles])
 }
 const adminItem=user.is_admin?['admin','관리자','관리',ShieldCheck]:null
 const renderNavItem=([id,name,mobileName,Icon])=><button type="button" key={id} title={name} aria-label={name} aria-current={page===id?'page':undefined} className={page===id?'active':''} onClick={()=>navigatePage(id)}><Icon size={18}/><span className="nav-label nav-label-desktop">{name}</span><span className="nav-label nav-label-mobile">{mobileName}</span><ChevronRight className="nav-chevron" size={14}/></button>
 return <><GlobalDialog/><GlobalTradeFillNotifier enabled={marketRegion==='domestic'&&can('mock_trading')&&tradingEnvironment==='mock'&&page!=='admin'}/><div className={`app market-${marketRegion}`}>
  <a className="skip-link" href="#stocklog-main">본문으로 건너뛰기</a>
  <header className="mobile-app-header">
   <div className="mobile-app-brand"><BarChart3 size={20}/><b>StockLog</b></div>
   <div className="mobile-app-user-actions">
    <button type="button" className={`mobile-profile-button ${page==='account-profile'?'active':''}`} onClick={()=>navigatePage('account-profile')} aria-label="프로필">
     <Settings size={17}/><span>{signedInGreeting}</span>
    </button>
    <button type="button" className="mobile-logout-button" onClick={logout} aria-label="로그아웃" title="로그아웃"><LogOut size={17}/></button>
   </div>
  </header>
  <aside className="app-sidebar">
   <div className="logo sidebar-brand">
    <span className="sidebar-brand-mark"><BarChart3/></span>
    <span className="logo-word sidebar-brand-copy"><b>StockLog</b></span>
   </div>
   <div className="sidebar-account-compact"><span className="sidebar-account-name">{signedInGreeting}</span><button type="button" className={`sidebar-settings-button ${page==='account-profile'?'active':''}`} title="계정 설정" aria-label="계정 설정" onClick={()=>navigatePage('account-profile')}><Settings size={17}/></button><button type="button" className="sidebar-account-exit" title="로그아웃" aria-label="로그아웃" onClick={logout}><LogOut size={17}/></button></div>
   <div className="market-region-switch" role="tablist" aria-label="증권 시장 선택"><button type="button" role="tab" aria-selected={marketRegion==='domestic'} className={marketRegion==='domestic'?'active':''} onClick={()=>changeMarketRegion('domestic')}><Landmark size={15}/>국내증권</button><button type="button" role="tab" aria-selected={marketRegion==='overseas'} className={marketRegion==='overseas'?'active':''} onClick={()=>changeMarketRegion('overseas')}><Globe2 size={15}/>해외증권</button></div>
   <nav ref={mobileNavRef} className="app-nav" aria-label="주요 메뉴">
    <span className="sidebar-nav-caption">종목 분석</span>
    {analysisItems.map(renderNavItem)}
    {investmentItems.length>0&&<><span className="sidebar-nav-caption investment-caption">증권투자</span>{investmentItems.map(renderNavItem)}</>}
    {adminItem&&<><span className="sidebar-nav-caption admin-caption">관리</span>{renderNavItem(adminItem)}</>}
   </nav>
  </aside>
  <main id="stocklog-main" className="app-main" tabIndex={-1}>
   <GlobalMarketTicker marketRegion={marketRegion}/>
   {page==='smart'&&(marketRegion==='overseas'?<OverseasWorkspace view="smart"/>:<Smart openStock={openDetail}/>)}
   {page==='themes'&&(marketRegion==='overseas'?<OverseasWorkspace view="themes"/>:<Themes openStock={openDetail} user={user}/>)}
   {page==='flow'&&(marketRegion==='overseas'?<OverseasWorkspace view="flow"/>:<FlowAnalysis openStock={openDetail} user={user}/>)}
   {page==='trading'&&(marketRegion==='overseas'?<OverseasWorkspace view="trading"/>:<InvestmentPageShell environment={tradingEnvironment} onEnvironmentChange={changeTradingEnvironment} canMock={can('mock_trading')} canLive={can('live_trading')}><Trading key={`manual-${tradingEnvironment}`} intent={tradeIntent} user={user} environment={tradingEnvironment}/></InvestmentPageShell>)}
   {page==='trading-auto'&&(marketRegion==='overseas'?<OverseasWorkspace view="trading-auto"/>:<InvestmentPageShell environment={tradingEnvironment} onEnvironmentChange={changeTradingEnvironment} canMock={can('mock_trading')} canLive={can('live_trading')}><AutoTrading key={`auto-${tradingEnvironment}`} user={user} navigatePage={navigatePage} environment={tradingEnvironment}/></InvestmentPageShell>)}
   {page==='auto-settings'&&(marketRegion==='overseas'?<OverseasWorkspace view="auto-settings"/>:<InvestmentPageShell environment={tradingEnvironment} onEnvironmentChange={changeTradingEnvironment} canMock={can('mock_trading')} canLive={can('live_trading')}><AutoTradingSettingsPage key={`auto-settings-${tradingEnvironment}`} navigatePage={navigatePage} environment={tradingEnvironment}/></InvestmentPageShell>)}
   {page==='portfolio'&&(marketRegion==='overseas'?<OverseasWorkspace view="portfolio"/>:<InvestmentPageShell environment={tradingEnvironment} onEnvironmentChange={changeTradingEnvironment} canMock={can('mock_trading')} canLive={can('live_trading')}><PortfolioPage key={`portfolio-${tradingEnvironment}`} user={user} openStock={openDetail} environment={tradingEnvironment}/></InvestmentPageShell>)}
   {page==='settings'&&<TradingConnectionSettings/>}
   {page==='account-profile'&&<AccountProfilePage user={user} navigatePage={navigatePage}/>}
   {page==='profile'&&<InvestmentProfilePage/>}
   {page==='admin'&&user.is_admin&&<Admin currentUser={user}/>}
  </main>
  {marketRegion==='domestic'&&detail&&<StockDetail code={detail.code} smartMode={detail.smartMode||'ai'} recommendScore={detail.recommendScore} recommendType={detail.recommendType||''} onBuy={buyFromDetail} onClose={closeDetail} user={user}/>}
 </div>{pageTransition&&<WorkspacePageLoadingOverlay market={pageTransition.market} page={pageTransition.page} stage={pageTransitionStage}/>}</>
}
