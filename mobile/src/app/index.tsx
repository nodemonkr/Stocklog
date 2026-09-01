import { Redirect } from 'expo-router';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { useAuth } from '@/context/AuthContext';
import { colors } from '@/constants/theme';

export default function Index() {
  const { ready, user } = useAuth();
  if (!ready) return <View style={styles.root}><ActivityIndicator size="large" color={colors.primary}/><Text style={styles.text}>StockLog 시작 중...</Text></View>;
  return <Redirect href={user ? '/(tabs)' : '/login'} />;
}
const styles=StyleSheet.create({root:{flex:1,alignItems:'center',justifyContent:'center',gap:12,backgroundColor:colors.bg},text:{color:colors.text2,fontWeight:'700'}});
