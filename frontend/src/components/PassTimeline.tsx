import type { PassEvent } from "../types/api";
import { formatTime } from "../utils/format";

interface PassTimelineProps {
  pass: PassEvent;
}

function PassTimeline({ pass }: PassTimelineProps) {
  const riseMs = new Date(pass.rise_time).getTime();
  const setMs = new Date(pass.set_time).getTime();
  const peakMs = new Date(pass.peak_time).getTime();
  const peakFraction = setMs > riseMs ? (peakMs - riseMs) / (setMs - riseMs) : 0.5;

  return (
    <div className="pass-timeline">
      <div className="pass-timeline__track">
        <div className="pass-timeline__fill" />
        <div
          className="pass-timeline__marker pass-timeline__marker--peak"
          style={{ left: `${peakFraction * 100}%` }}
        />
      </div>
      <div className="pass-timeline__labels">
        <span>Rise · {formatTime(pass.rise_time)}</span>
        <span className="pass-timeline__labels-peak">
          Peak · {formatTime(pass.peak_time)} ({Math.round(pass.max_elevation_deg)}°)
        </span>
        <span>Set · {formatTime(pass.set_time)}</span>
      </div>
    </div>
  );
}

export default PassTimeline;
