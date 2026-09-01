import { Tabs } from 'expo-router';
import { Text } from 'react-native';
import { colors } from '@/constants/theme';

const icons:Record<string,string>={index:'⌂',analysis:'⌕',portfolio:'₩',auto:'◎',more:'•••'};
export default function TabsLayout(){
 return <Tabs screenOptions={({route})=>({
   headerShown:false,
   tabBarActiveTintColor:colors.primary,
   tabBarInactiveTintColor:colors.text3,
   tabBarStyle:{height:66,paddingTop:7,paddingBottom:8,borderTopColor:colors.border,backgroundColor:'#FFFFFF'},
   tabBarLabelStyle:{fontSize:10,fontWeight:'800'},
   tabBarIcon:({color})=><Text style={{color,fontSize:20,fontWeight:'900'}}>{icons[route.name]||'•'}</Text>,
 })}>
  <Tabs.Screen name="index" options={{title:'홈'}}/>
  <Tabs.Screen name="analysis" options={{title:'분석'}}/>
  <Tabs.Screen name="portfolio" options={{title:'투자'}}/>
  <Tabs.Screen name="auto" options={{title:'자동매매'}}/>
  <Tabs.Screen name="more" options={{title:'더보기'}}/>
 </Tabs>
}
