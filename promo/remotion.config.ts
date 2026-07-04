import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setCodec("h264");
// High visual quality (lower CRF = higher quality / bigger file). 18 is visually lossless-ish.
Config.setCrf(18);
