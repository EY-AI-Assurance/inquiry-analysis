const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MULTIPART_OVERHEAD_BYTES = 1024 * 1024;
const DEFAULT_UPSTREAM_TIMEOUT_SECONDS = 660;

function upstreamTimeoutMs() {
  const configured = Number(
    process.env.BACKEND_ANALYSIS_TIMEOUT_SECONDS ??
      DEFAULT_UPSTREAM_TIMEOUT_SECONDS,
  );
  const seconds = Number.isFinite(configured)
    ? Math.min(3_660, Math.max(60, configured))
    : DEFAULT_UPSTREAM_TIMEOUT_SECONDS;
  return seconds * 1_000;
}

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
  const timeoutMs = upstreamTimeoutMs();
  const timeoutId = setTimeout(() => timeout.abort(), timeoutMs);

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
        `分析耗时超过 ${Math.round(timeoutMs / 60_000)} 分钟，网站已停止等待。` +
          "云端分析此前可能仍在运行，请检查 Python 后端日志。",
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
