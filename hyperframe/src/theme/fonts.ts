import { staticFile } from "remotion";

const fontUrl = (fileName: string) => staticFile(`fonts/${fileName}`);

export const fontFaces = `
@font-face {
  font-family: 'Paperlogy';
  src: url('${fontUrl("Paperlogy-4Regular.ttf")}') format('truetype');
  font-weight: 400;
  font-style: normal;
}
@font-face {
  font-family: 'Paperlogy';
  src: url('${fontUrl("Paperlogy-5Medium.ttf")}') format('truetype');
  font-weight: 500;
  font-style: normal;
}
@font-face {
  font-family: 'Paperlogy';
  src: url('${fontUrl("Paperlogy-6SemiBold.ttf")}') format('truetype');
  font-weight: 600;
  font-style: normal;
}
@font-face {
  font-family: 'Paperlogy';
  src: url('${fontUrl("Paperlogy-7Bold.ttf")}') format('truetype');
  font-weight: 700;
  font-style: normal;
}
@font-face {
  font-family: 'Paperlogy';
  src: url('${fontUrl("Paperlogy-8ExtraBold.ttf")}') format('truetype');
  font-weight: 800;
  font-style: normal;
}
@font-face {
  font-family: 'Pretendard';
  src: url('${fontUrl("PretendardVariable.ttf")}') format('truetype');
  font-weight: 100 900;
  font-style: normal;
  font-display: block;
}
@font-face {
  font-family: 'Noto Sans SC';
  src: url('${fontUrl("NotoSansSC-Regular.ttf")}') format('truetype');
  font-weight: 400;
  font-style: normal;
  font-display: block;
}
@font-face {
  font-family: 'Noto Sans SC';
  src: url('${fontUrl("NotoSansSC-Bold.ttf")}') format('truetype');
  font-weight: 700;
  font-style: normal;
  font-display: block;
}
@font-face {
  font-family: 'JetBrains Mono';
  src: url('${fontUrl("JetBrainsMono-Regular.woff2")}') format('woff2');
  font-weight: 400;
  font-style: normal;
}
`;
