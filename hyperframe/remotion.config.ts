import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setCodec("h264-mkv");
Config.setScale(1);
Config.overrideWebpackConfig((currentConfiguration) => {
  return currentConfiguration;
});
