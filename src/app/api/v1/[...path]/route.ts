import { NextRequest, NextResponse } from "next/server";

type RouteContext = {
  params: Promise<{
    path: string[];
  }>;
};

function getApiOrigin(): string {
  return (process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

async function forwardRequest(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  try {
    const { path } = await context.params;
    const subpath = path.join("/");
    const url = new URL(request.url);
    const targetUrl = `${getApiOrigin()}/api/v1/${subpath}${url.search}`;

    const forwardHeaders = new Headers();
    const cookie = request.headers.get("cookie");
    if (cookie) forwardHeaders.set("cookie", cookie);

    const origin = request.headers.get("origin") ?? "http://localhost:3000";
    forwardHeaders.set("origin", origin);

    const contentType = request.headers.get("content-type");
    if (contentType) forwardHeaders.set("content-type", contentType);

    const referer = request.headers.get("referer");
    if (referer) forwardHeaders.set("referer", referer);

    let body: ArrayBuffer | undefined = undefined;
    if (request.method !== "GET" && request.method !== "HEAD") {
      const arrayBuf = await request.arrayBuffer();
      if (arrayBuf.byteLength > 0) {
        body = arrayBuf;
      }
    }

    const backendResponse = await fetch(targetUrl, {
      method: request.method,
      headers: forwardHeaders,
      body,
      cache: "no-store",
    });

    const responseHeaders = new Headers();

    const resContentType = backendResponse.headers.get("content-type");
    if (resContentType) {
      responseHeaders.set("content-type", resContentType);
    }
    responseHeaders.set("cache-control", "no-store");

    const setCookie = backendResponse.headers.get("set-cookie");
    if (setCookie) {
      responseHeaders.set("set-cookie", setCookie);
    }

    const isNoContent =
      backendResponse.status === 204 ||
      backendResponse.status === 205 ||
      backendResponse.status === 304;

    const responseBody = isNoContent ? null : await backendResponse.arrayBuffer();

    return new NextResponse(responseBody, {
      status: backendResponse.status,
      headers: responseHeaders,
    });
  } catch (error) {
    return NextResponse.json(
      { detail: error instanceof Error ? error.message : "API proxy error." },
      { status: 500 }
    );
  }
}

export const GET = forwardRequest;
export const POST = forwardRequest;
export const PUT = forwardRequest;
export const PATCH = forwardRequest;
export const DELETE = forwardRequest;
export const HEAD = forwardRequest;
export const OPTIONS = forwardRequest;
