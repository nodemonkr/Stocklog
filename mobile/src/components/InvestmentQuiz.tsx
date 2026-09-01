import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Card, Button } from '@/components/ui';
import { colors } from '@/constants/theme';
import { calculateInvestmentProfile, investmentQuestions, investmentTraits } from '@/data/investment';

export type InvestmentResult = ReturnType<typeof calculateInvestmentProfile>;
type QuizProgress={answers:Record<number,string>;index:number};

export function InvestmentQuiz({ initialAnswers, initialIndex=0, onProgress, onReset, onComplete, submitting = false }: { initialAnswers?: Record<number,string>; initialIndex?:number; onProgress?:(progress:QuizProgress)=>void|Promise<void>; onReset?:()=>void|Promise<void>; onComplete: (result: InvestmentResult) => void | Promise<void>; submitting?: boolean }) {
  const safeIndex=Math.max(0,Math.min(investmentQuestions.length-1,Number(initialIndex)||0));
  const [index, setIndex] = useState(safeIndex);
  const [answers, setAnswers] = useState<Record<number,string>>(initialAnswers || {});
  const [showResult,setShowResult]=useState(false);
  const q = investmentQuestions[index];
  const selected = answers[q.id];
  const progress = Math.round(((index + 1) / investmentQuestions.length) * 100);
  const complete=Object.keys(answers).length===investmentQuestions.length;
  const preview = useMemo(() => complete ? calculateInvestmentProfile(answers) : null, [answers,complete]);

  const persist=(next:Record<number,string>,nextIndex:number)=>{void onProgress?.({answers:next,index:nextIndex})};
  const go=(nextIndex:number)=>{const v=Math.max(0,Math.min(investmentQuestions.length-1,nextIndex));setIndex(v);persist(answers,v)};
  const choose = (id: string) => {
    const next = { ...answers, [q.id]: id };
    setAnswers(next);
    if (index < investmentQuestions.length - 1) {
      const nextIndex=index+1;persist(next,nextIndex);setTimeout(() => setIndex(i => i===index?nextIndex:i), 120);
    } else {
      persist(next,index);setShowResult(true);
    }
  };
  const reset=()=>{setAnswers({});setIndex(0);setShowResult(false);void onReset?.();void onProgress?.({answers:{},index:0})};

  if (showResult&&preview) {
    return <View style={{ gap: 14 }}>
      <Card>
        <Text style={styles.resultLabel}>MY INVESTOR DNA</Text>
        <View style={styles.codeRow}>{preview.code.split('').map((c, i) => <View key={`${c}-${i}`} style={styles.codeBox}><Text style={styles.code}>{c}</Text><Text style={styles.codeSub}>{investmentTraits[c]?.short}</Text></View>)}</View>
        <Text style={styles.resultText}>{preview.code.split('').map(c => investmentTraits[c]?.name).join(' · ')}</Text>
      </Card>
      <View style={styles.actions}><Button title="답변 다시 보기" tone="secondary" onPress={() => {setShowResult(false);setIndex(0)}} /><Button title={submitting ? '저장 중...' : '이 결과 사용하기'} disabled={submitting} onPress={() => onComplete(preview)} /></View>
    </View>;
  }

  return <View style={{ gap: 14 }}>
    <View style={styles.progressHead}><Text style={styles.progressText}>{index + 1} / {investmentQuestions.length}</Text><Text style={styles.progressText}>{progress}%</Text></View>
    <View style={styles.progressTrack}><View style={[styles.progressFill, { width: `${progress}%` }]} /></View>
    <Card>
      <View style={styles.questionTop}><Text style={styles.questionNo}>QUESTION {String(q.id).padStart(2, '0')}</Text><Pressable onPress={reset}><Text style={styles.reset}>처음부터</Text></Pressable></View>
      <Text style={styles.question}>{q.title}</Text>
      <View style={{ gap: 9, marginTop: 16 }}>
        {q.options.map((option, optionIndex) => {
          const active = selected === option.id;
          return <Pressable key={option.id} onPress={() => choose(option.id)} style={({pressed}) => [styles.option, active && styles.optionActive, pressed && { opacity: .7 }]}>
            <View style={[styles.optionKey, active && styles.optionKeyActive]}><Text style={[styles.optionKeyText, active && { color: '#fff' }]}>{['A','B','C','D'][optionIndex]}</Text></View>
            <Text style={[styles.optionText, active && { color: colors.primary }]}>{option.label}</Text>
          </Pressable>;
        })}
      </View>
    </Card>
    <View style={styles.navRow}>
      <Button title="이전" tone="secondary" disabled={index === 0} onPress={() => go(index-1)} />
      {index === investmentQuestions.length - 1 && selected && complete ? <Button title="결과 보기" onPress={() => setShowResult(true)} /> : <Text style={styles.autoText}>선택하면 다음 문항으로 이동합니다.</Text>}
    </View>
  </View>;
}

const styles = StyleSheet.create({
  progressHead:{flexDirection:'row',justifyContent:'space-between'}, progressText:{fontSize:11,fontWeight:'800',color:colors.text2},
  progressTrack:{height:6,borderRadius:6,backgroundColor:'#E7EAF0',overflow:'hidden'}, progressFill:{height:6,backgroundColor:colors.primary,borderRadius:6},
  questionTop:{flexDirection:'row',alignItems:'center',justifyContent:'space-between'},questionNo:{fontSize:10,fontWeight:'900',letterSpacing:1,color:colors.primary},reset:{fontSize:10,fontWeight:'800',color:colors.text3}, question:{fontSize:20,fontWeight:'800',lineHeight:29,color:colors.text,marginTop:8},
  option:{minHeight:64,flexDirection:'row',alignItems:'center',gap:11,padding:12,borderWidth:1,borderColor:colors.border,borderRadius:14,backgroundColor:colors.surfaceMuted}, optionActive:{borderColor:colors.primary,backgroundColor:colors.primarySoft},
  optionKey:{width:30,height:30,borderRadius:10,alignItems:'center',justifyContent:'center',backgroundColor:'#E8ECF2'}, optionKeyActive:{backgroundColor:colors.primary}, optionKeyText:{fontWeight:'900',color:colors.text2}, optionText:{flex:1,fontSize:13,lineHeight:19,color:colors.text2,fontWeight:'600'},
  navRow:{minHeight:48,flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:10}, autoText:{flex:1,textAlign:'right',fontSize:11,color:colors.text3},
  resultLabel:{fontSize:10,fontWeight:'900',letterSpacing:1,color:colors.primary}, codeRow:{flexDirection:'row',gap:8,marginTop:16}, codeBox:{flex:1,alignItems:'center',paddingVertical:13,borderRadius:13,backgroundColor:colors.primarySoft}, code:{fontSize:24,fontWeight:'900',color:colors.primary}, codeSub:{fontSize:9,fontWeight:'700',color:colors.text2,marginTop:3}, resultText:{marginTop:14,fontSize:13,lineHeight:20,color:colors.text2}, actions:{gap:9}
});
