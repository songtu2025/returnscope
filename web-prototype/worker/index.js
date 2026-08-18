export default {
  async fetch(request, env) {
    let response = await env.ASSETS.fetch(request);
    const acceptsHtml = request.headers.get("accept")?.includes("text/html");

    if (
      response.status === 404 &&
      acceptsHtml &&
      ["GET", "HEAD"].includes(request.method)
    ) {
      const indexUrl = new URL(request.url);
      indexUrl.pathname = "/index.html";
      indexUrl.search = "";
      response = await env.ASSETS.fetch(new Request(indexUrl, request));
    }

    if (response.headers.get("content-type")?.includes("text/html")) {
      const html = (await response.text()).replaceAll(
        "__SITE_ORIGIN__",
        new URL(request.url).origin,
      );
      return new Response(html, response);
    }
    return response;
  },
};
