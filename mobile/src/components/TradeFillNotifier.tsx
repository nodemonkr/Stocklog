import { useEffect, useRef, useState } from 'react';
import { AppState, Pressable, StyleSheet, Text, View } from 'react-native';
import { get } from '@/lib/api';
import { colors } from '@/constants/theme';
import { useAuth } from '@/context/AuthContext';
import { dateTime, won } from '@/lib/format';

export function TradeFillNotifier(){
 const {user}=useAuth();
 const [toast,setToast]=useState<any>(null);
 const seen=useRef<Map<string,number>>(new Map());
 const initialized=useRef(false);
 const hide=useRef<ReturnType<typeof setTimeout>|null>(null);
 useEffect(()=>{
  if(!user||user?.features?.mock_trading?.enabled===false)return;
  let stopped=false;let running=false;
  const poll=async()=>{if(stopped||running||AppState.currentState!=='active')return;running=true;try{const r=await get<any>('/api/trading/fill-events');const rows=Array.isArray(r?.items)?r.items.slice().reverse():[];if(!initialized.current){rows.forEach((x:any)=>seen.current.set(String(x.id||`${x.order_no}:${x.code}:${x.time}`),Number(x.quantity||0)));initialized.current=true;return;}for(const x of rows){const key=String(x.id||`${x.order_no}:${x.code}:${x.time}`);const cur=Math.max(0,Number(x.quantity||0));const prev=seen.current.get(key);if(prev===undefined){seen.current.set(key,cur);if(cur>0){setToast({...x,quantity:cur});break}}else if(cur>prev){seen.current.set(key,cur);setToast({...x,quantity:cur-prev});break}}}catch{}finally{running=false}};
  void poll();const id=setInterval(()=>void poll(),4000);const sub=AppState.addEventListener('change',state=>{if(state==='active')void poll()});return()=>{stopped=true;clearInterval(id);sub.remove()};
 },[user]);
 useEffect(()=>{if(!toast)return;if(hide.current)clearTimeout(hide.current);hide.current=setTimeout(()=>setToast(null),5500);return()=>{if(hide.current)clearTimeout(hide.current)}},[toast]);
 if(!toast)return null;const sell=toast.side==='sell';return <Pressable onPress={()=>setToast(null)} style={[s.toast,{borderLeftColor:sell?colors.negative:colors.positive}]}><View style={{flex:1}}><Text style={s.title}>{toast.source==='auto'?'자동 ':toast.source==='manual'?'수동 ':''}{sell?'매도':'매수'} {toast.partial?'부분 체결':'체결 완료'}</Text><Text style={s.body}>{toast.name||toast.code} · {won(toast.quantity)}주 · {won(toast.price)}원</Text><Text style={s.time}>{dateTime(toast.time)}</Text></View><Text style={s.close}>×</Text></Pressable>;
}
const s=StyleSheet.create({toast:{position:'absolute',zIndex:9999,top:54,left:12,right:12,backgroundColor:'#FFFFFF',borderWidth:1,borderColor:colors.border,borderLeftWidth:5,borderRadius:16,padding:13,flexDirection:'row',gap:10,shadowColor:'#000',shadowOpacity:.12,shadowRadius:12,shadowOffset:{width:0,height:5},elevation:9},title:{fontSize:13,fontWeight:'900',color:colors.text},body:{fontSize:11,fontWeight:'700',color:colors.text2,marginTop:4},time:{fontSize:9,color:colors.text3,marginTop:4},close:{fontSize:20,color:colors.text3,lineHeight:22}});
