import { useCallback, useEffect, useState } from 'react';
import { router, useFocusEffect } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Button, Card, Empty, ErrorState, Loading, PageHeader, Screen, SectionTitle, Stat } from '@/components/ui';
import { colors } from '@/constants/theme';
import { get } from '@/lib/api';
import { compactWon, pct, won } from '@/lib/format';
import { useAuth } from '@/context/AuthContext';

export default function Home(){
 const {user,refreshUser}=useAuth(); const [market,setMarket]=useState<any[]>([]); const [portfolio,setPortfolio]=useState<any>(null); const [loading,setLoading]=useState(true); const [error,setError]=useState('');
 const load=useCallback(async()=>{setLoading(true);setError('');try{const [m,p]=await Promise.allSettled([get<any>('/api/market-overview'),get<any>('/api/trading/portfolio')]);if(m.status==='fulfilled')setMarket(m.value?.items||[]);if(p.status==='fulfilled')setPortfolio(p.value);await refreshUser().catch(()=>{})}catch(e:any){setError(e.message||'홈 데이터를 불러오지 못했습니다.')}finally{setLoading(false)}},[refreshUser]);
 useFocusEffect(useCallback(()=>{load()},[load]));
 const s=portfolio?.summary||{}; const holdings=portfolio?.holdings||[];
 return <Screen>
  <PageHeader eyebrow="STOCKLOG MOBILE" title={`${user?.display_name||user?.username||'회원'}님`} subtitle="오늘 시장과 내 모의투자 현황을 한눈에 확인하세요." right={<View style={styles.tier}><Text style={styles.tierText}>{user?.membership_label||user?.membership_tier||'MEMBER'}</Text></View>}/>
  {loading?<Loading label="시장과 포트폴리오를 확인하고 있습니다."/>:null}{error?<ErrorState message={error} retry={load}/>:null}
  <Card style={styles.assetCard}>
   <Text style={styles.assetLabel}>모의투자 총 자산</Text><Text style={styles.assetValue}>{portfolio?won(s.total_asset):'연결 전'}</Text>
   {portfolio?<View style={styles.assetStats}><Stat label="구매 가능 자산" value={compactWon(s.buying_power_available?s.buying_power:(s.buying_power||s.cash))}/><Stat label="금일 순익" value={won(s.day_profit)} tone={Number(s.day_profit)>=0?'up':'down'}/><Stat label="금일 순익률" value={pct(s.day_return_rate)} tone={Number(s.day_return_rate)>=0?'up':'down'}/><Stat label="총 순익" value={won(s.profit_loss)} tone={Number(s.profit_loss)>=0?'up':'down'}/><Stat label="총 순익률" value={pct(s.return_rate)} tone={Number(s.return_rate)>=0?'up':'down'}/><Stat label="보유 종목 수" value={`${holdings.length}종목`}/></View>:<Text style={styles.assetHint}>키움 모의투자를 연결하면 자산 현황이 표시됩니다.</Text>}
   <Button title={portfolio?'포트폴리오 열기':'모의투자 연결하기'} tone="secondary" onPress={()=>router.push(portfolio?'/(tabs)/portfolio':'/trading/connection')}/>
  </Card>

  <View><SectionTitle title="주요 시장지표" hint="백엔드가 수집한 최신 시장 데이터"/><View style={styles.marketGrid}>{market.slice(0,6).map(item=>{const rate=Number(item.change_rate||0);return <Card key={item.key||item.label} style={styles.marketCard}><Text style={styles.marketLabel}>{item.label}</Text><Text style={styles.marketValue}>{item.available===false?'--':Number(item.value||0).toLocaleString('ko-KR',{maximumFractionDigits:2})}</Text><Text style={[styles.marketRate,{color:rate>0?colors.positive:rate<0?colors.negative:colors.text3}]}>{Number.isFinite(rate)?pct(rate):''}</Text></Card>})}</View>{!market.length&&!loading?<Empty title="시장 데이터가 아직 없습니다."/>:null}</View>

  <View><SectionTitle title="빠른 실행"/><View style={styles.quickGrid}>{[
   ['스마트 분석','종목 추천과 점수','/(tabs)/analysis'],['종목 검색','종목 상세 바로 찾기','/search'],['자동매매','Gbot 상태와 설정','/(tabs)/auto'],['투자성향','내 Investor DNA','/profile/investment'],
  ].map(([title,sub,href])=><Pressable key={title} onPress={()=>router.push(href as any)} style={({pressed})=>[styles.quick,pressed&&{opacity:.65}]}><Text style={styles.quickTitle}>{title}</Text><Text style={styles.quickSub}>{sub}</Text><Text style={styles.quickArrow}>›</Text></Pressable>)}</View></View>

  {holdings.length?<View><SectionTitle title="보유종목" hint={`현재 ${holdings.length}종목`}/>{holdings.slice(0,4).map((h:any)=><Pressable key={h.code||h.stock_code} onPress={()=>router.push(`/stock/${h.code||h.stock_code}` as any)}><Card style={styles.holding}><View style={{flex:1}}><Text style={styles.holdingName}>{h.name||h.stock_name||h.code}</Text><Text style={styles.holdingSub}>{h.code||h.stock_code} · {Number(h.quantity||0).toLocaleString()}주 · {h.acquisition_source_label||''}</Text></View><View style={{alignItems:'flex-end'}}><Text style={styles.holdingPrice}>{won(h.evaluation_amount||h.market_value)}</Text><Text style={{fontWeight:'800',fontSize:12,color:Number(h.return_rate||0)>=0?colors.positive:colors.negative}}>{pct(h.return_rate)}</Text></View></Card></Pressable>)}</View>:null}
 </Screen>
}
const styles=StyleSheet.create({tier:{backgroundColor:colors.navy,borderRadius:999,paddingHorizontal:10,paddingVertical:6},tierText:{color:'#fff',fontSize:9,fontWeight:'900'},assetCard:{backgroundColor:colors.navy,borderColor:colors.navy},assetLabel:{fontSize:11,color:'#9CA8BA',fontWeight:'700'},assetValue:{fontSize:29,color:'#fff',fontWeight:'900',marginTop:5},assetStats:{flexDirection:'row',flexWrap:'wrap',gap:12,marginVertical:18},assetHint:{color:'#B7C1D0',fontSize:12,lineHeight:18,marginVertical:14},marketGrid:{flexDirection:'row',flexWrap:'wrap',gap:8},marketCard:{width:'48.7%',padding:13,shadowOpacity:0},marketLabel:{fontSize:10,color:colors.text3,fontWeight:'800'},marketValue:{fontSize:18,fontWeight:'800',color:colors.text,marginTop:5},marketRate:{fontSize:11,fontWeight:'800',marginTop:3},quickGrid:{flexDirection:'row',flexWrap:'wrap',gap:8},quick:{width:'48.7%',minHeight:88,padding:14,borderRadius:16,backgroundColor:colors.surface,borderWidth:1,borderColor:colors.border},quickTitle:{fontSize:14,fontWeight:'800',color:colors.text},quickSub:{fontSize:10,color:colors.text3,marginTop:5},quickArrow:{position:'absolute',right:13,bottom:8,fontSize:22,color:colors.text3},holding:{flexDirection:'row',alignItems:'center',gap:10,padding:13,marginBottom:7,shadowOpacity:0},holdingName:{fontSize:14,fontWeight:'800',color:colors.text},holdingSub:{fontSize:10,color:colors.text3,marginTop:4},holdingPrice:{fontSize:13,fontWeight:'800',color:colors.text,marginBottom:3}});
