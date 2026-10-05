import { useEffect, useRef } from "react";

import { createGlobeScene, type GlobeSceneHandle } from "../three/globeScene";
import type { PassEvent } from "../types/api";

interface Globe3DProps {
  observerLatDeg: number;
  observerLonDeg: number;
  pass: PassEvent;
}

function Globe3D({ observerLatDeg, observerLonDeg, pass }: Globe3DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<GlobeSceneHandle | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handle = createGlobeScene(container);
    handleRef.current = handle;

    const resizeObserver = new ResizeObserver(() => handle.resize());
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      handle.dispose();
      handleRef.current = null;
    };
  }, []);

  useEffect(() => {
    handleRef.current?.setPassData(observerLatDeg, observerLonDeg, pass);
  }, [observerLatDeg, observerLonDeg, pass]);

  return (
    <div className="globe-3d">
      <div ref={containerRef} className="globe-3d__canvas" />
      <p className="help-text">
        Drag to rotate, scroll to zoom. The satellite&apos;s path across the sky is approximated
        from the pass&apos;s rise/peak/set geometry, not a full continuous ephemeris.
      </p>
    </div>
  );
}

export default Globe3D;
