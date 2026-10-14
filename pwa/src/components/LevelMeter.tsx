// Pegelanzeige: zeigt, dass das Mikrofon etwas hört. Die Balken werden mit
// requestAnimationFrame ~60-mal pro Sekunde aktualisiert – direkt am DOM statt über
// React-State, damit nicht 60-mal pro Sekunde die ganze Seite neu gezeichnet wird.

import { useEffect, useRef } from "react";

const BARS = 24;

export function LevelMeter({ source }: { source: () => number }) {
  const ref = useRef<HTMLDivElement>(null);
  // Die Quelle in einer Ref merken: Sie ist bei jedem Neuzeichnen eine neue Funktion,
  // die Animation soll deshalb aber nicht jedes Mal neu starten
  const sourceRef = useRef(source);
  sourceRef.current = source;

  useEffect(() => {
    const history = new Array(BARS).fill(0);
    let frame = 0;
    const tick = () => {
      history.push(sourceRef.current());
      history.shift();
      ref.current?.querySelectorAll("span").forEach((bar, i) => {
        (bar as HTMLElement).style.height = `${4 + history[i] * 36}px`;
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <div className="meter" ref={ref} aria-hidden="true">
      {Array.from({ length: BARS }, (_, i) => <span key={i} style={{ height: 4 }} />)}
    </div>
  );
}
