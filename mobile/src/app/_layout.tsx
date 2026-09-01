import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider } from '@/context/AuthContext';
import { colors } from '@/constants/theme';
import { TradeFillNotifier } from '@/components/TradeFillNotifier';

export default function RootLayout() {
  return <AuthProvider>
    <StatusBar style="dark" />
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg }, animation: 'slide_from_right' }} />
    <TradeFillNotifier />
  </AuthProvider>;
}
