import { ImageResponse } from "next/og";
import { createElement } from "react";

export const runtime = "nodejs";
export const contentType = "image/png";

export async function GET() {
  return new ImageResponse(
    createElement(
      "div",
      {
        style: {
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#FAFBFC",
          color: "#B2273C",
          fontSize: 184,
          fontWeight: 700,
          borderRadius: 0,
        },
      },
      "BR"
    ),
    {
      width: 512,
      height: 512,
    }
  );
}
