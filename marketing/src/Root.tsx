import "./index.css";
import { Composition } from "remotion";
import { PillVideo } from "./PillVideo";
import { TourVideo } from "./TourVideo";
import { ReadmeDemo } from "./ReadmeDemo";

// 30 seconds @ 30fps, 1080p 16:9 — README-ready.
const FPS = 30;
const DURATION = 30 * FPS;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ReadmeDemo"
        component={ReadmeDemo}
        durationInFrames={570}
        fps={30}
        width={1600}
        height={900}
      />
      <Composition
        id="PillDemo"
        component={PillVideo}
        durationInFrames={DURATION}
        fps={FPS}
        width={1920}
        height={1080}
      />
      <Composition
        id="AppTour"
        component={TourVideo}
        durationInFrames={DURATION}
        fps={FPS}
        width={1920}
        height={1080}
      />
    </>
  );
};
