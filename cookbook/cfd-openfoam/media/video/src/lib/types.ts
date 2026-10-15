// Types shared by the Remotion components. Every string/number here is
// filled from data.json, which media/make_media.sh writes from this run's
// judge verdict JSONs and RECEIPT.md.
export interface DemoData {
  video: { durationInFrames: number; fps: number; width: number; height: number };
  clips: { hook: string; cavity: string; agent: string };
  hud: {
    residFinal: string;
    cellCount: string;
    l2: string;
    orders: string;
    ghiaU: string;
    ghiaV: string;
    kills: string;
  };
  agent: { seconds: number; speed: string };
  verdict: {
    pass: boolean;
    killPct: string;
    gates: { name: string; ok: boolean }[];
  };
}
