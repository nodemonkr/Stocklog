import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Button, Card, Chip, SectionTitle, Stat } from '@/components/ui';
import { colors } from '@/constants/theme';
import { dateTime, won } from '@/lib/format';

const statusLabel:Record<string,string>={filled:'체결 완료',partial:'부분 체결',accepted:'주문 접수',submitting:'주문 전송 중',blocked:'안전장치 차단',order_failed:'주문 실패',hold:'관망',decision:'판단'};

export function AutoAuditDetail({row,onClose}:{row:any|null;onClose:()=>void}){
 if(!row)return null;
 const attempted=Boolean(row.order_attempted);
 const action=row.action==='buy'?'매수':row.action==='sell'?'매도':'관망';
 const amount=Number(row.filled_amount||0)>0?Number(row.filled_amount):Number(row.requested_amount||0);
 const evidence=Array.isArray(row.evidence)?row.evidence:[];
 const risks=Array.isArray(row.risks)?row.risks:[];
 return <Modal visible transparent animationType="slide" onRequestClose={onClose}>
  <View style={s.backdrop}><Pressable style={StyleSheet.absoluteFill} onPress={onClose}/><View style={s.sheet}>
   <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
    <View style={s.head}><View style={{flex:1}}><Text style={s.eyebrow}>{attempted?'AI EXECUTION REASON':'AI DECISION REASON'} · #{row.id||'-'}</Text><Text style={s.title}>{row.name||row.code||'자동매매 상세'}</Text><Text style={s.sub}>{row.code||'-'} · {statusLabel[row.status]||row.status||'-'}</Text></View><Chip label={action} active={row.action==='buy'}/></View>
    <Card><View style={s.stats}><Stat label={row.filled_quantity?'체결금액':'주문금액'} value={amount>0?`${won(amount)}원`:'-'}/><Stat label="수량" value={`${won(row.filled_quantity||row.requested_quantity)}주`}/><Stat label={row.filled_quantity?'체결가격':'주문가격'} value={`${won(row.filled_price||row.requested_price)}원`}/><Stat label="Gbot 확신도" value={`${Number(row.confidence||0).toFixed(0)}점`}/></View></Card>
    <Card><SectionTitle title={attempted?'AI 체결사유':'AI 판단사유'}/><Text style={s.body}>{row.reason||'상세 판단 이유가 기록되지 않았습니다.'}</Text></Card>
    {evidence.length?<Card><SectionTitle title="핵심 근거"/>{evidence.map((x:any,i:number)=><Text key={i} style={s.bullet}>• {String(x)}</Text>)}</Card>:null}
    {risks.length?<Card><SectionTitle title="위험 요인"/>{risks.map((x:any,i:number)=><Text key={i} style={[s.bullet,{color:colors.danger}]}>• {String(x)}</Text>)}</Card>:null}
    {row.exit_plan?<Card><SectionTitle title="재평가 · 청산 기준"/><Text style={s.body}>{String(row.exit_plan)}</Text></Card>:null}
    <Card><SectionTitle title="주문 · 체결 정보"/><View style={s.kv}>{[
     ['주문수량',`${won(row.requested_quantity)}주`],['주문가격',`${won(row.requested_price)}원`],['주문금액',`${won(row.requested_amount)}원`],['체결수량',`${won(row.filled_quantity)}주`],['체결가격',`${won(row.filled_price)}원`],['체결금액',`${won(row.filled_amount)}원`],['주문번호',row.broker_order_no||'-']
    ].map(([k,v])=><View key={k} style={s.kvRow}><Text style={s.k}>{k}</Text><Text selectable style={s.v}>{v}</Text></View>)}</View></Card>
    <Card><SectionTitle title="시간 기록"/><Text style={s.body}>판단 {dateTime(row.decided_at)}\n주문 {dateTime(row.order_submitted_at)}\n체결 {dateTime(row.filled_at)}</Text></Card>
    {row.guard_message?<Card style={s.guard}><SectionTitle title="STOCKLOG GUARD"/><Text style={s.body}>{String(row.guard_message)}</Text></Card>:null}
    <Button title="닫기" tone="secondary" onPress={onClose}/>
   </ScrollView>
  </View></View>
 </Modal>;
}
const s=StyleSheet.create({backdrop:{flex:1,justifyContent:'flex-end',backgroundColor:'rgba(8,15,28,.44)'},sheet:{maxHeight:'92%',backgroundColor:colors.bg,borderTopLeftRadius:24,borderTopRightRadius:24,overflow:'hidden'},scroll:{padding:16,paddingBottom:32,gap:12},head:{flexDirection:'row',gap:10,alignItems:'flex-start'},eyebrow:{fontSize:9,fontWeight:'800',letterSpacing:1,color:colors.primary},title:{fontSize:24,fontWeight:'900',color:colors.text,marginTop:5},sub:{fontSize:11,color:colors.text3,marginTop:4},stats:{flexDirection:'row',flexWrap:'wrap',gap:14},body:{fontSize:12,lineHeight:19,color:colors.text2},bullet:{fontSize:12,lineHeight:19,color:colors.text2,marginBottom:3},kv:{gap:0},kvRow:{flexDirection:'row',justifyContent:'space-between',gap:12,paddingVertical:8,borderBottomWidth:1,borderBottomColor:colors.border},k:{fontSize:11,color:colors.text3},v:{flex:1,textAlign:'right',fontSize:11,fontWeight:'700',color:colors.text2},guard:{backgroundColor:colors.surfaceMuted}});
