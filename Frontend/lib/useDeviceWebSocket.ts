'use client';

import { useEffect, useRef, useState } from 'react';

export interface LiveDevice {
  id: string;
  nombre: string;
  ip: string;
  estado: string;
  online: boolean;
  ultimo_heartbeat: string | null;
}

const SSE_URL = process.env.NEXT_PUBLIC_API_URL || `http://${typeof window !== 'undefined' ? window.location.hostname : 'localhost'}:5000`;

export function useDeviceWebSocket() {
  const [devices, setDevices] = useState<Map<string, LiveDevice>>(new Map());
  const esRef = useRef<EventSource | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    function connect() {
      const es = new EventSource(`${SSE_URL}/sse/devices`);
      esRef.current = es;

      es.onopen = () => {
        console.log('[SSE] Conectado a /sse/devices');
      };

      es.onmessage = (event) => {
        try {
          const data: LiveDevice = JSON.parse(event.data);
          setDevices((prev) => {
            const next = new Map(prev);
            next.set(data.id, data);
            return next;
          });
        } catch {
          // ignore
        }
      };

      es.onerror = () => {
        console.log('[SSE] Error/reconectando en 5s...');
        es.close();
        reconnectRef.current = setTimeout(connect, 5000);
      };
    }

    connect();

    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (esRef.current) esRef.current.close();
    };
  }, []);

  return Array.from(devices.values());
}
