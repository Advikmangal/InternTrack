"use strict";
window.addEventListener("DOMContentLoaded", () => {
  SwaggerUIBundle({
    url: "/openapi.json",
    dom_id: "#swagger-ui",
    deepLinking: true,
    requestInterceptor: async (request) => {
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method.toUpperCase())) {
        const response = await fetch("/api/auth/me");
        if (response.ok)
          request.headers["X-CSRF-Token"] = (await response.json()).csrf;
      }
      return request;
    },
  });
});
