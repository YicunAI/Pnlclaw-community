import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  reactStrictMode: false,
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
