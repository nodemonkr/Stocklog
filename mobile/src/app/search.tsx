import { useEffect, useState } from 'react';
import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Card, Empty, ErrorState, Field, Loading, PageHeader, Screen } from '@/components/ui';
import { colors } from '@/constants/theme';
import { get } from '@/lib/api';
import { pct, won } from '@/lib/format';

export default function Search(){
 const [q,setQ]=useState('');const [rows,setRows]=useState<any[]>([]);const [loading,setLoading]=useState(false);const [error,setError]=useState('');
 useEffect(()=>{const term=q.trim();if(!term){setRows([]);return}const t=setTimeout(async()=>{setLoading(true);setError('');try{const r=await get<any>('/api/stocks/search',{q:term,limit:20});setRows(Array.isArray(r)?r:(r?.items||[]))}catch(e:any){setError(e.message)}finally{setLoading(false)}},250);return()=>clearTimeout(t)},[q]);
 return <Screen><PageHeader eyebrow="STOCK SEARCH" title="종목 검색" subtitle="종목명 또는 6자리 코드를 입력하세요."/><Field label="검색어" value={q} onChangeText={setQ} placeholder="예: 삼성전자 / 005930" autoFocus/>{loading?<Loading/>:null}{error?<ErrorState message={error}/>:null}{!loading&&q.trim()&&!rows.length&&!error?<Empty title="검색 결과가 없습니다."/>:null}<View style={{gap:7}}>{rows.map(row=><Pressable key={row.code} onPress={()=>router.push(`/stock/${row.code}` as any)}><Card style={styles.row}><View style={{flex:1}}><Text style={styles.name}>{row.name}</Text><Text style={styles.sub}>{row.code} · {row.market||''} · {row.display_category||row.category||''}</Text></View><View style={{alignItems:'flex-end'}}>{row.price?<Text style={styles.price}>{won(row.price)}</Text>:null}{row.change_rate!==undefined?<Text style={{fontSize:11,fontWeight:'800',color:Number(row.change_rate)>=0?colors.positive:colors.negative}}>{pct(row.change_rate)}</Text>:null}</View></Card></Pressable>)}</View></Screen>
}
const styles=StyleSheet.create({row:{flexDirection:'row',alignItems:'center',padding:13,shadowOpacity:0},name:{fontSize:14,fontWeight:'800',color:colors.text},sub:{fontSize:10,color:colors.text3,marginTop:4},price:{fontSize:13,fontWeight:'800',color:colors.text,marginBottom:3}});
