import { PropsWithChildren, ReactNode } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleProp, StyleSheet, Text, TextInput, TextInputProps, View, ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors, radius, shadow } from '@/constants/theme';

export function Screen({ children, scroll = true, contentStyle }: PropsWithChildren<{ scroll?: boolean; contentStyle?: StyleProp<ViewStyle> }>) {
  const body = <View style={[styles.content, contentStyle]}>{children}</View>;
  return <SafeAreaView style={styles.safe} edges={['top']}>{scroll ? <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scroll}>{body}</ScrollView> : body}</SafeAreaView>;
}

export function PageHeader({ eyebrow, title, subtitle, right }: { eyebrow?: string; title: string; subtitle?: string; right?: ReactNode }) {
  return <View style={styles.pageHeader}><View style={{ flex: 1 }}>{eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}<Text style={styles.pageTitle}>{title}</Text>{subtitle ? <Text style={styles.pageSubtitle}>{subtitle}</Text> : null}</View>{right}</View>;
}

export function Card({ children, style }: PropsWithChildren<{ style?: StyleProp<ViewStyle> }>) { return <View style={[styles.card, style]}>{children}</View>; }
export function SectionTitle({ title, hint, right }: { title: string; hint?: string; right?: ReactNode }) { return <View style={styles.sectionHead}><View style={{ flex: 1 }}><Text style={styles.sectionTitle}>{title}</Text>{hint ? <Text style={styles.sectionHint}>{hint}</Text> : null}</View>{right}</View>; }

export function Button({ title, onPress, disabled, tone = 'primary', compact = false }: { title: string; onPress?: () => void; disabled?: boolean; tone?: 'primary'|'secondary'|'danger'|'ghost'; compact?: boolean }) {
  return <Pressable onPress={onPress} disabled={disabled} style={({ pressed }) => [styles.button, styles[`button_${tone}`], compact && styles.buttonCompact, (pressed || disabled) && { opacity: disabled ? .45 : .72 }]}><Text style={[styles.buttonText, tone !== 'primary' && styles[`buttonText_${tone}`]]}>{title}</Text></Pressable>;
}

export function Chip({ label, active, onPress, disabled }: { label: string; active?: boolean; onPress?: () => void; disabled?: boolean }) {
  return <Pressable disabled={disabled} onPress={onPress} style={({ pressed }) => [styles.chip, active && styles.chipActive, (pressed || disabled) && { opacity: disabled ? .4 : .7 }]}><Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text></Pressable>;
}

export function Field({ label, hint, ...props }: TextInputProps & { label: string; hint?: string }) {
  return <View style={styles.field}><Text style={styles.fieldLabel}>{label}</Text><TextInput placeholderTextColor={colors.text3} {...props} style={[styles.input, props.multiline && styles.inputMulti, props.style]} />{hint ? <Text style={styles.fieldHint}>{hint}</Text> : null}</View>;
}

export function Stat({ label, value, detail, tone }: { label: string; value: string; detail?: string; tone?: 'up'|'down'|'normal' }) {
  const c = tone === 'up' ? colors.positive : tone === 'down' ? colors.negative : colors.text;
  return <View style={styles.stat}><Text style={styles.statLabel}>{label}</Text><Text style={[styles.statValue, { color: c }]} numberOfLines={1}>{value}</Text>{detail ? <Text style={styles.statDetail}>{detail}</Text> : null}</View>;
}

export function Loading({ label = '불러오는 중...' }: { label?: string }) { return <View style={styles.state}><ActivityIndicator/><Text style={styles.stateText}>{label}</Text></View>; }
export function ErrorState({ message, retry }: { message: string; retry?: () => void }) { return <Card style={styles.errorCard}><Text style={styles.errorTitle}>불러오지 못했습니다</Text><Text style={styles.errorText}>{message}</Text>{retry ? <Button title="다시 시도" tone="secondary" compact onPress={retry}/> : null}</Card>; }
export function Empty({ title, detail }: { title: string; detail?: string }) { return <Card style={styles.empty}><Text style={styles.emptyTitle}>{title}</Text>{detail ? <Text style={styles.emptyText}>{detail}</Text> : null}</Card>; }
export function FeatureLocked({ title='현재 등급에서 사용할 수 없습니다.', detail='회원 등급별 기능 권한 정책에 따라 이 기능이 제한되어 있습니다.' }: { title?:string; detail?:string }) { return <Card style={styles.locked}><Text style={styles.lockedBadge}>MEMBERSHIP</Text><Text style={styles.lockedTitle}>{title}</Text><Text style={styles.lockedText}>{detail}</Text></Card>; }

export function RowLink({ title, subtitle, value, onPress, danger = false, disabled = false }: { title: string; subtitle?: string; value?: string; onPress?: () => void; danger?: boolean; disabled?:boolean }) {
 return <Pressable disabled={disabled} onPress={onPress} style={({pressed})=>[styles.rowLink, (pressed||disabled)&&{ opacity: disabled ? .45 : .65 }]}><View style={{flex:1}}><Text style={[styles.rowTitle,danger&&{color:colors.danger}]}>{title}</Text>{subtitle?<Text style={styles.rowSub}>{subtitle}</Text>:null}</View>{value?<Text style={styles.rowValue}>{value}</Text>:null}<Text style={styles.chevron}>{disabled?'🔒':'›'}</Text></Pressable>;
}

export function Divider() { return <View style={styles.divider}/>; }

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { flexGrow: 1 },
  content: { paddingHorizontal: 16, paddingTop: 10, paddingBottom: 38, gap: 14 },
  pageHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingVertical: 4 },
  eyebrow: { fontSize: 10, fontWeight: '800', letterSpacing: 1.2, color: colors.primary, marginBottom: 5 },
  pageTitle: { fontSize: 27, fontWeight: '800', color: colors.text, letterSpacing: -.5 },
  pageSubtitle: { fontSize: 13, color: colors.text2, lineHeight: 19, marginTop: 5 },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 16, ...shadow },
  sectionHead: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
  sectionTitle: { color: colors.text, fontWeight: '800', fontSize: 16 },
  sectionHint: { color: colors.text3, fontSize: 11, marginTop: 3, lineHeight: 16 },
  button: { minHeight: 46, borderRadius: 13, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  buttonCompact: { minHeight: 36, borderRadius: 10, paddingHorizontal: 12 },
  button_primary: { backgroundColor: colors.primary },
  button_secondary: { backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: '#D9DDFB' },
  button_danger: { backgroundColor: colors.dangerSoft, borderWidth: 1, borderColor: '#F2CDD3' },
  button_ghost: { backgroundColor: colors.surfaceMuted, borderWidth: 1, borderColor: colors.border },
  buttonText: { color: '#fff', fontWeight: '800', fontSize: 14 },
  buttonText_secondary: { color: colors.primary }, buttonText_danger: { color: colors.danger }, buttonText_ghost: { color: colors.text2 },
  chip: { minHeight: 34, paddingHorizontal: 12, borderRadius: radius.pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  chipActive: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  chipText: { color: colors.text2, fontSize: 12, fontWeight: '700' }, chipTextActive: { color: colors.primary },
  field: { gap: 6 }, fieldLabel: { fontSize: 12, fontWeight: '700', color: colors.text2 }, fieldHint: { fontSize: 10, color: colors.text3 },
  input: { minHeight: 47, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 13, backgroundColor: colors.surface, color: colors.text, fontSize: 15 },
  inputMulti: { minHeight: 100, textAlignVertical: 'top', paddingVertical: 12 },
  stat: { flex: 1, minWidth: 100, gap: 4 }, statLabel: { fontSize: 10, fontWeight: '700', color: colors.text3 }, statValue: { fontSize: 18, fontWeight: '800' }, statDetail: { fontSize: 10, color: colors.text3 },
  state: { paddingVertical: 30, alignItems: 'center', gap: 9 }, stateText: { color: colors.text3, fontSize: 12 },
  errorCard: { backgroundColor: '#FFF8F8', borderColor: '#F2D7D7', gap: 8 }, errorTitle: { color: colors.danger, fontWeight: '800', fontSize: 14 }, errorText: { color: colors.text2, fontSize: 12, lineHeight: 18 },
  empty: { alignItems: 'center', paddingVertical: 26, shadowOpacity: 0 }, emptyTitle: { fontWeight: '800', color: colors.text2 }, emptyText: { marginTop: 5, fontSize: 12, color: colors.text3, textAlign: 'center', lineHeight: 18 }, locked:{backgroundColor:colors.surfaceMuted,shadowOpacity:0},lockedBadge:{fontSize:9,fontWeight:'900',letterSpacing:1,color:colors.primary},lockedTitle:{fontSize:15,fontWeight:'900',color:colors.text,marginTop:7},lockedText:{fontSize:11,lineHeight:17,color:colors.text3,marginTop:6},
  rowLink: { minHeight: 60, flexDirection: 'row', alignItems: 'center', gap: 9, paddingVertical: 10 }, rowTitle: { fontSize: 14, fontWeight: '700', color: colors.text }, rowSub: { marginTop: 3, fontSize: 11, color: colors.text3, lineHeight: 16 }, rowValue: { color: colors.text2, fontSize: 12, maxWidth: 100 }, chevron: { fontSize: 25, color: colors.text3, lineHeight: 28 }, divider: { height: 1, backgroundColor: colors.border },
});
