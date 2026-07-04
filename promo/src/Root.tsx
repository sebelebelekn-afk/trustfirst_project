import React from "react";
import { Composition } from "remotion";
import { Promo } from "./Promo";
import { VIDEO } from "./theme";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="TrustFirstPromo"
      component={Promo}
      durationInFrames={VIDEO.durationInFrames}
      fps={VIDEO.fps}
      width={VIDEO.width}
      height={VIDEO.height}
    />
  );
};
