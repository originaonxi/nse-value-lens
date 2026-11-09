import { useEffect, useState } from 'react';
import { MarketFlowPage } from '@/features/market-flow/MarketFlowPage';
import { loadUnderlyings, type Underlying } from '@/lib/underlyings';

export default function App() {
  const [universe, setUniverse] = useState<Underlying[]>([]);
  useEffect(() => { loadUnderlyings().then(setUniverse); }, []);
  return <MarketFlowPage universe={universe} />;
}
