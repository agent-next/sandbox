import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
// "angle" renders on the GPU path of headless Chrome; "swangle" (the previous
// setting) forces the CPU SwiftShader rasteriser and measured ~5x slower per
// frame on this sandbox's 2-core runner.
Config.setChromiumOpenGlRenderer("angle");
