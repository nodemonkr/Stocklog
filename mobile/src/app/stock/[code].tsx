import { useCallback, useEffect, useState } from 'react';
import { Alert, Linking, Pressable, StyleSheet, Text, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Button, Card, Chip, Empty, ErrorState, Loading, PageHeader, Screen, SectionTitle, Stat } from '@/components/ui';
import { colors } from '@/constants/theme';
import { useAuth } from '@/context/AuthContext';
import { get, postParams } from '@/lib/api';
import { compactWon, dateTime, errorText, n, pct, qty, won } from '@/lib/format';

function Spark({chart}:{chart:any[]}){const rows=(chart||[]).slice(-48),values=rows.map(x=>n(x.close??x.price)).filter(Boolean);const min=Math.min(...values),max=Math.max(...values);if(!values.length)return <View style={s.chartEmpty}><Text style={s.muted}>차트 데이터 없음</Text></View>;return <View style={s.spark}>{values.map((v,i)=>{const h=12+((v-min)/Math.max(1,max-min))*80;return <View key={i} style={[s.bar,{height:h,backgroundColor:i===values.length-1?colors.primary:'#C9D0E8'}]}/>})}</View>}
function Pager({page,pages,setPage}:{page:number;pages:number;setPage:(v:number)=>void}){if(pages<=1)return null;return <View style={s.pager}><Button compact tone="secondary" title="이전" disabled={page<=1} onPress={()=>setPage(Math.max(1,page-1))}/><Text style={s.pageText}>{page} / {pages}</Text><Button compact tone="secondary" title="다음" disabled={page>=pages} onPress={()=>setPage(Math.min(pages,page+1))}/></View>}
function SentimentBadge({value}:{value?:string}){const sentiment=String(value||'neutral').toLowerCase(),positive=sentiment==='positive',negative=sentiment==='negative',label=positive?'긍정':negative?'부정':'관망',color=positive?colors.positive:negative?colors.negative:colors.text3,backgroundColor=positive?colors.positiveSoft:negative?colors.negativeSoft:colors.surfaceMuted;return <View style={[s.sentimentBadge,{borderColor:color,backgroundColor}]}><Text style={[s.sentimentBadgeText,{color}]}>{label}</Text></View>}
function NewsList({items}:{items:any[]}){if(!items?.length)return <Empty title="표시할 항목이 없습니다."/>;return <View style={{gap:8}}>{items.map((x:any,i:number)=><Pressable key={`${x.url||x.link||i}`} onPress={()=>{const u=x.url||x.link;if(u)void Linking.openURL(u)}}><Card style={{shadowOpacity:0}}><View style={s.newsHead}><Text style={s.newsTitle}>{x.title||x.report_title||x.name||'제목 없음'}</Text><SentimentBadge value={x.sentiment}/></View><Text style={s.newsSub}>{x.press||x.source||x.broker||''} {dateTime(x.published_at||x.date||x.report_date)}</Text>{x.summary?<Text numberOfLines={4} style={s.newsBody}>{x.summary}</Text>:null}</Card></Pressable>)}</View>}
function FilteredBlock({title,items,filter,setFilter,page,setPage}:{title:string;items:any[];filter:string;setFilter:(v:string)=>void;page:number;setPage:(v:number)=>void}){const size=3,filtered=filter==='all'?items:items.filter(x=>String(x.sentiment||'neutral')===filter),pages=Math.max(1,Math.ceil(filtered.length/size)),safe=Math.min(page,pages),visible=filtered.slice((safe-1)*size,safe*size);useEffect(()=>{if(page>pages)setPage(pages)},[page,pages,setPage]);return <View style={{gap:8}}><SectionTitle title={title} hint={`${filtered.length}건`}/><View style={s.tags}><Chip label="전체" active={filter==='all'} onPress={()=>{setFilter('all');setPage(1)}}/><Chip label="긍정" active={filter==='positive'} onPress={()=>{setFilter('positive');setPage(1)}}/><Chip label="중립" active={filter==='neutral'} onPress={()=>{setFilter('neutral');setPage(1)}}/><Chip label="부정" active={filter==='negative'} onPress={()=>{setFilter('negative');setPage(1)}}/></View><NewsList items={visible}/><Pager page={safe} pages={pages} setPage={setPage}/></View>}

export default function StockDetail(){
 const {user}=useAuth();
 const {code}=useLocalSearchParams<{code:string}>();
 const stockCode=String(code||'');
 const [data,setData]=useState<any>(null),[preview,setPreview]=useState<any>({quote:null,chart:[]}),[detailLoading,setDetailLoading]=useState(true),[aiStatus,setAiStatus]=useState<any>(null),[aiUsage,setAiUsage]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[refreshingNews,setRefreshingNews]=useState(false),[section,setSection]=useState<'overview'|'flow'|'news'|'ai'>('overview');
 const [reportPage,setReportPage]=useState(1),[newsPage,setNewsPage]=useState(1),[disclosurePage,setDisclosurePage]=useState(1),[reportFilter,setReportFilter]=useState('all'),[newsFilter,setNewsFilter]=useState('all');
 const aiAllowed=user?.features?.ai_analysis?.enabled!==false;

 const loadPreview=useCallback(async()=>{
  if(!stockCode)return;
  const [q,c]=await Promise.allSettled([get<any>(`/api/stocks/${stockCode}/quote`),get<any>(`/api/stocks/${stockCode}/chart/cached`)]);
  setPreview({quote:q.status==='fulfilled'?q.value:null,chart:c.status==='fulfilled'?(c.value?.chart||[]):[]});
 },[stockCode]);
 const loadDetail=useCallback(async(refreshNews=false,silent=false)=>{
  if(!stockCode)return;
  if(!silent)setDetailLoading(true);
  try{
   const d=await get<any>(`/api/stocks/${stockCode}/detail`,{smart_mode:'ai',refresh_news:refreshNews});
   setData(d);setError('');
  }catch(e){
   if(!silent)setError(errorText(e));
  }finally{
   if(!silent)setDetailLoading(false);
  }
 },[stockCode]);
 const loadAiMeta=useCallback(async()=>{
  if(!aiAllowed||!stockCode){setAiStatus(null);setAiUsage(null);return}
  const [status,usage]=await Promise.allSettled([get<any>(`/api/stocks/${stockCode}/ai-analysis/status`,{smart_mode:'ai'}),get<any>('/api/ai-usage')]);
  if(status.status==='fulfilled')setAiStatus(status.value);
  if(usage.status==='fulfilled')setAiUsage(usage.value);
 },[stockCode,aiAllowed]);

 useEffect(()=>{
  setData(null);setPreview({quote:null,chart:[]});setError('');setDetailLoading(true);setSection('overview');setReportPage(1);setNewsPage(1);setDisclosurePage(1);
  void loadPreview();void loadDetail(false,false);void loadAiMeta();
 },[loadPreview,loadDetail,loadAiMeta]);
 useEffect(()=>{
  if(!['queued','context','running','obot_running','obot_completed','gbot_running','gbot_completed','verifying'].includes(String(aiStatus?.status||'')))return;
  const id=setInterval(async()=>{try{const st=await get<any>(`/api/stocks/${stockCode}/ai-analysis/status`,{smart_mode:'ai'});setAiStatus(st);if(['ready','stale','failed'].includes(st?.status)){clearInterval(id);get('/api/ai-usage').then(setAiUsage).catch(()=>{})}}catch{}},2000);
  return()=>clearInterval(id)
 },[aiStatus?.status,stockCode]);

 const fullStock=data?.stock||{};
 const quote=preview?.quote||{};
 const st={...quote,...fullStock,code:fullStock.code||quote.code||stockCode,name:fullStock.name||quote.name||quote.stock_name||stockCode,price:fullStock.price??quote.current_price??quote.price??0,change_rate:fullStock.change_rate??quote.change_rate??0};
 const change=n(st.change_rate),analysis=data?.analysis||{},investor=data?.investor_flow||{},flow=Array.isArray(investor)?investor:(investor.series||investor.items||[]),aiResult=aiStatus?.result||{},signal=aiResult?.action||aiResult?.recommendation||aiResult?.signal||analysis?.recommendation||analysis?.signal;
 const statuses=data?.data_status||{},reports=data?.reports||[],news=data?.news||[],disclosures=data?.disclosures||[];
 const themes=st.themes||data?.themes||[];
 const chart=(data?.chart&&data.chart.length?data.chart:preview.chart)||[];
 const hasPreview=Boolean(st.name&&st.name!==stockCode)||n(st.price)>0||chart.length>0;

 const beginAi=async(force:boolean)=>{setBusy(true);try{const r=await postParams<any>(`/api/stocks/${stockCode}/ai-analysis/start`,undefined,{smart_mode:'ai',force});setAiStatus((x:any)=>({...x,...r,status:r.status||'queued'}));setAiUsage(r.ai_usage||aiUsage)}catch(e){Alert.alert('AI 분석',errorText(e))}finally{setBusy(false)}};
 const askAi=async(force:boolean)=>{if(!aiAllowed){Alert.alert('AI 분석','현재 회원 등급에서는 AI 분석 기능을 사용할 수 없습니다.');return}let usage=aiUsage;try{usage=await get<any>('/api/ai-usage');setAiUsage(usage)}catch{}const available=usage?.unlimited?'무제한':usage?`${Number(usage.remaining||0)}회 남음`:'사용량 확인 필요';if(usage&&!usage.unlimited&&Number(usage.remaining||0)<=0){Alert.alert('AI 분석','오늘 사용할 수 있는 AI 분석 횟수를 모두 사용했습니다.');return}Alert.alert(force?'Gbot 다시 분석':'Gbot 분석',`Gbot이 재무·가격·수급·뉴스 등 핵심 투자 데이터를 종합해 의견과 근거를 정리합니다.\n\n오늘 이용 가능: ${available}\n분석을 시작할까요?`,[{text:'취소'},{text:'동의하고 시작',onPress:()=>void beginAi(force)}])};
 const refreshNews=async()=>{setRefreshingNews(true);try{await loadDetail(true,true);setNewsPage(1);setReportPage(1);setDisclosurePage(1)}finally{setRefreshingNews(false)}};
 const retryAll=()=>{void loadPreview();void loadDetail(false,false);void loadAiMeta()};

 if(!hasPreview&&!data&&!error)return <Screen><PageHeader title="종목"/><Loading label="현재가와 저장 차트를 먼저 준비하고 있습니다."/></Screen>;
 if(!hasPreview&&!data&&error)return <Screen><PageHeader title="종목" right={<Button compact tone="ghost" title="닫기" onPress={()=>router.back()}/>}/><ErrorState message={error} retry={retryAll}/></Screen>;

 return <Screen>
  <PageHeader eyebrow={`${st.market||''} · ${st.code||stockCode}`} title={st.name||stockCode} subtitle={st.display_category||st.primary_theme||st.sector||'종목 상세'} right={<Button compact tone="ghost" title="닫기" onPress={()=>router.back()}/>}/>
  {error&&hasPreview?<Card style={s.progressCard}><Text style={s.progressTitle}>일부 상세정보를 불러오지 못했습니다.</Text><Text style={s.muted}>{error}</Text><Button compact tone="secondary" title="상세 다시 불러오기" onPress={()=>void loadDetail(false,false)}/></Card>:null}
  <Card><View style={s.priceRow}><View><Text style={s.price}>{won(st.price)}</Text><Text style={[s.change,{color:change>=0?colors.positive:colors.negative}]}>{pct(change)}</Text></View>{signal?<Chip label={String(signal).toUpperCase()} active/>:detailLoading?<Chip label="상세 로딩 중"/>:null}</View><Spark chart={chart}/><View style={s.statWrap}><Stat label="시가총액" value={compactWon(st.market_cap)}/><Stat label="PER" value={n(st.per)?n(st.per).toFixed(1):'-'}/><Stat label="PBR" value={n(st.pbr)?n(st.pbr).toFixed(2):'-'}/><Stat label="ROE" value={n(st.roe)?pct(st.roe):'-'}/></View><View style={s.quick}><Button title="매수" onPress={()=>router.push({pathname:'/(tabs)/portfolio',params:{code:stockCode,side:'buy'}} as any)}/><Button title="매도" tone="secondary" onPress={()=>router.push({pathname:'/(tabs)/portfolio',params:{code:stockCode,side:'sell'}} as any)}/><Button title={aiStatus?.result?'AI 다시 분석':'AI 분석'} tone="ghost" disabled={busy||!aiAllowed} onPress={()=>void askAi(!!aiStatus?.result)}/></View></Card>
  {detailLoading?<Card style={s.progressCard}><Text style={s.progressTitle}>상세 분석을 추가로 불러오는 중</Text><Text style={s.muted}>현재가와 차트는 먼저 사용할 수 있습니다. 재무·수급·뉴스는 준비되는 대로 아래에 표시합니다.</Text></Card>:null}
  <View style={s.tabs}><Chip label="개요" active={section==='overview'} onPress={()=>setSection('overview')}/><Chip label="수급" active={section==='flow'} onPress={()=>setSection('flow')}/><Chip label="뉴스/리포트" active={section==='news'} onPress={()=>setSection('news')}/><Chip label="AI" active={section==='ai'} onPress={()=>setSection('ai')}/></View>

  {section==='overview'?<>
   <Card><SectionTitle title="데이터 상태"/>{Object.keys(statuses).length?<View style={s.statusGrid}>{Object.entries(statuses).map(([k,v]:any)=><View key={k} style={s.statusItem}><Chip label={v.ok?'정상':'확인 필요'} active={!!v.ok}/><Text style={s.statusTitle}>{k}</Text><Text style={s.statusMessage}>{v.message||'-'}</Text></View>)}</View>:detailLoading?<Loading label="데이터 상태 확인 중..."/>:<Empty title="데이터 상태 정보가 없습니다."/>}</Card>
   <Card><SectionTitle title="기업 지표"/><View style={s.statWrap}><Stat label="EPS" value={n(st.eps)?n(st.eps).toLocaleString('ko-KR'):'-'}/><Stat label="BPS" value={n(st.bps)?n(st.bps).toLocaleString('ko-KR'):'-'}/><Stat label="매출 성장" value={n(st.revenue_growth)?pct(st.revenue_growth):'-'}/><Stat label="영업이익률" value={n(st.operating_margin)?pct(st.operating_margin):'-'}/><Stat label="배당수익률" value={n(st.dividend_yield)?pct(st.dividend_yield):'-'}/><Stat label="20일 모멘텀" value={n(st.momentum_20d)?pct(st.momentum_20d):'-'}/><Stat label="변동성" value={n(st.volatility)?pct(st.volatility):'-'}/></View></Card>
   <Card><SectionTitle title="테마 / 사업 분류"/><View style={s.tags}>{themes.slice(0,20).map((x:any,i:number)=><Chip key={i} label={typeof x==='string'?x:(x.name||x.theme_name||String(x))}/>)}</View>{st.primary_business?<Text style={s.body}>{st.primary_business}</Text>:null}{st.classification_reason?<Text style={s.body}>분류 근거: {st.classification_reason}</Text>:null}</Card>
   <Card><SectionTitle title="최근 재무"/>{(data?.financials||[]).length?(data.financials||[]).slice(0,4).map((x:any,i:number)=><View key={i} style={s.finRow}><Text style={s.finPeriod}>{x.period_label||x.period||x.year||`기간 ${i+1}`}</Text><Text style={s.finVal}>매출 {compactWon(x.revenue||x.sales)}</Text><Text style={s.finVal}>영업익 {compactWon(x.operating_income)}</Text><Text style={s.finVal}>당기순익 {compactWon(x.net_income)}</Text></View>):detailLoading?<Loading label="재무 데이터를 확인하고 있습니다."/>:<Empty title="재무 데이터가 없습니다."/>}</Card>
  </>:null}

  {section==='flow'?<Card><SectionTitle title="투자자 수급" hint={investor.available?`최근 ${investor.days||flow.length}거래일`:'저장된 수급 데이터'}/>{investor.summary?<Text style={s.body}>{investor.summary}</Text>:null}{flow.length?flow.slice(-15).reverse().map((x:any,i:number)=><View key={i} style={s.flowRow}><Text style={s.flowDate}>{String(x.date||x.trade_date||'').slice(5,10)}</Text><Text style={[s.flowText,{color:n(x.foreign??x.foreign_net)>=0?colors.positive:colors.negative}]}>외 {qty(x.foreign??x.foreign_net)}</Text><Text style={[s.flowText,{color:n(x.institution??x.institution_net)>=0?colors.positive:colors.negative}]}>기 {qty(x.institution??x.institution_net)}</Text><Text style={[s.flowText,{color:n(x.individual??x.individual_net)>=0?colors.positive:colors.negative}]}>개 {qty(x.individual??x.individual_net)}</Text></View>):detailLoading?<Loading label="수급 데이터를 확인하고 있습니다."/>:<Empty title="수급 데이터가 없습니다."/>}</Card>:null}

  {section==='news'?<View style={{gap:12}}><View style={s.newsTools}><SectionTitle title="최신 공개정보" hint="뉴스·증권사 리포트·공시"/><Button compact tone="secondary" title={refreshingNews?'갱신 중':'최신 정보 갱신'} disabled={refreshingNews} onPress={()=>void refreshNews()}/></View>{detailLoading&&!data?<Loading label="뉴스와 리포트를 확인하고 있습니다."/>:<><FilteredBlock title="뉴스" items={news} filter={newsFilter} setFilter={setNewsFilter} page={newsPage} setPage={setNewsPage}/><FilteredBlock title="증권사 리포트" items={reports} filter={reportFilter} setFilter={setReportFilter} page={reportPage} setPage={setReportPage}/><View style={{gap:8}}><SectionTitle title="공시" hint={`${disclosures.length}건`}/><NewsList items={disclosures.slice((disclosurePage-1)*3,disclosurePage*3)}/><Pager page={disclosurePage} pages={Math.max(1,Math.ceil(disclosures.length/3))} setPage={setDisclosurePage}/></View></>}</View>:null}

  {section==='ai'?<Card><SectionTitle title="StockLog Gbot 분석" hint={aiStatus?.message||'분석 상태를 확인합니다.'}/><View style={s.aiUsage}><Stat label="현재 등급" value={user?.membership_label||user?.membership_tier||'회원'}/><Stat label="오늘 이용" value={aiUsage?.unlimited?`${n(aiUsage.used)}회 · 무제한`:aiUsage?`${n(aiUsage.used)} / ${n(aiUsage.daily_limit)}회`:'-'}/><Stat label="남은 횟수" value={aiUsage?.unlimited?'무제한':aiUsage?`${n(aiUsage.remaining)}회`:'-'}/></View>{['running','queued','context','obot_running','obot_completed','gbot_running','gbot_completed','verifying'].includes(String(aiStatus?.status||''))?<View style={{gap:8}}><Loading label={aiStatus?.progress?.message||aiStatus?.message||'Gbot이 투자 데이터를 분석하고 있습니다.'}/>{aiStatus?.progress?.elapsed_seconds!=null?<Text style={s.muted}>경과 {Math.round(n(aiStatus.progress.elapsed_seconds))}초 · 화면을 닫아도 분석은 계속됩니다.</Text>:null}</View>:aiStatus?.status==='failed'?<ErrorState message={aiStatus?.message||aiStatus?.error_message||'Gbot 분석을 완료하지 못했습니다.'}/>:aiStatus?.result?<View style={{gap:12}}><Text style={s.aiSignal}>{String(signal||'ANALYSIS')}</Text><Text style={s.body}>{aiResult?.summary||aiResult?.opinion||aiResult?.reason||'Gbot 분석 결과가 준비되었습니다.'}</Text>{Array.isArray(aiResult?.evidence)?aiResult.evidence.map((x:any,i:number)=><Text key={i} style={s.bullet}>• {typeof x==='string'?x:JSON.stringify(x)}</Text>):null}{Array.isArray(aiResult?.risks)?<><Text style={s.sectionMini}>위험 요인</Text>{aiResult.risks.map((x:any,i:number)=><Text key={i} style={s.bullet}>• {typeof x==='string'?x:JSON.stringify(x)}</Text>)}</>:null}<Button title="다시 분석" tone="secondary" disabled={busy} onPress={()=>void askAi(true)}/></View>:<><Text style={s.body}>Gbot이 재무·가격·수급·뉴스를 종합해 의견과 근거를 정리합니다.</Text><Button title="Gbot 분석 시작" disabled={busy||!aiAllowed} onPress={()=>void askAi(false)}/>{!aiAllowed?<Text style={s.muted}>현재 등급에서는 AI 분석 기능을 사용할 수 없습니다.</Text>:null}</>}</Card>:null}
 </Screen>;
}

const s=StyleSheet.create({progressCard:{shadowOpacity:0,backgroundColor:colors.surfaceMuted},progressTitle:{fontSize:12,fontWeight:'900',color:colors.text,marginBottom:4},priceRow:{flexDirection:'row',justifyContent:'space-between',alignItems:'flex-start'},price:{fontSize:28,fontWeight:'900',color:colors.text},change:{fontSize:14,fontWeight:'800',marginTop:5},spark:{height:110,flexDirection:'row',alignItems:'flex-end',gap:2,marginVertical:18,paddingHorizontal:2},bar:{flex:1,minWidth:2,borderRadius:2},chartEmpty:{height:100,alignItems:'center',justifyContent:'center'},muted:{fontSize:11,color:colors.text3,lineHeight:17},statWrap:{flexDirection:'row',flexWrap:'wrap',gap:14},quick:{flexDirection:'row',gap:8,flexWrap:'wrap',marginTop:15},tabs:{flexDirection:'row',gap:7,flexWrap:'wrap'},tags:{flexDirection:'row',gap:7,flexWrap:'wrap'},body:{fontSize:12,lineHeight:19,color:colors.text2,marginTop:10},finRow:{gap:4,paddingVertical:9,borderBottomWidth:1,borderBottomColor:colors.border},finPeriod:{fontSize:11,fontWeight:'800',color:colors.text},finVal:{fontSize:11,color:colors.text2},flowRow:{flexDirection:'row',gap:7,paddingVertical:9,borderBottomWidth:1,borderBottomColor:colors.border},flowDate:{width:44,fontSize:10,color:colors.text3},flowText:{flex:1,fontSize:10,fontWeight:'700'},newsTools:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:8},newsHead:{flexDirection:'row',alignItems:'flex-start',gap:6},newsTitle:{flex:1,fontSize:13,fontWeight:'800',color:colors.text,lineHeight:19},sentimentBadge:{minWidth:42,height:24,paddingHorizontal:8,borderRadius:999,borderWidth:1,alignItems:'center',justifyContent:'center'},sentimentBadgeText:{fontSize:10,fontWeight:'900'},newsSub:{fontSize:10,color:colors.text3,marginTop:5},newsBody:{fontSize:11,color:colors.text2,lineHeight:17,marginTop:6},aiSignal:{fontSize:26,fontWeight:'900',color:colors.primary},bullet:{fontSize:11,lineHeight:18,color:colors.text2},aiUsage:{flexDirection:'row',gap:10,flexWrap:'wrap'},sectionMini:{fontSize:11,fontWeight:'900',color:colors.text,marginTop:4},pager:{flexDirection:'row',alignItems:'center',justifyContent:'center',gap:10,marginVertical:5},pageText:{fontSize:10,fontWeight:'800',color:colors.text3},statusGrid:{gap:8},statusItem:{padding:9,borderRadius:10,backgroundColor:colors.surfaceMuted},statusTitle:{fontSize:10,fontWeight:'800',color:colors.text,marginTop:6,textTransform:'uppercase'},statusMessage:{fontSize:10,color:colors.text3,lineHeight:15,marginTop:3}});
