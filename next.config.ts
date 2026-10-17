import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  devIndicators: false,
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "api.indiankanoon.org",
        port: "",
        pathname: "/static/pics/ikanoon6_powered_transparent.png",
        search: "",
      },
    ],
  },
};

export default nextConfig;
