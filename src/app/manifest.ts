import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Blood Request PWA",
    short_name: "BloodRequest",
    description: "Clinical blood request workflow application for hospital use trials.",
    start_url: "/sign-in",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#FAFBFC",
    theme_color: "#FAFBFC",
    icons: [
      {
        src: "/icons/icon-192",
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: "/icons/icon-512",
        sizes: "512x512",
        type: "image/png",
      },
      {
        src: "/icons/icon-512-maskable",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
