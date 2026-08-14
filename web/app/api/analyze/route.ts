const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MULTIPART_OVERHEAD_BYTES = 1024 * 1024;
const UPSTREAM_TIMEOUT_MS = 180_000;

function errorResponse(status: number, code: string, message: string) {
  return Response.json({ error: { code, message } }, { status });
}

export async function POST(request: Request) {
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().startsWith("multipart/form-data")) {
    return errorResponse(
      415,
      "INVALID_CONTENT_TYPE",
      "分析请求必须使用 multipart/form-data 上传文件。",
    );
  }

  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (
    Number.isFinite(contentLength) &&
    contentLength > MAX_FILE_BYTES + MULTIPART_OVERHEAD_BYTES
  ) {
    return errorResponse(413, "FILE_TOO_LARGE", "单个文件不能超过 50 MB。");
  }

  const baseUrl = process.env.BACKEND_BASE_URL?.replace(/\/+$/, "");
  const appToken = process.env.BACKEND_APP_TOKEN;
  if (!baseUrl || !appToken) {
    return errorResponse(
      503,
      "BACKEND_NOT_CONFIGURED",
      "Python 后端尚未配置。请检查网站服务端环境变量。",
    );
  }

  const timeout = new AbortController();
  const timeoutId = setTimeout(() => timeout.abort(), UPSTREAM_TIMEOUT_MS);

  try {
    const upstreamHeaders: Record<string, string> = {
      "content-type": contentType,
      "x-app-token": appToken,
    };
    const init: RequestInit & { duplex?: "half" } = {
      method: "POST",
      headers: upstreamHeaders,
      body: request.body,
      signal: timeout.signal,
      duplex: "half",
    };
    const upstream = await fetch(`${baseUrl}/analyze`, init);

    const headers = new Headers();
    headers.set(
      "content-type",
      upstream.headers.get("content-type") ?? "application/json; charset=utf-8",
    );
    headers.set("cache-control", "no-store");

    return new Response(upstream.body, {
      status: upstream.status,
      headers,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      return errorResponse(
        504,
        "BACKEND_TIMEOUT",
        "分析耗时超过 3 分钟，请稍后重试或上传更精简的文件。",
      );
    }
    return errorResponse(
      502,
      "BACKEND_UNREACHABLE",
      "暂时无法连接 Python 后端，请确认本地后端已启动。",
    );
  } finally {
    clearTimeout(timeoutId);
  }
}
