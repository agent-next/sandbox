import { registerRoot, Composition } from "remotion";
import { Kestrel } from "./Kestrel";

registerRoot(() => (
  <Composition
    id="Kestrel"
    component={Kestrel}
    durationInFrames={1320}
    fps={30}
    width={1920}
    height={1080}
    defaultProps={{}}
  />
));
