const DEFAULT_BASE_URL = "http://127.0.0.1:8000/api";
const ACCESS_TOKEN_KEY = "afyora_access_token";
const REFRESH_TOKEN_KEY = "afyora_refresh_token";
const DEFAULT_INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000;

const ACTIVITY_EVENTS = [
  "mousemove",
  "mousedown",
  "keydown",
  "scroll",
  "touchstart",
  "click",
];

function buildUrl(baseUrl, path, query) {
  const url = new URL(`${baseUrl.replace(/\/$/, "")}/${path.replace(/^\//, "")}`);
  if (query) {
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
  }
  return url.toString();
}

function getAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

function setTokens({ accessToken, refreshToken }) {
  if (accessToken) {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  }
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
}

function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

async function request({
  baseUrl = DEFAULT_BASE_URL,
  path,
  method = "GET",
  body,
  query,
  token,
  headers = {},
}) {
  const resolvedToken = token || getAccessToken();
  const requestHeaders = {
    "Content-Type": "application/json",
    ...headers,
  };

  if (resolvedToken) {
    requestHeaders.Authorization = `Bearer ${resolvedToken}`;
  }

  const response = await fetch(buildUrl(baseUrl, path, query), {
    method,
    headers: requestHeaders,
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    data = await response.json();
  }

  if (!response.ok) {
    const error = new Error("API request failed");
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

export function createUsersApi(options = {}) {
  const baseUrl = options.baseUrl || DEFAULT_BASE_URL;
  const inactivityTimeoutMs = options.inactivityTimeoutMs || DEFAULT_INACTIVITY_TIMEOUT_MS;
  const onSessionExpired =
    typeof options.onSessionExpired === "function" ? options.onSessionExpired : null;

  let inactivityTimerId = null;
  let sessionTrackingEnabled = false;

  const activityHandler = () => {
    resetInactivityTimer();
  };

  function stopInactivityTimer() {
    if (inactivityTimerId) {
      clearTimeout(inactivityTimerId);
      inactivityTimerId = null;
    }
  }

  function bindActivityListeners() {
    if (typeof window === "undefined") {
      return;
    }
    ACTIVITY_EVENTS.forEach((eventName) => {
      window.addEventListener(eventName, activityHandler, true);
    });
  }

  function unbindActivityListeners() {
    if (typeof window === "undefined") {
      return;
    }
    ACTIVITY_EVENTS.forEach((eventName) => {
      window.removeEventListener(eventName, activityHandler, true);
    });
  }

  function startInactivitySession(customTimeoutMs) {
    sessionTrackingEnabled = true;
    bindActivityListeners();
    resetInactivityTimer(customTimeoutMs);
  }

  function stopInactivitySession() {
    sessionTrackingEnabled = false;
    stopInactivityTimer();
    unbindActivityListeners();
  }

  function resetInactivityTimer(customTimeoutMs) {
    if (!sessionTrackingEnabled) {
      return;
    }
    stopInactivityTimer();

    const timeoutMs = customTimeoutMs || inactivityTimeoutMs;
    inactivityTimerId = setTimeout(async () => {
      await api.logout({
        reason: "inactive",
      });
      if (onSessionExpired) {
        onSessionExpired();
      }
    }, timeoutMs);
  }

  let api = null;

  api = {
    getAccessToken,
    getRefreshToken,
    setTokens,
    clearTokens,

    // Auth
    async login({ email, password, rememberMe = true }) {
      const result = await request({
        baseUrl,
        path: "auth/login/",
        method: "POST",
        body: {
          email,
          password,
          remember_me: rememberMe,
        },
      });

      setTokens({
        accessToken: result.access_token,
        refreshToken: result.refresh_token,
      });

      startInactivitySession();

      return result;
    },

    async logout({ reason = "manual" } = {}) {
      try {
        if (getAccessToken()) {
          await request({
            baseUrl,
            path: "auth/logout/",
            method: "POST",
            body: { reason },
          });
        }
      } catch (error) {
        // Local token clear must still happen even if backend logout fails.
      } finally {
        stopInactivitySession();
        clearTokens();
      }
    },

    startInactivitySession,
    stopInactivitySession,
    resetInactivityTimer,

    // Users
    getProfile() {
      return request({ baseUrl, path: "users/profile/" });
    },

    listUsers(params = {}) {
      return request({ baseUrl, path: "users/", query: params });
    },

    getUser(userId) {
      return request({ baseUrl, path: `users/${userId}/` });
    },

    createUser(payload) {
      return request({
        baseUrl,
        path: "users/",
        method: "POST",
        body: payload,
      });
    },

    updateUser(userId, payload) {
      return request({
        baseUrl,
        path: `users/${userId}/`,
        method: "PUT",
        body: payload,
      });
    },

    deactivateUser(userId) {
      return request({
        baseUrl,
        path: `users/${userId}/`,
        method: "DELETE",
      });
    },

    listStaff() {
      return request({ baseUrl, path: "users/staff/" });
    },

    changePassword(userId, payload) {
      return request({
        baseUrl,
        path: `users/${userId}/change_password/`,
        method: "POST",
        body: payload,
      });
    },
  };

  return api;
}
